# OnlineShop

An online clothing shop built from [`Software_Requirements_Specification.md`](Software_Requirements_Specification.md).

- **Frontend:** plain HTML, CSS and JavaScript (`frontend/`)
- **Backend:** Python + FastAPI with SQLite storage (`backend/`)

## Quick start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. FastAPI serves both the API (`/api/...`) and the frontend pages,
so there is nothing else to start. Interactive API docs are at <http://localhost:8000/docs>.

On first start the database (`backend/data/shop.db`) is created with demo accounts and 16 demo
products in four categories. Delete `backend/data/` and `backend/uploads/` to reset everything.

### Demo accounts (development only)

| Role          | Username | Password   |
|---------------|----------|------------|
| Administrator | `admin`  | `admin123` |
| Customer      | `alice`  | `alice123` |
| Customer      | `bob`    | `bob12345` |

These passwords are public, so the server logs a warning at start-up while any of them is still in
use. They are only created when demo data is enabled (the default for local development).

### Managing accounts (FR3, FR54)

There is no registration or account page in the web interface. Accounts are managed from the
`backend` directory with:

```bash
python -m app.accounts create carol --role customer --name "Carol"   # prompts for the password
python -m app.accounts set-password carol                            # also logs carol out everywhere
python -m app.accounts list
```

Passwords must be 8–128 characters, contain a letter and a digit, and differ from the username.

### Running the tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## Pages

| Page            | Who           | Requirements |
|-----------------|---------------|--------------|
| `index.html`    | everyone      | Login with Administrator / Customer selection (FR1–FR4) |
| `admin.html`    | administrator | Product list with search, category filter, sorting and pages; add, view, edit, delete; images; categories (FR7–FR14, FR60–FR66) |
| `shop.html`     | customer      | Product grid with search, category/price/size/stock filters, sorting and pages, all kept in the URL (FR15–FR16, FR63–FR66) |
| `product.html`  | customer      | Image gallery, description, category, size & quantity selection, Add to Cart, Buy Now (FR17–FR20, FR27, FR33, FR62) |
| `cart.html`     | customer      | Cart with quantity updates, removal, live prices, warnings (FR21–FR26, FR30, FR34) |
| `checkout.html` | customer      | Shared order summary for cart and Buy Now, stock revalidation (FR28–FR31) |
| `payment.html`  | customer      | Order summary, amount payable and **Place Order**; payment itself is out of scope (FR32, FR41–FR43) |
| `orders.html`   | customer      | My Orders: order history (FR46) |
| `order.html`    | customer      | Order details, confirmation after placing, cancellation (FR45, FR47, FR48) |
| `admin-orders.html` | administrator | Order Management: list, filter, search, details, status changes (FR47–FR49) |

Every page checks the user's role and the API enforces it again (FR5); all pages have a Log out button (FR6).

## How some requirements are handled

- **Validation (FR13):** name and 1–8 images required, price > 0 with at most two decimals, stock is
  a non-negative whole number, sizes limited to S/M/L/XL, at least one size, description up to
  2,000 characters, category must exist. Checked in the browser for quick feedback and always
  re-checked by the server.
- **Images (FR14, FR62):** JPEG, PNG, GIF or WEBP up to 5 MB each; the server checks the file's
  actual contents. Each image is uploaded on its own request (`POST /api/admin/images`) as soon as
  it is chosen, so no request exceeds the 6 MB limit; saving the product (JSON, with `image_ids`)
  attaches them in order, the first being the main image. Removed images are deleted after the save
  (unless an order still shows them), and uploads never attached are deleted after 24 hours.
- **Catalogue (FR60–FR67):** categories are managed on the Product Management page; deleting one
  leaves its products uncategorised. Search matches names and descriptions with full Unicode case
  folding (a `casefold()` SQL function registered on each connection). Filtering, sorting, counting
  and paging all happen in SQL, and only the requested page is loaded: 12 products per page for
  customers, 20 for administrators.
- **Cart (FR19–FR25):** stored on the server per customer. Adding the same product and size again
  merges the entries; quantities can never exceed the stock for that size.
- **Prices (FR25, FR30):** cart and checkout always use the product's *current* price.
- **Stock checks (FR29, FR33):** out-of-stock sizes cannot be selected; the checkout summary is
  rebuilt from current data when the page loads and again when you click *Continue to Payment*.
- **Deleted products (FR34):** cart entries for deleted products (or removed sizes) stay visible,
  marked as unavailable, and block checkout until removed.
- **Orders (FR41–FR44):** *Place Order* revalidates stock and prices and then, in one database
  transaction holding SQLite's write lock, deducts stock, creates the order and clears the ordered
  cart items. If anything is invalid nothing changes. The order is only placed for the total the
  customer saw; a repeated submission (double click, retry) returns the order already placed.
- **Order records (FR45):** items store the name, image, size and price at order time, so later
  product edits or deletion do not change past orders; images used by orders are kept.
- **Statuses (FR47, FR48):** Placed → Shipped → Completed, or Placed → Cancelled (by the customer
  or an administrator), which returns the items to stock. Every change is kept in the status history.
- **Payment (FR32):** still out of scope — orders are placed without taking any payment.

## Running in production

| Variable | Production value | Purpose |
|----------|------------------|---------|
| `SHOP_SEED_DEMO_DATA` | `0` | Do not create demo accounts/products (FR54). Create real accounts with `python -m app.accounts`. |
| `SHOP_COOKIE_SECURE` | `1` | Mark cookies `Secure` and send HSTS (FR56). |
| `SHOP_DB_PATH`, `SHOP_UPLOAD_DIR` | persistent paths | Where the database and uploaded images live. |

Serve the app only over HTTPS, e.g. behind a reverse proxy (nginx, Caddy) that terminates TLS and
forwards to uvicorn. Make sure the proxy passes the original `Host` header through, because the
cross-site check (FR52) compares it with the browser's `Origin`.

The login throttle counts failures per client address. Behind a reverse proxy, run uvicorn with
`--proxy-headers --forwarded-allow-ips=<proxy address>` so the real client address is used;
otherwise every visitor appears to come from the proxy.

## Security (SRS Section 9)

- **Sessions (FR51):** the session id is only in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` over
  HTTPS); the database stores only its SHA-256 hash. Page scripts never see it.
- **CSRF (FR52):** every state-changing request must send the session's anti-forgery token in the
  `X-CSRF-Token` header (the page copies it from the readable `shop_csrf` cookie), and requests
  whose `Origin`/`Referer` is another site are rejected — including login.
- **Login throttling (FR53):** 5 failures per username or 30 per client address within 15 minutes
  lock further attempts for up to 15 minutes, with the same message whether the user exists or not.
- **Headers (FR55):** a strict Content Security Policy (no inline scripts or styles), no framing,
  `nosniff`, `Referrer-Policy: same-origin`, and HSTS over HTTPS.
- **Limits and errors (FR57, FR58):** request bodies over 6 MB get 413; unexpected errors return a
  generic message and are logged with details.
- **Logging (FR59):** logins, failures, lockouts, logouts, password changes and rejected security
  checks are logged by the `onlineshop.security` logger, never with passwords or tokens.

## Project layout

```
backend/
  app/
    main.py              FastAPI app, static file mounts
    config.py            settings (env vars: SHOP_DB_PATH, SHOP_UPLOAD_DIR, ...)
    database.py          SQLite schema and connections
    security.py          password hashing, cookie sessions, CSRF check, role checks
    login_throttle.py    login throttling per username and client address
    web_security.py      origin check, security headers, request size limit, error responses
    accounts.py          account command (create users, set passwords)
    seed.py              demo accounts and demo products
    products.py          catalogue queries (search, filters, sorting, pages) and validation
    product_images.py    staged image uploads, attaching to products, cleanup
    orders.py            cart / checkout pricing and stock evaluation
    order_service.py     order placement, cancellation, status changes
    images.py            image upload validation and storage
    errors.py            uniform JSON error responses
    routers/             auth, admin_products, admin_orders, catalog (categories), shop (products, cart, checkout), orders
  tests/                 pytest suite
frontend/
  *.html                 pages
  css/style.css
  js/                    common helpers + one script per page
```

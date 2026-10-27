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

On first start the database (`backend/data/shop.db`) is created with the preconfigured accounts
and six demo products. Delete `backend/data/` and `backend/uploads/` to reset everything.

### Preconfigured accounts (FR3 — no self-registration)

| Role          | Username | Password   |
|---------------|----------|------------|
| Administrator | `admin`  | `admin123` |
| Customer      | `alice`  | `alice123` |
| Customer      | `bob`    | `bob123`   |

Accounts are defined in `backend/app/seed.py`.

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
| `admin.html`    | administrator | Product list, search, add, view, edit, delete, image upload (FR7–FR14) |
| `shop.html`     | customer      | Product grid with case-insensitive search (FR15–FR16) |
| `product.html`  | customer      | Details, size & quantity selection, Add to Cart, Buy Now (FR17–FR20, FR27, FR33) |
| `cart.html`     | customer      | Cart with quantity updates, removal, live prices, warnings (FR21–FR26, FR30, FR34) |
| `checkout.html` | customer      | Shared order summary for cart and Buy Now, stock revalidation (FR28–FR31) |
| `payment.html`  | customer      | Order summary and amount payable; payment itself is out of scope (FR32) |

Every page checks the user's role and the API enforces it again (FR5); all pages have a Log out button (FR6).

## How some requirements are handled

- **Validation (FR13):** name and image required, price > 0 with at most two decimals, stock is a
  non-negative whole number, sizes limited to S/M/L/XL, at least one size. Checked in the browser
  for quick feedback and always re-checked by the server.
- **Images (FR14):** JPEG, PNG, GIF or WEBP up to 5 MB. The server checks the file's actual
  contents, not just its name, and returns a clear error otherwise. Replacing an image removes the old file.
- **Cart (FR19–FR25):** stored on the server per customer. Adding the same product and size again
  merges the entries; quantities can never exceed the stock for that size.
- **Prices (FR25, FR30):** cart and checkout always use the product's *current* price.
- **Stock checks (FR29, FR33):** out-of-stock sizes cannot be selected; the checkout summary is
  rebuilt from current data when the page loads and again when you click *Continue to Payment*.
- **Deleted products (FR34):** cart entries for deleted products (or removed sizes) stay visible,
  marked as unavailable, and block checkout until removed.
- **Payment (FR32):** the payment page shows the order summary and total only. No order is created
  and stock is not reduced.

## Project layout

```
backend/
  app/
    main.py              FastAPI app, static file mounts
    config.py            settings (env vars: SHOP_DB_PATH, SHOP_UPLOAD_DIR, ...)
    database.py          SQLite schema and connections
    security.py          password hashing, session tokens, role checks
    seed.py              preconfigured accounts and demo products
    products.py          product queries and validation
    orders.py            cart / checkout pricing and stock evaluation
    images.py            image upload validation and storage
    errors.py            uniform JSON error responses
    routers/             auth, admin_products, shop (products, cart, checkout)
  tests/                 pytest suite
frontend/
  *.html                 pages
  css/style.css
  js/                    common helpers + one script per page
```

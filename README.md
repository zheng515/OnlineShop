# OnlineShop

An online clothing shop built from [`Software_Requirements_Specification.md`](Software_Requirements_Specification.md).

- **Frontend:** plain HTML, CSS and JavaScript (`frontend/`)
- **Backend:** Python + FastAPI (`backend/`), on **PostgreSQL** in production or **SQLite** for local
  development, with schema migrations by Alembic
- **Deployment:** Docker image and docker compose (app + PostgreSQL); CI on GitHub Actions

## Quick start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -c requirements.lock
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. FastAPI serves both the API (`/api/...`) and the frontend pages,
so there is nothing else to start. Interactive API docs are at <http://localhost:8000/docs>.

On first start the SQLite database (`backend/data/shop.db`) is created and migrated automatically,
with demo accounts and 16 demo products in four categories. Delete `backend/data/` and
`backend/uploads/` to reset everything. To develop against PostgreSQL instead, set
`SHOP_DATABASE_URL=postgresql://user:password@localhost:5432/shop`.

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

### Running the tests and checks (FR74, FR75)

```bash
cd backend
pip install -r requirements-dev.txt -c requirements.lock
pytest                                   # on SQLite
SHOP_TEST_DATABASE_URL=postgresql://shop:shop@localhost:5432/shop_test pytest   # on PostgreSQL
cd .. && ruff check .                    # static checks
```

The PostgreSQL run needs an empty database the user may create schemas in; each test gets its own
schema, dropped afterwards. One way to get one:
`docker run -d -e POSTGRES_USER=shop -e POSTGRES_PASSWORD=shop -e POSTGRES_DB=shop_test -p 5432:5432 postgres:16`.

Browser (end-to-end) tests start their own server with demo data and drive Chromium:

```bash
cd e2e
pip install -r requirements.txt -c ../backend/requirements.lock
python -m playwright install --with-deps chromium
pytest
```

They fail on any JavaScript error or Content Security Policy violation. Set
`E2E_CHROMIUM_EXECUTABLE` to use an already installed Chromium instead.

## Pages

| Page            | Who           | Requirements |
|-----------------|---------------|--------------|
| `index.html`    | everyone      | Login with Administrator / Customer selection (FR1–FR4) |
| `admin.html`    | administrator | Product list with search, category filter, sorting and pages; add, view, edit, delete; images; categories (FR7–FR14, FR60–FR66) |
| `shop.html`     | customer      | Product grid with search, category/price/size/stock filters, sorting and pages, all kept in the URL (FR15–FR16, FR63–FR66) |
| `product.html`  | customer      | Image gallery, description, category, size & quantity selection, Add to Cart, Buy Now (FR17–FR20, FR27, FR33, FR62) |
| `cart.html`     | customer      | Cart with quantity updates, removal, live prices, warnings (FR21–FR26, FR30, FR34) |
| `checkout.html` | customer      | Shared order summary for cart and Buy Now, stock revalidation (FR28–FR31) |
| `payment.html`  | customer      | Order summary, amount payable and **Place Order and Pay** (FR32, FR41–FR43) |
| `mock-pay.html` | anyone with the link | The mock payment provider's own page (FR84) |
| `orders.html`   | customer      | My Orders: order history, time left to pay (FR46, FR86) |
| `order.html`    | customer      | Order details, payment result, **Pay now** with countdown, payments and refunds, cancellation (FR45–FR48, FR78–FR86) |
| `admin-orders.html` | administrator | Order Management: list, filter, search, details, payments and refunds, status changes, refund retry (FR47–FR49, FR82) |

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
- **Statuses (FR47, FR48):** Awaiting payment → Paid → Shipped → Completed. An order can be
  cancelled while awaiting payment (by the customer, an administrator, or the payment deadline) or
  once paid (by the customer or an administrator, with a full refund); the items go back to stock.
  Every change is a guarded `UPDATE … WHERE status = <expected>`, so two simultaneous changes cannot
  both succeed, and every change is kept in the status history.

## Payments (SRS Section 12)

Placing an order holds its items and sends the customer to the payment provider's page. The order
becomes **Paid** only when the provider's signed notification confirms the payment; returning to
the shop proves nothing. Unpaid orders are cancelled 30 minutes after they were placed, and their
items go back to stock.

```
Place Order and Pay ─▶ order "Awaiting payment" (stock held, deadline set)
        │
        ▼
provider page ── declined / left ──▶ back to the order: "Pay now" until the deadline
        │ paid
        ▼
signed notification ─▶ verified, processed once ─▶ order "Paid"
                                     └─ order already cancelled or paid ─▶ automatic refund
```

- **Mock provider (FR84):** `SHOP_PAYMENT_PROVIDER=mock` (the only provider so far) is a built-in
  stand-in with its own page (`mock-pay.html`), sessions that expire with the order, signed
  notifications and refunds. It moves no money; its page and the shop's payment page say so, and the
  server logs a warning at start-up. On its page you choose to pay, to simulate a declined payment,
  or to cancel. It delivers its notification by calling the same handler that
  `POST /api/payments/webhooks/mock` uses.
- **Notifications (FR81):** HMAC-SHA256 signature over `"<timestamp>.<body>"` with
  `SHOP_PAYMENT_WEBHOOK_SECRET`, rejected if older than 5 minutes, processed once per event id
  (also when copies arrive at the same time), and the amount and currency must match.
- **Deadline (FR79):** every server worker runs a job every `SHOP_JOB_INTERVAL_SECONDS` that cancels
  overdue orders, and opening an overdue order cancels it at once. `python -m app.jobs` does the
  same from cron. A payment confirmed after cancellation is refunded automatically, and so is a second
  payment for an order that is already paid.
- **Refunds (FR82):** cancelling a paid order refunds it in full. A refund the provider rejects is
  shown to administrators with **Retry refund**; a payment can never be refunded twice (unique
  constraint).
- **Adding a real provider (FR85):** implement the `PaymentProvider` interface in
  `app/payments/provider.py` (start a payment, page URL, is it still usable, parse and verify a
  notification, refund), return it from `get_provider`, and set the provider's secret in
  `SHOP_PAYMENT_WEBHOOK_SECRET`. The order logic in `app/payments/service.py` stays the same.
- **Earlier orders (FR87):** orders with the old status *Placed* became *Paid* in migration 0002;
  cancelling them refunds nothing, because nothing was paid through the shop.

## Deployment (SRS Section 11)

### With Docker (FR71)

```bash
cp .env.example .env          # set POSTGRES_PASSWORD (letters and digits)
docker compose up -d --build  # app on port 8000, PostgreSQL, persistent volumes
docker compose exec app python -m app.accounts create admin --role admin   # first administrator
```

The container runs as a non-root user, applies pending migrations before starting two uvicorn
workers, and reports its health at `/api/health` (FR72), which Docker uses for its health check.
Demo data is off and cookies are `Secure` by default. For a local trial with demo accounts over
plain HTTP: `docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build`.

Building behind a TLS-inspecting proxy: pass its CA bundle with
`docker build --secret id=ca_bundle,src=/path/to/ca.crt -t onlineshop:latest .` and then
`docker compose up -d --no-build`.

Serve the app only over HTTPS (FR56), behind a reverse proxy (nginx, Caddy, a load balancer) that
terminates TLS, passes the original `Host` header (the cross-site check compares it with the
browser's `Origin`), and sets `X-Forwarded-For`. Set `FORWARDED_ALLOW_IPS` to the proxy's address so
the login throttle sees real client addresses rather than the proxy's.

### Configuration (FR70)

| Variable | Default | Purpose |
|----------|---------|---------|
| `SHOP_DATABASE_URL` | SQLite at `SHOP_DB_PATH` | `postgresql://user:password@host:5432/db` or `sqlite:////abs/path.db` |
| `SHOP_DB_PATH` | `backend/data/shop.db` | SQLite file used when no database URL is set |
| `SHOP_UPLOAD_DIR` | `backend/uploads` | Uploaded product images (keep on persistent storage) |
| `SHOP_SEED_DEMO_DATA` | `1` (container: `0`) | Create demo accounts and products once (FR54) |
| `SHOP_COOKIE_SECURE` | `0` (container: `1`) | `Secure` cookies and HSTS; required over HTTPS (FR56) |
| `SHOP_AUTO_MIGRATE` | `1` (container: `0`) | Apply migrations at start-up; when `0` the server refuses an outdated schema |
| `SHOP_TOKEN_TTL_HOURS` | `8` | Session lifetime (FR36) |
| `SHOP_PAYMENT_PROVIDER` | `mock` | Payment provider (FR85); `mock` moves no money (FR84) |
| `SHOP_PAYMENT_TIMEOUT_MINUTES` | `30` | Time to pay before an order is cancelled (FR79) |
| `SHOP_PAYMENT_WEBHOOK_SECRET` | random per start | Secret for verifying payment notifications (FR81); set it to the provider's value with a real provider |
| `SHOP_CURRENCY` | `USD` | Currency sent to the payment provider |
| `SHOP_JOB_INTERVAL_SECONDS` | `60` | How often overdue unpaid orders are cancelled; `0` turns the job off |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxy addresses whose `X-Forwarded-For` uvicorn trusts |

### Schema migrations (FR69)

Migrations live in `backend/migrations/versions/` and run with
`python -m app.migrations upgrade` (`check` exits 1 when migrations are pending; `current` prints
the revision). They are safe to start from several processes at once (PostgreSQL advisory lock,
a file lock for SQLite). SQLite databases created before migrations existed are recognised,
brought to the rev. 5 structure and stamped automatically. To change the schema, add a new revision
(`alembic revision -m "..."` from `backend/`) and write portable SQL — see `app/database.py`.

**SQLite vs PostgreSQL (FR68):** the application uses the same SQL on both. Case-insensitive search
uses Python's `casefold()` on SQLite and `lower()` on PostgreSQL, so on PostgreSQL "ß" does not match
"ss"; PostgreSQL needs a UTF-8 locale (the compose file sets one) for non-English letters to fold.

### Backups (FR73)

Back up the database and the uploaded images together:

```bash
docker compose exec -T db pg_dump -U shop -d shop --format=custom > shop-$(date +%F).dump
docker run --rm -v onlineshop_uploads:/data:ro -v "$PWD":/backup busybox:1.37 \
  tar czf /backup/uploads-$(date +%F).tgz -C /data .
```

(`onlineshop_uploads` is the compose volume name; it is prefixed with the project directory name.)

Check a backup by restoring it into a scratch database and looking at the data:

```bash
docker compose exec -T db createdb -U shop shop_restore_check
docker compose exec -T db pg_restore -U shop -d shop_restore_check --no-owner < shop-2026-11-19.dump
docker compose exec -T db psql -U shop -d shop_restore_check -c "SELECT count(*) FROM products"
docker compose exec -T db dropdb -U shop shop_restore_check
```

Restore after data loss:

```bash
docker compose stop app
docker compose exec -T db pg_restore -U shop -d shop --clean --if-exists --no-owner < shop-2026-11-19.dump
docker run --rm -v onlineshop_uploads:/data -v "$PWD":/backup busybox:1.37 \
  sh -c "rm -rf /data/* && tar xzf /backup/uploads-2026-11-19.tgz -C /data"
docker compose start app      # applies any migrations newer than the backup
```

With SQLite, copy the database while the server runs with `sqlite3 shop.db ".backup shop-backup.db"`
and archive the upload folder.

### Continuous integration (FR76)

`.github/workflows/ci.yml` runs on every push and pull request: ruff and JavaScript syntax checks,
a migration check, the backend tests on SQLite and on PostgreSQL, the browser tests, and a
container build that is started with PostgreSQL and must report healthy. Make the **CI passed**
job a required status check in the repository's branch protection so only green changes merge.

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
    config.py            settings from environment variables
    database.py          connections and portable SQL for SQLite and PostgreSQL
    migrations.py        migration commands, legacy database adoption
    legacy_schema.py     upgrade path for pre-migration SQLite databases
    security.py          password hashing, cookie sessions, CSRF check, role checks
    login_throttle.py    login throttling per username and client address
    web_security.py      origin check, security headers, request size limit, error responses
    accounts.py          account command (create users, set passwords)
    seed.py              demo accounts and demo products
    products.py          catalogue queries (search, filters, sorting, pages) and validation
    product_images.py    staged image uploads, attaching to products, cleanup
    orders.py            cart / checkout pricing and stock evaluation
    order_service.py     order placement, statuses, cancellation, refund records
    payments/            provider interface, mock provider, payment service (notifications, refunds, deadline)
    jobs.py              background job: cancel orders whose payment deadline passed
    images.py            image upload validation and storage
    errors.py            uniform JSON error responses
    routers/             auth, admin_products, admin_orders, catalog (categories), health, shop, orders, payments
  migrations/            Alembic environment and numbered migration scripts
  tests/                 pytest suite (SQLite and PostgreSQL)
  requirements*.txt      pinned dependencies; requirements.lock pins everything (FR77)
e2e/                     Playwright browser tests (FR74)
frontend/
  *.html                 pages
  css/style.css
  js/                    common helpers + one script per page
Dockerfile, docker-compose*.yml, .env.example
.github/workflows/ci.yml
```

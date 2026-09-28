# Plately Architecture

## System overview

Plately is a server-rendered Django application. The `delivery` Python package
contains the application code; Django retains the `FoodHub` app label to match
existing database tables and migration records. Local settings use SQLite.

```text
Browser
  -> Foodly project URL configuration
       -> delivery URL routes
            -> views and session checks
                 -> Django ORM -> SQLite
                 -> shared templates -> HTML
                 -> Razorpay Python SDK -> order and payment APIs
```

## Project map

```text
Foodly/
+-- CHANGES.txt
+-- requirements.txt
+-- .env.example
+-- db.sqlite3
+-- manage.py
+-- Foodly/                      # Django project settings and URLs
+-- docs/                        # PRD, architecture, rules, design, memory
+-- delivery/
|   +-- models.py                # accounts, catalog, cart, orders
|   +-- views.py                 # workflows, validation, payment checks
|   +-- urls.py                  # named app routes
|   +-- context_processors.py    # signed-in navigation context
|   +-- management/commands/     # repeatable catalog import command
|   +-- data/catalog/            # curated restaurant and dish CSV data
|   +-- tests.py                 # request and payment-flow tests
|   +-- migrations/              # historical FoodHub migration label
|   +-- Templates/delivery/      # shared base and page templates
|   +-- static/FoodHub/          # stylesheet and downloadable import template
+-- myenv/                       # local Python environment; do not commit
```

The project keeps its existing layout. `settings.py` explicitly registers the
capitalized `delivery/Templates` directory, and the legacy `FoodHub` app label
is preserved for schema continuity.

## Main modules

- **`Foodly/settings.py`:** loads local `.env` values, configures Django apps,
  middleware, SQLite, template lookup, static files, and Razorpay settings.
- **`Foodly/urls.py`:** exposes Django admin and includes `delivery.urls`.
- **`delivery/urls.py`:** names routes for public pages, customer workflows,
  catalog administration, checkout, payment verification, and order history.
- **`delivery/views.py`:** validates form input, checks the custom customer
  session, coordinates catalog/cart/order changes, accepts admin CSV uploads,
  and verifies payment.
- **`delivery/management/commands/import_catalog.py`:** validates a complete
  CSV before a transaction; case-insensitive matching updates existing
  restaurants and dishes, while absent rows are preserved.
- **`delivery/context_processors.py`:** resolves the current customer for
  shared navigation and identifies the reserved catalog-admin account.
- **`delivery/models.py`:** stores customers, restaurants, menu entries, carts,
  orders, and purchase-line snapshots.
- **`delivery/Templates/delivery/base.html`:** supplies global navigation,
  messages, footer, brand, and the shared stylesheet to every page.
- **`delivery/static/FoodHub/styles.css`:** provides design tokens, responsive
  grids, forms, cards, tables, notices, cart, and confirmation styles.
- **`delivery/tests.py`:** exercises rendering, account/session behavior,
  catalog access, search, cart changes, and payment outcomes.

## Data model

| Model | Purpose | Key relationships and fields |
| --- | --- | --- |
| `Customer` | Account and delivery details | Username, password hash, email, mobile, address |
| `Restaurant` | Discoverable restaurant | Name, image URL, cuisine, rating |
| `Item` | Menu dish | Restaurant, name, description, decimal price, vegetarian flag, image URL |
| `Cart` | Current selection | Customer and many-to-many menu items; no quantity field |
| `Order` | Payment and order state | Customer, unique provider order ID, payment ID, status, total, address snapshot |
| `OrderItem` | Purchase snapshot | Order, optional source item, saved name, unit price, quantity |

The model field `vegeterian` is misspelled historically and is intentionally
left unchanged to avoid an unplanned migration. The same applies to the
`FoodHub` Django app label.

## Important workflows

### Session access

On successful password verification, the view rotates the session key and
stores the customer's ID under `customer_id`. Customer views require that ID
to match the username in the route. Catalog views require the session to belong
to the reserved `admin` account. Sign-out is POST-only and flushes the session.
This is a custom session layer, not Django's built-in user/group permission
system.

### Checkout and confirmation

1. Checkout creates a Razorpay order with an integer amount in paise.
2. The app persists a pending local `Order` and `OrderItem` snapshots.
3. Razorpay Checkout submits order ID, payment ID, and signature to a
   CSRF-protected route.
4. The Razorpay SDK verifies the signature. The view fetches provider payment
   details and checks order ID, amount, currency, and captured status.
5. A database transaction marks the order paid and removes the ordered items
   from the customer's cart. Failure leaves the order pending and cart intact.
6. Order history and confirmation read saved order records without mutating the
   cart.

## Local setup and operations

- Install dependencies with `myenv/Scripts/python.exe -m pip install -r
  requirements.txt` on Windows, or activate `myenv` and run `pip install -r
  requirements.txt` on other platforms.
- Copy `.env.example` to `.env` and configure `DJANGO_SECRET_KEY`,
  `RAZORPAY_KEY_ID`, and `RAZORPAY_KEY_SECRET`. `.env` is ignored by Git and
  must not be shared.
- Enable automatic capture for the Razorpay test account. The app confirms
  only captured payments.
- Prepare a CSV with the supplied `catalog_import_template.csv`. Check it
  without changes using
  `python manage.py import_catalog delivery/static/FoodHub/catalog_import_template.csv --dry-run`;
  omit `--dry-run` to apply it. The admin dashboard also accepts CSV uploads.
  Use only records you own or have permission to import.
- Curated Plately catalog data is stored under `delivery/data/catalog/` and can
  be validated or imported with the same `import_catalog` command.
- Apply schema changes with `python manage.py migrate`.
- Run `python manage.py check` and `python manage.py test` before accepting a
  code change.

For deployment, set `DEBUG=False`, configure allowed hosts and HTTPS cookie
settings, use production provider credentials, and replace the reserved-name
admin role with Django authentication and explicit permissions.

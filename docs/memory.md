# Plately Project Memory

Fast facts for the next contributor. Keep this file aligned with the code.

## At a glance

- **Framework:** Django with server-rendered templates; product name: Plately.
- **Project package:** `Foodly/`.
- **Application package:** `delivery/`; historical Django app label: `FoodHub`.
- **Database:** local SQLite at `Foodly/db.sqlite3`.
- **Templates and styles:** `delivery/Templates/delivery/` and
  `delivery/static/FoodHub/styles.css`.
- **Payment:** Razorpay SDK creates provider orders and verifies signatures;
  payment status is fetched and must be captured before confirmation.
- **Configuration:** local `.env` is ignored; `.env.example` documents variable
  names. Never copy actual credentials into tracked files.
- **Docs and history:** `Foodly/docs/` and `Foodly/CHANGES.txt`.

## Implementation facts

- Models are `Customer`, `Restaurant`, `Item`, `Cart`, `Order`, and `OrderItem`.
- Cart entries are unique related items with no quantities. Order lines keep
  item name and unit-price snapshots.
- New passwords are hashed; a legacy plaintext password is upgraded after a
  successful sign-in.
- The custom session stores `customer_id`. Customer routes require a matching
  username; catalog routes check for the reserved `admin` username. This is
  not Django's built-in User/Group authorization.
- Restaurant search covers restaurant name and cuisine. Catalog admins can
  add/edit/delete restaurants and menu items, or bulk-import an authorized CSV
  from the admin dashboard or `import_catalog` management command.
- The CSV importer validates all rows before an atomic upsert, preserves rows
  omitted from the file, and supports `--dry-run`. The sample CSV contains
  fictional sample data only.
- `requirements.txt` includes Django, Razorpay, python-dotenv, and a compatible
  setuptools version required by the current Razorpay SDK import.
- `delivery/tests.py` covers shared page rendering, sessions, catalog access,
  search, cart actions, order/payment states, and SDK signature verification.

## Preserve when changing the app

- Keep the `FoodHub` app label so existing migrations and table names remain
  valid. Apply new schema work through a new migration.
- Keep template discovery for the capitalized `Templates` directory in sync
  with any future template move.
- Keep the cart unchanged on incomplete or mismatched payments.
- Read `architecture.md` before changing app registration, sessions, checkout,
  or payment verification.

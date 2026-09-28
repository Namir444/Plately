# Plately Engineering Rules

These rules preserve the working project layout and keep customer flows,
catalog operations, and payment behavior understandable.

## Project organization

- Keep project settings in `Foodly/` and business behavior in the `delivery`
  app. Preserve the `FoodHub` Django app label and existing migration history
  unless a planned migration explicitly covers the database transition.
- Keep contributor documents in `docs/` and record meaningful changes in
  `CHANGES.txt`.
- Preserve the existing `delivery/Templates/` path and update Django template
  settings in the same change if it ever moves.
- Keep the local virtual environment, `.env`, SQLite database copies, and
  generated Python caches out of source control.

## Django behavior

- Use named URL routes and `reverse`/`{% url %}` rather than hard-coded paths.
- Validate submitted values before saving. Use explicit missing-record
  handling and avoid broad exception handlers.
- Use POST for every state-changing action, include a CSRF token, and check
  customer or catalog-admin access before reading or changing protected data.
- Keep money in `Decimal` fields and convert to integer paise only at the
  Razorpay API boundary.
- For bulk catalog imports, validate the entire CSV before writes, use a
  database transaction, update matching records idempotently, and never delete
  catalog entries just because they are absent from an import file.
- Hash new passwords with Django's hashers. Never add new plaintext password
  storage. Migrate legacy data deliberately.
- Treat payment callbacks as untrusted. Verify provider signature, order ID,
  amount, currency, and captured status before marking orders paid or removing
  items from a cart.
- Add schema changes as new migrations; do not edit migrations already applied
  to a developer database.

## Templates and styles

- Extend `delivery/base.html` for all product pages. Keep brand, global
  navigation, flash messages, and footer in the base template.
- Keep app assets under `delivery/static/` and reference them with Django's
  `{% static %}` tag. Continue using the `FoodHub/styles.css` static path while
  the historical app label is retained.
- Use reusable CSS classes and shared design tokens. Avoid inline styles and
  one-off page colors; maintain the responsive layout and visible focus state.
- Label form controls, use semantic headings and buttons, and include useful
  alt text for meaningful images. Let Django autoescape rendered values.
- Keep interface language warm, concise, and consistent with the Plately brand.

## Verification and documentation

- Add or update tests for behavior changes. Run `python manage.py check`,
  `python manage.py makemigrations --check --dry-run`, and `python manage.py
  test` when relevant.
- Update `prd.md`, `architecture.md`, `design.md`, and `memory.md` when the
  implemented workflows, modules, or visual system change.
- Do not store API credentials in source, templates, documentation, or the
  change log. Use ignored local environment configuration.
- Do not scrape competitor apps for catalog data. Import restaurant supplied,
  licensed, or otherwise authorized CSV data instead.

# Plately

Plately is a Django food-ordering demo. Customers can browse restaurants,
search menus, manage a cart, and use Razorpay Checkout in test mode. Catalog
data can be imported from CSV files.

This repository is intended for local demos and portfolio use, not commercial
deployment.

## Requirements

- Python 3.12 or newer
- A Razorpay account for testing checkout (optional for browsing)

## Run locally

From the project root, create and activate a virtual environment in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `DJANGO_SECRET_KEY` in `.env` to a locally generated secret. To test
checkout, also set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` to Razorpay test
credentials. Never commit `.env` or use live payment credentials for a demo.

Initialize the database and load the included catalog:

```powershell
python manage.py migrate
python manage.py import_catalog delivery/data/catalog/plately_catalog_additions.csv
python manage.py import_catalog delivery/data/catalog/plately_catalog_expansion_02.csv
```

Start the development server:

```powershell
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and create a customer account to browse and order.
Razorpay checkout requires valid test credentials; without them, online
payments remain unavailable.

## Checks

```powershell
python manage.py check
python manage.py test
```

To validate either catalog file without changing the database, add
`--dry-run` to its `import_catalog` command.

## Repository hygiene

`.env`, SQLite data, and virtual environments are excluded by `.gitignore`.
`.env.example` contains variable names only and is safe to commit. The catalog
CSV files are included so the demo data can be recreated after cloning.
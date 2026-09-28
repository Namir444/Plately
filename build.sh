#!/usr/bin/env bash
set -o errexit

python -m pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --noinput
python manage.py import_catalog delivery/data/catalog/plately_catalog_additions.csv
python manage.py import_catalog delivery/data/catalog/plately_catalog_expansion_02.csv
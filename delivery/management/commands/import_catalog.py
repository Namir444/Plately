import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import transaction

from delivery.models import Item, Restaurant


REQUIRED_COLUMNS = {
    'restaurant_name',
    'cuisine',
    'rating',
    'dish_name',
    'description',
    'price',
}
MAX_ITEM_PRICE = Decimal('99999999.99')
IMAGE_URL_VALIDATOR = URLValidator(schemes=('http', 'https'))


class Command(BaseCommand):
    help = 'Import or update restaurants and menu items from an authorized CSV file.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=Path)
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate the whole file without writing any records.',
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        try:
            with csv_file.open('r', encoding='utf-8-sig', newline='') as source:
                result = self.import_rows(source, dry_run=options['dry_run'])
        except FileNotFoundError as error:
            raise CommandError(f'CSV file not found: {csv_file}') from error
        except (OSError, UnicodeError) as error:
            raise CommandError(f'Could not read CSV file: {error}') from error
        self.stdout.write(self.style.SUCCESS(result))

    def import_rows(self, source, *, dry_run=False):
        rows = self._read_rows(source)
        if dry_run:
            restaurant_count = len({row['restaurant_key'] for row in rows})
            return (
                f'Validated {restaurant_count} restaurants and {len(rows)} dishes. '
                'No records were changed.'
            )

        counts = {'restaurants_created': 0, 'restaurants_updated': 0,
                  'dishes_created': 0, 'dishes_updated': 0}
        with transaction.atomic():
            restaurants = {
                restaurant.name.casefold(): restaurant
                for restaurant in Restaurant.objects.order_by('pk')
            }
            dishes = {
                (item.restaurant_id, item.name.casefold()): item
                for item in Item.objects.select_related('restaurant').order_by('pk')
            }

            for row in rows:
                restaurant = restaurants.get(row['restaurant_key'])
                if restaurant is None:
                    restaurant_fields = {
                        'name': row['restaurant_name'],
                        'cuisine': row['cuisine'],
                        'rating': row['rating'],
                    }
                    if row['restaurant_picture']:
                        restaurant_fields['picture'] = row['restaurant_picture']
                    restaurant = Restaurant.objects.create(**restaurant_fields)
                    restaurants[row['restaurant_key']] = restaurant
                    counts['restaurants_created'] += 1
                else:
                    changed_fields = []
                    for field in ('name', 'cuisine', 'rating'):
                        value = row['restaurant_name'] if field == 'name' else row[field]
                        if getattr(restaurant, field) != value:
                            setattr(restaurant, field, value)
                            changed_fields.append(field)
                    if row['restaurant_picture'] and restaurant.picture != row['restaurant_picture']:
                        restaurant.picture = row['restaurant_picture']
                        changed_fields.append('picture')
                    if changed_fields:
                        restaurant.save(update_fields=changed_fields)
                        counts['restaurants_updated'] += 1

                dish_key = (restaurant.pk, row['dish_key'])
                item = dishes.get(dish_key)
                if item is None:
                    item_fields = {
                        'restaurant': restaurant,
                        'name': row['dish_name'],
                        'description': row['description'],
                        'price': row['price'],
                        'vegeterian': row['vegetarian'],
                    }
                    if row['dish_picture']:
                        item_fields['picture'] = row['dish_picture']
                    item = Item.objects.create(**item_fields)
                    dishes[dish_key] = item
                    counts['dishes_created'] += 1
                else:
                    changed_fields = []
                    updates = {
                        'name': row['dish_name'],
                        'description': row['description'],
                        'price': row['price'],
                        'vegeterian': row['vegetarian'],
                    }
                    if row['dish_picture']:
                        updates['picture'] = row['dish_picture']
                    for field, value in updates.items():
                        if getattr(item, field) != value:
                            setattr(item, field, value)
                            changed_fields.append(field)
                    if changed_fields:
                        item.save(update_fields=changed_fields)
                        counts['dishes_updated'] += 1

        return (
            'Catalog import complete: '
            f"{counts['restaurants_created']} restaurants created, "
            f"{counts['restaurants_updated']} updated, "
            f"{counts['dishes_created']} dishes created, "
            f"{counts['dishes_updated']} updated."
        )

    def _read_rows(self, source):
        try:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise CommandError('The CSV file must include a header row.')
            if any(not name or not name.strip() for name in reader.fieldnames):
                raise CommandError('The CSV file contains a blank column name.')
            reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise CommandError('The CSV file contains duplicate column names.')
            missing = REQUIRED_COLUMNS.difference(reader.fieldnames)
            if missing:
                raise CommandError(
                    'Missing CSV columns: ' + ', '.join(sorted(missing))
                )
            rows = []
            dish_keys = set()
            restaurant_profiles = {}
            for line_number, raw_row in enumerate(reader, start=2):
                if None in raw_row:
                    raise CommandError(f'CSV line {line_number}: row has more values than the header.')
                if not raw_row or not any((value or '').strip() for value in raw_row.values() if isinstance(value, str)):
                    continue
                row = self._validate_row(raw_row, line_number)
                profile = restaurant_profiles.get(row['restaurant_key'])
                if profile is None:
                    restaurant_profiles[row['restaurant_key']] = {
                        'cuisine': row['cuisine'],
                        'rating': row['rating'],
                        'picture': row['restaurant_picture'],
                    }
                else:
                    if profile['cuisine'] != row['cuisine'] or profile['rating'] != row['rating']:
                        raise CommandError(
                            f'CSV line {line_number}: restaurant details must match across its dish rows.'
                        )
                    if profile['picture'] and row['restaurant_picture'] and profile['picture'] != row['restaurant_picture']:
                        raise CommandError(
                            f'CSV line {line_number}: restaurant image URL conflicts with an earlier row.'
                        )
                    if not profile['picture']:
                        profile['picture'] = row['restaurant_picture']

                dish_identity = (row['restaurant_key'], row['dish_key'])
                if dish_identity in dish_keys:
                    raise CommandError(
                        f'CSV line {line_number}: duplicate dish for this restaurant.'
                    )
                dish_keys.add(dish_identity)
                rows.append(row)
        except csv.Error as error:
            raise CommandError(f'Could not read CSV file: {error}') from error

        if not rows:
            raise CommandError('The CSV file contains no catalog rows.')
        return rows

    def _validate_row(self, raw_row, line_number):
        values = {
            key: (value or '').strip()
            for key, value in raw_row.items()
            if key is not None
        }
        restaurant_name = values.get('restaurant_name', '')
        cuisine = values.get('cuisine', '')
        dish_name = values.get('dish_name', '')
        description = values.get('description', '')
        if not all((restaurant_name, cuisine, dish_name, description, values.get('rating'), values.get('price'))):
            raise CommandError(f'CSV line {line_number}: required values cannot be blank.')
        if len(restaurant_name) > 20 or len(dish_name) > 20:
            raise CommandError(
                f'CSV line {line_number}: restaurant and dish names must be 20 characters or fewer.'
            )
        if len(cuisine) > 200 or len(description) > 200:
            raise CommandError(f'CSV line {line_number}: cuisine and descriptions must be 200 characters or fewer.')

        try:
            rating = Decimal(values['rating'])
            raw_price = Decimal(values['price'])
            price = raw_price.quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise CommandError(f'CSV line {line_number}: rating and price must be valid numbers.')
        if raw_price != price:
            raise CommandError(f'CSV line {line_number}: dish price must use no more than two decimal places.')
        if not rating.is_finite() or not Decimal('0') <= rating <= Decimal('5'):
            raise CommandError(f'CSV line {line_number}: rating must be between 0 and 5.')
        if not price.is_finite() or not Decimal('0') <= price <= MAX_ITEM_PRICE:
            raise CommandError(f'CSV line {line_number}: dish price is outside the supported range.')

        vegetarian_value = values.get('vegetarian', '').casefold()
        if vegetarian_value in ('', 'false', 'no', '0'):
            vegetarian = False
        elif vegetarian_value in ('true', 'yes', '1'):
            vegetarian = True
        else:
            raise CommandError(
                f'CSV line {line_number}: vegetarian must be true/false, yes/no, or 1/0.'
            )

        restaurant_picture = values.get('restaurant_picture', '')
        dish_picture = values.get('dish_picture', '')
        self._validate_image_url(restaurant_picture, 'restaurant_picture', line_number, 200)
        self._validate_image_url(dish_picture, 'dish_picture', line_number, 400)
        return {
            'restaurant_name': restaurant_name,
            'restaurant_key': restaurant_name.casefold(),
            'cuisine': cuisine,
            'rating': float(rating),
            'restaurant_picture': restaurant_picture,
            'dish_name': dish_name,
            'dish_key': dish_name.casefold(),
            'description': description,
            'price': price,
            'vegetarian': vegetarian,
            'dish_picture': dish_picture,
        }

    def _validate_image_url(self, value, field, line_number, max_length):
        if not value:
            return
        if len(value) > max_length:
            raise CommandError(f'CSV line {line_number}: {field} exceeds {max_length} characters.')
        try:
            IMAGE_URL_VALIDATOR(value)
        except ValidationError as error:
            raise CommandError(f'CSV line {line_number}: {field} must be an http or https URL.') from error

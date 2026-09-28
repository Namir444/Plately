import hashlib
import hmac
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import razorpay
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .management.commands.import_catalog import Command as CatalogImportCommand
from .models import Cart, Customer, Item, Order, Restaurant


class FoodlyFlowTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            username='sam',
            password=make_password('correct horse'),
            email='sam@example.test',
            mobile='9876543210',
            address='12 Market Street',
        )
        self.admin = Customer.objects.create(
            username='admin',
            password=make_password('admin password'),
            email='admin@example.test',
            mobile='9876543211',
            address='Plately HQ',
        )
        self.restaurant = Restaurant.objects.create(
            name='Good Bowl', cuisine='Indian', rating=4.5,
        )
        self.item = Item.objects.create(
            restaurant=self.restaurant,
            name='Masala Bowl',
            description='A warm spiced bowl',
            price=Decimal('12.50'),
            picture='https://example.test/bowl.jpg',
        )

    def sign_in_as(self, customer=None):
        session = self.client.session
        session['customer_id'] = (customer or self.customer).pk
        session.save()

    def make_payment_client(self, *, status='captured', amount=1250, order_id='order_test_1'):
        return SimpleNamespace(
            order=SimpleNamespace(create=Mock(return_value={'id': order_id})),
            utility=SimpleNamespace(verify_payment_signature=Mock(return_value=None)),
            payment=SimpleNamespace(fetch=Mock(return_value={
                'order_id': order_id,
                'amount': amount,
                'currency': 'INR',
                'status': status,
            })),
        )

    def make_cart(self):
        cart, _ = Cart.objects.get_or_create(customer=self.customer)
        cart.items.add(self.item)
        return cart

    def write_catalog_csv(self, rows):
        return StringIO(
            'restaurant_name,cuisine,rating,restaurant_picture,dish_name,description,price,vegetarian,dish_picture\n'
            + rows
        )

    def test_catalog_import_creates_and_idempotently_updates_records(self):
        rows = (
            'Garden Table,Mediterranean,4.6,,Lemon Rice Bowl,"Rice with lemon and herbs",8.50,true,\n'
            'Garden Table,Mediterranean,4.6,,Roasted Veg Wrap,"Seasonal vegetables in flatbread",9.00,true,\n'
        )
        importer = CatalogImportCommand()
        result = importer.import_rows(self.write_catalog_csv(rows))
        self.assertEqual(Restaurant.objects.filter(name='Garden Table').count(), 1)
        self.assertEqual(Item.objects.filter(restaurant__name='Garden Table').count(), 2)
        self.assertIn('1 restaurants created', result)

        updated_rows = rows.replace('4.6', '4.8').replace('8.50', '8.75')
        importer.import_rows(self.write_catalog_csv(updated_rows))
        restaurant = Restaurant.objects.get(name='Garden Table')
        self.assertEqual(restaurant.rating, 4.8)
        self.assertEqual(Item.objects.get(name='Lemon Rice Bowl').price, Decimal('8.75'))
        self.assertEqual(Restaurant.objects.filter(name='Garden Table').count(), 1)

    def test_catalog_import_dry_run_and_validation_do_not_write_records(self):
        good_rows = 'Garden Table,Mediterranean,4.6,,Lemon Rice Bowl,"Rice with herbs",8.50,true,\n'
        bad_rows = 'Broken Cafe,Cafe,4.2,,Oversized Dish Name That Does Not Fit,"Description",8.50,false,\n'
        importer = CatalogImportCommand()
        result = importer.import_rows(self.write_catalog_csv(good_rows), dry_run=True)
        self.assertIn('No records were changed', result)
        self.assertFalse(Restaurant.objects.filter(name='Garden Table').exists())
        with self.assertRaisesMessage(CommandError, 'names must be 20 characters or fewer'):
            importer.import_rows(self.write_catalog_csv(good_rows + bad_rows))
        self.assertFalse(Restaurant.objects.filter(name='Garden Table').exists())

    def test_catalog_management_command_accepts_the_downloadable_template(self):
        output = StringIO()
        template = settings.BASE_DIR / 'delivery' / 'static' / 'FoodHub' / 'catalog_import_template.csv'
        call_command('import_catalog', template, dry_run=True, stdout=output)
        self.assertIn('Validated 1 restaurants and 2 dishes', output.getvalue())
        self.assertFalse(Restaurant.objects.filter(name='Sample Kitchen').exists())

    def test_catalog_import_rejects_duplicate_dishes_and_malformed_rows(self):
        duplicate_rows = (
            'Garden Table,Mediterranean,4.6,,Lemon Rice Bowl,"Rice with herbs",8.50,true,\n'
            'Garden Table,Mediterranean,4.6,,lemon rice bowl,"Another description",8.90,true,\n'
        )
        extra_value_rows = 'Garden Table,Mediterranean,4.6,,Lemon Rice Bowl,"Rice with herbs",8.50,true,,extra\n'
        importer = CatalogImportCommand()
        with self.assertRaisesMessage(CommandError, 'duplicate dish'):
            importer.import_rows(self.write_catalog_csv(duplicate_rows))
        with self.assertRaisesMessage(CommandError, 'more values than the header'):
            importer.import_rows(self.write_catalog_csv(extra_value_rows))
        self.assertFalse(Restaurant.objects.filter(name='Garden Table').exists())

    def test_catalog_import_rejects_blank_headers_and_fractional_paise(self):
        importer = CatalogImportCommand()
        with self.assertRaisesMessage(CommandError, 'blank column name'):
            importer.import_rows(StringIO(
                'restaurant_name,,cuisine,rating,restaurant_picture,dish_name,description,price,vegetarian,dish_picture\n'
                'Garden Table,,Mediterranean,4.6,,Lemon Rice Bowl,"Rice with herbs",8.50,true,\n'
            ))
        with self.assertRaisesMessage(CommandError, 'no more than two decimal places'):
            importer.import_rows(self.write_catalog_csv(
                'Garden Table,Mediterranean,4.6,,Lemon Rice Bowl,"Rice with herbs",8.501,true,\n',
            ))
        self.assertFalse(Restaurant.objects.filter(name='Garden Table').exists())

    def test_installed_razorpay_sdk_verifies_payment_signature(self):
        client = razorpay.Client(auth=('test-key', 'test-secret'))
        signature = hmac.new(
            b'test-secret', b'order_test_1|pay_test_1', hashlib.sha256,
        ).hexdigest()
        result = client.utility.verify_payment_signature({
            'razorpay_order_id': 'order_test_1',
            'razorpay_payment_id': 'pay_test_1',
            'razorpay_signature': signature,
        })
        self.assertTrue(result)

    def test_public_pages_render_shared_plately_layout(self):
        for route in ('index', 'open_signin', 'open_signup'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Plately')
                self.assertContains(response, 'FoodHub/styles.css')
                if route != 'index':
                    self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_signup_hashes_password_and_reserves_admin_username(self):
        response = self.client.post(reverse('signup'), {
            'username': 'lee', 'password': 'a long password',
            'email': 'lee@example.test', 'mobile': '9876500000',
            'address': '8 Garden Road',
        })
        self.assertEqual(response.status_code, 200)
        created = Customer.objects.get(username='lee')
        self.assertTrue(check_password('a long password', created.password))

        response = self.client.post(reverse('signup'), {
            'username': 'admin', 'password': 'anything',
            'email': 'another-admin@example.test', 'mobile': '9876500002',
            'address': '8 Garden Road',
        })
        self.assertContains(response, 'reserved')
        self.assertEqual(Customer.objects.filter(username='admin').count(), 1)

        response = self.client.post(reverse('signup'), {
            'username': 'bad/name', 'password': 'anything',
            'email': 'bad-name@example.test', 'mobile': '9876500004',
            'address': '8 Garden Road',
        })
        self.assertContains(response, 'letters, numbers')
        self.assertFalse(Customer.objects.filter(username='bad/name').exists())

    def test_signin_establishes_session_and_redirects_to_explore(self):
        response = self.client.post(reverse('signin'), {
            'username': 'sam', 'password': 'correct horse',
        })
        self.assertRedirects(response, reverse('customer_home', args=('sam',)))
        self.assertEqual(self.client.session['customer_id'], self.customer.pk)

    def test_signin_upgrades_legacy_plaintext_password(self):
        legacy = Customer.objects.create(
            username='legacy', password='old password',
            email='legacy@example.test', mobile='9876500003', address='Old address',
        )
        response = self.client.post(reverse('signin'), {
            'username': 'legacy', 'password': 'old password',
        })
        legacy.refresh_from_db()
        self.assertRedirects(response, reverse('customer_home', args=('legacy',)))
        self.assertTrue(check_password('old password', legacy.password))
        self.assertNotEqual(legacy.password, 'old password')

    def test_signin_renders_safe_error_for_invalid_credentials(self):
        response = self.client.post(reverse('signin'), {
            'username': 'sam', 'password': 'not the password',
        })
        self.assertEqual(response.status_code, 401)
        self.assertContains(response, 'Check your username and password', status_code=401)
        self.assertNotIn('customer_id', self.client.session)

    def test_signout_clears_session(self):
        self.sign_in_as()
        response = self.client.post(reverse('signout'))
        self.assertRedirects(response, reverse('index'))
        self.assertNotIn('customer_id', self.client.session)

    def test_customer_pages_require_matching_signed_in_customer(self):
        url = reverse('customer_home', args=('sam',))
        self.assertRedirects(self.client.get(url), reverse('open_signin'))
        self.sign_in_as()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(
            self.client.get(reverse('customer_home', args=('somebody-else',))),
            reverse('open_signin'),
        )

    def test_customer_browsing_cart_and_order_screens_render(self):
        self.sign_in_as()
        urls = (
            reverse('customer_home', args=('sam',)),
            reverse('view_menu', args=(self.restaurant.pk, 'sam')),
            reverse('show_cart', args=('sam',)),
            reverse('orders', args=('sam',)),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Plately')
        response = self.client.post(reverse('checkout', args=('sam',)))
        self.assertContains(response, 'Your cart is empty.')

    def test_restaurant_search_filters_name_and_cuisine(self):
        Restaurant.objects.create(name='Noodle House', cuisine='Thai', rating=4.0)
        self.sign_in_as()
        response = self.client.get(reverse('customer_home', args=('sam',)), {'q': 'Thai'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Noodle House')
        self.assertNotContains(response, 'Good Bowl')

    def test_catalog_pages_are_admin_only(self):
        dashboard = reverse('admin_home')
        self.assertRedirects(self.client.get(dashboard), reverse('open_signin'))
        self.sign_in_as()
        self.assertRedirects(self.client.get(dashboard), reverse('open_signin'))
        self.sign_in_as(self.admin)
        response = self.client.get(dashboard)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Restaurants')
        self.assertContains(response, 'Menu items')

    def test_admin_catalog_screens_render(self):
        self.sign_in_as(self.admin)
        urls = (
            reverse('open_add_restaurant'),
            reverse('open_show_restaurant'),
            reverse('open_update_restaurant', args=(self.restaurant.pk,)),
            reverse('open_update_menu', args=(self.restaurant.pk,)),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Plately')

        dashboard = self.client.get(reverse('admin_home'))
        self.assertContains(dashboard, 'dashboard-hero')
        self.assertContains(dashboard, 'metric-grid')
        self.assertContains(dashboard, 'dashboard-action-grid')
        self.assertContains(dashboard, 'styles.css?v=20260925-catalog-import-1')
        self.assertContains(dashboard, 'catalog_import_template.csv')
        self.assertContains(dashboard, 'Import restaurants and dishes')

    def test_only_admin_can_upload_a_catalog_csv(self):
        csv_content = (
            b'restaurant_name,cuisine,rating,restaurant_picture,dish_name,description,price,vegetarian,dish_picture\n'
            b'Garden Table,Mediterranean,4.6,,Lemon Rice Bowl,"Rice with lemon and herbs",8.50,true,\n'
        )
        response = self.client.post(reverse('upload_catalog'), {
            'catalog_file': SimpleUploadedFile('catalog.csv', csv_content, content_type='text/csv'),
        })
        self.assertRedirects(response, reverse('open_signin'))
        self.assertFalse(Restaurant.objects.filter(name='Garden Table').exists())

        self.sign_in_as(self.admin)
        response = self.client.post(reverse('upload_catalog'), {
            'catalog_file': SimpleUploadedFile('catalog.csv', csv_content, content_type='text/csv'),
        })
        self.assertRedirects(response, reverse('admin_home'))
        self.assertTrue(Restaurant.objects.filter(name='Garden Table').exists())
        self.assertTrue(Item.objects.filter(name='Lemon Rice Bowl').exists())

    def test_failed_catalog_upload_is_atomic_and_reports_validation_error(self):
        csv_content = (
            b'restaurant_name,cuisine,rating,restaurant_picture,dish_name,description,price,vegetarian,dish_picture\n'
            b'Garden Table,Mediterranean,4.6,,Lemon Rice Bowl,"Rice with herbs",8.50,true,\n'
            b'Broken Cafe,Cafe,4.2,,Oversized Dish Name That Does Not Fit,"Description",8.50,false,\n'
        )
        self.sign_in_as(self.admin)
        response = self.client.post(reverse('upload_catalog'), {
            'catalog_file': SimpleUploadedFile('invalid.csv', csv_content, content_type='text/csv'),
        }, follow=True)
        self.assertContains(response, 'names must be 20 characters or fewer')
        self.assertFalse(Restaurant.objects.filter(name='Garden Table').exists())

    def test_catalog_mutations_require_csrf_token(self):
        self.sign_in_as(self.admin)
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.cookies[settings.SESSION_COOKIE_NAME] = self.client.session.session_key
        response = strict_client.post(reverse('delete_restaurant', args=(self.restaurant.pk,)))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Restaurant.objects.filter(pk=self.restaurant.pk).exists())

    def test_admin_can_add_restaurant_and_reject_invalid_rating(self):
        self.sign_in_as(self.admin)
        response = self.client.post(reverse('add_restaurant'), {
            'name': 'Little Wok', 'cuisine': 'Chinese', 'rating': '4.2',
        })
        self.assertRedirects(response, reverse('open_show_restaurant'))
        self.assertTrue(Restaurant.objects.filter(name='Little Wok').exists())

        self.client.post(reverse('add_restaurant'), {
            'name': 'Bad Rating', 'cuisine': 'Fusion', 'rating': '8',
        })
        self.assertFalse(Restaurant.objects.filter(name='Bad Rating').exists())

    def test_admin_can_add_edit_and_remove_menu_item(self):
        self.sign_in_as(self.admin)
        response = self.client.post(reverse('update_menu', args=(self.restaurant.pk,)), {
            'name': 'Mango Lassi', 'description': 'Cold and creamy', 'price': '4.25',
        })
        self.assertRedirects(response, reverse('open_update_menu', args=(self.restaurant.pk,)))
        added = Item.objects.get(name='Mango Lassi')
        self.client.post(reverse('update_menu_item', args=(added.pk,)), {
            'name': 'Mango Lassi Large', 'description': 'Cold, creamy, and fresh', 'price': '5.00',
        })
        added.refresh_from_db()
        self.assertEqual(added.name, 'Mango Lassi Large')
        self.assertEqual(added.price, Decimal('5.00'))
        self.client.post(reverse('delete_menu_item', args=(added.pk,)))
        self.assertFalse(Item.objects.filter(pk=added.pk).exists())

    def test_admin_rejects_duplicate_and_out_of_range_menu_prices(self):
        self.sign_in_as(self.admin)
        url = reverse('update_menu', args=(self.restaurant.pk,))
        response = self.client.post(url, {
            'name': 'masala bowl', 'description': 'Duplicate', 'price': '15.00',
        })
        self.assertRedirects(response, reverse('open_update_menu', args=(self.restaurant.pk,)))
        self.assertEqual(Item.objects.filter(restaurant=self.restaurant).count(), 1)
        self.client.post(url, {
            'name': 'Oversized price', 'description': 'Out of range', 'price': '100000000.00',
        })
        self.assertFalse(Item.objects.filter(name='Oversized price').exists())

    def test_customer_can_add_and_remove_cart_items(self):
        self.sign_in_as()
        response = self.client.post(reverse('add_to_cart', args=(self.item.pk, 'sam')))
        self.assertRedirects(response, reverse('view_menu', args=(self.restaurant.pk, 'sam')))
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.total_price(), Decimal('12.50'))
        response = self.client.post(reverse('remove_from_cart', args=('sam', self.item.pk)))
        self.assertRedirects(response, reverse('show_cart', args=('sam',)))
        self.assertFalse(cart.items.exists())

    def test_checkout_requires_post_and_handles_missing_payment_client(self):
        self.make_cart()
        self.sign_in_as()
        url = reverse('checkout', args=('sam',))
        self.assertEqual(self.client.get(url).status_code, 405)
        with patch('delivery.views._payment_client', return_value=None):
            response = self.client.post(url)
        self.assertContains(response, 'not configured')
        self.assertEqual(Order.objects.count(), 0)
        self.assertTrue(Cart.objects.get(customer=self.customer).items.exists())

    def test_checkout_creates_pending_order_and_payment_verification_captures_it(self):
        cart = self.make_cart()
        self.sign_in_as()
        payment_client = self.make_payment_client()
        with patch('delivery.views._payment_client', return_value=payment_client):
            response = self.client.post(reverse('checkout', args=('sam',)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pay securely with Razorpay')
        order = Order.objects.get(razorpay_order_id='order_test_1')
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total_amount, Decimal('12.50'))
        self.assertEqual(order.lines.count(), 1)

        with patch('delivery.views._payment_client', return_value=payment_client):
            response = self.client.post(reverse('verify_payment', args=('sam',)), {
                'razorpay_order_id': order.razorpay_order_id,
                'razorpay_payment_id': 'pay_test_1',
                'razorpay_signature': 'valid-signature',
            })
        self.assertRedirects(response, reverse('order_confirmation', args=('sam', order.pk)))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.razorpay_payment_id, 'pay_test_1')
        self.assertFalse(cart.items.exists())
        self.assertEqual(self.client.get(reverse('orders', args=('sam',))).status_code, 200)
        confirmation = self.client.get(reverse('order_confirmation', args=('sam', order.pk)))
        self.assertContains(confirmation, 'Something delicious is on its way.')

    def test_uncaptured_or_mismatched_payment_keeps_order_pending_and_cart_items(self):
        cart = self.make_cart()
        self.sign_in_as()
        payment_client = self.make_payment_client(status='authorized')
        with patch('delivery.views._payment_client', return_value=payment_client):
            self.client.post(reverse('checkout', args=('sam',)))
        order = Order.objects.get(razorpay_order_id='order_test_1')
        with patch('delivery.views._payment_client', return_value=payment_client):
            response = self.client.post(reverse('verify_payment', args=('sam',)), {
                'razorpay_order_id': order.razorpay_order_id,
                'razorpay_payment_id': 'pay_test_1',
                'razorpay_signature': 'valid-signature',
            })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'not been captured', status_code=400)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertTrue(cart.items.exists())

        payment_client.payment.fetch.return_value['status'] = 'captured'
        payment_client.payment.fetch.return_value['amount'] = 1
        with patch('delivery.views._payment_client', return_value=payment_client):
            response = self.client.post(reverse('verify_payment', args=('sam',)), {
                'razorpay_order_id': order.razorpay_order_id,
                'razorpay_payment_id': 'pay_test_2',
                'razorpay_signature': 'valid-signature',
            })
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertTrue(cart.items.exists())

    def test_invalid_signature_never_marks_order_paid(self):
        cart = self.make_cart()
        self.sign_in_as()
        payment_client = self.make_payment_client()
        payment_client.utility.verify_payment_signature.side_effect = ValueError('bad signature')
        with patch('delivery.views._payment_client', return_value=payment_client):
            self.client.post(reverse('checkout', args=('sam',)))
        order = Order.objects.get(razorpay_order_id='order_test_1')
        with patch('delivery.views._payment_client', return_value=payment_client):
            response = self.client.post(reverse('verify_payment', args=('sam',)), {
                'razorpay_order_id': order.razorpay_order_id,
                'razorpay_payment_id': 'pay_test_1',
                'razorpay_signature': 'bad-signature',
            })
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertTrue(cart.items.exists())

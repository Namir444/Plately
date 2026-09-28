import hmac
import logging
import re
from decimal import Decimal, InvalidOperation
from functools import wraps
from io import StringIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Cart, Customer, Item, Order, OrderItem, Restaurant
from .management.commands.import_catalog import Command as CatalogImportCommand

try:
    import razorpay
except ImportError:  # The app can still run when online payments are not installed.
    razorpay = None

logger = logging.getLogger(__name__)
MAX_MENU_PRICE = Decimal('99999999.99')
USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{1,20}$')


def customer_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        username = kwargs.get('username')
        customer = Customer.objects.filter(pk=request.session.get('customer_id')).first()
        if customer is None or customer.username != username:
            return redirect('open_signin')
        request.current_customer = customer
        return view_func(request, *args, **kwargs)
    return wrapped


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        customer = Customer.objects.filter(pk=request.session.get('customer_id')).first()
        if customer is None or customer.username != 'admin':
            return redirect('open_signin')
        request.current_customer = customer
        return view_func(request, *args, **kwargs)
    return wrapped


def _check_customer_password(customer, submitted_password):
    """Check a password and upgrade a legacy plain-text value on success."""
    if not submitted_password:
        return False
    try:
        identify_hasher(customer.password)
    except ValueError:
        if not hmac.compare_digest(
            submitted_password.encode('utf-8'), customer.password.encode('utf-8')
        ):
            return False
        customer.password = make_password(submitted_password)
        customer.save(update_fields=['password'])
        return True
    return check_password(submitted_password, customer.password)


def _payment_client():
    if razorpay is None or not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        return None
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _parse_menu_price(value):
    try:
        price = Decimal(value).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not price.is_finite() or not Decimal('0.00') <= price <= MAX_MENU_PRICE:
        return None
    return price


def _payment_failure(request, username, message, retry_payment=None):
    return render(request, 'delivery/payment_failed.html', {
        'username': username,
        'message': message,
        'retry_payment': retry_payment,
    }, status=400)


# Create your views here.
def index(request):
    return render(request, 'delivery/index.html')

def open_signin(request):
    return render(request, 'delivery/signin.html')

def open_signup(request):
    return render(request, 'delivery/signup.html')

def signup(request):
    if request.method != 'POST':
        return redirect('open_signup')

    username = (request.POST.get('username') or '').strip()
    password = request.POST.get('password') or ''
    email = (request.POST.get('email') or '').strip()
    mobile = (request.POST.get('mobile') or '').strip()
    address = (request.POST.get('address') or '').strip()

    if not all((username, password, email, mobile, address)):
        return render(request, 'delivery/signup.html', {
            'error': 'Please complete every field.',
        })
    if not USERNAME_PATTERN.fullmatch(username):
        return render(request, 'delivery/signup.html', {
            'error': 'Use 1–20 letters, numbers, dots, underscores, or hyphens for your username.',
        })
    if len(address) > 50 or len(mobile) > 10:
        return render(request, 'delivery/signup.html', {
            'error': 'Your mobile number or delivery address is too long.',
        })
    if username.lower() == 'admin':
        return render(request, 'delivery/signup.html', {
            'error': 'That username is reserved.',
        })
    if Customer.objects.filter(username=username).exists():
        return render(request, 'delivery/signup.html', {
            'error': 'That username is already in use.',
        })
    if Customer.objects.filter(email=email).exists():
        return render(request, 'delivery/signup.html', {
            'error': 'That email address is already in use.',
        })

    Customer.objects.create(
        username=username,
        password=make_password(password),
        email=email,
        mobile=mobile,
        address=address,
    )
    return render(request, 'delivery/signin.html', {
        'message': 'Your account is ready. Please sign in.',
    })


def signin(request):
    if request.method != 'POST':
        return redirect('open_signin')

    username = (request.POST.get('username') or '').strip()
    password = request.POST.get('password') or ''
    customer = Customer.objects.filter(username=username).first()
    if customer is None or not _check_customer_password(customer, password):
        return render(request, 'delivery/fail.html', status=401)

    request.session.cycle_key()
    request.session['customer_id'] = customer.pk
    if username == 'admin':
        return redirect('admin_home')

    return redirect('customer_home', username=username)


@require_POST
def signout(request):
    request.session.flush()
    messages.success(request, 'You have signed out.')
    return redirect('index')


@customer_required
def customer_home(request, username):
    query = (request.GET.get('q') or '').strip()
    restaurants = Restaurant.objects.all().order_by('name')
    if query:
        restaurants = restaurants.filter(
            Q(name__icontains=query) | Q(cuisine__icontains=query)
        )
    return render(request, 'delivery/customer_home.html', {
        'restaurantList': restaurants,
        'username': username,
        'query': query,
    })


@admin_required
def admin_home(request):
    return render(request, 'delivery/admin_home.html', {
        'restaurant_count': Restaurant.objects.count(),
        'menu_item_count': Item.objects.count(),
    })


@admin_required
@require_POST
def upload_catalog(request):
    catalog_file = request.FILES.get('catalog_file')
    if catalog_file is None:
        messages.error(request, 'Choose a CSV file to import.')
        return redirect('admin_home')
    if catalog_file.size > 2 * 1024 * 1024:
        messages.error(request, 'Catalog CSV files must be 2 MB or smaller.')
        return redirect('admin_home')
    if not catalog_file.name.lower().endswith('.csv'):
        messages.error(request, 'Upload a .csv file using the Plately catalog format.')
        return redirect('admin_home')

    try:
        csv_content = catalog_file.read().decode('utf-8-sig')
        result = CatalogImportCommand().import_rows(StringIO(csv_content))
    except (CommandError, UnicodeDecodeError) as error:
        messages.error(request, str(error))
        return redirect('admin_home')

    messages.success(request, result)
    return redirect('admin_home')

@admin_required
def open_add_restaurant(request):
    return render(request, 'delivery/add_restaurant.html')

@admin_required
@require_POST
def add_restaurant(request):
    name = (request.POST.get('name') or '').strip()
    picture = (request.POST.get('picture') or '').strip()
    cuisine = (request.POST.get('cuisine') or '').strip()
    try:
        rating = float(request.POST.get('rating', ''))
    except (TypeError, ValueError):
        rating = -1

    if not name or len(name) > 20 or not cuisine or not 0 <= rating <= 5:
        messages.error(request, 'Enter a restaurant name, cuisine, and a rating from 0 to 5.')
        return redirect('open_add_restaurant')
    if Restaurant.objects.filter(name__iexact=name).exists():
        messages.error(request, 'A restaurant with that name is already listed.')
        return redirect('open_add_restaurant')

    fields = {'name': name, 'cuisine': cuisine, 'rating': rating}
    if picture:
        fields['picture'] = picture
    Restaurant.objects.create(**fields)
    messages.success(request, f'{name} was added to the directory.')
    return redirect('open_show_restaurant')

@admin_required
def open_show_restaurant(request):
    restaurantList = Restaurant.objects.all().order_by('name')
    return render(request, 'delivery/show_restaurants.html',{"restaurantList" : restaurantList})

@admin_required
def open_update_restaurant(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    return render(request, 'delivery/update_restaurant.html', {"restaurant" : restaurant})

@admin_required
@require_POST
def update_restaurant(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    name = (request.POST.get('name') or '').strip()
    cuisine = (request.POST.get('cuisine') or '').strip()
    picture = (request.POST.get('picture') or '').strip()
    try:
        rating = float(request.POST.get('rating', ''))
    except (TypeError, ValueError):
        rating = -1

    if not name or len(name) > 20 or not cuisine or not 0 <= rating <= 5:
        messages.error(request, 'Enter a restaurant name, cuisine, and a rating from 0 to 5.')
        return redirect('open_update_restaurant', restaurant_id=restaurant.pk)
    if Restaurant.objects.filter(name__iexact=name).exclude(pk=restaurant.pk).exists():
        messages.error(request, 'A restaurant with that name is already listed.')
        return redirect('open_update_restaurant', restaurant_id=restaurant.pk)

    restaurant.name = name
    restaurant.cuisine = cuisine
    restaurant.rating = rating
    if picture:
        restaurant.picture = picture
    restaurant.save()
    messages.success(request, f'{restaurant.name} was updated.')
    return redirect('open_show_restaurant')


@admin_required
@require_POST
def delete_restaurant(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    name = restaurant.name
    restaurant.delete()
    messages.success(request, f'{name} and its menu were removed.')
    return redirect('open_show_restaurant')


@admin_required
def open_update_menu(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    itemList = restaurant.items.all().order_by('name')
    return render(request, 'delivery/update_menu.html',{"itemList" : itemList, "restaurant" : restaurant})

@admin_required
@require_POST
def update_menu(request, restaurant_id):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    name = (request.POST.get('name') or '').strip()
    description = (request.POST.get('description') or '').strip()
    picture = (request.POST.get('picture') or '').strip()
    price = _parse_menu_price(request.POST.get('price', ''))

    if not name or len(name) > 20 or not description or price is None:
        messages.error(request, 'Enter a dish name, description, and valid non-negative price.')
        return redirect('open_update_menu', restaurant_id=restaurant.pk)
    if Item.objects.filter(restaurant=restaurant, name__iexact=name).exists():
        messages.error(request, 'That dish is already on this menu.')
        return redirect('open_update_menu', restaurant_id=restaurant.pk)

    item_fields = {
        'restaurant': restaurant,
        'name': name,
        'description': description,
        'price': price,
        'vegeterian': request.POST.get('vegeterian') == 'on',
    }
    if picture:
        item_fields['picture'] = picture
    Item.objects.create(**item_fields)
    messages.success(request, f'{name} was added to the menu.')
    return redirect('open_update_menu', restaurant_id=restaurant.pk)


@admin_required
@require_POST
def update_menu_item(request, item_id):
    item = get_object_or_404(Item, pk=item_id)
    name = (request.POST.get('name') or '').strip()
    description = (request.POST.get('description') or '').strip()
    picture = (request.POST.get('picture') or '').strip()
    price = _parse_menu_price(request.POST.get('price', ''))

    if not name or len(name) > 20 or not description or price is None:
        messages.error(request, 'Enter a name, description, and valid non-negative price.')
        return redirect('open_update_menu', restaurant_id=item.restaurant_id)
    if Item.objects.filter(restaurant=item.restaurant, name__iexact=name).exclude(pk=item.pk).exists():
        messages.error(request, 'That dish is already on this menu.')
        return redirect('open_update_menu', restaurant_id=item.restaurant_id)

    item.name = name
    item.description = description
    item.price = price
    item.picture = picture or item.picture
    item.vegeterian = request.POST.get('vegeterian') == 'on'
    item.save()
    messages.success(request, f'{item.name} was updated.')
    return redirect('open_update_menu', restaurant_id=item.restaurant_id)


@admin_required
@require_POST
def delete_menu_item(request, item_id):
    item = get_object_or_404(Item, pk=item_id)
    restaurant_id = item.restaurant_id
    item.delete()
    messages.success(request, 'Menu item was removed.')
    return redirect('open_update_menu', restaurant_id=restaurant_id)


@customer_required
def view_menu(request, restaurant_id, username):
    restaurant = get_object_or_404(Restaurant, id=restaurant_id)
    itemList = restaurant.items.all().order_by('name')
    return render(request, 'delivery/customer_menu.html'
                        ,{"itemList" : itemList,
                            "restaurant" : restaurant,
                     "username":username})

@customer_required
@require_POST
def add_to_cart(request, item_id, username):
    item = get_object_or_404(Item, id=item_id)
    customer = request.current_customer

    cart, _created = Cart.objects.get_or_create(customer = customer)

    cart.items.add(item)
    messages.success(request, f'{item.name} was added to your cart.')
    return redirect('view_menu', restaurant_id=item.restaurant_id, username=username)


@customer_required
@require_POST
def remove_from_cart(request, item_id, username):
    customer = request.current_customer
    item = get_object_or_404(Item, pk=item_id)
    cart = Cart.objects.filter(customer=customer).first()
    if cart:
        cart.items.remove(item)
        messages.success(request, f'{item.name} was removed from your cart.')
    return redirect('show_cart', username=username)


@customer_required
def show_cart(request, username):
    customer = request.current_customer
    cart = Cart.objects.filter(customer=customer).first()
    items = cart.items.all() if cart else []
    total_price = cart.total_price() if cart else 0

    return render(request, 'delivery/cart.html', {
        'itemList': items,
        'total_price': total_price,
        'username': username,
    })

# Checkout View
@customer_required
@require_POST
def checkout(request, username):
    customer = get_object_or_404(Customer, username=username)
    cart = Cart.objects.filter(customer=customer).first()
    cart_items = list(cart.items.all()) if cart else []
    total_price = cart.total_price() if cart else Decimal('0.00')

    if not cart_items or total_price <= 0:
        return render(request, 'delivery/checkout.html', {
            'username': username,
            'error': 'Your cart is empty.',
        })

    client = _payment_client()
    if client is None:
        return render(request, 'delivery/checkout.html', {
            'username': username,
            'cart_items': cart_items,
            'total_price': total_price,
            'error': 'Online payments are not configured. Please try again later.',
        })

    amount_paise = int(total_price * 100)
    try:
        razorpay_order = client.order.create(data={
            'amount': amount_paise,
            'currency': 'INR',
        })
    except Exception:
        logger.exception('Razorpay order creation failed for customer %s', customer.pk)
        return render(request, 'delivery/checkout.html', {
            'username': username,
            'cart_items': cart_items,
            'total_price': total_price,
            'error': 'We could not start the payment. Your cart is unchanged; please try again.',
        })

    order = Order.objects.create(
        customer=customer,
        razorpay_order_id=razorpay_order['id'],
        total_amount=total_price,
        delivery_address=customer.address,
    )
    OrderItem.objects.bulk_create([
        OrderItem(
            order=order,
            item=item,
            item_name=item.name,
            unit_price=item.price,
            quantity=1,
        )
        for item in cart_items
    ])

    return render(request, 'delivery/checkout.html', {
        'username': username,
        'customer': customer,
        'cart_items': cart_items,
        'total_price': total_price,
        'amount_paise': amount_paise,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'order_id': order.razorpay_order_id,
    })


@customer_required
@require_POST
def verify_payment(request, username):
    customer = get_object_or_404(Customer, username=username)
    razorpay_order_id = request.POST.get('razorpay_order_id', '')
    payment_id = request.POST.get('razorpay_payment_id', '')
    signature = request.POST.get('razorpay_signature', '')
    order = get_object_or_404(
        Order,
        customer=customer,
        razorpay_order_id=razorpay_order_id,
    )

    if order.status == Order.Status.PAID:
        if order.razorpay_payment_id == payment_id:
            return redirect('order_confirmation', username=username, order_id=order.pk)
        return _payment_failure(request, username, 'This order is already paid.')

    client = _payment_client()
    if client is None or not payment_id or not signature:
        return _payment_failure(request, username, 'We could not verify this payment.')

    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': order.razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature,
        })
        payment = client.payment.fetch(payment_id)
    except Exception:
        logger.warning('Razorpay signature verification failed for order %s', order.pk)
        return _payment_failure(request, username, 'We could not verify this payment.')

    expected_amount = int(order.total_amount * 100)
    if (
        payment.get('order_id') != order.razorpay_order_id
        or payment.get('amount') != expected_amount
        or payment.get('currency') != 'INR'
    ):
        logger.warning('Razorpay payment details did not match order %s', order.pk)
        return _payment_failure(request, username, 'We could not match this payment to your order.')
    if payment.get('status') != 'captured':
        return _payment_failure(
            request,
            username,
            'Payment has not been captured yet. Please try again shortly.',
            retry_payment={
                'razorpay_order_id': order.razorpay_order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature,
            },
        )

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status == Order.Status.PAID:
            if locked_order.razorpay_payment_id != payment_id:
                return _payment_failure(request, username, 'This order is already paid.')
        else:
            updated = Order.objects.filter(
                pk=locked_order.pk,
                status=Order.Status.PENDING,
            ).update(
                status=Order.Status.PAID,
                razorpay_payment_id=payment_id,
            )
            if updated:
                cart = Cart.objects.filter(customer=customer).first()
                if cart:
                    ordered_item_ids = list(
                        locked_order.lines.exclude(item__isnull=True)
                        .values_list('item_id', flat=True)
                    )
                    if ordered_item_ids:
                        cart.items.remove(*ordered_item_ids)
            else:
                current_order = Order.objects.get(pk=locked_order.pk)
                if (
                    current_order.status != Order.Status.PAID
                    or current_order.razorpay_payment_id != payment_id
                ):
                    return _payment_failure(request, username, 'We could not confirm this payment.')

    return redirect('order_confirmation', username=username, order_id=order.pk)


@customer_required
def orders(request, username):
    customer = get_object_or_404(Customer, username=username)
    order_list = Order.objects.filter(
        customer=customer,
        status=Order.Status.PAID,
    ).order_by('-created_at')
    return render(request, 'delivery/orders.html', {
        'username': username,
        'orderList': order_list,
    })


@customer_required
def order_confirmation(request, username, order_id):
    customer = get_object_or_404(Customer, username=username)
    order = get_object_or_404(
        Order.objects.prefetch_related('lines'),
        pk=order_id,
        customer=customer,
        status=Order.Status.PAID,
    )
    return render(request, 'delivery/success.html', {
        'username': username,
        'order': order,
    })

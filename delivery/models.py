from decimal import Decimal

from django.db import models


class Customer(models.Model):
    username = models.CharField(max_length=20)
    # New passwords are Django hashes. Legacy plain text values are upgraded
    # after a successful sign-in.
    password = models.CharField(max_length=128)
    email = models.EmailField(unique=True)
    mobile = models.CharField(max_length=10)
    address = models.TextField(max_length=50, default='Not provided')

    def __str__(self):
        return self.username


class Restaurant(models.Model):
    name = models.CharField(max_length=20)
    picture = models.URLField(
        max_length=200,
        default='https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSHi0HDEC4AHKzvFurHhnfMY73FYok-UY0rlgvl3f0gfg&s=10',
    )
    cuisine = models.CharField(max_length=200)
    rating = models.FloatField()

    def __str__(self):
        return self.name


class Item(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='items'
    )
    name = models.CharField(max_length=20)
    description = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    vegeterian = models.BooleanField(default=False)
    picture = models.URLField(
        max_length=400,
        default='https://www.indiafilings.com/learn/wp-content/uploads/2024/08/How-to-Start-Food-Business.jpg',
    )

    def __str__(self):
        return self.name


class Cart(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='cart')
    items = models.ManyToManyField(Item, related_name='carts')

    def total_price(self):
        return sum((item.price for item in self.items.all()), Decimal('0.00'))


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending payment'
        PAID = 'paid', 'Paid'

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders')
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Order {self.pk} ({self.status})'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True)
    item_name = models.CharField(max_length=100)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return f'{self.quantity} x {self.item_name}'

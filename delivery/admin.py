from django.contrib import admin

from .models import Cart, Customer, Item, Order, OrderItem, Restaurant
# Register your models here.
admin.site.register(Customer)
admin.site.register(Restaurant)
admin.site.register(Item)
admin.site.register(Cart)
admin.site.register(Order)
admin.site.register(OrderItem)

from django.urls import path
from . import views
urlpatterns = [
    path('', views.index, name='index'),
    path('open_signin', views.open_signin, name='open_signin'),
    path('open_signup', views.open_signup, name='open_signup'),
    path('signup', views.signup, name='signup'),
    path('signin', views.signin, name='signin'),
    path('signout', views.signout, name='signout'),
    path('restaurants/<str:username>/', views.customer_home, name='customer_home'),
    path('admin-home/', views.admin_home, name='admin_home'),
    path('catalog/import/', views.upload_catalog, name='upload_catalog'),
    path('open_add_restaurant', views.open_add_restaurant, name='open_add_restaurant'),
    path('add_restaurant', views.add_restaurant, name='add_restaurant'),
    path('open_show_restaurant', views.open_show_restaurant, name='open_show_restaurant'),
    path('open_update_restaurant/<int:restaurant_id>', views.open_update_restaurant, name='open_update_restaurant'),
    path('update_restaurant/<int:restaurant_id>', views.update_restaurant, name='update_restaurant'),
    path('delete_restaurant/<int:restaurant_id>', views.delete_restaurant, name='delete_restaurant'),
    path('open_update_menu/<int:restaurant_id>', views.open_update_menu, name='open_update_menu'),
    path('update_menu/<int:restaurant_id>', views.update_menu, name='update_menu'),
    path('update_menu_item/<int:item_id>', views.update_menu_item, name='update_menu_item'),
    path('delete_menu_item/<int:item_id>', views.delete_menu_item, name='delete_menu_item'),
    path('view_menu/<int:restaurant_id>/<str:username>', views.view_menu, name='view_menu'),

    path('add_to_cart/<int:item_id>/<str:username>', views.add_to_cart, name='add_to_cart'),
    path('remove_from_cart/<str:username>/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),

    path('show_cart/<str:username>', views.show_cart, name='show_cart'),

    path('checkout/<str:username>/', views.checkout, name='checkout'),
    path('payments/verify/<str:username>/', views.verify_payment, name='verify_payment'),

    path('orders/<str:username>/', views.orders, name='orders'),
    path('orders/<str:username>/<int:order_id>/', views.order_confirmation, name='order_confirmation'),
]

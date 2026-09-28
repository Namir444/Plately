from django.apps import AppConfig


class DeliveryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'delivery'
    # Existing migrations and database tables use the FoodHub app label.
    label = 'FoodHub'

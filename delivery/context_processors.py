from .models import Customer


def current_customer(request):
    customer = getattr(request, 'current_customer', None)
    if customer is None:
        customer_id = request.session.get('customer_id')
        if customer_id:
            customer = Customer.objects.filter(pk=customer_id).first()

    return {
        'current_customer': customer,
        'is_admin': bool(customer and customer.username == 'admin'),
    }

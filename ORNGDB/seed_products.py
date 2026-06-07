import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ORNGDB.settings')
django.setup()

from products.models import Product

products_data = [
    {"name": "Fresh Oranges", "price": 80.00, "icon": "🍊"},
    {"name": "Apples (Fuji)", "price": 120.00, "icon": "🍎"},
    {"name": "Tomatoes", "price": 40.00, "icon": "🍅"},
    {"name": "Potatoes", "price": 30.00, "icon": "🥔"},
    {"name": "Coriander", "price": 10.00, "icon": "🌿"},
    {"name": "Watermelon", "price": 60.00, "icon": "🍉"},
]

for item in products_data:
    p, created = Product.objects.get_or_create(
        name=item["name"],
        defaults={
            "price": item["price"],
            "icon": item["icon"],
            "available": True
        }
    )
    if created:
        print(f"Created product: {p.name}")
    else:
        print(f"Product already exists: {p.name}")

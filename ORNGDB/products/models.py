from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    available = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(null=True, blank=True)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    icon = models.CharField(max_length=50, blank=True, default='📦')
    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ['position', 'name']

    def __str__(self):
        return f"{self.name} (₹{self.price})"

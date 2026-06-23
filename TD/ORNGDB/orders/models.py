from django.db import models
from django.conf import settings
from products.models import Product

class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('packed', 'Packed'),
        ('delivered', 'Delivered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    )
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    store_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_delivery_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='deliveries'
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    old_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    remaining_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_status = models.CharField(max_length=20, choices=(('paid', 'Paid'), ('unpaid', 'Unpaid')), default='unpaid')
    created_at = models.DateTimeField(auto_now_add=True)
    packed_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    @property
    def grand_total(self):
        return self.total_amount + self.old_balance

    @property
    def remaining_due(self):
        return self.remaining_balance if self.remaining_balance is not None else self.grand_total

    @property
    def cash_paid(self):
        return self.grand_total - self.remaining_due

    @property
    def display_customer_name(self):
        if self.customer:
            return self.customer.name or self.customer.store_name
        return self.store_name

    @property
    def display_store_name(self):
        if self.store_name:
            return self.store_name
        if self.customer:
            return self.customer.store_name or self.customer.name
        return "Guest"

    def __str__(self):
        return f"Order #{self.id} - {self.store_name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if self.customer and not self.store_name:
            self.store_name = self.customer.store_name
            
        if not self.pk and not self.assigned_delivery_user:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            agent_guy = User.objects.filter(role='agent').first()
            if agent_guy:
                self.assigned_delivery_user = agent_guy
        
        if self.remaining_balance is None:
            self.remaining_balance = self.total_amount + self.old_balance
            
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    price_at_time = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def row_total(self):
        return self.price_at_time * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

class CartItem(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"Cart: {self.quantity} x {self.product.name} for {self.customer.username}"

class DraftBill(models.Model):
    """Persists an in-progress quick bill for a delivery user so they can resume after closing the app."""
    delivery_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='draft_bill'
    )
    items_json = models.JSONField(default=dict)   # {product_id: qty}
    store_name = models.CharField(max_length=255, blank=True, default='')
    old_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Draft bill for {self.delivery_user.username}"

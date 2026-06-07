from django.contrib import admin
from .models import Order, OrderItem, CartItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'status', 'assigned_delivery_user', 'total_amount', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('customer__store_name', 'customer__phone')
    inlines = [OrderItemInline]

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'quantity')

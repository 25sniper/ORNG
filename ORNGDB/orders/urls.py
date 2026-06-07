from django.urls import path
from . import views

urlpatterns = [
    path('cart/', views.cart_view, name='cart_view'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'),
    path('cart/update/<int:item_id>/', views.cart_update, name='cart_update'),
    path('cart/remove/<int:item_id>/', views.cart_remove, name='cart_remove'),
    path('checkout/', views.checkout, name='checkout'),
    path('my-orders/', views.my_orders, name='my_orders'),
    path('order/<int:order_id>/', views.order_detail, name='order_detail'),
    path('order/<int:order_id>/received/', views.mark_order_received, name='mark_order_received'),
    path('order/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('cart/update-qty/<int:product_id>/', views.cart_update_qty, name='cart_update_qty'),
]

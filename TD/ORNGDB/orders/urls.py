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
    path('quick-bill/', views.quick_bill_create, name='quick_bill_create'),
    path('order/<int:order_id>/share/', views.share_order_bill, name='share_order_bill'),
    path('order/<int:order_id>/toggle-payment/', views.toggle_order_payment_status, name='toggle_order_payment_status'),
    path('store/pay-balance/', views.pay_store_balance, name='pay_store_balance'),
    path('store/orders/', views.store_orders_api, name='store_orders_api'),
    path('draft-bill/get/', views.draft_bill_get, name='draft_bill_get'),
    path('draft-bill/save/', views.draft_bill_save, name='draft_bill_save'),
    path('draft-bill/clear/', views.draft_bill_clear, name='draft_bill_clear'),
    path('order/<int:order_id>/edit-details/', views.order_edit_details_api, name='order_edit_details_api'),
]

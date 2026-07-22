from django.urls import path
from . import views

urlpatterns = [
    path('order/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('quick-bill/', views.quick_bill_create, name='quick_bill_create'),
    path('order/<int:order_id>/share/', views.share_order_bill, name='share_order_bill'),
    path('order/<int:order_id>/toggle-payment/', views.toggle_order_payment_status, name='toggle_order_payment_status'),
    path('store/pay-balance/', views.pay_store_balance, name='pay_store_balance'),
    path('store/orders/', views.store_orders_api, name='store_orders_api'),
    path('draft-bill/get/', views.draft_bill_get, name='draft_bill_get'),
    path('draft-bill/save/', views.draft_bill_save, name='draft_bill_save'),
    path('draft-bill/clear/', views.draft_bill_clear, name='draft_bill_clear'),
    path('order/<int:order_id>/edit-details/', views.order_edit_details_api, name='order_edit_details_api'),
    path('customer-quick-bill/', views.customer_quick_bill_create, name='customer_quick_bill_create'),
    path('load-more-delivered/', views.load_more_delivered_orders, name='load_more_delivered_orders'),
]

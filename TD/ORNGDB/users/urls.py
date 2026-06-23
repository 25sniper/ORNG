from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_redirect, name='home'),
    path('login/', views.unified_login, name='login'),
    path('register/', views.customer_register, name='register'),
    path('logout/', views.user_logout, name='logout'),
    path('profile/', views.profile_view, name='profile_view'),
    
    # Dashboards
    path('manage/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('manage/products/', views.admin_products_view, name='admin_products_view'),
    path('manage/stores/', views.admin_stores_view, name='admin_stores_view'),
    path('manage/staff/', views.admin_staff_view, name='admin_staff_view'),
    path('manage/order/<int:order_id>/', views.admin_order_detail_view, name='admin_order_detail_view'),
    path('agent/dashboard/', views.delivery_dashboard, name='delivery_dashboard'),
    path('customer/menu/', views.customer_menu, name='customer_menu'),
    
    # Admin & Agent Actions
    path('manage/assign-agent/<int:order_id>/', views.admin_assign_delivery, name='admin_assign_delivery'),
    path('manage/create-agent-account/', views.admin_create_delivery_account, name='admin_create_delivery_account'),
    path('manage/toggle-product/<int:product_id>/', views.admin_toggle_product, name='admin_toggle_product'),
    path('manage/product/add/', views.admin_add_product, name='admin_add_product'),
    path('manage/product/edit/<int:product_id>/', views.admin_edit_product, name='admin_edit_product'),
    path('manage/store/add/', views.admin_add_store, name='admin_add_store'),
    path('manage/store/edit/<int:store_id>/', views.admin_edit_store, name='admin_edit_store'),
    path('manage/store/delete/<int:store_id>/', views.admin_delete_store, name='admin_delete_store'),
    path('manage/delete-order-history/', views.admin_delete_order_history, name='admin_delete_order_history'),
    path('manage/products/reorder/', views.admin_reorder_products, name='admin_reorder_products'),
    path('order/<int:order_id>/pack/', views.pack_order, name='pack_order'),
    path('order/<int:order_id>/deliver/', views.deliver_order, name='deliver_order'),
    path('order/<int:order_id>/cancel/', views.delivery_cancel_order, name='delivery_cancel_order'),
    path('order/<int:order_id>/edit-to-draft/', views.delivery_edit_order_to_draft, name='edit_order_to_draft'),
    path('agent/order/<int:order_id>/pack/', views.delivery_pack_order, name='delivery_pack_order'),
]

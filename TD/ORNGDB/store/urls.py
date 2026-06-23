from django.urls import path
from . import views

urlpatterns = [
    path('', views.store_list, name='store_list'),
    path('add/', views.store_create, name='store_create'),
    path('<int:store_id>/edit/', views.store_update, name='store_update'),
    path('<int:store_id>/delete/', views.store_delete, name='store_delete'),
]

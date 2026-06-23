from django.contrib import admin
from .models import Store

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'owner')
    search_fields = ('name', 'owner__username')
    list_filter = ('owner',)

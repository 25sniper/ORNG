from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('role', 'name', 'phone', 'store_name', 'location', 'contact_number')}),
    )
    list_display = ('username', 'role', 'name', 'phone', 'store_name')

admin.site.register(User, CustomUserAdmin)

from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('delivery', 'Delivery'),
        ('customer', 'Customer'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    store_name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=500, blank=True)
    google_maps_url = models.URLField(max_length=1000, blank=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


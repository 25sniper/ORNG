from django.contrib.auth.models import AbstractUser, UserManager as DefaultUserManager
from django.db import models

class UserManager(DefaultUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        return super().create_superuser(username, email, password, **extra_fields)

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('agent', 'Agent'),
    )

    objects = UserManager()

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='agent')
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    store_name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=500, blank=True)
    google_maps_url = models.URLField(max_length=1000, blank=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


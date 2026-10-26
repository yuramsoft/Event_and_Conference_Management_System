from django.conf import settings
from django.db import models


class Venue(models.Model):
    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="venues")
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Nigeria")
    capacity = models.PositiveIntegerField(null=True, blank=True)
    map_url = models.URLField(blank=True, help_text="Google Maps or similar link")
    notes = models.TextField(blank=True, help_text="Parking, access, directions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.city}"

    @property
    def full_address(self):
        return ", ".join(p for p in [self.address, self.city, self.state, self.country] if p)

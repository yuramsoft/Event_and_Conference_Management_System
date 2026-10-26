from django.conf import settings
from django.db import models


class Speaker(models.Model):
    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="speakers")
    events = models.ManyToManyField("events.Event", blank=True, related_name="speakers")
    name = models.CharField(max_length=150)
    title = models.CharField(max_length=150, blank=True, help_text="Job title")
    company = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to="speakers/", blank=True)
    website = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    x_handle = models.CharField("X / Twitter handle", max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def initials(self):
        return "".join(p[0] for p in self.name.split()[:2]).upper()

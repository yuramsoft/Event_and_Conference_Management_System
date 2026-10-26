from django.conf import settings
from django.db import models


class CheckIn(models.Model):
    """Every scan attempt — accepted or rejected — is recorded."""

    class Result(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        DUPLICATE = "duplicate", "Already checked in"
        INVALID = "invalid", "Invalid ticket"
        WRONG_EVENT = "wrong_event", "Different event"
        CANCELLED = "cancelled", "Cancelled ticket"

    class Method(models.TextChoices):
        SCAN = "scan", "QR scan"
        MANUAL = "manual", "Manual entry"

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="checkins")
    ticket = models.ForeignKey(
        "tickets.Ticket", null=True, blank=True, on_delete=models.SET_NULL, related_name="checkins"
    )
    scanned_code = models.CharField(max_length=60)
    result = models.CharField(max_length=20, choices=Result.choices, db_index=True)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.SCAN)
    checked_in_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    gate = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.scanned_code} → {self.result}"

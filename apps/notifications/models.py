from django.db import models


class EmailLog(models.Model):
    """Outbound email record; lets reminders be sent once and failures be retried."""

    class Kind(models.TextChoices):
        ORDER_CONFIRMATION = "order_confirmation", "Order confirmation"
        REMINDER = "reminder", "Event reminder"
        REFUND = "refund", "Refund update"
        REPORT = "report", "Sales report"
        PAYMENT_FAILED = "payment_failed", "Payment failed"

    kind = models.CharField(max_length=30, choices=Kind.choices, db_index=True)
    to = models.EmailField()
    subject = models.CharField(max_length=255)
    order = models.ForeignKey("registrations.Order", null=True, blank=True, on_delete=models.SET_NULL)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.SET_NULL)
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        indexes = [models.Index(fields=["kind", "event", "to"])]

    def __str__(self):
        return f"{self.kind} → {self.to}"

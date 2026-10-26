from django.conf import settings
from django.db import models


class RefundRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved – processing"
        PROCESSED = "processed", "Refunded"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Gateway error"

    order = models.ForeignKey("registrations.Order", on_delete=models.CASCADE, related_name="refunds")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="refund_requests"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="refunds_reviewed"
    )
    review_note = models.TextField(blank=True)
    gateway_reference = models.CharField(max_length=80, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund {self.order.reference} ({self.status})"

    @property
    def status_badge(self):
        return {"requested": "warning", "approved": "primary", "processed": "success",
                "rejected": "secondary", "failed": "danger"}[self.status]

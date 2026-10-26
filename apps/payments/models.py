from django.db import models


class Payment(models.Model):
    """One Paystack transaction attempt for an order."""

    class Status(models.TextChoices):
        INITIALIZED = "initialized", "Initialized"
        SUCCESS = "success", "Successful"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Abandoned"

    order = models.ForeignKey("registrations.Order", on_delete=models.CASCADE, related_name="payments")
    reference = models.CharField(max_length=60, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=5, default="NGN")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIALIZED, db_index=True)
    authorization_url = models.URLField(blank=True, max_length=500)
    access_code = models.CharField(max_length=100, blank=True)
    channel = models.CharField(max_length=40, blank=True)
    gateway_response = models.CharField(max_length=255, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} ({self.status})"


class WebhookEvent(models.Model):
    """Every Paystack webhook received, for idempotency and debugging."""

    event = models.CharField(max_length=60)
    reference = models.CharField(max_length=60, blank=True, db_index=True)
    payload = models.JSONField()
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.event} {self.reference}"

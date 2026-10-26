import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


def _order_reference():
    return "EH-" + secrets.token_hex(5).upper()


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PAID = "paid", "Paid"
        FAILED = "failed", "Payment failed"
        EXPIRED = "expired", "Reservation expired"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    reference = models.CharField(max_length=20, unique=True, default=_order_reference, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    buyer_name = models.CharField(max_length=150)
    buyer_email = models.EmailField()
    buyer_phone = models.CharField(max_length=30, blank=True)

    discount_code = models.ForeignKey(
        "discounts.DiscountCode", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    needs_review = models.BooleanField(
        default=False, help_text="Paid after reservation lapsed and inventory was gone — refund required"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference

    def get_absolute_url(self):
        return reverse("attendee:order_detail", args=[self.reference])

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    @property
    def reservation_active(self):
        return self.is_pending and self.expires_at and self.expires_at > timezone.now()

    @property
    def seconds_left(self):
        if not self.reservation_active:
            return 0
        return int((self.expires_at - timezone.now()).total_seconds())

    @property
    def quantity(self):
        return sum(i.quantity for i in self.items.all())

    @property
    def amount_kobo(self):
        """Paystack amounts are in the currency's subunit."""
        return int((self.total * 100).quantize(Decimal("1")))

    @property
    def status_badge(self):
        return {
            "pending": "warning",
            "paid": "success",
            "failed": "danger",
            "expired": "secondary",
            "cancelled": "secondary",
            "refunded": "info",
        }.get(self.status, "secondary")


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    ticket_type = models.ForeignKey("tickets.TicketType", on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} × {self.ticket_type.name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity

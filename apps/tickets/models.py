import secrets

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone


class TicketType(models.Model):
    """A sellable ticket tier (e.g. Early Bird, Regular, VIP)."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="ticket_types")
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(help_text="Total tickets available for this tier")
    sold = models.PositiveIntegerField(default=0, editable=False)
    sales_start = models.DateTimeField(null=True, blank=True)
    sales_end = models.DateTimeField(null=True, blank=True)
    min_per_order = models.PositiveSmallIntegerField(default=1)
    max_per_order = models.PositiveSmallIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "price"]

    def __str__(self):
        return f"{self.event} – {self.name}"

    def clean(self):
        if self.min_per_order > self.max_per_order:
            raise ValidationError("Minimum per order cannot exceed maximum per order.")
        if self.sales_start and self.sales_end and self.sales_end <= self.sales_start:
            raise ValidationError({"sales_end": "Sales must end after they start."})
        if self.pk and self.quantity < self.sold:
            raise ValidationError({"quantity": f"{self.sold} tickets are already sold."})

    @property
    def is_free(self):
        return self.price == 0

    @property
    def reserved(self):
        """Tickets held by unpaid orders whose reservation hasn't expired."""
        from apps.registrations.models import Order

        return (
            self.order_items.filter(order__status=Order.Status.PENDING, order__expires_at__gt=timezone.now())
            .aggregate(n=Sum("quantity"))["n"]
            or 0
        )

    @property
    def available(self):
        return max(self.quantity - self.sold - self.reserved, 0)

    @property
    def on_sale(self):
        now = timezone.now()
        if not self.is_active or not self.event.is_on_sale:
            return False
        if self.sales_start and now < self.sales_start:
            return False
        if self.sales_end and now > self.sales_end:
            return False
        return True

    @property
    def sale_status(self):
        now = timezone.now()
        if not self.is_active:
            return "Unavailable"
        if self.sales_start and now < self.sales_start:
            return f"On sale {timezone.localtime(self.sales_start):%b %d}"
        if self.sales_end and now > self.sales_end:
            return "Sales ended"
        if self.available == 0:
            return "Sold out"
        return "On sale"


def _ticket_code():
    return secrets.token_urlsafe(12)


class Ticket(models.Model):
    """An issued, scannable ticket. One per admitted person."""

    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        USED = "used", "Checked in"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey("registrations.Order", on_delete=models.CASCADE, related_name="tickets")
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name="tickets")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="tickets")
    code = models.CharField(max_length=40, unique=True, default=_ticket_code, editable=False)
    attendee_name = models.CharField(max_length=150)
    attendee_email = models.EmailField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.VALID, db_index=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.code} ({self.ticket_type.name})"

    def get_absolute_url(self):
        return reverse("attendee:ticket_detail", args=[self.code])

    @property
    def short_code(self):
        return self.code[:8].upper()

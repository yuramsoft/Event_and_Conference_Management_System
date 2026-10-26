from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class DiscountCode(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", "Percentage"
        FIXED = "fixed", "Fixed amount"

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="discount_codes")
    code = models.CharField(max_length=40)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Blank for unlimited")
    used_count = models.PositiveIntegerField(default=0, editable=False)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    ticket_types = models.ManyToManyField(
        "tickets.TicketType", blank=True, help_text="Leave empty to apply to all ticket types"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "code"], name="uniq_discount_code_per_event")]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def clean(self):
        if self.kind == self.Kind.PERCENT and not (0 < self.value <= 100):
            raise ValidationError({"value": "Percentage must be between 0 and 100."})
        if self.value is not None and self.value <= 0:
            raise ValidationError({"value": "Value must be positive."})

    @property
    def label(self):
        if self.kind == self.Kind.PERCENT:
            return f"{self.value:f}".rstrip("0").rstrip(".") + "% off"
        from django.conf import settings

        return f"{settings.CURRENCY_SYMBOL}{self.value:,.0f} off"

    def validity_error(self):
        """Return a human-readable reason this code can't be used now, or None."""
        now = timezone.now()
        if not self.is_active:
            return "This code is no longer active."
        if self.valid_from and now < self.valid_from:
            return "This code is not active yet."
        if self.valid_until and now > self.valid_until:
            return "This code has expired."
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return "This code has reached its usage limit."
        return None

    def discount_for(self, lines):
        """
        lines: iterable of (ticket_type, quantity, unit_price).
        Returns discount amount applied to eligible lines only.
        """
        eligible_ids = set(self.ticket_types.values_list("id", flat=True))
        eligible = sum(
            (price * qty for tt, qty, price in lines if not eligible_ids or tt.id in eligible_ids), Decimal("0")
        )
        if eligible <= 0:
            return Decimal("0.00")
        if self.kind == self.Kind.PERCENT:
            amount = eligible * self.value / Decimal("100")
        else:
            amount = min(self.value, eligible)
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

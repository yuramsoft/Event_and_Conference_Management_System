"""
Order creation and the reservation lifecycle.

Inventory model
---------------
* ``TicketType.sold`` is only incremented when payment is confirmed.
* A PENDING order whose ``expires_at`` is in the future *holds* its quantities
  (see ``TicketType.reserved``). When it lapses, Celery marks it EXPIRED and the
  hold disappears automatically — no counters to repair.
* All availability checks run inside a transaction with ``select_for_update`` on
  the ticket-type rows, so two buyers can't both take the last seat.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_action
from apps.discounts.models import DiscountCode
from apps.tickets.models import TicketType

from .models import Order, OrderItem


class OrderError(Exception):
    """User-facing error raised while building an order."""


@dataclass
class Quote:
    lines: list  # [(ticket_type, qty, unit_price)]
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    discount_code: DiscountCode | None
    discount_error: str | None = None


def resolve_discount(event, code):
    if not code:
        return None, None
    dc = DiscountCode.objects.filter(event=event, code=code.strip().upper()).first()
    if dc is None:
        return None, "That discount code doesn't exist for this event."
    err = dc.validity_error()
    return (None, err) if err else (dc, None)


def build_quote(event, selections, code=None, ticket_types=None):
    """
    selections: {ticket_type_id: qty}. Validates limits and availability.
    ticket_types: optional pre-locked queryset/dict for use inside a transaction.
    """
    selections = {int(k): int(v) for k, v in selections.items() if int(v or 0) > 0}
    if not selections:
        raise OrderError("Select at least one ticket.")

    if ticket_types is None:
        ticket_types = {t.id: t for t in TicketType.objects.filter(event=event, id__in=selections)}

    lines = []
    for tt_id, qty in selections.items():
        tt = ticket_types.get(tt_id)
        if tt is None:
            raise OrderError("One of the selected tickets is not available for this event.")
        if not tt.on_sale:
            raise OrderError(f"{tt.name} is not on sale right now.")
        if qty < tt.min_per_order or qty > tt.max_per_order:
            raise OrderError(f"{tt.name}: choose between {tt.min_per_order} and {tt.max_per_order} tickets.")
        if qty > tt.available:
            left = tt.available
            raise OrderError(f"Only {left} {tt.name} ticket{'s' if left != 1 else ''} left." if left else f"{tt.name} is sold out.")
        lines.append((tt, qty, tt.price))

    if event.capacity:
        held = sum(t.sold + t.reserved for t in event.ticket_types.all())
        if held + sum(q for _, q, _ in lines) > event.capacity:
            raise OrderError("The event has reached capacity.")

    subtotal = sum((p * q for _, q, p in lines), Decimal("0.00"))
    dc, dc_error = resolve_discount(event, code)
    discount = dc.discount_for(lines) if dc else Decimal("0.00")
    total = max(subtotal - discount, Decimal("0.00"))
    return Quote(lines, subtotal, discount, total, dc, dc_error)


@transaction.atomic
def create_order(*, event, selections, buyer_name, buyer_email, buyer_phone="", user=None, code=None):
    """Create a PENDING order that reserves inventory for RESERVATION_MINUTES."""
    if not event.is_on_sale:
        raise OrderError("Tickets for this event are not on sale.")

    ids = [int(k) for k, v in selections.items() if int(v or 0) > 0]
    locked = {t.id: t for t in TicketType.objects.select_for_update().filter(event=event, id__in=ids)}
    quote = build_quote(event, selections, code=code, ticket_types=locked)
    if code and quote.discount_error:
        raise OrderError(quote.discount_error)

    order = Order.objects.create(
        event=event,
        user=user if user and user.is_authenticated else None,
        buyer_name=buyer_name.strip(),
        buyer_email=buyer_email.strip().lower(),
        buyer_phone=buyer_phone.strip(),
        discount_code=quote.discount_code,
        subtotal=quote.subtotal,
        discount_amount=quote.discount,
        total=quote.total,
        expires_at=timezone.now() + timedelta(minutes=settings.RESERVATION_MINUTES),
    )
    OrderItem.objects.bulk_create(
        [OrderItem(order=order, ticket_type=tt, quantity=q, unit_price=p) for tt, q, p in quote.lines]
    )
    log_action("order.created", order, description=f"{order.quantity} tickets, total {order.total}")
    return order


@transaction.atomic
def expire_order(order):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.PENDING:
        return False
    order.status = Order.Status.EXPIRED
    order.save(update_fields=["status", "updated_at"])
    log_action("order.expired", order, actor=None)
    return True


@transaction.atomic
def cancel_order(order, by=None):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.PENDING:
        raise OrderError("Only unpaid orders can be cancelled.")
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    log_action("order.cancelled", order, actor=by)
    return order

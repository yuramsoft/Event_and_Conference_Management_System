"""
Payment flow:

    create order → initialize Paystack → Paystack checkout
        → webhook (charge.success) and/or callback redirect
        → verify with Paystack API → fulfill_order (idempotent)
        → issue tickets → confirmation email (Celery)

Both the webhook and the browser callback call ``verify_and_process`` — whichever
arrives first fulfils the order; the second is a no-op.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.audit.services import log_action
from apps.discounts.models import DiscountCode
from apps.refunds.models import RefundRequest
from apps.registrations.models import Order
from apps.tickets.models import Ticket, TicketType

from .models import Payment
from .paystack import PaystackClient, PaystackError

logger = logging.getLogger(__name__)


def get_client():
    return PaystackClient()


def start_payment(order, *, callback_url):
    """Return a URL to send the buyer to. Free orders are fulfilled immediately."""
    if not order.reservation_active:
        raise PaystackError("This reservation has expired. Please select your tickets again.")

    if order.total == 0:
        fulfill_order(order)
        return reverse("payments:complete", args=[order.reference])

    attempt = order.payments.count() + 1
    payment = Payment.objects.create(
        order=order,
        reference=f"{order.reference}-{attempt}",
        amount=order.total,
        currency=settings.CURRENCY,
    )
    data = get_client().initialize(
        email=order.buyer_email,
        amount_kobo=order.amount_kobo,
        reference=payment.reference,
        callback_url=callback_url,
        currency=settings.CURRENCY,
        metadata={"order_reference": order.reference, "event": order.event.title},
    )
    payment.authorization_url = data.get("authorization_url", "")
    payment.access_code = data.get("access_code", "")
    payment.save(update_fields=["authorization_url", "access_code", "updated_at"])
    log_action("payment.initialized", payment, description=payment.reference)
    return payment.authorization_url


def verify_and_process(reference):
    """Ask Paystack for the authoritative status of a transaction and act on it."""
    payment = Payment.objects.select_related("order").filter(reference=reference).first()
    if payment is None:
        logger.warning("Unknown payment reference %s", reference)
        return None
    if payment.status == Payment.Status.SUCCESS and payment.order.is_paid:
        return payment
    data = get_client().verify(reference)
    return apply_transaction_data(payment, data)


@transaction.atomic
def apply_transaction_data(payment, data):
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
    status = data.get("status")
    payment.raw_response = data
    payment.channel = data.get("channel") or ""
    payment.gateway_response = (data.get("gateway_response") or "")[:255]

    if status == "success":
        amount_ok = int(data.get("amount", 0)) >= int((payment.amount * 100).quantize(Decimal("1")))
        currency_ok = (data.get("currency") or payment.currency) == payment.currency
        if not (amount_ok and currency_ok):
            payment.status = Payment.Status.FAILED
            payment.gateway_response = "Amount/currency mismatch"
            payment.save()
            log_action("payment.mismatch", payment, actor=None, received=data.get("amount"))
            return payment
        payment.status = Payment.Status.SUCCESS
        payment.paid_at = parse_datetime(data["paid_at"]) if data.get("paid_at") else timezone.now()
        payment.save()
        fulfill_order(payment.order, payment=payment)
    elif status in {"failed", "abandoned", "reversed"}:
        payment.status = Payment.Status.ABANDONED if status == "abandoned" else Payment.Status.FAILED
        payment.save()
        log_action("payment.failed", payment, actor=None, status=status)
        transaction.on_commit(lambda: _notify_failed(payment.order_id))
    else:  # "ongoing", "pending" … nothing final yet
        payment.save()
    return payment


def _notify_failed(order_id):
    from apps.notifications.tasks import send_payment_failed

    send_payment_failed.delay(order_id)


@transaction.atomic
def fulfill_order(order, payment=None):
    """Mark the order paid, consume inventory and issue tickets. Safe to call twice."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status in (Order.Status.PAID, Order.Status.REFUNDED):
        return order

    items = list(order.items.select_related("ticket_type"))
    tts = {t.id: t for t in TicketType.objects.select_for_update().filter(id__in=[i.ticket_type_id for i in items])}

    # Paid after the hold lapsed? Re-check stock; if gone, keep the money for refund review.
    if order.status != Order.Status.PENDING or not order.reservation_active:
        short = [i for i in items if tts[i.ticket_type_id].available < i.quantity]
        if short:
            order.status = Order.Status.PAID
            order.paid_at = timezone.now()
            order.needs_review = True
            order.save(update_fields=["status", "paid_at", "needs_review", "updated_at"])
            RefundRequest.objects.create(
                order=order,
                amount=order.total,
                reason="Automatic: payment received after the reservation expired and tickets sold out.",
            )
            log_action("order.paid_without_stock", order, actor=None)
            return order

    for item in items:
        TicketType.objects.filter(pk=item.ticket_type_id).update(sold=F("sold") + item.quantity)
        Ticket.objects.bulk_create(
            [
                Ticket(
                    order=order,
                    ticket_type=item.ticket_type,
                    event_id=order.event_id,
                    attendee_name=order.buyer_name,
                    attendee_email=order.buyer_email,
                )
                for _ in range(item.quantity)
            ]
        )
    if order.discount_code_id:
        DiscountCode.objects.filter(pk=order.discount_code_id).update(used_count=F("used_count") + 1)

    order.status = Order.Status.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "paid_at", "updated_at"])
    log_action("order.paid", order, actor=None, payment=getattr(payment, "reference", "free"))

    from apps.notifications.tasks import send_order_confirmation

    transaction.on_commit(lambda: send_order_confirmation.delay(order.pk))
    return order

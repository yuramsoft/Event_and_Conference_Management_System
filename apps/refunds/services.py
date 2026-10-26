from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.audit.services import log_action
from apps.payments.models import Payment
from apps.payments.paystack import PaystackClient, PaystackError
from apps.registrations.models import Order
from apps.tickets.models import Ticket, TicketType

from .models import RefundRequest


class RefundError(Exception):
    pass


def request_refund(order, *, user, reason):
    if not order.is_paid:
        raise RefundError("Only paid orders can be refunded.")
    if order.refunds.exclude(status__in=[RefundRequest.Status.REJECTED, RefundRequest.Status.FAILED]).exists():
        raise RefundError("A refund for this order is already in progress.")
    if order.tickets.filter(status=Ticket.Status.USED).exists():
        raise RefundError("Tickets on this order have already been used.")
    refund = RefundRequest.objects.create(order=order, amount=order.total, reason=reason, requested_by=user)
    log_action("refund.requested", refund, actor=user)
    return refund


def reject_refund(refund, *, reviewer, note=""):
    refund.status = RefundRequest.Status.REJECTED
    refund.reviewed_by = reviewer
    refund.review_note = note
    refund.save()
    log_action("refund.rejected", refund, actor=reviewer)
    _notify(refund)
    return refund


def approve_refund(refund, *, reviewer, note=""):
    """Approve and send to Paystack (free orders are refunded instantly)."""
    refund.status = RefundRequest.Status.APPROVED
    refund.reviewed_by = reviewer
    refund.review_note = note
    refund.save()
    log_action("refund.approved", refund, actor=reviewer)

    payment = refund.order.payments.filter(status=Payment.Status.SUCCESS).first()
    if refund.amount > 0 and payment:
        try:
            data = PaystackClient().refund(
                transaction_reference=payment.reference,
                amount_kobo=int(refund.amount * 100),
                note=f"Refund for {refund.order.reference}",
            )
        except PaystackError as exc:
            refund.status = RefundRequest.Status.FAILED
            refund.gateway_response = {"error": str(exc)}
            refund.save()
            log_action("refund.gateway_failed", refund, actor=reviewer, error=str(exc))
            raise RefundError(str(exc)) from exc
        refund.gateway_reference = str(data.get("id") or "")
        refund.gateway_response = data
    complete_refund(refund)
    return refund


@transaction.atomic
def complete_refund(refund):
    """Cancel tickets, return inventory (unless the order never got stock) and mark order refunded."""
    order = Order.objects.select_for_update().get(pk=refund.order_id)
    if not order.needs_review:
        for item in order.items.all():
            TicketType.objects.filter(pk=item.ticket_type_id, sold__gte=item.quantity).update(
                sold=F("sold") - item.quantity
            )
    order.tickets.update(status=Ticket.Status.CANCELLED)
    order.status = Order.Status.REFUNDED
    order.needs_review = False
    order.save(update_fields=["status", "needs_review", "updated_at"])
    refund.status = RefundRequest.Status.PROCESSED
    refund.processed_at = timezone.now()
    refund.save()
    log_action("refund.processed", refund, actor=refund.reviewed_by)
    transaction.on_commit(lambda: _notify(refund))


def _notify(refund):
    from apps.notifications.tasks import send_refund_update

    send_refund_update.delay(refund.pk)

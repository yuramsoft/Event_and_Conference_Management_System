import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.events.models import Event
from apps.registrations.models import Order
from apps.tickets.models import Ticket
from apps.tickets.qr import qr_png_bytes

from .emails import send_templated
from .models import EmailLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation(self, order_id):
    order = Order.objects.select_related("event", "event__venue").get(pk=order_id)
    tickets = list(order.tickets.select_related("ticket_type"))
    attachments = [(f"ticket-{t.short_code}.png", qr_png_bytes(t.code), "image/png") for t in tickets]
    try:
        send_templated(
            kind=EmailLog.Kind.ORDER_CONFIRMATION,
            to=order.buyer_email,
            subject=f"Your tickets for {order.event.title} ({order.reference})",
            template="order_confirmation",
            context={"order": order, "tickets": tickets, "event": order.event},
            order=order,
            event=order.event,
            attachments=attachments,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def send_payment_failed(order_id):
    order = Order.objects.select_related("event").get(pk=order_id)
    if order.is_paid:
        return
    send_templated(
        kind=EmailLog.Kind.PAYMENT_FAILED,
        to=order.buyer_email,
        subject=f"Payment not completed – {order.event.title}",
        template="payment_failed",
        context={"order": order, "event": order.event},
        order=order,
        event=order.event,
    )


@shared_task
def send_event_reminders():
    """Hourly: email ticket holders of events starting within REMINDER_HOURS_BEFORE. Sent once per person."""
    now = timezone.now()
    window_end = now + timedelta(hours=settings.REMINDER_HOURS_BEFORE)
    sent = 0
    for event in Event.objects.published().filter(starts_at__gt=now, starts_at__lte=window_end):
        already = set(EmailLog.objects.filter(kind=EmailLog.Kind.REMINDER, event=event, success=True).values_list("to", flat=True))
        emails = (
            Ticket.objects.filter(event=event, status=Ticket.Status.VALID)
            .values_list("attendee_email", flat=True)
            .distinct()
        )
        for email in emails:
            if email in already:
                continue
            try:
                send_templated(
                    kind=EmailLog.Kind.REMINDER,
                    to=email,
                    subject=f"Reminder: {event.title} starts {timezone.localtime(event.starts_at):%a %d %b, %I:%M %p}",
                    template="event_reminder",
                    context={"event": event},
                    event=event,
                )
                sent += 1
            except Exception:
                continue
    return sent


@shared_task
def send_refund_update(refund_id):
    from apps.refunds.models import RefundRequest

    refund = RefundRequest.objects.select_related("order", "order__event").get(pk=refund_id)
    send_templated(
        kind=EmailLog.Kind.REFUND,
        to=refund.order.buyer_email,
        subject=f"Refund update for order {refund.order.reference}",
        template="refund_update",
        context={"refund": refund, "order": refund.order, "event": refund.order.event},
        order=refund.order,
        event=refund.order.event,
    )

from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

from apps.notifications.emails import send_templated
from apps.notifications.models import EmailLog
from apps.registrations.models import Order

from .services import attendee_rows, order_rows, organizer_events, to_xlsx, ORDER_HEADERS


@shared_task
def send_daily_sales_summaries():
    """07:00 daily: each organizer with sales yesterday gets a summary + Excel of yesterday's orders."""
    User = get_user_model()
    end = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    sent = 0
    for user in User.objects.filter(role=User.Role.ORGANIZER, is_active=True):
        events = organizer_events(user)
        paid = Order.objects.filter(event__in=events, status=Order.Status.PAID, paid_at__gte=start, paid_at__lt=end)
        if not paid.exists():
            continue
        rows = [r for r in order_rows(events) if r[12] and r[12] >= start.strftime("%Y-%m-%d") and r[12] < end.strftime("%Y-%m-%d")]
        send_templated(
            kind=EmailLog.Kind.REPORT,
            to=user.email,
            subject=f"Sales summary for {start:%a %d %b %Y}",
            template="daily_summary",
            context={
                "user": user,
                "day": start,
                "orders": paid.count(),
                "revenue": paid.aggregate(s=Sum("total"))["s"],
            },
            attachments=[(f"orders-{start:%Y-%m-%d}.xlsx", to_xlsx(ORDER_HEADERS, rows, "Orders"),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
        )
        sent += 1
    return sent


@shared_task
def email_attendee_export(event_id, user_id):
    """For very large events: build the attendee workbook in the background and email it."""
    from apps.events.models import Event
    from .services import ATTENDEE_HEADERS

    event = Event.objects.get(pk=event_id)
    user = get_user_model().objects.get(pk=user_id)
    send_templated(
        kind=EmailLog.Kind.REPORT,
        to=user.email,
        subject=f"Attendee list – {event.title}",
        template="export_ready",
        context={"user": user, "event": event},
        event=event,
        attachments=[(f"attendees-{event.slug}.xlsx", to_xlsx(ATTENDEE_HEADERS, list(attendee_rows(event)), "Attendees"),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
    )

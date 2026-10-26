from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_action
from apps.tickets.models import Ticket

from .models import CheckIn


@dataclass
class CheckInResult:
    result: str
    message: str
    ticket: Ticket | None
    checkin: CheckIn

    @property
    def ok(self):
        return self.result == CheckIn.Result.ACCEPTED

    def as_dict(self):
        t = self.ticket
        return {
            "ok": self.ok,
            "result": self.result,
            "message": self.message,
            "ticket": None
            if t is None
            else {
                "code": t.short_code,
                "attendee": t.attendee_name,
                "email": t.attendee_email,
                "ticket_type": t.ticket_type.name,
                "order": t.order.reference,
                "checked_in_at": timezone.localtime(t.checked_in_at).strftime("%H:%M:%S") if t.checked_in_at else None,
            },
        }


def normalize_code(raw):
    raw = (raw or "").strip()
    # QR may contain a full URL ending in the code
    if "/" in raw:
        raw = raw.rstrip("/").rsplit("/", 1)[-1]
    return raw


@transaction.atomic
def check_in(*, event, code, by, method=CheckIn.Method.SCAN, gate=""):
    code = normalize_code(code)
    ticket = (
        Ticket.objects.select_for_update().select_related("ticket_type", "order").filter(code=code).first()
        if code
        else None
    )
    if ticket is None and len(code) == 8:  # manual entry of the printed short code
        ticket = (
            Ticket.objects.select_for_update()
            .select_related("ticket_type", "order")
            .filter(event=event, code__istartswith=code)
            .first()
        )

    if ticket is None:
        result, message = CheckIn.Result.INVALID, "Ticket not found."
    elif ticket.event_id != event.id:
        result, message = CheckIn.Result.WRONG_EVENT, f"Ticket is for a different event ({ticket.event.title})."
    elif ticket.status == Ticket.Status.CANCELLED:
        result, message = CheckIn.Result.CANCELLED, "Ticket was cancelled or refunded."
    elif ticket.status == Ticket.Status.USED:
        when = timezone.localtime(ticket.checked_in_at).strftime("%H:%M") if ticket.checked_in_at else "earlier"
        result, message = CheckIn.Result.DUPLICATE, f"Already checked in at {when}."
    else:
        ticket.status = Ticket.Status.USED
        ticket.checked_in_at = timezone.now()
        ticket.save(update_fields=["status", "checked_in_at"])
        result, message = CheckIn.Result.ACCEPTED, f"Welcome, {ticket.attendee_name}!"

    record = CheckIn.objects.create(
        event=event,
        ticket=ticket if result != CheckIn.Result.WRONG_EVENT else None,
        scanned_code=code[:60],
        result=result,
        method=method,
        checked_in_by=by,
        gate=gate,
    )
    if result == CheckIn.Result.ACCEPTED:
        log_action("ticket.checked_in", ticket, actor=by)
    return CheckInResult(result, message, ticket if result != CheckIn.Result.WRONG_EVENT else None, record)

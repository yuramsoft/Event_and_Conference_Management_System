from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.events.models import Event
from apps.payments.models import Payment
from apps.refunds.services import RefundError, request_refund
from apps.tickets.models import Ticket

from .models import Order


def _mine(request):
    return Q(user=request.user) | Q(buyer_email__iexact=request.user.email)


@login_required
def dashboard(request):
    orders = Order.objects.filter(_mine(request))
    tickets = Ticket.objects.filter(Q(order__user=request.user) | Q(attendee_email__iexact=request.user.email)).exclude(
        status=Ticket.Status.CANCELLED
    )
    next_events = (
        Event.objects.filter(tickets__in=tickets, ends_at__gte=timezone.now()).distinct().select_related("venue")[:3]
    )
    return render(
        request,
        "attendee/dashboard.html",
        {
            "next_events": next_events,
            "recent_orders": orders.select_related("event")[:5],
            "stats": {
                "upcoming": Event.objects.filter(tickets__in=tickets, ends_at__gte=timezone.now()).distinct().count(),
                "tickets": tickets.count(),
                "orders": orders.filter(status=Order.Status.PAID).count(),
                "attended": Event.objects.filter(tickets__in=tickets.filter(status=Ticket.Status.USED)).distinct().count(),
            },
            "pending": orders.filter(status=Order.Status.PENDING, expires_at__gt=timezone.now()).first(),
        },
    )


@login_required
def my_events(request):
    tickets = Ticket.objects.filter(Q(order__user=request.user) | Q(attendee_email__iexact=request.user.email)).exclude(
        status=Ticket.Status.CANCELLED
    )
    events = Event.objects.filter(tickets__in=tickets).distinct().select_related("venue")
    now = timezone.now()
    return render(
        request,
        "attendee/my_events.html",
        {
            "upcoming": events.filter(ends_at__gte=now).order_by("starts_at"),
            "past": events.filter(ends_at__lt=now).order_by("-starts_at"),
        },
    )


@login_required
def orders(request):
    qs = Order.objects.filter(_mine(request)).select_related("event").prefetch_related("items")
    return render(request, "attendee/orders.html", {"orders": qs})


@login_required
def order_detail(request, reference):
    order = get_object_or_404(Order.objects.filter(_mine(request)).select_related("event", "event__venue"), reference=reference)
    return render(
        request,
        "attendee/order_detail.html",
        {
            "order": order,
            "items": order.items.select_related("ticket_type"),
            "tickets": order.tickets.select_related("ticket_type"),
            "payments": order.payments.all(),
            "refunds": order.refunds.all(),
            "can_refund": order.is_paid and not order.refunds.exclude(status__in=["rejected", "failed"]).exists()
            and not order.event.is_past,
        },
    )


@login_required
@require_POST
def refund_request(request, reference):
    order = get_object_or_404(Order.objects.filter(_mine(request)), reference=reference)
    reason = request.POST.get("reason", "").strip()
    if len(reason) < 5:
        messages.error(request, "Please tell the organizer briefly why you need a refund.")
    else:
        try:
            request_refund(order, user=request.user, reason=reason)
            messages.success(request, "Refund requested. The organizer will review it shortly.")
        except RefundError as exc:
            messages.error(request, str(exc))
    return redirect("attendee:order_detail", reference)


@login_required
def tickets(request):
    qs = (
        Ticket.objects.filter(Q(order__user=request.user) | Q(attendee_email__iexact=request.user.email))
        .select_related("event", "ticket_type", "event__venue")
        .order_by("event__starts_at")
    )
    return render(request, "attendee/tickets.html", {"tickets": qs})


def ticket_detail(request, code):
    """QR ticket. Accessible by the owner, or anyone holding the unguessable code link (sent by email)."""
    ticket = get_object_or_404(Ticket.objects.select_related("event", "event__venue", "ticket_type", "order"), code=code)
    return render(request, "attendee/ticket_detail.html", {"ticket": ticket, "event": ticket.event})


@login_required
def payments(request):
    qs = Payment.objects.filter(order__in=Order.objects.filter(_mine(request))).select_related("order", "order__event")
    return render(request, "attendee/payments.html", {"payments": qs})

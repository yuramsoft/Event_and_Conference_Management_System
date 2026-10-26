from itertools import groupby

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.events.models import Category, Event
from apps.registrations.models import Order
from apps.registrations.services import OrderError, cancel_order, create_order


def _public_events():
    return Event.objects.visible().select_related("venue", "category").with_min_price()


def home(request):
    events = _public_events()
    return render(
        request,
        "public/home.html",
        {
            "featured": events.filter(is_featured=True)[:3] or events[:3],
            "upcoming": events[:8],
            "categories": Category.objects.all(),
        },
    )


def event_list(request):
    qs = _public_events()
    q = request.GET.get("q", "").strip()
    cat = request.GET.get("category", "")
    when = request.GET.get("when", "")
    mode = request.GET.get("mode", "")
    qs = qs.search(q)
    if cat:
        qs = qs.filter(category__slug=cat)
    if mode == "online":
        qs = qs.filter(is_online=True)
    elif mode == "in-person":
        qs = qs.filter(is_online=False)
    today = timezone.localdate()
    if when == "week":
        qs = qs.filter(starts_at__date__lte=today + timezone.timedelta(days=7))
    elif when == "month":
        qs = qs.filter(starts_at__date__lte=today + timezone.timedelta(days=31))
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    return render(
        request,
        "public/event_list.html",
        {"page": page, "categories": Category.objects.all(), "q": q, "cat": cat, "when": when, "mode": mode},
    )


def _get_event_for_viewer(request, slug):
    event = get_object_or_404(Event.objects.select_related("venue", "category", "organizer"), slug=slug)
    is_owner = request.user.is_authenticated and (request.user == event.organizer or request.user.is_superuser)
    if not event.is_published and not is_owner:
        raise Http404
    return event, is_owner


def event_detail(request, slug):
    event, is_owner = _get_event_for_viewer(request, slug)
    sessions = event.sessions.prefetch_related("speakers").all()
    days = [(day, list(items)) for day, items in groupby(sessions, key=lambda s: timezone.localtime(s.starts_at).date())]
    ticket_types = [t for t in event.ticket_types.all() if t.is_active]
    return render(
        request,
        "public/event_detail.html",
        {
            "event": event,
            "is_owner": is_owner,
            "ticket_types": ticket_types,
            "agenda_days": days,
            "speakers": event.speakers.all(),
            "preview": not event.is_published,
        },
    )


def event_agenda(request, slug):
    event, _ = _get_event_for_viewer(request, slug)
    sessions = event.sessions.prefetch_related("speakers").all()
    days = [(day, list(items)) for day, items in groupby(sessions, key=lambda s: timezone.localtime(s.starts_at).date())]
    return render(request, "public/event_agenda.html", {"event": event, "agenda_days": days})


def event_speakers(request, slug):
    event, _ = _get_event_for_viewer(request, slug)
    return render(
        request,
        "public/event_speakers.html",
        {"event": event, "speakers": event.speakers.prefetch_related("sessions").all()},
    )


@require_POST
def reserve(request, slug):
    """Ticket selection form → PENDING order holding inventory."""
    event, _ = _get_event_for_viewer(request, slug)
    selections = {k[4:]: v for k, v in request.POST.items() if k.startswith("qty_") and v.isdigit()}
    user = request.user if request.user.is_authenticated else None
    try:
        order = create_order(
            event=event,
            selections=selections,
            buyer_name=(user.get_full_name() if user else "") or "",
            buyer_email=user.email if user else "",
            user=user,
            code=request.POST.get("discount_code", ""),
        )
    except OrderError as exc:
        messages.error(request, str(exc))
        return redirect(event.get_absolute_url() + "#tickets")
    request.session["orders"] = (request.session.get("orders", []) + [order.reference])[-20:]
    return redirect("core:checkout", order.reference)


def _session_order(request, reference):
    order = get_object_or_404(Order.objects.select_related("event", "event__venue", "discount_code"), reference=reference)
    owns = request.user.is_authenticated and order.user_id == request.user.id
    if not (owns or reference in request.session.get("orders", [])):
        raise Http404
    return order


def checkout(request, reference):
    order = _session_order(request, reference)
    if order.is_paid:
        return redirect("payments:complete", reference)
    if request.method == "POST":
        name = request.POST.get("buyer_name", "").strip()
        email = request.POST.get("buyer_email", "").strip().lower()
        phone = request.POST.get("buyer_phone", "").strip()
        if not name or "@" not in email:
            messages.error(request, "Please enter your name and a valid email address.")
        elif not order.reservation_active:
            messages.error(request, "Your reservation expired. Please select tickets again.")
        else:
            order.buyer_name, order.buyer_email, order.buyer_phone = name, email, phone
            order.save(update_fields=["buyer_name", "buyer_email", "buyer_phone", "updated_at"])
            # hand over to payments:pay (POST) via an auto-submitting form
            return render(request, "public/redirect_to_pay.html", {"order": order})
    return render(
        request,
        "public/checkout.html",
        {"order": order, "items": order.items.select_related("ticket_type"), "paystack_ready": bool(settings.PAYSTACK_SECRET_KEY)},
    )


@require_POST
def cancel_checkout(request, reference):
    order = _session_order(request, reference)
    try:
        cancel_order(order, by=request.user if request.user.is_authenticated else None)
        messages.info(request, "Your reservation was released.")
    except OrderError as exc:
        messages.error(request, str(exc))
    return redirect(order.event.get_absolute_url())


def about(request):
    return render(request, "public/about.html")

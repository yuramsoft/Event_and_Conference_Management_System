import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.checkin.models import CheckIn
from apps.discounts.models import DiscountCode
from apps.events.models import Event
from apps.refunds.models import RefundRequest
from apps.refunds.services import RefundError, approve_refund, reject_refund
from apps.registrations.models import Order
from apps.reports import services as reports
from apps.schedules.models import Session
from apps.speakers.models import Speaker
from apps.tickets.models import Ticket, TicketType
from apps.venues.models import Venue

from .forms import DiscountCodeForm, EventForm, SessionForm, SpeakerForm, TicketTypeForm, VenueForm


# ------------------------------------------------------------------ access control
class OrganizerMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_organizer

    def owned_events(self):
        return reports.organizer_events(self.request.user)


class EventScopedMixin(OrganizerMixin):
    """For objects that live under /organizer/events/<event_pk>/..."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_organizer:
            self.event = get_object_or_404(self.owned_events(), pk=kwargs["event_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["event"] = self.event
        return ctx


def organizer_required(view):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        if not request.user.is_organizer:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


def _event_or_404(request, pk):
    return get_object_or_404(reports.organizer_events(request.user), pk=pk)


class FormPageMixin:
    """Shared form template: organizer/form.html."""

    template_name = "organizer/form.html"
    page_title = ""
    cancel_url_name = None

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["page_title"] = self.page_title or (
            f"Edit {self.model._meta.verbose_name}" if getattr(self, "object", None) else f"New {self.model._meta.verbose_name}"
        )
        ctx["cancel_url"] = self.get_success_url()
        return ctx

    def form_valid(self, form):
        resp = super().form_valid(form)
        verb = "updated" if "pk" in self.kwargs else "created"
        log_action(f"{self.model._meta.model_name}.{verb}", self.object, description=str(self.object))
        messages.success(self.request, f"{self.model._meta.verbose_name.capitalize()} {verb}.")
        return resp


class ConfirmDeleteMixin:
    template_name = "organizer/confirm_delete.html"

    def form_valid(self, form):
        log_action(f"{self.model._meta.model_name}.deleted", self.object, description=str(self.object))
        messages.success(self.request, f"{self.model._meta.verbose_name.capitalize()} deleted.")
        return super().form_valid(form)

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["cancel_url"] = self.get_success_url()
        return ctx


# ------------------------------------------------------------------ dashboard
@organizer_required
def dashboard(request):
    events = reports.organizer_events(request.user)
    return render(
        request,
        "organizer/dashboard.html",
        {
            "s": reports.summary(events),
            "chart": json.dumps(reports.daily_sales(events, 30)),
            "upcoming": events.filter(ends_at__gte=timezone.now()).order_by("starts_at")[:5],
            "recent_orders": Order.objects.filter(event__in=events).select_related("event")[:8],
            "pending_refunds": RefundRequest.objects.filter(order__event__in=events, status="requested").count(),
            "review_orders": Order.objects.filter(event__in=events, needs_review=True).count(),
        },
    )


# ------------------------------------------------------------------ events
class EventList(OrganizerMixin, ListView):
    template_name = "organizer/events/list.html"
    context_object_name = "events"

    def get_queryset(self):
        qs = self.owned_events().select_related("venue").annotate(
            n_tickets=Count("tickets", filter=~Q(tickets__status="cancelled"), distinct=True)
        )
        status = self.request.GET.get("status")
        return qs.filter(status=status) if status else qs.order_by("-starts_at")


class EventCreate(OrganizerMixin, FormPageMixin, CreateView):
    model = Event
    form_class = EventForm
    page_title = "Create event"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        form.instance.organizer = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("organizer:event_manage", args=[self.object.pk]) if self.object else reverse("organizer:events")


class EventUpdate(OrganizerMixin, FormPageMixin, UpdateView):
    model = Event
    form_class = EventForm

    def get_queryset(self):
        return self.owned_events()

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_success_url(self):
        return reverse("organizer:event_manage", args=[self.object.pk])


class EventDelete(OrganizerMixin, ConfirmDeleteMixin, DeleteView):
    model = Event

    def get_queryset(self):
        return self.owned_events()

    def post(self, request, *args, **kwargs):
        event = self.get_object()
        if event.orders.exists():
            messages.error(request, "This event has orders. Cancel it instead of deleting it.")
            return redirect("organizer:event_manage", event.pk)
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("organizer:events")


@organizer_required
def event_manage(request, pk):
    event = _event_or_404(request, pk)
    return render(
        request,
        "organizer/events/manage.html",
        {
            "event": event,
            "ticket_types": event.ticket_types.all(),
            "sessions": event.sessions.prefetch_related("speakers"),
            "speakers": event.speakers.all(),
            "discounts": event.discount_codes.all(),
            "problems": event.publish_problems(),
            "s": reports.summary(Event.objects.filter(pk=event.pk)),
            "checkin": reports.checkin_stats(event),
        },
    )


@organizer_required
def event_publish(request, pk):
    event = _event_or_404(request, pk)
    if request.method != "POST":
        return redirect("organizer:event_manage", pk)
    action = request.POST.get("action")
    if action == "publish":
        problems = event.publish_problems()
        if problems:
            for p in problems:
                messages.error(request, p)
        else:
            event.publish()
            log_action("event.published", event)
            messages.success(request, "Event is live! 🎉")
    elif action == "unpublish":
        event.unpublish()
        log_action("event.unpublished", event)
        messages.info(request, "Event moved back to draft.")
    elif action == "cancel":
        event.status = Event.Status.CANCELLED
        event.save(update_fields=["status", "updated_at"])
        log_action("event.cancelled", event)
        messages.warning(request, "Event cancelled. Review refunds for paid orders.")
    return redirect("organizer:event_manage", pk)


# ------------------------------------------------------------------ venues & speakers (organizer-owned)
class VenueList(OrganizerMixin, ListView):
    template_name = "organizer/venues/list.html"
    context_object_name = "venues"

    def get_queryset(self):
        return Venue.objects.filter(organizer=self.request.user).annotate(n_events=Count("events"))


class VenueCreate(OrganizerMixin, FormPageMixin, CreateView):
    model = Venue
    form_class = VenueForm

    def form_valid(self, form):
        form.instance.organizer = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("organizer:venues")


class VenueUpdate(OrganizerMixin, FormPageMixin, UpdateView):
    model = Venue
    form_class = VenueForm

    def get_queryset(self):
        return Venue.objects.filter(organizer=self.request.user)

    def get_success_url(self):
        return reverse("organizer:venues")


class VenueDelete(OrganizerMixin, ConfirmDeleteMixin, DeleteView):
    model = Venue

    def get_queryset(self):
        return Venue.objects.filter(organizer=self.request.user)

    def get_success_url(self):
        return reverse("organizer:venues")


class SpeakerList(OrganizerMixin, ListView):
    template_name = "organizer/speakers/list.html"
    context_object_name = "speakers"

    def get_queryset(self):
        return Speaker.objects.filter(organizer=self.request.user).prefetch_related("events")


class SpeakerCreate(OrganizerMixin, FormPageMixin, CreateView):
    model = Speaker
    form_class = SpeakerForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        form.instance.organizer = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("organizer:speakers")


class SpeakerUpdate(OrganizerMixin, FormPageMixin, UpdateView):
    model = Speaker
    form_class = SpeakerForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_queryset(self):
        return Speaker.objects.filter(organizer=self.request.user)

    def get_success_url(self):
        return reverse("organizer:speakers")


class SpeakerDelete(OrganizerMixin, ConfirmDeleteMixin, DeleteView):
    model = Speaker

    def get_queryset(self):
        return Speaker.objects.filter(organizer=self.request.user)

    def get_success_url(self):
        return reverse("organizer:speakers")


# ------------------------------------------------------------------ event-scoped: tickets, sessions, discounts
def _event_scoped(model, form_class, list_anchor):
    """Builds Create/Update/Delete views for a model with an `event` FK."""

    class Base(EventScopedMixin):
        def get_queryset(self):
            return model.objects.filter(event=self.event)

        def get_success_url(self):
            return reverse("organizer:event_manage", args=[self.event.pk]) + f"#{list_anchor}"

    class Create(Base, FormPageMixin, CreateView):
        pass

    class Update(Base, FormPageMixin, UpdateView):
        pass

    class Delete(Base, ConfirmDeleteMixin, DeleteView):
        pass

    for cls in (Create, Update):
        cls.model, cls.form_class = model, form_class
    Delete.model = model

    def form_kwargs(self):
        kw = CreateView.get_form_kwargs(self)
        if form_class is not TicketTypeForm:
            kw["event"] = self.event
        return kw

    def ticket_valid(self, form):
        form.instance.event = self.event
        return FormPageMixin.form_valid(self, form)

    for cls in (Create, Update):
        cls.get_form_kwargs = form_kwargs
        cls.form_valid = ticket_valid
    return Create, Update, Delete


TicketTypeCreate, TicketTypeUpdate, TicketTypeDelete = _event_scoped(TicketType, TicketTypeForm, "tickets")
SessionCreate, SessionUpdate, SessionDelete = _event_scoped(Session, SessionForm, "schedule")
DiscountCreate, DiscountUpdate, DiscountDelete = _event_scoped(DiscountCode, DiscountCodeForm, "discounts")


def _guard_ticket_delete(view_cls):
    original = view_cls.post

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.sold or obj.order_items.exists():
            messages.error(request, "This ticket type has orders; deactivate it instead.")
            return redirect(self.get_success_url())
        return original(self, request, *args, **kwargs)

    view_cls.post = post


_guard_ticket_delete(TicketTypeDelete)


@organizer_required
def schedule_builder(request, event_pk):
    event = _event_or_404(request, event_pk)
    sessions = list(event.sessions.prefetch_related("speakers"))
    rooms = sorted({s.room or "Main" for s in sessions})
    return render(
        request,
        "organizer/events/schedule.html",
        {"event": event, "sessions": sessions, "rooms": rooms},
    )


# ------------------------------------------------------------------ attendees, orders, refunds
@organizer_required
def attendees(request, event_pk):
    event = _event_or_404(request, event_pk)
    tickets = Ticket.objects.filter(event=event).select_related("ticket_type", "order")
    return render(request, "organizer/events/attendees.html", {"event": event, "tickets": tickets,
                                                               "checkin": reports.checkin_stats(event)})


@organizer_required
def orders(request):
    events = reports.organizer_events(request.user)
    qs = Order.objects.filter(event__in=events).select_related("event").prefetch_related("items")
    event_id = request.GET.get("event")
    status = request.GET.get("status")
    if event_id:
        qs = qs.filter(event_id=event_id)
    if status:
        qs = qs.filter(status=status)
    if request.GET.get("review"):
        qs = qs.filter(needs_review=True)
    return render(request, "organizer/orders/list.html", {"orders": qs[:1000], "events": events,
                                                          "statuses": Order.Status.choices,
                                                          "f_event": event_id, "f_status": status})


@organizer_required
def order_detail(request, reference):
    order = get_object_or_404(
        Order.objects.filter(event__in=reports.organizer_events(request.user)).select_related("event"), reference=reference
    )
    return render(request, "organizer/orders/detail.html", {
        "order": order,
        "items": order.items.select_related("ticket_type"),
        "tickets": order.tickets.select_related("ticket_type"),
        "payments": order.payments.all(),
        "refunds": order.refunds.all(),
        "audit": AuditLog.objects.filter(target_type="Order", target_id=str(order.pk))[:20],
    })


@organizer_required
def refunds(request):
    qs = RefundRequest.objects.filter(order__event__in=reports.organizer_events(request.user)).select_related(
        "order", "order__event", "requested_by"
    )
    return render(request, "organizer/orders/refunds.html", {"refunds": qs})


@organizer_required
def refund_review(request, pk):
    refund = get_object_or_404(
        RefundRequest.objects.filter(order__event__in=reports.organizer_events(request.user)), pk=pk
    )
    if request.method == "POST" and refund.status == RefundRequest.Status.REQUESTED:
        note = request.POST.get("note", "")
        if request.POST.get("decision") == "approve":
            try:
                approve_refund(refund, reviewer=request.user, note=note)
                messages.success(request, f"Refund for {refund.order.reference} processed.")
            except RefundError as exc:
                messages.error(request, f"Paystack refused the refund: {exc}")
        else:
            reject_refund(refund, reviewer=request.user, note=note)
            messages.info(request, "Refund rejected.")
    return redirect(request.POST.get("next") or "organizer:refunds")


# ------------------------------------------------------------------ check-in
@organizer_required
def checkin(request, event_pk):
    event = _event_or_404(request, event_pk)
    recent = CheckIn.objects.filter(event=event).select_related("ticket", "ticket__ticket_type")[:25]
    return render(request, "organizer/events/checkin.html",
                  {"event": event, "stats": reports.checkin_stats(event), "recent": recent})


# ------------------------------------------------------------------ reports & exports
@organizer_required
def reports_view(request):
    events = reports.organizer_events(request.user)
    days = int(request.GET.get("days", 30)) if request.GET.get("days", "30").isdigit() else 30
    days = min(max(days, 7), 365)
    return render(request, "organizer/reports.html", {
        "s": reports.summary(events),
        "chart": json.dumps(reports.daily_sales(events, days)),
        "by_event": reports.event_breakdown(events),
        "by_type": reports.ticket_type_breakdown(events),
        "days": days,
    })


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file_response(content, filename, content_type):
    resp = HttpResponse(content, content_type=content_type)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@organizer_required
def export_attendees(request, event_pk, fmt):
    event = _event_or_404(request, event_pk)
    rows = list(reports.attendee_rows(event))
    log_action("export.attendees", event, format=fmt, rows=len(rows))
    if fmt == "xlsx":
        return _file_response(reports.to_xlsx(reports.ATTENDEE_HEADERS, rows, "Attendees"),
                              f"attendees-{event.slug}.xlsx", XLSX)
    return _file_response(reports.to_csv(reports.ATTENDEE_HEADERS, rows), f"attendees-{event.slug}.csv", "text/csv")


@organizer_required
def export_orders(request, fmt):
    events = reports.organizer_events(request.user)
    if request.GET.get("event"):
        events = events.filter(pk=request.GET["event"])
    rows = list(reports.order_rows(events))
    stamp = timezone.localdate().isoformat()
    log_action("export.orders", None, format=fmt, rows=len(rows))
    if fmt == "xlsx":
        return _file_response(reports.to_xlsx(reports.ORDER_HEADERS, rows, "Orders"), f"orders-{stamp}.xlsx", XLSX)
    return _file_response(reports.to_csv(reports.ORDER_HEADERS, rows), f"orders-{stamp}.csv", "text/csv")


@organizer_required
def audit_log(request):
    events = reports.organizer_events(request.user)
    order_ids = [str(i) for i in Order.objects.filter(event__in=events).values_list("id", flat=True)[:5000]]
    event_ids = [str(i) for i in events.values_list("id", flat=True)]
    logs = AuditLog.objects.filter(
        Q(actor=request.user) | Q(target_type="Order", target_id__in=order_ids) | Q(target_type="Event", target_id__in=event_ids)
    ).select_related("actor")[:300]
    return render(request, "organizer/audit.html", {"logs": logs})

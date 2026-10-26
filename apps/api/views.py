from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.checkin.services import check_in
from apps.events.models import Event
from apps.payments.paystack import PaystackError
from apps.payments.services import start_payment
from apps.registrations.models import Order
from apps.registrations.services import OrderError, build_quote, create_order
from apps.reports import services as reports
from apps.tickets.models import Ticket

from . import serializers as s


class IsOrganizer(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_organizer)


# ------------------------------------------------------------------ auth
class RegisterView(generics.CreateAPIView):
    serializer_class = s.RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = s.UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# ------------------------------------------------------------------ events (public)
class EventViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Event.objects.visible().select_related("venue", "category").with_min_price()
        qs = qs.search(self.request.query_params.get("q"))
        if cat := self.request.query_params.get("category"):
            qs = qs.filter(category__slug=cat)
        if self.action == "retrieve":
            qs = qs.prefetch_related("ticket_types", "sessions__speakers", "speakers")
        return qs

    def get_serializer_class(self):
        return s.EventDetailSerializer if self.action == "retrieve" else s.EventListSerializer

    @extend_schema(request=s.QuoteRequestSerializer, responses={200: dict})
    @action(detail=True, methods=["post"], permission_classes=[permissions.AllowAny])
    def quote(self, request, slug=None):
        """Price a ticket selection and validate a discount code (used by the checkout page)."""
        event = self.get_object()
        ser = s.QuoteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            q = build_quote(event, ser.validated_data["selections"], ser.validated_data.get("discount_code"))
        except OrderError as exc:
            return Response({"ok": False, "error": str(exc)}, status=400)
        return Response({
            "ok": True,
            "subtotal": str(q.subtotal),
            "discount": str(q.discount),
            "total": str(q.total),
            "discount_label": q.discount_code.label if q.discount_code else None,
            "discount_error": q.discount_error,
            "currency": settings.CURRENCY,
        })


# ------------------------------------------------------------------ orders & tickets (attendee)
class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    lookup_field = "reference"
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        u = self.request.user
        return Order.objects.filter(Q(user=u) | Q(buyer_email__iexact=u.email)).prefetch_related(
            "items__ticket_type", "tickets__ticket_type", "tickets__event"
        ).select_related("event")

    def get_serializer_class(self):
        return s.OrderCreateSerializer if self.action == "create" else s.OrderSerializer

    @extend_schema(request=s.OrderCreateSerializer, responses={201: s.OrderSerializer})
    def create(self, request, *args, **kwargs):
        ser = s.OrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            order = create_order(
                event=d["event"], selections=d["selections"], buyer_name=d["buyer_name"],
                buyer_email=d["buyer_email"], buyer_phone=d.get("buyer_phone", ""), user=request.user,
                code=d.get("discount_code"),
            )
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(s.OrderSerializer(order).data, status=201)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def pay(self, request, reference=None):
        """Initialize Paystack; returns the authorization_url to redirect the buyer to."""
        order = self.get_object()
        try:
            url = start_payment(order, callback_url=request.build_absolute_uri(reverse("payments:callback")))
        except PaystackError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"authorization_url": request.build_absolute_uri(url)})


class MyTicketsView(generics.ListAPIView):
    serializer_class = s.TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        u = self.request.user
        return Ticket.objects.filter(Q(order__user=u) | Q(attendee_email__iexact=u.email)).select_related(
            "event", "ticket_type"
        )


# ------------------------------------------------------------------ organizer
@extend_schema(request=s.CheckInRequestSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsOrganizer])
def checkin_scan(request):
    ser = s.CheckInRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    event = get_object_or_404(reports.organizer_events(request.user), pk=ser.validated_data["event"])
    res = check_in(event=event, code=ser.validated_data["code"], by=request.user,
                   method=ser.validated_data["method"], gate=ser.validated_data.get("gate", ""))
    data = res.as_dict()
    data["stats"] = reports.checkin_stats(event)
    return Response(data, status=200)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsOrganizer])
def checkin_stats(request, event_id):
    event = get_object_or_404(reports.organizer_events(request.user), pk=event_id)
    return Response(reports.checkin_stats(event))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsOrganizer])
def organizer_stats(request):
    events = reports.organizer_events(request.user)
    days = min(max(int(request.query_params.get("days", 30)), 7), 365)
    summary = {k: (str(v) if not isinstance(v, int) else v) for k, v in reports.summary(events).items()}
    return Response({"summary": summary, "daily": reports.daily_sales(events, days)})

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.events.models import Category, Event
from apps.registrations.models import Order, OrderItem
from apps.schedules.models import Session
from apps.speakers.models import Speaker
from apps.tickets.models import Ticket, TicketType
from apps.venues.models import Venue

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "role", "organization"]
        read_only_fields = ["id", "email", "role"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "password", "first_name", "last_name", "phone"]

    def validate_email(self, v):
        if User.objects.filter(email__iexact=v).exists():
            raise serializers.ValidationError("Email already registered.")
        return v.lower()

    def validate_password(self, v):
        validate_password(v)
        return v

    def create(self, data):
        return User.objects.create_user(**data)


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ["id", "name", "address", "city", "state", "country", "capacity", "map_url"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon"]


class TicketTypeSerializer(serializers.ModelSerializer):
    available = serializers.IntegerField(read_only=True)
    on_sale = serializers.BooleanField(read_only=True)
    sale_status = serializers.CharField(read_only=True)

    class Meta:
        model = TicketType
        fields = ["id", "name", "description", "price", "quantity", "available", "on_sale", "sale_status",
                  "min_per_order", "max_per_order", "sales_start", "sales_end"]


class SpeakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Speaker
        fields = ["id", "name", "title", "company", "bio", "photo", "website", "linkedin", "x_handle"]


class SessionSerializer(serializers.ModelSerializer):
    speakers = SpeakerSerializer(many=True, read_only=True)

    class Meta:
        model = Session
        fields = ["id", "title", "description", "kind", "starts_at", "ends_at", "room", "speakers"]


class EventListSerializer(serializers.ModelSerializer):
    venue = VenueSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    min_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    url = serializers.CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = Event
        fields = ["id", "slug", "title", "summary", "banner", "starts_at", "ends_at", "is_online",
                  "venue", "category", "min_price", "url"]


class EventDetailSerializer(EventListSerializer):
    ticket_types = serializers.SerializerMethodField()
    sessions = SessionSerializer(many=True, read_only=True)
    speakers = SpeakerSerializer(many=True, read_only=True)

    class Meta(EventListSerializer.Meta):
        fields = EventListSerializer.Meta.fields + ["description", "ticket_types", "sessions", "speakers", "contact_email"]

    @extend_schema_field(TicketTypeSerializer(many=True))
    def get_ticket_types(self, obj):
        return TicketTypeSerializer(obj.ticket_types.filter(is_active=True), many=True).data


class QuoteRequestSerializer(serializers.Serializer):
    selections = serializers.DictField(child=serializers.IntegerField(min_value=0))
    discount_code = serializers.CharField(required=False, allow_blank=True)


class OrderCreateSerializer(QuoteRequestSerializer):
    event = serializers.SlugRelatedField(slug_field="slug", queryset=Event.objects.published())
    buyer_name = serializers.CharField(max_length=150)
    buyer_email = serializers.EmailField()
    buyer_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)


class OrderItemSerializer(serializers.ModelSerializer):
    ticket_type = serializers.CharField(source="ticket_type.name")

    class Meta:
        model = OrderItem
        fields = ["ticket_type", "quantity", "unit_price"]


class TicketSerializer(serializers.ModelSerializer):
    event = serializers.CharField(source="event.title")
    ticket_type = serializers.CharField(source="ticket_type.name")
    url = serializers.CharField(source="get_absolute_url")
    short_code = serializers.CharField(read_only=True)

    class Meta:
        model = Ticket
        fields = ["code", "short_code", "event", "ticket_type", "attendee_name", "attendee_email", "status",
                  "checked_in_at", "url"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    tickets = TicketSerializer(many=True, read_only=True)
    event = serializers.CharField(source="event.slug")
    seconds_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = ["reference", "event", "status", "buyer_name", "buyer_email", "subtotal", "discount_amount",
                  "total", "expires_at", "seconds_left", "paid_at", "items", "tickets", "created_at"]


class CheckInRequestSerializer(serializers.Serializer):
    event = serializers.IntegerField()
    code = serializers.CharField(max_length=200)
    method = serializers.ChoiceField(choices=["scan", "manual"], default="scan")
    gate = serializers.CharField(required=False, allow_blank=True, max_length=60)

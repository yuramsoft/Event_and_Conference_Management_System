"""Admin registrations for the smaller modules, kept in one place."""
from django.contrib import admin

from apps.audit.models import AuditLog
from apps.checkin.models import CheckIn
from apps.discounts.models import DiscountCode
from apps.notifications.models import EmailLog
from apps.payments.models import Payment, WebhookEvent
from apps.refunds.models import RefundRequest
from apps.registrations.models import Order, OrderItem
from apps.schedules.models import Session
from apps.speakers.models import Speaker
from apps.tickets.models import Ticket, TicketType
from apps.venues.models import Venue


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "capacity", "organizer"]
    search_fields = ["name", "city", "address"]


@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    list_display = ["name", "title", "company", "organizer"]
    search_fields = ["name", "company"]
    filter_horizontal = ["events"]


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ["title", "event", "kind", "starts_at", "ends_at", "room"]
    list_filter = ["kind", "event"]
    filter_horizontal = ["speakers"]


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "event", "price", "quantity", "sold", "is_active"]
    list_filter = ["is_active", "event"]
    readonly_fields = ["sold"]


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ["short_code", "attendee_name", "event", "ticket_type", "status", "checked_in_at"]
    list_filter = ["status", "event"]
    search_fields = ["code", "attendee_name", "attendee_email", "order__reference"]
    readonly_fields = ["code", "issued_at"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["ticket_type", "quantity", "unit_price"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["reference", "event", "buyer_email", "total", "status", "needs_review", "created_at"]
    list_filter = ["status", "needs_review", "event"]
    search_fields = ["reference", "buyer_email", "buyer_name"]
    readonly_fields = ["reference", "subtotal", "discount_amount", "total", "paid_at", "created_at"]
    inlines = [OrderItemInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "order", "amount", "status", "channel", "paid_at"]
    list_filter = ["status", "channel"]
    search_fields = ["reference", "order__reference"]
    readonly_fields = [f.name for f in Payment._meta.fields]


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["event", "reference", "signature_valid", "processed", "received_at"]
    list_filter = ["event", "processed", "signature_valid"]
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]


@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "event", "kind", "value", "used_count", "max_uses", "is_active"]
    list_filter = ["kind", "is_active"]
    filter_horizontal = ["ticket_types"]


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ["scanned_code", "event", "result", "method", "checked_in_by", "created_at"]
    list_filter = ["result", "method", "event"]


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display = ["order", "amount", "status", "requested_by", "created_at", "processed_at"]
    list_filter = ["status"]


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["kind", "to", "subject", "success", "sent_at"]
    list_filter = ["kind", "success"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "action", "actor", "target_type", "target_id", "ip_address"]
    list_filter = ["action"]
    search_fields = ["action", "target_id", "description"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

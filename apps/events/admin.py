from django.contrib import admin

from apps.schedules.models import Session
from apps.tickets.models import TicketType

from .models import Category, Event


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 0
    readonly_fields = ["sold"]


class SessionInline(admin.TabularInline):
    model = Session
    extra = 0
    filter_horizontal = ["speakers"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "icon"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "organizer", "starts_at", "status", "is_featured", "venue"]
    list_filter = ["status", "is_featured", "category", "is_online"]
    search_fields = ["title", "summary", "organizer__email"]
    prepopulated_fields = {"slug": ["title"]}
    date_hierarchy = "starts_at"
    inlines = [TicketTypeInline, SessionInline]
    actions = ["publish", "unpublish"]

    @admin.action(description="Publish selected events")
    def publish(self, request, queryset):
        for e in queryset:
            e.publish()

    @admin.action(description="Move selected events to draft")
    def unpublish(self, request, queryset):
        queryset.update(status=Event.Status.DRAFT)

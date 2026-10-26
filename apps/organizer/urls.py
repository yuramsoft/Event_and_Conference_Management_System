from django.urls import path

from . import views as v

app_name = "organizer"

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    # events
    path("events/", v.EventList.as_view(), name="events"),
    path("events/new/", v.EventCreate.as_view(), name="event_create"),
    path("events/<int:pk>/", v.event_manage, name="event_manage"),
    path("events/<int:pk>/edit/", v.EventUpdate.as_view(), name="event_edit"),
    path("events/<int:pk>/delete/", v.EventDelete.as_view(), name="event_delete"),
    path("events/<int:pk>/publish/", v.event_publish, name="event_publish"),
    # tickets
    path("events/<int:event_pk>/tickets/new/", v.TicketTypeCreate.as_view(), name="ticket_create"),
    path("events/<int:event_pk>/tickets/<int:pk>/edit/", v.TicketTypeUpdate.as_view(), name="ticket_edit"),
    path("events/<int:event_pk>/tickets/<int:pk>/delete/", v.TicketTypeDelete.as_view(), name="ticket_delete"),
    # schedule
    path("events/<int:event_pk>/schedule/", v.schedule_builder, name="schedule"),
    path("events/<int:event_pk>/schedule/new/", v.SessionCreate.as_view(), name="session_create"),
    path("events/<int:event_pk>/schedule/<int:pk>/edit/", v.SessionUpdate.as_view(), name="session_edit"),
    path("events/<int:event_pk>/schedule/<int:pk>/delete/", v.SessionDelete.as_view(), name="session_delete"),
    # discounts
    path("events/<int:event_pk>/discounts/new/", v.DiscountCreate.as_view(), name="discount_create"),
    path("events/<int:event_pk>/discounts/<int:pk>/edit/", v.DiscountUpdate.as_view(), name="discount_edit"),
    path("events/<int:event_pk>/discounts/<int:pk>/delete/", v.DiscountDelete.as_view(), name="discount_delete"),
    # attendees & check-in
    path("events/<int:event_pk>/attendees/", v.attendees, name="attendees"),
    path("events/<int:event_pk>/attendees/export.<str:fmt>", v.export_attendees, name="export_attendees"),
    path("events/<int:event_pk>/checkin/", v.checkin, name="checkin"),
    # venues & speakers
    path("venues/", v.VenueList.as_view(), name="venues"),
    path("venues/new/", v.VenueCreate.as_view(), name="venue_create"),
    path("venues/<int:pk>/edit/", v.VenueUpdate.as_view(), name="venue_edit"),
    path("venues/<int:pk>/delete/", v.VenueDelete.as_view(), name="venue_delete"),
    path("speakers/", v.SpeakerList.as_view(), name="speakers"),
    path("speakers/new/", v.SpeakerCreate.as_view(), name="speaker_create"),
    path("speakers/<int:pk>/edit/", v.SpeakerUpdate.as_view(), name="speaker_edit"),
    path("speakers/<int:pk>/delete/", v.SpeakerDelete.as_view(), name="speaker_delete"),
    # orders, refunds, reports
    path("orders/", v.orders, name="orders"),
    path("orders/export.<str:fmt>", v.export_orders, name="export_orders"),
    path("orders/<str:reference>/", v.order_detail, name="order_detail"),
    path("refunds/", v.refunds, name="refunds"),
    path("refunds/<int:pk>/review/", v.refund_review, name="refund_review"),
    path("reports/", v.reports_view, name="reports"),
    path("audit/", v.audit_log, name="audit"),
]

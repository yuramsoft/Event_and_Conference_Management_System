from django.urls import path

from . import views_attendee as v

app_name = "attendee"

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("events/", v.my_events, name="my_events"),
    path("orders/", v.orders, name="orders"),
    path("orders/<str:reference>/", v.order_detail, name="order_detail"),
    path("orders/<str:reference>/refund/", v.refund_request, name="refund_request"),
    path("tickets/", v.tickets, name="tickets"),
    path("tickets/<str:code>/", v.ticket_detail, name="ticket_detail"),
    path("payments/", v.payments, name="payments"),
]

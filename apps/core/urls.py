from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("events/", views.event_list, name="event_list"),
    path("events/<slug:slug>/", views.event_detail, name="event_detail"),
    path("events/<slug:slug>/agenda/", views.event_agenda, name="event_agenda"),
    path("events/<slug:slug>/speakers/", views.event_speakers, name="event_speakers"),
    path("events/<slug:slug>/reserve/", views.reserve, name="reserve"),
    path("checkout/<str:reference>/", views.checkout, name="checkout"),
    path("checkout/<str:reference>/cancel/", views.cancel_checkout, name="cancel_checkout"),
]

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

router = DefaultRouter()
router.register("events", views.EventViewSet, basename="event")
router.register("orders", views.OrderViewSet, basename="order")

app_name = "api"

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/tickets/", views.MyTicketsView.as_view(), name="my_tickets"),
    path("checkin/scan/", views.checkin_scan, name="checkin_scan"),
    path("checkin/<int:event_id>/stats/", views.checkin_stats, name="checkin_stats"),
    path("organizer/stats/", views.organizer_stats, name="organizer_stats"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    path("redoc/", SpectacularRedocView.as_view(url_name="api:schema"), name="redoc"),
    path("", include(router.urls)),
]

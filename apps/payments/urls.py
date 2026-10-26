from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("pay/<str:reference>/", views.pay, name="pay"),
    path("callback/", views.callback, name="callback"),
    path("complete/<str:reference>/", views.complete, name="complete"),
    path("webhook/paystack/", views.webhook, name="webhook"),
]

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "EventHandler administration"
admin.site.site_title = "EventHandler admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("me/", include("apps.registrations.urls_attendee")),
    path("organizer/", include("apps.organizer.urls")),
    path("payments/", include("apps.payments.urls")),
    path("api/", include("apps.api.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.conf import settings


def site(request):
    return {
        "SITE_NAME": settings.SITE_NAME,
        "CURRENCY": settings.CURRENCY,
        "CURRENCY_SYMBOL": settings.CURRENCY_SYMBOL,
        "RESERVATION_MINUTES": settings.RESERVATION_MINUTES,
    }

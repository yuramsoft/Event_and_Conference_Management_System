import logging

from celery import shared_task
from django.utils import timezone

from .models import Order
from .services import expire_order

logger = logging.getLogger(__name__)


@shared_task
def release_expired_reservations():
    """Runs every minute via Celery beat: frees inventory held by unpaid orders."""
    stale = Order.objects.filter(status=Order.Status.PENDING, expires_at__lte=timezone.now())
    released = sum(1 for order in stale.iterator() if expire_order(order))
    if released:
        logger.info("Released %s expired reservations", released)
    return released

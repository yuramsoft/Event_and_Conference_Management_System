import logging

from celery import shared_task

from .models import WebhookEvent
from .paystack import PaystackError
from .services import verify_and_process

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def process_webhook(self, webhook_id):
    record = WebhookEvent.objects.get(pk=webhook_id)
    if record.processed:
        return "already processed"
    if record.event in {"charge.success", "charge.failed"} and record.reference:
        try:
            # Never trust the webhook body alone — always re-verify with the API.
            verify_and_process(record.reference)
        except PaystackError as exc:
            record.error = str(exc)
            record.save(update_fields=["error"])
            raise self.retry(exc=exc)
    record.processed = True
    record.save(update_fields=["processed"])
    return "ok"

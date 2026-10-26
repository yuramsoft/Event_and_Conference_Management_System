import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import EmailLog

logger = logging.getLogger(__name__)


def send_templated(*, kind, to, subject, template, context, order=None, event=None, attachments=()):
    """Render templates/emails/<template>.txt|.html and send. Logs every attempt."""
    context = {"site_url": settings.SITE_URL, "site_name": settings.SITE_NAME, **context}
    text = render_to_string(f"emails/{template}.txt", context)
    html = render_to_string(f"emails/{template}.html", context)
    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
    msg.attach_alternative(html, "text/html")
    for name, content, mimetype in attachments:
        msg.attach(name, content, mimetype)
    try:
        msg.send()
        EmailLog.objects.create(kind=kind, to=to, subject=subject, order=order, event=event)
        return True
    except Exception as exc:
        logger.exception("Email %s to %s failed", kind, to)
        EmailLog.objects.create(kind=kind, to=to, subject=subject, order=order, event=event, success=False, error=str(exc))
        raise

import logging

from .middleware import get_current_request
from .models import AuditLog

logger = logging.getLogger(__name__)


def _client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(action, target=None, actor=None, description="", **metadata):
    """Record an audit entry. Never raises: auditing must not break business flows."""
    try:
        request = get_current_request()
        if actor is None and request is not None and getattr(request, "user", None) and request.user.is_authenticated:
            actor = request.user
        return AuditLog.objects.create(
            actor=actor,
            action=action,
            target_type=target.__class__.__name__ if target is not None else "",
            target_id=str(getattr(target, "pk", "") or ""),
            description=description[:255],
            metadata=metadata,
            ip_address=_client_ip(request),
        )
    except Exception:  # pragma: no cover
        logger.exception("Failed to write audit log for %s", action)
        return None

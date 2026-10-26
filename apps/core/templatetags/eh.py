from decimal import Decimal

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

from apps.tickets.qr import qr_svg

register = template.Library()


@register.filter
def money(value):
    """₦12,500 / ₦12,500.50 / Free."""
    if value in (None, ""):
        return ""
    value = Decimal(value)
    if value == 0:
        return "Free"
    fmt = f"{value:,.0f}" if value == value.to_integral() else f"{value:,.2f}"
    return f"{settings.CURRENCY_SYMBOL}{fmt}"


@register.filter
def money0(value):
    """Like money but shows ₦0 instead of Free (for totals)."""
    value = Decimal(value or 0)
    fmt = f"{value:,.0f}" if value == value.to_integral() else f"{value:,.2f}"
    return f"{settings.CURRENCY_SYMBOL}{fmt}"


@register.simple_tag
def qr(data):
    return mark_safe(qr_svg(data))


@register.simple_tag(takes_context=True)
def active(context, *names):
    """'active' if the current url name (ns:name) starts with any of names."""
    match = getattr(context.get("request"), "resolver_match", None)
    if not match:
        return ""
    current = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
    return "active" if any(current.startswith(n) for n in names) else ""


@register.filter
def get_item(d, key):
    return d.get(key) if hasattr(d, "get") else None

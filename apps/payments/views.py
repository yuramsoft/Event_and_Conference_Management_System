import json
import logging

from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.registrations.models import Order

from .models import WebhookEvent
from .paystack import PaystackError, valid_signature
from .services import start_payment, verify_and_process
from .tasks import process_webhook

logger = logging.getLogger(__name__)


def _order_for_session(request, reference):
    """Orders are visible to their owner, or to the browser session that created them."""
    order = get_object_or_404(Order.objects.select_related("event"), reference=reference)
    owns = request.user.is_authenticated and order.user_id == request.user.id
    if not (owns or reference in request.session.get("orders", []) or request.user.is_staff):
        raise Http404
    return order


@require_POST
def pay(request, reference):
    order = _order_for_session(request, reference)
    if order.is_paid:
        return redirect("payments:complete", reference)
    if not order.buyer_email or not order.buyer_name:
        messages.error(request, "Please enter your details first.")
        return redirect("core:checkout", reference)
    try:
        url = start_payment(order, callback_url=request.build_absolute_uri(reverse("payments:callback")))
    except PaystackError as exc:
        messages.error(request, str(exc))
        return redirect("core:checkout", reference)
    return redirect(url)


def callback(request):
    """Paystack redirects the buyer here with ?reference=..."""
    reference = request.GET.get("reference") or request.GET.get("trxref")
    if not reference:
        return HttpResponseBadRequest("Missing reference")
    try:
        payment = verify_and_process(reference)
    except PaystackError as exc:
        messages.warning(request, f"We couldn't confirm your payment yet ({exc}). We'll email you once it clears.")
        payment = None
    order_ref = payment.order.reference if payment else reference.rsplit("-", 1)[0]
    return redirect("payments:complete", order_ref)


def complete(request, reference):
    order = _order_for_session(request, reference)
    return render(request, "public/payment_complete.html", {"order": order, "tickets": order.tickets.all()})


@csrf_exempt
@require_POST
def webhook(request):
    """Paystack webhook. Verify signature, store, process asynchronously, return 200 fast."""
    raw = request.body
    sig_ok = valid_signature(raw, request.headers.get("X-Paystack-Signature", ""))
    try:
        payload = json.loads(raw)
    except ValueError:
        return HttpResponseBadRequest("Invalid JSON")
    record = WebhookEvent.objects.create(
        event=payload.get("event", "")[:60],
        reference=(payload.get("data") or {}).get("reference", "")[:60],
        payload=payload,
        signature_valid=sig_ok,
    )
    if not sig_ok:
        logger.warning("Rejected Paystack webhook with bad signature (id=%s)", record.pk)
        return HttpResponse(status=401)
    process_webhook.delay(record.pk)
    return HttpResponse(status=200)

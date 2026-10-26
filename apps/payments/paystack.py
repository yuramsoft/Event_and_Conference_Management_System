"""Thin Paystack client. Docs: https://paystack.com/docs/api/"""
import hashlib
import hmac
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    pass


class PaystackClient:
    def __init__(self, secret_key=None, base_url=None, timeout=20):
        self.secret_key = secret_key or settings.PAYSTACK_SECRET_KEY
        self.base_url = (base_url or settings.PAYSTACK_BASE_URL).rstrip("/")
        self.timeout = timeout

    def _request(self, method, path, **kwargs):
        if not self.secret_key:
            raise PaystackError("PAYSTACK_SECRET_KEY is not configured.")
        headers = {"Authorization": f"Bearer {self.secret_key}", "Content-Type": "application/json"}
        try:
            resp = requests.request(method, f"{self.base_url}{path}", headers=headers, timeout=self.timeout, **kwargs)
            body = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.exception("Paystack request failed: %s %s", method, path)
            raise PaystackError("Could not reach Paystack. Please try again.") from exc
        if not resp.ok or not body.get("status"):
            raise PaystackError(body.get("message") or f"Paystack error ({resp.status_code})")
        return body["data"]

    def initialize(self, *, email, amount_kobo, reference, callback_url, metadata=None, currency="NGN"):
        return self._request(
            "POST",
            "/transaction/initialize",
            json={
                "email": email,
                "amount": amount_kobo,
                "reference": reference,
                "callback_url": callback_url,
                "currency": currency,
                "metadata": metadata or {},
            },
        )

    def verify(self, reference):
        return self._request("GET", f"/transaction/verify/{reference}")

    def refund(self, *, transaction_reference, amount_kobo=None, note=""):
        payload = {"transaction": transaction_reference, "merchant_note": note[:255]}
        if amount_kobo:
            payload["amount"] = amount_kobo
        return self._request("POST", "/refund", json=payload)


def valid_signature(raw_body: bytes, signature: str, secret_key=None) -> bool:
    """Paystack signs webhooks with HMAC-SHA512 of the raw body using your secret key."""
    secret = (secret_key or settings.PAYSTACK_SECRET_KEY or "").encode()
    if not secret or not signature:
        return False
    expected = hmac.new(secret, raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)

# EventHandler

Event management and ticketing platform built with **Django + Django REST Framework**, server-rendered
**Bootstrap 5** templates with **vanilla JavaScript**, **MySQL 8**, **Celery + Redis** and **Paystack**.

Organizers publish events with venues, speakers, multi-track schedules, ticket tiers and discount codes.
Attendees buy tickets (seats are held for 15 minutes while they pay), receive QR tickets by email, and are
checked in at the door from any phone camera. Organizers get live dashboards, revenue reports and
CSV/Excel exports.

```
Browser ──► Django templates (Bootstrap 5 + vanilla JS)
               │                         └── fetch() ──► DRF endpoints (/api/…)
               ▼
        Django / DRF ──► MySQL 8
               │
               └──► Redis ──► Celery worker + beat ──► emails · reminders · reservation expiry · reports
```

---

## Features

| Area | What's included |
|---|---|
| **Public site** | Home, event listing with search/filters, event detail with agenda & speakers tabs, printable agenda, speaker bios, ticket selection with live pricing and discount codes, checkout with reservation countdown, Paystack redirect, confirmation page with QR tickets |
| **Attendee dashboard** | Overview, my events (upcoming/past), orders, order detail with refund request, tickets, full-screen QR ticket, payment history, profile & password |
| **Organizer dashboard** | Stats + 30-day sales chart (Chart.js), events CRUD, publish/unpublish/cancel with pre-publish checks, venues, speakers, schedule builder with overlap detection, ticket tiers with sales windows and per-order limits, discount codes (percent/fixed, usage caps, ticket-type scoping), attendees (DataTables), orders & payments, refund review, camera check-in, revenue reports, CSV/Excel exports, audit log |
| **Payments** | Paystack initialize → checkout → callback + signed webhook (HMAC-SHA512) → server-side verify → idempotent fulfilment. Amount/currency checked. Free orders skip Paystack |
| **Inventory** | Pending orders hold stock for `RESERVATION_MINUTES` (default 15). Row locks (`select_for_update`) prevent overselling. Celery releases expired holds every minute. A payment that lands after its hold lapsed is honoured if stock remains; otherwise it's flagged and an automatic refund request is created |
| **Check-in** | html5-qrcode scanner + manual 8-char code entry, beep/vibrate, duplicate/wrong-event/cancelled detection, every scan logged, live counters for multiple gates |
| **Background jobs** | Order confirmation email with QR PNG attachments, payment-failed email, event reminders (once per attendee), daily sales summary with Excel attachment, reservation expiry |
| **API** | JWT (SimpleJWT) + session auth, OpenAPI schema with Swagger UI (`/api/docs/`) and ReDoc (`/api/redoc/`) |
| **Admin** | Django admin for every model, including read-only payment, webhook and audit records |

## Modules

```
apps/
  accounts       custom User (email login, attendee/organizer role), signup/login/profile
  events         Event, Category; publish rules
  venues         Venue
  speakers       Speaker (M2M to events)
  schedules      Session (agenda items, rooms/tracks, speakers)
  tickets        TicketType (tiers, sales windows) and Ticket (issued, QR code); qr.py
  discounts      DiscountCode
  registrations  Order, OrderItem; services.py (quote, reserve, expire); attendee views; tasks
  payments       Payment, WebhookEvent; paystack.py client; services.py (verify/fulfil); webhook
  checkin        CheckIn log; services.py (scan logic)
  refunds        RefundRequest; services.py (request/approve/reject via Paystack refunds API)
  notifications  EmailLog; templated emails; Celery tasks
  reports        aggregations, CSV/XLSX exports, daily summary task
  audit          AuditLog, request-context middleware, log_action()
  core           public pages, template tags, seed_demo command
  organizer      organizer dashboard views/forms
  api            DRF serializers, viewsets and routes
```

---

## Quick start (local, SQLite, no Redis)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt                         # mysqlclient needs MySQL headers; skip it for SQLite
cp .env.example .env
# in .env set: DB_ENGINE=sqlite   and comment out REDIS_URL
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

With `DJANGO_DEBUG=True` and no `REDIS_URL`, Celery tasks run inline, so no worker is needed. Emails print
to the terminal.

Demo accounts created by `seed_demo`:

| Role | Email | Password |
|---|---|---|
| Organizer | organizer@example.com | demo12345 |
| Attendee | attendee@example.com | demo12345 |
| Admin | admin@example.com | admin12345 |

Every event has the discount code **WELCOME10**.

## Running with MySQL + Redis + Celery (Docker)

```bash
cp .env.example .env          # set DJANGO_SECRET_KEY and Paystack keys
docker compose up --build -d
docker compose exec web python manage.py seed_demo      # optional
docker compose exec web python manage.py createsuperuser
```

Services: `web` (gunicorn on :8000, runs migrations + collectstatic), `worker` (Celery), `beat`
(Celery beat with the database scheduler), `db` (MySQL 8), `redis`.

Without Docker, run these alongside `runserver`:

```bash
celery -A config worker -l info
celery -A config beat -l info
```

## Paystack setup

1. Put your test keys in `.env` (`PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`).
2. In the Paystack dashboard set the **webhook URL** to `https://<your-domain>/payments/webhook/paystack/`.
   For local testing, expose your server with a tunnel (e.g. ngrok) and use that URL.
3. The callback URL (`/payments/callback/`) is sent automatically on each transaction.

The webhook rejects requests whose `X-Paystack-Signature` doesn't match, stores every event in
`WebhookEvent`, and processes it in Celery. Fulfilment never trusts the webhook body; it always re-verifies
the transaction with Paystack's API and checks the amount and currency.

## API

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/api/auth/token/`, `/api/auth/token/refresh/`, `/api/auth/register/` | – |
| GET/PATCH | `/api/me/` · GET `/api/me/tickets/` | JWT/session |
| GET | `/api/events/`, `/api/events/{slug}/` | public |
| POST | `/api/events/{slug}/quote/` – price a selection + validate discount | public |
| GET/POST | `/api/orders/` · GET `/api/orders/{reference}/` | JWT/session |
| POST | `/api/orders/{reference}/pay/` → `authorization_url` | JWT/session |
| POST | `/api/checkin/scan/` · GET `/api/checkin/{event_id}/stats/` | organizer |
| GET | `/api/organizer/stats/?days=30` | organizer |

Full schema: `/api/docs/` (Swagger) and `/api/redoc/`.

## Tests

```bash
DJANGO_SETTINGS_MODULE=config.settings_test python manage.py test tests
```

38 tests cover reservations and overselling, expiry, discounts, free orders, the Paystack webhook
(bad signature, success, retries/idempotency, amount mismatch, failed charges, late payments with and
without stock), callback verification, check-in outcomes, refunds (including gateway failure),
permissions between organizers, exports, and the JWT/REST API. Paystack calls are mocked.

## Configuration

All settings come from environment variables; see `.env.example`. Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `DB_ENGINE` | `mysql` | `mysql` or `sqlite` |
| `RESERVATION_MINUTES` | `15` | How long unpaid orders hold tickets |
| `REMINDER_HOURS_BEFORE` | `24` | Reminder email window |
| `CURRENCY` / `CURRENCY_SYMBOL` | `NGN` / `₦` | Paystack currency and display |
| `CELERY_TASK_ALWAYS_EAGER` | on in DEBUG without Redis | Run tasks inline |

## Production checklist

- `DJANGO_DEBUG=False`, a long random `DJANGO_SECRET_KEY`, real `DJANGO_ALLOWED_HOSTS` and
  `DJANGO_CSRF_TRUSTED_ORIGINS`, `SITE_URL` with https.
- SMTP email backend configured.
- Live Paystack keys and webhook URL.
- Put Nginx/Caddy (TLS) in front of gunicorn and serve `/media/` from a volume or object storage.
- Back up the MySQL volume.

## Frontend libraries (CDN)

Bootstrap 5.3, Bootstrap Icons, Chart.js 4, DataTables 2, qrcodejs (ticket display) and html5-qrcode
(scanner). No build step. Swap to local copies under `static/` if you need to run offline.

"""
python manage.py seed_demo

Creates demo accounts, venues, speakers, events with schedules and ticket tiers,
discount codes, and a few paid orders with issued tickets so every screen has data.
Safe to run more than once.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.discounts.models import DiscountCode
from apps.events.models import Category, Event
from apps.payments.models import Payment
from apps.payments.services import fulfill_order
from apps.registrations.services import create_order
from apps.schedules.models import Session
from apps.speakers.models import Speaker
from apps.tickets.models import TicketType
from apps.venues.models import Venue

CATEGORIES = [("Technology", "cpu"), ("Business", "briefcase"), ("Music", "music-note-beamed"),
              ("Education", "mortarboard"), ("Health", "heart-pulse"), ("Community", "people")]

SPEAKERS = [
    ("Amina Bello", "CTO", "Kanuri Labs", "Builds payment infrastructure for West African fintechs."),
    ("Chinedu Okafor", "Head of Data", "Lagos Analytics", "Leads a team of 30 data scientists working on credit risk."),
    ("Fatima Abubakar", "Founder", "SolarGrid NG", "Engineer bringing off-grid solar to rural clinics."),
    ("Tunde Adeyemi", "Product Lead", "Paylane", "Ten years designing checkout flows people actually finish."),
    ("Ngozi Eze", "Research Scientist", "AI Africa", "Works on speech recognition for Hausa, Yoruba and Igbo."),
    ("Ibrahim Musa", "Senior Engineer", "CloudNaija", "Runs Kubernetes clusters serving 20M requests a day."),
]

EVENTS = [
    {
        "title": "Abuja Tech Summit 2026", "cat": "Technology", "days": 18, "hours": 9, "length": 9,
        "summary": "A day of talks and workshops on AI, fintech and cloud infrastructure in Nigeria.",
        "tickets": [("Early Bird", 15000, 150), ("Regular", 25000, 300), ("VIP", 75000, 40)],
        "featured": True,
    },
    {
        "title": "Founders & Funders Breakfast", "cat": "Business", "days": 9, "hours": 8, "length": 3,
        "summary": "Pitch practice, investor Q&A and a proper Nigerian breakfast.",
        "tickets": [("Founder", 10000, 60), ("Investor", 0, 25)],
        "featured": True,
    },
    {
        "title": "Highlife Nights: Live in Lagos", "cat": "Music", "days": 25, "hours": 19, "length": 4,
        "summary": "An evening of live highlife and afrobeat with a 10-piece band.",
        "tickets": [("Standard", 8000, 400), ("Table for 4", 60000, 20)],
        "featured": True,
    },
    {
        "title": "Intro to Embedded Systems Workshop", "cat": "Education", "days": 5, "hours": 10, "length": 6,
        "summary": "Hands-on ESP32 workshop: sensors, Wi-Fi and your first IoT dashboard.",
        "tickets": [("Student", 5000, 30), ("Professional", 12000, 20)],
    },
    {
        "title": "Remote Work Meetup (Online)", "cat": "Community", "days": 3, "hours": 17, "length": 2,
        "summary": "Tools, rituals and contracts for Nigerians working with global teams.",
        "tickets": [("Free RSVP", 0, 500)],
        "online": True,
    },
]


class Command(BaseCommand):
    help = "Seed demo data (organizer, attendee, events, tickets, orders)."

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(7)
        org, created = User.objects.get_or_create(
            email="organizer@example.com",
            defaults={"first_name": "Ada", "last_name": "Organizer", "role": User.Role.ORGANIZER,
                      "organization": "Arewa Events Co."},
        )
        if created:
            org.set_password("demo12345")
            org.save()
        att, created = User.objects.get_or_create(
            email="attendee@example.com", defaults={"first_name": "Musa", "last_name": "Attendee"}
        )
        if created:
            att.set_password("demo12345")
            att.save()
        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser("admin@example.com", "admin12345", first_name="Site", last_name="Admin")

        cats = {n: Category.objects.get_or_create(name=n, defaults={"icon": i})[0] for n, i in CATEGORIES}

        venues = [
            Venue.objects.get_or_create(organizer=org, name="International Conference Centre",
                                        defaults={"address": "Herbert Macaulay Way, Central Business District",
                                                  "city": "Abuja", "state": "FCT", "capacity": 2000,
                                                  "map_url": "https://maps.google.com/?q=International+Conference+Centre+Abuja"})[0],
            Venue.objects.get_or_create(organizer=org, name="Landmark Event Centre",
                                        defaults={"address": "Plot 2&3 Water Corporation Road, Victoria Island",
                                                  "city": "Lagos", "state": "Lagos", "capacity": 1500})[0],
            Venue.objects.get_or_create(organizer=org, name="Engineering Faculty Hall",
                                        defaults={"address": "University of Maiduguri", "city": "Maiduguri",
                                                  "state": "Borno", "capacity": 120})[0],
        ]

        speakers = []
        for name, title, company, bio in SPEAKERS:
            speakers.append(Speaker.objects.get_or_create(organizer=org, name=name,
                                                          defaults={"title": title, "company": company, "bio": bio})[0])

        now = timezone.localtime().replace(minute=0, second=0, microsecond=0)
        for i, spec in enumerate(EVENTS):
            starts = (now + timedelta(days=spec["days"])).replace(hour=spec["hours"])
            event, created = Event.objects.get_or_create(
                title=spec["title"],
                defaults={
                    "organizer": org, "category": cats[spec["cat"]], "summary": spec["summary"],
                    "description": spec["summary"] + "\n\nJoin practitioners from across the country for a focused, "
                    "practical programme. Doors open 30 minutes before the start time. Bring a valid QR ticket "
                    "(on your phone is fine) and a photo ID.\n\nRefunds are available up to 48 hours before the event.",
                    "starts_at": starts, "ends_at": starts + timedelta(hours=spec["length"]),
                    "venue": None if spec.get("online") else venues[i % len(venues)],
                    "is_online": bool(spec.get("online")),
                    "online_url": "https://meet.example.com/remote-work" if spec.get("online") else "",
                    "is_featured": spec.get("featured", False),
                    "contact_email": "hello@example.com",
                },
            )
            if not created:
                continue
            for pos, (name, price, qty) in enumerate(spec["tickets"]):
                TicketType.objects.create(event=event, name=name, price=Decimal(price), quantity=qty, position=pos,
                                          max_per_order=10 if price else 2,
                                          sales_end=starts - timedelta(days=7) if name == "Early Bird" else None)
            if spec["length"] >= 3:
                t = starts
                agenda = [("Registration & coffee", "networking", 30, "Lobby"),
                          ("Opening keynote", "keynote", 45, "Main Hall"),
                          ("Panel: building for the next billion", "panel", 60, "Main Hall"),
                          ("Hands-on workshop", "workshop", 90, "Room B"),
                          ("Lunch", "break", 60, "Lobby"),
                          ("Lightning talks", "talk", 45, "Main Hall")]
                for title, kind, mins, room in agenda:
                    if t + timedelta(minutes=mins) > event.ends_at:
                        break
                    s = Session.objects.create(event=event, title=title, kind=kind, starts_at=t,
                                               ends_at=t + timedelta(minutes=mins), room=room)
                    if kind in ("keynote", "panel", "workshop", "talk"):
                        s.speakers.set(random.sample(speakers, 1 if kind != "panel" else 3))
                    t += timedelta(minutes=mins)
                event.speakers.set({sp for ss in event.sessions.all() for sp in ss.speakers.all()})
            DiscountCode.objects.create(event=event, code="WELCOME10", kind="percent", value=Decimal("10"), max_uses=100)
            event.publish()

            # a handful of paid orders so dashboards have numbers
            paid_types = [tt for tt in event.ticket_types.all()]
            for n in range(random.randint(4, 9)):
                tt = random.choice(paid_types)
                buyer = att if n == 0 else None
                order = create_order(
                    event=event, selections={tt.id: random.randint(1, 2)},
                    buyer_name=buyer.get_full_name() if buyer else f"Guest {n}",
                    buyer_email=buyer.email if buyer else f"guest{n}.{event.pk}@example.com",
                    user=buyer,
                )
                if order.total:
                    Payment.objects.create(order=order, reference=f"{order.reference}-1", amount=order.total,
                                           status=Payment.Status.SUCCESS, channel=random.choice(["card", "bank_transfer", "ussd"]),
                                           paid_at=timezone.now())
                fulfill_order(order)
                back = timezone.now() - timedelta(days=random.randint(0, 20), hours=random.randint(0, 12))
                type(order).objects.filter(pk=order.pk).update(paid_at=back, created_at=back)

        self.stdout.write(self.style.SUCCESS(
            "Demo data ready.\n"
            "  Organizer: organizer@example.com / demo12345\n"
            "  Attendee:  attendee@example.com / demo12345\n"
            "  Admin:     admin@example.com / admin12345 (if created)"
        ))

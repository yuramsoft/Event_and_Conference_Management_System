from django.conf import settings
from django.db import models
from django.db.models import Min, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True)
    icon = models.CharField(max_length=40, default="calendar-event", help_text="Bootstrap Icons name")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class EventQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Event.Status.PUBLISHED)

    def upcoming(self):
        return self.filter(ends_at__gte=timezone.now())

    def visible(self):
        return self.published().upcoming()

    def search(self, term):
        if not term:
            return self
        return self.filter(
            Q(title__icontains=term) | Q(summary__icontains=term) | Q(venue__city__icontains=term)
        )

    def with_min_price(self):
        return self.annotate(
            min_price=Min("ticket_types__price", filter=Q(ticket_types__is_active=True))
        ).order_by("-is_featured", "starts_at")


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CANCELLED = "cancelled", "Cancelled"

    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    summary = models.CharField(max_length=300, help_text="Short teaser shown on cards")
    description = models.TextField()
    banner = models.ImageField(upload_to="events/banners/", blank=True)
    venue = models.ForeignKey(
        "venues.Venue", null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )
    is_online = models.BooleanField(default=False)
    online_url = models.URLField(blank=True, help_text="Shared with paid attendees only")
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(
        null=True, blank=True, help_text="Optional overall cap across all ticket types"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_featured = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    contact_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200] or "event"
            slug, n = base, 2
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("core:event_detail", args=[self.slug])

    # ---- state helpers
    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    @property
    def is_past(self):
        return self.ends_at < timezone.now()

    @property
    def is_on_sale(self):
        return self.is_published and not self.is_past

    def publish(self):
        self.status = self.Status.PUBLISHED
        self.published_at = self.published_at or timezone.now()
        self.save(update_fields=["status", "published_at", "updated_at"])

    def unpublish(self):
        self.status = self.Status.DRAFT
        self.save(update_fields=["status", "updated_at"])

    def publish_problems(self):
        """Reasons an event can't go live yet (shown in the organizer UI)."""
        problems = []
        if not self.ticket_types.filter(is_active=True).exists():
            problems.append("Add at least one active ticket type.")
        if not self.is_online and not self.venue_id:
            problems.append("Choose a venue or mark the event as online.")
        if self.ends_at <= self.starts_at:
            problems.append("End time must be after start time.")
        return problems

    @property
    def tickets_sold(self):
        return sum(t.sold for t in self.ticket_types.all())

    @property
    def total_capacity(self):
        if self.capacity:
            return self.capacity
        return sum(t.quantity for t in self.ticket_types.all())

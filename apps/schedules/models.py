from django.core.exceptions import ValidationError
from django.db import models


class Session(models.Model):
    class Kind(models.TextChoices):
        TALK = "talk", "Talk"
        KEYNOTE = "keynote", "Keynote"
        PANEL = "panel", "Panel"
        WORKSHOP = "workshop", "Workshop"
        BREAK = "break", "Break"
        NETWORKING = "networking", "Networking"

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="sessions")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.TALK)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    room = models.CharField(max_length=100, blank=True, help_text="Hall, room or track")
    speakers = models.ManyToManyField("speakers.Speaker", blank=True, related_name="sessions")

    class Meta:
        ordering = ["starts_at", "room"]

    def __str__(self):
        return f"{self.title} ({self.starts_at:%H:%M})"

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "Session must end after it starts."})
        if self.event_id and self.starts_at and self.ends_at:
            if self.starts_at < self.event.starts_at or self.ends_at > self.event.ends_at:
                raise ValidationError("Session must fall within the event's start and end time.")

    @property
    def duration_minutes(self):
        return int((self.ends_at - self.starts_at).total_seconds() // 60)

from django import forms
from django.utils import timezone

from apps.accounts.forms import BootstrapMixin
from apps.discounts.models import DiscountCode
from apps.events.models import Event
from apps.schedules.models import Session
from apps.speakers.models import Speaker
from apps.tickets.models import TicketType
from apps.venues.models import Venue

DT = {"type": "datetime-local"}


class DateTimeLocal(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%dT%H:%M")


class StyledModelForm(BootstrapMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field, forms.DateTimeField):
                field.widget = DateTimeLocal()
                field.input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
        self._style()


class EventForm(StyledModelForm):
    class Meta:
        model = Event
        fields = ["title", "category", "summary", "description", "banner", "starts_at", "ends_at",
                  "is_online", "venue", "online_url", "capacity", "contact_email", "is_featured"]
        widgets = {"description": forms.Textarea(attrs={"rows": 8})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["venue"].queryset = Venue.objects.filter(organizer=user)
        if user and not user.is_superuser:
            self.fields.pop("is_featured")

    def clean(self):
        data = super().clean()
        s, e = data.get("starts_at"), data.get("ends_at")
        if s and e and e <= s:
            self.add_error("ends_at", "End must be after start.")
        if not data.get("is_online") and not data.get("venue"):
            self.add_error("venue", "Choose a venue, or mark the event as online.")
        if data.get("is_online") and not data.get("online_url"):
            self.add_error("online_url", "Online events need a joining link.")
        return data


class VenueForm(StyledModelForm):
    class Meta:
        model = Venue
        fields = ["name", "address", "city", "state", "country", "capacity", "map_url", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class SpeakerForm(StyledModelForm):
    class Meta:
        model = Speaker
        fields = ["name", "title", "company", "bio", "photo", "website", "linkedin", "x_handle", "events"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 4}), "events": forms.CheckboxSelectMultiple}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["events"].queryset = Event.objects.filter(organizer=user)
        self.fields["events"].widget.attrs["class"] = "form-check-input"


class TicketTypeForm(StyledModelForm):
    class Meta:
        model = TicketType
        fields = ["name", "description", "price", "quantity", "sales_start", "sales_end",
                  "min_per_order", "max_per_order", "position", "is_active"]


class SessionForm(StyledModelForm):
    class Meta:
        model = Session
        fields = ["title", "kind", "starts_at", "ends_at", "room", "speakers", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "speakers": forms.CheckboxSelectMultiple}

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event
        self.fields["speakers"].queryset = Speaker.objects.filter(organizer=event.organizer)
        self.fields["speakers"].widget.attrs["class"] = "form-check-input"
        if not self.instance.pk and event:
            self.initial.setdefault("starts_at", timezone.localtime(event.starts_at))


class DiscountCodeForm(StyledModelForm):
    class Meta:
        model = DiscountCode
        fields = ["code", "kind", "value", "max_uses", "valid_from", "valid_until", "ticket_types", "is_active"]
        widgets = {"ticket_types": forms.CheckboxSelectMultiple}

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.instance.event = event
        self.fields["ticket_types"].queryset = event.ticket_types.all()
        self.fields["ticket_types"].widget.attrs["class"] = "form-check-input"

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        clash = DiscountCode.objects.filter(event=self.event, code=code).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("This event already has that code.")
        return code

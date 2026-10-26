from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.audit.services import log_action
from apps.registrations.models import Order

from .forms import LoginForm, ProfileForm, SignupForm


def _claim_session_orders(request, user):
    """Attach orders placed before logging in (same browser) to the account."""
    refs = request.session.get("orders", [])
    if refs:
        Order.objects.filter(reference__in=refs, user__isnull=True).update(user=user)


def signup(request):
    if request.user.is_authenticated:
        return redirect("accounts:after_login")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        refs = request.session.get("orders", [])
        login(request, user)
        request.session["orders"] = refs
        _claim_session_orders(request, user)
        log_action("account.signup", user, actor=user)
        messages.success(request, f"Welcome to EventHandler, {user.display_name}!")
        return redirect("accounts:after_login")
    return render(request, "accounts/signup.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        refs = self.request.session.get("orders", [])
        response = super().form_valid(form)
        self.request.session["orders"] = refs
        _claim_session_orders(self.request, form.get_user())
        return response


@login_required
def after_login(request):
    nxt = request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("organizer:dashboard" if request.user.is_organizer else "attendee:dashboard")


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    pw_form = PasswordChangeForm(request.user, request.POST if "change_password" in request.POST else None)
    for f in pw_form.fields.values():
        f.widget.attrs["class"] = "form-control"
    if request.method == "POST":
        if "change_password" in request.POST:
            if pw_form.is_valid():
                user = pw_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated.")
                return redirect("accounts:profile")
        elif form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
            return redirect("accounts:profile")
    base = "organizer/base.html" if request.user.is_organizer else "attendee/base.html"
    return render(request, "accounts/profile.html", {"form": form, "pw_form": pw_form, "base_template": base})

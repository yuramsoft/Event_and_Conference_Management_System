"""Settings for the test suite: SQLite, eager Celery, in-memory email, fake Paystack key."""
import os

os.environ["DB_ENGINE"] = "sqlite"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "1"
os.environ["DJANGO_DEBUG"] = "1"

from .settings import *  # noqa: E402,F401,F403

DATABASES["default"]["NAME"] = ":memory:"  # noqa: F405
PAYSTACK_SECRET_KEY = "sk_test_dummy"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405
LOGGING = {"version": 1, "disable_existing_loggers": True, "root": {"level": "CRITICAL"}}

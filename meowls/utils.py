# meowls/utils.py
from django.utils import timezone
from django.db.models import Sum
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.timezone import now
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator

from .models import PointsLedger, UserStatus


def leaderboard(period: str = "all"):
    qs = PointsLedger.objects.all()
    now = timezone.now()
    if period == "30d":
        qs = qs.filter(created_at__gte=now - timezone.timedelta(days=30))
    elif period == "7d":
        qs = qs.filter(created_at__gte=now - timezone.timedelta(days=7))

    return (qs.values("user__username")
              .annotate(total=Sum("points"))
              .order_by("-total"))


def send_email_verification(request, user):
    """
    Send a verification email to the given user with a signed token link.
    """
    st, _ = UserStatus.objects.get_or_create(user=user)

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse("meowls:verify_email", args=[uidb64, token])
    )

    subject = "Confirm your email for Meowl"
    body = (
        f"Hi {user.username},\n\n"
        f"Please confirm your email by clicking the link below:\n{verify_url}\n\n"
        f"If you didn’t sign up, you can ignore this email."
    )

    send_mail(
        subject,
        body,
        getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        [user.email],
        fail_silently=False,
    )

    st.email_verification_sent_at = now()
    st.save(update_fields=["email_verification_sent_at"])

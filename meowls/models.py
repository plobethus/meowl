from django.db import models
from django.contrib.auth.models import User
from django.conf import settings


class Meowl(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, default="")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="meowls_owned")

    # Archival
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="meowls_archived"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def current_location(self) -> "MeowlLocation | None":
        return (
            self.locations.filter(status="current")
            .order_by("-verified_at", "-id")
            .first()
        )

    @property
    def lat(self):
        loc = self.current_location
        return loc.lat if loc else None

    @property
    def lng(self):
        loc = self.current_location
        return loc.lng if loc else None


class MeowlLocation(models.Model):
    STATUS_CHOICES = (
        ("proposed", "Proposed"),
        ("verified", "Verified"),
        ("current", "Current"),
        ("rejected", "Rejected"),
    )

    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE, related_name="locations")
    lat = models.FloatField()
    lng = models.FloatField()
    address = models.CharField(max_length=255, blank=True, default="")

    proposer = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="proposed_locations")
    verifier = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_locations")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="proposed")
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-verified_at", "-id"]

    def __str__(self) -> str:
        return f"{self.meowl.slug} @ ({self.lat:.5f}, {self.lng:.5f}) [{self.status}]"


class LocationVerification(models.Model):
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE, null=True, blank=True)  # <-- nullable
    verifier = models.ForeignKey(User, on_delete=models.CASCADE)
    lat = models.FloatField(null=True, blank=True)   # <-- nullable
    lng = models.FloatField(null=True, blank=True)   # <-- nullable
    created_at = models.DateTimeField(auto_now_add=True)


class Scan(models.Model):
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    user_agent = models.TextField(blank=True, default="")
    ip_hash = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Comment(models.Model):
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()

    # Soft-hide, not delete
    is_hidden = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="comments_hidden")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"#{self.id} by {self.user.username} on {self.meowl.slug}"


class PointsLedger(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    meowl = models.ForeignKey(Meowl, null=True, blank=True, on_delete=models.SET_NULL)
    points = models.IntegerField(default=0)
    reason = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AuditLog(models.Model):
    ACTION_CHOICES = (
        ("comment_hide", "Hide Comment"),
        ("comment_unhide", "Unhide Comment"),
        ("meowl_archive", "Archive Meowl"),
        ("meowl_unarchive", "Unarchive Meowl"),
        ("user_promote", "Promote User"),
        ("user_demote", "Demote User"),
        ("user_suspend", "Suspend User"),      # NEW
        ("user_unsuspend", "Unsuspend User"),  # NEW
        ("scan", "Scan"),
        ("create", "Create"),
        ("verify", "Verify"),
    )

    actor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_actor"
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    meowl = models.ForeignKey(Meowl, null=True, blank=True, on_delete=models.SET_NULL)  # <-- nullable
    target_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_target"
    )  # <-- fixed: removed stray line
    comment_id = models.IntegerField(null=True, blank=True)
    detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        who = self.actor.username if self.actor else "system"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {who} {self.action}"



# meowls/models.py
class UserStatus(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="status", on_delete=models.CASCADE)
    is_suspended = models.BooleanField(default=False)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspended_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="suspended_users", on_delete=models.SET_NULL)
    reason = models.CharField(max_length=200, blank=True)

    # NEW: email verification flags
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"UserStatus<{self.user_id}>"

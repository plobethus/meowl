from django.db import models
from django.contrib.auth.models import User


class Meowl(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="meowls_owned")
    slug = models.SlugField(max_length=60, unique=True)
    status = models.CharField(max_length=20, default="active")
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="meowls_archived"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    # Your app calls this; keep its behavior the same as before.
    def current_location(self):
        return (
            self.locations.filter(status="current")
            .order_by("-verified_at", "-id")
            .first()
        )


class MeowlLocation(models.Model):
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE, related_name="locations")
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, default="current")
    proposer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="proposed_locations")
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class LocationVerification(models.Model):
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE)
    verifier = models.ForeignKey(User, on_delete=models.CASCADE)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)


class Scan(models.Model):
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    user_agent = models.CharField(max_length=255, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Comment(models.Model):
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    is_hidden = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="comments_hidden"
    )
    hidden_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PointsLedger(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE, null=True, blank=True)
    points = models.IntegerField()
    reason = models.CharField(max_length=32)
    ref_scan = models.ForeignKey(Scan, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


# -------------------------
# New: Audit log
# -------------------------
class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("meowl.create", "Meowl created"),
        ("meowl.archive", "Meowl archived"),
        ("meowl.unarchive", "Meowl unarchived"),
        ("comment.create", "Comment created"),
        ("comment.hide", "Comment hidden"),
        ("comment.unhide", "Comment unhidden"),
        ("user.promote", "User promoted to staff"),
        ("user.demote", "User demoted from staff"),
    ]

    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_actions")
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_targets")
    meowl = models.ForeignKey(Meowl, null=True, blank=True, on_delete=models.SET_NULL)
    comment = models.ForeignKey(Comment, null=True, blank=True, on_delete=models.SET_NULL)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        bits = [self.action]
        if self.meowl:
            bits.append(f"meowl={self.meowl.slug}")
        if self.comment_id:
            bits.append(f"comment={self.comment_id}")
        if self.target_user:
            bits.append(f"target_user={self.target_user.username}")
        return " ".join(bits)

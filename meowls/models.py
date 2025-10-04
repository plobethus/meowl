from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

User = get_user_model()

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    is_suspended = models.BooleanField(default=False)
    suspend_reason = models.CharField(max_length=255, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)

class Meowl(models.Model):
    STATUS = [("hidden","Hidden"),("active","Active"),("archived","Archived")]
    slug = models.SlugField(max_length=64, unique=True, blank=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS, default="hidden")
    created_at = models.DateTimeField(auto_now_add=True)

    # Soft archive
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="archived_meowls")
    archived_reason = models.CharField(max_length=255, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "meowl"
            cand, i = base, 2
            while Meowl.objects.filter(slug=cand).exclude(pk=self.pk).exists():
                cand = f"{base}-{i}"; i += 1
            self.slug = cand
        super().save(*args, **kwargs)

    def current_location(self):
        return self.locations.filter(status="current").order_by("-verified_at","-created_at").first()

    def __str__(self): return self.name

class MeowlLocation(models.Model):
    STATUS = [("current","Current"),("pending","Pending"),("hidden","Hidden")]
    meowl = models.ForeignKey(Meowl, related_name="locations", on_delete=models.CASCADE)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="hidden")
    proposer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="proposed_locations")
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

class LocationVerification(models.Model):
    location = models.ForeignKey(MeowlLocation, related_name="verifications", on_delete=models.CASCADE)
    verifier = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = [("location","verifier")]

class Scan(models.Model):
    meowl = models.ForeignKey(Meowl, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Comment(models.Model):
    meowl = models.ForeignKey(Meowl, related_name="comments", on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="hidden_comments")
    hidden_reason = models.CharField(max_length=255, blank=True)

class PointsLedger(models.Model):
    REASON=[("scan","Scan"),("verify","Verify"),("create","Create"),("other","Other")]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    meowl = models.ForeignKey(Meowl, on_delete=models.SET_NULL, null=True, blank=True)
    points = models.IntegerField()
    reason = models.CharField(max_length=10, choices=REASON)
    ref_scan = models.ForeignKey(Scan, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class MeowlUpdate(models.Model):
    UPDATE_TYPES = [
        ("create","Created"),
        ("edit","Edited"),
        ("location_proposed","Location Proposed"),
        ("location_verified","Location Verified"),
        ("comment_hidden","Comment Hidden"),
        ("meowl_archived","Meowl Archived"),
        ("meowl_unarchived","Meowl Unarchived"),
        ("user_suspended","User Suspended"),
        ("user_unsuspended","User Unsuspended"),
    ]
    meowl = models.ForeignKey(Meowl, related_name="updates", on_delete=models.CASCADE, null=True, blank=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    update_type = models.CharField(max_length=32, choices=UPDATE_TYPES)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    meta_json = models.JSONField(default=dict, blank=True)
    class Meta: ordering = ["-created_at"]

class AuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    meta_json = models.JSONField(default=dict, blank=True)

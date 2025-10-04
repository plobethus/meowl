from django.contrib import admin
from .models import (
    Meowl,
    MeowlLocation,
    LocationVerification,
    Scan,
    Comment,
    PointsLedger,
    AuditLog,
)

@admin.register(Meowl)
class MeowlAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "owner", "is_archived", "created_at")
    list_filter = ("is_archived",)
    search_fields = ("name", "slug", "owner__username")

@admin.register(MeowlLocation)
class MeowlLocationAdmin(admin.ModelAdmin):
    list_display = ("id", "meowl", "lat", "lng", "status", "proposer", "verified_at")
    list_filter = ("status",)
    search_fields = ("meowl__name", "meowl__slug", "proposer__username")

@admin.register(LocationVerification)
class LocationVerificationAdmin(admin.ModelAdmin):
    list_display = ("id", "meowl", "verifier", "lat", "lng", "created_at")
    search_fields = ("meowl__name", "meowl__slug", "verifier__username")

@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("id", "meowl", "user", "created_at")
    search_fields = ("meowl__name", "meowl__slug", "user__username")
    readonly_fields = ("user_agent", "ip_hash")

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "meowl", "user", "is_hidden", "created_at")
    list_filter = ("is_hidden",)
    search_fields = ("meowl__name", "meowl__slug", "user__username", "text")

@admin.register(PointsLedger)
class PointsLedgerAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "meowl", "points", "reason", "created_at")
    list_filter = ("reason",)
    search_fields = ("user__username", "meowl__name", "meowl__slug")

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "actor", "action", "target_user", "meowl", "comment_id")
    list_filter = ("action",)
    search_fields = ("actor__username", "target_user__username", "meowl__slug")
    readonly_fields = ("created_at",)

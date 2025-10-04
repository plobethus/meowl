from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Meowl, MeowlLocation, LocationVerification, Scan, Comment,
    PointsLedger, MeowlUpdate, Profile, AuditLog
)

@admin.register(Meowl)
class MeowlAdmin(admin.ModelAdmin):
    list_display=("id","name","slug","owner","status","is_archived","archived_by","archived_reason","created_at")
    search_fields=("name","slug","description","archived_reason")
    list_filter=("status","is_archived")

@admin.register(MeowlLocation)
class MeowlLocationAdmin(admin.ModelAdmin):
    list_display=("id","meowl","status","lat","lng","proposer","verification_count","verified_at","created_at")
    list_filter=("status",)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display=("id","meowl","user","short_text","is_hidden","hidden_by","hidden_reason","created_at")
    list_filter=("is_hidden",)
    search_fields=("text","hidden_reason")
    def short_text(self,obj): return (obj.text[:60] + "…") if len(obj.text)>60 else obj.text

admin.site.register(LocationVerification)
admin.site.register(Scan)
admin.site.register(PointsLedger)
admin.site.register(MeowlUpdate)
admin.site.register(Profile)
admin.site.register(AuditLog)

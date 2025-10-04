from django.urls import path
from . import views

app_name = "meowls"

urlpatterns = [
    path("", views.meowl_index, name="index"),
    path("create/", views.meowl_create, name="create"),

    path("<slug:slug>/", views.meowl_detail, name="detail"),
    path("<slug:slug>/scan/", views.scan_meowl, name="scan"),
    path("<slug:slug>/verify/", views.verify_location, name="verify"),

    # PDF: staff-only (no public links)
    path("<slug:slug>/pdf/preview/", views.pdf_preview, name="pdf_preview"),
    path("<slug:slug>/pdf/download/", views.pdf_download, name="pdf_download"),

    # Comments
    path("comments/<int:pk>/hide/", views.hide_comment, name="hide_comment"),

    # Leaderboard
    path("leaderboard/", views.leaderboard, name="leaderboard"),

    # Staff dashboard
    path("admin-dashboard/", views.staff_dashboard, name="staff_dashboard"),
    path("admin-dashboard/<slug:slug>/archive/", views.archive_meowl, name="archive_meowl"),
    path("admin-dashboard/<slug:slug>/unarchive/", views.unarchive_meowl, name="unarchive_meowl"),
]

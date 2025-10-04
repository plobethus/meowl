from django.urls import path
from . import views

app_name = "meowls"

urlpatterns = [
    path("", views.meowl_index, name="index"),
    path("create/", views.meowl_create, name="create"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),

    # QR-gated detail
    path("<slug:slug>/", views.meowl_detail, name="detail"),
    path("<slug:slug>/scan/", views.scan_meowl, name="scan"),

    # PDF
    path("<slug:slug>/pdf/preview/", views.pdf_preview, name="pdf_preview"),
    path("<slug:slug>/pdf/download/", views.pdf_download, name="pdf_download"),

    # Staff tools
    path("admin/", views.staff_dashboard, name="staff_dashboard"),
    path("admin/meowl/<slug:slug>/archive/", views.archive_meowl, name="archive_meowl"),
    path("admin/meowl/<slug:slug>/unarchive/", views.unarchive_meowl, name="unarchive_meowl"),
    path("admin/comment/<int:pk>/hide/", views.hide_comment, name="hide_comment"),
    path("admin/comment/<int:pk>/unhide/", views.unhide_comment, name="unhide_comment"),
    path("admin/user/<int:user_id>/promote/", views.promote_user, name="promote_user"),
    path("admin/user/<int:user_id>/demote/", views.demote_user, name="demote_user"),

    # Signup (public)
    path("signup/", views.signup, name="signup"),
]

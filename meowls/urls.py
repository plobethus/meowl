from django.urls import path
from . import views

app_name = "meowls"

urlpatterns = [
    # Index & creation
    path("", views.meowl_index, name="index"),
    path("create/", views.meowl_create, name="create"),

    # Auth helpers
    path("signup/", views.signup, name="signup"),
    path("logout/", views.logout_view, name="logout"),  # <-- BEFORE slug

    # Leaderboard
    path("leaderboard/", views.leaderboard, name="leaderboard"),

    # PDF
    path("<slug:slug>/pdf/preview/", views.meowl_pdf_preview, name="pdf_preview"),
    path("<slug:slug>/pdf/download/", views.meowl_pdf_download, name="pdf_download"),
    path("<slug:slug>/pdf/", views.meowl_pdf, name="pdf"),

    # Actions tied to a specific Meowl
    path("<slug:slug>/scan/", views.scan_meowl, name="scan"),
    path("<slug:slug>/comment/", views.post_comment, name="comment"),
    path("<slug:slug>/propose-location/", views.propose_location, name="propose_location"),
    path("<slug:slug>/verify/", views.verify_location, name="verify_location"),
    path("<slug:slug>/archive/", views.archive_meowl, name="archive_meowl"),
    path("<slug:slug>/unarchive/", views.unarchive_meowl, name="unarchive_meowl"),
    path("comment/<int:comment_id>/hide/", views.hide_comment, name="hide_comment"),

    # Catch-all slug LAST
    path("<slug:slug>/", views.meowl_detail, name="detail"),
]

from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count
from django.http import Http404, HttpResponseForbidden, FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Meowl, Comment, ScanEvent, LocationUpdate  # adjust names if needed
from .forms import CommentForm  # make sure you have a simple form with a "body" field
from .pdf import render_meowl_pdf  # existing helper that returns a BytesIO/bytes
from .utils import geocode_if_needed  # if you had helper; otherwise inline

# ---------- helpers

def staff_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view)

def can_view_pdf(user):
    return user.is_authenticated and user.is_staff  # tighten here if you want creator allowed too

def _meowl_qs():
    # Only show non-archived in public views
    return Meowl.objects.filter(archived=False)

# ---------- index / create

def meowl_index(request):
    qs = _meowl_qs().order_by("-created_at")  # created_at field assumed
    return render(request, "meowls/index.html", {"meowls": qs})

@login_required
def meowl_create(request):
    # if you already have a working create view, keep it.
    # placeholder link from navbar should go to your existing create flow.
    return render(request, "meowls/create.html")
    # wire your create POST here if needed

# ---------- detail + comments + location panel

def meowl_detail(request, slug):
    meowl = get_object_or_404(_meowl_qs(), slug=slug)

    # POST => new comment
    if request.method == "POST":
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Login required")
        form = CommentForm(request.POST)
        if form.is_valid():
            Comment.objects.create(
                meowl=meowl,
                author=request.user,
                body=form.cleaned_data["body"],
            )
            messages.success(request, "Comment added.")
            return redirect("meowls:detail", slug=meowl.slug)
    else:
        form = CommentForm()

    comments = (
        Comment.objects.filter(meowl=meowl, hidden=False)
        .select_related("author")
        .order_by("-created_at")
    )

    # location + status panel
    pending_move = (
        LocationUpdate.objects.filter(meowl=meowl, confirmed=False)
        .order_by("-created_at")
        .first()
    )
    context = {
        "meowl": meowl,
        "comments": comments,
        "form": form,
        "pending_move": pending_move,
    }
    return render(request, "meowls/detail.html", context)

# ---------- scans / verification / points

@login_required
def scan_meowl(request, slug):
    meowl = get_object_or_404(_meowl_qs(), slug=slug)
    # award points for scan (de-dupe if you like)
    ScanEvent.objects.create(meowl=meowl, user=request.user, kind="scan", points=5)
    messages.success(request, "Scan recorded. +5 pts!")
    return redirect("meowls:detail", slug=meowl.slug)

@login_required
def verify_location(request, slug):
    meowl = get_object_or_404(_meowl_qs(), slug=slug)
    # user is confirming last pending move
    update = (
        LocationUpdate.objects.filter(meowl=meowl, confirmed=False)
        .order_by("-created_at")
        .first()
    )
    if not update:
        messages.info(request, "No pending location to verify.")
        return redirect("meowls:detail", slug=meowl.slug)

    # record a verification
    ScanEvent.objects.create(meowl=meowl, user=request.user, kind="verify", points=10)

    # if two distinct verifiers (not the mover), mark confirmed & apply
    distinct_verifiers = (
        ScanEvent.objects.filter(meowl=meowl, kind="verify", created_at__gte=update.created_at)
        .values("user_id")
        .distinct()
        .count()
    )
    if distinct_verifiers >= 2:
        meowl.lat = update.lat
        meowl.lng = update.lng
        meowl.save(update_fields=["lat", "lng"])
        update.confirmed = True
        update.confirmed_at = timezone.now()
        update.save(update_fields=["confirmed", "confirmed_at"])
        messages.success(request, "Location verified and updated on the map.")
    else:
        messages.info(request, "Thanks! Another user must verify before it goes live.")
    return redirect("meowls:detail", slug=meowl.slug)

# ---------- PDF (staff-only)

@staff_required
def pdf_preview(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)  # allow viewing even if archived for admin
    # Show a template that renders a preview image and a "Download" button hitting pdf_download
    return render(request, "meowls/pdf_preview.html", {"meowl": meowl})

@staff_required
def pdf_download(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    pdf_bytes = render_meowl_pdf(request, meowl)  # your existing helper should embed the fixed header image + QR
    return FileResponse(
        pdf_bytes, as_attachment=True, filename=f"{meowl.slug}.pdf", content_type="application/pdf"
    )

# ---------- moderation

@staff_required
def staff_dashboard(request):
    meowls = Meowl.objects.all().order_by("-created_at")
    # pending comments count
    comments_by_meowl = (
        Comment.objects.values("meowl_id").annotate(c=Count("id"))
    )
    counts = {row["meowl_id"]: row["c"] for row in comments_by_meowl}
    return render(request, "meowls/admin_dashboard.html", {"meowls": meowls, "counts": counts})

@staff_required
def archive_meowl(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    meowl.archived = True
    meowl.archived_at = timezone.now()
    meowl.archived_by = request.user
    meowl.save(update_fields=["archived", "archived_at", "archived_by"])
    messages.success(request, f"Archived {meowl.name}.")
    return redirect("meowls:staff_dashboard")

@staff_required
def unarchive_meowl(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    meowl.archived = False
    meowl.save(update_fields=["archived"])
    messages.success(request, f"Unarchived {meowl.name}.")
    return redirect("meowls:staff_dashboard")

@staff_required
def hide_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    reason = request.POST.get("reason", "").strip()[:200]
    comment.hidden = True
    comment.hidden_at = timezone.now()
    comment.hidden_by = request.user
    comment.hidden_reason = reason
    comment.save(update_fields=["hidden", "hidden_at", "hidden_by", "hidden_reason"])
    messages.success(request, "Comment hidden.")
    return redirect("meowls:detail", slug=comment.meowl.slug)

# ---------- leaderboard

def leaderboard(request):
    leaderboard_rows = (
        ScanEvent.objects.values("user__username")
        .annotate(points=Sum("points"))
        .order_by("-points")[:50]
    )
    return render(request, "meowls/leaderboard.html", {"rows": leaderboard_rows})

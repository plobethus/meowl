from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count
from django.http import (
    Http404,
    HttpResponseForbidden,
    FileResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .forms import CommentForm, SignupForm, ReasonForm
from .models import (
    Meowl,
    Comment,
    Scan,
    MeowlLocation,
    LocationVerification,
    PointsLedger,
)
from .pdf import build_meowl_pdf
from .utils import leaderboard as leaderboard_qs
from .tokens import check_qr_token


# ---------- helpers

def _meowl_qs():
    return Meowl.objects.filter(is_archived=False)

def _attach_latlng(obj):
    try:
        loc = obj.current_location()
    except Exception:
        loc = None
    if loc:
        obj.lat = loc.lat
        obj.lng = loc.lng
        obj.address = loc.address
    else:
        obj.lat = None
        obj.lng = None
        obj.address = ""
    obj.archived = bool(getattr(obj, "is_archived", False))
    return obj

def _hash_ip(ip: str) -> str:
    import hashlib
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


# ---------- public views

def meowl_index(request):
    meowls = list(_meowl_qs().order_by("name"))
    for m in meowls:
        _attach_latlng(m)
    return render(request, "meowls/index.html", {"meowls": meowls})

def meowl_detail(request, slug):
    """
    Detail/comments require a valid QR token (non-staff).
    """
    meowl = get_object_or_404(Meowl, slug=slug)
    _attach_latlng(meowl)

    if not request.user.is_staff:
        token = request.GET.get("t", "")
        valid_slug = check_qr_token(token) if token else None
        if valid_slug != slug:
            messages.error(
                request,
                "This page is only accessible by scanning the Meowl’s QR code."
            )
            return redirect("meowls:index")

    if request.method == "POST":
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Log in to comment.")
        form = CommentForm(request.POST)
        if form.is_valid():
            Comment.objects.create(
                meowl=meowl,
                user=request.user,
                text=form.cleaned_data["text"],
            )
            messages.success(request, "Comment posted.")
            return redirect("meowls:detail", slug=meowl.slug)
    else:
        form = CommentForm()

    comments = (
        Comment.objects.filter(meowl=meowl, is_hidden=False)
        .select_related("user")
        .order_by("-created_at")
    )
    return render(
        request,
        "meowls/detail.html",
        {"meowl": meowl, "comments": comments, "form": form},
    )


@login_required
@require_POST
def scan_meowl(request, slug):
    """
    Record a scan and award points, but only once per user per Meowl per day.
    """
    meowl = get_object_or_404(Meowl, slug=slug, is_archived=False)

    today = timezone.localdate()
    already_scanned = Scan.objects.filter(
        user=request.user,
        meowl=meowl,
        created_at__date=today,
    ).exists()

    if already_scanned:
        messages.info(request, "You’ve already scanned this Meowl today. Try again tomorrow!")
        return redirect("meowls:detail", slug=meowl.slug)

    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", "")
    )

    scan = Scan.objects.create(
        meowl=meowl,
        user=request.user,
        user_agent=ua,
        ip_hash=_hash_ip(ip),
    )

    points_for_scan = getattr(settings, "POINTS_SCAN", 5)

    PointsLedger.objects.create(
        user=request.user,
        meowl=meowl,
        points=points_for_scan,
        reason="scan",
        ref_scan=scan,
    )
    messages.success(request, f"Scan recorded (+{points_for_scan}).")
    return redirect("meowls:detail", slug=meowl.slug)


# ---------- PDF (owner or staff)

def pdf_preview(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    is_owner = request.user.is_authenticated and request.user == meowl.owner
    if not (request.user.is_staff or is_owner):
        return HttpResponseForbidden("Only staff or the owner can view the PDF.")
    # Pass flags for nicer messaging in the template
    return render(request, "meowls/pdf_preview.html", {"meowl": meowl, "is_owner": is_owner})

@xframe_options_sameorigin  # allow embedding this PDF from our own site (base setting is DENY)
def pdf_download(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    if not (request.user.is_staff or request.user == meowl.owner):
        return HttpResponseForbidden("Only staff or the owner can download the PDF.")
    pdf_bytes = build_meowl_pdf(meowl)
    return FileResponse(
        BytesIO(pdf_bytes),
        as_attachment=False,
        filename=f"{meowl.slug}.pdf",
        content_type="application/pdf",
    )


# ---------- comments moderation (staff)

def _staff_check(user):
    return user.is_staff

@user_passes_test(_staff_check)
@require_POST
def hide_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    form = ReasonForm(request.POST)
    reason = form.data.get("reason", "").strip() if form.is_valid() else ""
    comment.is_hidden = True
    comment.hidden_at = timezone.now()
    comment.hidden_by = request.user
    comment.hidden_reason = reason[:255]
    comment.save(
        update_fields=["is_hidden", "hidden_at", "hidden_by", "hidden_reason"]
    )
    messages.success(request, "Comment hidden.")
    return redirect("meowls:detail", slug=comment.meowl.slug)


# ---------- leaderboard

def leaderboard(request):
    period = request.GET.get("period", "all")
    rows = (
        leaderboard_qs(period)
        .values("user__username")
        .annotate(points=Sum("points"))
        .order_by("-points")
    )
    return render(request, "meowls/leaderboard.html", {"rows": rows})


# ---------- staff dashboard & archive toggles

@user_passes_test(_staff_check)
def staff_dashboard(request):
    qs = Meowl.objects.all().order_by("name")
    meowls = []
    for m in qs:
        _attach_latlng(m)
        meowls.append(m)

    counts = (
        Comment.objects.values("meowl_id")
        .annotate(total=Count("id"))
    )
    counts_map = {row["meowl_id"]: row["total"] for row in counts}
    return render(
        request,
        "meowls/admin_dashboard.html",
        {"meowls": meowls, "counts": counts_map},
    )

@user_passes_test(_staff_check)
def archive_meowl(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    if not meowl.is_archived:
        meowl.is_archived = True
        meowl.archived_at = timezone.now()
        meowl.archived_by = request.user
        meowl.save(update_fields=["is_archived", "archived_at", "archived_by"])
        messages.success(request, f"Archived {meowl.name}.")
    return redirect("meowls:staff_dashboard")

@user_passes_test(_staff_check)
def unarchive_meowl(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    if meowl.is_archived:
        meowl.is_archived = False
        meowl.archived_at = None
        meowl.archived_by = None
        meowl.save(update_fields=["is_archived", "archived_at", "archived_by"])
        messages.success(request, f"Unarchived {meowl.name}.")
    return redirect("meowls:staff_dashboard")


# ---------- create meowl (simple)

@login_required
def meowl_create(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        lat = request.POST.get("lat")
        lng = request.POST.get("lng")

        if not name or not lat or not lng:
            messages.error(request, "Name and location are required.")
            return render(request, "meowls/create.html")

        m = Meowl.objects.create(
            name=name,
            description=description,
            owner=request.user,
            status="active",
        )
        from django.utils.text import slugify
        base = slugify(name)[:50] or "meowl"
        slug = base
        i = 2
        while Meowl.objects.filter(slug=slug).exists():
            slug = f"{base}-{i}"
            i += 1
        m.slug = slug
        m.save(update_fields=["slug"])

        MeowlLocation.objects.create(
            meowl=m,
            lat=lat,
            lng=lng,
            address="",
            status="current",
            proposer=request.user,
            verified_at=timezone.now(),
            verification_count=1,
        )

        PointsLedger.objects.create(
            user=request.user,
            meowl=m,
            points=getattr(settings, "POINTS_CREATE", 25),
            reason="create",
        )
        messages.success(request, "Meowl created (+25).")
        return redirect("meowls:pdf_preview", slug=m.slug)

    return render(request, "meowls/create.html")


# ---------- signup

def signup(request):
    if request.user.is_authenticated:
        return redirect("meowls:index")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome!")
            return redirect("meowls:index")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})

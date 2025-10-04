from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone

from .models import (
    Meowl, MeowlLocation, LocationVerification, Scan, Comment,
    PointsLedger, MeowlUpdate, Profile, AuditLog
)
from .forms import CommentForm, LocationProposalForm, SignupForm, ReasonForm
from .tokens import make_qr_token, check_qr_token
from .pdf import build_meowl_pdf
from .utils import leaderboard as _lb
import hashlib

User = get_user_model()

def is_admin(user): return user.is_superuser or user.is_staff

# ---------- auth ----------
def signup(request):
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

def logout_view(request):
    logout(request)
    messages.success(request, "Logged out.")
    return redirect("meowls:index")

# ---------- pages ----------
def meowl_index(request):
    meowls = Meowl.objects.filter(is_archived=False).order_by("-created_at")[:50]
    return render(request, "meowls/index.html", {"meowls": meowls})

@login_required
def meowl_create(request):
    if request.method == "POST":
        name = request.POST.get("name","").strip()
        description = request.POST.get("description","").strip()
        lat = request.POST.get("lat"); lng = request.POST.get("lng")
        if not (name and lat and lng):
            messages.error(request, "Name and initial location are required.")
            return redirect("meowls:create")
        meowl = Meowl.objects.create(name=name, description=description, owner=request.user, status="hidden")
        MeowlLocation.objects.create(meowl=meowl, lat=lat, lng=lng, proposer=request.user, status="hidden")
        MeowlUpdate.objects.create(meowl=meowl, actor=request.user, update_type="create", message="Meowl created")
        messages.success(request, "Meowl created.")
        return redirect("meowls:pdf_preview", slug=meowl.slug)
    return render(request, "meowls/create.html")

def meowl_detail(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)

    # QR-only access
    gate_key = f"qr_access_{slug}"
    if not request.session.get(gate_key):
        token = request.GET.get("t")
        if not token or check_qr_token(token) != slug:
            return HttpResponseForbidden("This page can only be opened by scanning its QR code.")
        request.session[gate_key] = True
        request.session.set_expiry(settings.QR_TOKEN_MINUTES * 60)

    current_loc = meowl.current_location()
    pending = meowl.locations.filter(status="pending").order_by("-created_at").first()

    if request.user.is_authenticated and is_admin(request.user):
        comments = meowl.comments.order_by("-created_at")[:100]
    else:
        comments = meowl.comments.filter(is_hidden=False).order_by("-created_at")[:100]

    return render(request, "meowls/detail.html", {
        "meowl": meowl,
        "current_loc": current_loc,
        "pending_loc": pending,
        "comment_form": CommentForm(),
        "proposal_form": LocationProposalForm(),
    })

# QR token bounce (optional)
def request_qr_token(request, slug):
    get_object_or_404(Meowl, slug=slug)
    token = make_qr_token(slug)
    url = reverse("meowls:detail", kwargs={"slug": slug}) + f"?t={token}"
    return redirect(url)

@login_required
@transaction.atomic
def scan_meowl(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    ua = request.META.get("HTTP_USER_AGENT","")
    ip = request.META.get("REMOTE_ADDR","0.0.0.0")
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()
    scan = Scan.objects.create(meowl=meowl, user=request.user, user_agent=ua, ip_hash=ip_hash)

    cutoff = timezone.now() - timezone.timedelta(hours=24)
    recent = Scan.objects.filter(meowl=meowl, user=request.user, created_at__gte=cutoff).exclude(id=scan.id).exists()
    if not recent:
        PointsLedger.objects.create(user=request.user, meowl=meowl, points=settings.POINTS_SCAN, reason="scan", ref_scan=scan)

    pending = meowl.locations.filter(status="pending").order_by("-created_at").first()
    if pending and pending.proposer_id != request.user.id:
        if not LocationVerification.objects.filter(location=pending, verifier=request.user).exists():
            LocationVerification.objects.create(location=pending, verifier=request.user)
            pending.verification_count = pending.verifications.count()
            if pending.verification_count >= 2:
                meowl.locations.filter(status="current").update(status="hidden")
                pending.status = "current"
                pending.verified_at = timezone.now()
                pending.save()
                meowl.status = "active"; meowl.save()
                MeowlUpdate.objects.create(meowl=meowl, actor=request.user, update_type="location_verified")
            else:
                pending.save()
            PointsLedger.objects.create(user=request.user, meowl=meowl, points=settings.POINTS_VERIFY, reason="verify")

    messages.success(request, "Scan recorded!")
    return redirect("meowls:detail", slug=meowl.slug)

@login_required
def post_comment(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.meowl = meowl
            c.user = request.user
            c.save()
            messages.success(request, "Comment posted.")
    return redirect("meowls:detail", slug=slug)

@login_required
def propose_location(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    if request.method == "POST":
        form = LocationProposalForm(request.POST)
        if form.is_valid():
            meowl.locations.filter(status="pending").update(status="hidden")
            loc = form.save(commit=False)
            loc.meowl = meowl
            loc.proposer = request.user
            loc.status = "pending"
            loc.verification_count = 0
            loc.save()
            MeowlUpdate.objects.create(meowl=meowl, actor=request.user, update_type="location_proposed")
            messages.success(request, "Location change proposed. It’ll go live after two verifications.")
    return redirect("meowls:detail", slug=slug)

@login_required
@transaction.atomic
def verify_location(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    pending = meowl.locations.filter(status="pending").order_by("-created_at").first()
    if not pending or pending.proposer_id == request.user.id:
        return redirect("meowls:detail", slug=slug)
    if not LocationVerification.objects.filter(location=pending, verifier=request.user).exists():
        LocationVerification.objects.create(location=pending, verifier=request.user)
        pending.verification_count = pending.verifications.count()
        if pending.verification_count >= 2:
            meowl.locations.filter(status="current").update(status="hidden")
            pending.status = "current"
            pending.verified_at = timezone.now()
            pending.save()
            meowl.status = "active"; meowl.save()
            MeowlUpdate.objects.create(meowl=meowl, actor=request.user, update_type="location_verified")
        else:
            pending.save()
        PointsLedger.objects.create(user=request.user, meowl=meowl, points=settings.POINTS_VERIFY, reason="verify")
    return redirect("meowls:detail", slug=slug)

# ----- PDF -----
def meowl_pdf(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    pdf = build_meowl_pdf(meowl)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{meowl.slug}.pdf"'
    return resp

def meowl_pdf_download(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    pdf = build_meowl_pdf(meowl)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{meowl.slug}.pdf"'
    return resp

def meowl_pdf_preview(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    return render(request, "meowls/pdf_preview.html", {"meowl": meowl})

# ----- leaderboard -----
def leaderboard(request):
    period = request.GET.get("period","all")
    data = _lb(period)
    return render(request, "meowls/leaderboard.html", {"rows": data, "period": period})

# ----- moderation -----
@login_required
@user_passes_test(is_admin)
def archive_meowl(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            meowl.is_archived = True
            meowl.archived_at = timezone.now()
            meowl.archived_by = request.user
            meowl.archived_reason = form.cleaned_data["reason"]
            meowl.save()
            MeowlUpdate.objects.create(meowl=meowl, actor=request.user, update_type="meowl_archived",
                                       message=meowl.archived_reason)
            messages.success(request, "Meowl archived.")
    return redirect("meowls:detail", slug=slug)

@login_required
@user_passes_test(is_admin)
def unarchive_meowl(request, slug):
    meowl = get_object_or_404(Meowl, slug=slug)
    meowl.is_archived = False
    meowl.archived_at = None
    meowl.archived_by = None
    meowl.archived_reason = ""
    meowl.save()
    MeowlUpdate.objects.create(meowl=meowl, actor=request.user, update_type="meowl_unarchived")
    messages.success(request, "Meowl unarchived.")
    return redirect("meowls:detail", slug=slug)

@login_required
@user_passes_test(is_admin)
def hide_comment(request, comment_id):
    c = get_object_or_404(Comment, id=comment_id)
    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            c.is_hidden = True
            c.hidden_at = timezone.now()
            c.hidden_by = request.user
            c.hidden_reason = form.cleaned_data["reason"]
            c.save()
            MeowlUpdate.objects.create(meowl=c.meowl, actor=request.user, update_type="comment_hidden",
                                       message=c.hidden_reason, meta_json={"comment_id": c.id})
            messages.success(request, "Comment hidden.")
    return redirect("meowls:detail", slug=c.meowl.slug)

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.db.models import Max
from django.utils.timezone import now, timedelta
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from .utils import send_email_verification
from django.conf import settings

from .forms import CommentForm, LocationProposalForm, ReasonForm, SignupForm
from .models import AuditLog, Comment, Meowl, MeowlLocation, PointsLedger, Scan, UserStatus
from .pdf import build_meowl_pdf
from .tokens import check_qr_token



User = get_user_model()

# -----------------------
# Public pages
# -----------------------


def meowl_index(request):
    meowls = (
        Meowl.objects
        .select_related("owner")
        .filter(is_archived=False)           # hide archived ones
        .annotate(last_scan=Max("scan__created_at"))  # add last scan timestamp
        .order_by("name")
    )
    return render(request, "meowls/index.html", {"meowls": meowls})




@login_required
def meowl_create(request):
    # Block suspended users
    if UserStatus.objects.filter(user=request.user, is_suspended=True).exists():
        messages.error(request, "Your account is suspended; you can’t create Meowls.")
        return redirect("meowls:index")
    # Require verified email?
    if not UserStatus.objects.filter(user=request.user, email_verified=True).exists():
        messages.error(request, "Verify your email to create Meowls.")
        return redirect("meowls:index")


    # Enforce daily limit
    today = now().date()
    daily_count = Meowl.objects.filter(
        owner=request.user,
        created_at__date=today
    ).count()
    if daily_count >= 3:
        messages.error(request, "You’ve reached the daily limit of 3 Meowls.")
        return redirect("meowls:index")

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        slug = name.lower().replace(" ", "-")
        description = request.POST.get("description", "")
        lat = request.POST.get("lat")
        lng = request.POST.get("lng")

        if not name or not lat or not lng:
            messages.error(request, "Name and a map location are required.")
            return redirect("meowls:create")

        m = Meowl.objects.create(
            name=name,
            slug=slug,
            description=description,
            owner=request.user,
        )
        MeowlLocation.objects.create(
            meowl=m,
            lat=float(lat),
            lng=float(lng),
            status="current",
            proposer=request.user,
            verifier=request.user,
            verified_at=now(),
        )
        PointsLedger.objects.create(user=request.user, meowl=m, points=10, reason="create")
        AuditLog.objects.create(actor=request.user, action="create", meowl=m, detail=f"Created {m.slug}")
        messages.success(request, "Meowl created. Generating printable poster…")
        return redirect("meowls:pdf_preview", slug=m.slug)

    return render(request, "meowls/create.html")



def meowl_detail(request, slug):
    m = get_object_or_404(Meowl.objects.select_related("owner"), slug=slug)

    token = request.GET.get("t")
    token_ok = (token and check_qr_token(token) == slug)

    # Allow staff/owner always; everyone else must have a valid QR token
    is_staff_or_owner = request.user.is_authenticated and (request.user.is_staff or request.user == m.owner)
    if not is_staff_or_owner and not token_ok:
        messages.error(request, "This page can only be opened by scanning the official QR code.")
        return redirect("meowls:index")

    # (leave the rest of your existing comment handling & context as-is)
    ...


    # --- AUTO SCAN (once per day) ---
    if request.method == "GET":
        if request.user.is_authenticated:
            today = now().date()
            already = Scan.objects.filter(
                meowl=m, user=request.user, created_at__date=today
            ).exists()
            if not already:
                ua = request.META.get("HTTP_USER_AGENT", "")
                ip = request.META.get("REMOTE_ADDR", "")
                Scan.objects.create(meowl=m, user=request.user, user_agent=ua, ip_hash=ip)
                PointsLedger.objects.create(user=request.user, meowl=m, points=5, reason="scan")
                AuditLog.objects.create(actor=request.user, action="scan", meowl=m, detail=f"Scanned {m.slug}")
                messages.success(request, "Scan recorded. +5 points!")
            else:
                # Optional: gentle note; or remove this if you prefer no message
                messages.info(request, "You already got today’s +5 points for this Meowl.")
        else:
            messages.info(request, "Log in to earn +5 points for scanning.")

    # Handle comment submit
    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Please sign in to comment.")
            return redirect("login")
        form = CommentForm(request.POST)
        if form.is_valid():
            Comment.objects.create(meowl=m, user=request.user, text=form.cleaned_data["text"])
            messages.success(request, "Comment posted.")
            return redirect("meowls:detail", slug=m.slug)
        comment_form = form
    else:
        comment_form = CommentForm()

    comments = m.comments.select_related("user").order_by("-created_at")
    if not (request.user.is_authenticated and request.user.is_staff):
        comments = comments.filter(is_hidden=False)

    ctx = {
        "meowl": m,
        "comments": comments,
        "comment_form": comment_form,
        "token_ok": token_ok,
    }
    return render(request, "meowls/detail.html", ctx)


@login_required
def scan_meowl(request, slug):
    m = get_object_or_404(Meowl, slug=slug)
    ua = request.META.get("HTTP_USER_AGENT", "")
    ip = request.META.get("REMOTE_ADDR", "")
    Scan.objects.create(meowl=m, user=request.user, user_agent=ua, ip_hash=ip)
    PointsLedger.objects.create(user=request.user, meowl=m, points=5, reason="scan")
    AuditLog.objects.create(actor=request.user, action="scan", meowl=m, detail=f"Scanned {m.slug}")
    messages.success(request, "Scan recorded. +5 points!")
    return redirect("meowls:detail", slug=slug)

# -----------------------
# Staff / Admin
# -----------------------

staff_required = user_passes_test(lambda u: u.is_staff)
superuser_required = user_passes_test(lambda u: u.is_superuser)


@staff_required
def staff_dashboard(request):
    # OPTIONAL: make sure every user has a UserStatus row so templates never explode
    missing_ids = list(User.objects.filter(status__isnull=True).values_list("id", flat=True))
    if missing_ids:
        UserStatus.objects.bulk_create([UserStatus(user_id=uid) for uid in missing_ids], ignore_conflicts=True)

    meowls = (
        Meowl.objects.select_related("owner")
        .annotate(visible_comments=Count("comments", filter=Q(comments__is_hidden=False)))
        .order_by("name")
    )

    # ✅ use "status" (not "userstatus")
    users = User.objects.select_related("status").order_by("username")

    recent_comments = (
        Comment.objects.select_related("user", "meowl")
        .order_by("-created_at")[:50]
    )
    logs = (
        AuditLog.objects.select_related("actor", "target_user", "meowl")
        .order_by("-created_at")[:100]
    )

    return render(
        request,
        "meowls/admin_dashboard.html",
        {"meowls": meowls, "recent_comments": recent_comments, "users": users, "logs": logs},
    )

@staff_required
def archive_meowl(request, slug):
    if request.method != "POST":
        return redirect("meowls:staff_dashboard")
    m = get_object_or_404(Meowl, slug=slug)
    if not m.is_archived:
        m.is_archived = True
        m.archived_at = now()
        m.archived_by = request.user
        m.save(update_fields=["is_archived", "archived_at", "archived_by"])
        AuditLog.objects.create(actor=request.user, action="meowl_archive", meowl=m, detail=f"Archived {m.slug}")
        messages.success(request, f"Archived {m.name}.")
    return redirect("meowls:staff_dashboard")


@staff_required
def unarchive_meowl(request, slug):
    if request.method != "POST":
        return redirect("meowls:staff_dashboard")
    m = get_object_or_404(Meowl, slug=slug)
    if m.is_archived:
        m.is_archived = False
        m.archived_at = None
        m.archived_by = None
        m.save(update_fields=["is_archived", "archived_at", "archived_by"])
        AuditLog.objects.create(actor=request.user, action="meowl_unarchive", meowl=m, detail=f"Unarchived {m.slug}")
        messages.success(request, f"Unarchived {m.name}.")
    return redirect("meowls:staff_dashboard")


@staff_required
def hide_comment(request, pk: int):
    if request.method != "POST":
        return redirect("meowls:staff_dashboard")
    c = get_object_or_404(Comment, pk=pk)
    if not c.is_hidden:
        c.is_hidden = True
        c.hidden_at = now()
        c.hidden_by = request.user
        c.save(update_fields=["is_hidden", "hidden_at", "hidden_by"])
        reason = (request.POST.get("reason") or "").strip()
        AuditLog.objects.create(
            actor=request.user,
            action="comment_hide",
            meowl=c.meowl,
            comment_id=c.id,
            detail=reason,
        )
        messages.success(request, f"Comment #{c.id} hidden.")
    return redirect("meowls:detail", slug=c.meowl.slug)


@staff_required
def unhide_comment(request, pk: int):
    if request.method != "POST":
        return redirect("meowls:staff_dashboard")
    c = get_object_or_404(Comment, pk=pk)
    if c.is_hidden:
        c.is_hidden = False
        c.hidden_at = None
        c.hidden_by = None
        c.save(update_fields=["is_hidden", "hidden_at", "hidden_by"])
        AuditLog.objects.create(
            actor=request.user,
            action="comment_unhide",
            meowl=c.meowl,
            comment_id=c.id,
        )
        messages.success(request, f"Comment #{c.id} unhidden.")
    return redirect("meowls:detail", slug=c.meowl.slug)


@superuser_required
def promote_user(request, user_id: int):
    if request.method != "POST":
        return redirect("meowls:staff_dashboard")
    u = get_object_or_404(User, pk=user_id)
    if not u.is_staff:
        u.is_staff = True
        u.save(update_fields=["is_staff"])
        AuditLog.objects.create(actor=request.user, action="user_promote", target_user=u)
        messages.success(request, f"Promoted {u.username} to staff.")
    return redirect("meowls:staff_dashboard")


@superuser_required
def demote_user(request, user_id: int):
    if request.method != "POST":
        return redirect("meowls:staff_dashboard")
    u = get_object_or_404(User, pk=user_id)
    if u.is_staff and u != request.user:
        u.is_staff = False
        u.save(update_fields=["is_staff"])
        AuditLog.objects.create(actor=request.user, action="user_demote", target_user=u)
        messages.success(request, f"Demoted {u.username} from staff.")
    elif u == request.user:
        messages.error(request, "You can’t demote yourself.")
    return redirect("meowls:staff_dashboard")

# -----------------------
# PDF (viewer + file endpoints)
# -----------------------

@login_required
@login_required
def pdf_preview(request, slug):
    """
    Renders an HTML viewer page with an <iframe> that loads the PDF.
    Only staff or the owner can view.
    """
    m = get_object_or_404(Meowl, slug=slug)
    is_owner = request.user == m.owner
    if not (request.user.is_staff or is_owner):
        messages.error(request, "Only staff or the owner can view the PDF.")
        return redirect("meowls:detail", slug=slug)
    return render(request, "meowls/pdf_preview.html", {"meowl": m, "is_owner": is_owner})


@login_required
@xframe_options_sameorigin   # <-- allow embedding this response on same-origin pages
def pdf_file(request, slug):
    """
    Returns the PDF bytes with inline disposition so the iframe can render it.
    """
    m = get_object_or_404(Meowl, slug=slug)
    if not (request.user.is_staff or request.user == m.owner):
        messages.error(request, "Only staff or the owner can view the PDF.")
        return redirect("meowls:detail", slug=slug)
    data = build_meowl_pdf(m)
    from django.http import HttpResponse
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="meowl.pdf"'
    return resp

@login_required
def pdf_download(request, slug):
    """
    Forces a download of the PDF.
    """
    m = get_object_or_404(Meowl, slug=slug)
    if not (request.user.is_staff or request.user == m.owner):
        messages.error(request, "Only staff or the owner can download the PDF.")
        return redirect("meowls:detail", slug=slug)
    data = build_meowl_pdf(m)
    from django.http import HttpResponse
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{m.slug}.pdf"'
    return resp

# -----------------------
# Leaderboard & signup
# -----------------------

def leaderboard(request):
    rows = (
        PointsLedger.objects
        .filter(Q(user__status__is_suspended=False) | Q(user__status__isnull=True))
        .values("user__username")
        .annotate(points=Sum("points"))
        .order_by("-points")[:100]
    )
    return render(request, "meowls/leaderboard.html", {"rows": rows})


# meowls/views.py (inside signup)
def signup(request):
    if request.user.is_authenticated:
        return redirect("meowls:index")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            u = form.save()
            login(request, u)
            # Send email verification
            if u.email:
                send_email_verification(request, u)
                messages.success(request, "Welcome! We sent a verification email—please check your inbox.")
            else:
                messages.info(request, "Add your email to verify your account.")
            return redirect("meowls:index")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


@superuser_required
def suspend_user(request, user_id: int):
    if request.method != "POST":
        return redirect("meowls:staff_dashboard")
    u = get_object_or_404(User, pk=user_id)
    st, _ = UserStatus.objects.get_or_create(user=u)
    if not st.is_suspended:
        st.is_suspended = True
        st.suspended_at = now()
        st.suspended_by = request.user
        st.reason = (request.POST.get("reason") or "").strip()
        st.save()
        AuditLog.objects.create(actor=request.user, action="user_suspend", target_user=u, detail=st.reason)
        messages.success(request, f"Suspended {u.username}.")
    return redirect("meowls:staff_dashboard")


@superuser_required
def unsuspend_user(request, user_id: int):
    if request.method != "POST":
        return redirect("meowls:staff_dashboard")
    u = get_object_or_404(User, pk=user_id)
    
    st, _ = UserStatus.objects.get_or_create(user=u)
    if st.is_suspended:
        st.is_suspended = False
        st.suspended_at = None
        st.suspended_by = None
        st.reason = ""
        st.save()
        AuditLog.objects.create(actor=request.user, action="user_unsuspend", target_user=u)
        messages.success(request, f"Unsuspended {u.username}.")
    return redirect("meowls:staff_dashboard")

@login_required
def resend_verification(request):
    if not request.user.email:
        messages.error(request, "Add an email to your account first.")
        return redirect("meowls:index")

    st, _ = UserStatus.objects.get_or_create(user=request.user)
    if st.email_verified:
        messages.info(request, "Your email is already verified.")
        return redirect("meowls:index")

    send_email_verification(request, request.user)
    messages.success(request, "Verification email sent.")
    return redirect("meowls:index")


def verify_email(request, uidb64, token):
    user = None
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    if user and default_token_generator.check_token(user, token):
        st, _ = UserStatus.objects.get_or_create(user=user)
        if not st.email_verified:
            st.email_verified = True
            st.email_verified_at = now()
            st.save(update_fields=["email_verified", "email_verified_at"])
        messages.success(request, "Email verified! 🎉")
        return redirect("meowls:index")
    else:
        messages.error(request, "Invalid or expired verification link.")
        return redirect("meowls:index")
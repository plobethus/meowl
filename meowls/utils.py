from django.utils import timezone
from django.db.models import Sum
from .models import PointsLedger

def leaderboard(period: str = "all"):
    qs = PointsLedger.objects.all()
    now = timezone.now()
    if period == "30d":
        qs = qs.filter(created_at__gte=now - timezone.timedelta(days=30))
    elif period == "7d":
        qs = qs.filter(created_at__gte=now - timezone.timedelta(days=7))

    return (qs.values("user__username")
              .annotate(total=Sum("points"))
              .order_by("-total"))

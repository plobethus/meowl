from django.core import signing
from django.conf import settings
from datetime import timedelta

def make_qr_token(slug: str) -> str:
    signer = signing.TimestampSigner()
    return signer.sign(slug)

def check_qr_token(token: str, max_age_minutes: int = None) -> str|None:
    if max_age_minutes is None:
        max_age_minutes = settings.QR_TOKEN_MINUTES
    signer = signing.TimestampSigner()
    try:
        slug = signer.unsign(token, max_age=max_age_minutes*60)
        return slug
    except signing.BadSignature:
        return None

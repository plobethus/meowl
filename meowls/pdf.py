from io import BytesIO
from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML

def build_meowl_pdf(meowl):
    # short-lived token used in printed QR
    from .tokens import make_qr_token
    token = make_qr_token(meowl.slug)
    qr_url = f"{settings.SITE_URL}/meowls/{meowl.slug}/?t={token}"

    # absolute URL for the header image (single official image)
    header_image = settings.SITE_URL.rstrip("/") + settings.MEOWL_HEADER_IMAGE

    html = render_to_string("meowls/pdf.html", {
        "meowl": meowl,
        "qr_url": qr_url,
        "header_image": header_image,
        "site_url": settings.SITE_URL,
    })
    out = BytesIO()
    HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(out)
    return out.getvalue()

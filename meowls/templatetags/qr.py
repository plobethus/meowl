import base64, qrcode
from io import BytesIO
from django import template
register = template.Library()

@register.filter(name="qr_b64")
def qr_b64(_val, data: str) -> str:
    img = qrcode.make(data)
    bio = BytesIO()
    img.save(bio, format="PNG")
    return base64.b64encode(bio.getvalue()).decode("ascii")

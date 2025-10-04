import base64
from io import BytesIO
import qrcode
from django import template

register = template.Library()

@register.filter(name="qr_b64")
def qr_b64(_val, data: str) -> str:
    img = qrcode.make(data)
    bio = BytesIO()
    img.save(bio, format="PNG")
    return base64.b64encode(bio.getvalue()).decode("ascii")

@register.filter
def get_item(d, key):
    """
    Safe dict lookup in templates: {{ mydict|get_item:some_id }}
    Returns 0 if the dict is missing or key not present.
    """
    try:
        return d.get(key, 0)
    except Exception:
        return 0

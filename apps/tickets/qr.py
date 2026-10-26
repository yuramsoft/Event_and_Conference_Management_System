"""Server-side QR rendering (used in emails and as a no-JS fallback)."""
import base64
import io

import qrcode
from qrcode.image.svg import SvgPathImage


def qr_png_bytes(data: str, box_size: int = 8) -> bytes:
    img = qrcode.make(data, box_size=box_size, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def qr_png_data_uri(data: str) -> str:
    return "data:image/png;base64," + base64.b64encode(qr_png_bytes(data)).decode()


def qr_svg(data: str) -> str:
    img = qrcode.make(data, image_factory=SvgPathImage, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()

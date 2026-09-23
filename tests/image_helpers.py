# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""Real (tiny) image files for upload tests. Uploads are identified by their bytes, not
the declared Content-Type (services/tenant_service.py::_detect_image_type), so tests need
genuine images rather than placeholder bytes."""

import io

from PIL import Image


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (16, 16)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (37, 99, 235)).save(buffer, format=fmt)
    return buffer.getvalue()


PNG = image_bytes("PNG")
JPEG = image_bytes("JPEG")
ICO = image_bytes("ICO")
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(document.cookie)</script></svg>"

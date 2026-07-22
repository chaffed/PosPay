from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel


class OCRResult(BaseModel):
    extracted_amount: Decimal | None
    extracted_payee: str | None
    confidence: float  # 0.0-1.0, normalized across providers
    raw_response: dict[str, Any]


class OCRProvider(Protocol):
    """Calling code (networks/check/ocr_processing.py) depends only on this protocol via
    factory.get_ocr_provider() — never on a concrete provider — so swapping Tesseract for
    a cloud vendor is a config change, not a code change."""

    name: str

    def extract(self, image_bytes: bytes, *, image_format: str = "png") -> OCRResult: ...

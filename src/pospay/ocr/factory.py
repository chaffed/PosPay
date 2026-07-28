# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.config import Settings, get_settings
from pospay.ocr.base import OCRProvider

_PROVIDER_CACHE: dict[str, OCRProvider] = {}


def get_ocr_provider(settings: Settings | None = None) -> OCRProvider:
    settings = settings or get_settings()
    provider_name = settings.ocr_provider

    if provider_name in _PROVIDER_CACHE:
        return _PROVIDER_CACHE[provider_name]

    if provider_name == "tesseract":
        from pospay.ocr.tesseract_provider import TesseractOCRProvider

        provider: OCRProvider = TesseractOCRProvider()
    elif provider_name == "textract":
        from pospay.ocr.textract_provider import TextractOCRProvider

        provider = TextractOCRProvider()
    elif provider_name == "azure_document_intelligence":
        from pospay.ocr.azure_di_provider import AzureDocumentIntelligenceOCRProvider

        provider = AzureDocumentIntelligenceOCRProvider()
    else:
        raise ValueError(f"Unknown OCR provider: {provider_name!r}")

    _PROVIDER_CACHE[provider_name] = provider
    return provider

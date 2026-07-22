from pospay.ocr.base import OCRResult


class AzureDocumentIntelligenceOCRProvider:
    """Azure AI Document Intelligence implements the same OCRProvider protocol. Strong
    general handwriting recognition — worth considering for tenants already on Azure.

    Stub: requires `pip install pospay[azure-di]` plus an Azure Document Intelligence
    resource endpoint/key. Not wired up to a real prebuilt-document call in this build —
    implementing and testing that requires a live Azure resource."""

    name = "azure_document_intelligence"

    def __init__(self) -> None:
        try:
            import azure.ai.documentintelligence  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "azure_document_intelligence OCR provider requires the 'azure-di' extra: "
                "pip install pospay[azure-di]"
            ) from exc

    def extract(self, image_bytes: bytes, *, image_format: str = "png") -> OCRResult:
        raise NotImplementedError(
            "AzureDocumentIntelligenceOCRProvider.extract() is a stub — wire up the "
            "prebuilt-document analyze call here when a live Azure resource is available."
        )

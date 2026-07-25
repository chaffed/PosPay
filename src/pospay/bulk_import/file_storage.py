import contextlib
import uuid
from pathlib import Path

from pospay.config import get_settings


def save_uploaded_file(tenant_id: uuid.UUID, upload_id: uuid.UUID, filename: str, data: bytes) -> str:
    """Local filesystem storage, same pattern as ocr/storage.py::save_image and
    web/branding_storage.py::save_tenant_asset — the DB only ever stores this path, never
    the blob itself. The id-prefixed filename avoids collisions between uploads that
    happen to share a name; the original name is preserved for the download's
    Content-Disposition header. Best-effort read-only permissions afterward — a
    defense-in-depth nicety, not what actually detects tampering (that's the HMAC in
    bulk_import/signing.py, re-checked against a fresh read of this file on demand)."""
    settings = get_settings()
    directory = Path(settings.bulk_upload_storage_dir) / str(tenant_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{upload_id}_{filename}"
    path.write_bytes(data)
    with contextlib.suppress(OSError):
        path.chmod(0o444)
    return str(path)


def read_uploaded_file(path: str) -> bytes:
    return Path(path).read_bytes()

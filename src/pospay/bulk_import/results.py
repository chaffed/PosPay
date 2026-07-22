import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BulkFileRowResult:
    """Shared across every bulk-file import path (issued items, ACH — delimited/Excel/
    NACHA) so the web layer has one result shape to render regardless of source format.
    `row_label` is a human-facing locator: a 1-based row number for tabular files, or
    something like 'entry 3 (trace 123456789012345)' for NACHA, since a raw list index
    means nothing to someone looking at their own spreadsheet or ACH file."""

    row_label: str
    success: bool
    created_id: uuid.UUID | None = None
    error: str | None = None

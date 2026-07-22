from pydantic import BaseModel


class BulkRowResultOut(BaseModel):
    index: int
    success: bool
    id: str | None = None
    status: str | None = None
    error: str | None = None


class BulkSubmitResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[BulkRowResultOut]

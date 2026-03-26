"""Common schemas."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    message: str
    details: dict | None = None

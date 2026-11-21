"""Pydantic schemas for vendor lifecycle activity history."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class VendorActivityItem(BaseModel):
    """Structured representation of a discrete vendor lifecycle event."""
    id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    vendor_id: str = Field(..., examples=["123e4567-e89b-12d3-a456-426614174000"])
    event_type: str = Field(..., examples=["VENDOR_SUBMITTED", "DECISION_EXECUTED", "DECISION_REEVALUATED", "VENDOR_UPDATED"])
    title: str = Field(..., examples=["Vendor Registration Submitted"])
    description: str = Field(..., examples=["Initial vendor registration submitted with status SUBMITTED."])
    status: Optional[str] = Field(None, examples=["SUBMITTED", "APPROVED", "PENDING", "REJECTED"])
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VendorActivityPagination(BaseModel):
    """Paginated collection of vendor activity events."""
    items: List[VendorActivityItem]
    total: int = Field(..., examples=[3])
    page: int = Field(..., examples=[1])
    page_size: int = Field(..., examples=[10])
    total_pages: int = Field(..., examples=[1])

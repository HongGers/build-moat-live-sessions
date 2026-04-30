from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    expires_at: datetime | None = None


class CreateResponse(BaseModel):
    token: str
    short_url: str
    qr_code_url: str
    original_url: str


class QRInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token: str
    original_url: str
    short_url: str
    qr_code_url: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    is_deleted: bool


class UpdateRequest(BaseModel):
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    expires_at: datetime | None = None


class AnalyticsDay(BaseModel):
    date: str
    count: int


class AnalyticsResponse(BaseModel):
    token: str
    total_scans: int
    scans_by_day: list[AnalyticsDay]

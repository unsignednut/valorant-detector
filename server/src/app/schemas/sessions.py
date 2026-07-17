from datetime import datetime

from pydantic import BaseModel, Field


class Resolution(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SessionCreateRequest(BaseModel):
    mode: str = "offline_review"
    map_id: str | None = None
    resolution: Resolution | None = None
    source: str = "manual_upload"


class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: datetime
    manifest_path: str


class SessionManifest(BaseModel):
    schema_version: str
    session_id: str
    created_at: datetime
    mode: str
    map_id: str | None
    resolution: Resolution | None
    source: str
    media_assets: list[dict] = []


from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    original_name: str | None
    stored_name: str
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    path: str


class ImageInfo(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: str
    mode: str


class RoiInfo(BaseModel):
    name: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    normalized: dict[str, float]
    path: str
    sha256: str


class MediaUploadResponse(BaseModel):
    status: str
    session_id: str
    media_id: str
    uploaded_at: datetime
    file: FileInfo
    image: ImageInfo
    rois: list[RoiInfo] = []
    observation_ids: list[str] = Field(default_factory=list)
    analysis: dict[str, Any] = Field(default_factory=dict)


class LegacyFrameAnalysisResponse(BaseModel):
    status: str
    file: dict
    image: ImageInfo
    analysis: dict
    message: str

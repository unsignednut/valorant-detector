from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ObservationSource = Literal[
    "roi",
    "hud",
    "minimap",
    "main_view",
    "killfeed",
    "audio",
    "manual",
]


class ObservationEvent(BaseModel):
    observation_id: str
    session_id: str
    media_id: str | None = None
    round_id: str | None = None
    frame_id: int | None = Field(default=None, ge=0)
    timestamp_ms: int = Field(ge=0)
    source: ObservationSource
    kind: str
    entity_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    payload: dict[str, Any]
    model_version: str | None = None
    created_at: datetime


class ObservationListResponse(BaseModel):
    session_id: str
    count: int
    observations: list[ObservationEvent]


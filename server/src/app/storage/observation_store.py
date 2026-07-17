from __future__ import annotations

from datetime import datetime, timezone

from server.src.app.schemas.media import RoiInfo
from server.src.app.schemas.observations import ObservationEvent
from server.src.app.storage.session_store import session_store


class ObservationStore:
    def next_observation_index(self, session_id: str) -> int:
        return len(self.list_observations(session_id)) + 1

    def append_many(
        self,
        session_id: str,
        observations: list[ObservationEvent],
    ) -> None:
        path = session_store.observations_jsonl_path(session_id)
        with path.open("a", encoding="utf-8") as file:
            for observation in observations:
                file.write(observation.model_dump_json())
                file.write("\n")

    def list_observations(self, session_id: str) -> list[ObservationEvent]:
        path = session_store.observations_jsonl_path(session_id)
        if not path.exists():
            return []

        observations: list[ObservationEvent] = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                observations.append(ObservationEvent.model_validate_json(line))

        return observations

    def create_roi_observations(
        self,
        session_id: str,
        media_id: str,
        rois: list[RoiInfo],
        timestamp_ms: int = 0,
        start_index: int | None = None,
    ) -> list[ObservationEvent]:
        start_index = start_index or self.next_observation_index(session_id)
        created_at = datetime.now(timezone.utc)

        observations: list[ObservationEvent] = []
        for offset, roi in enumerate(rois):
            observations.append(
                ObservationEvent(
                    observation_id=f"obs_{start_index + offset:06d}",
                    session_id=session_id,
                    media_id=media_id,
                    timestamp_ms=timestamp_ms,
                    source="roi",
                    kind="roi_extracted",
                    confidence=1.0,
                    payload={
                        "roi_name": roi.name,
                        "x": roi.x,
                        "y": roi.y,
                        "width": roi.width,
                        "height": roi.height,
                        "normalized": roi.normalized,
                        "path": roi.path,
                        "sha256": roi.sha256,
                    },
                    model_version="roi-extractor-0.1",
                    created_at=created_at,
                )
            )

        return observations


observation_store = ObservationStore()

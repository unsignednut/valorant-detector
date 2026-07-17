from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from server.src.app.schemas.sessions import SessionCreateRequest, SessionManifest

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class SessionNotFoundError(FileNotFoundError):
    pass


class InvalidSessionIdError(ValueError):
    pass


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        data_dir = os.environ.get("VALORANT_DETECTOR_DATA_DIR")
        self.root = (root or Path(data_dir or "data/sessions")).resolve()

    def create_session(self, request: SessionCreateRequest) -> SessionManifest:
        created_at = datetime.now(timezone.utc)
        session_id = self._new_session_id(created_at)
        session_dir = self._session_dir(session_id, must_exist=False)

        session_dir.mkdir(parents=True, exist_ok=False)
        for child in (
            "media",
            "rois",
            "observations",
            "states",
            "decisions",
            "annotations",
            "logs",
        ):
            (session_dir / child).mkdir()

        manifest = SessionManifest(
            schema_version="0.1",
            session_id=session_id,
            created_at=created_at,
            mode=request.mode,
            map_id=request.map_id,
            resolution=request.resolution,
            source=request.source,
            media_assets=[],
        )
        self.write_manifest(manifest)
        return manifest

    def get_manifest(self, session_id: str) -> SessionManifest:
        manifest_path = self.manifest_path(session_id)
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SessionNotFoundError(session_id) from exc

        return SessionManifest.model_validate(data)

    def write_manifest(self, manifest: SessionManifest) -> None:
        manifest_path = self.manifest_path(manifest.session_id, must_exist=False)
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def register_media_asset(self, session_id: str, asset: dict) -> None:
        manifest = self.get_manifest(session_id)
        manifest.media_assets.append(asset)
        self.write_manifest(manifest)

    def media_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "media"

    def roi_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "rois"

    def observations_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "observations"

    def observations_jsonl_path(self, session_id: str) -> Path:
        return self.observations_dir(session_id) / "observations.jsonl"

    def manifest_path(self, session_id: str, must_exist: bool = True) -> Path:
        return self._session_dir(session_id, must_exist=must_exist) / "manifest.json"

    def _session_dir(self, session_id: str, must_exist: bool = True) -> Path:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise InvalidSessionIdError(session_id)

        session_dir = (self.root / session_id).resolve()
        root = self.root.resolve()

        if session_dir != root and root not in session_dir.parents:
            raise InvalidSessionIdError(session_id)

        if must_exist and not session_dir.exists():
            raise SessionNotFoundError(session_id)

        return session_dir

    def _new_session_id(self, created_at: datetime) -> str:
        date_part = created_at.strftime("%Y%m%d_%H%M%S")
        return f"session_{date_part}_{uuid4().hex[:8]}"


session_store = SessionStore()

from fastapi import APIRouter, Body, HTTPException

from server.src.app.schemas.sessions import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionManifest,
)
from server.src.app.storage.session_store import (
    InvalidSessionIdError,
    SessionNotFoundError,
    session_store,
)

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionCreateResponse)
async def create_session(
    request: SessionCreateRequest | None = Body(default=None),
) -> SessionCreateResponse:
    manifest = session_store.create_session(request or SessionCreateRequest())
    return SessionCreateResponse(
        session_id=manifest.session_id,
        created_at=manifest.created_at,
        manifest_path=str(session_store.manifest_path(manifest.session_id)),
    )


@router.get("/{session_id}", response_model=SessionManifest)
async def get_session(session_id: str) -> SessionManifest:
    try:
        return session_store.get_manifest(session_id)
    except InvalidSessionIdError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id.") from exc
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc


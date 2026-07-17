from fastapi import APIRouter, HTTPException

from server.src.app.schemas.observations import ObservationListResponse
from server.src.app.storage.observation_store import observation_store
from server.src.app.storage.session_store import InvalidSessionIdError, SessionNotFoundError

router = APIRouter(
    prefix="/v1/sessions/{session_id}/observations",
    tags=["observations"],
)


@router.get("", response_model=ObservationListResponse)
async def list_observations(session_id: str) -> ObservationListResponse:
    try:
        observations = observation_store.list_observations(session_id)
    except InvalidSessionIdError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id.") from exc
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc

    return ObservationListResponse(
        session_id=session_id,
        count=len(observations),
        observations=observations,
    )


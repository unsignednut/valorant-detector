from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile

from server.src.app.media.image_loader import (
    MAX_IMAGE_SIZE,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageTypeError,
    extension_for_content_type,
    image_sha256,
    inspect_image,
    next_media_id,
    validate_content_type,
    validate_size,
)
from server.src.app.schemas.media import (
    FileInfo,
    LegacyFrameAnalysisResponse,
    MediaUploadResponse,
    RoiInfo,
)
from server.src.app.schemas.observations import ObservationEvent
from server.src.app.storage.observation_store import observation_store
from server.src.app.storage.session_store import (
    InvalidSessionIdError,
    SessionNotFoundError,
    session_store,
)
from server.src.app.vision.health import HealthDetection, detect_health_from_player_status
from server.src.app.vision.roi import save_default_rois

router = APIRouter(
    prefix="/v1/sessions/{session_id}/media",
    tags=["media"],
)
legacy_router = APIRouter(tags=["legacy"])


@router.post("", response_model=MediaUploadResponse)
async def upload_media(
    session_id: str,
    file: UploadFile = File(...),
) -> MediaUploadResponse:
    image_data = await _read_supported_image(file)
    image = _inspect_or_400(image_data)
    content_type = validate_content_type(file.content_type)
    digest = image_sha256(image_data)

    try:
        media_dir = session_store.media_dir(session_id)
        roi_dir = session_store.roi_dir(session_id)
    except InvalidSessionIdError as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id.") from exc
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc

    media_id = next_media_id(media_dir)
    stored_name = f"{media_id}{extension_for_content_type(content_type)}"
    stored_path = media_dir / stored_name
    stored_path.write_bytes(image_data)
    rois = save_default_rois(image_data, roi_dir, media_id)

    observation_start = observation_store.next_observation_index(session_id)
    observations = observation_store.create_roi_observations(
        session_id=session_id,
        media_id=media_id,
        rois=rois,
        start_index=observation_start,
    )

    health_detection = _detect_health(rois)
    if health_detection is not None:
        observations.append(
            _health_observation(
                session_id=session_id,
                media_id=media_id,
                observation_index=observation_start + len(observations),
                detection=health_detection,
            )
        )

    observation_store.append_many(session_id, observations)

    uploaded_at = datetime.now(timezone.utc)
    file_info = FileInfo(
        original_name=file.filename,
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=len(image_data),
        sha256=digest,
        path=str(stored_path),
    )

    response = MediaUploadResponse(
        status="success",
        session_id=session_id,
        media_id=media_id,
        uploaded_at=uploaded_at,
        file=file_info,
        image=image,
        rois=rois,
        observation_ids=[observation.observation_id for observation in observations],
        analysis={
            "health": _health_analysis_payload(health_detection),
        },
    )

    session_store.register_media_asset(
        session_id,
        {
            "media_id": media_id,
            "uploaded_at": uploaded_at.isoformat(),
            "file": file_info.model_dump(),
            "image": image.model_dump(),
            "rois": [roi.model_dump() for roi in rois],
            "observation_ids": [
                observation.observation_id for observation in observations
            ],
        },
    )
    return response


@legacy_router.post("/analyze/frame", response_model=LegacyFrameAnalysisResponse)
async def analyze_frame(
    file: UploadFile = File(...),
) -> LegacyFrameAnalysisResponse:
    image_data = await _read_supported_image(file)
    image = _inspect_or_400(image_data)

    return LegacyFrameAnalysisResponse(
        status="success",
        file={
            "name": file.filename,
            "content_type": file.content_type,
            "size_bytes": len(image_data),
        },
        image=image,
        analysis={
            "map": None,
            "round_time": None,
            "player_health": None,
            "weapon": None,
            "minimap_detected": False,
        },
        message="Image loaded successfully. Vision recognition is not connected yet.",
    )


async def _read_supported_image(file: UploadFile) -> bytes:
    try:
        validate_content_type(file.content_type)
        image_data = await file.read(MAX_IMAGE_SIZE + 1)
        validate_size(image_data)
        return image_data
    except UnsupportedImageTypeError as exc:
        raise HTTPException(
            status_code=415,
            detail="Only PNG, JPEG, and WebP images are supported.",
        ) from exc
    except ImageTooLargeError as exc:
        raise HTTPException(status_code=413, detail="Image cannot exceed 10 MB.") from exc
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail="Invalid image file.") from exc


def _inspect_or_400(image_data: bytes):
    try:
        return inspect_image(image_data)
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail="Invalid image file.") from exc


def _detect_health(rois: list[RoiInfo]) -> HealthDetection | None:
    player_status_roi = next((roi for roi in rois if roi.name == "player_status"), None)
    if player_status_roi is None:
        return None
    return detect_health_from_player_status(player_status_roi)


def _health_observation(
    session_id: str,
    media_id: str,
    observation_index: int,
    detection: HealthDetection,
) -> ObservationEvent:
    return ObservationEvent(
        observation_id=f"obs_{observation_index:06d}",
        session_id=session_id,
        media_id=media_id,
        timestamp_ms=0,
        source="hud",
        kind="health_observed",
        entity_id="self",
        confidence=detection.confidence,
        payload=_health_analysis_payload(detection),
        model_version="health-detector-0.1",
        created_at=datetime.now(timezone.utc),
    )


def _health_analysis_payload(detection: HealthDetection | None) -> dict:
    if detection is None:
        return {
            "value": None,
            "confidence": 0.0,
            "source_roi": None,
        }

    return {
        "value": detection.value,
        "text": detection.text,
        "confidence": detection.confidence,
        "source_roi": detection.source_roi,
        "roi_path": detection.roi_path,
        "bbox": detection.bbox,
        "digit_scores": detection.digit_scores,
    }

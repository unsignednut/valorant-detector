from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image

from server.src.app.schemas.media import RoiInfo


@dataclass(frozen=True)
class RoiSpec:
    name: str
    left: float
    top: float
    right: float
    bottom: float


DEFAULT_ROI_SPECS = [
    RoiSpec("minimap", 0.00, 0.00, 0.24, 0.40),
    RoiSpec("killfeed", 0.70, 0.04, 0.99, 0.30),
    RoiSpec("hud_bottom", 0.22, 0.78, 0.78, 0.99),
    RoiSpec("player_status", 0.18, 0.78, 0.40, 0.99),
    RoiSpec("weapon_ammo", 0.70, 0.78, 0.99, 0.99),
    RoiSpec("center_view", 0.31, 0.16, 0.69, 0.84),
]


def save_default_rois(
    image_data: bytes,
    roi_dir: Path,
    media_id: str,
) -> list[RoiInfo]:
    roi_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(BytesIO(image_data)) as image:
        image.load()
        source = image.convert("RGB")
        source_width, source_height = source.size

        rois: list[RoiInfo] = []
        for spec in DEFAULT_ROI_SPECS:
            left, top, right, bottom = _to_pixels(spec, source_width, source_height)
            crop = source.crop((left, top, right, bottom))

            stored_name = f"{media_id}_{spec.name}.png"
            stored_path = roi_dir / stored_name
            crop.save(stored_path, format="PNG")

            data = stored_path.read_bytes()
            rois.append(
                RoiInfo(
                    name=spec.name,
                    x=left,
                    y=top,
                    width=right - left,
                    height=bottom - top,
                    normalized={
                        "left": spec.left,
                        "top": spec.top,
                        "right": spec.right,
                        "bottom": spec.bottom,
                    },
                    path=str(stored_path),
                    sha256=sha256(data).hexdigest(),
                )
            )

    return rois


def _to_pixels(spec: RoiSpec, width: int, height: int) -> tuple[int, int, int, int]:
    left = round(spec.left * width)
    top = round(spec.top * height)
    right = round(spec.right * width)
    bottom = round(spec.bottom * height)

    left = max(0, min(left, width - 1))
    top = max(0, min(top, height - 1))
    right = max(left + 1, min(right, width))
    bottom = max(top + 1, min(bottom, height))

    return left, top, right, bottom


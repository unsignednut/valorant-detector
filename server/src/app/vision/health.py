from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from server.src.app.schemas.media import RoiInfo


@dataclass(frozen=True)
class HealthDetection:
    value: int | None
    text: str | None
    confidence: float
    source_roi: str
    roi_path: str
    bbox: dict[str, int] | None
    digit_scores: list[float]


@dataclass(frozen=True)
class _DigitComponent:
    x: int
    y: int
    width: int
    height: int
    mask: np.ndarray


def detect_health_from_player_status(roi: RoiInfo) -> HealthDetection:
    if roi.name != "player_status":
        return _empty_detection(roi, 0.0)

    image = cv2.imread(roi.path)
    if image is None:
        return _empty_detection(roi, 0.0)

    components = _find_digit_components(image)
    groups = _candidate_groups(components, image.shape[1])

    best: tuple[int, str, float, float, dict[str, int], list[float]] | None = None
    for group in groups:
        text = ""
        digit_scores: list[float] = []
        for component in group:
            digit, score = _classify_digit(component.mask)
            text += str(digit)
            digit_scores.append(score)

        if not text:
            continue

        try:
            value = int(text)
        except ValueError:
            continue

        if value < 0 or value > 100:
            continue

        confidence = float(np.mean(digit_scores)) if digit_scores else 0.0
        selection_score = confidence + (0.04 * (len(text) - 1))
        bbox = _group_bbox(group)

        if best is None or selection_score > best[3]:
            best = (value, text, confidence, selection_score, bbox, digit_scores)

    if best is None:
        return _empty_detection(roi, 0.0)

    value, text, confidence, _selection_score, bbox, digit_scores = best
    if confidence < 0.55:
        return HealthDetection(
            value=None,
            text=text,
            confidence=round(confidence, 3),
            source_roi=roi.name,
            roi_path=roi.path,
            bbox=bbox,
            digit_scores=[round(score, 3) for score in digit_scores],
        )

    return HealthDetection(
        value=value,
        text=text,
        confidence=round(min(confidence, 0.99), 3),
        source_roi=roi.name,
        roi_path=roi.path,
        bbox=bbox,
        digit_scores=[round(score, 3) for score in digit_scores],
    )


def _empty_detection(roi: RoiInfo, confidence: float) -> HealthDetection:
    return HealthDetection(
        value=None,
        text=None,
        confidence=confidence,
        source_roi=roi.name,
        roi_path=roi.path,
        bbox=None,
        digit_scores=[],
    )


def _find_digit_components(image: np.ndarray) -> list[_DigitComponent]:
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    bright_text = cv2.inRange(
        hsv,
        np.array([0, 0, 165], dtype=np.uint8),
        np.array([180, 105, 255], dtype=np.uint8),
    )

    labels_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        bright_text,
        8,
    )

    components: list[_DigitComponent] = []
    min_height = max(10, round(height * 0.10))
    max_height = max(min_height + 1, round(height * 0.30))
    min_area = max(20, round(height * width * 0.0004))

    for label in range(1, labels_count):
        x, y, component_width, component_height, area = [
            int(value) for value in stats[label]
        ]

        if y < height * 0.45:
            continue
        if component_height < min_height or component_height > max_height:
            continue
        if component_width < 3 or component_width > width * 0.20:
            continue
        if area < min_area:
            continue

        component_mask = bright_text[y : y + component_height, x : x + component_width]
        components.append(
            _DigitComponent(
                x=x,
                y=y,
                width=component_width,
                height=component_height,
                mask=component_mask,
            )
        )

    return sorted(components, key=lambda component: component.x)


def _candidate_groups(
    components: list[_DigitComponent],
    image_width: int,
) -> list[list[_DigitComponent]]:
    groups: list[list[_DigitComponent]] = []

    for start in range(len(components)):
        group: list[_DigitComponent] = []
        previous: _DigitComponent | None = None

        for component in components[start:]:
            if previous is not None:
                gap = component.x - (previous.x + previous.width)
                if gap < 0 or gap > image_width * 0.08:
                    break

                vertical_overlap = min(
                    previous.y + previous.height,
                    component.y + component.height,
                ) - max(previous.y, component.y)
                if vertical_overlap < min(previous.height, component.height) * 0.55:
                    break

            group.append(component)
            previous = component

            if 1 <= len(group) <= 3:
                groups.append(group.copy())
            if len(group) == 3:
                break

    return groups


def _classify_digit(mask: np.ndarray) -> tuple[int, float]:
    normalized = _normalize_mask(mask)

    best_digit = 0
    best_score = 0.0
    for digit, template in _digit_templates():
        score = _iou(normalized, template)
        if score > best_score:
            best_digit = digit
            best_score = score

    return best_digit, best_score


@lru_cache(maxsize=1)
def _digit_templates() -> tuple[tuple[int, np.ndarray], ...]:
    templates: list[tuple[int, np.ndarray]] = []

    font_paths = [
        Path("C:/Windows/Fonts/bahnschrift.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf"),
    ]

    for font_path in font_paths:
        if not font_path.exists():
            continue

        for font_size in (24, 26, 28, 30, 32, 34, 36):
            for digit in range(10):
                templates.append(
                    (digit, _render_digit_template(digit, font_path, font_size))
                )

    if not templates:
        for digit in range(10):
            templates.append((digit, _render_cv2_digit_template(digit)))

    return tuple((digit, template) for digit, template in templates)


def _render_digit_template(digit: int, font_path: Path, font_size: int) -> np.ndarray:
    image = Image.new("L", (64, 64), 0)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), font_size)
    bbox = draw.textbbox((0, 0), str(digit), font=font)
    draw.text(
        (6 - bbox[0], 6 - bbox[1]),
        str(digit),
        font=font,
        fill=255,
    )
    array = np.array(image)
    _, binary = cv2.threshold(array, 10, 255, cv2.THRESH_BINARY)
    return _normalize_mask(binary)


def _render_cv2_digit_template(digit: int) -> np.ndarray:
    image = np.zeros((64, 64), dtype=np.uint8)
    cv2.putText(
        image,
        str(digit),
        (6, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.3,
        255,
        3,
        cv2.LINE_AA,
    )
    _, binary = cv2.threshold(image, 10, 255, cv2.THRESH_BINARY)
    return _normalize_mask(binary)


def _normalize_mask(mask: np.ndarray, target_size: tuple[int, int] = (28, 40)) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    canvas_width, canvas_height = target_size
    canvas = np.zeros((canvas_height, canvas_width), dtype=np.uint8)

    if len(xs) == 0 or len(ys) == 0:
        return canvas

    crop = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    crop_height, crop_width = crop.shape[:2]

    scale = min(
        (canvas_width - 4) / max(crop_width, 1),
        (canvas_height - 4) / max(crop_height, 1),
    )
    resized_width = max(1, round(crop_width * scale))
    resized_height = max(1, round(crop_height * scale))

    resized = cv2.resize(
        crop,
        (resized_width, resized_height),
        interpolation=cv2.INTER_NEAREST,
    )

    x = (canvas_width - resized_width) // 2
    y = (canvas_height - resized_height) // 2
    canvas[y : y + resized_height, x : x + resized_width] = resized
    return canvas


def _iou(left: np.ndarray, right: np.ndarray) -> float:
    left_mask = left > 0
    right_mask = right > 0
    intersection = np.logical_and(left_mask, right_mask).sum()
    union = np.logical_or(left_mask, right_mask).sum()
    if union == 0:
        return 0.0
    return float(intersection / union)


def _group_bbox(group: list[_DigitComponent]) -> dict[str, int]:
    left = min(component.x for component in group)
    top = min(component.y for component in group)
    right = max(component.x + component.width for component in group)
    bottom = max(component.y + component.height for component in group)
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }

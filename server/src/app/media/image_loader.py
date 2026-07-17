from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from server.src.app.schemas.media import ImageInfo

MAX_IMAGE_SIZE = 10 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class UnsupportedImageTypeError(ValueError):
    pass


class ImageTooLargeError(ValueError):
    pass


class InvalidImageError(ValueError):
    pass


def validate_content_type(content_type: str | None) -> str:
    if content_type not in SUPPORTED_IMAGE_TYPES:
        raise UnsupportedImageTypeError("Only PNG, JPEG, and WebP images are supported.")
    return content_type


def validate_size(data: bytes) -> None:
    if len(data) > MAX_IMAGE_SIZE:
        raise ImageTooLargeError("Image cannot exceed 10 MB.")


def inspect_image(data: bytes) -> ImageInfo:
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            width, height = image.size
            image_format = image.format or "unknown"
            image_mode = image.mode
    except UnidentifiedImageError as exc:
        raise InvalidImageError("The uploaded file is not a valid image.") from exc

    return ImageInfo(
        width=width,
        height=height,
        format=image_format,
        mode=image_mode,
    )


def image_sha256(data: bytes) -> str:
    return sha256(data).hexdigest()


def extension_for_content_type(content_type: str) -> str:
    return SUPPORTED_IMAGE_TYPES[content_type]


def next_media_id(media_dir: Path) -> str:
    existing_count = len(list(media_dir.glob("image_*.*")))
    return f"image_{existing_count + 1:06d}"


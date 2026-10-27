"""Product image upload validation and storage (FR14)."""

import uuid
from pathlib import Path

from fastapi import UploadFile

# Detected by file signature rather than trusting the file name or the
# client-supplied content type.
SUPPORTED_FORMATS = {"jpeg": ".jpg", "png": ".png", "gif": ".gif", "webp": ".webp"}
SUPPORTED_LABEL = "JPEG, PNG, GIF or WEBP"


class ImageUploadError(Exception):
    pass


def detect_image_format(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def has_file(upload: UploadFile | None) -> bool:
    return upload is not None and bool(upload.filename)


async def save_image(upload: UploadFile, upload_dir: Path, max_bytes: int) -> str:
    """Validate an uploaded image and store it. Returns the stored file name."""
    try:
        data = await upload.read(max_bytes + 1)
    except Exception as exc:  # noqa: BLE001 - any read failure is an upload failure
        raise ImageUploadError("The image could not be uploaded. Please try again.") from exc
    if not data:
        raise ImageUploadError("The selected image file is empty.")
    if len(data) > max_bytes:
        raise ImageUploadError(f"The image is too large. The maximum size is {max_bytes // (1024 * 1024)} MB.")
    image_format = detect_image_format(data)
    if image_format is None:
        raise ImageUploadError(f"Unsupported image format. Please upload a {SUPPORTED_LABEL} image.")

    file_name = f"{uuid.uuid4().hex}{SUPPORTED_FORMATS[image_format]}"
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / file_name).write_bytes(data)
    except OSError as exc:
        raise ImageUploadError("The image could not be saved on the server. Please try again.") from exc
    return file_name


def delete_image(upload_dir: Path, file_name: str) -> None:
    path = upload_dir / file_name
    if path.parent == upload_dir:
        path.unlink(missing_ok=True)


def image_url(file_name: str) -> str:
    return f"/uploads/{file_name}"

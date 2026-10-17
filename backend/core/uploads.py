"""Image uploads (school logo, candidate photos).

Files are stored in UPLOAD_DIR under random names; the database keeps the public path '/uploads/<name>'.
Each API serves that folder under its own prefix (/api/web/uploads, /api/mobile/uploads), and the
web and mobile apps add their own API base to the stored path.

Safety: the file type is detected from the file's first bytes, never from its name or the browser's
content-type. Only PNG, JPEG, GIF and WebP are accepted. SVG is refused because it can carry scripts.
"""
import os
import uuid

from fastapi import UploadFile

from . import config
from .errors import ServiceError

PREFIX = "/uploads/"


def _ext(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def read_limited(file: UploadFile) -> bytes:
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise ServiceError(f"Image is too large. Maximum size is {config.MAX_UPLOAD_MB} MB.", 413)
    return data


def save_image(data: bytes) -> str:
    if not data:
        raise ServiceError("No file received.")
    ext = _ext(data)
    if ext is None:
        raise ServiceError("Upload a PNG, JPG, GIF or WebP image.", 415)
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(config.UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    return PREFIX + name


def delete_file(url: str | None):
    """Remove a previously uploaded file. Ignores external URLs and anything that is not in the uploads folder."""
    if not url or not url.startswith(PREFIX):
        return
    path = os.path.join(config.UPLOAD_DIR, os.path.basename(url))
    try:
        os.remove(path)
    except OSError:
        pass

"""Photo storage utilities for delivery order photos.

Responsibilities:
- validate_magic_bytes: verify JPEG/PNG by actual file content, not Content-Type.
- save_photo: persist uploaded bytes to PHOTOS_ROOT/{year}/{month}/{uuid}.{ext}
  and return the relative path.
- resolve_path_safely: build the absolute path for serving, with path-traversal
  guard that ensures the result stays within PHOTOS_ROOT.

Design decisions:
- PHOTOS_ROOT is read from Settings.photos_root at call time (not at import).
  This allows tests to override it via a fixture without patching globals.
- The file is named with a UUID generated at upload time, so the filename in
  the database is never user-supplied — path traversal is structurally impossible.
  The guard in resolve_path_safely is an additional defensive layer.
- Content-type from the multipart envelope is NOT trusted.  Magic bytes are the
  authoritative format check.
"""

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum allowed file size in bytes (2 MB).
MAX_PHOTO_BYTES = 2 * 1024 * 1024

# Magic-byte signatures for supported formats.
# JPEG: FF D8 FF (any next byte)
# PNG:  89 50 4E 47 0D 0A 1A 0A
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Supported MIME types and their canonical file extensions.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class PhotoValidationError(Exception):
    """Raised when a photo fails format or size validation."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_magic_bytes(data: bytes) -> str:
    """Return the canonical extension ('jpg' or 'png') by inspecting magic bytes.

    Raises PhotoValidationError(415) if the bytes do not match JPEG or PNG.
    The caller must pass at least 8 bytes (length of PNG magic).
    """
    if data[:3] == _JPEG_MAGIC:
        return "jpg"
    if data[:8] == _PNG_MAGIC:
        return "png"
    raise PhotoValidationError(
        "Unsupported image format. Only JPEG and PNG are accepted.",
        status_code=415,
    )


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


async def read_and_validate_upload(upload: UploadFile) -> tuple[bytes, str]:
    """Read the entire upload, enforce size limit, and validate magic bytes.

    Returns (raw_bytes, extension) where extension is 'jpg' or 'png'.

    Raises:
    - PhotoValidationError(413) if the file exceeds MAX_PHOTO_BYTES.
    - PhotoValidationError(415) if the format is not JPEG or PNG.

    Reading strategy: read in chunks up to MAX_PHOTO_BYTES + 1 so we can
    detect oversize uploads without loading unbounded data into memory.
    """
    # Read up to limit + 1 byte to detect oversize payloads efficiently.
    buf = io.BytesIO()
    chunk_size = 64 * 1024  # 64 KB chunks
    total = 0

    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_PHOTO_BYTES:
            raise PhotoValidationError(
                f"File exceeds maximum allowed size of {MAX_PHOTO_BYTES // (1024 * 1024)} MB.",
                status_code=413,
            )
        buf.write(chunk)

    raw = buf.getvalue()
    if not raw:
        raise PhotoValidationError("Empty file.", status_code=400)

    ext = validate_magic_bytes(raw)
    return raw, ext


def save_photo(raw: bytes, ext: str, photos_root: Path, taken_at: datetime) -> str:
    """Persist photo bytes to PHOTOS_ROOT/{year}/{month}/{uuid}.{ext}.

    Args:
        raw: validated image bytes.
        ext: canonical extension ('jpg' or 'png').
        photos_root: absolute or relative root directory (from Settings).
        taken_at: UTC timestamp of the photo event — used for year/month dirs.

    Returns:
        Relative path string in the form '{year}/{month}/{uuid}.{ext}'.
        This value is stored in delivery_orders.photo_url.

    Implementation note:
        Writes to a .tmp file first so that the caller can flush the DB and
        then do an atomic os.replace().  The caller is responsible for the
        rename — see upload_photo in delivery_orders.py.
    """
    year = taken_at.astimezone(UTC).strftime("%Y")
    month = taken_at.astimezone(UTC).strftime("%m")
    file_name = f"{uuid.uuid4()}.{ext}"
    relative = f"{year}/{month}/{file_name}"

    dest = photos_root / year / month / file_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(raw)

    return relative, tmp, dest  # caller must os.replace(tmp, dest) after DB flush


# ---------------------------------------------------------------------------
# Serve
# ---------------------------------------------------------------------------


def resolve_path_safely(relative: str, photos_root: Path) -> Path:
    """Return the absolute path for a stored photo, guarding against traversal.

    The filename stored in the DB is always a UUID, so traversal is structurally
    impossible — but this check is an explicit defensive layer.

    Uses Path.relative_to() instead of startswith() to correctly handle:
    - Relative '.' paths
    - Symlinks (resolve() follows them before the check)
    - Ambiguous prefix matches (e.g. /root-extra vs /root)

    Raises:
        ValueError: if the resolved path escapes photos_root.
    """
    root = photos_root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Resolved path {candidate} is outside photos_root {root}"
        )
    return candidate


def content_type_for_extension(ext: str) -> str:
    """Return the MIME type for a stored extension."""
    return "image/png" if ext == "png" else "image/jpeg"

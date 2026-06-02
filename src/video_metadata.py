"""
Video Metadata Module for PicPlotter Auto

Extracts GPS coordinates (and a best-effort timestamp) from MP4 / MOV video
containers, and provides the video-vs-photo classification helpers used across
the app. Pure standard library only — no extra dependencies — so it parses the
ISO base media file format (ISO-BMFF) boxes directly.

GPS is stored by phones in one of two places inside the ``moov`` box:
  * ``moov/udta/©xyz`` — an ISO-6709 string (Android and many iPhones)
  * a QuickTime ``com.apple.quicktime.location.ISO6709`` metadata key (iPhone)
Both ultimately hold an ISO-6709 string such as ``+37.7866-122.4097+010.000/``.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.exif_extractor import (
    GPSCoordinates,
    ImageMetadata,
    get_supported_extensions,
    is_supported_format,
)

# Video extensions we accept. Lowercase; matching is case-insensitive.
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}

# MIME types for the formats above (used for <video> tags / asset uploads).
_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".m4v": "video/x-m4v",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}

# The QuickTime/Android GPS atom type: 0xA9 ('©') followed by 'xyz'.
_XYZ_MARKER = b"\xa9xyz"
# Matches the decimal-degree ISO-6709 strings phones emit: two signed decimals
# (lat, lon) plus an optional third (altitude). Phones never use the DDMM/DDMMSS
# packed forms, so decimal degrees is sufficient here.
_ISO6709_RE = re.compile(
    rb"([+-]\d{1,3}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?"
)

# Seconds between 1904-01-01 (QuickTime epoch) and 1970-01-01 (Unix epoch).
_QT_EPOCH = datetime(1904, 1, 1)


# ---------------------------------------------------------------------------
# Format classification
# ---------------------------------------------------------------------------

def is_video_format(filepath: str) -> bool:
    """Return True if *filepath* has a recognized video extension."""
    return Path(filepath).suffix.lower() in VIDEO_EXTENSIONS


def get_video_extensions() -> list:
    """Video extensions in both cases (mirrors get_supported_extensions)."""
    extensions = []
    for ext in sorted(VIDEO_EXTENSIONS):
        extensions.append(ext)
        extensions.append(ext.upper())
    return extensions


def video_mime_for(filepath: str) -> str:
    """Best-guess MIME type for a video path; defaults to video/mp4."""
    return _VIDEO_MIME.get(Path(filepath).suffix.lower(), "video/mp4")


def is_supported_media(filepath: str) -> bool:
    """True for any supported photo OR video file."""
    return is_supported_format(filepath) or is_video_format(filepath)


def get_supported_media_extensions() -> list:
    """All supported photo + video extensions (for file-dialog patterns)."""
    return get_supported_extensions() + get_video_extensions()


# ---------------------------------------------------------------------------
# ISO-6709 parsing
# ---------------------------------------------------------------------------

def parse_iso6709(value: str) -> Optional[GPSCoordinates]:
    """Parse a decimal-degree ISO-6709 string into GPSCoordinates."""
    if not value:
        return None
    match = _ISO6709_RE.search(value.encode("ascii", errors="ignore"))
    if not match:
        return None
    try:
        lat = float(match.group(1))
        lon = float(match.group(2))
    except (TypeError, ValueError):
        return None
    alt = None
    if match.group(3):
        try:
            alt = float(match.group(3))
        except (TypeError, ValueError):
            alt = None
    if lat == 0.0 and lon == 0.0:
        return None
    return GPSCoordinates(latitude=lat, longitude=lon, altitude=alt)


# ---------------------------------------------------------------------------
# ISO-BMFF box walking
# ---------------------------------------------------------------------------

def _read_moov_payload(fileobj, file_size: int) -> Optional[bytes]:
    """Seek through the top-level boxes and return the ``moov`` payload bytes.

    Reads only box headers (and the moov payload) so large files are not loaded
    into memory. Handles ``moov`` placed at either the start or the end of the
    file (iPhone writes it at the end).
    """
    offset = 0
    while offset + 8 <= file_size:
        fileobj.seek(offset)
        header = fileobj.read(8)
        if len(header) < 8:
            break
        size = int.from_bytes(header[0:4], "big")
        box_type = header[4:8]
        header_size = 8
        if size == 1:
            ext = fileobj.read(8)
            if len(ext) < 8:
                break
            size = int.from_bytes(ext, "big")
            header_size = 16
        elif size == 0:
            size = file_size - offset
        if size < header_size:
            break
        if box_type == b"moov":
            fileobj.seek(offset + header_size)
            return fileobj.read(size - header_size)
        offset += size
    return None


def _gps_from_region(region: bytes) -> Optional[GPSCoordinates]:
    """Find a GPS location inside a region of box bytes (e.g. the moov payload)."""
    if not region:
        return None

    # Primary: the ©xyz atom (size:4, type:4, strlen:2, lang:2, string).
    idx = region.find(_XYZ_MARKER)
    if idx != -1 and idx + 8 <= len(region):
        str_len = int.from_bytes(region[idx + 4:idx + 6], "big")
        start = idx + 8
        raw = region[start:start + str_len] if str_len else region[start:start + 64]
        coords = parse_iso6709(raw.decode("ascii", errors="ignore"))
        if coords:
            return coords

    # Fallback: scan for any ISO-6709 decimal string (covers the QuickTime
    # com.apple.quicktime.location.ISO6709 key without parsing keys/ilst).
    match = _ISO6709_RE.search(region)
    if match:
        return parse_iso6709(match.group(0).decode("ascii", errors="ignore"))
    return None


def _timestamp_from_moov(moov: bytes) -> Optional[datetime]:
    """Best-effort capture time from the mvhd box (QuickTime 1904 epoch)."""
    idx = moov.find(b"mvhd")
    if idx == -1:
        return None
    payload = moov[idx + 4:]
    if len(payload) < 20:
        return None
    version = payload[0]
    try:
        if version == 1:
            creation = int.from_bytes(payload[4:12], "big")
        else:
            creation = int.from_bytes(payload[4:8], "big")
    except (IndexError, ValueError):
        return None
    if creation <= 0:
        return None
    try:
        return _QT_EPOCH + timedelta(seconds=creation)
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public extraction API
# ---------------------------------------------------------------------------

def extract_video_gps(data: bytes) -> Optional[GPSCoordinates]:
    """Extract GPS from a complete (or moov-containing) video byte blob."""
    if not data:
        return None
    moov = _read_moov_payload(io.BytesIO(data), len(data))
    region = moov if moov is not None else data
    return _gps_from_region(region)


def extract_video_metadata(filepath: str) -> ImageMetadata:
    """Extract GPS + best-effort timestamp from a local video file.

    Returns an ImageMetadata so the rest of the app treats videos and photos
    uniformly. camera_make / camera_model are always None for video.
    """
    path = Path(filepath)
    gps: Optional[GPSCoordinates] = None
    timestamp: Optional[datetime] = None

    try:
        file_size = path.stat().st_size
        with open(filepath, "rb") as fileobj:
            moov = _read_moov_payload(fileobj, file_size)
        if moov:
            gps = _gps_from_region(moov)
            timestamp = _timestamp_from_moov(moov)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Error extracting video metadata from {filepath}: {exc}")

    return ImageMetadata(
        filepath=path,
        filename=path.name,
        gps=gps,
        timestamp=timestamp,
        camera_make=None,
        camera_model=None,
    )


def extract_video_metadata_from_bytes(data: bytes, virtual_path: str) -> ImageMetadata:
    """Extract video metadata from in-memory bytes (e.g. a Drive partial download).

    Best-effort: if the bytes don't contain the moov box (common when the moov
    atom lives at the end of the file and only a prefix was downloaded), GPS
    comes back None and the media falls back to manual placement.
    """
    gps = None
    try:
        gps = extract_video_gps(data)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Error extracting video metadata from bytes ({virtual_path}): {exc}")

    filename = virtual_path.rsplit("/", 1)[-1] if "/" in virtual_path else virtual_path
    return ImageMetadata(
        filepath=Path(virtual_path),
        filename=filename,
        gps=gps,
        timestamp=None,
        camera_make=None,
        camera_model=None,
    )

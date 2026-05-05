"""
Google Drive API client for PicPlotter.

Lists images from shared Google Drive folders and provides URLs
for referencing photos directly in web deployments.
Uses stdlib urllib only - no additional dependencies.
"""

from __future__ import annotations

import io
import json
import re
from typing import List, NamedTuple, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from src.config import get_ssl_context


class DriveFileInfo(NamedTuple):
    """Metadata for a file in a Google Drive folder."""
    file_id: str
    name: str
    mime_type: str
    size: int


class ImageMetadataFromDrive(NamedTuple):
    """GPS and camera metadata extracted from a Drive image."""
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    timestamp: Optional[str]
    camera_make: Optional[str]
    camera_model: Optional[str]


# ---------------------------------------------------------------------------
# URL Parsing
# ---------------------------------------------------------------------------

_FOLDER_PATTERNS = [
    # https://drive.google.com/drive/folders/{id}?...
    re.compile(r"drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)"),
    # https://drive.google.com/open?id={id}
    re.compile(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)"),
    # Just a raw folder ID (alphanumeric + dashes/underscores, 20+ chars)
    re.compile(r"^([a-zA-Z0-9_-]{20,})$"),
]


def parse_drive_folder_url(url: str) -> Optional[str]:
    """Extract a Google Drive folder ID from a sharing URL or raw ID.

    Returns the folder ID string, or None if not recognised.
    """
    url = url.strip()
    if not url:
        return None
    for pattern in _FOLDER_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


# ---------------------------------------------------------------------------
# Drive API helpers
# ---------------------------------------------------------------------------

_DRIVE_API = "https://www.googleapis.com/drive/v3"
_IMAGE_MIME_QUERY = (
    "(mimeType contains 'image/jpeg' or "
    "mimeType contains 'image/png' or "
    "mimeType contains 'image/heic' or "
    "mimeType contains 'image/heif' or "
    "mimeType contains 'image/tiff' or "
    "mimeType contains 'image/webp')"
)


def _drive_request(
    url: str,
    api_key: Optional[str] = None,
    headers: Optional[dict] = None,
    access_token: Optional[str] = None,
) -> bytes:
    """Make an authenticated GET request to the Drive API.

    Uses Bearer token auth if *access_token* is provided, otherwise API key.
    """
    if headers is None:
        headers = {}
    if access_token:
        full_url = url
        headers["Authorization"] = f"Bearer {access_token}"
    elif api_key:
        sep = "&" if "?" in url else "?"
        full_url = f"{url}{sep}key={quote(api_key)}"
    else:
        raise ValueError("Either api_key or access_token must be provided")
    req = Request(full_url)
    for k, v in headers.items():
        req.add_header(k, v)
    with urlopen(req, timeout=30, context=get_ssl_context()) as resp:
        return resp.read()


def validate_folder_access(
    folder_id: str,
    api_key: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Tuple[bool, str]:
    """Test whether the API key / token can list files in the given folder.

    Returns (success, message).
    """
    params = urlencode({
        "q": f"'{folder_id}' in parents and trashed = false",
        "pageSize": "1",
        "fields": "files(id)",
    })
    url = f"{_DRIVE_API}/files?{params}"
    try:
        _drive_request(url, api_key=api_key, access_token=access_token)
        return True, "OK"
    except HTTPError as exc:
        if exc.code == 404:
            return False, "Folder not found. Check the URL and sharing settings."
        if exc.code == 403:
            body = exc.read().decode("utf-8", errors="replace")
            if "Drive API" in body or "accessNotConfigured" in body:
                return False, (
                    "Google Drive API is not enabled on your Cloud project. "
                    "Enable it at console.cloud.google.com, then retry."
                )
            return False, (
                "Access denied. Ensure the folder is shared as "
                "'Anyone with the link' and your API key allows the Drive API."
            )
        if exc.code == 400:
            return False, "Invalid API key or request. Check your Google Maps API key."
        return False, f"Drive API error {exc.code}: {exc.reason}"
    except URLError as exc:
        return False, f"Network error: {exc.reason}"


def list_folder_images(
    folder_id: str,
    api_key: Optional[str] = None,
    page_size: int = 100,
    access_token: Optional[str] = None,
) -> List[DriveFileInfo]:
    """List image files inside a Google Drive folder (handles pagination)."""
    files: List[DriveFileInfo] = []
    page_token: Optional[str] = None

    while True:
        params: dict = {
            "q": f"'{folder_id}' in parents and {_IMAGE_MIME_QUERY} and trashed = false",
            "pageSize": str(page_size),
            "fields": "nextPageToken,files(id,name,mimeType,size)",
            "orderBy": "name",
        }
        if page_token:
            params["pageToken"] = page_token

        url = f"{_DRIVE_API}/files?{urlencode(params)}"
        data = json.loads(_drive_request(url, api_key=api_key, access_token=access_token))

        for entry in data.get("files", []):
            files.append(DriveFileInfo(
                file_id=entry["id"],
                name=entry["name"],
                mime_type=entry.get("mimeType", "image/jpeg"),
                size=int(entry.get("size", 0)),
            ))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return files


# ---------------------------------------------------------------------------
# Image URLs (for public / "anyone with link" shared files)
# ---------------------------------------------------------------------------

def get_image_url(file_id: str, size: int = 1920) -> str:
    """Return a public thumbnail URL for a shared Drive file.

    Works without auth for files shared as 'Anyone with the link'.
    """
    return f"https://drive.google.com/thumbnail?id={quote(file_id)}&sz=w{size}"


def get_thumbnail_url(file_id: str, size: int = 450) -> str:
    """Return a smaller thumbnail URL suitable for previews."""
    return get_image_url(file_id, size)


# ---------------------------------------------------------------------------
# Direct file download (for local/KMZ exports)
# ---------------------------------------------------------------------------

def fetch_image_bytes(
    file_id: str,
    api_key: Optional[str] = None,
    max_bytes: Optional[int] = None,
    access_token: Optional[str] = None,
) -> bytes:
    """Download file content from Drive via the API (alt=media).

    If *max_bytes* is set, only the first N bytes are fetched (Range header).
    Useful for partial EXIF extraction.
    """
    url = f"{_DRIVE_API}/files/{quote(file_id)}?alt=media"
    headers: dict = {}
    if max_bytes is not None:
        headers["Range"] = f"bytes=0-{max_bytes - 1}"
    return _drive_request(url, api_key=api_key, headers=headers, access_token=access_token)


# ---------------------------------------------------------------------------
# Metadata extraction via Drive API imageMediaMetadata
# ---------------------------------------------------------------------------

def get_drive_image_metadata(
    file_id: str,
    api_key: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Optional[ImageMetadataFromDrive]:
    """Try to get GPS/camera metadata from the Drive API's imageMediaMetadata.

    Returns None if the field is unavailable (common for shared files).
    """
    params = urlencode({
        "fields": "imageMediaMetadata",
    })
    url = f"{_DRIVE_API}/files/{quote(file_id)}?{params}"
    try:
        data = json.loads(_drive_request(url, api_key=api_key, access_token=access_token))
    except (HTTPError, URLError):
        return None

    meta = data.get("imageMediaMetadata")
    if not meta:
        return None

    location = meta.get("location")
    lat = location.get("latitude") if location else None
    lng = location.get("longitude") if location else None
    alt = location.get("altitude") if location else None

    return ImageMetadataFromDrive(
        latitude=lat,
        longitude=lng,
        altitude=alt,
        timestamp=meta.get("time"),
        camera_make=meta.get("cameraMake"),
        camera_model=meta.get("cameraModel"),
    )


# ---------------------------------------------------------------------------
# EXIF extraction from partial download
# ---------------------------------------------------------------------------

def extract_metadata_from_drive(
    file_id: str,
    filename: str,
    api_key: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Optional[ImageMetadataFromDrive]:
    """Extract EXIF metadata by downloading the first ~128KB of the file.

    Falls back gracefully if the image cannot be parsed.
    """
    try:
        from PIL import Image
        from src.exif_extractor import get_image_metadata_from_bytes

        partial = fetch_image_bytes(file_id, api_key=api_key, max_bytes=131072, access_token=access_token)
        meta = get_image_metadata_from_bytes(partial, f"gdrive://{file_id}/{filename}")

        lat = meta.gps.latitude if meta.gps else None
        lng = meta.gps.longitude if meta.gps else None
        alt = meta.gps.altitude if meta.gps else None
        ts = meta.timestamp.isoformat() if meta.timestamp else None

        return ImageMetadataFromDrive(
            latitude=lat,
            longitude=lng,
            altitude=alt,
            timestamp=ts,
            camera_make=meta.camera_make,
            camera_model=meta.camera_model,
        )
    except Exception:
        return None

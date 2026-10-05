"""
Configuration helpers for PicPlotter Auto.

Centralizes configuration, constants, and shared utilities.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, UnidentifiedImageError


# =============================================================================
# Application Constants
# =============================================================================

# Map tile constants
TILE_SIZE = 256
DEFAULT_ZOOM = 19

# Export constants
EXPORT_MAX_DIM = 2048
DEFAULT_COMPRESSION_QUALITY = 85
DEFAULT_MAX_IMAGE_DIMENSION = 1920
DEFAULT_MARKER_SIZE = 96

# =============================================================================
# Configuration Paths
# =============================================================================

CONFIG_DIR = Path.home() / ".picplotter_auto"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOGO_FILE = CONFIG_DIR / "logo.png"
LOGO_MAX_LONG_EDGE = 512
API_KEY_FIELD = "google_maps_api_key"
NETLIFY_TOKEN_FIELD = "netlify_token"
OAUTH_CLIENT_ID_FIELD = "google_oauth_client_id"
OAUTH_CLIENT_SECRET_FIELD = "google_oauth_client_secret"
OAUTH_REFRESH_TOKEN_FIELD = "google_oauth_refresh_token"
COMPANY_NAME_FIELD = "company_name"
COMPANY_ADDRESS_FIELD = "company_address"
COMPANY_PHONE_FIELD = "company_phone"
COMPANY_WEBSITE_FIELD = "company_website"


# =============================================================================
# SSL Context (HTTPS for urllib)
# =============================================================================

_ssl_context = None


def get_ssl_context():
    """Return a cached SSL context backed by certifi when available.

    PyInstaller .app bundles on macOS don't have access to the system trust
    store, so urllib's default context fails CERTIFICATE_VERIFY_FAILED. Using
    certifi's CA bundle works in both bundled and from-source runs.
    """
    global _ssl_context
    if _ssl_context is not None:
        return _ssl_context
    import ssl
    try:
        import certifi
        _ssl_context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        _ssl_context = ssl.create_default_context()
    return _ssl_context


# =============================================================================
# Asset Path Helper
# =============================================================================

def get_asset_path(filename: str) -> Path:
    """
    Get path to asset file, handling both development and PyInstaller bundled scenarios.

    Args:
        filename: Name of the asset file (e.g., 'marker_pin.png')

    Returns:
        Path to the asset file
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        base_path = Path(sys._MEIPASS)
    else:
        # Running from source
        base_path = Path(__file__).parent.parent
    return base_path / "assets" / filename


# =============================================================================
# Config File Management
# =============================================================================


def _load_config() -> Dict[str, Any]:
    """Load config from disk, returning an empty dict if missing or invalid."""
    try:
        if not CONFIG_FILE.exists():
            return {}
        with CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(data: Dict[str, Any]) -> None:
    """Persist config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def get_google_maps_api_key() -> Optional[str]:
    """Return API key from env or config, if available."""
    env_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if env_key:
        env_key = env_key.strip()
        if env_key:
            return env_key

    data = _load_config()
    key = data.get(API_KEY_FIELD)
    return key.strip() if isinstance(key, str) else None


def set_google_maps_api_key(value: str) -> None:
    """Save the Google Maps API key to config."""
    data = _load_config()
    cleaned = value.strip()
    if cleaned:
        data[API_KEY_FIELD] = cleaned
    else:
        data.pop(API_KEY_FIELD, None)
    _save_config(data)


def get_netlify_token() -> Optional[str]:
    """Return Netlify token from config, if available."""
    data = _load_config()
    token = data.get(NETLIFY_TOKEN_FIELD)
    return token.strip() if isinstance(token, str) else None


def set_netlify_token(value: str) -> None:
    """Save the Netlify token to config."""
    data = _load_config()
    cleaned = value.strip()
    if cleaned:
        data[NETLIFY_TOKEN_FIELD] = cleaned
    else:
        data.pop(NETLIFY_TOKEN_FIELD, None)
    _save_config(data)


def get_oauth_client_id() -> Optional[str]:
    """Return Google OAuth Client ID from config, if available."""
    data = _load_config()
    client_id = data.get(OAUTH_CLIENT_ID_FIELD)
    return client_id.strip() if isinstance(client_id, str) else None


def set_oauth_client_id(value: str) -> None:
    """Save the Google OAuth Client ID to config."""
    data = _load_config()
    cleaned = value.strip()
    if cleaned:
        data[OAUTH_CLIENT_ID_FIELD] = cleaned
    else:
        data.pop(OAUTH_CLIENT_ID_FIELD, None)
    _save_config(data)


def get_oauth_client_secret() -> Optional[str]:
    """Return Google OAuth Client Secret from config, if available."""
    data = _load_config()
    secret = data.get(OAUTH_CLIENT_SECRET_FIELD)
    return secret.strip() if isinstance(secret, str) else None


def set_oauth_client_secret(value: str) -> None:
    """Save the Google OAuth Client Secret to config."""
    data = _load_config()
    cleaned = value.strip()
    if cleaned:
        data[OAUTH_CLIENT_SECRET_FIELD] = cleaned
    else:
        data.pop(OAUTH_CLIENT_SECRET_FIELD, None)
    _save_config(data)


def get_oauth_refresh_token() -> Optional[str]:
    """Return stored OAuth refresh token, if available."""
    data = _load_config()
    token = data.get(OAUTH_REFRESH_TOKEN_FIELD)
    return token.strip() if isinstance(token, str) else None


def set_oauth_refresh_token(value: str) -> None:
    """Save or clear the OAuth refresh token."""
    data = _load_config()
    cleaned = value.strip() if value else ""
    if cleaned:
        data[OAUTH_REFRESH_TOKEN_FIELD] = cleaned
    else:
        data.pop(OAUTH_REFRESH_TOKEN_FIELD, None)
    _save_config(data)


# =============================================================================
# Project Management
# =============================================================================

PROJECTS_DIR = CONFIG_DIR / "projects"


def list_projects() -> list[str]:
    """Return sorted list of saved project names."""
    if not PROJECTS_DIR.exists():
        return []
    names = []
    for f in PROJECTS_DIR.iterdir():
        if f.suffix == ".json" and f.is_file():
            names.append(f.stem)
    names.sort(key=str.lower)
    return names


def save_project(name: str, data: Dict[str, Any]) -> None:
    """Save project data to a JSON file."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PROJECTS_DIR / f"{name}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def load_project(name: str) -> Optional[Dict[str, Any]]:
    """Load project data by name. Returns None if not found."""
    path = PROJECTS_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def delete_project(name: str) -> bool:
    """Delete a saved project. Returns True if deleted."""
    path = PROJECTS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


# =============================================================================
# Branding (user logo + company info)
# =============================================================================


def get_user_logo_path() -> Optional[Path]:
    """Return path to user-uploaded logo if present, else None."""
    return LOGO_FILE if LOGO_FILE.exists() else None


def set_user_logo_from_bytes(data: bytes) -> None:
    """
    Save an uploaded logo as a normalized PNG at LOGO_FILE.

    Accepts JPG/PNG only. Downscales so the longer edge is <= 512px,
    preserving aspect ratio. Raises ValueError on unsupported format
    or unreadable image.
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Logo must be a JPG or PNG image") from exc

    fmt = (img.format or "").upper()
    if fmt not in ("JPEG", "JPG", "PNG"):
        raise ValueError("Logo must be a JPG or PNG image")

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

    long_edge = max(img.size)
    if long_edge > LOGO_MAX_LONG_EDGE:
        scale = LOGO_MAX_LONG_EDGE / long_edge
        new_size = (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    img.save(LOGO_FILE, format="PNG")


def clear_user_logo() -> None:
    """Delete the user-uploaded logo, reverting to bundled default."""
    if LOGO_FILE.exists():
        LOGO_FILE.unlink()


def _normalize_website(value: str) -> str:
    """
    Normalize a website string for storage.

    - Trims whitespace.
    - If non-empty and lacks a scheme, prepends 'https://'.
    - Preserves explicit 'http://'.
    - Returns the value as-is (without scheme) when no '.' is present;
      callers render such values as plain text rather than as a link.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    has_scheme = lowered.startswith("http://") or lowered.startswith("https://")
    has_dot = "." in cleaned
    if not has_scheme and has_dot:
        return f"https://{cleaned}"
    return cleaned


def get_company_info() -> Dict[str, str]:
    """Return saved company info as a dict with all four keys (empty strings if unset)."""
    data = _load_config()
    return {
        "company_name": str(data.get(COMPANY_NAME_FIELD, "") or ""),
        "company_address": str(data.get(COMPANY_ADDRESS_FIELD, "") or ""),
        "company_phone": str(data.get(COMPANY_PHONE_FIELD, "") or ""),
        "company_website": str(data.get(COMPANY_WEBSITE_FIELD, "") or ""),
    }


def set_company_info(
    name: str = "",
    address: str = "",
    phone: str = "",
    website: str = "",
) -> None:
    """Save company info to config. Empty values clear the corresponding field."""
    data = _load_config()
    fields = {
        COMPANY_NAME_FIELD: (name or "").strip(),
        COMPANY_ADDRESS_FIELD: (address or "").strip(),
        COMPANY_PHONE_FIELD: (phone or "").strip(),
        COMPANY_WEBSITE_FIELD: _normalize_website(website),
    }
    for key, value in fields.items():
        if value:
            data[key] = value
        else:
            data.pop(key, None)
    _save_config(data)

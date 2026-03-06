"""
Configuration helpers for PicPlotter Auto.

Centralizes configuration, constants, and shared utilities.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


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
API_KEY_FIELD = "google_maps_api_key"
NETLIFY_TOKEN_FIELD = "netlify_token"
NETLIFY_SITE_ID_FIELD = "netlify_site_id"
OAUTH_CLIENT_ID_FIELD = "google_oauth_client_id"


# =============================================================================
# Asset Path Helper
# =============================================================================

def get_asset_path(filename: str) -> Path:
    """
    Get path to asset file, handling both development and PyInstaller bundled scenarios.

    Args:
        filename: Name of the asset file (e.g., 'marker_outlined_transparent.png')

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
    """Save the Netlify token to config. Clears site_id when token is cleared."""
    data = _load_config()
    cleaned = value.strip()
    if cleaned:
        data[NETLIFY_TOKEN_FIELD] = cleaned
    else:
        data.pop(NETLIFY_TOKEN_FIELD, None)
        data.pop(NETLIFY_SITE_ID_FIELD, None)
    _save_config(data)


def get_netlify_site_id() -> Optional[str]:
    """Return Netlify site ID from config, if available."""
    data = _load_config()
    site_id = data.get(NETLIFY_SITE_ID_FIELD)
    return site_id.strip() if isinstance(site_id, str) else None


def set_netlify_site_id(value: str) -> None:
    """Save the Netlify site ID to config."""
    data = _load_config()
    cleaned = value.strip()
    if cleaned:
        data[NETLIFY_SITE_ID_FIELD] = cleaned
    else:
        data.pop(NETLIFY_SITE_ID_FIELD, None)
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

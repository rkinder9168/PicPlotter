"""
PicPlotter Auto - Single-window pywebview application.

Provides a main dashboard and embedded map editor in one HTML UI.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import io
import json
import math
import secrets
import threading
import uuid
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote, urlencode, parse_qs, urlparse
from urllib.request import Request, urlopen

import webview
from PIL import Image, ImageOps

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import (
    CONFIG_DIR,
    EXPORT_MAX_DIM,
    TILE_SIZE,
    get_asset_path,
    get_ssl_context,
    get_google_maps_api_key,
    set_google_maps_api_key,
    get_netlify_token,
    set_netlify_token,
    get_oauth_client_id,
    set_oauth_client_id,
    get_oauth_client_secret,
    set_oauth_client_secret,
    get_oauth_refresh_token,
    set_oauth_refresh_token,
    list_projects as _list_projects,
    save_project as _save_project,
    load_project as _load_project,
    delete_project as _delete_project,
    get_user_logo_path,
    set_user_logo_from_bytes,
    clear_user_logo,
    get_company_info,
    set_company_info,
)
from src.netlify_deployer import NetlifyDeployer, verify_token as verify_netlify_token
from src.exif_extractor import (
    get_image_metadata,
    get_image_metadata_from_bytes,
    HEIC_SUPPORTED,
    GPSCoordinates,
    ImageMetadata,
)
from src.google_drive import (
    parse_drive_folder_url,
    validate_folder_access,
    list_folder_images,
    get_image_url,
    get_thumbnail_url,
    get_video_embed_url,
    fetch_image_bytes,
    get_drive_image_metadata,
    extract_metadata_from_drive,
)
from src.video_metadata import (
    is_video_format,
    is_supported_media,
    get_supported_media_extensions,
    video_mime_for,
    extract_video_metadata,
)
from src.html_map_generator import (
    HTMLMapGenerator,
    get_window_icon_path,
    set_window_icon,
)
from src.image_processor import ImageProcessor
from src.kmz_generator import create_kmz_from_files
from src.marker_utils import get_colorizer, reset_colorizer
from src.photo_groups import GroupAssignments, DEFAULT_GROUPS, PRESET_COLORS, PhotoGroup
from src.photo_pages import (
    DEFAULT_PAGE_ID,
    MAP_SOURCE_CUSTOM,
    MAP_SOURCE_TILES,
    PageAssignments,
    PageEditorState,
    PhotoPage,
)
from src.utils import get_default_output_path, open_file_in_default_app, open_folder_containing
from src.coordinate_transform import PixelPoint


TILE_HOSTS = ("mt0.google.com", "mt1.google.com", "mt2.google.com", "mt3.google.com")
TILE_URL = "https://{host}/vt/lyrs=s&x={x}&y={y}&z={z}"
DEFAULT_GROUP_IDS = {group["id"] for group in DEFAULT_GROUPS}
UI_MARKER_ICON_SIZE = 256
PHOTO_PREVIEW_MAX_DIM = 450
PHOTO_PREVIEW_QUALITY = 70

# Inline SVG ▶ placeholder shown in the editor for local videos (Drive videos use
# Drive's real auto-generated thumbnail). Inline so nothing extra needs bundling.
_VIDEO_PLACEHOLDER_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='160' height='120' viewBox='0 0 160 120'>"
    "<rect width='160' height='120' rx='10' fill='#1f2937'/>"
    "<circle cx='80' cy='60' r='28' fill='rgba(255,255,255,0.18)'/>"
    "<path d='M70 44 L70 76 L98 60 Z' fill='#ffffff'/></svg>"
)
_VIDEO_PLACEHOLDER_URI = "data:image/svg+xml," + quote(_VIDEO_PLACEHOLDER_SVG)


def _get_local_media_metadata(filepath: str) -> ImageMetadata:
    """Extract metadata from a local file, dispatching video vs photo."""
    if is_video_format(filepath):
        return extract_video_metadata(filepath)
    return get_image_metadata(filepath)


@dataclass
class AppState:
    selected_files: List[str]
    file_metadata: Dict[str, ImageMetadata]
    gps_overrides: Dict[str, GPSCoordinates]
    custom_map_path: Optional[str]
    custom_marker_overrides: Dict[str, PixelPoint]
    custom_autoplot_enabled: bool
    marker_size: int
    heading: int
    custom_heading: int
    output_folder: Optional[str]
    overrides_path: Path
    group_assignments: GroupAssignments
    page_assignments: PageAssignments
    assignment_mode: str
    photo_aliases: Dict[str, str]
    group_aliases: Dict[str, str]
    photo_notes: Dict[str, str]
    photo_previews: Dict[str, str]
    drive_sources: Dict[str, str]       # virtual_path -> file_id
    drive_folder_url: Optional[str]     # currently imported folder URL
    drive_access_token: Optional[str]   # OAuth access token for private folders
    current_project_name: Optional[str] = None  # name of the saved project currently loaded, if any
    netlify_site_id: Optional[str] = None       # Netlify site for the active project (per-project URL)
    netlify_deploy_url: Optional[str] = None    # last deploy URL for the active project
    hide_markers: bool = False                  # deployed image: invisible (but clickable) markers, no number badge
    hide_sidebar: bool = False                  # deployed single-page image: drop the sidebar (full-bleed map)


class AppApi:
    def __init__(self, state: AppState):
        self._state = state
        self._window: Optional[webview.Window] = None
        self._kmz_thread: Optional[threading.Thread] = None
        self._kmz_lock = threading.Lock()

    def attach_window(self, window: webview.Window) -> None:
        self._window = window

    def save_api_key(self, value: str) -> bool:
        set_google_maps_api_key(value)
        return True

    # ── Project management ──────────────────────────────────────────

    def get_projects(self) -> Dict[str, Any]:
        return {"status": "ok", "projects": _list_projects()}

    def save_project(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = (payload.get("name") or "").strip()
        if not name:
            return {"status": "error", "message": "Project name is required."}
        existing = _load_project(name) or {}
        # If renaming away from the previously loaded project, the new file starts fresh —
        # otherwise carry the live state's site so the per-project URL survives the save.
        if self._state.current_project_name and self._state.current_project_name != name:
            preserved_site_id = None
            preserved_deploy_url = None
        else:
            preserved_site_id = self._state.netlify_site_id or existing.get("netlify_site_id")
            preserved_deploy_url = self._state.netlify_deploy_url or existing.get("netlify_deploy_url")
        overrides_payload = _serialize_overrides_state(self._state)
        data = {
            "project_name": payload.get("project_name", ""),
            "proposal_link": payload.get("proposal_link", ""),
            "download_photos_link": payload.get("download_photos_link", ""),
            "client_name": payload.get("client_name", ""),
            "client_company": payload.get("client_company", ""),
            "client_address": payload.get("client_address", ""),
            "quality": payload.get("quality", 30),
            "output_folder": self._state.output_folder,
            "drive_folder_url": self._state.drive_folder_url,
            "selected_files": list(self._state.selected_files),
            "drive_sources": dict(self._state.drive_sources),
            **overrides_payload,
            "netlify_site_id": preserved_site_id,
            "netlify_deploy_url": preserved_deploy_url,
        }
        _save_project(name, data)
        self._state.current_project_name = name
        self._state.netlify_site_id = preserved_site_id
        self._state.netlify_deploy_url = preserved_deploy_url
        return {
            "status": "ok",
            "projects": _list_projects(),
            "deploy_url": preserved_deploy_url or "",
        }

    def load_project(self, name: str) -> Dict[str, Any]:
        if not name:
            return {"status": "error", "message": "No project selected."}
        data = _load_project(name)
        if data is None:
            return {"status": "error", "message": f"Project '{name}' not found."}

        # Start from a clean slate so nothing from the previous project leaks in
        # (e.g. custom_map_path, per-page editor state) when the saved JSON
        # doesn't carry that field.
        self._reset_state_for_new_project()

        output_folder = data.get("output_folder")
        if output_folder:
            self._state.output_folder = output_folder

        # Re-import saved photos
        errors: List[str] = []
        loaded_local = 0
        loaded_drive = 0

        self._state.drive_folder_url = data.get("drive_folder_url")

        drive_sources = data.get("drive_sources", {})
        api_key = get_google_maps_api_key() if drive_sources else None

        # Walk selected_files in saved order to preserve sequence
        saved_files = data.get("selected_files", [])
        # Backwards compat: fall back to local_files + drive_sources keys
        if not saved_files:
            saved_files = list(data.get("local_files", []))
            saved_files.extend(drive_sources.keys())

        for filepath in saved_files:
            file_id = drive_sources.get(filepath)
            if file_id:
                # Drive file
                filename = filepath.split("/", 1)[-1] if "/" in filepath else file_id
                try:
                    drive_meta = get_drive_image_metadata(file_id, api_key=api_key)
                    if drive_meta and drive_meta.latitude is not None:
                        from datetime import datetime
                        gps = GPSCoordinates(
                            latitude=drive_meta.latitude,
                            longitude=drive_meta.longitude,
                            altitude=drive_meta.altitude,
                        )
                        ts = None
                        if drive_meta.timestamp:
                            try:
                                ts = datetime.fromisoformat(drive_meta.timestamp)
                            except (ValueError, TypeError):
                                pass
                        meta = ImageMetadata(
                            filepath=Path(filepath),
                            filename=filename,
                            gps=gps, timestamp=ts,
                            camera_make=drive_meta.camera_make,
                            camera_model=drive_meta.camera_model,
                        )
                    else:
                        meta = ImageMetadata(
                            filepath=Path(filepath), filename=filename,
                            gps=None, timestamp=None,
                            camera_make=None, camera_model=None,
                        )
                    self._state.selected_files.append(filepath)
                    self._state.file_metadata[filepath] = meta
                    self._state.drive_sources[filepath] = file_id
                    loaded_drive += 1
                except Exception as exc:
                    errors.append(f"{filename}: {exc}")
            else:
                # Local file
                if not Path(filepath).exists():
                    errors.append(f"{Path(filepath).name}: file not found")
                    continue
                if not is_supported_media(filepath):
                    continue
                try:
                    metadata = _get_local_media_metadata(filepath)
                except Exception as exc:
                    errors.append(f"{Path(filepath).name}: {exc}")
                    continue
                self._state.file_metadata[filepath] = metadata
                self._state.selected_files.append(filepath)
                loaded_local += 1

        # Always replay the saved overrides so group-mode top-level state
        # (custom_map_path, marker placements, headings, autoplot flag) is
        # restored — _reset_state_for_new_project() above wiped it.
        _apply_overrides(self._state, data)
        self._sync_group_assignments()
        self._sync_page_assignments()

        self._state.current_project_name = name
        site_id = data.get("netlify_site_id")
        deploy_url = data.get("netlify_deploy_url")
        self._state.netlify_site_id = site_id if isinstance(site_id, str) and site_id else None
        self._state.netlify_deploy_url = deploy_url if isinstance(deploy_url, str) and deploy_url else None

        response: Dict[str, Any] = {
            "status": "ok",
            "data": data,
            "photos": self._build_photo_list(),
            "loaded_local": loaded_local,
            "loaded_drive": loaded_drive,
            "deploy_url": self._state.netlify_deploy_url or "",
        }
        if errors:
            response["warnings"] = errors[:5]
        return response

    def delete_project(self, name: str) -> Dict[str, Any]:
        if not name:
            return {"status": "error", "message": "No project selected."}
        deleted = _delete_project(name)
        if not deleted:
            return {"status": "error", "message": f"Project '{name}' not found."}
        if self._state.current_project_name == name:
            self._state.current_project_name = None
            self._state.netlify_site_id = None
            self._state.netlify_deploy_url = None
        return {"status": "ok", "projects": _list_projects()}

    # ────────────────────────────────────────────────────────────────

    def save_oauth_client_id(self, value: str) -> bool:
        set_oauth_client_id(value)
        return True

    def save_oauth_client_secret(self, value: str) -> bool:
        set_oauth_client_secret(value)
        return True

    def try_refresh_token(self) -> Dict[str, Any]:
        """Try to get a new access token using a stored refresh token."""
        client_id = get_oauth_client_id()
        client_secret = get_oauth_client_secret()
        refresh_token = get_oauth_refresh_token()
        if not all([client_id, client_secret, refresh_token]):
            return {"status": "error", "message": "No saved session."}

        try:
            data = urlencode({
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }).encode()
            req = Request("https://oauth2.googleapis.com/token", data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urlopen(req, timeout=10, context=get_ssl_context()) as resp:
                result = json.loads(resp.read().decode())
            access_token = result.get("access_token")
            if access_token:
                return {"status": "ok", "access_token": access_token}
            return {"status": "error", "message": "No access token in refresh response."}
        except Exception as exc:
            # Clear refresh token if Google rejected it (revoked/expired)
            from urllib.error import HTTPError
            if isinstance(exc, HTTPError) and exc.code in (400, 401):
                set_oauth_refresh_token("")
            return {"status": "error", "message": "Session expired. Please sign in again."}

    def start_oauth_flow(self) -> Dict[str, Any]:
        """Open system browser for Google OAuth authorization code flow with PKCE."""
        client_id = get_oauth_client_id()
        if not client_id:
            return {"status": "error", "message": "Set your OAuth Client ID in Settings first."}
        client_secret = get_oauth_client_secret()
        if not client_secret:
            return {"status": "error", "message": "Set your OAuth Client Secret in Settings first."}

        # Generate PKCE code verifier and challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()

        auth_code_result: Dict[str, Any] = {"status": "error", "message": "Authentication timed out."}
        server_ready = threading.Event()

        class OAuthHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                # Extract authorization code from query string
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                error = params.get("error", [None])[0]

                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()

                if code:
                    auth_code_result["status"] = "ok"
                    auth_code_result["code"] = code
                    self.wfile.write(b"<html><body><h2>Sign-in complete. You can close this tab.</h2></body></html>")
                elif error:
                    auth_code_result["message"] = f"Authorization denied: {error}"
                    self.wfile.write(b"<html><body><h2>Sign-in failed. Please close this tab and try again.</h2></body></html>")
                else:
                    self.wfile.write(b"<html><body><h2>Sign-in failed. Please close this tab and try again.</h2></body></html>")

                threading.Thread(target=self.server.shutdown, daemon=True).start()

            def log_message(self, format, *args):
                pass

        try:
            server = http.server.HTTPServer(("127.0.0.1", 24817), OAuthHandler)
        except OSError:
            return {"status": "error", "message": "OAuth callback port 24817 is in use. Close any previous sign-in tabs and try again."}
        redirect_uri = "http://127.0.0.1:24817"

        def run_server():
            server_ready.set()
            server.serve_forever()

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        server_ready.wait()

        auth_params = urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/drive.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        })
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{auth_params}"
        webbrowser.open(auth_url)

        server_thread.join(timeout=120)
        server.server_close()

        if auth_code_result["status"] != "ok" or "code" not in auth_code_result:
            return {"status": "error", "message": auth_code_result.get("message", "Authentication failed.")}

        # Exchange authorization code for tokens
        try:
            exchange_data = urlencode({
                "code": auth_code_result["code"],
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            }).encode()
            req = Request("https://oauth2.googleapis.com/token", data=exchange_data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urlopen(req, timeout=15, context=get_ssl_context()) as resp:
                tokens = json.loads(resp.read().decode())
        except Exception as exc:
            return {"status": "error", "message": f"Token exchange failed: {exc}"}

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        if not access_token:
            return {"status": "error", "message": "No access token received from Google."}

        if refresh_token:
            set_oauth_refresh_token(refresh_token)

        return {"status": "ok", "access_token": access_token}

    def save_netlify_token(self, value: str) -> Dict[str, Any]:
        """Save Netlify token and verify it."""
        if not value or not value.strip():
            set_netlify_token("")
            return {"status": "ok", "message": "Token cleared"}

        is_valid, message = verify_netlify_token(value.strip())
        if is_valid:
            set_netlify_token(value.strip())
            return {"status": "ok", "message": message}
        return {"status": "error", "message": message}

    def get_netlify_token(self) -> str:
        """Return the saved Netlify token."""
        return get_netlify_token() or ""

    def select_photos(self) -> Dict[str, Any]:
        if not self._window:
            return {"status": "error", "message": "Window not ready"}

        patterns = ";".join(f"*{ext}" for ext in get_supported_media_extensions())
        file_types = [
            # pywebview validates each filter as `^[\w ]+\(...\)$` — the description
            # must be word chars + spaces only (no '&', '/', etc.) or
            # create_file_dialog raises and the dialog never opens.
            f"Media files ({patterns})",
            "All files (*.*)",
        ]

        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=file_types,
            )
        except Exception as exc:
            return {"status": "error", "message": f"File dialog failed: {exc}"}

        if not result:
            return {"status": "cancel", "photos": self._build_photo_list()}

        errors: List[str] = []
        for filepath in result:
            if filepath in self._state.selected_files:
                continue
            if not is_supported_media(filepath):
                continue
            try:
                metadata = _get_local_media_metadata(filepath)
            except Exception as exc:
                errors.append(f"{Path(filepath).name}: {exc}")
                continue
            self._state.file_metadata[filepath] = metadata
            self._state.selected_files.append(filepath)

        self._sync_group_assignments()
        self._sync_page_assignments()

        if not self._state.selected_files and errors:
            message = "No supported photos or videos loaded."
            message = f"{message} {errors[0]}" if errors else message
            return {"status": "error", "message": message}

        response = {"status": "ok", "photos": self._build_photo_list()}
        if errors:
            response["warnings"] = errors[:3]
        return response

    def import_from_drive(self, folder_url: str) -> Dict[str, Any]:
        """Import photos from a shared Google Drive folder (URL paste)."""
        if not folder_url or not isinstance(folder_url, str):
            return {"status": "error", "message": "Please enter a Google Drive folder URL."}

        folder_id = parse_drive_folder_url(folder_url)
        if not folder_id:
            return {"status": "error", "message": "Could not parse a folder ID from that URL."}

        api_key = get_google_maps_api_key()
        if not api_key:
            return {"status": "error", "message": "Please set your Google Maps API key first (it must also have Google Drive API enabled)."}

        result = self._do_drive_import(folder_id, api_key=api_key)
        if result["status"] == "ok":
            self._state.drive_folder_url = folder_url
        return result

    def import_from_drive_picker(self, folder_id: str, access_token: str) -> Dict[str, Any]:
        """Import photos from a Google Drive folder selected via Picker."""
        if not folder_id:
            return {"status": "error", "message": "No folder selected."}
        if not access_token:
            return {"status": "error", "message": "Authentication required."}

        result = self._do_drive_import(folder_id, access_token=access_token)
        if result["status"] == "ok":
            self._state.drive_access_token = access_token
            self._state.drive_folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
        return result

    def _do_drive_import(
        self,
        folder_id: str,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Shared logic for importing photos from a Drive folder."""
        ok, msg = validate_folder_access(folder_id, api_key=api_key, access_token=access_token)
        if not ok:
            return {"status": "error", "message": msg}

        try:
            drive_files = list_folder_images(folder_id, api_key=api_key, access_token=access_token)
        except Exception as exc:
            return {"status": "error", "message": f"Failed to list folder: {exc}"}

        if not drive_files:
            return {"status": "error", "message": "No image files found in that folder."}

        errors: List[str] = []

        def _extract_one(file_info):
            vpath = f"gdrive://{file_info.file_id}/{file_info.name}"
            # Try Drive API imageMediaMetadata first
            drive_meta = get_drive_image_metadata(
                file_info.file_id, api_key=api_key, access_token=access_token,
            )
            if drive_meta and drive_meta.latitude is not None:
                from datetime import datetime
                gps = GPSCoordinates(
                    latitude=drive_meta.latitude,
                    longitude=drive_meta.longitude,
                    altitude=drive_meta.altitude,
                )
                ts = None
                if drive_meta.timestamp:
                    try:
                        ts = datetime.fromisoformat(drive_meta.timestamp)
                    except (ValueError, TypeError):
                        pass
                meta = ImageMetadata(
                    filepath=Path(vpath),
                    filename=file_info.name,
                    gps=gps,
                    timestamp=ts,
                    camera_make=drive_meta.camera_make,
                    camera_model=drive_meta.camera_model,
                )
                return vpath, file_info.file_id, meta, None

            # Fall back to partial download + EXIF
            exif_meta = extract_metadata_from_drive(
                file_info.file_id, file_info.name, api_key=api_key, access_token=access_token,
            )
            if exif_meta and exif_meta.latitude is not None:
                from datetime import datetime
                gps = GPSCoordinates(
                    latitude=exif_meta.latitude,
                    longitude=exif_meta.longitude,
                    altitude=exif_meta.altitude,
                )
                ts = None
                if exif_meta.timestamp:
                    try:
                        ts = datetime.fromisoformat(exif_meta.timestamp)
                    except (ValueError, TypeError):
                        pass
                meta = ImageMetadata(
                    filepath=Path(vpath),
                    filename=file_info.name,
                    gps=gps,
                    timestamp=ts,
                    camera_make=exif_meta.camera_make,
                    camera_model=exif_meta.camera_model,
                )
                return vpath, file_info.file_id, meta, None
            else:
                # No GPS - still add the file, just without GPS
                meta = ImageMetadata(
                    filepath=Path(vpath),
                    filename=file_info.name,
                    gps=None,
                    timestamp=None,
                    camera_make=None,
                    camera_model=None,
                )
                return vpath, file_info.file_id, meta, None

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(_extract_one, f): f for f in drive_files
            }
            for future in as_completed(futures):
                file_info = futures[future]
                try:
                    vpath, file_id, meta, err = future.result()
                    if err:
                        errors.append(err)
                        continue
                    if vpath not in self._state.selected_files:
                        self._state.selected_files.append(vpath)
                    self._state.file_metadata[vpath] = meta
                    self._state.drive_sources[vpath] = file_id
                except Exception as exc:
                    errors.append(f"{file_info.name}: {exc}")

        self._sync_group_assignments()
        self._sync_page_assignments()

        if not self._state.selected_files and errors:
            return {"status": "error", "message": f"No photos imported. {errors[0] if errors else ''}"}

        response: Dict[str, Any] = {"status": "ok", "photos": self._build_photo_list()}
        if errors:
            response["warnings"] = errors[:3]
        return response

    def select_custom_map_image(self) -> Dict[str, Any]:
        if not self._window:
            return {"status": "error", "message": "Window not ready"}

        file_types = [
            "Image files (*.jpg;*.jpeg;*.png;*.tif;*.tiff)",
            "All files (*.*)",
        ]

        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=file_types,
            )
        except Exception as exc:
            return {"status": "error", "message": f"File dialog failed: {exc}"}

        if not result:
            return {"status": "cancel"}

        path = result[0]
        try:
            with Image.open(path) as image:
                width, height = image.size
        except Exception as exc:
            return {"status": "error", "message": f"Unable to read image: {exc}"}

        if self._state.custom_map_path and self._state.custom_map_path != path:
            self._state.custom_marker_overrides = {}

        self._state.custom_map_path = path
        return {
            "status": "ok",
            "path": path,
            "uri": _image_to_data_uri(path),
            "file_uri": _path_to_uri(path),
            "width": width,
            "height": height,
            "name": Path(path).name,
        }

    def select_page_custom_map_image(self, page_id: str) -> Dict[str, Any]:
        if not self._window:
            return {"status": "error", "message": "Window not ready"}
        page = self._state.page_assignments.get_page(page_id)
        if not page:
            return {"status": "error", "message": "Page not found."}

        file_types = [
            "Image files (*.jpg;*.jpeg;*.png;*.tif;*.tiff)",
            "All files (*.*)",
        ]

        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=file_types,
            )
        except Exception as exc:
            return {"status": "error", "message": f"File dialog failed: {exc}"}

        if not result:
            return {"status": "cancel"}

        path = result[0]
        try:
            with Image.open(path) as image:
                width, height = image.size
        except Exception as exc:
            return {"status": "error", "message": f"Unable to read image: {exc}"}

        editor_state = page.editor_state
        if editor_state.custom_map_path and editor_state.custom_map_path != path:
            editor_state.custom_marker_overrides = {}
        editor_state.custom_map_path = path
        editor_state.map_source = MAP_SOURCE_CUSTOM
        _apply_overrides(self._state, {})
        return {
            "status": "ok",
            "path": path,
            "uri": _image_to_data_uri(path),
            "file_uri": _path_to_uri(path),
            "width": width,
            "height": height,
            "name": Path(path).name,
        }

    def _reset_state_for_new_project(self) -> None:
        """Wipe per-project state so a new project starts from defaults.
        Persisted to map_overrides.json via the trailing _apply_overrides."""
        state = self._state
        state.selected_files = []
        state.file_metadata = {}
        state.photo_previews = {}
        state.drive_sources = {}
        state.drive_folder_url = None
        state.drive_access_token = None
        state.current_project_name = None
        state.netlify_site_id = None
        state.netlify_deploy_url = None
        state.gps_overrides = {}
        state.custom_marker_overrides = {}
        state.custom_map_path = None
        state.custom_autoplot_enabled = True
        state.hide_markers = False
        state.hide_sidebar = False
        state.heading = 0
        state.custom_heading = 0
        state.photo_aliases = {}
        state.photo_notes = {}
        state.group_aliases = {}
        state.group_assignments.clear_all()
        state.page_assignments.clear_all()
        _apply_overrides(state, {})

    def clear_photos(self) -> Dict[str, Any]:
        self._reset_state_for_new_project()
        return {
            "status": "ok",
            "assignment_mode": self._state.assignment_mode,
            "groups": self._serialize_groups(),
            "pages": self._serialize_pages(),
            "preset_colors": PRESET_COLORS,
            "marker_images": self._build_marker_images(),
            "plain_marker_image": self._build_plain_marker_image(),
            "photos": [],
        }

    def delete_photos(self, filepaths: List[str]) -> Dict[str, Any]:
        if not isinstance(filepaths, list) or not filepaths:
            return {"status": "error", "message": "No photos selected."}

        valid_paths = [path for path in filepaths if path in self._state.selected_files]
        if not valid_paths:
            return {"status": "error", "message": "Photo not found."}

        for path in valid_paths:
            if path in self._state.selected_files:
                self._state.selected_files.remove(path)
            self._state.file_metadata.pop(path, None)
            self._state.gps_overrides.pop(path, None)
            self._state.custom_marker_overrides.pop(path, None)
            self._state.photo_aliases.pop(path, None)
            self._state.photo_notes.pop(path, None)
            self._state.photo_previews.pop(path, None)
            self._state.drive_sources.pop(path, None)
            self._state.group_assignments.unassign_photo(path)
            self._state.page_assignments.unassign_photo(path)
            for page in self._state.page_assignments.pages.values():
                page.editor_state.gps_overrides.pop(path, None)
                page.editor_state.custom_marker_overrides.pop(path, None)

        markers_payload = []
        for filepath, gps in self._state.gps_overrides.items():
            markers_payload.append({
                "filepath": filepath,
                "latitude": gps.latitude,
                "longitude": gps.longitude,
                "altitude": gps.altitude,
            })

        custom_markers_payload = []
        for filepath, pixel in self._state.custom_marker_overrides.items():
            custom_markers_payload.append({
                "filepath": filepath,
                "x": pixel.x,
                "y": pixel.y,
            })

        _apply_overrides(
            self._state,
            {
                "markers": markers_payload,
                "custom_markers": custom_markers_payload,
            },
        )

        payload = self._groups_payload()
        payload["photos"] = self._build_photo_list()
        return payload

    def get_photo_list(self) -> Dict[str, Any]:
        self._sync_group_assignments()
        self._sync_page_assignments()
        return {"status": "ok", "photos": self._build_photo_list()}

    def get_groups(self) -> Dict[str, Any]:
        self._sync_group_assignments()
        return self._groups_payload()

    def get_assignment_state(self) -> Dict[str, Any]:
        self._sync_group_assignments()
        self._sync_page_assignments()
        payload = self._groups_payload()
        payload.update({
            "assignment_mode": self._state.assignment_mode,
            "pages": self._serialize_pages(),
            "plain_marker_image": self._build_plain_marker_image(),
        })
        return payload

    def set_assignment_mode(self, mode: str) -> Dict[str, Any]:
        cleaned = str(mode or "").strip().lower()
        if cleaned not in ("group", "page"):
            return {"status": "error", "message": "Assignment mode must be group or page."}
        self._state.assignment_mode = cleaned
        if cleaned == "group":
            self._sync_group_assignments()
        else:
            self._sync_page_assignments()
        _apply_overrides(self._state, {"assignment_mode": cleaned})
        return self.get_assignment_state()

    def add_page(self, name: str = "") -> Dict[str, Any]:
        self._state.page_assignments.add_page(str(name or ""))
        self._sync_page_assignments()
        _apply_overrides(self._state, {})
        return self.get_assignment_state()

    def delete_page(self, page_id: str) -> Dict[str, Any]:
        if page_id == DEFAULT_PAGE_ID:
            return {"status": "error", "message": "Page 1 cannot be deleted."}
        if not self._state.page_assignments.get_page(page_id):
            return {"status": "error", "message": "Page not found."}
        self._state.page_assignments.remove_page(page_id)
        self._sync_page_assignments()
        _apply_overrides(self._state, {})
        return self.get_assignment_state()

    def rename_page(self, page_id: str, new_name: str) -> Dict[str, Any]:
        name = str(new_name or "").strip()
        if not name:
            return {"status": "error", "message": "Page name cannot be empty."}
        if not self._state.page_assignments.rename_page(page_id, name):
            return {"status": "error", "message": "Page not found."}
        _apply_overrides(self._state, {})
        return self.get_assignment_state()

    def assign_photo_page(self, filepath: Union[str, List[str]], page_id: str) -> Dict[str, Any]:
        if isinstance(filepath, list):
            raw_paths = filepath
        else:
            raw_paths = [filepath]

        paths = [path for path in raw_paths if isinstance(path, str) and path]
        if not paths:
            return {"status": "error", "message": "No photos selected."}
        if not self._state.page_assignments.get_page(page_id):
            return {"status": "error", "message": "Page not found."}

        seen = set()
        valid_paths = []
        for path in paths:
            if path in self._state.selected_files and path not in seen:
                valid_paths.append(path)
                seen.add(path)
        if not valid_paths:
            return {"status": "error", "message": "Photo not found."}

        for path in valid_paths:
            self._state.page_assignments.assign_photo(path, page_id)
        self._sync_page_assignments()
        _apply_overrides(self._state, {})
        return {
            "status": "ok",
            "assignment_mode": self._state.assignment_mode,
            "photos": self._build_photo_list(),
            "pages": self._serialize_pages(),
        }

    def set_photo_name(self, filepath: str, name: str) -> Dict[str, Any]:
        if filepath not in self._state.selected_files:
            return {"status": "error", "message": "Photo not found."}
        cleaned = str(name or "").strip()
        if cleaned:
            self._state.photo_aliases[filepath] = cleaned
        else:
            self._state.photo_aliases.pop(filepath, None)
        _apply_overrides(self._state, {})
        return {"status": "ok", "photos": self._build_photo_list()}

    def set_photo_note(self, filepath: str, note: str) -> Dict[str, Any]:
        if filepath not in self._state.selected_files:
            return {"status": "error", "message": "Photo not found."}
        cleaned = str(note or "").strip()
        if cleaned:
            self._state.photo_notes[filepath] = cleaned
        else:
            self._state.photo_notes.pop(filepath, None)
        _apply_overrides(self._state, {})
        return {"status": "ok", "photos": self._build_photo_list()}

    def add_group(self, name: str = "") -> Dict[str, Any]:
        display_name = str(name or "").strip()
        if not display_name:
            display_name = f"Group {len(self._state.group_assignments.groups)}"

        used_colors = {g.color.lower() for g in self._state.group_assignments.groups.values()}
        next_color = "#F6D11A"
        for preset in PRESET_COLORS:
            if preset["hex"] == "default":
                continue
            if preset["hex"].lower() not in used_colors:
                next_color = preset["hex"]
                break

        self._state.group_assignments.add_group(display_name, next_color)
        _apply_overrides(self._state, {})
        return self._groups_payload()

    def delete_group(self, group_id: str) -> Dict[str, Any]:
        if group_id in DEFAULT_GROUP_IDS:
            return {"status": "error", "message": "Default groups cannot be deleted."}
        group = self._state.group_assignments.get_group(group_id)
        if not group:
            return {"status": "error", "message": "Group not found."}

        for filepath in list(group.photo_paths):
            self._state.group_assignments.assign_photo(filepath, "default")
        self._state.group_assignments.remove_group(group_id)
        self._state.group_aliases.pop(group_id, None)
        _apply_overrides(self._state, {})
        return self._groups_payload()

    def set_group_display_name(self, group_id: str, name: str) -> Dict[str, Any]:
        if not self._state.group_assignments.get_group(group_id):
            return {"status": "error", "message": "Group not found."}
        cleaned = str(name or "").strip()
        if cleaned:
            self._state.group_aliases[group_id] = cleaned
        else:
            self._state.group_aliases.pop(group_id, None)
        _apply_overrides(self._state, {})
        return self._groups_payload()

    def rename_group(self, group_id: str, new_name: str) -> Dict[str, Any]:
        name = str(new_name or "").strip()
        if not name:
            return {"status": "error", "message": "Group name cannot be empty."}
        if not self._state.group_assignments.rename_group(group_id, name):
            return {"status": "error", "message": "Group not found."}
        _apply_overrides(self._state, {})
        return self._groups_payload()

    def change_group_color(self, group_id: str, color: str) -> Dict[str, Any]:
        color_value = str(color or "").strip()
        if not color_value:
            return {"status": "error", "message": "Color cannot be empty."}
        if not self._state.group_assignments.change_group_color(group_id, color_value):
            return {"status": "error", "message": "Group not found."}
        _apply_overrides(self._state, {})
        return self._groups_payload()

    def assign_photo_group(self, filepath: Union[str, List[str]], group_id: str) -> Dict[str, Any]:
        if isinstance(filepath, list):
            raw_paths = filepath
        else:
            raw_paths = [filepath]

        paths = [path for path in raw_paths if isinstance(path, str) and path]
        if not paths:
            return {"status": "error", "message": "No photos selected."}
        if not self._state.group_assignments.get_group(group_id):
            return {"status": "error", "message": "Group not found."}

        seen = set()
        valid_paths = []
        for path in paths:
            if path in self._state.selected_files and path not in seen:
                valid_paths.append(path)
                seen.add(path)
        if not valid_paths:
            return {"status": "error", "message": "Photo not found."}

        for path in valid_paths:
            self._state.group_assignments.assign_photo(path, group_id)
        self._sync_group_assignments()
        _apply_overrides(self._state, {})
        return {
            "status": "ok",
            "photos": self._build_photo_list(),
            "groups": self._serialize_groups(),
        }

    def select_output_folder(self) -> Dict[str, Any]:
        if not self._window:
            return {"status": "error", "message": "Window not ready"}

        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not result:
            return {"status": "cancel"}
        folder = result[0]
        self._state.output_folder = folder
        return {"status": "ok", "path": folder}

    def reset_output_folder(self) -> Dict[str, Any]:
        self._state.output_folder = None
        return {"status": "ok"}

    def _logo_data_uri(self) -> str:
        path = get_user_logo_path()
        if path is None:
            path = get_asset_path("everline-horizontal-logo.jpg")
        if not path or not path.exists():
            return ""
        try:
            with Image.open(path) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                return f"data:image/png;base64,{b64}"
        except (OSError, ValueError):
            return ""

    def get_branding(self) -> Dict[str, Any]:
        info = get_company_info()
        return {
            "status": "ok",
            "logo_data_uri": self._logo_data_uri(),
            "has_user_logo": get_user_logo_path() is not None,
            **info,
        }

    def select_and_save_logo(self) -> Dict[str, Any]:
        if not self._window:
            return {"status": "error", "ok": False, "error": "Window not ready"}

        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Image files (*.jpg;*.jpeg;*.png)",),
        )
        if not result:
            return {"status": "cancel", "ok": False}

        try:
            data = Path(result[0]).read_bytes()
        except OSError as exc:
            return {"status": "error", "ok": False, "error": f"Could not read file: {exc}"}

        try:
            set_user_logo_from_bytes(data)
        except ValueError as exc:
            return {"status": "error", "ok": False, "error": str(exc)}

        reset_colorizer()
        return {
            "status": "ok",
            "ok": True,
            "logo_data_uri": self._logo_data_uri(),
        }

    def clear_logo(self) -> Dict[str, Any]:
        clear_user_logo()
        reset_colorizer()
        return {
            "status": "ok",
            "ok": True,
            "logo_data_uri": self._logo_data_uri(),
        }

    def save_company_info(
        self,
        company_name: str = "",
        company_address: str = "",
        company_phone: str = "",
        company_website: str = "",
    ) -> Dict[str, Any]:
        set_company_info(
            company_name,
            company_address,
            company_phone,
            company_website,
        )
        return {"status": "ok", **get_company_info()}

    def _build_editor_photo_payload(
        self,
        filepath: str,
        page_editor_state: Optional[PageEditorState] = None,
    ) -> Optional[Dict[str, Any]]:
        metadata = self._state.file_metadata.get(filepath)
        if not metadata:
            return None

        gps = metadata.gps
        if page_editor_state is not None:
            override = page_editor_state.gps_overrides.get(filepath)
        else:
            override = self._state.gps_overrides.get(filepath)
        if override:
            gps = override

        gps_payload = None
        if gps:
            gps_payload = {
                "latitude": gps.latitude,
                "longitude": gps.longitude,
                "altitude": gps.altitude,
            }

        if page_editor_state is not None:
            custom_pixel = page_editor_state.custom_marker_overrides.get(filepath)
        else:
            custom_pixel = self._state.custom_marker_overrides.get(filepath)
        pixel_payload = None
        if custom_pixel:
            pixel_payload = {"x": custom_pixel.x, "y": custom_pixel.y}

        group = self._state.group_assignments.get_group_for_photo(filepath)
        group_id = group.id if group else "default"
        group_color = group.color if group else "default"
        page = self._state.page_assignments.get_page_for_photo(filepath)
        if page is None:
            page = self._state.page_assignments.get_page(DEFAULT_PAGE_ID)
        custom_name = self._state.photo_aliases.get(filepath, "")
        display_name = custom_name if custom_name else metadata.filename
        note = self._state.photo_notes.get(filepath, "")

        return {
            "filepath": filepath,
            "filename": Path(filepath).name,
            "display_name": display_name,
            "custom_name": custom_name,
            "note": note,
            "has_gps": bool(metadata.gps),
            "has_override": bool(override),
            "gps": gps_payload,
            "pixel": pixel_payload,
            "group_id": group_id,
            "group_color": group_color,
            "page_id": page.id if page else DEFAULT_PAGE_ID,
            "page_name": page.name if page else "Page 1",
        }

    def get_editor_state(self) -> Dict[str, Any]:
        if not self._state.selected_files:
            return {"status": "empty", "message": "No photos selected."}

        self._sync_group_assignments()
        self._sync_page_assignments()

        if self._state.assignment_mode == "page":
            pages_payload = []
            for page in self._state.page_assignments.get_all_pages():
                editor_state = page.editor_state
                custom_map_uri = ""
                custom_map_file_uri = ""
                custom_map_path = editor_state.custom_map_path
                if custom_map_path and Path(custom_map_path).exists():
                    custom_map_uri = _image_to_data_uri(custom_map_path)
                    custom_map_file_uri = _path_to_uri(custom_map_path)

                photos = []
                for filepath in page.photo_paths:
                    photo_payload = self._build_editor_photo_payload(filepath, editor_state)
                    if photo_payload:
                        photos.append(photo_payload)

                pages_payload.append({
                    "id": page.id,
                    "name": page.name,
                    "display_name": page.name,
                    "locked": page.locked or page.id == DEFAULT_PAGE_ID,
                    "photos": photos,
                    "marker_size": self._state.marker_size,
                    "map_source": editor_state.map_source,
                    "heading": editor_state.heading,
                    "custom_heading": editor_state.custom_heading,
                    "custom_map_path": custom_map_path,
                    "custom_map_uri": custom_map_uri,
                    "custom_map_file_uri": custom_map_file_uri,
                    "custom_autoplot_enabled": editor_state.custom_autoplot_enabled,
                    "tile_view": editor_state.tile_view,
                    "custom_view": editor_state.custom_view,
                })

            return {
                "status": "ok",
                "assignment_mode": "page",
                "pages": pages_payload,
                "photos": pages_payload[0]["photos"] if pages_payload else [],
                "marker_size": self._state.marker_size,
                "hide_markers": self._state.hide_markers,
                "hide_sidebar": self._state.hide_sidebar,
                "plain_marker_image": self._build_plain_marker_image(),
            }

        custom_map_path = self._state.custom_map_path
        custom_map_uri = ""
        custom_map_file_uri = ""
        if custom_map_path and Path(custom_map_path).exists():
            custom_map_uri = _image_to_data_uri(custom_map_path)
            custom_map_file_uri = _path_to_uri(custom_map_path)

        photos = []
        for filepath in self._state.selected_files:
            photo_payload = self._build_editor_photo_payload(filepath)
            if photo_payload:
                photos.append(photo_payload)

        return {
            "status": "ok",
            "assignment_mode": "group",
            "photos": photos,
            "marker_size": self._state.marker_size,
            "hide_markers": self._state.hide_markers,
            "hide_sidebar": self._state.hide_sidebar,
            "heading": self._state.heading,
            "custom_heading": self._state.custom_heading,
            "custom_map_path": custom_map_path,
            "custom_map_uri": custom_map_uri,
            "custom_map_file_uri": custom_map_file_uri,
            "custom_autoplot_enabled": self._state.custom_autoplot_enabled,
        }

    def save_overrides(self, payload: Dict[str, Any]) -> bool:
        try:
            _apply_overrides(self._state, payload)
            self._persist_active_project_overrides()
            return True
        except Exception:
            return False

    def _persist_active_project_overrides(self) -> None:
        """Merge live overrides state into the active project's JSON so the
        background image and placements survive switching to another project
        and back. No-op when no saved project is loaded."""
        name = self._state.current_project_name
        if not name:
            return
        try:
            stored = _load_project(name)
            if stored is None:
                return
            stored.update(_serialize_overrides_state(self._state))
            stored["selected_files"] = list(self._state.selected_files)
            stored["drive_sources"] = dict(self._state.drive_sources)
            stored["drive_folder_url"] = self._state.drive_folder_url
            stored["output_folder"] = self._state.output_folder
            _save_project(name, stored)
        except Exception:
            pass

    def export_html(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        output_path = self._prompt_html_save_path(payload)
        if not output_path:
            return {"status": "cancel"}

        try:
            self._sync_group_assignments()
            self._sync_page_assignments()

            # The single-file HTML deliverable can't play video — drop video markers
            # and tell the user (videos are supported via Deploy to Web).
            video_paths = {fp for fp in self._state.selected_files if is_video_format(fp)}
            dropped_videos = _strip_video_markers(payload, video_paths) if video_paths else 0
            warning = (
                f"{dropped_videos} video(s) skipped — videos play in Deploy to Web."
                if dropped_videos else None
            )

            def _ok(path: str) -> Dict[str, Any]:
                out = {"status": "ok", "path": path}
                if warning:
                    out["warning"] = warning
                return out

            if payload.get("assignment_mode") == "page":
                export_pages = _build_multi_page_export_pages(self._state, payload, use_drive_urls=False)
                generator = HTMLMapGenerator(
                    project_name=payload.get("project_name", "Photo Map"),
                    marker_size=int(payload.get("marker_size", self._state.marker_size)),
                    proposal_link=payload.get("proposal_link"),
                    download_photos_link=payload.get("download_photos_link"),
                    client_name=payload.get("client_name"),
                    client_company=payload.get("client_company"),
                    client_address=payload.get("client_address"),
                    hide_markers=bool(payload.get("hide_markers", self._state.hide_markers)),
                    hide_sidebar=bool(payload.get("hide_sidebar", self._state.hide_sidebar)),
                    **get_company_info(),
                )
                result_path = generator.generate_multi_page_html(
                    export_pages,
                    output_path=output_path,
                )
                _apply_overrides(self._state, payload)
                if not open_file_in_default_app(result_path):
                    open_folder_containing(result_path)
                return _ok(result_path)

            map_source = payload.get("map_source", "tiles")
            if map_source == "custom":
                custom_markers = payload.get("custom_markers", [])
                if not custom_markers:
                    return {"status": "error", "message": "No placed photos available."}
                custom_image_path = payload.get("custom_image_path") or self._state.custom_map_path
                if not custom_image_path:
                    return {"status": "error", "message": "No custom image selected."}
                if not Path(custom_image_path).exists():
                    return {"status": "error", "message": "Custom image not found."}

                compression_quality = int(payload.get("compression_quality", 30))
                processed_photos, marker_pixels = _process_custom_export(
                    self._state,
                    custom_markers,
                    compression_quality,
                )
                heading = float(payload.get("heading", self._state.custom_heading))
                export_image_path = custom_image_path
                if heading:
                    export_image_path, marker_pixels = _rotate_custom_map_for_export(
                        custom_image_path,
                        marker_pixels,
                        heading,
                    )

                marker_size = int(payload.get("marker_size", self._state.marker_size))
                custom_zoom = payload.get("custom_zoom")
                try:
                    zoom = float(custom_zoom)
                    if zoom > 0:
                        marker_size = max(1, int(round(marker_size / zoom)))
                except (TypeError, ValueError):
                    pass

                generator = HTMLMapGenerator(
                    project_name=payload.get("project_name", "Photo Map"),
                    marker_size=marker_size,
                    proposal_link=payload.get("proposal_link"),
                    download_photos_link=payload.get("download_photos_link"),
                    client_name=payload.get("client_name"),
                    client_company=payload.get("client_company"),
                    client_address=payload.get("client_address"),
                    hide_markers=bool(payload.get("hide_markers", self._state.hide_markers)),
                    hide_sidebar=bool(payload.get("hide_sidebar", self._state.hide_sidebar)),
                    **get_company_info(),
                )

                result_path = generator.generate_single_html(
                    processed_photos,
                    export_image_path,
                    transform=None,
                    output_path=output_path,
                    marker_pixels=marker_pixels,
                    group_assignments=self._state.group_assignments,
                    group_aliases=self._state.group_aliases,
                )

                _apply_overrides(self._state, payload)
                if not open_file_in_default_app(result_path):
                    open_folder_containing(result_path)
                return _ok(result_path)

            map_state = payload.get("map_state", {})
            center = map_state.get("center", {})
            zoom = int(map_state.get("zoom", 19))
            heading = float(map_state.get("heading", 0))
            export_width = int(map_state.get("width", EXPORT_MAX_DIM))
            export_height = int(map_state.get("height", EXPORT_MAX_DIM))

            marker_size = int(payload.get("marker_size", self._state.marker_size))
            viewport_width = payload.get("viewport_width")
            viewport_height = payload.get("viewport_height")
            scale = None
            try:
                if viewport_width:
                    scale = float(export_width) / float(viewport_width)
                elif viewport_height:
                    scale = float(export_height) / float(viewport_height)
            except (TypeError, ValueError, ZeroDivisionError):
                scale = None
            if scale and scale > 0:
                marker_size = max(1, int(round(marker_size * scale)))

            base_width, base_height = _compute_base_size(export_width, export_height, heading)
            api_key = get_google_maps_api_key() or ""
            map_image, left, top = _stitch_tiles(
                float(center.get("lat", 0.0)),
                float(center.get("lng", 0.0)),
                zoom,
                base_width,
                base_height,
                api_key=api_key,
            )

            map_image, expand_left, expand_top = _rotate_map_for_export(
                map_image,
                base_width,
                base_height,
                heading,
            )

            rotated_width, rotated_height = map_image.size
            crop_left = int(round((rotated_width - export_width) / 2))
            crop_top = int(round((rotated_height - export_height) / 2))
            crop_box = (
                crop_left,
                crop_top,
                crop_left + export_width,
                crop_top + export_height,
            )
            map_image = map_image.crop(crop_box)
            crop_left -= expand_left
            crop_top -= expand_top

            buffer = io.BytesIO()
            map_image.save(buffer, format="PNG")
            map_image_bytes = buffer.getvalue()
            map_image_size = map_image.size
            marker_pixels = _build_marker_pixels(
                payload.get("markers", []),
                left,
                top,
                base_width,
                base_height,
                heading,
                crop_left,
                crop_top,
                zoom,
            )

            compression_quality = int(payload.get("compression_quality", 30))
            processed_photos = _process_photos(self._state, payload.get("markers", []), compression_quality)

            generator = HTMLMapGenerator(
                project_name=payload.get("project_name", "Photo Map"),
                marker_size=marker_size,
                proposal_link=payload.get("proposal_link"),
                download_photos_link=payload.get("download_photos_link"),
                client_name=payload.get("client_name"),
                client_company=payload.get("client_company"),
                client_address=payload.get("client_address"),
                hide_markers=bool(payload.get("hide_markers", self._state.hide_markers)),
                hide_sidebar=bool(payload.get("hide_sidebar", self._state.hide_sidebar)),
                **get_company_info(),
            )

            result_path = generator.generate_single_html(
                processed_photos,
                aerial_image_path=None,
                transform=None,
                output_path=output_path,
                marker_pixels=marker_pixels,
                group_assignments=self._state.group_assignments,
                group_aliases=self._state.group_aliases,
                aerial_image_bytes=map_image_bytes,
                aerial_image_mime="image/png",
                aerial_image_size=map_image_size,
            )

            _apply_overrides(self._state, payload)
            if not open_file_in_default_app(result_path):
                open_folder_containing(result_path)
            return _ok(result_path)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _deploy_html_to_netlify(
        self,
        token: str,
        html_content: str,
        project_name: str,
        extra_files: Optional[Dict[str, bytes]] = None,
    ) -> Dict[str, Any]:
        """Run the Netlify deploy, persist the site_id/URL for the active project, and
        produce the API response dict. extra_files carries local video assets."""
        deployer = NetlifyDeployer(token, self._state.netlify_site_id)
        result = deployer.deploy(html_content, project_name, extra_files)
        if not result.success:
            return {"status": "error", "message": result.error}

        self._state.netlify_site_id = result.site_id
        self._state.netlify_deploy_url = result.url

        # Persist deploy info + the latest overrides state to the saved project JSON
        # so the link AND the editor configuration survive session restarts.
        self._persist_active_project_overrides()
        if self._state.current_project_name:
            try:
                stored = _load_project(self._state.current_project_name) or {}
                stored["netlify_site_id"] = result.site_id
                stored["netlify_deploy_url"] = result.url
                _save_project(self._state.current_project_name, stored)
            except Exception:
                pass

        return {
            "status": "ok",
            "url": result.url,
            "deployment_id": result.deployment_id,
        }

    def deploy_to_web(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy HTML map to Netlify and return shareable URL."""
        token = get_netlify_token()
        if not token:
            return {
                "status": "error",
                "message": "Please add your Netlify token in Options first.",
            }

        try:
            self._sync_group_assignments()
            self._sync_page_assignments()
            if payload.get("assignment_mode") == "page":
                export_pages = _build_multi_page_export_pages(self._state, payload, use_drive_urls=True)
                # Collect local-video bytes across all pages and resolve their media/ URLs
                # before generating the HTML that references them.
                all_page_photos = [p for page in export_pages for p in page.get("photos", [])]
                extra_files = _collect_video_assets(all_page_photos)
                generator = HTMLMapGenerator(
                    project_name=payload.get("project_name", "Photo Map"),
                    marker_size=int(payload.get("marker_size", self._state.marker_size)),
                    proposal_link=payload.get("proposal_link"),
                    download_photos_link=payload.get("download_photos_link"),
                    client_name=payload.get("client_name"),
                    client_company=payload.get("client_company"),
                    client_address=payload.get("client_address"),
                    hide_markers=bool(payload.get("hide_markers", self._state.hide_markers)),
                    hide_sidebar=bool(payload.get("hide_sidebar", self._state.hide_sidebar)),
                    **get_company_info(),
                )
                html_content = generator.generate_multi_page_html(
                    export_pages,
                    return_content=True,
                )
                project_name = payload.get("project_name", "Photo Map")
                response = self._deploy_html_to_netlify(token, html_content, project_name, extra_files)
                if response["status"] == "ok":
                    _apply_overrides(self._state, payload)
                return response

            map_source = payload.get("map_source", "tiles")

            if map_source == "custom":
                custom_markers = payload.get("custom_markers", [])
                if not custom_markers:
                    return {"status": "error", "message": "No placed photos available."}
                custom_image_path = payload.get("custom_image_path") or self._state.custom_map_path
                if not custom_image_path:
                    return {"status": "error", "message": "No custom image selected."}
                if not Path(custom_image_path).exists():
                    return {"status": "error", "message": "Custom image not found."}

                compression_quality = int(payload.get("compression_quality", 30))

                # Check if all custom-placed photos are from Drive
                custom_filepaths = [m.get("filepath") for m in custom_markers if m.get("filepath")]
                all_drive_custom = custom_filepaths and all(
                    fp in self._state.drive_sources for fp in custom_filepaths
                )

                if all_drive_custom:
                    processed_photos, marker_pixels = _build_drive_custom_export(
                        self._state, custom_markers,
                    )
                else:
                    processed_photos, marker_pixels = _process_custom_export(
                        self._state,
                        custom_markers,
                        compression_quality,
                    )
                heading = float(payload.get("heading", self._state.custom_heading))
                export_image_path = custom_image_path
                if heading:
                    export_image_path, marker_pixels = _rotate_custom_map_for_export(
                        custom_image_path,
                        marker_pixels,
                        heading,
                    )

                marker_size = int(payload.get("marker_size", self._state.marker_size))
                custom_zoom = payload.get("custom_zoom")
                try:
                    zoom = float(custom_zoom)
                    if zoom > 0:
                        marker_size = max(1, int(round(marker_size / zoom)))
                except (TypeError, ValueError):
                    pass

                generator = HTMLMapGenerator(
                    project_name=payload.get("project_name", "Photo Map"),
                    marker_size=marker_size,
                    proposal_link=payload.get("proposal_link"),
                    download_photos_link=payload.get("download_photos_link"),
                    client_name=payload.get("client_name"),
                    client_company=payload.get("client_company"),
                    client_address=payload.get("client_address"),
                    hide_markers=bool(payload.get("hide_markers", self._state.hide_markers)),
                    hide_sidebar=bool(payload.get("hide_sidebar", self._state.hide_sidebar)),
                    **get_company_info(),
                )

                extra_files = _collect_video_assets(processed_photos)
                html_content = generator.generate_single_html(
                    processed_photos,
                    export_image_path,
                    transform=None,
                    marker_pixels=marker_pixels,
                    group_assignments=self._state.group_assignments,
                    group_aliases=self._state.group_aliases,
                    return_content=True,
                )
            else:
                # Google tiles export
                map_state = payload.get("map_state", {})
                center = map_state.get("center", {})
                zoom = int(map_state.get("zoom", 19))
                heading = float(map_state.get("heading", 0))
                export_width = int(map_state.get("width", EXPORT_MAX_DIM))
                export_height = int(map_state.get("height", EXPORT_MAX_DIM))

                marker_size = int(payload.get("marker_size", self._state.marker_size))
                viewport_width = payload.get("viewport_width")
                viewport_height = payload.get("viewport_height")
                scale = None
                try:
                    if viewport_width:
                        scale = float(export_width) / float(viewport_width)
                    elif viewport_height:
                        scale = float(export_height) / float(viewport_height)
                except (TypeError, ValueError, ZeroDivisionError):
                    scale = None
                if scale and scale > 0:
                    marker_size = max(1, int(round(marker_size * scale)))

                base_width, base_height = _compute_base_size(export_width, export_height, heading)
                api_key = get_google_maps_api_key() or ""
                map_image, left, top = _stitch_tiles(
                    float(center.get("lat", 0.0)),
                    float(center.get("lng", 0.0)),
                    zoom,
                    base_width,
                    base_height,
                    api_key=api_key,
                )

                map_image, expand_left, expand_top = _rotate_map_for_export(
                    map_image,
                    base_width,
                    base_height,
                    heading,
                )

                rotated_width, rotated_height = map_image.size
                crop_left = int(round((rotated_width - export_width) / 2))
                crop_top = int(round((rotated_height - export_height) / 2))
                crop_box = (
                    crop_left,
                    crop_top,
                    crop_left + export_width,
                    crop_top + export_height,
                )
                map_image = map_image.crop(crop_box)
                crop_left -= expand_left
                crop_top -= expand_top

                buffer = io.BytesIO()
                map_image.save(buffer, format="PNG")
                map_image_bytes = buffer.getvalue()
                map_image_size = map_image.size
                marker_pixels = _build_marker_pixels(
                    payload.get("markers", []),
                    left,
                    top,
                    base_width,
                    base_height,
                    heading,
                    crop_left,
                    crop_top,
                    zoom,
                )

                compression_quality = int(payload.get("compression_quality", 30))

                # Check if all photos to export are from Drive
                filepaths_to_export = [
                    item.get("filepath")
                    for item in payload.get("markers", [])
                    if item.get("filepath")
                ]
                all_drive = filepaths_to_export and all(
                    fp in self._state.drive_sources for fp in filepaths_to_export
                )

                if all_drive:
                    processed_photos = _build_drive_photo_dicts(
                        self._state, payload.get("markers", []),
                    )
                else:
                    processed_photos = _process_photos(self._state, payload.get("markers", []), compression_quality)

                generator = HTMLMapGenerator(
                    project_name=payload.get("project_name", "Photo Map"),
                    marker_size=marker_size,
                    proposal_link=payload.get("proposal_link"),
                    download_photos_link=payload.get("download_photos_link"),
                    client_name=payload.get("client_name"),
                    client_company=payload.get("client_company"),
                    client_address=payload.get("client_address"),
                    hide_markers=bool(payload.get("hide_markers", self._state.hide_markers)),
                    hide_sidebar=bool(payload.get("hide_sidebar", self._state.hide_sidebar)),
                    **get_company_info(),
                )

                extra_files = _collect_video_assets(processed_photos)
                html_content = generator.generate_single_html(
                    processed_photos,
                    aerial_image_path=None,
                    transform=None,
                    marker_pixels=marker_pixels,
                    group_assignments=self._state.group_assignments,
                    group_aliases=self._state.group_aliases,
                    aerial_image_bytes=map_image_bytes,
                    aerial_image_mime="image/png",
                    aerial_image_size=map_image_size,
                    return_content=True,
                )

            project_name = payload.get("project_name", "Photo Map")
            response = self._deploy_html_to_netlify(token, html_content, project_name, extra_files)
            if response["status"] == "ok":
                _apply_overrides(self._state, payload)
            return response

        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def start_kmz_export(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        gps_files = []
        video_skipped = 0
        for path in self._state.selected_files:
            metadata = self._state.file_metadata.get(path)
            if not metadata:
                continue
            if metadata.gps or path in self._state.gps_overrides:
                # KMZ (Google Earth) doesn't support video playback — omit videos.
                if is_video_format(path):
                    video_skipped += 1
                    continue
                gps_files.append(path)
        if not gps_files:
            if video_skipped:
                return {
                    "status": "error",
                    "message": "KMZ supports photos only. Use Deploy to Web for video.",
                }
            return {"status": "error", "message": "No placed photos available."}

        output_path = self._prompt_kmz_save_path(payload)
        if not output_path:
            return {"status": "cancel"}

        with self._kmz_lock:
            if self._kmz_thread and self._kmz_thread.is_alive():
                return {"status": "busy", "message": "KMZ export already running."}

            thread = threading.Thread(
                target=self._run_kmz_export,
                args=(gps_files, output_path, payload, video_skipped),
                daemon=True,
            )
            self._kmz_thread = thread
            thread.start()

        return {"status": "started"}

    def open_file(self, path: str) -> bool:
        return open_file_in_default_app(path)

    def open_folder(self, path: str) -> bool:
        return open_folder_containing(path)

    def on_closing(self) -> None:
        return

    def _run_kmz_export(
        self,
        files: List[str],
        output_path: str,
        payload: Dict[str, Any],
        video_skipped: int = 0,
    ) -> None:
        import tempfile

        def progress_callback(status: str, current: int, total: int) -> None:
            if not self._window:
                return
            progress = (current / total) if total else 0
            self._window.evaluate_js(
                f"window.kmzProgress({json.dumps(status)}, {progress})"
            )

        temp_files: List[str] = []
        try:
            # For Drive photos, download to temp files so KMZ generator can read them
            actual_files = []
            drive_temp_map: Dict[str, str] = {}  # temp_path -> virtual_path
            api_key = get_google_maps_api_key() or ""

            for filepath in files:
                file_id = self._state.drive_sources.get(filepath)
                if file_id and api_key:
                    metadata = self._state.file_metadata.get(filepath)
                    filename = metadata.filename if metadata else "photo.jpg"
                    raw_bytes = fetch_image_bytes(file_id, api_key)
                    suffix = Path(filename).suffix or ".jpg"
                    tmp = tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix, prefix="pp_drive_"
                    )
                    tmp.write(raw_bytes)
                    tmp.close()
                    temp_files.append(tmp.name)
                    actual_files.append(tmp.name)
                    drive_temp_map[tmp.name] = filepath
                else:
                    actual_files.append(filepath)

            # Remap gps_overrides to temp paths for Drive files
            gps_overrides = dict(self._state.gps_overrides) if self._state.gps_overrides else {}
            for temp_path, vpath in drive_temp_map.items():
                if vpath in gps_overrides:
                    gps_overrides[temp_path] = gps_overrides.pop(vpath)

            result_path, processed, skipped, errors = create_kmz_from_files(
                actual_files,
                output_path,
                project_name=payload.get("project_name", "PicPlotter Export"),
                compression_quality=int(payload.get("compression_quality", 30)),
                max_dimension=1920,
                progress_callback=progress_callback,
                gps_overrides=gps_overrides or None,
            )

            if self._window:
                result = {
                    "status": "ok",
                    "path": result_path,
                    "processed": processed,
                    "skipped": skipped,
                    "errors": errors,
                    "video_skipped": video_skipped,
                }
                self._window.evaluate_js(f"window.kmzComplete({json.dumps(result)})")
        except Exception as exc:
            if self._window:
                self._window.evaluate_js(f"window.kmzError({json.dumps(str(exc))})")
        finally:
            for tmp in temp_files:
                try:
                    Path(tmp).unlink()
                except OSError:
                    pass

    def _prompt_html_save_path(self, payload: Dict[str, Any]) -> Optional[str]:
        if not self._window:
            return None
        default_path = get_default_output_path(self._state.selected_files[0] if self._state.selected_files else None)
        initial_dir = self._state.output_folder or str(Path(default_path).parent)
        project_name = payload.get("project_name", "Photo Map")
        save_name = f"{project_name}.html"
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=initial_dir,
            save_filename=save_name,
            file_types=("HTML files (*.html)",),
        )
        if not result:
            return None
        return result[0]

    def _prompt_kmz_save_path(self, payload: Dict[str, Any]) -> Optional[str]:
        if not self._window:
            return None
        default_path = get_default_output_path(self._state.selected_files[0] if self._state.selected_files else None)
        initial_dir = self._state.output_folder or str(Path(default_path).parent)
        project_name = payload.get("project_name", "PicPlotter Export")
        save_name = f"{project_name}.kmz"
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=initial_dir,
            save_filename=save_name,
            file_types=("KMZ files (*.kmz)",),
        )
        if not result:
            return None
        return result[0]

    def _sync_group_assignments(self) -> None:
        _sync_group_assignments_state(self._state, prune_photos=bool(self._state.selected_files))

    def _sync_page_assignments(self) -> None:
        _sync_page_assignments_state(self._state, prune_photos=bool(self._state.selected_files))

    def _serialize_groups(self) -> List[Dict[str, Any]]:
        groups = []
        for group in self._state.group_assignments.get_all_groups():
            custom_name = self._state.group_aliases.get(group.id, "")
            display_name = custom_name if custom_name else group.name
            groups.append({
                "id": group.id,
                "name": group.name,
                "display_name": display_name,
                "custom_name": custom_name,
                "color": group.color,
                "count": len(group.photo_paths),
                "locked": group.id in DEFAULT_GROUP_IDS,
            })
        return groups

    def _serialize_pages(self) -> List[Dict[str, Any]]:
        pages = []
        for page in self._state.page_assignments.get_all_pages():
            pages.append({
                "id": page.id,
                "name": page.name,
                "display_name": page.name,
                "count": len(page.photo_paths),
                "locked": page.locked or page.id == DEFAULT_PAGE_ID,
            })
        return pages

    def _build_marker_images(self) -> Dict[str, str]:
        colorizer = get_colorizer()
        colors = {group.color for group in self._state.group_assignments.get_all_groups()}
        images: Dict[str, str] = {}
        for color in colors:
            marker_bytes = colorizer.get_colored_marker_bytes(color, UI_MARKER_ICON_SIZE)
            b64 = base64.b64encode(marker_bytes).decode("utf-8")
            images[color] = f"data:image/png;base64,{b64}"
        return images

    def _build_plain_marker_image(self) -> str:
        marker_bytes = get_colorizer().get_plain_marker_bytes(UI_MARKER_ICON_SIZE)
        b64 = base64.b64encode(marker_bytes).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    def _groups_payload(self) -> Dict[str, Any]:
        self._sync_group_assignments()
        return {
            "status": "ok",
            "groups": self._serialize_groups(),
            "preset_colors": PRESET_COLORS,
            "marker_images": self._build_marker_images(),
        }

    def _get_photo_preview_uri(self, filepath: str) -> str:
        cached = self._state.photo_previews.get(filepath)
        if cached is not None:
            return cached
        file_id = self._state.drive_sources.get(filepath)
        if file_id:
            # Drive auto-generates a poster thumbnail for videos too.
            preview_uri = get_thumbnail_url(file_id, PHOTO_PREVIEW_MAX_DIM)
        elif is_video_format(filepath):
            # No dependency-free way to grab a local video frame — use a placeholder.
            preview_uri = _VIDEO_PLACEHOLDER_URI
        else:
            preview_uri = _image_to_preview_data_uri(
                filepath,
                max_dimension=PHOTO_PREVIEW_MAX_DIM,
                quality=PHOTO_PREVIEW_QUALITY,
            )
        self._state.photo_previews[filepath] = preview_uri
        return preview_uri

    def _build_photo_list(self) -> List[Dict[str, Any]]:
        photos = []
        for filepath in self._state.selected_files:
            metadata = self._state.file_metadata.get(filepath)
            if not metadata:
                continue
            group = self._state.group_assignments.get_group_for_photo(filepath)
            group_id = group.id if group else "default"
            group_color = group.color if group else "default"
            page = self._state.page_assignments.get_page_for_photo(filepath)
            if page is None:
                page = self._state.page_assignments.get_page(DEFAULT_PAGE_ID)
            page_id = page.id if page else DEFAULT_PAGE_ID
            page_name = page.name if page else "Page 1"
            custom_name = self._state.photo_aliases.get(filepath, "")
            display_name = custom_name if custom_name else metadata.filename
            note = self._state.photo_notes.get(filepath, "")
            has_page_override = False
            if page:
                has_page_override = (
                    filepath in page.editor_state.gps_overrides
                    or filepath in page.editor_state.custom_marker_overrides
                )
            photos.append({
                "filepath": filepath,
                "filename": metadata.filename,
                "display_name": display_name,
                "custom_name": custom_name,
                "note": note,
                "preview_uri": self._get_photo_preview_uri(filepath),
                "has_gps": bool(metadata.gps),
                "is_video": is_video_format(filepath),
                "has_override": (
                    has_page_override
                    if self._state.assignment_mode == "page"
                    else filepath in self._state.gps_overrides
                ),
                "group_id": group_id,
                "group_color": group_color,
                "page_id": page_id,
                "page_name": page_name,
            })
        return photos


def _sync_group_assignments_state(state: AppState, prune_photos: bool = True) -> None:
    if prune_photos:
        selected = set(state.selected_files)
        for group in state.group_assignments.groups.values():
            group.photo_paths = [path for path in group.photo_paths if path in selected]
        state.group_assignments.auto_assign_unassigned(state.selected_files)
    if state.group_aliases:
        valid_ids = set(state.group_assignments.groups.keys())
        state.group_aliases = {
            group_id: name
            for group_id, name in state.group_aliases.items()
            if group_id in valid_ids
        }


def _sync_page_assignments_state(state: AppState, prune_photos: bool = True) -> None:
    if prune_photos:
        state.page_assignments.prune_to_photos(state.selected_files)
        state.page_assignments.auto_assign_unassigned(state.selected_files)


def _normalize_custom_markers(raw: Any) -> Dict[str, PixelPoint]:
    markers: Dict[str, PixelPoint] = {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            items.append((item.get("filepath"), item))
    else:
        return markers

    for filepath, entry in items:
        if not filepath or not isinstance(entry, dict):
            continue
        x = entry.get("x")
        y = entry.get("y")
        try:
            markers[str(filepath)] = PixelPoint(float(x), float(y))
        except (TypeError, ValueError):
            continue
    return markers


def _serialize_group_state(state: AppState) -> tuple[List[Dict[str, str]], Dict[str, str]]:
    groups_payload: List[Dict[str, str]] = []
    for group in state.group_assignments.get_all_groups():
        groups_payload.append({
            "id": group.id,
            "name": group.name,
            "color": group.color,
        })

    group_assignments_payload: Dict[str, str] = {}
    for group in state.group_assignments.groups.values():
        for filepath in group.photo_paths:
            if filepath:
                group_assignments_payload[filepath] = group.id

    return groups_payload, group_assignments_payload


def _serialize_page_editor_state(editor_state: PageEditorState) -> Dict[str, Any]:
    markers_payload = []
    for filepath, gps in editor_state.gps_overrides.items():
        markers_payload.append({
            "filepath": filepath,
            "latitude": gps.latitude,
            "longitude": gps.longitude,
            "altitude": gps.altitude,
        })

    custom_markers_payload = []
    for filepath, pixel in editor_state.custom_marker_overrides.items():
        custom_markers_payload.append({
            "filepath": filepath,
            "x": pixel.x,
            "y": pixel.y,
        })

    return {
        "map_source": editor_state.map_source,
        "heading": editor_state.heading,
        "custom_heading": editor_state.custom_heading,
        "custom_map_path": editor_state.custom_map_path,
        "custom_markers": custom_markers_payload,
        "markers": markers_payload,
        "custom_autoplot_enabled": editor_state.custom_autoplot_enabled,
        "tile_view": editor_state.tile_view,
        "custom_view": editor_state.custom_view,
    }


def _serialize_page_state(state: AppState) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    pages_payload: List[Dict[str, Any]] = []
    page_assignments_payload: Dict[str, str] = {}

    for page in state.page_assignments.get_all_pages():
        item: Dict[str, Any] = {
            "id": page.id,
            "name": page.name,
            "locked": page.locked or page.id == DEFAULT_PAGE_ID,
        }
        item.update(_serialize_page_editor_state(page.editor_state))
        pages_payload.append(item)
        for filepath in page.photo_paths:
            if filepath:
                page_assignments_payload[filepath] = page.id

    return pages_payload, page_assignments_payload


def _normalize_gps_markers(raw: Any) -> Dict[str, GPSCoordinates]:
    markers: Dict[str, GPSCoordinates] = {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            items.append((item.get("filepath"), item))
    else:
        return markers

    for filepath, entry in items:
        if not filepath or not isinstance(entry, dict):
            continue
        try:
            markers[str(filepath)] = GPSCoordinates(
                latitude=float(entry.get("latitude", 0.0)),
                longitude=float(entry.get("longitude", 0.0)),
                altitude=entry.get("altitude"),
            )
        except (TypeError, ValueError):
            continue
    return markers


def _load_page_editor_state(raw: Dict[str, Any]) -> PageEditorState:
    map_source = raw.get("map_source")
    if map_source not in (MAP_SOURCE_TILES, MAP_SOURCE_CUSTOM):
        map_source = MAP_SOURCE_TILES

    def _parse_int(value: Any, fallback: int = 0) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return fallback

    custom_map_path = raw.get("custom_map_path")
    if not isinstance(custom_map_path, str) or not custom_map_path.strip():
        custom_map_path = None

    return PageEditorState(
        map_source=map_source,
        gps_overrides=_normalize_gps_markers(raw.get("markers", [])),
        custom_map_path=custom_map_path,
        custom_marker_overrides=_normalize_custom_markers(raw.get("custom_markers", [])),
        custom_autoplot_enabled=(
            raw.get("custom_autoplot_enabled")
            if isinstance(raw.get("custom_autoplot_enabled"), bool)
            else True
        ),
        heading=_parse_int(raw.get("heading"), 0),
        custom_heading=_parse_int(raw.get("custom_heading"), _parse_int(raw.get("heading"), 0)),
        tile_view=raw.get("tile_view") if isinstance(raw.get("tile_view"), dict) else {},
        custom_view=raw.get("custom_view") if isinstance(raw.get("custom_view"), dict) else {},
    )


def _load_overrides(
    overrides_path: Path,
) -> tuple[
    int,
    int,
    int,
    Dict[str, GPSCoordinates],
    Optional[str],
    Dict[str, PixelPoint],
    bool,
    Dict[str, str],
    Dict[str, str],
    Dict[str, str],
    GroupAssignments,
    str,
    PageAssignments,
    bool,
    bool,
]:
    marker_size = 96
    heading = 0
    custom_heading = heading
    overrides: Dict[str, GPSCoordinates] = {}
    custom_map_path: Optional[str] = None
    custom_markers: Dict[str, PixelPoint] = {}
    custom_autoplot_enabled = True
    photo_aliases: Dict[str, str] = {}
    group_aliases: Dict[str, str] = {}
    photo_notes: Dict[str, str] = {}
    group_assignments = GroupAssignments()
    assignment_mode = "group"
    page_assignments = PageAssignments()
    hide_markers = False
    hide_sidebar = False

    if overrides_path.exists():
        try:
            data = json.loads(overrides_path.read_text(encoding="utf-8"))
            raw_assignment_mode = data.get("assignment_mode")
            if raw_assignment_mode in ("group", "page"):
                assignment_mode = raw_assignment_mode
            marker_size = int(data.get("marker_size", marker_size))
            if isinstance(data.get("hide_markers"), bool):
                hide_markers = data["hide_markers"]
            if isinstance(data.get("hide_sidebar"), bool):
                hide_sidebar = data["hide_sidebar"]
            heading = int(data.get("heading", heading))
            raw_custom_heading = data.get("custom_heading", heading)
            try:
                custom_heading = int(float(raw_custom_heading))
            except (TypeError, ValueError):
                custom_heading = heading
            markers = data.get("markers", [])
            for item in markers:
                filepath = item.get("filepath")
                if not filepath:
                    continue
                overrides[filepath] = GPSCoordinates(
                    latitude=float(item.get("latitude", 0.0)),
                    longitude=float(item.get("longitude", 0.0)),
                    altitude=item.get("altitude"),
                )
            custom_map_path = data.get("custom_map_path") if isinstance(data.get("custom_map_path"), str) else None
            custom_markers = _normalize_custom_markers(data.get("custom_markers", []))
            raw_autoplot = data.get("custom_autoplot_enabled")
            if isinstance(raw_autoplot, bool):
                custom_autoplot_enabled = raw_autoplot
            raw_photo_aliases = data.get("photo_aliases", {})
            if isinstance(raw_photo_aliases, dict):
                for filepath, name in raw_photo_aliases.items():
                    if not isinstance(filepath, str) or not isinstance(name, str):
                        continue
                    cleaned = name.strip()
                    if cleaned:
                        photo_aliases[filepath] = cleaned
            raw_group_aliases = data.get("group_aliases", {})
            if isinstance(raw_group_aliases, dict):
                for group_id, name in raw_group_aliases.items():
                    if not isinstance(group_id, str) or not isinstance(name, str):
                        continue
                    cleaned = name.strip()
                    if cleaned:
                        group_aliases[group_id] = cleaned
            raw_groups = data.get("groups", [])
            if isinstance(raw_groups, list):
                default_defs = {group["id"]: group for group in DEFAULT_GROUPS}
                for entry in raw_groups:
                    if not isinstance(entry, dict):
                        continue
                    group_id = entry.get("id")
                    if not isinstance(group_id, str):
                        continue
                    group_id = group_id.strip()
                    if not group_id:
                        continue
                    name = entry.get("name")
                    color = entry.get("color")
                    name_value = name.strip() if isinstance(name, str) else ""
                    color_value = color.strip() if isinstance(color, str) else ""
                    if group_id in group_assignments.groups:
                        if name_value:
                            group_assignments.groups[group_id].name = name_value
                        if color_value:
                            group_assignments.groups[group_id].color = color_value
                        continue
                    default_def = default_defs.get(group_id)
                    fallback_name = default_def["name"] if default_def else group_id
                    fallback_color = default_def["color"] if default_def else "default"
                    group_assignments.groups[group_id] = PhotoGroup(
                        id=group_id,
                        name=name_value or fallback_name,
                        color=color_value or fallback_color,
                    )
            raw_group_assignments = data.get("group_assignments", {})
            if isinstance(raw_group_assignments, dict):
                for filepath, group_id in raw_group_assignments.items():
                    if not isinstance(filepath, str) or not isinstance(group_id, str):
                        continue
                    if group_id not in group_assignments.groups:
                        continue
                    group_assignments.assign_photo(filepath, group_id)
            raw_pages = data.get("pages", [])
            if isinstance(raw_pages, list):
                loaded_pages: Dict[str, PhotoPage] = {}
                for entry in raw_pages:
                    if not isinstance(entry, dict):
                        continue
                    page_id = entry.get("id")
                    if not isinstance(page_id, str):
                        continue
                    page_id = page_id.strip()
                    if not page_id:
                        continue
                    name = entry.get("name")
                    name_value = name.strip() if isinstance(name, str) and name.strip() else page_id
                    loaded_pages[page_id] = PhotoPage(
                        id=page_id,
                        name=name_value,
                        locked=bool(entry.get("locked")) or page_id == DEFAULT_PAGE_ID,
                        editor_state=_load_page_editor_state(entry),
                    )
                if loaded_pages:
                    page_assignments = PageAssignments(loaded_pages)
            raw_page_assignments = data.get("page_assignments", {})
            if isinstance(raw_page_assignments, dict):
                for filepath, page_id in raw_page_assignments.items():
                    if not isinstance(filepath, str) or not isinstance(page_id, str):
                        continue
                    if page_id not in page_assignments.pages:
                        continue
                    page_assignments.assign_photo(filepath, page_id)
            raw_photo_notes = data.get("photo_notes", {})
            if isinstance(raw_photo_notes, dict):
                for filepath, note in raw_photo_notes.items():
                    if not isinstance(filepath, str) or not isinstance(note, str):
                        continue
                    cleaned = note.strip()
                    if cleaned:
                        photo_notes[filepath] = cleaned
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            pass

    return (
        marker_size,
        heading,
        custom_heading,
        overrides,
        custom_map_path,
        custom_markers,
        custom_autoplot_enabled,
        photo_aliases,
        group_aliases,
        photo_notes,
        group_assignments,
        assignment_mode,
        page_assignments,
        hide_markers,
        hide_sidebar,
    )


def _apply_overrides(state: AppState, payload: Dict[str, Any]) -> None:
    markers = payload.get("markers")
    marker_size = int(payload.get("marker_size", state.marker_size))
    if isinstance(payload.get("hide_markers"), bool):
        state.hide_markers = payload["hide_markers"]
    if isinstance(payload.get("hide_sidebar"), bool):
        state.hide_sidebar = payload["hide_sidebar"]
    raw_assignment_mode = payload.get("assignment_mode")
    if raw_assignment_mode in ("group", "page"):
        state.assignment_mode = raw_assignment_mode
    raw_heading = payload.get("heading")
    raw_custom_heading = payload.get("custom_heading")
    map_source = payload.get("map_source")
    heading = state.heading
    custom_heading = state.custom_heading
    parsed_heading: Optional[int] = None
    parsed_custom_heading: Optional[int] = None
    if raw_heading is not None:
        try:
            parsed_heading = int(float(raw_heading))
        except (TypeError, ValueError):
            parsed_heading = None
    if raw_custom_heading is not None:
        try:
            parsed_custom_heading = int(float(raw_custom_heading))
        except (TypeError, ValueError):
            parsed_custom_heading = None

    if map_source == "custom":
        if parsed_custom_heading is not None:
            custom_heading = parsed_custom_heading
            if parsed_heading is not None:
                heading = parsed_heading
        elif parsed_heading is not None:
            custom_heading = parsed_heading
    else:
        if parsed_heading is not None:
            heading = parsed_heading
        if parsed_custom_heading is not None:
            custom_heading = parsed_custom_heading
    custom_markers_raw = payload.get("custom_markers")
    custom_map_path = payload.get("custom_map_path")
    custom_autoplot_enabled = payload.get("custom_autoplot_enabled")

    if markers is not None:
        overrides: Dict[str, GPSCoordinates] = {}
        for item in markers:
            filepath = item.get("filepath")
            if not filepath:
                continue
            overrides[filepath] = GPSCoordinates(
                latitude=float(item.get("latitude", 0.0)),
                longitude=float(item.get("longitude", 0.0)),
                altitude=item.get("altitude"),
            )
        state.gps_overrides = overrides

    if custom_markers_raw is not None:
        custom_overrides: Dict[str, PixelPoint] = {}
        for item in custom_markers_raw:
            filepath = item.get("filepath")
            if not filepath:
                continue
            try:
                custom_overrides[filepath] = PixelPoint(
                    float(item.get("x", 0.0)),
                    float(item.get("y", 0.0)),
                )
            except (TypeError, ValueError):
                continue
        state.custom_marker_overrides = custom_overrides

    if custom_map_path is not None:
        cleaned_path = str(custom_map_path).strip()
        state.custom_map_path = cleaned_path if cleaned_path else None

    if isinstance(custom_autoplot_enabled, bool):
        state.custom_autoplot_enabled = custom_autoplot_enabled

    raw_pages = payload.get("pages")
    has_page_assignments_payload = isinstance(payload.get("page_assignments"), dict)
    if isinstance(raw_pages, list):
        loaded_pages: Dict[str, PhotoPage] = {}
        for entry in raw_pages:
            if not isinstance(entry, dict):
                continue
            page_id = entry.get("id")
            if not isinstance(page_id, str):
                continue
            page_id = page_id.strip()
            if not page_id:
                continue
            name = entry.get("name")
            name_value = name.strip() if isinstance(name, str) and name.strip() else page_id
            existing_page = state.page_assignments.pages.get(page_id)
            photo_paths = (
                list(existing_page.photo_paths)
                if existing_page and not has_page_assignments_payload
                else []
            )
            loaded_pages[page_id] = PhotoPage(
                id=page_id,
                name=name_value,
                photo_paths=photo_paths,
                locked=bool(entry.get("locked")) or page_id == DEFAULT_PAGE_ID,
                editor_state=_load_page_editor_state(entry),
            )
        if loaded_pages:
            if not has_page_assignments_payload:
                for existing_id, existing_page in state.page_assignments.pages.items():
                    if existing_id not in loaded_pages:
                        loaded_pages[existing_id] = existing_page
            state.page_assignments = PageAssignments(loaded_pages)

    page_editor_states = payload.get("page_editor_states")
    if isinstance(page_editor_states, dict):
        for page_id, page_payload in page_editor_states.items():
            if not isinstance(page_id, str) or not isinstance(page_payload, dict):
                continue
            page = state.page_assignments.get_page(page_id)
            if not page:
                continue
            page.editor_state = _load_page_editor_state(page_payload)

    page_assignments_raw = payload.get("page_assignments")
    if isinstance(page_assignments_raw, dict):
        for page in state.page_assignments.pages.values():
            page.photo_paths = []
        for filepath, page_id in page_assignments_raw.items():
            if not isinstance(filepath, str) or not isinstance(page_id, str):
                continue
            state.page_assignments.assign_photo(filepath, page_id)

    state.marker_size = marker_size
    state.heading = heading
    state.custom_heading = custom_heading
    _sync_group_assignments_state(state, prune_photos=bool(state.selected_files))
    _sync_page_assignments_state(state, prune_photos=bool(state.selected_files))

    data = _serialize_overrides_state(state)
    state.overrides_path.parent.mkdir(parents=True, exist_ok=True)
    state.overrides_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _serialize_overrides_state(state: AppState) -> Dict[str, Any]:
    """Return the full editor-overrides payload (mirrors map_overrides.json).
    Used both to persist global overrides and to embed per-project state in
    the saved project JSON so background image and placements round-trip."""
    markers_payload = []
    for filepath, gps in state.gps_overrides.items():
        markers_payload.append({
            "filepath": filepath,
            "latitude": gps.latitude,
            "longitude": gps.longitude,
            "altitude": gps.altitude,
        })

    custom_markers_payload = []
    for filepath, pixel in state.custom_marker_overrides.items():
        custom_markers_payload.append({
            "filepath": filepath,
            "x": pixel.x,
            "y": pixel.y,
        })

    photo_aliases_payload = {
        filepath: name
        for filepath, name in state.photo_aliases.items()
        if filepath and name
    }
    group_aliases_payload = {
        group_id: name
        for group_id, name in state.group_aliases.items()
        if group_id and name
    }
    photo_notes_payload = {
        filepath: note
        for filepath, note in state.photo_notes.items()
        if filepath and note
    }
    groups_payload, group_assignments_payload = _serialize_group_state(state)
    pages_payload, page_assignments_payload = _serialize_page_state(state)

    return {
        "assignment_mode": state.assignment_mode,
        "marker_size": state.marker_size,
        "hide_markers": state.hide_markers,
        "hide_sidebar": state.hide_sidebar,
        "heading": state.heading,
        "custom_heading": state.custom_heading,
        "markers": markers_payload,
        "custom_map_path": state.custom_map_path,
        "custom_markers": custom_markers_payload,
        "custom_autoplot_enabled": state.custom_autoplot_enabled,
        "photo_aliases": photo_aliases_payload,
        "groups": groups_payload,
        "group_assignments": group_assignments_payload,
        "group_aliases": group_aliases_payload,
        "pages": pages_payload,
        "page_assignments": page_assignments_payload,
        "photo_notes": photo_notes_payload,
    }


def _build_html(state: AppState) -> str:
    template_path = get_asset_path("app.html")
    html = template_path.read_text(encoding="utf-8")

    marker_path = get_asset_path("marker_outlined_transparent.png")
    marker_b64 = ""
    if marker_path.exists():
        marker_b64 = base64.b64encode(marker_path.read_bytes()).decode("utf-8")

    initial_state = {
        "api_key": get_google_maps_api_key() or "",
        "oauth_client_id": get_oauth_client_id() or "",
        "oauth_client_secret": get_oauth_client_secret() or "",
        "has_refresh_token": bool(get_oauth_refresh_token()),
        "marker_size": state.marker_size,
        "hide_markers": state.hide_markers,
        "hide_sidebar": state.hide_sidebar,
        "heading": state.heading,
        "assignment_mode": state.assignment_mode,
        "heic_supported": HEIC_SUPPORTED,
        "projects": _list_projects(),
    }

    html = html.replace("__INITIAL_STATE__", json.dumps(initial_state))
    html = html.replace("__MARKER_ICON__", f"data:image/png;base64,{marker_b64}")
    html = html.replace("__EXPORT_MAX_DIM__", str(EXPORT_MAX_DIM))
    return html


def _path_to_uri(path: str) -> str:
    try:
        return Path(path).resolve().as_uri()
    except (ValueError, OSError):
        return ""


def _guess_mime_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext in (".tif", ".tiff"):
        return "image/tiff"
    return "application/octet-stream"


def _image_to_data_uri(path: str) -> str:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return ""
    mime = _guess_mime_type(path)
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _image_to_preview_data_uri(
    path: str,
    max_dimension: int = PHOTO_PREVIEW_MAX_DIM,
    quality: int = PHOTO_PREVIEW_QUALITY,
) -> str:
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "P", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                alpha = img.split()[-1] if img.mode in ("RGBA", "LA") else None
                background.paste(img, mask=alpha)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return ""


def _write_html_file(html: str) -> str:
    cache_dir = CONFIG_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = f"app_{uuid.uuid4().hex}.html"
    path = cache_dir / filename
    path.write_text(html, encoding="utf-8")
    return str(path)


def _clamp_lat(lat: float) -> float:
    return max(min(lat, 85.0), -85.0)


def _latlon_to_world_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    lat = _clamp_lat(lat)
    siny = math.sin(math.radians(lat))
    siny = min(max(siny, -0.9999), 0.9999)
    x = TILE_SIZE * (0.5 + lon / 360.0)
    y = TILE_SIZE * (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi))
    scale = 2 ** zoom
    return x * scale, y * scale


def _compute_base_size(width: int, height: int, heading: float) -> tuple[int, int]:
    if not heading:
        return width, height
    angle = math.radians(abs(heading) % 360)
    cos_a = abs(math.cos(angle))
    sin_a = abs(math.sin(angle))
    base_w = int(math.ceil(width * cos_a + height * sin_a))
    base_h = int(math.ceil(width * sin_a + height * cos_a))
    return base_w, base_h


def _fetch_tile_image(x: int, y: int, z: int, api_key: str) -> Optional[Image.Image]:
    headers = {"User-Agent": "Mozilla/5.0"}
    host_index = (x + y + z) % len(TILE_HOSTS)
    key_param = f"&key={quote(api_key)}" if api_key else ""

    for attempt in range(len(TILE_HOSTS)):
        host = TILE_HOSTS[(host_index + attempt) % len(TILE_HOSTS)]
        url = TILE_URL.format(host=host, x=x, y=y, z=z)
        url = f"{url}{key_param}"
        try:
            with urlopen(Request(url, headers=headers), timeout=10, context=get_ssl_context()) as response:
                data = response.read()
            image = Image.open(io.BytesIO(data))
            return image.convert("RGB")
        except Exception:
            continue

    return None


def _stitch_tiles(
    center_lat: float,
    center_lon: float,
    zoom: int,
    width: int,
    height: int,
    api_key: str = "",
) -> tuple[Image.Image, float, float]:
    center_x, center_y = _latlon_to_world_pixel(center_lat, center_lon, zoom)
    left = center_x - width / 2
    top = center_y - height / 2

    max_tile = 2 ** zoom
    min_tile_x = int(math.floor(left / TILE_SIZE))
    max_tile_x = int(math.floor((left + width - 1) / TILE_SIZE))
    min_tile_y = int(math.floor(top / TILE_SIZE))
    max_tile_y = int(math.floor((top + height - 1) / TILE_SIZE))

    image = Image.new("RGB", (width, height), (0, 0, 0))
    tiles_to_fetch = []

    for ty in range(min_tile_y, max_tile_y + 1):
        if ty < 0 or ty >= max_tile:
            continue
        for tx in range(min_tile_x, max_tile_x + 1):
            tile_x = tx % max_tile
            tiles_to_fetch.append((tile_x, ty, tx))

    tile_results: Dict[tuple[int, int, int], Image.Image] = {}
    if tiles_to_fetch:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(_fetch_tile_image, tile_x, ty, zoom, api_key): (tile_x, ty, tx)
                for tile_x, ty, tx in tiles_to_fetch
            }
            for future in as_completed(futures):
                tile_x, ty, tx = futures[future]
                tile = future.result()
                if tile is None:
                    continue
                tile_results[(tile_x, ty, tx)] = tile

    for (tile_x, ty, tx), tile in tile_results.items():
        dest_x = int(round(tx * TILE_SIZE - left))
        dest_y = int(round(ty * TILE_SIZE - top))
        image.paste(tile, (dest_x, dest_y))

    return image, left, top


def _rotate_point(x: float, y: float, center_x: float, center_y: float, heading: float) -> tuple[float, float]:
    if not heading:
        return x, y
    angle = math.radians(-heading)
    dx = x - center_x
    dy = y - center_y
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rx = dx * cos_a - dy * sin_a + center_x
    ry = dx * sin_a + dy * cos_a + center_y
    return rx, ry


def _save_map_image(map_image: Image.Image) -> str:
    cache_dir = CONFIG_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = f"map_export_{uuid.uuid4().hex}.png"
    path = cache_dir / filename
    map_image.save(path, format="PNG")
    return str(path)


def _save_rotated_custom_map_image(map_image: Image.Image, source_path: str) -> str:
    cache_dir = CONFIG_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(source_path).suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        filename = f"custom_map_rotated_{uuid.uuid4().hex}.jpg"
        path = cache_dir / filename
        if "A" in map_image.getbands():
            map_image = map_image.convert("RGB")
        map_image.save(path, format="JPEG", quality=95)
        return str(path)

    filename = f"custom_map_rotated_{uuid.uuid4().hex}.png"
    path = cache_dir / filename
    map_image.save(path, format="PNG")
    return str(path)


def _rotate_custom_marker_pixels(
    marker_pixels: List[PixelPoint],
    original_size: tuple[int, int],
    heading: float,
    rotated_size: tuple[int, int],
) -> List[PixelPoint]:
    if not heading:
        return marker_pixels
    center_x = original_size[0] / 2
    center_y = original_size[1] / 2
    new_center_x = rotated_size[0] / 2
    new_center_y = rotated_size[1] / 2
    angle = math.radians(-heading)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rotated: List[PixelPoint] = []
    for pixel in marker_pixels:
        dx = pixel.x - center_x
        dy = pixel.y - center_y
        rx = dx * cos_a - dy * sin_a + new_center_x
        ry = dx * sin_a + dy * cos_a + new_center_y
        rotated.append(PixelPoint(rx, ry))
    return rotated


def _rotate_custom_map_for_export(
    image_path: str,
    marker_pixels: List[PixelPoint],
    heading: float,
) -> tuple[str, List[PixelPoint]]:
    normalized_heading = heading % 360
    if not normalized_heading:
        return image_path, marker_pixels

    with Image.open(image_path) as img:
        original_size = img.size
        has_alpha = "A" in img.getbands()
        base = img.convert("RGBA" if has_alpha else "RGB")
        fill = (0, 0, 0, 0) if has_alpha else (0, 0, 0)
        rotated = base.rotate(
            normalized_heading,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=fill,
        )
        rotated_size = rotated.size
        rotated_path = _save_rotated_custom_map_image(rotated, image_path)

    rotated_markers = _rotate_custom_marker_pixels(
        marker_pixels,
        original_size,
        normalized_heading,
        rotated_size,
    )
    return rotated_path, rotated_markers


def _rotate_map_for_export(
    map_image: Image.Image,
    base_width: int,
    base_height: int,
    heading: float,
) -> tuple[Image.Image, float, float]:
    if not heading:
        return map_image, 0.0, 0.0
    rotated = map_image.rotate(
        heading,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        center=(base_width / 2, base_height / 2),
        fillcolor=(0, 0, 0),
    )
    expand_left = (rotated.size[0] - base_width) / 2
    expand_top = (rotated.size[1] - base_height) / 2
    return rotated, expand_left, expand_top


def _build_marker_pixels(
    markers: List[Dict[str, Any]],
    left: float,
    top: float,
    base_width: int,
    base_height: int,
    heading: float,
    crop_left: int,
    crop_top: int,
    zoom: int,
) -> List[Any]:
    pixels: List[PixelPoint] = []
    center_x = base_width / 2
    center_y = base_height / 2

    for marker in markers:
        lat = float(marker.get("latitude", 0.0))
        lon = float(marker.get("longitude", 0.0))
        point_x, point_y = _latlon_to_world_pixel(lat, lon, zoom)
        pixel_x = point_x - left
        pixel_y = point_y - top
        rotated_x, rotated_y = _rotate_point(pixel_x, pixel_y, center_x, center_y, heading)
        rotated_x -= crop_left
        rotated_y -= crop_top
        pixels.append(PixelPoint(rotated_x, rotated_y))

    return pixels


def _video_export_dict(
    filepath: str,
    drive_file_id: Optional[str],
    metadata: ImageMetadata,
    gps: GPSCoordinates,
    custom_name: str,
    note: str,
) -> Dict[str, Any]:
    """Build an export dict for a video item (no image bytes).

    Drive videos play via Drive's embed iframe; local videos reference a relative
    ``media/...`` URL whose bytes are uploaded at deploy time (see
    _collect_video_assets). Videos only play in the web deploy.
    """
    display_name = custom_name if custom_name else metadata.filename
    entry: Dict[str, Any] = {
        "filepath": filepath,
        "filename": metadata.filename,
        "display_name": display_name,
        "custom_name": custom_name,
        "note": note,
        "is_video": True,
        "gps": gps,
        "timestamp": metadata.timestamp,
    }
    if drive_file_id:
        entry["embed"] = True
        entry["video_url"] = get_video_embed_url(drive_file_id)
        entry["poster"] = get_image_url(drive_file_id, 1920)
    else:
        entry["embed"] = False
        entry["local_video_path"] = filepath
        entry["video_mime"] = video_mime_for(filepath)
        entry["video_url"] = ""  # resolved by _collect_video_assets() at deploy time
    return entry


def _collect_video_assets(processed_photos: List[Dict[str, Any]]) -> Dict[str, bytes]:
    """Assign relative media URLs to local-video dicts and collect their bytes.

    Mutates each local-video dict's ``video_url`` to ``media/<name>`` (in place,
    so nested page photo lists update by reference) and returns a mapping of
    site-absolute path -> bytes for NetlifyDeployer's extra_files. Drive videos
    (embed=True) stream from Drive and are skipped.
    """
    assets: Dict[str, bytes] = {}
    used: set = set()
    counter = 0
    for photo in processed_photos:
        if not photo.get("is_video"):
            continue
        local_path = photo.get("local_video_path")
        if not local_path:
            continue  # Drive video (embed) — nothing to upload
        try:
            data = Path(local_path).read_bytes()
        except OSError:
            continue
        stem = Path(local_path).stem
        ext = Path(local_path).suffix.lower() or ".mp4"
        safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in stem)[:48] or "video"
        name = f"{counter}_{safe}{ext}"
        while name in used:
            counter += 1
            name = f"{counter}_{safe}{ext}"
        used.add(name)
        counter += 1
        photo["video_url"] = f"media/{name}"
        assets[f"/media/{name}"] = data
    return assets


def _strip_video_markers(payload: Dict[str, Any], video_paths: set) -> int:
    """Remove video entries from the payload's marker lists in place.

    Used by KMZ + local single-file HTML, which don't support video playback.
    Returns the number of video markers removed.
    """
    removed = 0

    def strip_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        nonlocal removed
        kept = []
        for item in items:
            fp = item.get("filepath") if isinstance(item, dict) else None
            if fp in video_paths:
                removed += 1
            else:
                kept.append(item)
        return kept

    for key in ("markers", "custom_markers"):
        if isinstance(payload.get(key), list):
            payload[key] = strip_list(payload[key])
    for page in payload.get("pages") or []:
        if isinstance(page, dict):
            for key in ("markers", "custom_markers"):
                if isinstance(page.get(key), list):
                    page[key] = strip_list(page[key])
    return removed


def _process_single_photo(
    filepath: str,
    processor: ImageProcessor,
    metadata: ImageMetadata,
    gps: GPSCoordinates,
    custom_name: str,
    note: str,
    drive_file_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process a single photo for export (resize, compress, build metadata dict).

    This is the core processing function used by both custom and Google tiles export.
    Designed to be called in parallel using ThreadPoolExecutor.

    If drive_file_id is provided, downloads from Drive instead of local disk.
    """
    if is_video_format(filepath):
        return _video_export_dict(filepath, drive_file_id, metadata, gps, custom_name, note)
    if drive_file_id and api_key:
        raw_bytes = fetch_image_bytes(drive_file_id, api_key)
        image_data, filename = processor.process_image_bytes(raw_bytes, metadata.filename)
    else:
        image_data, filename = processor.process_image(filepath)
    display_name = custom_name if custom_name else metadata.filename

    return {
        "filepath": filepath,
        "filename": filename,
        "display_name": display_name,
        "custom_name": custom_name,
        "note": note,
        "image_data": image_data,
        "gps": gps,
        "timestamp": metadata.timestamp,
    }


def _process_custom_export(
    state: AppState,
    markers: List[Dict[str, Any]],
    compression_quality: int,
    max_workers: int = 4,
) -> tuple[List[Dict[str, Any]], List[PixelPoint]]:
    """
    Process photos for custom map export with parallel image processing.
    """
    processor = ImageProcessor(
        compression_quality=compression_quality,
        max_dimension=1920,
    )

    # Validate all markers first before processing
    validated_items = []
    for item in markers:
        filepath = item.get("filepath")
        if not filepath:
            raise ValueError("Custom marker missing filepath.")
        metadata = state.file_metadata.get(filepath)
        if not metadata:
            raise ValueError(f"Missing photo metadata for {Path(filepath).name}.")
        x = item.get("x")
        y = item.get("y")
        if x is None or y is None:
            raise ValueError(f"Missing custom placement for {Path(filepath).name}.")

        gps = metadata.gps or GPSCoordinates(latitude=0.0, longitude=0.0, altitude=None)
        custom_name = state.photo_aliases.get(filepath, "")
        note = state.photo_notes.get(filepath, "")

        validated_items.append({
            "filepath": filepath,
            "metadata": metadata,
            "gps": gps,
            "custom_name": custom_name,
            "note": note,
            "x": x,
            "y": y,
        })

    # Process photos in parallel
    results_map: Dict[str, Dict[str, Any]] = {}
    api_key = get_google_maps_api_key() or ""

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_single_photo,
                item["filepath"],
                processor,
                item["metadata"],
                item["gps"],
                item["custom_name"],
                item["note"],
                state.drive_sources.get(item["filepath"]),
                api_key if item["filepath"] in state.drive_sources else None,
            ): item["filepath"]
            for item in validated_items
        }

        for future in as_completed(futures):
            filepath = futures[future]
            results_map[filepath] = future.result()

    # Build output in original marker order
    processed_photos: List[Dict[str, Any]] = []
    marker_pixels: List[PixelPoint] = []

    for item in validated_items:
        processed_photos.append(results_map[item["filepath"]])
        marker_pixels.append(PixelPoint(float(item["x"]), float(item["y"])))

    return processed_photos, marker_pixels


def _process_marker_photos(
    state: AppState,
    marker_overrides: List[Dict[str, Any]],
    compression_quality: int,
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    """Process exactly the photos listed by marker_overrides, preserving marker order."""
    processor = ImageProcessor(
        compression_quality=compression_quality,
        max_dimension=1920,
    )

    validated_items = []
    for item in marker_overrides:
        filepath = item.get("filepath")
        if not filepath:
            raise ValueError("Marker missing filepath.")
        metadata = state.file_metadata.get(filepath)
        if not metadata:
            raise ValueError(f"Missing photo metadata for {Path(filepath).name}.")
        base_gps = metadata.gps
        gps = GPSCoordinates(
            latitude=float(item.get("latitude", base_gps.latitude if base_gps else 0.0)),
            longitude=float(item.get("longitude", base_gps.longitude if base_gps else 0.0)),
            altitude=item.get("altitude", base_gps.altitude if base_gps else None),
        )
        validated_items.append({
            "filepath": filepath,
            "metadata": metadata,
            "gps": gps,
            "custom_name": state.photo_aliases.get(filepath, ""),
            "note": state.photo_notes.get(filepath, ""),
        })

    results_map: Dict[str, Dict[str, Any]] = {}
    api_key = get_google_maps_api_key() or ""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_single_photo,
                item["filepath"],
                processor,
                item["metadata"],
                item["gps"],
                item["custom_name"],
                item["note"],
                state.drive_sources.get(item["filepath"]),
                api_key if item["filepath"] in state.drive_sources else None,
            ): item["filepath"]
            for item in validated_items
        }
        for future in as_completed(futures):
            filepath = futures[future]
            results_map[filepath] = future.result()

    return [results_map[item["filepath"]] for item in validated_items]


def _process_photos(
    state: AppState,
    marker_overrides: List[Dict[str, Any]],
    compression_quality: int,
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    """
    Process photos for Google tiles export with parallel image processing.
    """
    override_map = {
        item.get("filepath"): item
        for item in marker_overrides
        if item.get("filepath")
    }

    processor = ImageProcessor(
        compression_quality=compression_quality,
        max_dimension=1920,
    )

    # Prepare items for processing
    items_to_process = []
    for filepath in state.selected_files:
        metadata = state.file_metadata.get(filepath)
        if not metadata:
            continue

        override = override_map.get(filepath)
        gps = metadata.gps

        if not gps and not override:
            continue

        # Compute final GPS (apply override if present)
        if override:
            base_gps = metadata.gps
            gps = GPSCoordinates(
                latitude=override.get("latitude", base_gps.latitude if base_gps else 0.0),
                longitude=override.get("longitude", base_gps.longitude if base_gps else 0.0),
                altitude=override.get("altitude", base_gps.altitude if base_gps else None),
            )

        custom_name = state.photo_aliases.get(filepath, "")
        note = state.photo_notes.get(filepath, "")

        items_to_process.append({
            "filepath": filepath,
            "metadata": metadata,
            "gps": gps,
            "custom_name": custom_name,
            "note": note,
        })

    # Process photos in parallel
    results_map: Dict[str, Dict[str, Any]] = {}
    api_key = get_google_maps_api_key() or ""

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_single_photo,
                item["filepath"],
                processor,
                item["metadata"],
                item["gps"],
                item["custom_name"],
                item["note"],
                state.drive_sources.get(item["filepath"]),
                api_key if item["filepath"] in state.drive_sources else None,
            ): item["filepath"]
            for item in items_to_process
        }

        for future in as_completed(futures):
            filepath = futures[future]
            results_map[filepath] = future.result()

    # Build output in original file order
    processed_photos: List[Dict[str, Any]] = []
    for item in items_to_process:
        processed_photos.append(results_map[item["filepath"]])

    return processed_photos


def _build_drive_photo_dicts(
    state: AppState,
    marker_overrides: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build photo dicts with Drive image URLs for web deploy (no downloading)."""
    override_map = {
        item.get("filepath"): item
        for item in marker_overrides
        if item.get("filepath")
    }

    processed_photos: List[Dict[str, Any]] = []
    for filepath in state.selected_files:
        metadata = state.file_metadata.get(filepath)
        if not metadata:
            continue
        override = override_map.get(filepath)
        gps = metadata.gps
        if not gps and not override:
            continue
        if override:
            base_gps = metadata.gps
            gps = GPSCoordinates(
                latitude=override.get("latitude", base_gps.latitude if base_gps else 0.0),
                longitude=override.get("longitude", base_gps.longitude if base_gps else 0.0),
                altitude=override.get("altitude", base_gps.altitude if base_gps else None),
            )
        custom_name = state.photo_aliases.get(filepath, "")
        display_name = custom_name if custom_name else metadata.filename
        note = state.photo_notes.get(filepath, "")
        file_id = state.drive_sources[filepath]

        if is_video_format(filepath):
            processed_photos.append(
                _video_export_dict(filepath, file_id, metadata, gps, custom_name, note)
            )
            continue

        processed_photos.append({
            "filepath": filepath,
            "filename": metadata.filename,
            "display_name": display_name,
            "custom_name": custom_name,
            "note": note,
            "image_url": get_image_url(file_id, 1920),
            "gps": gps,
            "timestamp": metadata.timestamp,
        })

    return processed_photos


def _build_drive_photo_dicts_for_markers(
    state: AppState,
    marker_overrides: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build Drive URL photo dicts for exactly the marker list order."""
    processed_photos: List[Dict[str, Any]] = []
    for item in marker_overrides:
        filepath = item.get("filepath")
        if not filepath:
            continue
        metadata = state.file_metadata.get(filepath)
        if not metadata:
            continue
        base_gps = metadata.gps
        gps = GPSCoordinates(
            latitude=float(item.get("latitude", base_gps.latitude if base_gps else 0.0)),
            longitude=float(item.get("longitude", base_gps.longitude if base_gps else 0.0)),
            altitude=item.get("altitude", base_gps.altitude if base_gps else None),
        )
        custom_name = state.photo_aliases.get(filepath, "")
        display_name = custom_name if custom_name else metadata.filename
        note = state.photo_notes.get(filepath, "")
        file_id = state.drive_sources[filepath]

        if is_video_format(filepath):
            processed_photos.append(
                _video_export_dict(filepath, file_id, metadata, gps, custom_name, note)
            )
            continue

        processed_photos.append({
            "filepath": filepath,
            "filename": metadata.filename,
            "display_name": display_name,
            "custom_name": custom_name,
            "note": note,
            "image_url": get_image_url(file_id, 1920),
            "gps": gps,
            "timestamp": metadata.timestamp,
        })

    return processed_photos


def _build_drive_custom_export(
    state: AppState,
    markers: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[PixelPoint]]:
    """Build photo dicts with Drive image URLs for custom map web deploy."""
    processed_photos: List[Dict[str, Any]] = []
    marker_pixels: List[PixelPoint] = []

    for item in markers:
        filepath = item.get("filepath")
        if not filepath:
            continue
        metadata = state.file_metadata.get(filepath)
        if not metadata:
            continue
        x = item.get("x")
        y = item.get("y")
        if x is None or y is None:
            continue

        gps = metadata.gps or GPSCoordinates(latitude=0.0, longitude=0.0, altitude=None)
        custom_name = state.photo_aliases.get(filepath, "")
        display_name = custom_name if custom_name else metadata.filename
        note = state.photo_notes.get(filepath, "")
        file_id = state.drive_sources[filepath]

        if is_video_format(filepath):
            processed_photos.append(
                _video_export_dict(filepath, file_id, metadata, gps, custom_name, note)
            )
        else:
            processed_photos.append({
                "filepath": filepath,
                "filename": metadata.filename,
                "display_name": display_name,
                "custom_name": custom_name,
                "note": note,
                "image_url": get_image_url(file_id, 1920),
                "gps": gps,
                "timestamp": metadata.timestamp,
            })
        marker_pixels.append(PixelPoint(float(x), float(y)))

    return processed_photos, marker_pixels


def _scaled_marker_size_for_page(
    page_payload: Dict[str, Any],
    default_marker_size: int,
    export_width: Optional[int] = None,
    export_height: Optional[int] = None,
) -> int:
    marker_size = int(page_payload.get("marker_size", default_marker_size))
    map_source = page_payload.get("map_source", MAP_SOURCE_TILES)
    if map_source == MAP_SOURCE_CUSTOM:
        custom_zoom = page_payload.get("custom_zoom")
        try:
            zoom = float(custom_zoom)
            if zoom > 0:
                return max(1, int(round(marker_size / zoom)))
        except (TypeError, ValueError):
            return marker_size
        return marker_size

    viewport_width = page_payload.get("viewport_width")
    viewport_height = page_payload.get("viewport_height")
    scale = None
    try:
        if viewport_width and export_width:
            scale = float(export_width) / float(viewport_width)
        elif viewport_height and export_height:
            scale = float(export_height) / float(viewport_height)
    except (TypeError, ValueError, ZeroDivisionError):
        scale = None
    if scale and scale > 0:
        return max(1, int(round(marker_size * scale)))
    return marker_size


def _build_multi_page_export_pages(
    state: AppState,
    payload: Dict[str, Any],
    use_drive_urls: bool = False,
) -> List[Dict[str, Any]]:
    pages_payload = payload.get("pages", [])
    if not isinstance(pages_payload, list) or not pages_payload:
        raise ValueError("No pages available to export.")

    compression_quality = int(payload.get("compression_quality", 30))
    default_marker_size = int(payload.get("marker_size", state.marker_size))
    api_key = get_google_maps_api_key() or ""
    export_pages: List[Dict[str, Any]] = []

    for page_payload in pages_payload:
        if not isinstance(page_payload, dict):
            continue
        map_source = page_payload.get("map_source", MAP_SOURCE_TILES)
        page_name = page_payload.get("name") or "Page"

        if map_source == MAP_SOURCE_CUSTOM:
            custom_markers = page_payload.get("custom_markers", [])
            if not custom_markers:
                continue
            custom_image_path = page_payload.get("custom_image_path") or page_payload.get("custom_map_path")
            if not custom_image_path:
                raise ValueError(f"No custom image selected for {page_name}.")
            if not Path(custom_image_path).exists():
                raise ValueError(f"Custom image not found for {page_name}.")

            custom_filepaths = [m.get("filepath") for m in custom_markers if m.get("filepath")]
            all_drive_custom = custom_filepaths and all(
                fp in state.drive_sources for fp in custom_filepaths
            )
            if use_drive_urls and all_drive_custom:
                processed_photos, marker_pixels = _build_drive_custom_export(state, custom_markers)
            else:
                processed_photos, marker_pixels = _process_custom_export(
                    state,
                    custom_markers,
                    compression_quality,
                )

            heading = float(page_payload.get("heading", 0))
            export_image_path = custom_image_path
            if heading:
                export_image_path, marker_pixels = _rotate_custom_map_for_export(
                    custom_image_path,
                    marker_pixels,
                    heading,
                )

            with Image.open(export_image_path) as image:
                image_size = image.size
            image_bytes = Path(export_image_path).read_bytes()
            export_pages.append({
                "id": page_payload.get("id") or f"page-{len(export_pages) + 1}",
                "name": page_name,
                "aerial_image_bytes": image_bytes,
                "aerial_image_mime": _guess_mime_type(export_image_path),
                "aerial_image_size": image_size,
                "photos": processed_photos,
                "marker_pixels": marker_pixels,
                "marker_size": _scaled_marker_size_for_page(page_payload, default_marker_size),
            })
            continue

        markers = page_payload.get("markers", [])
        if not markers:
            continue

        map_state = page_payload.get("map_state", {})
        center = map_state.get("center", {})
        zoom = int(map_state.get("zoom", 19))
        heading = float(map_state.get("heading", page_payload.get("heading", 0)))
        export_width = int(map_state.get("width", EXPORT_MAX_DIM))
        export_height = int(map_state.get("height", EXPORT_MAX_DIM))

        base_width, base_height = _compute_base_size(export_width, export_height, heading)
        map_image, left, top = _stitch_tiles(
            float(center.get("lat", 0.0)),
            float(center.get("lng", 0.0)),
            zoom,
            base_width,
            base_height,
            api_key=api_key,
        )
        map_image, expand_left, expand_top = _rotate_map_for_export(
            map_image,
            base_width,
            base_height,
            heading,
        )

        rotated_width, rotated_height = map_image.size
        crop_left = int(round((rotated_width - export_width) / 2))
        crop_top = int(round((rotated_height - export_height) / 2))
        crop_box = (
            crop_left,
            crop_top,
            crop_left + export_width,
            crop_top + export_height,
        )
        map_image = map_image.crop(crop_box)
        crop_left -= expand_left
        crop_top -= expand_top

        buffer = io.BytesIO()
        map_image.save(buffer, format="PNG")
        map_image_bytes = buffer.getvalue()
        marker_pixels = _build_marker_pixels(
            markers,
            left,
            top,
            base_width,
            base_height,
            heading,
            crop_left,
            crop_top,
            zoom,
        )

        marker_filepaths = [item.get("filepath") for item in markers if item.get("filepath")]
        all_drive = marker_filepaths and all(fp in state.drive_sources for fp in marker_filepaths)
        if use_drive_urls and all_drive:
            processed_photos = _build_drive_photo_dicts_for_markers(state, markers)
        else:
            processed_photos = _process_marker_photos(state, markers, compression_quality)

        export_pages.append({
            "id": page_payload.get("id") or f"page-{len(export_pages) + 1}",
            "name": page_name,
            "aerial_image_bytes": map_image_bytes,
            "aerial_image_mime": "image/png",
            "aerial_image_size": map_image.size,
            "photos": processed_photos,
            "marker_pixels": marker_pixels,
            "marker_size": _scaled_marker_size_for_page(
                page_payload,
                default_marker_size,
                export_width=export_width,
                export_height=export_height,
            ),
        })

    if not export_pages:
        raise ValueError("No placed photos available.")
    return export_pages


def main() -> None:
    if sys.platform == "win32":
        try:
            import clr  # type: ignore
        except Exception as exc:
            raise SystemExit(
                "pywebview requires pythonnet on Windows. "
                "Install it with: pip install pythonnet"
            ) from exc

    overrides_path = CONFIG_DIR / "map_overrides.json"
    (
        marker_size,
        heading,
        custom_heading,
        overrides,
        custom_map_path,
        custom_markers,
        custom_autoplot_enabled,
        photo_aliases,
        group_aliases,
        photo_notes,
        group_assignments,
        assignment_mode,
        page_assignments,
        hide_markers,
        hide_sidebar,
    ) = _load_overrides(overrides_path)

    state = AppState(
        selected_files=[],
        file_metadata={},
        gps_overrides=overrides,
        custom_map_path=custom_map_path,
        custom_marker_overrides=custom_markers,
        custom_autoplot_enabled=custom_autoplot_enabled,
        marker_size=marker_size,
        heading=heading,
        custom_heading=custom_heading,
        output_folder=None,
        overrides_path=overrides_path,
        group_assignments=group_assignments,
        page_assignments=page_assignments,
        assignment_mode=assignment_mode,
        photo_aliases=photo_aliases,
        group_aliases=group_aliases,
        photo_notes=photo_notes,
        photo_previews={},
        drive_sources={},
        drive_folder_url=None,
        drive_access_token=None,
        hide_markers=hide_markers,
        hide_sidebar=hide_sidebar,
    )

    html = _build_html(state)
    html_path = _write_html_file(html)

    api = AppApi(state)

    def handle_closing(_window=None) -> None:
        api.on_closing()
        try:
            Path(html_path).unlink()
        except OSError:
            pass

    icon_path = get_window_icon_path()
    try:
        create_kwargs = dict(
            title="PicPlotter Auto",
            url=html_path,
            width=1200,
            height=820,
            resizable=True,
            js_api=api,
        )
        if icon_path:
            create_kwargs["icon"] = icon_path
        window = webview.create_window(**create_kwargs)
    except TypeError:
        window = webview.create_window(
            "PicPlotter Auto",
            url=html_path,
            width=1200,
            height=820,
            resizable=True,
            js_api=api,
        )
    if icon_path and hasattr(window, "icon"):
        try:
            window.icon = icon_path
        except Exception:
            pass
    api.attach_window(window)
    window.events.closing += handle_closing

    def apply_window_icon() -> None:
        set_window_icon("PicPlotter Auto", icon_path)

    webview.start(apply_window_icon, http_server=True, http_port=24816)


if __name__ == "__main__":
    main()

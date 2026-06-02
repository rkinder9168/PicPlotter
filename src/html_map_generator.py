"""
HTML Map Generator for PicPlotter.

Generates interactive HTML maps with an aerial image background and
clickable photo markers with lightbox viewing.
"""

import base64
import html
import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image

from src.config import get_asset_path, get_user_logo_path
from src.coordinate_transform import AffineTransform, PixelPoint
from src.exif_extractor import GPSCoordinates
from src.marker_utils import get_colorizer
from src.photo_groups import GroupAssignments, DEFAULT_GROUPS, PhotoGroup


def get_window_icon_path() -> Optional[str]:
    """Return a suitable window icon path for the current platform."""
    ico_asset = get_asset_path("icon.ico")
    if ico_asset.exists():
        return str(ico_asset)

    png_path = get_asset_path("marker_pin.png")
    if sys.platform != "win32":
        return str(png_path) if png_path.exists() else None

    if not png_path.exists():
        return None

    try:
        with Image.open(png_path) as img:
            img = img.convert("RGBA")
            max_side = max(img.size)
            square = Image.new("RGBA", (max_side, max_side), (0, 0, 0, 0))
            offset = ((max_side - img.size[0]) // 2, (max_side - img.size[1]) // 2)
            square.paste(img, offset)
            tmp_ico = Path(tempfile.gettempdir()) / "picplotter_marker_pin.ico"
            if not tmp_ico.exists():
                sizes = [
                    (16, 16),
                    (24, 24),
                    (32, 32),
                    (48, 48),
                    (64, 64),
                    (128, 128),
                    (256, 256),
                ]
                square.save(tmp_ico, format="ICO", sizes=sizes)
        return str(tmp_ico)
    except Exception:
        return None


def set_window_icon(title: str, icon_path: Optional[str]) -> None:
    """Apply a window icon on Windows when pywebview cannot set it directly."""
    if sys.platform != "win32" or not icon_path:
        return

    try:
        import ctypes
    except Exception:
        return

    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    pid = os.getpid()
    wm_seticon = 0x0080
    icon_small = 0
    icon_big = 1
    image_icon = 1
    lr_loadfromfile = 0x0010

    def apply_icon(hwnd: int) -> None:
        hicon = user32.LoadImageW(None, icon_path, image_icon, 0, 0, lr_loadfromfile)
        if hicon:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, hicon)
            user32.SendMessageW(hwnd, wm_seticon, icon_big, hicon)

    for _ in range(30):
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            apply_icon(hwnd)
            return

        hwnds = []

        def enum_cb(hwnd, _lparam):
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == pid:
                length = user32.GetWindowTextLengthW(hwnd)
                if length:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    if title and title not in buffer.value:
                        return True
                hwnds.append(hwnd)
            return True

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_cb)
        user32.EnumWindows(enum_proc, 0)
        if hwnds:
            for candidate in hwnds:
                apply_icon(candidate)
            return

        time.sleep(0.1)


class HTMLMapGenerator:
    """Generates interactive HTML photo maps."""

    # Marker display size in pixels (the asset is large, we resize it)
    MARKER_DISPLAY_SIZE = 96
    MARKER_ASSET_SIZE = 256
    DEFAULT_LOGO_FILENAME = "everline-horizontal-logo.jpg"
    LOGO_MAX_WIDTH = 317
    LOGO_MAX_HEIGHT = 92

    def __init__(
        self,
        project_name: str = "Photo Map",
        marker_size: int = 96,
        proposal_link: Optional[str] = None,
        download_photos_link: Optional[str] = None,
        client_name: Optional[str] = None,
        client_company: Optional[str] = None,
        client_address: Optional[str] = None,
        company_name: Optional[str] = None,
        company_address: Optional[str] = None,
        company_phone: Optional[str] = None,
        company_website: Optional[str] = None,
    ):
        """
        Initialize the HTML map generator.

        Args:
            project_name: Name for the map/project
            marker_size: Size of markers in pixels
            proposal_link: Optional proposal URL to show in the export header
            download_photos_link: Optional Dropbox (or other) URL where the
                client can download the source photos
            client_name: Optional client name to show in the export header
            client_company: Optional company name to show in the export header
            client_address: Optional address to show in the export header
            company_name: Optional preparing company name (for Prepared by block)
            company_address: Optional preparing company address
            company_phone: Optional preparing company phone
            company_website: Optional preparing company website
        """
        self.project_name = project_name
        self.marker_size = marker_size
        self.marker_asset_size = max(marker_size, self.MARKER_ASSET_SIZE)
        self.proposal_link = proposal_link.strip() if proposal_link else ""
        self.download_photos_link = download_photos_link.strip() if download_photos_link else ""
        self.client_name = client_name.strip() if client_name else ""
        self.client_company = client_company.strip() if client_company else ""
        self.client_address = client_address.strip() if client_address else ""
        self.company_name = company_name.strip() if company_name else ""
        self.company_address = company_address.strip() if company_address else ""
        self.company_phone = company_phone.strip() if company_phone else ""
        self.company_website = company_website.strip() if company_website else ""
        self._marker_b64: Optional[str] = None
        self._logo_b64: Optional[str] = None

    def _get_marker_image_b64(self) -> str:
        """Load and encode the marker icon as base64."""
        if self._marker_b64 is not None:
            return self._marker_b64

        marker_path = get_asset_path('marker_outlined_transparent.png')

        if marker_path.exists():
            # Load and resize the marker for web use
            with Image.open(marker_path) as img:
                # Resize to display size (original is very large)
                img = img.resize(
                    (self.marker_asset_size, self.marker_asset_size),
                    Image.Resampling.LANCZOS
                )

                # Convert to PNG bytes
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                self._marker_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        else:
            # Fallback: create a simple colored circle if asset not found
            self._marker_b64 = ""

        return self._marker_b64

    def _get_logo_image_src(self) -> str:
        """Load and encode the logo image as a data URI (user logo preferred)."""
        if self._logo_b64 is None:
            user_logo = get_user_logo_path()
            if user_logo is not None and user_logo.exists():
                logo_path = user_logo
            else:
                logo_path = get_asset_path(self.DEFAULT_LOGO_FILENAME)

            if logo_path.exists():
                with Image.open(logo_path) as img:
                    if img.mode not in ("RGB", "RGBA"):
                        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                    img.thumbnail(
                        (self.LOGO_MAX_WIDTH, self.LOGO_MAX_HEIGHT),
                        Image.Resampling.LANCZOS
                    )
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    self._logo_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            else:
                self._logo_b64 = ""
        if not self._logo_b64:
            return ""
        return f"data:image/png;base64,{self._logo_b64}"

    def generate_single_html(
        self,
        photos: List[Dict[str, Any]],
        aerial_image_path: Optional[str],
        transform: Optional[AffineTransform],
        output_path: Optional[str] = None,
        marker_pixels: Optional[List[PixelPoint]] = None,
        group_assignments: Optional[GroupAssignments] = None,
        group_aliases: Optional[Dict[str, str]] = None,
        aerial_image_bytes: Optional[bytes] = None,
        aerial_image_mime: Optional[str] = None,
        aerial_image_size: Optional[tuple[int, int]] = None,
        return_content: bool = False,
    ) -> str:
        """
        Generate a single self-contained HTML file with all images embedded as base64.

        Args:
            photos: List of photo dicts with 'image_data', 'gps', 'filename'
            aerial_image_path: Path to the aerial background image
            transform: Affine transform for GPS to pixel conversion (optional if marker_pixels provided)
            output_path: Output file path for the HTML (required unless return_content=True)
            marker_pixels: Optional pixel positions to use instead of GPS transform
            group_assignments: Optional photo group assignments for marker colors
            group_aliases: Optional group display names keyed by group id
            aerial_image_bytes: Optional aerial image bytes to embed instead of reading from disk
            aerial_image_mime: Optional MIME type when aerial_image_bytes is provided
            aerial_image_size: Optional (width, height) when aerial_image_bytes is provided
            return_content: If True, return HTML content string instead of writing to file

        Returns:
            Path to the generated HTML file, or HTML content string if return_content=True
        """
        if marker_pixels is not None and len(marker_pixels) != len(photos):
            raise ValueError("marker_pixels length must match photos")
        if marker_pixels is None and transform is None:
            raise ValueError("transform is required when marker_pixels is not provided")
        if aerial_image_bytes is None:
            if not aerial_image_path:
                raise ValueError("aerial_image_path is required when aerial_image_bytes is not provided")
            with open(aerial_image_path, 'rb') as f:
                aerial_data = f.read()
            mime_type = self._get_mime_type(aerial_image_path)
            with Image.open(aerial_image_path) as img:
                img_width, img_height = img.size
        else:
            aerial_data = aerial_image_bytes
            if aerial_image_mime:
                mime_type = aerial_image_mime
            elif aerial_image_path:
                mime_type = self._get_mime_type(aerial_image_path)
            else:
                mime_type = "image/png"
            if aerial_image_size:
                img_width, img_height = aerial_image_size
            else:
                with Image.open(io.BytesIO(aerial_data)) as img:
                    img_width, img_height = img.size

        aerial_b64 = base64.b64encode(aerial_data).decode('utf-8')
        aerial_src = f"data:{mime_type};base64,{aerial_b64}"

        colorizer = get_colorizer()
        unique_colors = set()
        photo_colors: Dict[str, str] = {}

        default_names = {group["id"]: group["name"] for group in DEFAULT_GROUPS}
        for photo in photos:
            filepath = photo.get("filepath", "")
            color = "default"
            if group_assignments:
                group = group_assignments.get_group_for_photo(filepath)
                if group:
                    color = group.color
            photo_colors[filepath] = color
            unique_colors.add(color)

        markers_by_color = {}
        for color in unique_colors:
            marker_bytes = colorizer.get_colored_marker_bytes(color, self.marker_asset_size)
            markers_by_color[color] = base64.b64encode(marker_bytes).decode("utf-8")

        legend_items = self._build_legend_items(photos, group_assignments, group_aliases)

        # Build photo data and markers
        photos_data = []
        markers_html = []

        default_group = group_assignments.get_group("default") if group_assignments else None
        for i, photo in enumerate(photos):
            # Encode photo - support video URLs, URL references, or base64
            if photo.get('is_video'):
                photo_src = str(photo.get('video_url') or "")
            elif 'image_url' in photo:
                photo_src = photo['image_url']
            else:
                photo_b64 = base64.b64encode(photo['image_data']).decode('utf-8')
                photo_src = f"data:image/jpeg;base64,{photo_b64}"
            filepath = photo.get("filepath", "")

            group = group_assignments.get_group_for_photo(filepath) if group_assignments else None
            if group is None:
                group = default_group
            if "custom_name" in photo:
                display_name = photo.get("custom_name") or ""
                if not display_name:
                    display_name = self._photo_title_for_group(group, default_names, group_aliases)
            else:
                display_name = photo.get("display_name") or photo.get("filename") or ""
                if not display_name:
                    display_name = self._photo_title_for_group(group, default_names, group_aliases)
            note = photo.get("note", "")
            photos_data.append({
                'src': photo_src,
                'filename': display_name,
                'note': note,
                'isVideo': bool(photo.get('is_video')),
                'embed': bool(photo.get('embed')),
                'poster': str(photo.get('poster') or ''),
            })

            # Calculate marker position
            if marker_pixels is not None:
                pixel = marker_pixels[i]
            else:
                pixel = transform.transform(photo['gps'])
            color = photo_colors.get(filepath, "default")
            markers_html.append(self._create_marker_html(i, pixel, color))

        # Generate HTML
        html_content = self._generate_html(
            aerial_src=aerial_src,
            image_width=img_width,
            image_height=img_height,
            markers_html='\n        '.join(markers_html),
            photos_json=json.dumps(photos_data),
            markers_by_color=markers_by_color,
            legend_items=legend_items,
        )

        if return_content:
            return html_content

        # Write file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return output_path

    def generate_multi_page_html(
        self,
        pages: List[Dict[str, Any]],
        output_path: Optional[str] = None,
        return_content: bool = False,
    ) -> str:
        """
        Generate a self-contained multi-page interactive HTML deliverable.

        Each page dict must include a name, background image data or path,
        photos, and marker_pixels matching those photos.
        """
        if not pages:
            raise ValueError("At least one page is required")
        if not return_content and not output_path:
            raise ValueError("output_path is required unless return_content=True")

        page_data: List[Dict[str, Any]] = []
        for page_index, page in enumerate(pages):
            photos = page.get("photos") or []
            marker_pixels = page.get("marker_pixels") or []
            if len(marker_pixels) != len(photos):
                raise ValueError("marker_pixels length must match photos")

            aerial_src, image_width, image_height = self._page_aerial_src(page)
            photos_data: List[Dict[str, str]] = []
            markers_data: List[Dict[str, float]] = []
            legend_data: List[Dict[str, str]] = []

            for photo_index, photo in enumerate(photos):
                photo_src = self._photo_src(photo)
                display_name = (
                    photo.get("custom_name")
                    or photo.get("display_name")
                    or photo.get("filename")
                    or f"Photo {photo_index + 1}"
                )
                note = photo.get("note") or ""
                pixel = marker_pixels[photo_index]
                photos_data.append({
                    "src": photo_src,
                    "filename": str(display_name),
                    "note": str(note),
                    "isVideo": bool(photo.get("is_video")),
                    "embed": bool(photo.get("embed")),
                    "poster": str(photo.get("poster") or ""),
                })
                markers_data.append({
                    "x": float(pixel.x),
                    "y": float(pixel.y),
                    "index": photo_index,
                    "number": photo_index + 1,
                })
                legend_data.append({
                    "number": str(photo_index + 1),
                    "label": str(display_name),
                })

            page_data.append({
                "id": str(page.get("id") or f"page-{page_index + 1}"),
                "name": str(page.get("name") or f"Page {page_index + 1}"),
                "aerialSrc": aerial_src,
                "width": int(image_width),
                "height": int(image_height),
                "markerSize": int(page.get("marker_size") or self.marker_size),
                "photos": photos_data,
                "markers": markers_data,
                "legend": legend_data,
            })

        marker_bytes = get_colorizer().get_plain_marker_bytes(self.marker_asset_size)
        marker_src = f"data:image/png;base64,{base64.b64encode(marker_bytes).decode('utf-8')}"
        html_content = self._generate_multi_page_html(
            pages_json=json.dumps(page_data),
            plain_marker_src=marker_src,
        )

        if return_content:
            return html_content

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return output_path

    def _page_aerial_src(self, page: Dict[str, Any]) -> tuple[str, int, int]:
        aerial_data = page.get("aerial_image_bytes")
        aerial_path = page.get("aerial_image_path")
        if aerial_data is None:
            if not aerial_path:
                raise ValueError("Page background image is required")
            with open(aerial_path, "rb") as f:
                aerial_data = f.read()
            mime_type = self._get_mime_type(str(aerial_path))
            with Image.open(aerial_path) as img:
                image_width, image_height = img.size
        else:
            mime_type = page.get("aerial_image_mime") or "image/png"
            image_size = page.get("aerial_image_size")
            if image_size:
                image_width, image_height = image_size
            else:
                with Image.open(io.BytesIO(aerial_data)) as img:
                    image_width, image_height = img.size
        aerial_b64 = base64.b64encode(aerial_data).decode("utf-8")
        return f"data:{mime_type};base64,{aerial_b64}", int(image_width), int(image_height)

    def _photo_src(self, photo: Dict[str, Any]) -> str:
        if photo.get("is_video"):
            return str(photo.get("video_url") or "")
        if "image_url" in photo:
            return str(photo["image_url"])
        photo_b64 = base64.b64encode(photo["image_data"]).decode("utf-8")
        return f"data:image/jpeg;base64,{photo_b64}"

    def _generate_multi_page_html(
        self,
        pages_json: str,
        plain_marker_src: str,
    ) -> str:
        """Generate the complete multi-page HTML document."""
        marker_font_size = max(12, int(self.marker_size * 0.29))
        logo_src = self._get_logo_image_src()
        logo_html = (
            f'<img id="logo" src="{logo_src}" alt="Company logo">'
            if logo_src else ""
        )
        project_label = html.escape(self.project_name)
        safe_marker_src = html.escape(plain_marker_src, quote=True)

        prepared_by_html = self._build_prepared_by_html(self._format_multiline)
        client_info_html = self._build_client_info_html()
        proposal_link_html = self._build_proposal_link_html()
        download_link_html = self._build_download_link_html()
        divider_html = self._build_sidebar_divider_html(
            has_top=bool(prepared_by_html or logo_html),
            has_bottom=bool(client_info_html),
        )
        sidebar_brand_html = (
            f'<div id="sidebar-brand">{logo_html}{prepared_by_html}'
            f'{divider_html}{client_info_html}'
            f'{proposal_link_html}{download_link_html}</div>'
        )

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_label}</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        :root {{
            --sidebar-width: 260px;
            --marker-size: {self.marker_size}px;
            --marker-font-size: {marker_font_size}px;
            --plain-marker-image: url('{safe_marker_src}');
            --sidebar-border: #e3e1da;
            --sidebar-text: #1b1b1b;
            --viewport-bottom-inset: 0px;
        }}
        body {{
            overflow: hidden;
            background: #151515;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: var(--sidebar-text);
        }}
        #layout {{
            display: grid;
            grid-template-columns: var(--sidebar-width) 1fr;
            width: 100vw;
            height: 100vh;
        }}
        #sidebar {{
            background: #ffffff;
            border-right: 1px solid var(--sidebar-border);
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            overflow: hidden;
            min-height: 0;
        }}
        #sidebar-brand {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            flex: 0 0 auto;
        }}
        #logo {{
            max-width: 210px;
            max-height: {self.LOGO_MAX_HEIGHT}px;
            width: auto;
            height: auto;
            display: block;
            margin: 0 auto;
        }}
        #prepared-by {{
            width: 100%;
            padding: 0 4px;
            text-align: center;
            display: flex;
            flex-direction: column;
            gap: 4px;
            color: var(--sidebar-text);
        }}
        .prepared-name {{
            font-size: 13px;
            font-weight: 700;
            word-break: break-word;
        }}
        .prepared-line {{
            font-size: 12px;
            word-break: break-word;
        }}
        .prepared-line a {{
            color: #1f6feb;
            text-decoration: none;
        }}
        .prepared-line a:hover {{
            text-decoration: underline;
        }}
        .sidebar-divider {{
            width: 100%;
            height: 1px;
            background: var(--sidebar-border);
            margin: 4px 0;
        }}
        #client-info {{
            width: 100%;
            border: 1px solid var(--sidebar-border);
            border-radius: 6px;
            padding: 8px 10px;
            background: #f5f5f5;
            text-align: left;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .client-row {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        .client-label {{
            font-size: 10px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #6b6b6b;
        }}
        .client-value {{
            font-size: 12px;
            font-weight: 600;
            color: var(--sidebar-text);
            word-break: break-word;
        }}
        .sidebar-action-link {{
            color: #0b0f0d;
            background: #ffffff;
            font-size: 14px;
            font-weight: 600;
            padding: 6px 10px;
            border-radius: 4px;
            text-decoration: none;
            display: block;
            text-align: center;
            border: 1px solid var(--sidebar-border);
        }}
        .sidebar-action-link:hover {{
            text-decoration: underline;
        }}
        #page-nav {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            flex: 0 0 auto;
        }}
        .page-nav-button {{
            border: 1px solid var(--sidebar-border);
            background: #f6f6f6;
            color: #1b1b1b;
            border-radius: 6px;
            padding: 8px 10px;
            min-height: 40px;
            cursor: pointer;
            font-size: 12px;
            flex: 1 1 100px;
        }}
        .page-nav-button.active {{
            background: #0c1412;
            color: #ffffff;
            border-color: #0c1412;
        }}
        #page-legend {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            border-top: 1px solid var(--sidebar-border);
            padding-top: 12px;
            flex: 1 1 auto;
            min-height: 0;
            overflow-y: auto;
        }}
        .page-legend-heading {{
            font-size: 15px;
            font-weight: 700;
            text-align: center;
        }}
        .page-legend-row {{
            display: grid;
            grid-template-columns: 28px 1fr;
            align-items: center;
            gap: 8px;
            min-height: 32px;
            font-size: 13px;
        }}
        .page-legend-number {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border-radius: 4px;
            background: #0c1412;
            color: #ffffff;
            font-weight: 700;
            font-size: 12px;
        }}
        #content, #viewport {{
            position: relative;
            overflow: hidden;
            width: 100%;
            height: 100%;
        }}
        #map-container {{
            position: absolute;
            cursor: grab;
            transform-origin: 0 0;
        }}
        #map-container:active {{
            cursor: grabbing;
        }}
        #aerial-image {{
            width: 100%;
            height: 100%;
            display: block;
            user-select: none;
            -webkit-user-drag: none;
        }}
        .marker {{
            position: absolute;
            width: var(--marker-size);
            height: var(--marker-size);
            margin-left: calc(var(--marker-size) / -2);
            margin-top: calc(var(--marker-size) / -2);
            background-image: var(--plain-marker-image);
            background-size: contain;
            background-repeat: no-repeat;
            cursor: pointer;
            border: none;
            border-radius: 0;
            z-index: 10;
        }}
        .marker:hover {{
            transform: scale(1.18);
            z-index: 20;
        }}
        .marker-number {{
            position: absolute;
            right: 4%;
            bottom: 4%;
            min-width: 1em;
            padding: 0.15em 0.35em;
            border-radius: 4px;
            border: 1px solid rgba(0, 0, 0, 0.25);
            background: #ffffff;
            color: #111111;
            font-size: var(--marker-font-size);
            font-weight: 700;
            line-height: 1;
            text-align: center;
            pointer-events: none;
        }}
        #controls {{
            position: absolute;
            right: 16px;
            bottom: 16px;
            display: flex;
            gap: 8px;
            z-index: 50;
        }}
        .control-btn {{
            border: 1px solid var(--sidebar-border);
            background: rgba(255, 255, 255, 0.95);
            color: #1b1b1b;
            border-radius: 6px;
            padding: 8px 14px;
            min-height: 40px;
            min-width: 44px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
        }}
        .control-btn:hover {{
            background: #ffffff;
        }}
        #lightbox {{
            display: none;
            position: absolute;
            inset: 0;
            z-index: 1000;
            background: rgba(0, 0, 0, 0.94);
            align-items: center;
            justify-content: center;
            flex-direction: column;
            padding: 24px;
        }}
        #lightbox.active {{
            display: flex;
        }}
        #lightbox-img, #lightbox-video {{
            max-width: 94%;
            max-height: 82%;
            object-fit: contain;
        }}
        #lightbox-frame {{
            width: min(94%, 1280px);
            max-height: 82%;
            aspect-ratio: 16 / 9;
            border: none;
            background: #000000;
        }}
        #lightbox-video[hidden], #lightbox-frame[hidden], #lightbox-img[hidden] {{
            display: none !important;
        }}
        #lightbox-title, #lightbox-index, #lightbox-note {{
            color: #ffffff;
            margin-top: 10px;
            text-align: center;
            max-width: 90%;
            white-space: pre-wrap;
        }}
        #lightbox-title {{
            font-weight: 700;
        }}
        #lightbox-index, #lightbox-note {{
            font-size: 13px;
            opacity: 0.85;
        }}
        #lightbox-close {{
            position: absolute;
            top: 16px;
            right: 22px;
            width: 44px;
            height: 44px;
            border: none;
            background: transparent;
            color: #ffffff;
            font-size: 38px;
            cursor: pointer;
        }}
        #lightbox-nav {{
            position: absolute;
            bottom: 20px;
            display: flex;
            gap: 16px;
        }}
        .nav-btn {{
            border: none;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.2);
            color: #ffffff;
            padding: 10px 18px;
            min-height: 44px;
            cursor: pointer;
        }}
        .nav-icon {{
            display: none;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            line-height: 1;
        }}
        .nav-label {{
            display: inline;
        }}
        #sidebar-close {{
            display: none;
            position: sticky;
            top: 0;
            align-self: flex-end;
            margin-left: auto;
            width: 44px;
            height: 44px;
            border-radius: 22px;
            border: 1px solid var(--sidebar-border);
            background: #ffffff;
            color: #1b1b1b;
            font-size: 24px;
            line-height: 1;
            cursor: pointer;
            align-items: center;
            justify-content: center;
            z-index: 2;
        }}
        #sidebar-close:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}
        #sidebar-toggle {{
            display: none;
            position: fixed;
            top: 12px;
            left: 12px;
            z-index: 900;
            background: rgba(12, 20, 18, 0.92);
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.2);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            cursor: pointer;
            min-height: 44px;
            min-width: 44px;
            align-items: center;
            justify-content: center;
        }}
        #sidebar-toggle:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}
        #sidebar-scrim {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.45);
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
            z-index: 850;
        }}
        body.sidebar-open #sidebar-scrim {{
            opacity: 1;
            pointer-events: auto;
        }}
        @media (max-width: 1200px) and (min-width: 901px) {{
            :root {{
                --sidebar-width: clamp(200px, 22vw, 240px);
                --marker-size: clamp(72px, 6vw, {self.marker_size}px);
            }}
            #sidebar {{
                padding: 16px;
            }}
        }}
        @media (max-width: 900px) {{
            :root {{
                --marker-size: clamp(56px, 14vw, 80px);
                --marker-font-size: clamp(12px, 3vw, 18px);
            }}
            #layout {{
                grid-template-columns: 1fr;
                grid-template-rows: 1fr;
            }}
            #sidebar {{
                position: fixed;
                top: 0;
                left: 0;
                width: min(320px, 86vw);
                height: 100vh;
                height: 100dvh;
                max-height: 100dvh;
                padding-top: calc(52px + env(safe-area-inset-top));
                padding-bottom: calc(28px + env(safe-area-inset-bottom) + var(--viewport-bottom-inset));
                border-right: 1px solid var(--sidebar-border);
                border-bottom: none;
                transform: translateX(-105%);
                transition: transform 0.25s ease;
                z-index: 950;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
            }}
            body.sidebar-open #sidebar {{
                transform: translateX(0);
            }}
            #sidebar-toggle {{
                display: inline-flex;
                top: calc(12px + env(safe-area-inset-top));
                left: calc(12px + env(safe-area-inset-left));
            }}
            #sidebar-close {{
                display: inline-flex;
            }}
            #sidebar-scrim {{
                display: block;
            }}
            #controls {{
                display: none;
            }}
            #viewport,
            #map-container {{
                touch-action: none;
            }}
            #page-legend {{
                flex: 1 1 auto;
                min-height: 0;
                overflow-y: visible;
            }}
            .page-nav-button {{
                flex: 1 1 calc(50% - 6px);
                min-height: 44px;
                padding: 10px 12px;
                font-size: 13px;
                word-break: break-word;
            }}
            #lightbox {{
                padding: calc(12px + env(safe-area-inset-top)) 12px calc(72px + env(safe-area-inset-bottom) + var(--viewport-bottom-inset));
            }}
            #lightbox-img {{
                max-width: 96vw;
                max-height: 78vh;
            }}
            #lightbox-close {{
                top: calc(12px + env(safe-area-inset-top));
                right: calc(12px + env(safe-area-inset-right));
                width: 44px;
                height: 44px;
                font-size: 32px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                z-index: 1200;
                background: rgba(0, 0, 0, 0.4);
                border-radius: 22px;
            }}
            #lightbox-note {{
                max-height: 28vh;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
                font-size: 12px;
            }}
            #lightbox-nav {{
                top: 50%;
                bottom: auto;
                left: 0;
                right: 0;
                transform: translateY(-50%);
                justify-content: space-between;
                padding: 0 12px;
                pointer-events: none;
                gap: 0;
            }}
            #lightbox-nav .nav-btn {{
                pointer-events: auto;
                width: 44px;
                height: 44px;
                padding: 0;
                border-radius: 999px;
                font-size: 22px;
                background: rgba(255, 255, 255, 0.25);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}
            .nav-icon {{
                display: inline-flex;
            }}
            .nav-label {{
                display: none;
            }}
        }}
        @media (max-width: 480px) {{
            :root {{
                --marker-size: clamp(48px, 18vw, 70px);
                --marker-font-size: clamp(12px, 3.6vw, 16px);
            }}
            #sidebar {{
                width: 100vw;
            }}
            .marker::before {{
                content: "";
                position: absolute;
                top: 50%;
                left: 50%;
                width: calc(var(--marker-size) + 16px);
                height: calc(var(--marker-size) + 16px);
                transform: translate(-50%, -50%);
                border-radius: 999px;
                background: transparent;
                pointer-events: auto;
            }}
        }}
        @media (max-width: 900px) and (orientation: landscape) {{
            #sidebar {{
                width: min(300px, 70vw);
            }}
        }}
    </style>
</head>
<body>
    <div id="layout">
        <aside id="sidebar">
            <button id="sidebar-close" type="button" aria-label="Close sidebar">&times;</button>
            {sidebar_brand_html}
            <div id="page-nav" aria-label="Pages"></div>
            <div id="page-legend"></div>
        </aside>
        <main id="content">
            <div id="sidebar-scrim" aria-hidden="true"></div>
            <button id="sidebar-toggle" type="button" aria-label="Toggle sidebar" aria-expanded="false" aria-controls="sidebar">Menu</button>
            <div id="viewport">
                <div id="map-container">
                    <img id="aerial-image" alt="Page background" draggable="false">
                    <div id="marker-layer"></div>
                </div>
                <div id="controls">
                    <button class="control-btn" id="zoom-in">Zoom +</button>
                    <button class="control-btn" id="zoom-out">Zoom -</button>
                    <button class="control-btn" id="fit-view">Fit</button>
                </div>
            </div>
            <div id="lightbox" role="dialog" aria-modal="true" aria-hidden="true">
                <button id="lightbox-close" type="button" aria-label="Close photo">&times;</button>
                <img id="lightbox-img" src="" alt="">
                <video id="lightbox-video" controls playsinline preload="metadata" hidden></video>
                <iframe id="lightbox-frame" allow="autoplay; fullscreen" allowfullscreen hidden></iframe>
                <div id="lightbox-title"></div>
                <div id="lightbox-index"></div>
                <div id="lightbox-note"></div>
                <div id="lightbox-nav">
                    <button class="nav-btn" id="prev-btn" type="button" aria-label="Previous photo">
                        <span class="nav-icon" aria-hidden="true">&larr;</span>
                        <span class="nav-label">&larr; Previous</span>
                    </button>
                    <button class="nav-btn" id="next-btn" type="button" aria-label="Next photo">
                        <span class="nav-icon" aria-hidden="true">&rarr;</span>
                        <span class="nav-label">Next &rarr;</span>
                    </button>
                </div>
            </div>
        </main>
    </div>

    <script>
        const pageData = {pages_json};
        let activePageIndex = 0;
        let currentPhotoIndex = -1;
        let scale = 1;
        let translateX = 0;
        let translateY = 0;
        let isPanning = false;
        let startX = 0;
        let startY = 0;
        let isPinching = false;
        let pinchStartDistance = 0;
        let pinchStartScale = 1;
        let lastViewportWidth = 0;
        let lastViewportHeight = 0;

        const pageNav = document.getElementById('page-nav');
        const pageLegend = document.getElementById('page-legend');
        const viewport = document.getElementById('viewport');
        const container = document.getElementById('map-container');
        const aerialImage = document.getElementById('aerial-image');
        const markerLayer = document.getElementById('marker-layer');
        const lightbox = document.getElementById('lightbox');
        const lightboxImg = document.getElementById('lightbox-img');
        const lightboxVideo = document.getElementById('lightbox-video');
        const lightboxFrame = document.getElementById('lightbox-frame');
        const lightboxTitle = document.getElementById('lightbox-title');
        const lightboxIndex = document.getElementById('lightbox-index');
        const lightboxNote = document.getElementById('lightbox-note');
        const lightboxNav = document.getElementById('lightbox-nav');
        const closeBtn = document.getElementById('lightbox-close');
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');
        const sidebarToggle = document.getElementById('sidebar-toggle');
        const sidebarClose = document.getElementById('sidebar-close');
        const sidebarScrim = document.getElementById('sidebar-scrim');
        const mobileMedia = window.matchMedia('(max-width: 900px)');

        function activePage() {{
            return pageData[activePageIndex] || pageData[0];
        }}

        function updateTransform() {{
            container.style.transform = `translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
        }}

        function fitToViewport() {{
            const page = activePage();
            const vw = viewport.clientWidth || 1;
            const vh = viewport.clientHeight || 1;
            scale = Math.min(vw / page.width, vh / page.height) * 0.95;
            translateX = (vw - page.width * scale) / 2;
            translateY = (vh - page.height * scale) / 2;
            updateTransform();
        }}

        function renderPageNav() {{
            pageNav.innerHTML = '';
            pageData.forEach((page, index) => {{
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'page-nav-button';
                button.dataset.pageId = page.id;
                button.textContent = page.name;
                button.classList.toggle('active', index === activePageIndex);
                button.addEventListener('click', () => {{
                    setActivePage(index);
                    if (mobileMedia.matches) setSidebarOpen(false);
                }});
                pageNav.appendChild(button);
            }});
        }}

        function renderLegend() {{
            const page = activePage();
            pageLegend.innerHTML = '';
            const heading = document.createElement('div');
            heading.className = 'page-legend-heading';
            heading.textContent = page.name;
            pageLegend.appendChild(heading);
            page.legend.forEach((item) => {{
                const row = document.createElement('div');
                row.className = 'page-legend-row';
                const number = document.createElement('span');
                number.className = 'page-legend-number';
                number.textContent = item.number;
                const label = document.createElement('span');
                label.textContent = item.label;
                row.appendChild(number);
                row.appendChild(label);
                pageLegend.appendChild(row);
            }});
        }}

        function renderMarkers() {{
            const page = activePage();
            markerLayer.innerHTML = '';
            page.markers.forEach((markerData) => {{
                const marker = document.createElement('button');
                marker.type = 'button';
                marker.className = 'marker';
                marker.style.left = `${{markerData.x}}px`;
                marker.style.top = `${{markerData.y}}px`;
                marker.dataset.index = String(markerData.index);
                marker.setAttribute('aria-label', `Open photo ${{markerData.number}}`);
                const number = document.createElement('span');
                number.className = 'marker-number';
                number.textContent = String(markerData.number);
                marker.appendChild(number);
                marker.addEventListener('click', () => showPhoto(markerData.index));
                markerLayer.appendChild(marker);
            }});
        }}

        function renderPage() {{
            const page = activePage();
            container.style.width = `${{page.width}}px`;
            container.style.height = `${{page.height}}px`;
            syncMarkerSizeForViewport(page);
            aerialImage.src = page.aerialSrc;
            aerialImage.style.width = `${{page.width}}px`;
            aerialImage.style.height = `${{page.height}}px`;
            currentPhotoIndex = -1;
            renderPageNav();
            renderLegend();
            renderMarkers();
            fitToViewport();
            closeLightbox();
        }}

        function setActivePage(index) {{
            if (index < 0 || index >= pageData.length || index === activePageIndex) {{
                return;
            }}
            activePageIndex = index;
            renderPage();
        }}

        function resetLightboxMedia() {{
            lightboxVideo.pause();
            lightboxVideo.removeAttribute('src');
            lightboxVideo.load();
            lightboxVideo.hidden = true;
            lightboxFrame.src = 'about:blank';
            lightboxFrame.hidden = true;
            lightboxImg.src = '';
            lightboxImg.hidden = false;
        }}

        function applyLightboxMedia(photo) {{
            resetLightboxMedia();
            if (photo.isVideo) {{
                lightboxImg.hidden = true;
                if (photo.embed) {{
                    lightboxFrame.src = photo.src;
                    lightboxFrame.hidden = false;
                }} else {{
                    if (photo.poster) {{ lightboxVideo.poster = photo.poster; }}
                    else {{ lightboxVideo.removeAttribute('poster'); }}
                    lightboxVideo.src = photo.src;
                    lightboxVideo.hidden = false;
                }}
            }} else {{
                lightboxImg.src = photo.src;
                lightboxImg.hidden = false;
            }}
        }}

        function showPhoto(index) {{
            const page = activePage();
            if (index < 0 || index >= page.photos.length) return;
            const photo = page.photos[index];
            currentPhotoIndex = index;
            applyLightboxMedia(photo);
            lightboxTitle.textContent = photo.filename || '';
            lightboxIndex.textContent = `Photo ${{index + 1}} of ${{page.photos.length}}`;
            const note = photo.note ? String(photo.note).trim() : '';
            lightboxNote.textContent = note;
            lightboxNote.style.display = note ? 'block' : 'none';
            lightbox.classList.add('active');
            lightbox.setAttribute('aria-hidden', 'false');
            updateNavButtons();
            requestAnimationFrame(updateLightboxLayout);
        }}

        function closeLightbox() {{
            lightbox.classList.remove('active');
            lightbox.setAttribute('aria-hidden', 'true');
            resetLightboxMedia();
            currentPhotoIndex = -1;
        }}

        function updateNavButtons() {{
            const page = activePage();
            prevBtn.style.visibility = currentPhotoIndex > 0 ? 'visible' : 'hidden';
            nextBtn.style.visibility = currentPhotoIndex < page.photos.length - 1 ? 'visible' : 'hidden';
        }}

        function navigatePhoto(delta) {{
            const page = activePage();
            const next = currentPhotoIndex + delta;
            if (next >= 0 && next < page.photos.length) {{
                showPhoto(next);
            }}
        }}

        function zoomAt(x, y, nextScale) {{
            const clamped = Math.min(10, Math.max(0.1, nextScale));
            translateX = x - (x - translateX) * (clamped / scale);
            translateY = y - (y - translateY) * (clamped / scale);
            scale = clamped;
            updateTransform();
        }}

        function getTouchDistance(touches) {{
            const dx = touches[0].clientX - touches[1].clientX;
            const dy = touches[0].clientY - touches[1].clientY;
            return Math.hypot(dx, dy);
        }}

        function getTouchCenter(touches) {{
            return {{
                x: (touches[0].clientX + touches[1].clientX) / 2,
                y: (touches[0].clientY + touches[1].clientY) / 2,
            }};
        }}

        function syncMarkerSizeForViewport(page) {{
            const root = document.documentElement;
            if (mobileMedia.matches) {{
                root.style.removeProperty('--marker-size');
                root.style.removeProperty('--marker-font-size');
                return;
            }}
            if (page && page.markerSize) {{
                root.style.setProperty('--marker-size', `${{page.markerSize}}px`);
                root.style.setProperty('--marker-font-size', `${{Math.max(12, Math.round(page.markerSize * 0.29))}}px`);
            }} else {{
                root.style.removeProperty('--marker-size');
                root.style.removeProperty('--marker-font-size');
            }}
        }}

        function setSidebarOpen(isOpen) {{
            document.body.classList.toggle('sidebar-open', isOpen);
            if (!sidebarToggle) return;
            sidebarToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            sidebarToggle.textContent = isOpen ? 'Close' : 'Menu';
        }}

        function syncSidebarToggle() {{
            if (!sidebarToggle) return;
            if (!mobileMedia.matches) {{
                document.body.classList.remove('sidebar-open');
                sidebarToggle.setAttribute('aria-expanded', 'false');
                sidebarToggle.textContent = 'Menu';
            }}
        }}

        function updateViewportInsets() {{
            if (!window.visualViewport) {{
                document.documentElement.style.setProperty('--viewport-bottom-inset', '0px');
                return;
            }}
            const vv = window.visualViewport;
            const bottomInset = Math.max(0, window.innerHeight - (vv.height + vv.offsetTop));
            document.documentElement.style.setProperty('--viewport-bottom-inset', `${{bottomInset}}px`);
        }}

        function updateLightboxLayout() {{
            if (!lightbox.classList.contains('active')) return;
            const styles = window.getComputedStyle(lightbox);
            const paddingTop = parseFloat(styles.paddingTop) || 0;
            const paddingBottom = parseFloat(styles.paddingBottom) || 0;
            const titleH = lightboxTitle.offsetHeight || 0;
            const indexH = lightboxIndex.offsetHeight || 0;
            const noteH = lightboxNote.style.display === 'none' ? 0 : (lightboxNote.offsetHeight || 0);
            const navH = lightboxNav ? lightboxNav.offsetHeight || 0 : 0;
            const isMobile = mobileMedia.matches;
            const chrome = isMobile ? 64 : 100;
            const available = (lightbox.clientHeight || window.innerHeight) - paddingTop - paddingBottom;
            const maxHeight = Math.max(160, available - titleH - indexH - noteH - (isMobile ? 0 : navH) - chrome);
            lightboxImg.style.maxHeight = `${{maxHeight}}px`;
            lightboxVideo.style.maxHeight = `${{maxHeight}}px`;
            lightboxFrame.style.maxHeight = `${{maxHeight}}px`;
        }}

        function preserveViewOnResize(newWidth, newHeight) {{
            if (lastViewportWidth === 0 || lastViewportHeight === 0) {{
                fitToViewport();
                return;
            }}
            const prevCenterX = lastViewportWidth / 2;
            const prevCenterY = lastViewportHeight / 2;
            const imageCenterX = (prevCenterX - translateX) / scale;
            const imageCenterY = (prevCenterY - translateY) / scale;
            translateX = (newWidth / 2) - imageCenterX * scale;
            translateY = (newHeight / 2) - imageCenterY * scale;
            updateTransform();
        }}

        function handleResize() {{
            const newWidth = viewport.clientWidth || 1;
            const newHeight = viewport.clientHeight || 1;
            if (lastViewportWidth === 0 || lastViewportHeight === 0) {{
                fitToViewport();
            }} else {{
                preserveViewOnResize(newWidth, newHeight);
            }}
            lastViewportWidth = newWidth;
            lastViewportHeight = newHeight;
            syncSidebarToggle();
            syncMarkerSizeForViewport(activePage());
            updateViewportInsets();
            updateLightboxLayout();
        }}

        viewport.addEventListener('wheel', (event) => {{
            event.preventDefault();
            const factor = event.deltaY > 0 ? 0.9 : 1.1;
            zoomAt(event.clientX, event.clientY, scale * factor);
        }}, {{ passive: false }});

        container.addEventListener('mousedown', (event) => {{
            if (event.target.closest('.marker')) return;
            isPanning = true;
            startX = event.clientX - translateX;
            startY = event.clientY - translateY;
        }});
        document.addEventListener('mousemove', (event) => {{
            if (!isPanning) return;
            translateX = event.clientX - startX;
            translateY = event.clientY - startY;
            updateTransform();
        }});
        document.addEventListener('mouseup', () => {{
            isPanning = false;
        }});

        container.addEventListener('touchstart', (event) => {{
            if (event.touches.length === 2) {{
                isPinching = true;
                isPanning = false;
                pinchStartDistance = getTouchDistance(event.touches);
                pinchStartScale = scale;
                event.preventDefault();
                return;
            }}
            if (event.touches.length !== 1) return;
            if (event.target.closest('.marker')) return;
            isPanning = true;
            startX = event.touches[0].clientX - translateX;
            startY = event.touches[0].clientY - translateY;
        }}, {{ passive: false }});

        container.addEventListener('touchmove', (event) => {{
            if (isPinching && event.touches.length === 2) {{
                event.preventDefault();
                if (pinchStartDistance > 0) {{
                    const distance = getTouchDistance(event.touches);
                    const center = getTouchCenter(event.touches);
                    const targetScale = pinchStartScale * (distance / pinchStartDistance);
                    zoomAt(center.x, center.y, targetScale);
                }}
                return;
            }}
            if (!isPanning || event.touches.length !== 1) return;
            event.preventDefault();
            translateX = event.touches[0].clientX - startX;
            translateY = event.touches[0].clientY - startY;
            updateTransform();
        }}, {{ passive: false }});

        container.addEventListener('touchend', (event) => {{
            if (event && event.touches) {{
                if (event.touches.length < 2) {{
                    isPinching = false;
                    pinchStartDistance = 0;
                }}
                if (event.touches.length === 0) {{
                    isPanning = false;
                }}
                return;
            }}
            isPinching = false;
            isPanning = false;
        }});

        container.addEventListener('touchcancel', () => {{
            isPinching = false;
            isPanning = false;
            pinchStartDistance = 0;
        }});

        if (sidebarToggle) {{
            sidebarToggle.addEventListener('click', () => {{
                setSidebarOpen(!document.body.classList.contains('sidebar-open'));
            }});
        }}
        if (sidebarScrim) {{
            sidebarScrim.addEventListener('click', () => setSidebarOpen(false));
        }}
        if (sidebarClose) {{
            sidebarClose.addEventListener('click', () => setSidebarOpen(false));
        }}

        document.getElementById('zoom-in').addEventListener('click', () => {{
            zoomAt(viewport.clientWidth / 2, viewport.clientHeight / 2, scale * 1.3);
        }});
        document.getElementById('zoom-out').addEventListener('click', () => {{
            zoomAt(viewport.clientWidth / 2, viewport.clientHeight / 2, scale / 1.3);
        }});
        document.getElementById('fit-view').addEventListener('click', fitToViewport);
        closeBtn.addEventListener('click', closeLightbox);
        prevBtn.addEventListener('click', () => navigatePhoto(-1));
        nextBtn.addEventListener('click', () => navigatePhoto(1));
        lightbox.addEventListener('click', (event) => {{
            if (event.target === lightbox) closeLightbox();
        }});
        document.addEventListener('keydown', (event) => {{
            if (!lightbox.classList.contains('active')) return;
            if (event.key === 'Escape') closeLightbox();
            if (event.key === 'ArrowLeft') navigatePhoto(-1);
            if (event.key === 'ArrowRight') navigatePhoto(1);
        }});
        window.addEventListener('resize', handleResize);
        window.addEventListener('orientationchange', () => {{
            handleResize();
            setTimeout(handleResize, 200);
        }});
        if (window.visualViewport) {{
            window.visualViewport.addEventListener('resize', () => {{
                updateViewportInsets();
                updateLightboxLayout();
            }});
            window.visualViewport.addEventListener('scroll', () => {{
                updateViewportInsets();
                updateLightboxLayout();
            }});
        }}

        renderPage();
        handleResize();
    </script>
</body>
</html>'''

    def generate_html_with_folder(
        self,
        photos: List[Dict[str, Any]],
        aerial_image_path: str,
        transform: Optional[AffineTransform],
        output_dir: str,
        base_name: str,
        marker_pixels: Optional[List[PixelPoint]] = None,
        group_assignments: Optional[GroupAssignments] = None,
        group_aliases: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Generate HTML with a separate images folder.

        Args:
            photos: List of photo dicts with 'image_data', 'gps', 'filename'
            aerial_image_path: Path to the aerial background image
            transform: Affine transform for GPS to pixel conversion (optional if marker_pixels provided)
            output_dir: Output directory
            base_name: Base name for HTML file and images folder
            marker_pixels: Optional pixel positions to use instead of GPS transform
            group_assignments: Optional photo group assignments for marker colors
            group_aliases: Optional group display names keyed by group id

        Returns:
            Path to the generated HTML file
        """
        if marker_pixels is not None and len(marker_pixels) != len(photos):
            raise ValueError("marker_pixels length must match photos")
        if marker_pixels is None and transform is None:
            raise ValueError("transform is required when marker_pixels is not provided")
        # Create images directory
        images_dir = os.path.join(output_dir, f"{base_name}_images")
        os.makedirs(images_dir, exist_ok=True)

        # Copy aerial image
        aerial_ext = Path(aerial_image_path).suffix
        aerial_filename = f"aerial{aerial_ext}"
        aerial_dest = os.path.join(images_dir, aerial_filename)
        shutil.copy(aerial_image_path, aerial_dest)
        aerial_src = f"{base_name}_images/{aerial_filename}"

        # Get aerial image dimensions
        with Image.open(aerial_image_path) as img:
            img_width, img_height = img.size

        colorizer = get_colorizer()
        unique_colors = set()
        photo_colors: Dict[str, str] = {}

        default_names = {group["id"]: group["name"] for group in DEFAULT_GROUPS}
        for photo in photos:
            filepath = photo.get("filepath", "")
            color = "default"
            if group_assignments:
                group = group_assignments.get_group_for_photo(filepath)
                if group:
                    color = group.color
            photo_colors[filepath] = color
            unique_colors.add(color)

        markers_by_color = {}
        for color in unique_colors:
            marker_bytes = colorizer.get_colored_marker_bytes(color, self.marker_asset_size)
            markers_by_color[color] = base64.b64encode(marker_bytes).decode("utf-8")

        legend_items = self._build_legend_items(photos, group_assignments, group_aliases)

        # Save photos and build data
        photos_data = []
        markers_html = []

        default_group = group_assignments.get_group("default") if group_assignments else None
        for i, photo in enumerate(photos):
            # Save photo
            photo_filename = f"photo_{i+1}.jpg"
            photo_path = os.path.join(images_dir, photo_filename)
            with open(photo_path, 'wb') as f:
                f.write(photo['image_data'])

            filepath = photo.get("filepath", "")
            group = group_assignments.get_group_for_photo(filepath) if group_assignments else None
            if group is None:
                group = default_group
            if "custom_name" in photo:
                display_name = photo.get("custom_name") or ""
                if not display_name:
                    display_name = self._photo_title_for_group(group, default_names, group_aliases)
            else:
                display_name = photo.get("display_name") or photo.get("filename") or ""
                if not display_name:
                    display_name = self._photo_title_for_group(group, default_names, group_aliases)
            note = photo.get("note", "")
            photos_data.append({
                'src': f"{base_name}_images/{photo_filename}",
                'filename': display_name,
                'note': note,
            })

            # Calculate marker position
            if marker_pixels is not None:
                pixel = marker_pixels[i]
            else:
                pixel = transform.transform(photo['gps'])
            color = photo_colors.get(filepath, "default")
            markers_html.append(self._create_marker_html(i, pixel, color))

        # Generate HTML
        html_content = self._generate_html(
            aerial_src=aerial_src,
            image_width=img_width,
            image_height=img_height,
            markers_html='\n        '.join(markers_html),
            photos_json=json.dumps(photos_data),
            markers_by_color=markers_by_color,
            legend_items=legend_items,
        )

        # Write HTML file
        html_path = os.path.join(output_dir, f"{base_name}.html")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return html_path

    def _create_marker_html(self, index: int, pixel: PixelPoint, color: str = "default") -> str:
        """Create HTML for a single marker with color-specific class."""
        color_class = color.lstrip("#").lower()
        return (
            f'<div class="marker marker-color-{color_class}" style="left:{pixel.x}px;top:{pixel.y}px" '
            f'data-index="{index}" tabindex="0" role="button" aria-haspopup="dialog" '
            f'aria-label="Open photo {index + 1}"><span class="marker-number">{index + 1}</span></div>'
        )

    def _get_mime_type(self, filepath: str) -> str:
        """Get MIME type for an image file."""
        ext = Path(filepath).suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.tif': 'image/tiff',
            '.tiff': 'image/tiff',
        }
        return mime_types.get(ext, 'image/jpeg')

    def _build_legend_items(
        self,
        photos: List[Dict[str, Any]],
        group_assignments: Optional[GroupAssignments],
        group_aliases: Optional[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Build legend items for any groups used in the map."""
        if not photos:
            return []

        default_names = {group["id"]: group["name"] for group in DEFAULT_GROUPS}
        legend_items: List[Dict[str, str]] = []

        if group_assignments:
            used_group_ids = set()
            default_group = group_assignments.get_group("default")
            for photo in photos:
                filepath = photo.get("filepath", "")
                group = group_assignments.get_group_for_photo(filepath)
                if group is None:
                    group = default_group
                if group:
                    used_group_ids.add(group.id)
                else:
                    used_group_ids.add("default")

            for group in group_assignments.get_all_groups():
                if group.id not in used_group_ids:
                    continue
                legend_items.append({
                    "color": group.color,
                    "label": self._legend_label_for_group(group, default_names, group_aliases),
                })

        if not legend_items:
            legend_items = [{"color": "default", "label": "Detail Photo"}]

        return legend_items

    def _legend_label_for_group(
        self,
        group: PhotoGroup,
        default_names: Dict[str, str],
        group_aliases: Optional[Dict[str, str]],
    ) -> str:
        """Determine the label to display for a legend entry."""
        custom_name = self._get_custom_group_name(group, default_names, group_aliases)
        if custom_name:
            return custom_name
        return "Detail Photo"

    def _photo_title_for_group(
        self,
        group: Optional[PhotoGroup],
        default_names: Dict[str, str],
        group_aliases: Optional[Dict[str, str]],
    ) -> str:
        """Choose the lightbox title based on group naming rules."""
        if not group:
            return "Detail Photo"
        custom_name = self._get_custom_group_name(group, default_names, group_aliases)
        if custom_name:
            return custom_name
        return "Detail Photo"

    def _get_custom_group_name(
        self,
        group: PhotoGroup,
        default_names: Dict[str, str],
        group_aliases: Optional[Dict[str, str]],
    ) -> str:
        """Return a custom group name if set, otherwise empty string."""
        alias = ""
        if group_aliases:
            alias = group_aliases.get(group.id, "").strip()
        if alias:
            return alias
        default_name = default_names.get(group.id)
        if default_name:
            if group.name and group.name != default_name:
                return group.name
            return ""
        return group.name or ""

    def _build_prepared_by_html(self, format_multiline) -> str:
        """Render the 'Prepared by' sidebar block, or empty string if no fields set."""
        rows = []
        if self.company_name:
            rows.append(
                f'<div class="prepared-name">{html.escape(self.company_name)}</div>'
            )
        if self.company_address:
            formatted = format_multiline(self.company_address)
            if formatted:
                rows.append(f'<div class="prepared-line">{formatted}</div>')
        if self.company_phone:
            rows.append(
                f'<div class="prepared-line">{html.escape(self.company_phone)}</div>'
            )
        if self.company_website:
            site = self.company_website
            if "." in site:
                rows.append(
                    '<div class="prepared-line">'
                    f'<a href="{html.escape(site, quote=True)}" target="_blank" rel="noopener">'
                    f'{html.escape(site)}</a>'
                    "</div>"
                )
            else:
                rows.append(
                    f'<div class="prepared-line">{html.escape(site)}</div>'
                )

        if not rows:
            return ""
        return (
            '<div id="prepared-by">'
            f'{"".join(rows)}'
            "</div>"
        )

    @staticmethod
    def _format_multiline(value: str) -> str:
        """Escape and join non-empty lines with <br>."""
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        if not lines:
            return ""
        return "<br>".join(html.escape(line) for line in lines)

    def _build_client_info_html(self) -> str:
        """Render the client info sidebar block, or empty string if no fields set."""
        client_rows = []
        if self.client_name:
            client_rows.append(
                '<div class="client-row">'
                '<div class="client-label">Client</div>'
                f'<div class="client-value">{html.escape(self.client_name)}</div>'
                "</div>"
            )
        if self.client_company:
            client_rows.append(
                '<div class="client-row">'
                '<div class="client-label">Company</div>'
                f'<div class="client-value">{html.escape(self.client_company)}</div>'
                "</div>"
            )
        if self.client_address:
            formatted_address = self._format_multiline(self.client_address)
            if formatted_address:
                client_rows.append(
                    '<div class="client-row">'
                    '<div class="client-label">Address</div>'
                    f'<div class="client-value">{formatted_address}</div>'
                    "</div>"
                )
        if not client_rows:
            return ""
        return f'<div id="client-info">{"".join(client_rows)}</div>'

    def _build_proposal_link_html(self) -> str:
        if not self.proposal_link:
            return ""
        safe_link = html.escape(self.proposal_link, quote=True)
        return (
            f'<a id="proposal-link" class="sidebar-action-link" '
            f'href="{safe_link}" target="_blank" rel="noopener">View Proposal</a>'
        )

    def _build_download_link_html(self) -> str:
        if not self.download_photos_link:
            return ""
        safe_link = html.escape(self.download_photos_link, quote=True)
        return (
            f'<a id="download-photos-link" class="sidebar-action-link" '
            f'href="{safe_link}" target="_blank" rel="noopener">Download Photos</a>'
        )

    @staticmethod
    def _build_sidebar_divider_html(has_top: bool, has_bottom: bool) -> str:
        if has_top and has_bottom:
            return '<div class="sidebar-divider"></div>'
        return ""

    def _generate_html(
        self,
        aerial_src: str,
        image_width: int,
        image_height: int,
        markers_html: str,
        photos_json: str,
        markers_by_color: Dict[str, str],
        legend_items: List[Dict[str, str]],
    ) -> str:
        """Generate the complete HTML document."""

        # Calculate font size proportionally (29% of marker size = 25% * 1.15, min 12px)
        marker_font_size = max(12, int(self.marker_size * 0.29))
        legend_scale = 1.15
        legend_font_size = int(round(12 * legend_scale))
        legend_title_size = int(round(13 * legend_scale))
        legend_heading_size = legend_title_size + 4
        legend_gap = int(round(7 * legend_scale))
        legend_padding_y = int(round(8 * legend_scale))
        legend_padding_x = int(round(10 * legend_scale))
        legend_radius = int(round(6 * legend_scale))
        legend_marker_size = int(round(24 * legend_scale))

        logo_src = self._get_logo_image_src()
        logo_html = (
            f'<img id="logo" src="{logo_src}" alt="Company logo">'
            if logo_src else ""
        )
        project_label = html.escape(self.project_name)
        proposal_link_html = self._build_proposal_link_html()
        download_link_html = self._build_download_link_html()
        prepared_by_html = self._build_prepared_by_html(self._format_multiline)
        client_info_html = self._build_client_info_html()
        divider_html = self._build_sidebar_divider_html(
            has_top=bool(prepared_by_html or logo_html),
            has_bottom=bool(client_info_html),
        )

        sidebar_brand_html = (
            f'<div id="sidebar-brand">{logo_html}{prepared_by_html}'
            f'{divider_html}{client_info_html}'
            f'{proposal_link_html}{download_link_html}</div>'
        )

        has_marker_images = bool(markers_by_color)

        marker_color_css = []
        for color, b64 in markers_by_color.items():
            color_class = color.lstrip("#").lower()
            marker_color_css.append(
                f".marker-color-{color_class} {{ background-image: url('data:image/png;base64,{b64}'); }}"
            )
        marker_color_styles = "\n        ".join(marker_color_css)

        if has_marker_images:
            marker_bg_size = "contain"
            marker_border = "none"
            marker_border_radius = "0"
        else:
            marker_bg_size = "auto"
            marker_border = "2px solid white"
            marker_border_radius = "50%"

        legend_rows = []
        for item in legend_items:
            color_class = item["color"].lstrip("#").lower()
            raw_label = item["label"]
            label = html.escape(raw_label)
            label_attr = html.escape(raw_label, quote=True)
            raw_color = item["color"]
            if raw_color == "default":
                toggle_color = "#1b1b1b"
            elif isinstance(raw_color, str) and raw_color.startswith("#"):
                toggle_color = raw_color
            else:
                toggle_color = "var(--sidebar-text)"
            legend_rows.append(
                f'<button class="legend-item" type="button" data-color="{color_class}" '
                f'aria-pressed="true" aria-label="Toggle {label_attr}">'
                f'<span class="legend-marker marker-color-{color_class}"></span>'
                f'<span class="legend-text">{label}</span>'
                f'<span class="legend-toggle" aria-hidden="true" style="color: {toggle_color};">'
                f'<svg class="legend-eye legend-eye-on" viewBox="0 0 24 24" role="presentation" aria-hidden="true">'
                f'<path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6-10-6-10-6z" '
                f'fill="none" stroke="currentColor" stroke-width="2"/>'
                f'<circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="2"/>'
                f'</svg>'
                f'<svg class="legend-eye legend-eye-off" viewBox="0 0 24 24" role="presentation" aria-hidden="true">'
                f'<path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6-10-6-10-6z" '
                f'fill="none" stroke="currentColor" stroke-width="2"/>'
                f'<circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="2"/>'
                f'<line x1="4" y1="4" x2="20" y2="20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                f'</svg>'
                f'</span></button>'
            )
        legend_html = (
            '<div id="legend">\n'
            '        <div class="legend-heading">Legend</div>\n'
            + "\n        ".join(legend_rows) + "\n    </div>"
            if legend_rows else ""
        )

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_label}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        :root {{
            --sidebar-width: 240px;
            --sidebar-bg: #ffffff;
            --sidebar-border: #e3e1da;
            --sidebar-text: #1b1b1b;
            --viewport-bottom-inset: 0px;
            --marker-size: {self.marker_size}px;
            --marker-font-size: {marker_font_size}px;
            --legend-font-size: {legend_font_size}px;
            --legend-title-size: {legend_title_size}px;
            --legend-heading-size: {legend_heading_size}px;
            --legend-gap: {legend_gap}px;
            --legend-padding-x: {legend_padding_x}px;
            --legend-padding-y: {legend_padding_y}px;
            --legend-radius: {legend_radius}px;
            --legend-marker-size: {legend_marker_size}px;
        }}

        body {{
            background: #1a1a1a;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}

        #layout {{
            display: grid;
            grid-template-columns: var(--sidebar-width) 1fr;
            width: 100vw;
            height: 100vh;
        }}

        #sidebar {{
            background: var(--sidebar-bg);
            border-right: 1px solid var(--sidebar-border);
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            overflow-y: auto;
            color: var(--sidebar-text);
            position: relative;
        }}

        #sidebar-close {{
            display: none;
            position: absolute;
            top: 12px;
            right: 12px;
            width: 44px;
            height: 44px;
            border-radius: 22px;
            border: 1px solid var(--sidebar-border);
            background: #ffffff;
            color: #1b1b1b;
            font-size: 20px;
            line-height: 1;
            cursor: pointer;
        }}

        #sidebar-close:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}

        #sidebar-toggle {{
            display: none;
            position: fixed;
            top: 12px;
            left: 12px;
            z-index: 900;
            background: rgba(12, 20, 18, 0.9);
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.2);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            cursor: pointer;
            min-height: 44px;
            min-width: 44px;
        }}

        #sidebar-toggle:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}

        #sidebar-scrim {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.45);
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
            z-index: 850;
        }}

        body.sidebar-open #sidebar-scrim {{
            opacity: 1;
            pointer-events: auto;
        }}

        #sidebar-brand {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
            text-align: center;
            width: 100%;
        }}

        .sidebar-title {{
            color: var(--sidebar-text);
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }}

        .sidebar-section-title {{
            color: var(--sidebar-text);
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        #content {{
            position: relative;
            overflow: hidden;
        }}

        #viewport {{
            width: 100%;
            height: 100%;
            overflow: hidden;
            position: relative;
        }}

        #map-container {{
            position: absolute;
            width: {image_width}px;
            height: {image_height}px;
            cursor: grab;
            transform-origin: 0 0;
        }}

        #map-container:active {{
            cursor: grabbing;
        }}

        #aerial-image {{
            width: 100%;
            height: 100%;
            user-select: none;
            -webkit-user-drag: none;
            display: block;
        }}

        .marker {{
            position: absolute;
            width: var(--marker-size);
            height: var(--marker-size);
            margin-left: calc(var(--marker-size) / -2);
            margin-top: calc(var(--marker-size) / -2);
            background-size: {marker_bg_size};
            background-repeat: no-repeat;
            border: {marker_border};
            border-radius: {marker_border_radius};
            cursor: pointer;
            transition: transform 0.15s ease;
            z-index: 10;
        }}

        .marker:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}

        .marker.marker-hidden {{
            display: none;
        }}

        /* Group-specific marker colors */
        {marker_color_styles}

        .marker:hover {{
            transform: scale(1.2);
            z-index: 20;
        }}

        .marker-number {{
            position: absolute;
            bottom: 4%;
            right: 4%;
            background: #ffffff;
            color: #111111;
            font-size: var(--marker-font-size);
            font-weight: 700;
            line-height: 1;
            padding: 0.15em 0.35em;
            border-radius: 4px;
            border: 1px solid rgba(0, 0, 0, 0.25);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
            min-width: 1em;
            text-align: center;
            pointer-events: none;
        }}

        /* Lightbox */
        #lightbox {{
            display: none;
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.95);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }}

        #lightbox:focus {{
            outline: none;
        }}

        #lightbox.active {{
            display: flex;
        }}

        #lightbox img, #lightbox video {{
            max-width: 95%;
            max-height: 85%;
            object-fit: contain;
            box-shadow: 0 0 50px rgba(0,0,0,0.5);
        }}

        #lightbox-frame {{
            width: min(95%, 1280px);
            max-height: 85%;
            aspect-ratio: 16 / 9;
            border: none;
            background: #000000;
            box-shadow: 0 0 50px rgba(0,0,0,0.5);
        }}

        #lightbox [hidden] {{
            display: none !important;
        }}

        #lightbox-meta {{
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-top: 15px;
            gap: 8px;
            max-width: 90%;
        }}

        #lightbox-header {{
            width: 100%;
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            align-items: center;
            gap: 8px;
        }}

        #lightbox-title {{
            color: white;
            font-size: 16px;
            font-weight: 600;
            opacity: 0.95;
            text-align: center;
            white-space: pre-wrap;
        }}

        #lightbox-index {{
            color: white;
            font-size: 13px;
            opacity: 0.7;
            text-align: right;
            white-space: nowrap;
        }}

        #lightbox-note {{
            color: rgba(255,255,255,0.85);
            font-size: 13px;
            line-height: 1.4;
            text-align: center;
            white-space: pre-wrap;
            max-height: calc(1.4em * 5);
            overflow: hidden;
            overflow-wrap: anywhere;
            display: none;
        }}

        #close-btn-mobile {{
            display: none;
        }}

        #lightbox-close {{
            position: absolute;
            top: 20px;
            right: 30px;
            color: white;
            font-size: 40px;
            cursor: pointer;
            opacity: 0.7;
            transition: opacity 0.2s;
            z-index: 1200;
            background: transparent;
            border: none;
            width: 44px;
            height: 44px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            line-height: 1;
        }}

        #lightbox-close:hover {{
            opacity: 1;
        }}

        #lightbox-close:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}

        #lightbox-nav {{
            position: absolute;
            bottom: 20px;
            display: flex;
            gap: 20px;
            z-index: 1100;
        }}

        #lightbox-actions {{
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: none;
            gap: 12px;
            z-index: 1100;
        }}

        .nav-btn {{
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            padding: 10px 20px;
            cursor: pointer;
            border-radius: 5px;
            font-size: 14px;
            transition: background 0.2s;
            min-height: 44px;
            min-width: 44px;
        }}

        .nav-btn:hover {{
            background: rgba(255,255,255,0.3);
        }}

        .nav-btn:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}

        .nav-icon {{
            display: none;
            font-size: 26px;
            line-height: 1;
            transform: translateY(-2px);
        }}

        .nav-label {{
            display: inline;
        }}

        #legend {{
            display: flex;
            flex-direction: column;
            gap: var(--legend-gap);
            color: var(--sidebar-text);
            font-size: var(--legend-font-size);
            background: transparent;
            padding: var(--legend-padding-y) var(--legend-padding-x);
            border-radius: var(--legend-radius);
            border: none;
            width: 100%;
            margin-top: auto;
        }}

        .legend-heading {{
            color: var(--sidebar-text);
            font-size: var(--legend-heading-size);
            font-weight: 700;
            text-align: center;
            align-self: stretch;
        }}

        .legend-title {{
            color: var(--sidebar-text);
            font-size: var(--legend-font-size);
            font-weight: 600;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: var(--legend-gap);
            background: transparent;
            border: none;
            padding: 0;
            text-align: left;
            width: 100%;
            cursor: pointer;
            color: inherit;
            font: inherit;
            min-height: 44px;
        }}

        .legend-text {{
            flex: 1;
        }}

        .legend-item[aria-pressed="false"] {{
            opacity: 0.45;
        }}

        .legend-item:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}

        .legend-toggle {{
            width: 20px;
            height: 20px;
            border: none;
            border-radius: 4px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            line-height: 1;
            flex: 0 0 auto;
            margin-left: auto;
            color: var(--sidebar-text);
        }}

        .legend-eye {{
            width: 18px;
            height: 18px;
        }}

        .legend-eye-off {{
            display: none;
        }}

        .legend-item[aria-pressed="false"] .legend-eye-on {{
            display: none;
        }}

        .legend-item[aria-pressed="false"] .legend-eye-off {{
            display: block;
        }}

        .legend-marker {{
            width: var(--legend-marker-size);
            height: var(--legend-marker-size);
            background-size: contain;
            background-repeat: no-repeat;
            flex: 0 0 auto;
        }}

        /* Floating zoom/fit controls anchored to the bottom-right of the canvas */
        #controls {{
            position: absolute;
            right: 16px;
            bottom: calc(16px + var(--viewport-bottom-inset, 0px));
            display: flex;
            gap: 8px;
            z-index: 50;
        }}

        .control-btn {{
            background: rgba(255, 255, 255, 0.95);
            color: #0c1412;
            border: 1px solid var(--sidebar-border);
            padding: 8px 14px;
            cursor: pointer;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            min-height: 40px;
            min-width: 44px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
            transition: background 0.2s;
        }}

        .control-btn:hover {{
            background: #ffffff;
        }}

        .control-btn:focus-visible {{
            outline: 2px solid #1f6feb;
            outline-offset: 2px;
        }}

        #logo {{
            max-width: 210px;
            max-height: {self.LOGO_MAX_HEIGHT}px;
            width: auto;
            height: auto;
            display: block;
        }}

        #logo + #prepared-by,
        #logo + #client-info {{
            margin-top: 12px;
        }}

        .sidebar-action-link {{
            color: #0b0f0d;
            background: #ffffff;
            font-size: 14px;
            font-weight: 600;
            padding: 6px 10px;
            border-radius: 4px;
            text-decoration: none;
            display: block;
            text-align: center;
            border: 1px solid var(--sidebar-border);
        }}

        .sidebar-action-link:hover {{
            text-decoration: underline;
        }}

        #client-info {{
            width: 100%;
            border: 1px solid var(--sidebar-border);
            border-radius: 6px;
            padding: 8px 10px;
            background: #f5f5f5;
            text-align: left;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .client-row {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .client-label {{
            font-size: 10px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #6b6b6b;
        }}

        .client-value {{
            font-size: 12px;
            font-weight: 600;
            color: var(--sidebar-text);
            word-break: break-word;
        }}

        #prepared-by {{
            width: 100%;
            padding: 8px 10px;
            background: transparent;
            text-align: center;
            display: flex;
            flex-direction: column;
            gap: 4px;
            color: var(--sidebar-text);
        }}

        .sidebar-divider {{
            width: 100%;
            height: 1px;
            background: var(--sidebar-border);
            margin: 4px 0;
        }}

        .prepared-name {{
            font-size: 13px;
            font-weight: 700;
            word-break: break-word;
        }}

        .prepared-line {{
            font-size: 12px;
            word-break: break-word;
        }}

        .prepared-line a {{
            color: #1f6feb;
            text-decoration: none;
        }}

        .prepared-line a:hover {{
            text-decoration: underline;
        }}

        @media (max-width: 1200px) and (min-width: 901px) {{
            :root {{
                --sidebar-width: clamp(180px, 20vw, 220px);
                --marker-size: clamp(72px, 6vw, {self.marker_size}px);
                --marker-font-size: clamp(12px, 2.2vw, {marker_font_size}px);
                --legend-font-size: clamp(12px, 1.3vw, {legend_font_size}px);
                --legend-heading-size: clamp(14px, 1.6vw, {legend_heading_size}px);
                --legend-marker-size: clamp(18px, 2vw, {legend_marker_size}px);
            }}

            #sidebar {{
                padding: 16px;
            }}
        }}

        @media (max-width: 900px) {{
            :root {{
                --marker-size: clamp(56px, 14vw, 80px);
                --marker-font-size: clamp(12px, 3vw, 18px);
                --legend-font-size: clamp(12px, 2.6vw, {legend_font_size}px);
                --legend-heading-size: clamp(14px, 3vw, {legend_heading_size}px);
                --legend-gap: clamp(6px, 2.2vw, {legend_gap}px);
                --legend-padding-x: clamp(8px, 3.2vw, {legend_padding_x}px);
                --legend-padding-y: clamp(6px, 2.4vw, {legend_padding_y}px);
                --legend-marker-size: clamp(18px, 4vw, {legend_marker_size}px);
            }}

            #layout {{
                grid-template-columns: 1fr;
                grid-template-rows: 1fr;
            }}

            #sidebar {{
                position: fixed;
                top: 0;
                left: 0;
                width: min(320px, 86vw);
                height: 100vh;
                height: 100dvh;
                max-height: 100dvh;
                padding-top: calc(52px + env(safe-area-inset-top));
                padding-bottom: calc(28px + env(safe-area-inset-bottom) + var(--viewport-bottom-inset));
                border-right: 1px solid var(--sidebar-border);
                border-bottom: none;
                transform: translateX(-105%);
                transition: transform 0.25s ease;
                z-index: 950;
                -webkit-overflow-scrolling: touch;
            }}

            #sidebar-close {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                position: sticky;
                right: auto;
                align-self: flex-end;
                margin-left: auto;
                z-index: 2;
            }}

            body.sidebar-open #sidebar {{
                transform: translateX(0);
            }}

            #sidebar-toggle {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}

            #sidebar-toggle {{
                top: calc(12px + env(safe-area-inset-top));
                left: calc(12px + env(safe-area-inset-left));
            }}

            #sidebar-close {{
                top: calc(12px + env(safe-area-inset-top));
                right: calc(12px + env(safe-area-inset-right));
            }}

            #sidebar-scrim {{
                display: block;
            }}

            #controls {{
                display: none;
            }}

            #lightbox {{
                padding: calc(12px + env(safe-area-inset-top)) 12px calc(72px + env(safe-area-inset-bottom) + var(--viewport-bottom-inset));
                justify-content: center;
            }}

            #viewport {{
                touch-action: none;
            }}

            #map-container {{
                touch-action: none;
            }}

            #lightbox img, #lightbox video {{
                max-width: 96vw;
                max-height: 78vh;
                margin-top: 0;
            }}

            #lightbox-frame {{
                width: 96vw;
                max-height: 78vh;
            }}

            #lightbox-meta {{
                position: absolute;
                left: 12px;
                right: 12px;
                bottom: calc(88px + env(safe-area-inset-bottom) + var(--viewport-bottom-inset));
                margin-top: 0;
                padding: 10px 12px;
                background: rgba(0, 0, 0, 0.7);
                border-radius: 10px;
                gap: 6px;
                opacity: 0;
                pointer-events: none;
                transform: translateY(8px);
                transition: opacity 0.2s ease, transform 0.2s ease;
                max-width: none;
            }}

            body.lightbox-notes-open #lightbox-meta {{
                opacity: 1;
                pointer-events: auto;
                transform: translateY(0);
            }}

            #lightbox-header {{
                width: 100%;
            }}

            #lightbox-title {{
                font-size: 14px;
                text-align: center;
            }}

            #lightbox-index {{
                font-size: 12px;
                text-align: right;
            }}

            #lightbox-note {{
                font-size: 12px;
                text-align: left;
                width: 100%;
                max-height: 28vh;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
            }}

            #lightbox-nav {{
                top: 50%;
                bottom: auto;
                left: 0;
                right: 0;
                transform: translateY(-50%);
                justify-content: space-between;
                padding: 0 12px;
                pointer-events: none;
            }}

            #lightbox-nav .nav-btn {{
                pointer-events: auto;
                width: 44px;
                height: 44px;
                padding: 0;
                border-radius: 999px;
                font-size: 22px;
                line-height: 1;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}

            .nav-icon {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 28px;
                line-height: 1;
                transform: translateY(-3px);
            }}

            .nav-label {{
                display: none;
            }}

            #lightbox-actions {{
                display: flex;
                bottom: calc(16px + env(safe-area-inset-bottom) + var(--viewport-bottom-inset));
                padding-bottom: 0;
            }}

            #notes-btn {{
                font-size: 12px;
                padding: 9px 18px;
            }}

            #close-btn-mobile {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}

            #lightbox-close {{
                display: none;
            }}
        }}

        @media (max-width: 480px) {{
            :root {{
                --marker-size: clamp(48px, 18vw, 70px);
                --marker-font-size: clamp(12px, 3.6vw, 16px);
                --legend-font-size: clamp(12px, 3.2vw, {legend_font_size}px);
                --legend-marker-size: clamp(16px, 5vw, 22px);
            }}

            #sidebar {{
                width: 100vw;
            }}

            .marker::before {{
                content: "";
                position: absolute;
                top: 50%;
                left: 50%;
                width: calc(var(--marker-size) + 16px);
                height: calc(var(--marker-size) + 16px);
                transform: translate(-50%, -50%);
                border-radius: 999px;
                background: transparent;
                pointer-events: auto;
            }}
        }}

        @media (max-width: 900px) and (orientation: landscape) {{
            #lightbox-meta {{
                left: 64px;
                right: 64px;
            }}
        }}

    </style>
</head>
<body>
    <div id="layout">
        <div id="sidebar">
            <button id="sidebar-close" aria-label="Close sidebar">&times;</button>
            {sidebar_brand_html}
            {legend_html}
        </div>
        <div id="content">
            <div id="sidebar-scrim" aria-hidden="true"></div>
            <button id="sidebar-toggle" aria-label="Toggle sidebar" aria-expanded="false" aria-controls="sidebar">
                Menu
            </button>
            <div id="viewport">
                <div id="map-container">
                    <img id="aerial-image" src="{aerial_src}" alt="Aerial Map" draggable="false">
                    {markers_html}
                </div>
                <div id="controls">
                    <button class="control-btn" id="zoom-in">Zoom +</button>
                    <button class="control-btn" id="zoom-out">Zoom -</button>
                    <button class="control-btn" id="fit-view">Fit</button>
                </div>
            </div>
            <div id="lightbox" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="lightbox-title" aria-describedby="lightbox-note" tabindex="-1">
                <button id="lightbox-close" type="button" aria-label="Close photo">&times;</button>
                <img id="lightbox-img" src="" alt="">
                <video id="lightbox-video" controls playsinline preload="metadata" hidden></video>
                <iframe id="lightbox-frame" allow="autoplay; fullscreen" allowfullscreen hidden></iframe>
                <div id="lightbox-meta">
                    <div id="lightbox-header">
                        <span></span>
                        <div id="lightbox-title"></div>
                        <div id="lightbox-index"></div>
                    </div>
                    <div id="lightbox-note"></div>
                </div>
                <div id="lightbox-nav">
                    <button class="nav-btn" id="prev-btn" aria-label="Previous photo">
                        <span class="nav-icon">&larr;</span>
                        <span class="nav-label">&larr; Previous</span>
                    </button>
                    <button class="nav-btn" id="next-btn" aria-label="Next photo">
                        <span class="nav-icon">&rarr;</span>
                        <span class="nav-label">Next &rarr;</span>
                    </button>
                </div>
                <div id="lightbox-actions">
                    <button class="nav-btn" id="notes-btn" aria-label="View notes" aria-expanded="false" aria-controls="lightbox-meta">View Notes</button>
                    <button class="nav-btn" id="close-btn-mobile" aria-label="Close photo">Close</button>
                </div>
            </div>
        </div>
    </div>


    <script>
        // Photo data
        const photos = {photos_json};
        const imageWidth = {image_width};
        const imageHeight = {image_height};

        // State
        let scale = 1;
        let translateX = 0;
        let translateY = 0;
        let isPanning = false;
        let startX = 0;
        let startY = 0;
        let isPinching = false;
        let pinchStartDistance = 0;
        let pinchStartScale = 1;
        let currentPhotoIndex = -1;
        let lastViewportWidth = 0;
        let lastViewportHeight = 0;
        let lastFocusedElement = null;

        // Elements
        const viewport = document.getElementById('viewport');
        const container = document.getElementById('map-container');
        const lightbox = document.getElementById('lightbox');
        const lightboxImg = document.getElementById('lightbox-img');
        const lightboxVideo = document.getElementById('lightbox-video');
        const lightboxFrame = document.getElementById('lightbox-frame');
        const lightboxTitle = document.getElementById('lightbox-title');
        const lightboxIndex = document.getElementById('lightbox-index');
        const lightboxNote = document.getElementById('lightbox-note');
        const lightboxMeta = document.getElementById('lightbox-meta');
        const lightboxNav = document.getElementById('lightbox-nav');
        const lightboxActions = document.getElementById('lightbox-actions');
        const legend = document.getElementById('legend');
        const closeBtn = document.getElementById('lightbox-close');
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');
        const notesBtn = document.getElementById('notes-btn');
        const closeBtnMobile = document.getElementById('close-btn-mobile');
        const sidebarToggle = document.getElementById('sidebar-toggle');
        const sidebarClose = document.getElementById('sidebar-close');
        const sidebarScrim = document.getElementById('sidebar-scrim');
        const mobileMedia = window.matchMedia('(max-width: 900px)');

        function updateViewportInsets() {{
            if (!window.visualViewport) {{
                document.documentElement.style.setProperty('--viewport-bottom-inset', '0px');
                return;
            }}
            const viewport = window.visualViewport;
            const bottomInset = Math.max(
                0,
                window.innerHeight - (viewport.height + viewport.offsetTop)
            );
            document.documentElement.style.setProperty('--viewport-bottom-inset', `${{bottomInset}}px`);
        }}

        function setSidebarOpen(isOpen) {{
            document.body.classList.toggle('sidebar-open', isOpen);
            if (!sidebarToggle) return;
            sidebarToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            sidebarToggle.textContent = isOpen ? 'Close' : 'Menu';
        }}

        function syncSidebarToggle() {{
            if (!sidebarToggle) return;
            if (!mobileMedia.matches) {{
                document.body.classList.remove('sidebar-open');
                sidebarToggle.setAttribute('aria-expanded', 'true');
                sidebarToggle.textContent = 'Menu';
                return;
            }}
            if (!document.body.classList.contains('sidebar-open')) {{
                setSidebarOpen(false);
            }}
        }}

        if (sidebarToggle) {{
            sidebarToggle.addEventListener('click', () => {{
                setSidebarOpen(!document.body.classList.contains('sidebar-open'));
            }});
        }}

        if (sidebarScrim) {{
            sidebarScrim.addEventListener('click', () => setSidebarOpen(false));
        }}

        if (sidebarClose) {{
            sidebarClose.addEventListener('click', () => setSidebarOpen(false));
        }}

        // Initial fit
        function fitToViewport() {{
            const vw = viewport.clientWidth;
            const vh = viewport.clientHeight;
            const scaleX = vw / imageWidth;
            const scaleY = vh / imageHeight;
            scale = Math.min(scaleX, scaleY) * 0.95;
            translateX = (vw - imageWidth * scale) / 2;
            translateY = (vh - imageHeight * scale) / 2;
            updateTransform();
        }}

        function updateTransform() {{
            container.style.transform = `translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
        }}

        function preserveViewOnResize(newWidth, newHeight) {{
            if (lastViewportWidth === 0 || lastViewportHeight === 0) {{
                fitToViewport();
                return;
            }}
            const prevCenterX = lastViewportWidth / 2;
            const prevCenterY = lastViewportHeight / 2;
            const imageCenterX = (prevCenterX - translateX) / scale;
            const imageCenterY = (prevCenterY - translateY) / scale;
            translateX = (newWidth / 2) - imageCenterX * scale;
            translateY = (newHeight / 2) - imageCenterY * scale;
            updateTransform();
        }}

        function clampScale(value) {{
            return Math.min(Math.max(0.1, value), 10);
        }}

        function zoomAt(pointX, pointY, targetScale) {{
            const newScale = clampScale(targetScale);
            translateX = pointX - (pointX - translateX) * (newScale / scale);
            translateY = pointY - (pointY - translateY) * (newScale / scale);
            scale = newScale;
            updateTransform();
        }}

        // Initialize
        function handleResize() {{
            const newWidth = viewport.clientWidth;
            const newHeight = viewport.clientHeight;
            if (lastViewportWidth === 0 || lastViewportHeight === 0) {{
                fitToViewport();
            }} else {{
                preserveViewOnResize(newWidth, newHeight);
            }}
            lastViewportWidth = newWidth;
            lastViewportHeight = newHeight;
            syncSidebarToggle();
            updateViewportInsets();
            updateLightboxLayout();
        }}

        handleResize();
        window.addEventListener('resize', handleResize);
        window.addEventListener('orientationchange', () => {{
            handleResize();
            setTimeout(handleResize, 200);
        }});
        if (window.visualViewport) {{
            window.visualViewport.addEventListener('resize', () => {{
                updateViewportInsets();
                updateLightboxLayout();
            }});
            window.visualViewport.addEventListener('scroll', () => {{
                updateViewportInsets();
                updateLightboxLayout();
            }});
        }}

        // Zoom controls
        document.getElementById('zoom-in').addEventListener('click', () => zoom(1.3));
        document.getElementById('zoom-out').addEventListener('click', () => zoom(1/1.3));
        document.getElementById('fit-view').addEventListener('click', fitToViewport);

        function zoom(factor) {{
            const vw = viewport.clientWidth;
            const vh = viewport.clientHeight;
            const centerX = vw / 2;
            const centerY = vh / 2;
            zoomAt(centerX, centerY, scale * factor);
        }}

        function getTouchDistance(touches) {{
            const dx = touches[0].clientX - touches[1].clientX;
            const dy = touches[0].clientY - touches[1].clientY;
            return Math.hypot(dx, dy);
        }}

        function getTouchCenter(touches) {{
            return {{
                x: (touches[0].clientX + touches[1].clientX) / 2,
                y: (touches[0].clientY + touches[1].clientY) / 2,
            }};
        }}

        // Mouse wheel zoom
        viewport.addEventListener('wheel', (e) => {{
            e.preventDefault();
            const factor = e.deltaY > 0 ? 0.9 : 1.1;
            zoom(factor);
        }}, {{ passive: false }});

        // Pan
        container.addEventListener('mousedown', (e) => {{
            if (e.target.classList.contains('marker') || e.target.classList.contains('marker-number')) return;
            isPanning = true;
            startX = e.clientX - translateX;
            startY = e.clientY - translateY;
            container.style.cursor = 'grabbing';
        }});

        document.addEventListener('mousemove', (e) => {{
            if (!isPanning) return;
            translateX = e.clientX - startX;
            translateY = e.clientY - startY;
            updateTransform();
        }});

        document.addEventListener('mouseup', () => {{
            isPanning = false;
            container.style.cursor = 'grab';
        }});

        // Touch pan for mobile
        container.addEventListener('touchstart', (e) => {{
            if (e.touches.length === 2) {{
                isPinching = true;
                isPanning = false;
                pinchStartDistance = getTouchDistance(e.touches);
                pinchStartScale = scale;
                e.preventDefault();
                return;
            }}
            if (e.touches.length !== 1) return;
            if (e.target.classList.contains('marker') || e.target.classList.contains('marker-number')) return;
            isPanning = true;
            startX = e.touches[0].clientX - translateX;
            startY = e.touches[0].clientY - translateY;
        }}, {{ passive: false }});

        container.addEventListener('touchmove', (e) => {{
            if (isPinching && e.touches.length === 2) {{
                e.preventDefault();
                if (pinchStartDistance > 0) {{
                    const distance = getTouchDistance(e.touches);
                    const center = getTouchCenter(e.touches);
                    const targetScale = pinchStartScale * (distance / pinchStartDistance);
                    zoomAt(center.x, center.y, targetScale);
                }}
                return;
            }}
            if (!isPanning || e.touches.length !== 1) return;
            e.preventDefault();
            translateX = e.touches[0].clientX - startX;
            translateY = e.touches[0].clientY - startY;
            updateTransform();
        }}, {{ passive: false }});

        container.addEventListener('touchend', (e) => {{
            if (e && e.touches) {{
                if (e.touches.length < 2) {{
                    isPinching = false;
                    pinchStartDistance = 0;
                }}
                if (e.touches.length === 0) {{
                    isPanning = false;
                }}
                return;
            }}
            isPinching = false;
            isPanning = false;
        }});

        container.addEventListener('touchcancel', () => {{
            isPinching = false;
            isPanning = false;
            pinchStartDistance = 0;
        }});

        // Lightbox
        document.querySelectorAll('.marker').forEach(marker => {{
            marker.addEventListener('click', (e) => {{
                e.stopPropagation();
                currentPhotoIndex = parseInt(marker.dataset.index);
                showPhoto(currentPhotoIndex);
            }});
            marker.addEventListener('keydown', (e) => {{
                if (e.key === 'Enter' || e.key === ' ') {{
                    e.preventDefault();
                    marker.click();
                }}
            }});
        }});

        if (legend) {{
            legend.querySelectorAll('.legend-item').forEach((button) => {{
                button.addEventListener('click', () => {{
                    const isActive = button.getAttribute('aria-pressed') !== 'true';
                    const color = button.dataset.color;
                    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
                    if (!color) return;
                    document.querySelectorAll(`.marker-color-${{color}}`).forEach(marker => {{
                        marker.classList.toggle('marker-hidden', !isActive);
                    }});
                    updateNavButtons();
                }});
            }});
        }}

        function getVisiblePhotoIndices() {{
            return Array.from(document.querySelectorAll('.marker'))
                .filter(marker => !marker.classList.contains('marker-hidden'))
                .map(marker => parseInt(marker.dataset.index, 10))
                .filter(Number.isFinite)
                .sort((a, b) => a - b);
        }}

        function getNextVisibleIndex(fromIndex, direction) {{
            const visible = getVisiblePhotoIndices();
            if (!visible.length) return -1;
            if (direction > 0) {{
                for (const index of visible) {{
                    if (index > fromIndex) {{
                        return index;
                    }}
                }}
                return -1;
            }}
            for (let i = visible.length - 1; i >= 0; i -= 1) {{
                if (visible[i] < fromIndex) {{
                    return visible[i];
                }}
            }}
            return -1;
        }}

        function navigatePhoto(direction) {{
            const targetIndex = getNextVisibleIndex(currentPhotoIndex, direction);
            if (targetIndex >= 0) {{
                showPhoto(targetIndex);
            }}
        }}

        function updateLightboxLayout() {{
            if (!lightbox.classList.contains('active')) return;
            const isMobile = mobileMedia.matches;
            const notesOpen = document.body.classList.contains('lightbox-notes-open');
            const metaHeight = (!isMobile || notesOpen) && lightboxMeta
                ? lightboxMeta.offsetHeight || 0
                : 0;
            const navHeight = lightboxNav.offsetHeight || 0;
            const actionsHeight = lightboxActions ? lightboxActions.offsetHeight || 0 : 0;
            const chrome = isMobile ? 120 : 140;
            const styles = window.getComputedStyle(lightbox);
            const paddingTop = parseFloat(styles.paddingTop) || 0;
            const paddingBottom = parseFloat(styles.paddingBottom) || 0;
            const availableHeight = (lightbox.clientHeight || window.innerHeight) - paddingTop - paddingBottom;
            const maxHeight = Math.max(160, availableHeight - metaHeight - navHeight - actionsHeight - chrome);
            lightboxImg.style.maxHeight = `${{maxHeight}}px`;
            lightboxVideo.style.maxHeight = `${{maxHeight}}px`;
            lightboxFrame.style.maxHeight = `${{maxHeight}}px`;
        }}

        function setNotesOpen(isOpen) {{
            document.body.classList.toggle('lightbox-notes-open', isOpen);
            if (notesBtn) {{
                notesBtn.textContent = isOpen ? 'Hide Notes' : 'View Notes';
                notesBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            }}
            updateLightboxLayout();
        }}

        if (notesBtn) {{
            notesBtn.addEventListener('click', (e) => {{
                e.stopPropagation();
                setNotesOpen(!document.body.classList.contains('lightbox-notes-open'));
            }});
        }}

        function resetLightboxMedia() {{
            lightboxVideo.pause();
            lightboxVideo.removeAttribute('src');
            lightboxVideo.load();
            lightboxVideo.hidden = true;
            lightboxFrame.src = 'about:blank';
            lightboxFrame.hidden = true;
            lightboxImg.src = '';
            lightboxImg.hidden = false;
        }}

        function applyLightboxMedia(photo) {{
            resetLightboxMedia();
            if (photo.isVideo) {{
                lightboxImg.hidden = true;
                if (photo.embed) {{
                    lightboxFrame.src = photo.src;
                    lightboxFrame.hidden = false;
                }} else {{
                    if (photo.poster) {{ lightboxVideo.poster = photo.poster; }}
                    else {{ lightboxVideo.removeAttribute('poster'); }}
                    lightboxVideo.src = photo.src;
                    lightboxVideo.hidden = false;
                }}
            }} else {{
                lightboxImg.src = photo.src;
                lightboxImg.hidden = false;
            }}
        }}

        function showPhoto(index) {{
            if (index < 0 || index >= photos.length) return;
            currentPhotoIndex = index;
            const photo = photos[index];
            applyLightboxMedia(photo);
            lightboxTitle.textContent = photo.filename || "";
            lightboxIndex.textContent = `Photo ${{index + 1}} of ${{photos.length}}`;
            const noteText = photo.note ? String(photo.note) : "";
            if (noteText.trim().length) {{
                lightboxNote.textContent = noteText;
                lightboxNote.style.display = "block";
            }} else {{
                lightboxNote.textContent = "";
                lightboxNote.style.display = "none";
            }}
            if (!lightbox.classList.contains('active')) {{
                lastFocusedElement = document.activeElement;
            }}
            lightbox.classList.add('active');
            lightbox.setAttribute('aria-hidden', 'false');
            setNotesOpen(false);
            updateNavButtons();
            requestAnimationFrame(() => {{
                updateLightboxLayout();
                const focusTarget = mobileMedia.matches ? closeBtnMobile : closeBtn;
                if (focusTarget) {{
                    focusTarget.focus();
                }} else {{
                    lightbox.focus();
                }}
            }});
        }}

        function updateNavButtons() {{
            const prevIndex = getNextVisibleIndex(currentPhotoIndex, -1);
            const nextIndex = getNextVisibleIndex(currentPhotoIndex, 1);
            prevBtn.style.visibility = prevIndex >= 0 ? 'visible' : 'hidden';
            nextBtn.style.visibility = nextIndex >= 0 ? 'visible' : 'hidden';
        }}

        function closeLightbox() {{
            setNotesOpen(false);
            lightbox.classList.remove('active');
            lightbox.setAttribute('aria-hidden', 'true');
            resetLightboxMedia();
            currentPhotoIndex = -1;
            if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {{
                lastFocusedElement.focus();
                lastFocusedElement = null;
            }}
        }}

        closeBtn.addEventListener('click', closeLightbox);
        if (closeBtnMobile) {{
            closeBtnMobile.addEventListener('click', closeLightbox);
        }}
        lightbox.addEventListener('click', (e) => {{
            if (e.target === lightbox) closeLightbox();
        }});

        prevBtn.addEventListener('click', () => navigatePhoto(-1));
        nextBtn.addEventListener('click', () => navigatePhoto(1));

        function getLightboxFocusable() {{
            if (!lightbox) return [];
            return Array.from(
                lightbox.querySelectorAll('button, [href], [tabindex]:not([tabindex="-1"])')
            ).filter(el => !el.hasAttribute('disabled') && el.offsetParent !== null);
        }}

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {{
            if (!lightbox.classList.contains('active')) return;
            if (e.key === 'Escape') {{
                closeLightbox();
                return;
            }}
            if (e.key === 'ArrowLeft') {{
                navigatePhoto(-1);
                return;
            }}
            if (e.key === 'ArrowRight') {{
                navigatePhoto(1);
                return;
            }}
            if (e.key === 'Tab') {{
                const focusable = getLightboxFocusable();
                if (!focusable.length) return;
                if (!lightbox.contains(document.activeElement)) {{
                    e.preventDefault();
                    focusable[0].focus();
                    return;
                }}
                const first = focusable[0];
                const last = focusable[focusable.length - 1];
                if (e.shiftKey && document.activeElement === first) {{
                    e.preventDefault();
                    last.focus();
                }} else if (!e.shiftKey && document.activeElement === last) {{
                    e.preventDefault();
                    first.focus();
                }}
            }}
        }});
    </script>
</body>
</html>'''

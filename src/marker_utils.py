"""
Marker Utilities for PicPlotter Auto.

Provides marker colorization functionality to generate different colored
versions of the marker icon.
"""

import io
import colorsys
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw

from src.config import get_asset_path, get_user_logo_path

MARKER_BASE_SIZE = 256


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def rgb_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """Convert RGB (0-255) to HSL (0-1)."""
    r_norm, g_norm, b_norm = r / 255.0, g / 255.0, b / 255.0
    h, l, s = colorsys.rgb_to_hls(r_norm, g_norm, b_norm)
    return h, s, l


def hsl_to_rgb(h: float, s: float, l: float) -> Tuple[int, int, int]:
    """Convert HSL (0-1) to RGB (0-255)."""
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


LOGO_CONTENT_RATIO = 0.82


def _normalize_to_square(
    image: Image.Image,
    size: int,
    content_ratio: float = LOGO_CONTENT_RATIO,
) -> Image.Image:
    """
    Center the image on a transparent square canvas of the given size.

    Longer edge is scaled to `content_ratio * size` (leaving margin for the
    group-color rectangle outline drawn in colorize_marker). Aspect ratio
    is preserved.
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    if w == 0 or h == 0:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    long_edge = max(w, h)
    target = max(1, int(size * content_ratio))
    scale = target / long_edge
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(resized, ((size - new_w) // 2, (size - new_h) // 2), resized)
    return canvas


def colorize_marker(
    marker_image: Image.Image,
    target_color: str,
    source_color: str = "#2A9D6E",
) -> Image.Image:
    """
    Draw a colored rectangular outline around the marker's content area.

    The logo's pixels are preserved unchanged — group identity comes from
    the rectangle color, not from tinting the logo. The rectangle hugs the
    logo's alpha bounding box with a small inset for breathing room.
    'default' uses a black rectangle. 'none' returns the logo with no
    rectangle at all (used in Page mode).

    Args:
        marker_image: PIL Image in RGBA mode (logo on transparent canvas)
        target_color: Hex color for the rectangle (e.g., "#F6D11A"),
            "default" for a black rectangle, or "none" for no rectangle
        source_color: Unused, kept for backwards compatibility

    Returns:
        New PIL Image: original logo + colored rectangle outline (or
        original logo unmodified when target_color == "none")
    """
    _ = source_color
    if marker_image.mode != "RGBA":
        marker_image = marker_image.convert("RGBA")

    if target_color.lower() == "none":
        return marker_image.copy()

    if target_color.lower() == "default":
        rect_rgb = (0, 0, 0)
    else:
        rect_rgb = hex_to_rgb(target_color)

    result = marker_image.copy()

    bbox = result.getbbox()
    if bbox is None:
        # No visible content (e.g., empty logo) — frame the whole canvas
        bbox = (0, 0, result.size[0] - 1, result.size[1] - 1)

    canvas_w, canvas_h = result.size
    canvas_size = max(canvas_w, canvas_h)
    inset = max(8, canvas_size // 32)
    stroke = max(10, canvas_size // 20)

    # Expand bbox outward by inset, clamped to canvas. PIL strokes are
    # centered on the rectangle line, so half the stroke also extends
    # inward — pull the rectangle in by stroke // 2 from each edge to
    # ensure the full outline stays within the canvas.
    half_stroke = stroke // 2
    x0 = max(half_stroke, bbox[0] - inset)
    y0 = max(half_stroke, bbox[1] - inset)
    x1 = min(canvas_w - 1 - half_stroke, bbox[2] + inset)
    y1 = min(canvas_h - 1 - half_stroke, bbox[3] + inset)

    if x1 <= x0 or y1 <= y0:
        return result

    draw = ImageDraw.Draw(result)
    draw.rectangle([x0, y0, x1, y1], outline=rect_rgb + (255,), width=stroke)

    return result


def create_fallback_marker(
    size: int,
    color: str,
    text: str = "",
) -> Image.Image:
    """
    Create a simple circular marker as fallback when PNG asset is unavailable.

    Args:
        size: Size of the marker in pixels
        color: Hex color for the marker
        text: Optional text to draw in center (unused in this app)

    Returns:
        PIL Image with the marker
    """
    _ = text
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    padding = 2
    fill_color = hex_to_rgb(color)
    draw.ellipse(
        [padding, padding, size - padding - 1, size - padding - 1],
        fill=fill_color + (255,),
        outline=(255, 255, 255, 255),
        width=2,
    )

    return image


class MarkerColorizer:
    """
    Caches colorized marker images for efficient rendering.

    Creates colored variants of the marker image on demand and
    caches them for reuse.
    """

    def __init__(self) -> None:
        self._base_image: Optional[Image.Image] = None
        self._base_image_full: Optional[Image.Image] = None
        self._cache: Dict[str, Image.Image] = {}
        self._load_base_image()

    def _load_base_image(self) -> None:
        """Load the base marker image, preferring user-uploaded logo over bundled default."""
        user_logo = get_user_logo_path()
        source_path = None
        if user_logo is not None and user_logo.exists():
            source_path = user_logo
        else:
            marker_path = get_asset_path("marker_outlined_transparent.png")
            if marker_path.exists():
                source_path = marker_path

        if source_path is None:
            self._base_image = None
            self._base_image_full = None
            return

        raw = Image.open(source_path).convert("RGBA")
        self._base_image = _normalize_to_square(raw, MARKER_BASE_SIZE)
        # Page mode (color="none") uses the logo without margin reserved for
        # the group rectangle, so the plain logo reads at full size.
        self._base_image_full = _normalize_to_square(raw, MARKER_BASE_SIZE, content_ratio=1.0)

    def reset(self) -> None:
        """Clear cache and reload base image (call after logo upload/clear)."""
        self._cache.clear()
        self._load_base_image()

    def get_colored_marker(self, color: str, size: int) -> Image.Image:
        """
        Get a colored marker image at the specified size.

        Args:
            color: Hex color for the marker, "default" (black rectangle),
                or "none" (plain logo, no rectangle)
            size: Desired size in pixels

        Returns:
            PIL Image of the colored marker
        """
        cache_key = f"{color}_{size}"

        if cache_key not in self._cache:
            base = self._base_image_full if color.lower() == "none" else self._base_image
            if base is not None:
                colored = colorize_marker(base, color)
                resized = colored.resize(
                    (size, size),
                    Image.Resampling.LANCZOS,
                )
                self._cache[cache_key] = resized
            else:
                fallback_color = "#000000" if color.lower() in ("default", "none") else color
                self._cache[cache_key] = create_fallback_marker(size, fallback_color)

        return self._cache[cache_key]

    def get_colored_marker_bytes(self, color: str, size: int) -> bytes:
        """
        Get colored marker as PNG bytes for embedding in HTML.

        Args:
            color: Hex color for the marker
            size: Desired size in pixels

        Returns:
            PNG image data as bytes
        """
        marker = self.get_colored_marker(color, size)
        buffer = io.BytesIO()
        marker.save(buffer, format="PNG")
        return buffer.getvalue()

    def clear_cache(self) -> None:
        """Clear the marker cache."""
        self._cache.clear()

    def has_base_image(self) -> bool:
        """Check if the base marker image is available."""
        return self._base_image is not None


_colorizer: Optional[MarkerColorizer] = None


def get_colorizer() -> MarkerColorizer:
    """Get the global MarkerColorizer instance."""
    global _colorizer
    if _colorizer is None:
        _colorizer = MarkerColorizer()
    return _colorizer


def reset_colorizer() -> None:
    """Reset the global colorizer cache and reload its base image."""
    global _colorizer
    if _colorizer is not None:
        _colorizer.reset()

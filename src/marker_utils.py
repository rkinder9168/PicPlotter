"""
Marker Utilities for PicPlotter Auto.

Provides marker colorization functionality to generate different colored
versions of the marker icon.
"""

import io
import colorsys
from typing import Dict, Optional, Tuple

import numpy as np
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


def _normalize_to_square(image: Image.Image, size: int) -> Image.Image:
    """
    Center the image on a transparent square canvas of the given size.

    Longer edge is scaled to `size`, aspect ratio is preserved. Used when
    a user-supplied logo (which may be wide or tall) becomes the marker
    base — guarantees a consistent square footprint downstream.
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    if w == 0 or h == 0:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    long_edge = max(w, h)
    scale = size / long_edge
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
    Colorize a marker image with a solid color for all stripes.

    All colored stripes become the exact same target color (completely solid).
    White outlines are preserved. For black markers, the number becomes green.

    Uses NumPy vectorized operations for 10-50x faster processing compared
    to pixel-by-pixel Python loops.

    Args:
        marker_image: PIL Image in RGBA mode
        target_color: Hex color for all stripes (e.g., "#F6D11A") or "default"
        source_color: Hex color of the original marker (unused, kept for compatibility)

    Returns:
        New PIL Image with solid colored stripes
    """
    if marker_image.mode != "RGBA":
        marker_image = marker_image.convert("RGBA")

    if target_color.lower() == "default":
        return marker_image.copy()

    target_rgb = hex_to_rgb(target_color)
    is_black_group = target_color.lower() == "#2a2a2a"
    green_rgb = hex_to_rgb("#2A9D6E")

    # Convert to NumPy array for vectorized operations
    arr = np.array(marker_image, dtype=np.uint8)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

    # Calculate brightness and max channel using vectorized operations
    brightness = (r.astype(np.float32) + g.astype(np.float32) + b.astype(np.float32)) / 3.0
    max_channel = np.maximum(np.maximum(r, g), b)

    # Create masks for different pixel categories
    visible = a > 0
    not_white = brightness <= 240
    not_black = max_channel >= 20
    is_black_pixel = max_channel < 20

    # Mask for pixels that should get the target color
    # (visible, not white, not black)
    colorize_mask = visible & not_white & not_black

    # Apply target color to matching pixels
    arr[colorize_mask, 0] = target_rgb[0]
    arr[colorize_mask, 1] = target_rgb[1]
    arr[colorize_mask, 2] = target_rgb[2]

    # For black group markers, colorize black pixels with green
    if is_black_group:
        black_colorize_mask = visible & not_white & is_black_pixel
        arr[black_colorize_mask, 0] = green_rgb[0]
        arr[black_colorize_mask, 1] = green_rgb[1]
        arr[black_colorize_mask, 2] = green_rgb[2]

    return Image.fromarray(arr, mode="RGBA")


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
        self._cache: Dict[str, Image.Image] = {}
        self._load_base_image()

    def _load_base_image(self) -> None:
        """Load the base marker image, preferring user-uploaded logo over bundled default."""
        user_logo = get_user_logo_path()
        if user_logo is not None and user_logo.exists():
            raw = Image.open(user_logo).convert("RGBA")
            self._base_image = _normalize_to_square(raw, MARKER_BASE_SIZE)
            return

        marker_path = get_asset_path("marker_outlined_transparent.png")
        if marker_path.exists():
            self._base_image = Image.open(marker_path).convert("RGBA")
        else:
            self._base_image = None

    def reset(self) -> None:
        """Clear cache and reload base image (call after logo upload/clear)."""
        self._cache.clear()
        self._load_base_image()

    def get_colored_marker(self, color: str, size: int) -> Image.Image:
        """
        Get a colored marker image at the specified size.

        Args:
            color: Hex color for the marker
            size: Desired size in pixels

        Returns:
            PIL Image of the colored marker
        """
        cache_key = f"{color}_{size}"

        if cache_key not in self._cache:
            if self._base_image is not None:
                colored = colorize_marker(self._base_image, color)
                resized = colored.resize(
                    (size, size),
                    Image.Resampling.LANCZOS,
                )
                self._cache[cache_key] = resized
            else:
                self._cache[cache_key] = create_fallback_marker(size, color)

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

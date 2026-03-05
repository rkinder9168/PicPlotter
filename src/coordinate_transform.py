"""
Coordinate transformation for converting GPS coordinates to pixel positions.

Uses affine transformation to convert between GPS coordinates and pixel
positions on an aerial image.
"""

from typing import NamedTuple, Optional
from dataclasses import dataclass

# Import GPSCoordinates from exif_extractor
from src.exif_extractor import GPSCoordinates


class PixelPoint(NamedTuple):
    """A point in pixel coordinates on the aerial image."""
    x: float
    y: float


@dataclass
class AffineTransform:
    """
    Affine transformation matrix for GPS -> pixel conversion.

    Pixel_x = a * lon + b * lat + c
    Pixel_y = d * lon + e * lat + f
    """
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    def transform(self, gps: GPSCoordinates) -> PixelPoint:
        """Convert GPS coordinates to pixel position."""
        x = self.a * gps.longitude + self.b * gps.latitude + self.c
        y = self.d * gps.longitude + self.e * gps.latitude + self.f
        return PixelPoint(x, y)

    def inverse_transform(self, pixel: PixelPoint) -> Optional[GPSCoordinates]:
        """
        Convert pixel position back to GPS coordinates.
        Returns None if transform is degenerate.
        """
        # Solve the linear system for lon, lat
        # x = a*lon + b*lat + c
        # y = d*lon + e*lat + f
        det = self.a * self.e - self.b * self.d
        if abs(det) < 1e-10:
            return None

        x_adj = pixel.x - self.c
        y_adj = pixel.y - self.f

        lon = (self.e * x_adj - self.b * y_adj) / det
        lat = (-self.d * x_adj + self.a * y_adj) / det

        return GPSCoordinates(lat, lon)

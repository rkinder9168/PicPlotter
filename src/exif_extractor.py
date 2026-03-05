"""
EXIF/GPS Extraction Module for PicPlotter Auto

Extracts GPS coordinates and metadata from JPG and HEIC images.
"""

from PIL import Image, ExifTags
from PIL.ExifTags import TAGS, GPSTAGS
from typing import Optional, Tuple, NamedTuple, Dict, Any, Union
from datetime import datetime
from pathlib import Path

# Register HEIC support if available
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False


class GPSCoordinates(NamedTuple):
    """GPS coordinates with optional altitude."""
    latitude: float
    longitude: float
    altitude: Optional[float] = None


class ImageMetadata(NamedTuple):
    """Complete metadata extracted from an image."""
    filepath: Path
    filename: str
    gps: Optional[GPSCoordinates]
    timestamp: Optional[datetime]
    camera_make: Optional[str]
    camera_model: Optional[str]


def _convert_to_degrees(value) -> float:
    """
    Convert GPS coordinates from EXIF format to decimal degrees.

    EXIF stores GPS as tuples of rationals: ((deg, 1), (min, 1), (sec, 100))
    or as IFDRational objects in newer Pillow versions.
    """
    try:
        # Handle different formats
        if hasattr(value[0], 'numerator'):
            # IFDRational objects
            d = float(value[0])
            m = float(value[1])
            s = float(value[2])
        elif isinstance(value[0], tuple):
            # Tuple of tuples: ((num, denom), ...)
            d = value[0][0] / value[0][1] if value[0][1] != 0 else 0
            m = value[1][0] / value[1][1] if value[1][1] != 0 else 0
            s = value[2][0] / value[2][1] if value[2][1] != 0 else 0
        else:
            # Direct float values
            d = float(value[0])
            m = float(value[1])
            s = float(value[2])

        return d + (m / 60.0) + (s / 3600.0)
    except (TypeError, IndexError, ZeroDivisionError):
        return 0.0


def _get_gps_data(exif_data: Union[dict, Image.Exif]) -> Optional[dict]:
    """Extract GPS IFD from EXIF data."""
    if hasattr(exif_data, "get_ifd"):
        try:
            gps_ifd = exif_data.get_ifd(ExifTags.IFD.GPSInfo)
            if gps_ifd:
                gps_data = {}
                for gps_tag_id, gps_value in gps_ifd.items():
                    gps_tag_name = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_data[gps_tag_name] = gps_value
                return gps_data
        except Exception:
            pass

    for tag_id, value in exif_data.items():
        tag_name = TAGS.get(tag_id, tag_id)
        if tag_name == "GPSInfo":
            gps_data = {}
            for gps_tag_id, gps_value in value.items():
                gps_tag_name = GPSTAGS.get(gps_tag_id, gps_tag_id)
                gps_data[gps_tag_name] = gps_value
            return gps_data
    return None


def _normalize_gps_ref(value: Any) -> str:
    """Normalize GPS reference values (N/S/E/W) to uppercase strings."""
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("ascii", errors="ignore")
        except Exception:
            return ""
    if isinstance(value, str):
        return value.strip().upper()
    return str(value).strip().upper()


def _get_exif_data(img: Image.Image) -> Optional[Union[dict, Image.Exif]]:
    """Return EXIF data when available."""
    exif_data: Optional[Union[dict, Image.Exif]] = None
    if hasattr(img, "getexif"):
        try:
            exif = img.getexif()
            if exif:
                exif_data = exif
        except Exception:
            exif_data = None
    if exif_data is None and hasattr(img, "_getexif"):
        try:
            exif = img._getexif()
            if exif:
                exif_data = exif
        except Exception:
            exif_data = None
    if not exif_data:
        try:
            exif_bytes = img.info.get("exif")
        except Exception:
            exif_bytes = None
        if exif_bytes:
            try:
                exif_obj = Image.Exif()
                exif_obj.load(exif_bytes)
                exif_data = exif_obj if exif_obj else None
            except Exception:
                exif_data = None
    return exif_data


def _extract_gps_from_exif(exif_data: Optional[Union[dict, Image.Exif]]) -> Optional[GPSCoordinates]:
    """
    Extract GPS coordinates from pre-loaded EXIF data.

    Args:
        exif_data: EXIF data already extracted from an image

    Returns:
        GPSCoordinates if GPS data found, None otherwise
    """
    if not exif_data:
        return None

    gps_data = _get_gps_data(exif_data)

    if not gps_data:
        return None

    # Check for required GPS fields
    if "GPSLatitude" not in gps_data or "GPSLongitude" not in gps_data:
        return None

    # Convert latitude
    lat = _convert_to_degrees(gps_data["GPSLatitude"])
    lat_ref = _normalize_gps_ref(gps_data.get("GPSLatitudeRef", "N"))
    if lat_ref == "S":
        lat = -lat

    # Convert longitude
    lon = _convert_to_degrees(gps_data["GPSLongitude"])
    lon_ref = _normalize_gps_ref(gps_data.get("GPSLongitudeRef", "E"))
    if lon_ref == "W":
        lon = -lon

    # Get altitude if available
    altitude = None
    if "GPSAltitude" in gps_data:
        try:
            alt_value = gps_data["GPSAltitude"]
            if hasattr(alt_value, 'numerator'):
                altitude = float(alt_value)
            elif isinstance(alt_value, tuple):
                altitude = alt_value[0] / alt_value[1] if alt_value[1] != 0 else 0
            else:
                altitude = float(alt_value)

            # Check altitude reference (0 = above sea level, 1 = below)
            alt_ref = gps_data.get("GPSAltitudeRef", 0)
            if isinstance(alt_ref, (bytes, bytearray)):
                alt_ref = alt_ref[0] if alt_ref else 0
            if isinstance(alt_ref, str):
                try:
                    alt_ref = int(alt_ref)
                except ValueError:
                    alt_ref = 0
            if alt_ref == 1:
                altitude = -altitude
        except (TypeError, IndexError, ZeroDivisionError):
            altitude = None

    return GPSCoordinates(latitude=lat, longitude=lon, altitude=altitude)


def extract_gps(image_path: str) -> Optional[GPSCoordinates]:
    """
    Extract GPS coordinates from an image file.

    Args:
        image_path: Path to the image file (JPG, JPEG, or HEIC)

    Returns:
        GPSCoordinates if GPS data found, None otherwise
    """
    try:
        with Image.open(image_path) as img:
            exif_data = _get_exif_data(img)
            return _extract_gps_from_exif(exif_data)
    except Exception as e:
        print(f"Error extracting GPS from {image_path}: {e}")
        return None


def _extract_timestamp_from_exif(exif_data: Optional[Union[dict, Image.Exif]]) -> Optional[datetime]:
    """
    Extract the photo timestamp from pre-loaded EXIF data.

    Args:
        exif_data: EXIF data already extracted from an image

    Returns:
        datetime if timestamp found, None otherwise
    """
    if not exif_data:
        return None

    # Try different timestamp tags
    timestamp_tags = [
        36867,  # DateTimeOriginal
        36868,  # DateTimeDigitized
        306,    # DateTime
    ]

    for tag_id in timestamp_tags:
        if tag_id in exif_data:
            timestamp_str = exif_data[tag_id]
            try:
                # EXIF format: "YYYY:MM:DD HH:MM:SS"
                return datetime.strptime(timestamp_str, "%Y:%m:%d %H:%M:%S")
            except (ValueError, TypeError):
                continue

    return None


def extract_timestamp(image_path: str) -> Optional[datetime]:
    """
    Extract the photo timestamp from EXIF data.

    Args:
        image_path: Path to the image file

    Returns:
        datetime if timestamp found, None otherwise
    """
    try:
        with Image.open(image_path) as img:
            exif_data = _get_exif_data(img)
            return _extract_timestamp_from_exif(exif_data)
    except Exception as e:
        print(f"Error extracting timestamp from {image_path}: {e}")
        return None


def _extract_camera_from_exif(exif_data: Optional[Union[dict, Image.Exif]]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract camera make and model from pre-loaded EXIF data.

    Args:
        exif_data: EXIF data already extracted from an image

    Returns:
        Tuple of (make, model), either can be None
    """
    if not exif_data:
        return None, None

    make = None
    model = None

    for tag_id, value in exif_data.items():
        tag_name = TAGS.get(tag_id, tag_id)
        if tag_name == "Make":
            make = str(value).strip()
        elif tag_name == "Model":
            model = str(value).strip()

    return make, model


def extract_camera_info(image_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract camera make and model from EXIF data.

    Args:
        image_path: Path to the image file

    Returns:
        Tuple of (make, model), either can be None
    """
    try:
        with Image.open(image_path) as img:
            exif_data = _get_exif_data(img)
            return _extract_camera_from_exif(exif_data)
    except Exception as e:
        print(f"Error extracting camera info from {image_path}: {e}")
        return None, None


def get_image_metadata(image_path: str) -> ImageMetadata:
    """
    Extract all relevant metadata from an image.

    Opens the image file once and extracts all EXIF data in a single pass,
    avoiding the overhead of opening the file multiple times.

    Args:
        image_path: Path to the image file

    Returns:
        ImageMetadata with all extracted information
    """
    path = Path(image_path)
    gps = None
    timestamp = None
    make = None
    model = None

    try:
        with Image.open(image_path) as img:
            exif_data = _get_exif_data(img)
            if exif_data:
                gps = _extract_gps_from_exif(exif_data)
                timestamp = _extract_timestamp_from_exif(exif_data)
                make, model = _extract_camera_from_exif(exif_data)
    except Exception as e:
        print(f"Error extracting metadata from {image_path}: {e}")

    return ImageMetadata(
        filepath=path,
        filename=path.name,
        gps=gps,
        timestamp=timestamp,
        camera_make=make,
        camera_model=model
    )


def get_image_metadata_from_bytes(image_data: bytes, virtual_path: str) -> ImageMetadata:
    """
    Extract all relevant metadata from in-memory image bytes.

    Used for Drive-sourced photos where we have raw bytes instead of a file path.

    Args:
        image_data: Raw image bytes (can be a partial file for EXIF-only extraction)
        virtual_path: Virtual path to use as the filepath (e.g. 'gdrive://id/name.jpg')

    Returns:
        ImageMetadata with all extracted information
    """
    import io

    gps = None
    timestamp = None
    make = None
    model = None

    try:
        with Image.open(io.BytesIO(image_data)) as img:
            exif_data = _get_exif_data(img)
            if exif_data:
                gps = _extract_gps_from_exif(exif_data)
                timestamp = _extract_timestamp_from_exif(exif_data)
                make, model = _extract_camera_from_exif(exif_data)
    except Exception as e:
        print(f"Error extracting metadata from bytes ({virtual_path}): {e}")

    # Use virtual_path parts for filepath and filename
    filename = virtual_path.rsplit("/", 1)[-1] if "/" in virtual_path else virtual_path

    return ImageMetadata(
        filepath=Path(virtual_path),
        filename=filename,
        gps=gps,
        timestamp=timestamp,
        camera_make=make,
        camera_model=model,
    )


def is_supported_format(filepath: str) -> bool:
    """
    Check if the file format is supported.

    Args:
        filepath: Path to check

    Returns:
        True if format is supported
    """
    ext = Path(filepath).suffix.lower()
    supported = ['.jpg', '.jpeg']

    if HEIC_SUPPORTED:
        supported.extend(['.heic', '.heif'])

    return ext in supported


def get_supported_extensions() -> list:
    """
    Get list of supported file extensions.

    Returns:
        List of extensions like ['.jpg', '.jpeg', '.heic']
    """
    extensions = ['.jpg', '.jpeg', '.JPG', '.JPEG']

    if HEIC_SUPPORTED:
        extensions.extend(['.heic', '.heif', '.HEIC', '.HEIF'])

    return extensions

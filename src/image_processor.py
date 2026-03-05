"""
Image Processing Module for PicPlotter Auto

Handles HEIC conversion, resizing, and compression while preserving GPS data.
"""

from PIL import Image, ExifTags
from PIL.ExifTags import TAGS
from pathlib import Path
from typing import Optional, Tuple
import io
import tempfile
import os

# EXIF orientation tag
ORIENTATION_TAG = None
for tag, name in ExifTags.TAGS.items():
    if name == 'Orientation':
        ORIENTATION_TAG = tag
        break

# Register HEIC support if available
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False


class ImageProcessor:
    """Processes images for KMZ export with resizing and compression."""

    def __init__(
        self,
        compression_quality: int = 30,
        max_dimension: int = 1920
    ):
        """
        Initialize the image processor.

        Args:
            compression_quality: JPEG quality (1-100, default 30)
            max_dimension: Maximum width or height in pixels (default 1920)
        """
        self.compression_quality = max(1, min(100, compression_quality))
        self.max_dimension = max_dimension

    def process_image(self, input_path: str) -> Tuple[bytes, str]:
        """
        Process an image: convert to JPG, apply orientation, resize if needed, compress.

        Args:
            input_path: Path to the input image

        Returns:
            Tuple of (processed image bytes, output filename)
        """
        path = Path(input_path)

        # Open image (pillow-heif handles HEIC automatically if registered)
        with Image.open(input_path) as img:
            # Get original EXIF data
            exif_data = self._get_exif_bytes(img)

            # Apply EXIF orientation (rotate image to correct orientation)
            img = self._apply_exif_orientation(img)

            # Convert to RGB if necessary (handles RGBA, P mode, etc.)
            if img.mode in ('RGBA', 'P', 'LA'):
                # Create white background for transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize if larger than max dimension
            img = self._resize_if_needed(img)

            # Save to bytes (without EXIF orientation since we already applied it)
            output = io.BytesIO()
            save_kwargs = {
                'format': 'JPEG',
                'quality': self.compression_quality,
                'optimize': True
            }

            # Note: We don't preserve the original EXIF orientation tag since we've
            # already rotated the image. This prevents double-rotation.

            img.save(output, **save_kwargs)

            # Generate output filename
            output_filename = path.stem + '.jpg'

            return output.getvalue(), output_filename

    def _apply_exif_orientation(self, img: Image.Image) -> Image.Image:
        """
        Apply EXIF orientation to correctly rotate the image.

        Args:
            img: PIL Image object

        Returns:
            Correctly oriented image
        """
        try:
            exif = img._getexif()
            if exif is None or ORIENTATION_TAG is None:
                return img

            orientation = exif.get(ORIENTATION_TAG)
            if orientation is None:
                return img

            # Apply rotation/flip based on EXIF orientation value
            if orientation == 2:
                # Mirrored horizontal
                img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                # Rotated 180
                img = img.transpose(Image.Transpose.ROTATE_180)
            elif orientation == 4:
                # Mirrored vertical
                img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                # Mirrored horizontal then rotated 90 CCW
                img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                img = img.transpose(Image.Transpose.ROTATE_90)
            elif orientation == 6:
                # Rotated 90 CW
                img = img.transpose(Image.Transpose.ROTATE_270)
            elif orientation == 7:
                # Mirrored horizontal then rotated 90 CW
                img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                img = img.transpose(Image.Transpose.ROTATE_270)
            elif orientation == 8:
                # Rotated 90 CCW
                img = img.transpose(Image.Transpose.ROTATE_90)

            return img

        except Exception:
            # If anything goes wrong, return the original image
            return img

    def _resize_if_needed(self, img: Image.Image) -> Image.Image:
        """
        Resize image if it exceeds max_dimension, maintaining aspect ratio.

        Args:
            img: PIL Image object

        Returns:
            Resized image (or original if no resize needed)
        """
        width, height = img.size

        # Check if resize is needed
        if width <= self.max_dimension and height <= self.max_dimension:
            return img

        # Calculate new dimensions maintaining aspect ratio
        if width > height:
            new_width = self.max_dimension
            new_height = int(height * (self.max_dimension / width))
        else:
            new_height = self.max_dimension
            new_width = int(width * (self.max_dimension / height))

        # Use high-quality resampling
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def _get_exif_bytes(self, img: Image.Image) -> Optional[bytes]:
        """
        Extract EXIF data as bytes for preservation.

        Args:
            img: PIL Image object

        Returns:
            EXIF bytes if available, None otherwise
        """
        try:
            # Try to get existing EXIF data
            if hasattr(img, 'info') and 'exif' in img.info:
                return img.info['exif']

            # For some formats, we need to extract differently
            exif_dict = img._getexif()
            if exif_dict:
                # Use PIL's built-in EXIF handling
                return img.info.get('exif')
        except Exception:
            pass

        return None

    def estimate_output_size(self, input_path: str) -> int:
        """
        Estimate the output size of a processed image.

        Args:
            input_path: Path to the input image

        Returns:
            Estimated size in bytes
        """
        try:
            with Image.open(input_path) as img:
                width, height = img.size

                # Calculate output dimensions
                if width > self.max_dimension or height > self.max_dimension:
                    if width > height:
                        out_width = self.max_dimension
                        out_height = int(height * (self.max_dimension / width))
                    else:
                        out_height = self.max_dimension
                        out_width = int(width * (self.max_dimension / height))
                else:
                    out_width, out_height = width, height

                # Rough estimate: compressed JPEG is about 0.5-1.5 bytes per pixel
                # depending on quality and content
                pixels = out_width * out_height
                bytes_per_pixel = 0.3 + (self.compression_quality / 100) * 0.7

                return int(pixels * bytes_per_pixel)

        except Exception:
            # Default estimate if we can't read the file
            return 500000  # 500KB default

    def get_image_dimensions(self, input_path: str) -> Tuple[int, int]:
        """
        Get the dimensions of an image.

        Args:
            input_path: Path to the image

        Returns:
            Tuple of (width, height)
        """
        try:
            with Image.open(input_path) as img:
                return img.size
        except Exception:
            return (0, 0)


def process_single_image(
    input_path: str,
    compression_quality: int = 30,
    max_dimension: int = 1920
) -> Tuple[bytes, str]:
    """
    Convenience function to process a single image.

    Args:
        input_path: Path to the input image
        compression_quality: JPEG quality (1-100)
        max_dimension: Maximum width or height

    Returns:
        Tuple of (processed bytes, output filename)
    """
    processor = ImageProcessor(compression_quality, max_dimension)
    return processor.process_image(input_path)


def estimate_batch_size(
    file_paths: list,
    compression_quality: int = 30,
    max_dimension: int = 1920
) -> int:
    """
    Estimate total output size for a batch of images.

    Args:
        file_paths: List of image file paths
        compression_quality: JPEG quality
        max_dimension: Maximum dimension

    Returns:
        Estimated total size in bytes
    """
    processor = ImageProcessor(compression_quality, max_dimension)
    total = 0

    for path in file_paths:
        total += processor.estimate_output_size(path)

    return total

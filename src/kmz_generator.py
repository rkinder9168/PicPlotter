"""
KMZ Generation Module for PicPlotter Auto

Creates KML/KMZ files with embedded images for Google Earth Pro.
"""

import zipfile
from xml.etree import ElementTree as ET
from typing import List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import io
import os

from PIL import Image, ImageDraw

from .config import get_asset_path
from .exif_extractor import GPSCoordinates


def create_red_dot_icon(size: int = 16) -> bytes:
    """
    Create a small red dot icon for KMZ markers.

    Args:
        size: Diameter of the dot in pixels

    Returns:
        PNG image bytes
    """
    # Create transparent image
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw red circle with white border
    border = 2
    # White border circle
    draw.ellipse([0, 0, size-1, size-1], fill=(255, 255, 255, 255))
    # Red inner circle
    draw.ellipse([border, border, size-1-border, size-1-border], fill=(231, 76, 60, 255))

    # Save to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


@dataclass
class ProcessedPhoto:
    """Represents a photo ready for KMZ export."""
    original_path: str
    filename: str
    image_data: bytes
    gps: GPSCoordinates
    timestamp: Optional[datetime] = None
    description: Optional[str] = None


class KMZGenerator:
    """Generates KMZ files with embedded photos."""

    # KML namespace
    KML_NS = "http://www.opengis.net/kml/2.2"

    # Red dot marker icon (embedded in KMZ)
    MARKER_ICON = "files/red_dot.png"
    MARKER_SIZE = 16  # pixels

    def __init__(self, project_name: str = "PicPlotter Export"):
        """
        Initialize the KMZ generator.

        Args:
            project_name: Name for the KML document
        """
        self.project_name = project_name

    def create_kmz(
        self,
        photos: List[ProcessedPhoto],
        output_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        Create a KMZ file with embedded images.

        Args:
            photos: List of ProcessedPhoto objects
            output_path: Path for the output KMZ file
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            Path to the created KMZ file
        """
        # Ensure .kmz extension
        output_path = str(output_path)
        if not output_path.lower().endswith('.kmz'):
            output_path += '.kmz'

        # Generate KML content
        kml_content = self._generate_kml(photos)

        # Create KMZ (ZIP archive)
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as kmz:
            # Add the main KML file
            kmz.writestr('doc.kml', kml_content)

            # Add red dot marker icon (generated programmatically)
            red_dot_data = create_red_dot_icon(self.MARKER_SIZE)
            kmz.writestr('files/red_dot.png', red_dot_data)

            # Add images to files/ directory
            total = len(photos)
            for i, photo in enumerate(photos):
                image_path = f'files/{photo.filename}'
                kmz.writestr(image_path, photo.image_data)

                if progress_callback:
                    progress_callback(i + 1, total)

        return output_path

    def _add_styles(self, document: ET.Element) -> None:
        """Add KML style for placemarks with custom marker icon."""
        style = ET.SubElement(document, 'Style', id='photoStyle')

        # Icon style - small red dot (10% larger than original 0.25)
        icon_style = ET.SubElement(style, 'IconStyle')
        icon_scale = ET.SubElement(icon_style, 'scale')
        icon_scale.text = '0.2756'
        icon = ET.SubElement(icon_style, 'Icon')
        href = ET.SubElement(icon, 'href')
        href.text = self.MARKER_ICON

        # Label style - smaller text (10% smaller than default 1.0)
        label_style = ET.SubElement(style, 'LabelStyle')
        label_scale = ET.SubElement(label_style, 'scale')
        label_scale.text = '0.9025'

        # Balloon style - removes "Directions" and shows only our content
        balloon_style = ET.SubElement(style, 'BalloonStyle')
        balloon_text = ET.SubElement(balloon_style, 'text')
        balloon_text.text = '$[description]'

    def _create_placemark(self, photo: ProcessedPhoto, index: int) -> ET.Element:
        """
        Create a KML placemark element for a photo.

        Args:
            photo: ProcessedPhoto object
            index: Photo index for numbering

        Returns:
            Placemark Element
        """
        placemark = ET.Element('Placemark')

        # Name (just the index number for cleaner display)
        name = ET.SubElement(placemark, 'name')
        name.text = str(index)

        # Description - use unique placeholder that will be replaced later
        description = ET.SubElement(placemark, 'description')
        description.text = f'@@DESC_{index}@@'

        # Style reference (red balloon)
        style_url = ET.SubElement(placemark, 'styleUrl')
        style_url.text = '#photoStyle'

        # Coordinates
        point = ET.SubElement(placemark, 'Point')
        coordinates = ET.SubElement(point, 'coordinates')

        # KML format: longitude,latitude,altitude
        alt = photo.gps.altitude if photo.gps.altitude else 0
        coordinates.text = f'{photo.gps.longitude},{photo.gps.latitude},{alt}'

        # Timestamp if available
        if photo.timestamp:
            timestamp = ET.SubElement(placemark, 'TimeStamp')
            when = ET.SubElement(timestamp, 'when')
            when.text = photo.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')

        return placemark, photo.filename

    def _generate_kml(self, photos: List[ProcessedPhoto]) -> str:
        """
        Generate KML XML content.

        Args:
            photos: List of ProcessedPhoto objects

        Returns:
            KML content as string
        """
        # Sort photos chronologically by capture date
        sorted_photos = sorted(
            photos,
            key=lambda p: p.timestamp if p.timestamp else datetime.min
        )

        # Create root KML element
        kml = ET.Element('kml', xmlns=self.KML_NS)
        document = ET.SubElement(kml, 'Document')

        # Document name
        name = ET.SubElement(document, 'name')
        name.text = self.project_name

        # Description
        desc = ET.SubElement(document, 'description')
        desc.text = f'Created by PicPlotter - {len(sorted_photos)} photos'

        # Add styles for placemarks (numbered icons)
        self._add_styles(document)

        # Add folder for photos
        folder = ET.SubElement(document, 'Folder')
        folder_name = ET.SubElement(folder, 'name')
        folder_name.text = 'Photos'

        # Add placemarks for each photo (now sorted chronologically)
        # Store filename mappings for later replacement
        filename_map = {}
        for i, photo in enumerate(sorted_photos):
            placemark, filename = self._create_placemark(photo, i + 1)
            folder.append(placemark)
            filename_map[i + 1] = filename

        # Convert to string and replace placeholders with actual CDATA content
        return self._finalize_xml(kml, filename_map)

    def _finalize_xml(self, elem: ET.Element, filename_map: dict) -> str:
        """
        Finalize XML string with proper CDATA handling.

        Args:
            elem: ElementTree Element
            filename_map: Dict mapping index to filename

        Returns:
            XML string with CDATA sections
        """
        # Add XML declaration
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'

        # Get raw XML string
        xml_string = ET.tostring(elem, encoding='unicode')

        # Replace description placeholders with actual CDATA content
        for index, filename in filename_map.items():
            placeholder = f'@@DESC_{index}@@'
            cdata_content = f'<![CDATA[<img src="files/{filename}" style="max-width:800px;height:auto;"/>]]>'
            xml_string = xml_string.replace(placeholder, cdata_content)

        return xml_declaration + xml_string


def create_kmz_from_files(
    image_paths: List[str],
    output_path: str,
    project_name: str = "PicPlotter Export",
    compression_quality: int = 30,
    max_dimension: int = 1920,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    gps_overrides: Optional[dict] = None
) -> tuple:
    """
    High-level function to create KMZ from a list of image files.

    Args:
        image_paths: List of paths to image files
        output_path: Path for output KMZ file
        project_name: Name for the KML document
        compression_quality: JPEG quality (1-100)
        max_dimension: Maximum image dimension
        progress_callback: Optional callback(status, current, total)
        gps_overrides: Optional dict mapping file paths to GPSCoordinates

    Returns:
        Tuple of (output_path, num_processed, num_skipped, errors)
    """
    from .exif_extractor import get_image_metadata, is_supported_format
    from .image_processor import ImageProcessor

    processor = ImageProcessor(compression_quality, max_dimension)
    generator = KMZGenerator(project_name)

    photos = []
    errors = []
    skipped = 0

    total = len(image_paths)

    for i, path in enumerate(image_paths):
        if progress_callback:
            progress_callback(f"Processing {Path(path).name}...", i, total)

        try:
            # Check format support
            if not is_supported_format(path):
                errors.append(f"{path}: Unsupported format")
                skipped += 1
                continue

            # Extract metadata
            metadata = get_image_metadata(path)
            override_gps = gps_overrides.get(path) if gps_overrides else None
            gps = override_gps or metadata.gps

            # Skip if no GPS
            if not gps:
                errors.append(f"{path}: No GPS data")
                skipped += 1
                continue

            # Process image
            image_data, filename = processor.process_image(path)

            # Create ProcessedPhoto
            photo = ProcessedPhoto(
                original_path=path,
                filename=filename,
                image_data=image_data,
                gps=gps,
                timestamp=metadata.timestamp
            )
            photos.append(photo)

        except Exception as e:
            errors.append(f"{path}: {str(e)}")
            skipped += 1

    if not photos:
        raise ValueError("No photos with GPS data to process")

    # Generate KMZ
    if progress_callback:
        progress_callback("Creating KMZ file...", total, total)

    output = generator.create_kmz(photos, output_path)

    return output, len(photos), skipped, errors

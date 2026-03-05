"""
Utility functions for PicPlotter Auto
"""

from pathlib import Path
from typing import List
import os


def get_image_files_from_paths(paths: List[str]) -> List[str]:
    """
    Filter paths to only include supported image files.

    Args:
        paths: List of file paths

    Returns:
        List of valid image file paths
    """
    from .exif_extractor import get_supported_extensions

    supported = get_supported_extensions()
    valid_files = []

    for path in paths:
        p = Path(path)
        if p.is_file() and p.suffix in supported:
            valid_files.append(str(p))

    return valid_files


def get_unique_filename(directory: str, base_name: str, extension: str) -> str:
    """
    Generate a unique filename in a directory.

    Args:
        directory: Target directory
        base_name: Base filename (without extension)
        extension: File extension (with dot)

    Returns:
        Unique filepath
    """
    dir_path = Path(directory)
    filename = f"{base_name}{extension}"
    filepath = dir_path / filename

    counter = 1
    while filepath.exists():
        filename = f"{base_name}_{counter}{extension}"
        filepath = dir_path / filename
        counter += 1

    return str(filepath)


def format_file_size(size_bytes: int) -> str:
    """
    Format a file size in bytes to human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string like "1.5 MB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing invalid characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Characters not allowed in filenames on Windows
    invalid_chars = '<>:"/\\|?*'

    result = filename
    for char in invalid_chars:
        result = result.replace(char, '_')

    # Remove leading/trailing spaces and dots
    result = result.strip('. ')

    # Ensure we have something left
    if not result:
        result = 'unnamed'

    return result


def get_default_output_path(first_image_path: str = None) -> str:
    """
    Get a sensible default output path for KMZ file.

    Args:
        first_image_path: Optional path to first image (uses its directory)

    Returns:
        Default output path
    """
    if first_image_path:
        directory = Path(first_image_path).parent
    else:
        # Use user's Documents folder or home
        directory = Path.home() / "Documents"
        if not directory.exists():
            directory = Path.home()

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"PicPlotter_{timestamp}.kmz"

    return str(directory / filename)


def open_file_in_default_app(filepath: str) -> bool:
    """
    Open a file with the system's default application.

    Args:
        filepath: Path to the file

    Returns:
        True if successful, False otherwise
    """
    import subprocess
    import platform

    try:
        system = platform.system()

        if system == 'Windows':
            os.startfile(filepath)
        elif system == 'Darwin':  # macOS
            subprocess.run(['open', filepath], check=True)
        else:  # Linux
            subprocess.run(['xdg-open', filepath], check=True)

        return True
    except Exception:
        return False


def open_folder_containing(filepath: str) -> bool:
    """
    Open the folder containing a file in the system file manager.

    Args:
        filepath: Path to the file

    Returns:
        True if successful, False otherwise
    """
    import subprocess
    import platform

    try:
        directory = str(Path(filepath).parent)
        system = platform.system()

        if system == 'Windows':
            subprocess.run(['explorer', directory], check=True)
        elif system == 'Darwin':  # macOS
            subprocess.run(['open', directory], check=True)
        else:  # Linux
            subprocess.run(['xdg-open', directory], check=True)

        return True
    except Exception:
        return False

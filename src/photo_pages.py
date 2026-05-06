"""
Photo Pages for PicPlotter Auto.

Page mode groups photos into named deliverable pages. Each page owns its own
editor background and placement state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from src.coordinate_transform import PixelPoint
from src.exif_extractor import GPSCoordinates


DEFAULT_PAGE_ID = "page-1"
DEFAULT_PAGE_NAME = "Page 1"
MAP_SOURCE_TILES = "tiles"
MAP_SOURCE_CUSTOM = "custom"


@dataclass
class PageEditorState:
    """Editor state scoped to a single page."""

    map_source: str = MAP_SOURCE_TILES
    gps_overrides: Dict[str, GPSCoordinates] = field(default_factory=dict)
    custom_map_path: Optional[str] = None
    custom_marker_overrides: Dict[str, PixelPoint] = field(default_factory=dict)
    custom_autoplot_enabled: bool = True
    heading: int = 0
    custom_heading: int = 0
    tile_view: Dict[str, Any] = field(default_factory=dict)
    custom_view: Dict[str, Any] = field(default_factory=dict)

    def prune_to_photos(self, selected_files: List[str]) -> None:
        selected = set(selected_files)
        self.gps_overrides = {
            filepath: gps
            for filepath, gps in self.gps_overrides.items()
            if filepath in selected
        }
        self.custom_marker_overrides = {
            filepath: pixel
            for filepath, pixel in self.custom_marker_overrides.items()
            if filepath in selected
        }


@dataclass
class PhotoPage:
    """A named page and its assigned photos."""

    id: str
    name: str
    photo_paths: List[str] = field(default_factory=list)
    editor_state: PageEditorState = field(default_factory=PageEditorState)
    locked: bool = False

    @classmethod
    def create_default(cls) -> "PhotoPage":
        return cls(id=DEFAULT_PAGE_ID, name=DEFAULT_PAGE_NAME, locked=True)

    @classmethod
    def create_new(cls, name: str) -> "PhotoPage":
        return cls(id=f"page-{uuid.uuid4().hex[:8]}", name=name)


@dataclass
class PageAssignments:
    """Manage all pages and photo-to-page assignments."""

    pages: Dict[str, PhotoPage] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if DEFAULT_PAGE_ID not in self.pages:
            self.pages = {DEFAULT_PAGE_ID: PhotoPage.create_default(), **self.pages}
        self.pages[DEFAULT_PAGE_ID].locked = True
        if not self.pages[DEFAULT_PAGE_ID].name:
            self.pages[DEFAULT_PAGE_ID].name = DEFAULT_PAGE_NAME

    def get_page(self, page_id: str) -> Optional[PhotoPage]:
        return self.pages.get(page_id)

    def get_page_for_photo(self, filepath: str) -> Optional[PhotoPage]:
        for page in self.pages.values():
            if filepath in page.photo_paths:
                return page
        return None

    def assign_photo(self, filepath: str, page_id: str) -> bool:
        if page_id not in self.pages:
            return False
        self.unassign_photo(filepath)
        if filepath not in self.pages[page_id].photo_paths:
            self.pages[page_id].photo_paths.append(filepath)
        return True

    def unassign_photo(self, filepath: str) -> None:
        for page in self.pages.values():
            if filepath in page.photo_paths:
                page.photo_paths.remove(filepath)
                break

    def unassigned_photos(self, all_photos: List[str]) -> List[str]:
        assigned = set()
        for page in self.pages.values():
            assigned.update(page.photo_paths)
        return [path for path in all_photos if path not in assigned]

    def add_page(self, name: str = "") -> PhotoPage:
        display_name = name.strip() if isinstance(name, str) else ""
        if not display_name:
            display_name = f"Page {len(self.pages) + 1}"
        page = PhotoPage.create_new(display_name)
        self.pages[page.id] = page
        return page

    def remove_page(self, page_id: str) -> bool:
        if page_id == DEFAULT_PAGE_ID:
            return False
        page = self.pages.get(page_id)
        if not page:
            return False
        default_page = self.pages[DEFAULT_PAGE_ID]
        for filepath in page.photo_paths:
            if filepath not in default_page.photo_paths:
                default_page.photo_paths.append(filepath)
        del self.pages[page_id]
        return True

    def rename_page(self, page_id: str, new_name: str) -> bool:
        page = self.pages.get(page_id)
        if not page:
            return False
        cleaned = new_name.strip() if isinstance(new_name, str) else ""
        if not cleaned:
            return False
        page.name = cleaned
        return True

    def get_all_pages(self) -> List[PhotoPage]:
        ordered: List[PhotoPage] = []
        default_page = self.pages.get(DEFAULT_PAGE_ID)
        if default_page:
            ordered.append(default_page)
        ordered.extend(
            page for page_id, page in self.pages.items() if page_id != DEFAULT_PAGE_ID
        )
        return ordered

    def auto_assign_unassigned(self, all_photos: List[str]) -> None:
        for filepath in self.unassigned_photos(all_photos):
            self.assign_photo(filepath, DEFAULT_PAGE_ID)

    def prune_to_photos(self, selected_files: List[str]) -> None:
        selected = set(selected_files)
        for page in self.pages.values():
            page.photo_paths = [path for path in page.photo_paths if path in selected]
            page.editor_state.prune_to_photos(selected_files)

    def clear_all(self) -> None:
        self.pages = {DEFAULT_PAGE_ID: PhotoPage.create_default()}

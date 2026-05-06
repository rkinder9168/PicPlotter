"""
Photo Pages for PicPlotter Auto.

Sibling concept to PhotoGroup: a page is a named, ordered grouping of photos
that produces its own section in the multi-page HTML deliverable. Unlike
groups, pages have no color or marker tinting (markers always use the plain
logo) and pages own their own map view (per-page satellite framing or per-page
custom-image background).

Pages can hold both GPS and non-GPS photos:
  - A page with a custom_map_path is in custom mode — markers placed manually
    via marker_overrides; autoplot can run for any GPS photos when enabled.
  - A page without custom_map_path is in tiles mode — GPS photos auto-plot from
    the saved view; non-GPS photos are skipped at export with a warning.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import uuid

from src.coordinate_transform import PixelPoint


@dataclass
class PageView:
    """Saved map view for a page. Tile and custom fields coexist."""

    # Tile mode
    lat: Optional[float] = None
    lng: Optional[float] = None
    zoom: Optional[float] = None
    heading: Optional[float] = None
    # Custom mode
    custom_center_x: Optional[float] = None
    custom_center_y: Optional[float] = None
    custom_zoom: Optional[float] = None
    custom_heading: Optional[float] = None

    def to_dict(self) -> Dict[str, Optional[float]]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "zoom": self.zoom,
            "heading": self.heading,
            "custom_center_x": self.custom_center_x,
            "custom_center_y": self.custom_center_y,
            "custom_zoom": self.custom_zoom,
            "custom_heading": self.custom_heading,
        }

    @classmethod
    def from_dict(cls, raw: Optional[Dict]) -> "PageView":
        view = cls()
        if not isinstance(raw, dict):
            return view
        for attr in (
            "lat", "lng", "zoom", "heading",
            "custom_center_x", "custom_center_y",
            "custom_zoom", "custom_heading",
        ):
            value = raw.get(attr)
            if value is None:
                continue
            try:
                setattr(view, attr, float(value))
            except (TypeError, ValueError):
                pass
        return view


@dataclass
class PhotoPage:
    """Represents a named page of photos with its own map view."""

    id: str
    name: str
    photo_paths: List[str] = field(default_factory=list)
    view: PageView = field(default_factory=PageView)
    custom_map_path: Optional[str] = None
    marker_overrides: Dict[str, PixelPoint] = field(default_factory=dict)
    autoplot_enabled: bool = True

    @classmethod
    def create_new(cls, name: str) -> "PhotoPage":
        return cls(
            id=f"page-{uuid.uuid4().hex[:8]}",
            name=name,
        )

    def has_custom_map(self) -> bool:
        return bool(self.custom_map_path)


@dataclass
class PageAssignments:
    """Manages all photo pages and their photo assignments."""

    pages: Dict[str, PhotoPage] = field(default_factory=dict)
    _order: List[str] = field(default_factory=list)

    def get_page(self, page_id: str) -> Optional[PhotoPage]:
        return self.pages.get(page_id)

    def get_page_for_photo(self, filepath: str) -> Optional[PhotoPage]:
        for page_id in self._order:
            page = self.pages.get(page_id)
            if page and filepath in page.photo_paths:
                return page
        return None

    def assign_photo(self, filepath: str, page_id: Optional[str]) -> bool:
        """Move photo to page_id (or unassign if page_id is None/empty)."""
        self.unassign_photo(filepath)
        if not page_id:
            return True
        if page_id not in self.pages:
            return False
        self.pages[page_id].photo_paths.append(filepath)
        return True

    def unassign_photo(self, filepath: str) -> None:
        for page in self.pages.values():
            if filepath in page.photo_paths:
                page.photo_paths.remove(filepath)

    def unassigned_photos(self, all_photos: List[str]) -> List[str]:
        assigned = set()
        for page in self.pages.values():
            assigned.update(page.photo_paths)
        return [p for p in all_photos if p not in assigned]

    def add_page(self, name: str) -> PhotoPage:
        cleaned = (name or "").strip()
        if not cleaned:
            cleaned = f"Page {len(self._order) + 1}"
        page = PhotoPage.create_new(cleaned)
        self.pages[page.id] = page
        self._order.append(page.id)
        return page

    def insert_page(self, page: PhotoPage) -> None:
        """Insert a fully-formed page (used during deserialization)."""
        if page.id in self.pages:
            return
        self.pages[page.id] = page
        self._order.append(page.id)

    def remove_page(self, page_id: str) -> bool:
        if page_id not in self.pages:
            return False
        del self.pages[page_id]
        if page_id in self._order:
            self._order.remove(page_id)
        return True

    def rename_page(self, page_id: str, new_name: str) -> bool:
        page = self.pages.get(page_id)
        if not page:
            return False
        cleaned = (new_name or "").strip()
        if not cleaned:
            return False
        page.name = cleaned
        return True

    def get_all_pages(self) -> List[PhotoPage]:
        """Insertion-ordered list of pages."""
        return [self.pages[pid] for pid in self._order if pid in self.pages]

    def update_view(self, page_id: str, view: PageView) -> bool:
        page = self.pages.get(page_id)
        if not page:
            return False
        page.view = view
        return True

    def set_custom_map(self, page_id: str, path: Optional[str]) -> bool:
        page = self.pages.get(page_id)
        if not page:
            return False
        cleaned = (path or "").strip() if isinstance(path, str) else None
        page.custom_map_path = cleaned if cleaned else None
        return True

    def set_marker_override(self, page_id: str, filepath: str, point: Optional[PixelPoint]) -> bool:
        page = self.pages.get(page_id)
        if not page or not filepath:
            return False
        if point is None:
            page.marker_overrides.pop(filepath, None)
        else:
            page.marker_overrides[filepath] = point
        return True

    def clear_marker_overrides(self, page_id: str, filepath: Optional[str] = None) -> bool:
        page = self.pages.get(page_id)
        if not page:
            return False
        if filepath:
            page.marker_overrides.pop(filepath, None)
        else:
            page.marker_overrides.clear()
        return True

    def set_autoplot_enabled(self, page_id: str, enabled: bool) -> bool:
        page = self.pages.get(page_id)
        if not page:
            return False
        page.autoplot_enabled = bool(enabled)
        return True

    def has_pages(self) -> bool:
        return bool(self.pages)

    def clear_all(self) -> None:
        self.pages.clear()
        self._order.clear()

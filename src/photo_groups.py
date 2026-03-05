"""
Photo Groups for PicPlotter Auto.

Data structures for managing photo groups with colored markers.
Each group has a name, color, and list of assigned photo paths.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import uuid


# Preset colors for groups
# "default" is special - uses original multi-colored marker
PRESET_COLORS = [
    {"id": "default", "name": "Default", "hex": "default"},
    {"id": "yellow", "name": "Yellow", "hex": "#F6D11A"},
    {"id": "green", "name": "Green", "hex": "#2A9D6E"},
    {"id": "red", "name": "Red", "hex": "#E53935"},
    {"id": "blue", "name": "Blue", "hex": "#1E88E5"},
    {"id": "purple", "name": "Purple", "hex": "#8E24AA"},
    {"id": "orange", "name": "Orange", "hex": "#FB8C00"},
    {"id": "brown", "name": "Brown", "hex": "#795548"},
    {"id": "gray", "name": "Gray", "hex": "#757575"},
]

# Default groups that are always pre-loaded
DEFAULT_GROUPS = [
    {"id": "default", "name": "Default", "color": "default"},
    {"id": "yellow", "name": "Yellow", "color": "#F6D11A"},
    {"id": "green", "name": "Green", "color": "#2A9D6E"},
    {"id": "red", "name": "Red", "color": "#E53935"},
    {"id": "blue", "name": "Blue", "color": "#1E88E5"},
    {"id": "purple", "name": "Purple", "color": "#8E24AA"},
    {"id": "orange", "name": "Orange", "color": "#FB8C00"},
    {"id": "brown", "name": "Brown", "color": "#795548"},
    {"id": "gray", "name": "Gray", "color": "#757575"},
]


@dataclass
class PhotoGroup:
    """Represents a group of photos with a specific marker color."""

    id: str
    name: str
    color: str  # Hex color like "#2A9D6E" or "default" for original marker
    photo_paths: List[str] = field(default_factory=list)

    @classmethod
    def create_default(cls) -> "PhotoGroup":
        """Create the default group (original multi-colored marker)."""
        return cls(
            id="default",
            name="Default",
            color="default",
        )

    @classmethod
    def create_new(cls, name: str, color: str) -> "PhotoGroup":
        """Create a new group with a unique ID."""
        return cls(
            id=f"group-{uuid.uuid4().hex[:8]}",
            name=name,
            color=color,
        )


@dataclass
class GroupAssignments:
    """
    Manages all photo groups and their assignments.

    Maintains a dictionary of groups and provides methods to
    assign/unassign photos, get group for a photo, etc.
    """

    groups: Dict[str, PhotoGroup] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize with default groups."""
        if not self.groups:
            for group_def in DEFAULT_GROUPS:
                self.groups[group_def["id"]] = PhotoGroup(
                    id=group_def["id"],
                    name=group_def["name"],
                    color=group_def["color"],
                )

    def get_group(self, group_id: str) -> Optional[PhotoGroup]:
        """Get a group by ID."""
        return self.groups.get(group_id)

    def get_group_for_photo(self, filepath: str) -> Optional[PhotoGroup]:
        """Get the group that contains the given photo."""
        for group in self.groups.values():
            if filepath in group.photo_paths:
                return group
        return None

    def assign_photo(self, filepath: str, group_id: str) -> bool:
        """
        Assign a photo to a group.

        Removes from any existing group first.
        Returns True if successful, False if group doesn't exist.
        """
        if group_id not in self.groups:
            return False

        self.unassign_photo(filepath)
        self.groups[group_id].photo_paths.append(filepath)
        return True

    def unassign_photo(self, filepath: str) -> None:
        """Remove a photo from whatever group it's in."""
        for group in self.groups.values():
            if filepath in group.photo_paths:
                group.photo_paths.remove(filepath)
                break

    def unassigned_photos(self, all_photos: List[str]) -> List[str]:
        """Get list of photos not assigned to any group."""
        assigned = set()
        for group in self.groups.values():
            assigned.update(group.photo_paths)
        return [p for p in all_photos if p not in assigned]

    def add_group(self, name: str, color: str) -> PhotoGroup:
        """Create and add a new group."""
        group = PhotoGroup.create_new(name, color)
        self.groups[group.id] = group
        return group

    def remove_group(self, group_id: str) -> bool:
        """
        Remove a group.

        Cannot remove the default group.
        Photos in the removed group become unassigned.
        """
        if group_id == "default":
            return False

        if group_id in self.groups:
            del self.groups[group_id]
            return True
        return False

    def rename_group(self, group_id: str, new_name: str) -> bool:
        """Rename a group."""
        if group_id in self.groups:
            self.groups[group_id].name = new_name
            return True
        return False

    def change_group_color(self, group_id: str, new_color: str) -> bool:
        """Change a group's color."""
        if group_id in self.groups:
            self.groups[group_id].color = new_color
            return True
        return False

    def get_all_groups(self) -> List[PhotoGroup]:
        """Get all groups, with default groups first in order."""
        groups = list(self.groups.values())
        default_order = {
            "default": 0,
            "yellow": 1,
            "green": 2,
            "red": 3,
            "blue": 4,
            "purple": 5,
            "orange": 6,
            "brown": 7,
            "gray": 8,
        }
        return sorted(groups, key=lambda g: (default_order.get(g.id, 99), g.name.lower()))

    def auto_assign_unassigned(self, all_photos: List[str]) -> None:
        """Assign any unassigned photos to the default group."""
        unassigned = self.unassigned_photos(all_photos)
        for filepath in unassigned:
            self.assign_photo(filepath, "default")

    def clear_all(self) -> None:
        """Clear all groups and photo assignments, reset to default groups."""
        self.groups = {}
        for group_def in DEFAULT_GROUPS:
            self.groups[group_def["id"]] = PhotoGroup(
                id=group_def["id"],
                name=group_def["name"],
                color=group_def["color"],
            )

    def has_multiple_groups(self) -> bool:
        """Check if there are multiple groups with photos."""
        groups_with_photos = [g for g in self.groups.values() if g.photo_paths]
        return len(groups_with_photos) > 1

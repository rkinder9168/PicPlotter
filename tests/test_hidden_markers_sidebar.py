import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

from PIL import Image

if "webview" not in sys.modules:
    sys.modules["webview"] = types.SimpleNamespace(
        FileDialog=types.SimpleNamespace(OPEN="open", SAVE="save", FOLDER="folder")
    )

from src.coordinate_transform import PixelPoint
from src.html_map_generator import HTMLMapGenerator
from src.main import AppState, _apply_overrides, _load_overrides, _serialize_overrides_state
from src.photo_groups import GroupAssignments
from src.photo_pages import PageAssignments


def png_bytes(color):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpg_bytes(color):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def make_state(tmpdir):
    return AppState(
        selected_files=[],
        file_metadata={},
        gps_overrides={},
        custom_map_path=None,
        custom_marker_overrides={},
        custom_autoplot_enabled=True,
        marker_size=96,
        heading=0,
        custom_heading=0,
        output_folder=None,
        overrides_path=Path(tmpdir) / "map_overrides.json",
        group_assignments=GroupAssignments(),
        page_assignments=PageAssignments(),
        assignment_mode="group",
        photo_aliases={},
        group_aliases={},
        photo_notes={},
        photo_previews={},
        drive_sources={},
        drive_folder_url=None,
        drive_access_token=None,
    )


def single_html(**kwargs):
    gen = HTMLMapGenerator(project_name="T", marker_size=80, **kwargs)
    return gen.generate_single_html(
        photos=[{"filepath": "/p/a.jpg", "filename": "a.jpg",
                 "display_name": "A", "image_data": jpg_bytes((255, 0, 0))}],
        aerial_image_path=None,
        transform=None,
        marker_pixels=[PixelPoint(2, 3)],
        aerial_image_bytes=png_bytes((255, 255, 255)),
        aerial_image_mime="image/png",
        aerial_image_size=(8, 8),
        return_content=True,
    )


def make_page(idx):
    return {"id": f"page-{idx}", "name": f"Page {idx}",
            "aerial_image_bytes": png_bytes((255, 255, 255)),
            "aerial_image_mime": "image/png", "aerial_image_size": (8, 8),
            "photos": [{"filepath": f"/p/{idx}.jpg", "filename": f"{idx}.jpg",
                        "display_name": f"P{idx}", "image_data": jpg_bytes((255, 0, 0))}],
            "marker_pixels": [PixelPoint(2, 3)]}


def multi_html(n_pages=1, **kwargs):
    gen = HTMLMapGenerator(project_name="MP", marker_size=64, **kwargs)
    return gen.generate_multi_page_html(
        [make_page(i + 1) for i in range(n_pages)],
        return_content=True,
    )


class HiddenMarkersSidebarGeneratorTests(unittest.TestCase):
    def test_single_page_default_has_no_display_classes(self):
        html = single_html()
        self.assertIn('<body class="">', html)

    def test_single_page_hide_markers_and_sidebar(self):
        html = single_html(hide_markers=True, hide_sidebar=True)
        self.assertIn('<body class="markers-hidden no-sidebar">', html)
        self.assertIn("body.markers-hidden .marker", html)
        self.assertIn("body.markers-hidden .marker-number", html)
        self.assertIn("body.no-sidebar #layout", html)
        # Markers stay clickable: the click handler over .marker is still present.
        self.assertIn("document.querySelectorAll('.marker')", html)

    def test_single_page_hide_markers_only(self):
        html = single_html(hide_markers=True)
        self.assertIn('<body class="markers-hidden">', html)
        self.assertNotIn("no-sidebar\"", html.split("<body", 1)[1][:40])

    def test_multi_page_single_page_honors_hide_sidebar(self):
        # One page -> nothing to navigate, so the sidebar may be hidden.
        html = multi_html(n_pages=1, hide_markers=True, hide_sidebar=True)
        self.assertIn('<body class="markers-hidden no-sidebar">', html)
        self.assertIn("body.no-sidebar #layout", html)
        self.assertIn("body.markers-hidden .marker", html)

    def test_multi_page_multiple_pages_ignore_hide_sidebar(self):
        # Two+ pages -> sidebar holds the page nav, so hide_sidebar is ignored.
        html = multi_html(n_pages=2, hide_markers=True, hide_sidebar=True)
        self.assertIn('<body class="markers-hidden">', html)
        self.assertIn("body.markers-hidden .marker", html)


class HiddenMarkersSidebarPersistenceTests(unittest.TestCase):
    def test_apply_and_serialize_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = make_state(tmpdir)
            self.assertFalse(state.hide_markers)
            self.assertFalse(state.hide_sidebar)

            _apply_overrides(state, {"hide_markers": True, "hide_sidebar": True})
            self.assertTrue(state.hide_markers)
            self.assertTrue(state.hide_sidebar)

            payload = _serialize_overrides_state(state)
            self.assertEqual(payload["hide_markers"], True)
            self.assertEqual(payload["hide_sidebar"], True)

            # Persisted to disk by _apply_overrides; reload should restore the flags.
            loaded = _load_overrides(state.overrides_path)
            self.assertEqual(loaded[-2], True)   # hide_markers
            self.assertEqual(loaded[-1], True)   # hide_sidebar

    def test_load_overrides_defaults_to_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map_overrides.json"
            path.write_text(json.dumps({"marker_size": 80}), encoding="utf-8")
            loaded = _load_overrides(path)
            self.assertEqual(loaded[-2], False)  # hide_markers
            self.assertEqual(loaded[-1], False)  # hide_sidebar


if __name__ == "__main__":
    unittest.main()

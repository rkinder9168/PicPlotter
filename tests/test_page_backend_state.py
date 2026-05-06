import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

if "webview" not in sys.modules:
    sys.modules["webview"] = types.SimpleNamespace(
        FileDialog=types.SimpleNamespace(OPEN="open", SAVE="save", FOLDER="folder")
    )

from src.exif_extractor import ImageMetadata
from PIL import Image

from src.main import AppApi, AppState, _build_multi_page_export_pages, _load_overrides
from src.photo_groups import GroupAssignments
from src.photo_pages import DEFAULT_PAGE_ID, PageAssignments


def make_metadata(filepath):
    return ImageMetadata(
        filepath=Path(filepath),
        filename=Path(filepath).name,
        gps=None,
        timestamp=None,
        camera_make=None,
        camera_model=None,
    )


def make_state(tmpdir):
    files = ["/photos/a.jpg", "/photos/b.jpg"]
    return AppState(
        selected_files=files[:],
        file_metadata={filepath: make_metadata(filepath) for filepath in files},
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


class PageBackendStateTests(unittest.TestCase):
    def test_page_assignment_api_updates_assignment_state_and_photo_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            api = AppApi(make_state(tmpdir))

            mode_result = api.set_assignment_mode("page")
            add_result = api.add_page("Interior")
            page_id = add_result["pages"][1]["id"]
            assign_result = api.assign_photo_page(["/photos/b.jpg"], page_id)
            state_result = api.get_assignment_state()
            photo_result = api.get_photo_list()

        self.assertEqual(mode_result["assignment_mode"], "page")
        self.assertEqual(assign_result["status"], "ok")
        self.assertEqual(state_result["assignment_mode"], "page")
        self.assertEqual(state_result["pages"][0]["id"], DEFAULT_PAGE_ID)
        self.assertEqual(state_result["pages"][1]["name"], "Interior")
        photo_b = next(photo for photo in photo_result["photos"] if photo["filepath"] == "/photos/b.jpg")
        self.assertEqual(photo_b["page_id"], page_id)
        self.assertEqual(photo_b["page_name"], "Interior")

    def test_load_overrides_defaults_legacy_files_to_group_mode_with_page_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map_overrides.json"
            path.write_text(json.dumps({"marker_size": 88}), encoding="utf-8")

            loaded = _load_overrides(path)

        self.assertEqual(loaded[-2], "group")
        self.assertEqual(loaded[-1].get_page(DEFAULT_PAGE_ID).name, "Page 1")

    def test_load_overrides_reads_page_assignments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "map_overrides.json"
            path.write_text(
                json.dumps(
                    {
                        "assignment_mode": "page",
                        "pages": [
                            {"id": DEFAULT_PAGE_ID, "name": "Page 1"},
                            {"id": "page-custom", "name": "Interior"},
                        ],
                        "page_assignments": {
                            "/photos/a.jpg": "page-custom",
                            "/photos/b.jpg": DEFAULT_PAGE_ID,
                        },
                    }
                ),
                encoding="utf-8",
            )

            loaded = _load_overrides(path)
            page_assignments = loaded[-1]

        self.assertEqual(loaded[-2], "page")
        self.assertEqual(page_assignments.get_page("page-custom").name, "Interior")
        self.assertEqual(page_assignments.get_page_for_photo("/photos/a.jpg").id, "page-custom")

    def test_build_multi_page_export_pages_processes_custom_page_offline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            background = Path(tmpdir) / "background.png"
            photo = Path(tmpdir) / "photo.jpg"
            Image.new("RGB", (24, 16), (240, 240, 240)).save(background)
            Image.new("RGB", (12, 10), (200, 10, 10)).save(photo)

            state = make_state(tmpdir)
            state.selected_files = [str(photo)]
            state.file_metadata = {str(photo): make_metadata(str(photo))}

            pages = _build_multi_page_export_pages(
                state,
                {
                    "assignment_mode": "page",
                    "marker_size": 64,
                    "compression_quality": 80,
                    "pages": [
                        {
                            "id": DEFAULT_PAGE_ID,
                            "name": "Page 1",
                            "map_source": "custom",
                            "custom_image_path": str(background),
                            "custom_markers": [
                                {"filepath": str(photo), "x": 5, "y": 6}
                            ],
                        }
                    ],
                },
                use_drive_urls=False,
            )

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["name"], "Page 1")
        self.assertEqual(len(pages[0]["photos"]), 1)
        self.assertEqual(pages[0]["marker_pixels"][0].x, 5)


if __name__ == "__main__":
    unittest.main()

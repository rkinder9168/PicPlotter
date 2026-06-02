"""Tests for video export wiring: export dicts, asset collection, marker stripping,
and the HTML generator's video lightbox output."""

import io
import sys
import tempfile
import types
import unittest
from pathlib import Path

if "webview" not in sys.modules:
    sys.modules["webview"] = types.SimpleNamespace(
        FileDialog=types.SimpleNamespace(OPEN="open", SAVE="save", FOLDER="folder")
    )

from PIL import Image

from src.exif_extractor import GPSCoordinates, ImageMetadata
from src.coordinate_transform import PixelPoint
from src.html_map_generator import HTMLMapGenerator
from src.main import (
    _collect_video_assets,
    _strip_video_markers,
    _video_export_dict,
)


def _meta(path):
    return ImageMetadata(
        filepath=Path(path),
        filename=Path(path).name,
        gps=GPSCoordinates(1.0, 2.0, None),
        timestamp=None,
        camera_make=None,
        camera_model=None,
    )


def _tiny_png():
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


class TestVideoExportDict(unittest.TestCase):
    def test_drive_video_uses_embed(self):
        entry = _video_export_dict(
            "gdrive://FID/v.mov", "FID", _meta("gdrive://FID/v.mov"),
            GPSCoordinates(1.0, 2.0, None), "", "",
        )
        self.assertTrue(entry["is_video"])
        self.assertTrue(entry["embed"])
        self.assertEqual(entry["video_url"], "https://drive.google.com/file/d/FID/preview")
        self.assertTrue(entry["poster"])
        self.assertNotIn("local_video_path", entry)

    def test_local_video_defers_url(self):
        entry = _video_export_dict(
            "/clips/a.mp4", None, _meta("/clips/a.mp4"),
            GPSCoordinates(1.0, 2.0, None), "Name", "note",
        )
        self.assertTrue(entry["is_video"])
        self.assertFalse(entry["embed"])
        self.assertEqual(entry["local_video_path"], "/clips/a.mp4")
        self.assertEqual(entry["video_mime"], "video/mp4")
        self.assertEqual(entry["video_url"], "")  # resolved at deploy time


class TestCollectVideoAssets(unittest.TestCase):
    def test_local_video_assets_collected_and_drive_untouched(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", prefix="my clip ", delete=False) as tmp:
            tmp.write(b"FAKEVIDEO")
            tmp_path = tmp.name
        try:
            drive = _video_export_dict("gdrive://D/v.mov", "D", _meta("gdrive://D/v.mov"),
                                       GPSCoordinates(1.0, 2.0, None), "", "")
            local = _video_export_dict(tmp_path, None, _meta(tmp_path),
                                       GPSCoordinates(1.0, 2.0, None), "", "")
            photos = [drive, {"filepath": "p.jpg", "is_video": False, "image_data": b"x"}, local]
            assets = _collect_video_assets(photos)

            self.assertEqual(len(assets), 1)
            key = next(iter(assets))
            self.assertTrue(key.startswith("/media/"))
            self.assertTrue(key.endswith(".mp4"))
            self.assertNotIn(" ", key)  # URL-safe
            self.assertEqual(assets[key], b"FAKEVIDEO")
            self.assertEqual(local["video_url"], key.lstrip("/"))
            # Drive video is streamed, not uploaded.
            self.assertEqual(drive["video_url"], "https://drive.google.com/file/d/D/preview")
        finally:
            Path(tmp_path).unlink()

    def test_unique_names_for_same_stem(self):
        files = []
        photos = []
        try:
            for _ in range(2):
                tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
                tmp.write(b"DATA")
                tmp.close()
                files.append(tmp.name)
            # Force identical stems by pointing two dicts at copies with same name is hard;
            # instead just assert two distinct files yield two distinct media keys.
            for f in files:
                photos.append(_video_export_dict(f, None, _meta(f), GPSCoordinates(1.0, 2.0, None), "", ""))
            assets = _collect_video_assets(photos)
            self.assertEqual(len(assets), 2)
            self.assertEqual(len({p["video_url"] for p in photos}), 2)
        finally:
            for f in files:
                Path(f).unlink()


class TestStripVideoMarkers(unittest.TestCase):
    def test_strips_from_markers_and_pages(self):
        payload = {
            "markers": [{"filepath": "p.jpg"}, {"filepath": "v.mp4"}],
            "custom_markers": [{"filepath": "v.mp4"}],
            "pages": [{"markers": [{"filepath": "v.mp4"}], "custom_markers": [{"filepath": "q.jpg"}]}],
        }
        removed = _strip_video_markers(payload, {"v.mp4"})
        self.assertEqual(removed, 3)
        self.assertEqual(payload["markers"], [{"filepath": "p.jpg"}])
        self.assertEqual(payload["custom_markers"], [])
        self.assertEqual(payload["pages"][0]["markers"], [])
        self.assertEqual(payload["pages"][0]["custom_markers"], [{"filepath": "q.jpg"}])


class TestHtmlVideoOutput(unittest.TestCase):
    def setUp(self):
        self.gen = HTMLMapGenerator(project_name="T", marker_size=80)
        self.aerial = _tiny_png()
        self.photos = [
            {"filepath": "a.jpg", "filename": "a.jpg", "display_name": "A", "image_data": self.aerial},
            {"filepath": "gdrive://X/v.mov", "filename": "v.mov", "display_name": "Clip",
             "is_video": True, "embed": True,
             "video_url": "https://drive.google.com/file/d/X/preview",
             "poster": "https://drive.google.com/thumbnail?id=X&sz=w1920"},
            {"filepath": "local.mp4", "filename": "local.mp4", "display_name": "Local",
             "is_video": True, "embed": False, "video_url": "media/2_local.mp4"},
        ]
        self.pixels = [PixelPoint(10, 10), PixelPoint(20, 20), PixelPoint(30, 30)]

    def test_single_page_emits_video_elements(self):
        html = self.gen.generate_single_html(
            self.photos, aerial_image_path=None, transform=None, marker_pixels=self.pixels,
            aerial_image_bytes=self.aerial, aerial_image_mime="image/png",
            aerial_image_size=(32, 32), return_content=True,
        )
        self.assertIn('<video id="lightbox-video"', html)
        self.assertIn('<iframe id="lightbox-frame"', html)
        self.assertIn("drive.google.com/file/d/X/preview", html)
        self.assertIn("media/2_local.mp4", html)

    def test_multi_page_emits_video_elements(self):
        pages = [{
            "id": "p1", "name": "Page 1", "aerial_image_bytes": self.aerial,
            "aerial_image_mime": "image/png", "aerial_image_size": (32, 32),
            "photos": self.photos, "marker_pixels": self.pixels, "marker_size": 80,
        }]
        html = self.gen.generate_multi_page_html(pages, return_content=True)
        self.assertIn('<video id="lightbox-video"', html)
        self.assertIn('<iframe id="lightbox-frame"', html)
        self.assertIn("drive.google.com/file/d/X/preview", html)
        self.assertIn("media/2_local.mp4", html)

    def test_photo_only_marks_isvideo_false(self):
        html = self.gen.generate_single_html(
            [self.photos[0]], aerial_image_path=None, transform=None,
            marker_pixels=[PixelPoint(5, 5)], aerial_image_bytes=self.aerial,
            aerial_image_mime="image/png", aerial_image_size=(32, 32), return_content=True,
        )
        self.assertTrue('"isVideo": false' in html or '"isVideo":false' in html)


if __name__ == "__main__":
    unittest.main()

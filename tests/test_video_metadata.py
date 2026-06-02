"""Tests for src/video_metadata.py — media classification + MP4/MOV GPS parsing."""

import struct
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.video_metadata import (
    extract_video_gps,
    extract_video_metadata,
    get_supported_media_extensions,
    is_supported_media,
    is_video_format,
    parse_iso6709,
    video_mime_for,
)


def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + box_type + payload


def _xyz_box(iso6709: bytes) -> bytes:
    # ©xyz payload: uint16 string length, uint16 language code, then the string.
    payload = struct.pack(">H", len(iso6709)) + struct.pack(">H", 0x15C7) + iso6709
    return _box(b"\xa9xyz", payload)


def _mvhd_box(when: datetime) -> bytes:
    secs = int((when - datetime(1904, 1, 1)).total_seconds())
    payload = bytes(4) + struct.pack(">I", secs) * 2 + struct.pack(">I", 600) + struct.pack(">I", 6000) + bytes(60)
    return _box(b"mvhd", payload)


def _build_mp4(iso6709: bytes, when: datetime | None = None, moov_at_end: bool = True) -> bytes:
    udta = _box(b"udta", _xyz_box(iso6709))
    moov_payload = udta if when is None else _mvhd_box(when) + udta
    moov = _box(b"moov", moov_payload)
    ftyp = _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
    mdat = _box(b"mdat", bytes(400))  # big media box the walker must skip
    return (ftyp + mdat + moov) if moov_at_end else (ftyp + moov + mdat)


class TestMediaClassification(unittest.TestCase):
    def test_is_video_format(self):
        self.assertTrue(is_video_format("clip.mp4"))
        self.assertTrue(is_video_format("CLIP.MOV"))
        self.assertTrue(is_video_format("a.webm"))
        self.assertFalse(is_video_format("photo.jpg"))
        self.assertFalse(is_video_format("photo.heic"))

    def test_is_supported_media(self):
        self.assertTrue(is_supported_media("photo.jpg"))
        self.assertTrue(is_supported_media("clip.mp4"))
        self.assertFalse(is_supported_media("notes.txt"))

    def test_supported_media_extensions_include_both(self):
        exts = [e.lower() for e in get_supported_media_extensions()]
        self.assertIn(".jpg", exts)
        self.assertIn(".mp4", exts)
        self.assertIn(".mov", exts)

    def test_video_mime_for(self):
        self.assertEqual(video_mime_for("a.mp4"), "video/mp4")
        self.assertEqual(video_mime_for("a.mov"), "video/quicktime")
        self.assertEqual(video_mime_for("a.webm"), "video/webm")
        self.assertEqual(video_mime_for("a.unknown"), "video/mp4")


class TestIso6709(unittest.TestCase):
    def test_lat_lon_alt(self):
        coords = parse_iso6709("+37.7866-122.4097+010.000/")
        self.assertAlmostEqual(coords.latitude, 37.7866, places=4)
        self.assertAlmostEqual(coords.longitude, -122.4097, places=4)
        self.assertAlmostEqual(coords.altitude, 10.0, places=3)

    def test_no_altitude(self):
        coords = parse_iso6709("-33.8688+151.2093/")
        self.assertAlmostEqual(coords.latitude, -33.8688, places=4)
        self.assertAlmostEqual(coords.longitude, 151.2093, places=4)
        self.assertIsNone(coords.altitude)

    def test_zero_zero_rejected(self):
        self.assertIsNone(parse_iso6709("+00.0000+000.0000/"))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_iso6709("not a location"))


class TestVideoGps(unittest.TestCase):
    def test_extract_from_xyz_box(self):
        data = _build_mp4(b"+40.7128-074.0060+005.000/")
        coords = extract_video_gps(data)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords.latitude, 40.7128, places=4)
        self.assertAlmostEqual(coords.longitude, -74.0060, places=4)

    def test_apple_key_fallback(self):
        # No ©xyz box — only the QuickTime apple location key + ISO string in moov.
        key = b"com.apple.quicktime.location.ISO6709"
        meta = _box(b"meta", key + b"\x00\x00\x00\x10data\x00\x00\x00\x01\x00\x00\x00\x00" + b"+51.5074-000.1278/")
        ftyp = _box(b"ftyp", b"isom")
        data = ftyp + _box(b"moov", meta)
        coords = extract_video_gps(data)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords.latitude, 51.5074, places=4)
        self.assertAlmostEqual(coords.longitude, -0.1278, places=4)

    def test_no_gps_returns_none(self):
        moov = _box(b"moov", _box(b"udta", b""))
        data = _box(b"ftyp", b"isom") + moov
        self.assertIsNone(extract_video_gps(data))

    def test_extract_video_metadata_from_file(self):
        when = datetime(2023, 5, 1, 12, 0, 0)
        data = _build_mp4(b"+34.0522-118.2437/", when=when, moov_at_end=True)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            meta = extract_video_metadata(tmp_path)
            self.assertEqual(meta.filename, Path(tmp_path).name)
            self.assertIsNotNone(meta.gps)
            self.assertAlmostEqual(meta.gps.latitude, 34.0522, places=4)
            self.assertEqual(meta.timestamp, when)
            self.assertIsNone(meta.camera_make)
        finally:
            Path(tmp_path).unlink()

    def test_metadata_missing_gps_is_safe(self):
        moov = _box(b"moov", _box(b"udta", b""))
        data = _box(b"ftyp", b"isom") + moov
        with tempfile.NamedTemporaryFile(suffix=".mov", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            meta = extract_video_metadata(tmp_path)
            self.assertIsNone(meta.gps)
        finally:
            Path(tmp_path).unlink()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from icloud_live_picker.orientation import (
    asset_exif_orientation,
    exif_orientation_filter,
    exif_orientation_to_ccw_degrees,
    exif_orientation_transform,
    has_baked_orientation_marker,
    repair_mov_orientation,
)


class OrientationTests(unittest.TestCase):
    def test_exif_rotation_mapping(self) -> None:
        self.assertEqual(exif_orientation_to_ccw_degrees(1), 0.0)
        self.assertEqual(exif_orientation_to_ccw_degrees(3), 180.0)
        self.assertEqual(exif_orientation_to_ccw_degrees(6), -90.0)
        self.assertEqual(exif_orientation_to_ccw_degrees(8), 90.0)
        self.assertIsNone(exif_orientation_to_ccw_degrees(2))

    def test_mirrored_exif_orientation_mapping(self) -> None:
        orientation_2 = exif_orientation_transform(2)
        orientation_4 = exif_orientation_transform(4)
        orientation_5 = exif_orientation_transform(5)
        orientation_7 = exif_orientation_transform(7)
        self.assertTrue(orientation_2.horizontal_flip)
        self.assertTrue(orientation_4.vertical_flip)
        self.assertEqual(orientation_5.rotation_ccw, 90.0)
        self.assertTrue(orientation_5.horizontal_flip)
        self.assertEqual(orientation_7.rotation_ccw, -90.0)
        self.assertTrue(orientation_7.horizontal_flip)
        self.assertEqual("hflip", exif_orientation_filter(2))
        self.assertEqual("hflip,vflip", exif_orientation_filter(3))
        self.assertEqual("vflip", exif_orientation_filter(4))
        self.assertEqual("transpose=cclock,hflip", exif_orientation_filter(5))
        self.assertEqual("transpose=clock", exif_orientation_filter(6))
        self.assertEqual("transpose=clock,hflip", exif_orientation_filter(7))
        self.assertEqual("transpose=cclock", exif_orientation_filter(8))

    def test_cloudkit_orientation_extraction(self) -> None:
        asset = SimpleNamespace(
            _master_record={"fields": {"originalOrientation": {"value": 6}}},
            _asset_record={"fields": {"orientation": {"value": 8}}},
        )
        self.assertEqual(asset_exif_orientation(asset), 6)
        asset_only = SimpleNamespace(
            _master_record={"fields": {}},
            _asset_record={"fields": {"orientation": {"value": 8}}},
        )
        self.assertEqual(asset_exif_orientation(asset_only), 8)
        legacy = SimpleNamespace(
            _master_record={"fields": {"orientation": {"value": "3"}}}
        )
        self.assertEqual(asset_exif_orientation(legacy), 3)
        self.assertIsNone(asset_exif_orientation(SimpleNamespace()))
        invalid = SimpleNamespace(
            _master_record={"fields": {"originalOrientation": {"value": 9}}},
            _asset_record={"fields": {"orientation": {"value": "bad"}}},
        )
        self.assertIsNone(asset_exif_orientation(invalid))

    def test_failure_keeps_original_mov(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "live.mov"
            path.write_bytes(b"original")
            failed = subprocess.CompletedProcess([], 1, "", "mux failed")
            with mock.patch("icloud_live_picker.orientation.subprocess.run", return_value=failed):
                result = repair_mov_orientation(path, 6, ffmpeg_executable="ffmpeg")
            self.assertFalse(result.changed)
            self.assertIn("mux failed", result.warning)
            self.assertEqual(path.read_bytes(), b"original")

    def test_success_replaces_mov_transactionally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "live.mov"
            path.write_bytes(b"original")

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
                Path(command[-1]).write_bytes(b"remuxed")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch("icloud_live_picker.orientation.subprocess.run", side_effect=fake_run):
                result = repair_mov_orientation(path, 8, ffmpeg_executable="ffmpeg")
            self.assertTrue(result.changed)
            self.assertEqual(path.read_bytes(), b"remuxed")

    def test_vertical_mirror_is_baked_and_display_matrix_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mirrored.mov"
            path.write_bytes(b"original")
            captured: list[str] = []

            def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
                captured.extend(command)
                Path(command[-1]).write_bytes(b"remuxed")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch("icloud_live_picker.orientation.subprocess.run", side_effect=fake_run):
                result = repair_mov_orientation(path, 4, ffmpeg_executable="ffmpeg")
            self.assertTrue(result.changed)
            self.assertIn("-noautorotate", captured)
            self.assertIn("libx265", captured)
            filter_value = captured[captured.index("-filter:v:0") + 1]
            self.assertEqual("vflip,sidedata=delete:type=DISPLAYMATRIX", filter_value)
            self.assertIn("iCloudPickerOrientationBaked=4", captured)
            self.assertNotIn("-display_vflip:v:0", captured)
            self.assertIn("copy", captured)

    def test_identity_and_already_baked_files_are_not_processed_again(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            identity = Path(temp_dir) / "identity.mov"
            identity.write_bytes(b"original")
            marked = Path(temp_dir) / "marked.mov"
            marked.write_bytes(b"prefix-iCloudPickerOrientationBaked-suffix")
            with mock.patch("icloud_live_picker.orientation.subprocess.run") as run:
                self.assertFalse(
                    repair_mov_orientation(identity, 1, ffmpeg_executable="ffmpeg").changed
                )
                self.assertFalse(
                    repair_mov_orientation(marked, 4, ffmpeg_executable="ffmpeg").changed
                )
            run.assert_not_called()
            self.assertTrue(has_baked_orientation_marker(marked))
            self.assertFalse(has_baked_orientation_marker(identity))


if __name__ == "__main__":
    unittest.main()

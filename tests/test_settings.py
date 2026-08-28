from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from icloud_live_picker.constants import SORT_NAME_ASC
from icloud_live_picker.settings import AppSettings, SETTINGS_SCHEMA_VERSION, SettingsStore


class SettingsTests(unittest.TestCase):
    def test_round_trip_persists_login_and_preferences_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            store = SettingsStore(path)
            settings = AppSettings(
                remember_account=True,
                account="+8613812345678",
                login_method="phone",
                country_code="+86",
                domain="cn",
                cookie_dir="C:/sessions",
                sort_mode=SORT_NAME_ASC,
                auto_pair_selection=True,
                auto_restore_session=True,
                last_login_ok=True,
                fix_mov_orientation=True,
                thumbnail_quality="high",
                preview_quality="original",
            )
            store.save(settings)
            loaded = store.load()
            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded.account, "+8613812345678")
        self.assertTrue(loaded.last_login_ok)
        self.assertEqual("phone", loaded.login_method)
        self.assertEqual("+86", loaded.country_code)
        self.assertTrue(loaded.auto_pair_selection)
        self.assertTrue(loaded.fix_mov_orientation)
        self.assertEqual("high", loaded.thumbnail_quality)
        self.assertEqual("original", loaded.preview_quality)
        self.assertNotIn("password", raw)
        self.assertNotIn("verification_code", raw)
        self.assertEqual(SETTINGS_SCHEMA_VERSION, raw["schema_version"])

    def test_invalid_settings_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(SettingsStore(path).load(), AppSettings())

    def test_disabling_account_memory_clears_login_state(self) -> None:
        settings = AppSettings(
            remember_account=False,
            account="should-clear",
            last_login_ok=True,
        ).normalize()
        self.assertEqual(settings.account, "")
        self.assertFalse(settings.last_login_ok)

    def test_invalid_image_quality_falls_back_to_recommended_defaults(self) -> None:
        settings = AppSettings(thumbnail_quality="unknown", preview_quality="huge").normalize()
        self.assertEqual("balanced", settings.thumbnail_quality)
        self.assertEqual("high", settings.preview_quality)

    def test_v02_remembered_account_is_migrated_for_session_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "remember_account": True,
                        "account": "+8613812345678",
                        "domain": "cn",
                        "cookie_dir": "C:/sessions",
                        "sort_mode": SORT_NAME_ASC,
                    }
                ),
                encoding="utf-8",
            )
            loaded = SettingsStore(path).load()
        self.assertTrue(loaded.last_login_ok)

    def test_new_install_defaults_to_mainland_phone_login(self) -> None:
        settings = AppSettings()
        self.assertEqual("phone", settings.login_method)
        self.assertEqual("+86", settings.country_code)
        self.assertEqual("cn", settings.domain)

    def test_missing_settings_file_defaults_to_mainland_phone_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            loaded = SettingsStore(Path(temp_dir) / "missing-settings.json").load()
        self.assertEqual("phone", loaded.login_method)
        self.assertEqual("+86", loaded.country_code)
        self.assertEqual("cn", loaded.domain)

    def test_user_directories_are_resolved_when_settings_are_created(self) -> None:
        target_home = Path("X:/Users/TargetUser")
        with (
            patch(
                "icloud_live_picker.settings.default_cookie_dir",
                return_value=target_home / ".icloudpd-picker",
            ),
            patch(
                "icloud_live_picker.settings.default_output_dir",
                return_value=target_home / "Pictures" / "iCloudPicker",
            ),
        ):
            settings = AppSettings()
        self.assertEqual(str(target_home / ".icloudpd-picker"), settings.cookie_dir)
        self.assertEqual(str(target_home / "Pictures" / "iCloudPicker"), settings.output_dir)

    def test_settings_store_resolves_default_path_at_construction_time(self) -> None:
        target = Path("X:/Users/TargetUser/AppData/Roaming/iCloudLivePhotoPicker/settings.json")
        with patch("icloud_live_picker.settings.default_settings_path", return_value=target):
            store = SettingsStore()
        self.assertEqual(target, store.path)

    def test_old_email_account_migrates_to_email_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text(
                json.dumps({"remember_account": True, "account": "name@example.com", "domain": "com"}),
                encoding="utf-8",
            )
            loaded = SettingsStore(path).load()
        self.assertEqual("email", loaded.login_method)
        self.assertEqual("name@example.com", loaded.account)

    def test_legacy_mainland_phone_domain_is_migrated_to_cn_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "remember_account": True,
                        "account": "+8613812345678",
                        "login_method": "phone",
                        "country_code": "+86",
                        "domain": "com",
                    }
                ),
                encoding="utf-8",
            )
            loaded = SettingsStore(path).load()
        self.assertEqual("cn", loaded.domain)
        self.assertEqual(SETTINGS_SCHEMA_VERSION, loaded.schema_version)

    def test_explicit_com_choice_is_preserved_after_domain_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": SETTINGS_SCHEMA_VERSION,
                        "remember_account": True,
                        "account": "+8613812345678",
                        "login_method": "phone",
                        "country_code": "+86",
                        "domain": "com",
                    }
                ),
                encoding="utf-8",
            )
            loaded = SettingsStore(path).load()
        self.assertEqual("com", loaded.domain)

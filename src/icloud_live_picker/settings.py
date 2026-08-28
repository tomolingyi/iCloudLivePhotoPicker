from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .constants import (
    SORT_NEWEST,
    SORT_OPTIONS,
    PREVIEW_QUALITY_LABELS,
    THUMBNAIL_QUALITY_LABELS,
    default_cookie_dir,
    default_output_dir,
    default_settings_path,
)


SETTINGS_SCHEMA_VERSION = 2


@dataclass
class AppSettings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    remember_account: bool = False
    account: str = ""
    login_method: str = "phone"
    country_code: str = "+86"
    domain: str = "cn"
    cookie_dir: str = field(default_factory=lambda: str(default_cookie_dir()))
    sort_mode: str = SORT_NEWEST
    auto_pair_selection: bool = True
    auto_restore_session: bool = True
    last_login_ok: bool = False
    fix_mov_orientation: bool = True
    thumbnail_quality: str = "balanced"
    preview_quality: str = "high"
    output_dir: str = field(default_factory=lambda: str(default_output_dir()))
    photo_size: str = "original"
    live_size: str = "original"
    overwrite: bool = False
    live_suffix: bool = False

    def normalize(self) -> "AppSettings":
        if self.login_method not in ("email", "phone"):
            self.login_method = "phone"
        normalized_code = "+" + "".join(character for character in self.country_code if character.isdigit())
        self.country_code = normalized_code if len(normalized_code) > 1 else "+86"
        if self.domain not in ("com", "cn"):
            self.domain = "cn"
        if self.sort_mode not in SORT_OPTIONS:
            self.sort_mode = SORT_NEWEST
        if self.photo_size not in ("original", "adjusted", "medium"):
            self.photo_size = "original"
        if self.live_size not in ("original", "medium", "small"):
            self.live_size = "original"
        if self.thumbnail_quality not in THUMBNAIL_QUALITY_LABELS:
            self.thumbnail_quality = "balanced"
        if self.preview_quality not in PREVIEW_QUALITY_LABELS:
            self.preview_quality = "high"
        if not self.remember_account:
            self.account = ""
            self.last_login_ok = False
        return self

    def public_dict(self) -> dict[str, Any]:
        """Return the complete allow-listed schema; it contains no secret fields."""
        return asdict(self)


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_settings_path()

    def load(self) -> AppSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return AppSettings()
        if not isinstance(raw, dict):
            return AppSettings()

        raw_schema_version = raw.get("schema_version", 0)
        if not isinstance(raw_schema_version, int):
            raw_schema_version = 0
        allowed = {field.name: field for field in fields(AppSettings)}
        values: dict[str, Any] = {}
        defaults = AppSettings()
        for key in allowed:
            value = raw.get(key, getattr(defaults, key))
            expected = type(getattr(defaults, key))
            if isinstance(value, expected):
                values[key] = value
        settings = AppSettings(**values)
        if "login_method" not in raw:
            settings.login_method = "email" if "@" in settings.account else "phone"
        if "country_code" not in raw and settings.account.startswith("+86"):
            settings.country_code = "+86"
        # Before v0.5.1, installs upgraded from an older release could retain
        # the historical `com` default even after phone/+86 became the default
        # login mode. Migrate that legacy combination once. Settings saved by
        # this schema keep an explicit user choice of `com` unchanged.
        if raw_schema_version < SETTINGS_SCHEMA_VERSION:
            if settings.domain == "com" and (
                (settings.login_method == "phone" and settings.country_code == "+86")
                or not settings.account
            ):
                settings.domain = "cn"
            settings.schema_version = SETTINGS_SCHEMA_VERSION
        # v0.2 saved the account and session directory but did not yet have an
        # explicit last_login_ok flag. Treat a remembered v0.2 account as a
        # candidate for one safe session-restore attempt after upgrading.
        if "last_login_ok" not in raw and settings.remember_account and settings.account:
            settings.last_login_ok = True
        return settings.normalize()

    def save(self, settings: AppSettings) -> None:
        payload = settings.normalize().public_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

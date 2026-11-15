"""Verify manifest, translations, and icon metadata consistency."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.bgw320_probe.binary_sensor import BINARY_SENSORS
from custom_components.bgw320_probe.const import DOMAIN
from custom_components.bgw320_probe.sensor import SENSORS

ROOT = Path(__file__).resolve().parents[1]
COMP_DIR = ROOT / "custom_components" / "bgw320_probe"


def test_manifest_and_hacs_metadata() -> None:
    """Verify manifest.json and hacs.json are valid and consistent."""
    manifest = json.loads((COMP_DIR / "manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))

    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_polling"
    assert manifest["integration_type"] == "device"
    assert manifest["requirements"] == []
    assert "version" in manifest
    assert hacs["name"] == manifest["name"]


def test_translations_and_icons_cover_all_entities() -> None:
    """Verify strings.json, translations/en.json, and icons.json match all entities."""
    strings = json.loads((COMP_DIR / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((COMP_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
    icons = json.loads((COMP_DIR / "icons.json").read_text(encoding="utf-8"))

    assert strings == en

    for desc in BINARY_SENSORS:
        assert desc.translation_key is not None
        assert desc.translation_key in strings["entity"]["binary_sensor"]
        assert desc.translation_key in icons["entity"]["binary_sensor"]

    for desc in SENSORS:
        assert desc.translation_key is not None
        assert desc.translation_key in strings["entity"]["sensor"]
        assert desc.translation_key in icons["entity"]["sensor"]


def test_brand_assets_are_valid_pngs() -> None:
    """Verify local Home Assistant brand assets exist and are valid PNG files."""
    brand_dir = COMP_DIR / "brand"
    for filename in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png"):
        asset = brand_dir / filename
        assert asset.is_file(), f"Missing brand asset: {filename}"
        assert asset.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


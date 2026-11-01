"""Tests for manifest, constants, and localization."""
import json
from pathlib import Path
from custom_components.cde_lightband.const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_HISTORY_DAYS,
    CONF_USERNAME,
    CONF_PASSWORD,
)

def test_constants_defined():
    assert DOMAIN == "cde_lightband"
    assert DEFAULT_SCAN_INTERVAL == 60
    assert DEFAULT_HISTORY_DAYS == 30
    assert CONF_USERNAME == "username"
    assert CONF_PASSWORD == "password"

def test_manifest_schema():
    manifest_path = Path("custom_components/cde_lightband/manifest.json")
    assert manifest_path.exists()
    with open(manifest_path) as f:
        manifest = json.load(f)
    assert manifest["domain"] == DOMAIN
    assert manifest["name"] == "CDE Lightband"
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "service"
    assert "iot_class" in manifest
    assert "version" in manifest

def test_translations_valid():
    strings_path = Path("custom_components/cde_lightband/strings.json")
    en_path = Path("custom_components/cde_lightband/translations/en.json")
    assert strings_path.exists()
    assert en_path.exists()
    with open(strings_path) as f:
        strings = json.load(f)
    with open(en_path) as f:
        en = json.load(f)
    assert "config" in strings
    assert "step" in strings["config"]
    assert "error" in strings["config"]
    assert "invalid_auth" in strings["config"]["error"]
    assert strings == en

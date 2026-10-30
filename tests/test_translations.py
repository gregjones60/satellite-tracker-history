"""translations/en.json is the only source of UI text; check it covers what the code and services.yaml use."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/satellite_tracker_history"
STRINGS = json.loads((ROOT / "translations/en.json").read_text())


def test_strings_json_is_not_reintroduced():
    # Custom integrations only load translations/; a second copy would silently drift.
    assert not (ROOT / "strings.json").exists()


def test_every_service_and_field_has_text_and_an_icon():
    yaml = pytest.importorskip("yaml")
    services = yaml.safe_load((ROOT / "services.yaml").read_text())
    icons = json.loads((ROOT / "icons.json").read_text())
    assert set(STRINGS["services"]) == set(services) == set(icons["services"])
    for name, service in services.items():
        text = STRINGS["services"][name]
        assert text["name"] and text["description"]
        assert set(text["fields"]) == set(service["fields"])
        assert all(field["name"] and field["description"] for field in text["fields"].values())
        assert "name" not in service and "description" not in service


def test_flow_steps_errors_and_aborts_are_translated():
    source = (ROOT / "config_flow.py").read_text()
    used_steps = set(re.findall(r'step_id="(\w+)"', source))
    # Error keys are written against "base" or a field constant such as CONF_FEED_ID.
    used_errors = set(re.findall(r'(?:"base"|CONF_\w+)\]? ?[:=] ?"(\w+)"', source))
    used_aborts = set(re.findall(r'reason="(\w+)"', source))
    # The provider menu's options are steps too, named after the providers.
    used_steps |= set(re.findall(r'async def async_step_(\w+)', source)) - {"import"}
    assert used_steps == {"user", "legacy", "spot", "garmin", "vehicle", "reconfigure", "init"}
    assert used_steps - {"init"} <= set(STRINGS["config"]["step"])
    assert set(STRINGS["config"]["step"]["user"]["menu_options"]) == {"spot", "garmin"}
    assert set(STRINGS["options"]["step"]) == {"init"}
    assert used_errors == {"cannot_connect", "feed_not_found", "feed_rejected", "no_messenger",
                           "mapshare_not_found", "mapshare_rejected"}
    # Feed-ID parse failures are passed to the shared feed step by name.
    used_errors |= set(re.findall(r'"(\w+_invalid)"', source)) | {"feed_not_found"}
    assert "mapshare_invalid" in used_errors
    assert used_errors <= set(STRINGS["config"]["error"])
    assert used_aborts <= set(STRINGS["config"]["abort"])
    assert {"already_configured", "reconfigure_successful"} <= set(STRINGS["config"]["abort"])


def test_exception_and_issue_keys_are_translated():
    for module in ("import_actions.py", "__init__.py"):
        source = (ROOT / module).read_text()
        issues = set(re.findall(r"async_create_issue\([^)]*translation_key='(\w+)'", source, re.S))
        exceptions = set(re.findall(r"translation_key='(\w+)'", source)) - issues
        assert exceptions and exceptions <= set(STRINGS["exceptions"]), module
        assert issues <= set(STRINGS.get("issues", {})), module
    assert {"title", "description"} <= set(STRINGS["issues"]["legacy_installed"])

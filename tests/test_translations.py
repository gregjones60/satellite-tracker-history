"""translations/en.json is the only source of UI text; check it covers what the code and services.yaml use."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/spot_trace_history"
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
    for section in ("config", "options"):
        keys = STRINGS[section]
        used_steps = set(re.findall(r'step_id="(\w+)"', source))
        used_errors = set(re.findall(r'"(?:base|feed_id)"\]? ?[:=] ?"(\w+)"', source))
        used_aborts = set(re.findall(r'reason="(\w+)"', source))
        if section == "config":
            assert {"user", "reconfigure"} <= set(keys["step"]) & used_steps
            assert used_errors <= set(keys["error"])
            assert {"already_configured", "reconfigure_successful"} <= set(keys["abort"])
        else:
            assert {"init", "manage_devices", "device"} <= set(keys["step"]) & used_steps
            assert used_aborts <= set(keys["abort"])
    assert used_errors == {"cannot_connect", "feed_not_found", "feed_rejected"}


def test_exception_keys_used_by_actions_are_translated():
    source = (ROOT / "import_actions.py").read_text()
    assert set(re.findall(r"translation_key='(\w+)'", source)) <= set(STRINGS["exceptions"])

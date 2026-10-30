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
    used_steps = set(re.findall(r'step_id="(\w+)"', source))
    # Error keys are written against "base" or a field constant such as CONF_FEED_ID.
    used_errors = set(re.findall(r'(?:"base"|CONF_\w+)\]? ?[:=] ?"(\w+)"', source))
    used_aborts = set(re.findall(r'reason="(\w+)"', source))
    assert used_steps == {"user", "vehicle", "reconfigure", "init"}
    assert {"user", "vehicle", "reconfigure"} <= set(STRINGS["config"]["step"])
    assert set(STRINGS["options"]["step"]) == {"init"}
    assert used_errors == {"cannot_connect", "feed_not_found", "feed_rejected", "no_messenger"}
    assert used_errors <= set(STRINGS["config"]["error"])
    assert used_aborts <= set(STRINGS["config"]["abort"])
    assert {"already_configured", "reconfigure_successful"} <= set(STRINGS["config"]["abort"])


def test_exception_keys_are_translated():
    for module in ("import_actions.py", "__init__.py"):
        source = (ROOT / module).read_text()
        keys = set(re.findall(r"translation_key='(\w+)'", source))
        assert keys and keys <= set(STRINGS["exceptions"]), module

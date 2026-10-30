"""Use the real Home Assistant test harness when installed, else import pure modules with stand-ins.

With requirements_test.txt installed (Python 3.14), the integration package is imported for real
and tests marked `ha` run against a live `hass` fixture. Without it, those tests are skipped and the
remaining tests use the minimal stand-ins below.
"""
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

try:
    import pytest_homeassistant_custom_component  # noqa: F401
except ImportError:
    HAS_HA = False
else:
    HAS_HA = True

if HAS_HA:
    sys.path.insert(0, str(ROOT))

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(request):
        """Let HA's loader find custom_components/ for harness tests."""
        if request.node.get_closest_marker("ha"):
            request.getfixturevalue("enable_custom_integrations")
else:
    package = types.ModuleType("custom_components")
    package.__path__ = [str(ROOT / "custom_components")]
    sys.modules.setdefault("custom_components", package)
    integration = types.ModuleType("custom_components.satellite_tracker_history")
    integration.__path__ = [str(ROOT / "custom_components" / "satellite_tracker_history")]
    sys.modules["custom_components.satellite_tracker_history"] = integration

    # Only the API module needs this Home Assistant helper.
    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    aio = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aio.async_get_clientsession = lambda hass: None
    sys.modules.setdefault("homeassistant", ha)
    sys.modules.setdefault("homeassistant.helpers", helpers)
    sys.modules.setdefault("homeassistant.helpers.aiohttp_client", aio)


def pytest_collection_modifyitems(config, items):
    if HAS_HA:
        return
    skip = pytest.mark.skip(reason="needs pytest-homeassistant-custom-component (pip install -r requirements_test.txt)")
    for item in items:
        if item.get_closest_marker("ha"):
            item.add_marker(skip)

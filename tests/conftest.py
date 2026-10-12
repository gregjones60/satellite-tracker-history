"""Import pure integration modules without starting Home Assistant."""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("custom_components")
package.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", package)
integration = types.ModuleType("custom_components.spot_trace_history")
integration.__path__ = [str(ROOT / "custom_components" / "spot_trace_history")]
sys.modules["custom_components.spot_trace_history"] = integration

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

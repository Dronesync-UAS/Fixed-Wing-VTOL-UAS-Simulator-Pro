"""
Plugin loader. Each file in the plugins/ folder defines one instructor
control. To add a new one later, just drop a new file in this folder -
nothing else needs to change.

Each plugin file must define a PLUGIN dictionary like this:

PLUGIN = {
    "id": "unique_id",           # used internally, no spaces
    "label": "Button Text",      # what the instructor sees
    "category": "Flight Ops",    # which section it appears in
    "style": "normal",           # normal / warning / experimental
    "handler": some_function,    # called when the button is clicked
}

Optionally a plugin may declare "inputs" - a list of number boxes shown
above its button that the instructor fills in first:

    "inputs": [{"name": "radius_m", "label": "Radius (m)", "default": 150,
                "min": 10, "step": 10}],

Each input's value is passed to the handler as a keyword argument of the
same name (as a string), e.g. handler(radius_m="150"). Handlers with
inputs should validate/convert those values themselves.

REVISED 23 Aug 2026: also keeps a reference to each plugin's loaded
module (under the "_module" key, not part of the documented PLUGIN
contract above). This lets instructor_station.py show a live on/off
status light on any plugin that happens to expose a module-level
`state` dict with an "active" key (the toggle-style failure plugins:
GPS, RC Signal, Data Link, Motor, Engine) - without every plugin author
needing to know that UI feature exists.
"""

import importlib.util
import os

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "plugins")


def load_plugins():
    plugins = []
    for filename in sorted(os.listdir(PLUGIN_DIR)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        path = os.path.join(PLUGIN_DIR, filename)
        spec = importlib.util.spec_from_file_location(filename[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "PLUGIN"):
            plugin = module.PLUGIN
            plugin["_module"] = module
            plugins.append(plugin)
    return plugins

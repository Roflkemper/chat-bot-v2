import sys
from pathlib import Path

_TRACKER_DIR = str(Path(__file__).parent.parent)

# ginarea_tracker/ must be first so its modules shadow root-level packages
# with the same names (e.g. root storage/ package vs ginarea_tracker/storage.py)
if _TRACKER_DIR not in sys.path:
    sys.path.insert(0, _TRACKER_DIR)
else:
    sys.path.remove(_TRACKER_DIR)
    sys.path.insert(0, _TRACKER_DIR)

# Purge any already-cached root-level modules with conflicting names
for _name in ("storage", "events", "ginarea_client"):
    cached = sys.modules.get(_name)
    if cached is not None:
        cached_file = getattr(cached, "__file__", "") or ""
        if _TRACKER_DIR not in cached_file:
            del sys.modules[_name]

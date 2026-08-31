"""pytest conftest: make plugin modules importable from the plugin root.

GTFS-GO modules use top-level imports (e.g. `import constants`,
`import gtfs_parser`, `from gtfs_go_dialog import ...`) as QGIS loads
them, so the plugin root must be on sys.path when tests import them.
"""

import sys
from pathlib import Path

_plugin_root = str(Path(__file__).resolve().parent)
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)

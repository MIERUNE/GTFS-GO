"""pytest conftest: make plugin importable as 'plugin_dir' package."""

import os
import sys
import types
from pathlib import Path

import pytest

# The plugin root is this directory. For relative imports like
# `from ...kumoy` (in processing/upload_vector/algorithm.py) to work,
# the plugin root must be importable as a package — not as top-level.
#
# Register a virtual 'plugin_dir' package whose __path__ points to the
# plugin root.  This avoids creating a filesystem symlink outside the
# project directory (which can fail in Docker / read-only environments).
_plugin_root = Path(__file__).resolve().parent

_pkg = types.ModuleType("plugin_dir")
_pkg.__path__ = [str(_plugin_root)]
sys.modules["plugin_dir"] = _pkg

# Remove the plugin root from sys.path so that plugin subpackages
# (e.g. 'processing/') don't shadow QGIS built-in modules.
# Plugin modules must be imported via 'plugin_dir.xxx' instead.
_plugin_root_str = str(_plugin_root)
sys.path[:] = [p for p in sys.path if p not in (_plugin_root_str, "")]


@pytest.fixture(scope="session")
def qgis_plugin_path(qgis_app):
    """Add QGIS's built-in plugin directory to sys.path.

    Depends on qgis_app (provided by pytest-qgis) to ensure
    QgsApplication is fully initialized before querying pkgDataPath().
    """
    from qgis.core import QgsApplication

    qgis_plugins = os.path.join(QgsApplication.pkgDataPath(), "python", "plugins")
    if os.path.isdir(qgis_plugins) and qgis_plugins not in sys.path:
        sys.path.append(qgis_plugins)

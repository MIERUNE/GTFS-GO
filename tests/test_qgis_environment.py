"""
reference: https://github.com/felt/qgis-plugin/blob/main/felt/test/test_qgis_environment.py
Tests for QGIS functionality.
"""

import unittest

from qgis.core import QgsProviderRegistry

from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class QGISTest(unittest.TestCase):
    """Test the QGIS Environment"""

    def test_qgis_environment(self):
        """QGIS environment has the expected providers"""

        r = QgsProviderRegistry.instance()
        self.assertIn("gdal", r.providerList())
        self.assertIn("ogr", r.providerList())


if __name__ == "__main__":
    unittest.main()

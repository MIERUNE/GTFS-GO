import os
import unittest

from gtfs_go_dialog import GTFSGoDialog

from .utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


class TestDialog(unittest.TestCase):
    def test_dialog(self):
        """Test the dialog."""
        dialog = GTFSGoDialog(IFACE)

        assert dialog.isVisible() is False
        dialog.show()
        assert dialog.isVisible() is True
        dialog.close()
        assert dialog.isVisible() is False


if __name__ == "__main__":
    unittest.main()

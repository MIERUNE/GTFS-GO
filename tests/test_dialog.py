from gtfs_go_dialog import GTFSGoDialog


def test_dialog(qgis_iface):
    """Test the dialog."""
    dialog = GTFSGoDialog(qgis_iface)

    assert dialog.isVisible() is False
    dialog.show()
    assert dialog.isVisible() is True
    dialog.close()
    assert dialog.isVisible() is False

from qgis.gui import QgisInterface

from gtfs_go_dialog import GTFSGoDialog


def test_init(qgis_iface: QgisInterface):
    dialog = GTFSGoDialog(qgis_iface)
    assert not dialog.isVisible()
    dialog.show()
    assert dialog.isVisible()
    dialog.close()
    assert not dialog.isVisible()

    # init_gui() runs during init
    assert dialog.repositoryCombobox.currentText() == "Preset"
    assert dialog.comboBox.currentText() == "---Load local ZipFile---"

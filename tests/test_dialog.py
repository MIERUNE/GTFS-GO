from gtfs_go_dialog import GTFSGoDialog


def test_dialog(qgis_iface):
    """Test the dialog."""
    dialog = GTFSGoDialog(qgis_iface)

    assert dialog.isVisible() is False
    dialog.show()
    assert dialog.isVisible() is True
    dialog.close()
    assert dialog.isVisible() is False


def test_japan_dpf_search(qgis_iface, monkeypatch):
    feed = {
        "organization_id": "org1",
        "organization_name": "Org",
        "feed_id": "feed1",
        "feed_name": "Feed",
        "feed_pref_id": 1,
        "file_uid": "uid1",
        "file_url": "https://example.com/gtfs.zip",
    }
    monkeypatch.setattr(
        "processing_provider.search_japan_dpf.api.get_feeds",
        lambda *args, **kwargs: [dict(feed)],
    )
    dialog = GTFSGoDialog(qgis_iface)
    dialog.japan_dpf_search()

    assert dialog.japanDpfResultTableView.model().rowCount() == 1
    row = dialog.get_selected_row_data_in_japan_dpf_table(0)
    assert row["organization"] == "Org"
    assert row["feed"] == "Feed"
    assert row["pref"] == "北海道"
    assert row["file_url"] == "https://example.com/gtfs.zip"

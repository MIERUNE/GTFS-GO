"""Test that the plugin entrypoint is importable."""


def test_import_plugin(qgis_app):
    from gtfs_go import GTFSGo

    assert GTFSGo is not None

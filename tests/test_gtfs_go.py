from gtfs_go import GTFSGo


def test_run(plugin: GTFSGo):
    """ダイアログを表示する関数のテスト"""

    # 初期状態でダイアログは未初期化
    assert plugin.dialog is None

    plugin.run()
    assert plugin.dialog.isVisible()

    plugin.dialog.close()

    assert not plugin.dialog.isVisible()  # ダイアログが閉じられても
    assert plugin.dialog is not None  # インスタンスは保持される

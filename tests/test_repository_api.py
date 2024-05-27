from repository.japan_dpf import api


def test_get_feeds_valid():
    feeds = api.get_feeds("2024-08-01")
    assert len(feeds) > 0

    feeds = api.get_feeds("2024-08-01", extent="139.7,35.6,139.8,35.7", pref="6")
    assert len(feeds) > 0


def test_get_feeds_invalid():
    feeds = api.get_feeds("2024-08-01", pref="48")  # 48 is invalid pref
    assert len(feeds) == 0

    feeds = api.get_feeds("2000-08-01")  # too old
    assert len(feeds) == 0

    feeds = api.get_feeds("2024-08-01", extent="0,0,0,0")  # null island
    assert len(feeds) == 0

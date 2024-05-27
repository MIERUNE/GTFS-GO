from gtfs_go_labeling import get_labeling_for_stops


def test_get_labeling_for_stops():
    labeling = get_labeling_for_stops()
    assert labeling.settings().fieldName == "stop_name"  # default value

    labeling = get_labeling_for_stops("testname")
    assert labeling.settings().fieldName == "testname"

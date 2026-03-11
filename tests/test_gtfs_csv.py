"""Tests for gtfs_csv module (pure Python, no QGIS dependency)."""

from pathlib import Path

from plugin_dir.gtfs_csv import CsvTable, load_gtfs_folder, save_gtfs_folder


class TestLoadGtfsFolder:
    def test_load_minimal_gtfs(self, minimal_gtfs: Path):
        tables = load_gtfs_folder(str(minimal_gtfs))

        assert "stops.txt" in tables
        assert "routes.txt" in tables
        assert "trips.txt" in tables
        assert "stop_times.txt" in tables
        assert "calendar.txt" in tables

    def test_headers_and_rows(self, minimal_gtfs: Path):
        tables = load_gtfs_folder(str(minimal_gtfs))

        stops = tables["stops.txt"]
        assert stops.headers == ["stop_id", "stop_name", "stop_lat", "stop_lon"]
        assert len(stops.rows) == 3
        assert stops.rows[0][0] == "S1"

    def test_ignores_non_txt_files(self, minimal_gtfs: Path):
        (minimal_gtfs / "readme.md").write_text("ignore me")
        (minimal_gtfs / "data.json").write_text("{}")

        tables = load_gtfs_folder(str(minimal_gtfs))
        assert "readme.md" not in tables
        assert "data.json" not in tables

    def test_skips_empty_file(self, tmp_path: Path):
        (tmp_path / "empty.txt").write_text("")
        tables = load_gtfs_folder(str(tmp_path))
        assert "empty.txt" not in tables

    def test_skips_header_only_file(self, tmp_path: Path):
        (tmp_path / "headeronly.txt").write_text("col_a,col_b\n")
        tables = load_gtfs_folder(str(tmp_path))
        assert "headeronly.txt" in tables
        assert tables["headeronly.txt"].rows == []

    def test_empty_folder(self, tmp_path: Path):
        tables = load_gtfs_folder(str(tmp_path))
        assert tables == {}

    def test_utf8_bom(self, tmp_path: Path):
        content = "\ufeffstop_id,stop_name\nS1,Station\n"
        (tmp_path / "stops.txt").write_text(content, encoding="utf-8-sig")
        tables = load_gtfs_folder(str(tmp_path))
        assert tables["stops.txt"].headers == ["stop_id", "stop_name"]

    def test_ignores_subdirectories(self, tmp_path: Path):
        sub = tmp_path / "subdir.txt"
        sub.mkdir()
        tables = load_gtfs_folder(str(tmp_path))
        assert "subdir.txt" not in tables


class TestSaveGtfsFolder:
    def test_save_creates_files(self, tmp_path: Path):
        tables = {
            "stops.txt": CsvTable(
                headers=["stop_id", "stop_name"],
                rows=[["S1", "Stop A"]],
            )
        }
        save_gtfs_folder(str(tmp_path), tables)
        assert (tmp_path / "stops.txt").exists()

    def test_roundtrip(self, minimal_gtfs: Path):
        tables = load_gtfs_folder(str(minimal_gtfs))

        out = minimal_gtfs / "output"
        out.mkdir()
        save_gtfs_folder(str(out), tables)
        tables2 = load_gtfs_folder(str(out))

        for name in tables:
            assert tables2[name].headers == tables[name].headers
            assert tables2[name].rows == tables[name].rows

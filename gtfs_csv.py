from __future__ import annotations

import csv
import os
from dataclasses import dataclass


@dataclass
class CsvTable:
    headers: list[str]
    rows: list[list[str]]


def load_gtfs_folder(folder: str) -> dict[str, CsvTable]:
    """Load all .txt CSV files from a GTFS folder."""
    tables: dict[str, CsvTable] = {}
    for filename in sorted(os.listdir(folder)):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(folder, filename)
        if not os.path.isfile(filepath):
            continue
        with open(filepath, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            if not headers:
                continue
            rows = [row for row in reader if row]
        tables[filename] = CsvTable(headers=headers, rows=rows)
    return tables


def save_gtfs_folder(folder: str, tables: dict[str, CsvTable]) -> None:
    """Write all tables back to CSV files in the folder."""
    for filename, table in tables.items():
        filepath = os.path.join(folder, filename)
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(table.headers)
            writer.writerows(table.rows)

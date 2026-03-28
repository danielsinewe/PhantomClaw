from __future__ import annotations

import json
import sqlite3
from pathlib import Path


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  page_shape_ok INTEGER NOT NULL DEFAULT 0,
  items_scanned INTEGER NOT NULL DEFAULT 0,
  items_considered INTEGER NOT NULL DEFAULT 0,
  items_liked INTEGER NOT NULL DEFAULT 0,
  stop_reason TEXT
);

CREATE TABLE IF NOT EXISTS run_reports (
  run_id TEXT PRIMARY KEY,
  search_url TEXT NOT NULL,
  artifact_path TEXT NOT NULL,
  screenshot_path TEXT,
  report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
  run_id TEXT NOT NULL,
  pass_index INTEGER NOT NULL,
  snapshot_json TEXT NOT NULL,
  PRIMARY KEY (run_id, pass_index)
);
"""


class StateStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SQLITE_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def start_run(self, run_id: str, started_at: str) -> None:
        self.conn.execute(
            "INSERT INTO runs (run_id, started_at, status) VALUES (?, ?, ?)",
            (run_id, started_at, "started"),
        )
        self.conn.commit()

    def finish_run(self, run_id: str, *, finished_at: str, status: str, page_shape_ok: bool, items_scanned: int, items_considered: int, items_liked: int, stop_reason: str | None) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, page_shape_ok=?, items_scanned=?, items_considered=?, items_liked=?, stop_reason=? WHERE run_id=?",
            (finished_at, status, int(page_shape_ok), items_scanned, items_considered, items_liked, stop_reason, run_id),
        )
        self.conn.commit()

    def record_snapshot(self, run_id: str, pass_index: int, snapshot) -> None:
        self.conn.execute(
            "INSERT INTO snapshots (run_id, pass_index, snapshot_json) VALUES (?, ?, ?) ON CONFLICT(run_id, pass_index) DO UPDATE SET snapshot_json=excluded.snapshot_json",
            (run_id, pass_index, json.dumps(snapshot.to_dict(), sort_keys=True)),
        )
        self.conn.commit()

    def record_run_report(self, run_id: str, search_url: str, artifact_path: str, report) -> None:
        self.conn.execute(
            "INSERT INTO run_reports (run_id, search_url, artifact_path, screenshot_path, report_json) VALUES (?, ?, ?, ?, ?) ON CONFLICT(run_id) DO UPDATE SET search_url=excluded.search_url, artifact_path=excluded.artifact_path, screenshot_path=excluded.screenshot_path, report_json=excluded.report_json",
            (run_id, search_url, artifact_path, report.screenshot_path, json.dumps(report.to_dict(), sort_keys=True)),
        )
        self.conn.commit()

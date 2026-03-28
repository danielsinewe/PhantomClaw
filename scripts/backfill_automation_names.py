from __future__ import annotations

import argparse
import sys
from pathlib import Path
import sqlite3

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import psycopg
from automation_analytics import ANALYTICS_POSTGRES_TABLE_SCHEMA, ANALYTICS_POSTGRES_VIEW_SCHEMA


POSTGRES_SQL = """
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS automation_label TEXT;
ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS surface TEXT;

UPDATE automation_runs
SET
  automation_name = CASE automation_name
    WHEN 'trustoutreach-linkedin' THEN 'linkedin-company-profile-engagement'
    WHEN 'linkedin-sales-community' THEN 'linkedin-sales-community-engagement'
    ELSE automation_name
  END,
  automation_label = CASE
    WHEN automation_name IN ('trustoutreach-linkedin', 'linkedin-company-profile-engagement') THEN 'LinkedIn Company Profile Engagement'
    WHEN automation_name IN ('linkedin-sales-community', 'linkedin-sales-community-engagement') THEN 'LinkedIn Sales Community Engagement'
    ELSE COALESCE(automation_label, automation_name)
  END,
  surface = CASE
    WHEN automation_name IN ('trustoutreach-linkedin', 'linkedin-company-profile-engagement') THEN 'core'
    WHEN automation_name IN ('linkedin-sales-community', 'linkedin-sales-community-engagement') THEN 'sales-community'
    ELSE COALESCE(surface, 'unknown')
  END
WHERE automation_name IN (
  'trustoutreach-linkedin',
  'linkedin-sales-community',
  'linkedin-company-profile-engagement',
  'linkedin-sales-community-engagement'
);
"""

SQLITE_SQL = """
UPDATE automation_runs
SET automation_name = CASE automation_name
  WHEN 'trustoutreach-linkedin' THEN 'linkedin-company-profile-engagement'
  WHEN 'linkedin-sales-community' THEN 'linkedin-sales-community-engagement'
  ELSE automation_name
END
WHERE automation_name IN ('trustoutreach-linkedin', 'linkedin-sales-community');
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill generic automation names into analytics storage")
    parser.add_argument("--database-url")
    parser.add_argument("--sqlite-path", type=Path)
    args = parser.parse_args(argv)

    if bool(args.database_url) == bool(args.sqlite_path):
        raise SystemExit("Provide exactly one of --database-url or --sqlite-path")

    if args.database_url:
        with psycopg.connect(args.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(ANALYTICS_POSTGRES_TABLE_SCHEMA)
                cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS automation_label TEXT")
                cur.execute("ALTER TABLE automation_runs ADD COLUMN IF NOT EXISTS surface TEXT")
                cur.execute(ANALYTICS_POSTGRES_VIEW_SCHEMA)
                cur.execute(POSTGRES_SQL)
            conn.commit()
        print("Backfilled Postgres automation names and surfaces")
        return 0

    with sqlite3.connect(args.sqlite_path) as conn:
        conn.execute(SQLITE_SQL)
        conn.commit()
    print(f"Backfilled SQLite automation names in {args.sqlite_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "tasks.db"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK(status IN ('Pending', 'Completed')),
    category TEXT NOT NULL DEFAULT 'General',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_due_status
    ON tasks (due_date, status);

CREATE TABLE IF NOT EXISTS deleted_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_task_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deleted_tasks_deleted_at
    ON deleted_tasks (deleted_at);
"""


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize(connection)
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    ensure_column(connection, "tasks", "category", "TEXT NOT NULL DEFAULT 'General'")
    ensure_column(connection, "tasks", "description", "TEXT NOT NULL DEFAULT ''")
    connection.commit()


def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )

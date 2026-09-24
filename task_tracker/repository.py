from __future__ import annotations

import sqlite3
from datetime import date

from .models import COMPLETED, PENDING, Task, TaskStats, utc_timestamp


class TaskRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def add_task(
        self,
        title: str,
        due_date: date,
        category: str = "General",
        description: str = "",
    ) -> Task:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Task title cannot be empty.")
        clean_category = category.strip() or "General"
        clean_description = description.strip()

        cursor = self.connection.execute(
            """
            INSERT INTO tasks (title, due_date, status, category, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                clean_title,
                due_date.isoformat(),
                PENDING,
                clean_category,
                clean_description,
            ),
        )
        self.connection.commit()
        return self.get_task(cursor.lastrowid)

    def get_task(self, task_id: int) -> Task:
        row = self.connection.execute(
            """
            SELECT id, title, due_date, status, category, description, created_at, completed_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"No task found with id {task_id}.")
        return Task.from_row(row)

    def pending_for_date(self, due_date: date) -> list[Task]:
        rows = self.connection.execute(
            """
            SELECT id, title, due_date, status, category, description, created_at, completed_at
            FROM tasks
            WHERE due_date = ?
              AND status = ?
            ORDER BY category ASC, id ASC
            """,
            (due_date.isoformat(), PENDING),
        ).fetchall()
        return [Task.from_row(row) for row in rows]

    def all_tasks(self) -> list[Task]:
        rows = self.connection.execute(
            """
            SELECT id, title, due_date, status, category, description, created_at, completed_at
            FROM tasks
            ORDER BY due_date ASC, status DESC, category ASC, id ASC
            """
        ).fetchall()
        return [Task.from_row(row) for row in rows]

    def all_for_date(self, due_date: date) -> list[Task]:
        rows = self.connection.execute(
            """
            SELECT id, title, due_date, status, category, description, created_at, completed_at
            FROM tasks
            WHERE due_date = ?
            ORDER BY status DESC, category ASC, id ASC
            """,
            (due_date.isoformat(),),
        ).fetchall()
        return [Task.from_row(row) for row in rows]

    def pending_before(self, due_date: date) -> list[Task]:
        rows = self.connection.execute(
            """
            SELECT id, title, due_date, status, category, description, created_at, completed_at
            FROM tasks
            WHERE due_date < ?
              AND status = ?
            ORDER BY due_date ASC, category ASC, id ASC
            """,
            (due_date.isoformat(), PENDING),
        ).fetchall()
        return [Task.from_row(row) for row in rows]

    def pending_from(self, start_date: date, limit: int = 3) -> list[Task]:
        rows = self.connection.execute(
            """
            SELECT id, title, due_date, status, category, description, created_at, completed_at
            FROM tasks
            WHERE due_date >= ?
              AND status = ?
            ORDER BY due_date ASC, category ASC, id ASC
            LIMIT ?
            """,
            (start_date.isoformat(), PENDING, limit),
        ).fetchall()
        return [Task.from_row(row) for row in rows]

    def between_dates(self, start_date: date, end_date: date) -> list[Task]:
        rows = self.connection.execute(
            """
            SELECT id, title, due_date, status, category, description, created_at, completed_at
            FROM tasks
            WHERE due_date BETWEEN ? AND ?
            ORDER BY due_date ASC, category ASC, id ASC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
        return [Task.from_row(row) for row in rows]

    def task_exists(self, title: str, due_date: date, category: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM tasks
            WHERE title = ?
              AND due_date = ?
              AND category = ?
            LIMIT 1
            """,
            (title.strip(), due_date.isoformat(), category.strip() or "General"),
        ).fetchone()
        return row is not None

    def mark_completed(self, task_id: int) -> Task:
        cursor = self.connection.execute(
            """
            UPDATE tasks
            SET status = ?,
                completed_at = COALESCE(completed_at, ?)
            WHERE id = ?
              AND status != ?
            """,
            (COMPLETED, utc_timestamp(), task_id, COMPLETED),
        )
        self.connection.commit()

        if cursor.rowcount == 0:
            return self.get_task(task_id)
        return self.get_task(task_id)

    def update_task(
        self,
        task_id: int,
        title: str,
        due_date: date,
        category: str,
        description: str,
        status: str,
    ) -> Task:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Task title cannot be empty.")
        if status not in {PENDING, COMPLETED}:
            raise ValueError("Task status must be Pending or Completed.")

        current = self.get_task(task_id)
        completed_at = current.completed_at
        if status == COMPLETED and completed_at is None:
            completed_at = utc_timestamp()
        if status == PENDING:
            completed_at = None

        self.connection.execute(
            """
            UPDATE tasks
            SET title = ?,
                due_date = ?,
                category = ?,
                description = ?,
                status = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (
                clean_title,
                due_date.isoformat(),
                category.strip() or "General",
                description.strip(),
                status,
                completed_at,
                task_id,
            ),
        )
        self.connection.commit()
        return self.get_task(task_id)

    def delete_task(self, task_id: int) -> None:
        cursor = self.connection.execute(
            """
            DELETE FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            raise LookupError(f"No task found with id {task_id}.")

    def stats_for_date(self, due_date: date) -> TaskStats:
        row = self.connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS completed
            FROM tasks
            WHERE due_date = ?
            """,
            (PENDING, COMPLETED, due_date.isoformat()),
        ).fetchone()
        return TaskStats(
            total=row["total"] or 0,
            pending=row["pending"] or 0,
            completed=row["completed"] or 0,
        )

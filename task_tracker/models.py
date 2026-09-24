from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from sqlite3 import Row


PENDING = "Pending"
COMPLETED = "Completed"


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    due_date: str
    status: str
    category: str
    description: str
    created_at: str
    completed_at: str | None = None

    @classmethod
    def from_row(cls, row: Row) -> "Task":
        return cls(
            id=row["id"],
            title=row["title"],
            due_date=row["due_date"],
            status=row["status"],
            category=row["category"],
            description=row["description"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )


@dataclass(frozen=True)
class TaskStats:
    total: int
    pending: int
    completed: int

    @property
    def completion_rate(self) -> int:
        if self.total == 0:
            return 0
        return round((self.completed / self.total) * 100)


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

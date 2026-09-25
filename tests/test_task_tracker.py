from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from task_tracker.database import connect
from task_tracker.models import COMPLETED, PENDING
from task_tracker.reminders import DailyReminderService
from task_tracker.repository import TaskRepository
from task_tracker.web import (
    notification_payload,
    page_scope,
    render_add_task_form,
    render_program_form,
    render_sidebar,
)


class MemoryNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, subject: str, message: str) -> None:
        self.messages.append((subject, message))


class TaskRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "tasks.db"
        self.connection = connect(db_path)
        self.repository = TaskRepository(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_add_task_starts_pending(self) -> None:
        task = self.repository.add_task("Draft project outline", date(2026, 9, 23))

        self.assertEqual(task.title, "Draft project outline")
        self.assertEqual(task.status, PENDING)
        self.assertEqual(task.due_date, "2026-09-23")

    def test_add_task_accepts_category_and_description(self) -> None:
        task = self.repository.add_task(
            "Build calculator",
            date(2026, 9, 20),
            category="Mini-project",
            description="Support addition, subtraction, multiplication, and division.",
        )

        self.assertEqual(task.category, "Mini-project")
        self.assertIn("addition", task.description)

    def test_pending_for_date_filters_completed_and_other_dates(self) -> None:
        pending = self.repository.add_task("Call client", date(2026, 9, 23))
        completed = self.repository.add_task("Send notes", date(2026, 9, 23))
        self.repository.add_task("Plan tomorrow", date(2026, 9, 24))
        self.repository.mark_completed(completed.id)

        tasks = self.repository.pending_for_date(date(2026, 9, 23))

        self.assertEqual([task.id for task in tasks], [pending.id])

    def test_pending_before_filters_completed_and_future_tasks(self) -> None:
        overdue = self.repository.add_task("Review loops", date(2026, 9, 20))
        completed = self.repository.add_task("Read variables", date(2026, 9, 21))
        self.repository.add_task("Practice functions", date(2026, 9, 24))
        self.repository.mark_completed(completed.id)

        tasks = self.repository.pending_before(date(2026, 9, 23))

        self.assertEqual([task.id for task in tasks], [overdue.id])

    def test_pending_from_returns_upcoming_pending_tasks_with_limit(self) -> None:
        first = self.repository.add_task("Practice conditions", date(2026, 9, 23))
        completed = self.repository.add_task("Finish calculator", date(2026, 9, 24))
        second = self.repository.add_task("Debug errors", date(2026, 9, 24))
        self.repository.add_task("Plan next week", date(2026, 9, 25))
        self.repository.mark_completed(completed.id)

        tasks = self.repository.pending_from(date(2026, 9, 23), limit=2)

        self.assertEqual([task.id for task in tasks], [first.id, second.id])

    def test_notification_payload_counts_overdue_and_due_today(self) -> None:
        self.repository.add_task("Review missed lesson", date(2026, 9, 22))
        self.repository.add_task("Practice functions", date(2026, 9, 23))
        completed = self.repository.add_task("Finish notes", date(2026, 9, 23))
        self.repository.mark_completed(completed.id)

        payload = notification_payload(self.repository, date(2026, 9, 23))

        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["overdue"], 1)
        self.assertEqual(payload["due_today"], 1)

    def test_add_task_form_allows_any_calendar_date(self) -> None:
        html = render_add_task_form(date(2026, 9, 14), "day")

        self.assertIn('type="date"', html)
        self.assertIn(f'value="{date.today().isoformat()}"', html)
        self.assertNotIn(' min="', html)
        self.assertNotIn(' max="', html)

    def test_program_form_allows_any_calendar_date(self) -> None:
        html = render_program_form(date(2026, 9, 14), "week")

        self.assertIn('id="program_due_date"', html)
        self.assertNotIn(' min="', html)
        self.assertNotIn(' max="', html)
        self.assertNotIn('name="return_date"', html)

    def test_task_and_plan_pages_have_meaningful_default_ranges(self) -> None:
        self.assertEqual(page_scope("tasks", None), "month")
        self.assertEqual(page_scope("program", None), "week")
        self.assertEqual(page_scope("tasks", "day"), "day")

    def test_sidebar_navigation_does_not_carry_an_old_viewing_date(self) -> None:
        html = render_sidebar("tasks", date(2026, 9, 14))

        self.assertIn('href="/dashboard"', html)
        self.assertIn('href="/tasks"', html)
        self.assertNotIn("2026-09-14", html)

    def test_mark_completed_updates_status(self) -> None:
        task = self.repository.add_task("Clean task list", date(2026, 9, 23))

        completed = self.repository.mark_completed(task.id)

        self.assertEqual(completed.status, COMPLETED)
        self.assertIsNotNone(completed.completed_at)

    def test_update_task_changes_program_fields(self) -> None:
        task = self.repository.add_task("Draft", date(2026, 9, 14))

        updated = self.repository.update_task(
            task.id,
            "Practice loops",
            date(2026, 9, 16),
            "Learn",
            "Use for loops and while loops.",
            COMPLETED,
        )

        self.assertEqual(updated.title, "Practice loops")
        self.assertEqual(updated.due_date, "2026-09-16")
        self.assertEqual(updated.category, "Learn")
        self.assertEqual(updated.status, COMPLETED)
        self.assertIsNotNone(updated.completed_at)

    def test_delete_task_removes_it(self) -> None:
        task = self.repository.add_task("Temporary item", date(2026, 9, 14))

        self.repository.delete_task(task.id)

        with self.assertRaises(LookupError):
            self.repository.get_task(task.id)

    def test_archive_deleted_task_can_be_restored(self) -> None:
        task = self.repository.add_task(
            "Restore me",
            date(2026, 9, 14),
            category="Learn",
            description="Accidental delete.",
        )

        deleted_id = self.repository.archive_deleted_task(task.id)

        with self.assertRaises(LookupError):
            self.repository.get_task(task.id)

        restored = self.repository.restore_deleted_task(deleted_id)

        self.assertEqual(restored.id, task.id)
        self.assertEqual(restored.title, "Restore me")
        self.assertEqual(restored.category, "Learn")
        self.assertEqual(restored.description, "Accidental delete.")

    def test_reminder_service_sends_pending_digest(self) -> None:
        self.repository.add_task("Morning review", date(2026, 9, 23))
        notifier = MemoryNotifier()
        service = DailyReminderService(self.repository, notifier)

        count = service.send_for_date(date(2026, 9, 23))

        self.assertEqual(count, 1)
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("Morning review", notifier.messages[0][1])


if __name__ == "__main__":
    unittest.main()

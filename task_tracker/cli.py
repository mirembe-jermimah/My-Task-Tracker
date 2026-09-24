from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Iterable

from .database import DEFAULT_DB_PATH, connect
from .models import Task, TaskStats
from .programs import seed_week_one_program
from .reminders import DailyReminderService, build_notifier
from .repository import TaskRepository
from .web import run_server


def parse_date(value: str) -> date:
    if value.lower() == "today":
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"'{value}' is not a valid date. Use YYYY-MM-DD or today."
        ) from exc


def resolve_target_date(args: argparse.Namespace) -> date:
    if getattr(args, "today", False):
        return date.today()
    if getattr(args, "date", None):
        return args.date
    return date.today()


def format_tasks(tasks: Iterable[Task]) -> str:
    task_list = list(tasks)
    if not task_list:
        return "No pending tasks found."

    rows = [("ID", "Due Date", "Status", "Category", "Title")]
    rows.extend(
        (str(task.id), task.due_date, task.status, task.category, task.title)
        for task in task_list
    )
    widths = [max(len(row[index]) for row in rows) for index in range(5)]
    lines = []
    for row_index, row in enumerate(rows):
        line = "  ".join(
            value.ljust(widths[index]) for index, value in enumerate(row)
        )
        lines.append(line)
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)


def progress_bar(stats: TaskStats, width: int = 24) -> str:
    if stats.total == 0:
        return "." * width
    filled = round((stats.completed / stats.total) * width)
    return "#" * filled + "." * (width - filled)


def print_dashboard(repository: TaskRepository, target_date: date) -> None:
    stats = repository.stats_for_date(target_date)
    pending_tasks = repository.pending_for_date(target_date)

    print("My Task Tracker")
    print("=================")
    print(f"Date:       {target_date.isoformat()}")
    print(f"Pending:    {stats.pending}")
    print(f"Completed:  {stats.completed}")
    print(f"Progress:   {progress_bar(stats)} {stats.completion_rate}%")
    print()
    print("Today's Schedule" if target_date == date.today() else "Schedule")
    print(format_tasks(pending_tasks))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="my-task-tracker",
        description="Simple SQLite task and reminder tracker.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path. Defaults to tasks.db in this project.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a pending task.")
    add_parser.add_argument("title", help="Task title.")
    add_parser.add_argument(
        "--due",
        required=True,
        type=parse_date,
        help="Due date as YYYY-MM-DD or today.",
    )
    add_parser.add_argument(
        "--category",
        default="General",
        help="Task category, such as Learn, Exercise, Mini-project, or Target.",
    )
    add_parser.add_argument(
        "--description",
        default="",
        help="Optional longer task description.",
    )

    list_parser = subparsers.add_parser("list", help="List pending tasks.")
    date_group = list_parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date",
        type=parse_date,
        help="Due date as YYYY-MM-DD or today. Defaults to today.",
    )
    date_group.add_argument(
        "--today",
        action="store_true",
        help="List pending tasks due today.",
    )

    subparsers.add_parser("today", help="List pending tasks due today.")

    complete_parser = subparsers.add_parser(
        "complete",
        help="Mark a task as completed.",
    )
    complete_parser.add_argument("task_id", type=int, help="Task ID to complete.")

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Show a clean daily dashboard.",
    )
    dashboard_group = dashboard_parser.add_mutually_exclusive_group()
    dashboard_group.add_argument(
        "--date",
        type=parse_date,
        help="Dashboard date as YYYY-MM-DD or today. Defaults to today.",
    )
    dashboard_group.add_argument(
        "--today",
        action="store_true",
        help="Show today's dashboard.",
    )

    remind_parser = subparsers.add_parser(
        "remind",
        help="Send a daily reminder digest.",
    )
    remind_group = remind_parser.add_mutually_exclusive_group()
    remind_group.add_argument(
        "--date",
        type=parse_date,
        help="Reminder date as YYYY-MM-DD or today. Defaults to today.",
    )
    remind_group.add_argument(
        "--today",
        action="store_true",
        help="Send reminders for today.",
    )
    remind_parser.add_argument(
        "--channel",
        choices=("console", "email", "telegram"),
        default="console",
        help="Notification channel. Defaults to console.",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run the visual web dashboard.",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for the local dashboard.",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for the local dashboard.",
    )

    seed_parser = subparsers.add_parser(
        "seed-week1",
        help='Load Week 1: "Think like a programmer" into the database.',
    )
    seed_parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Year for September 14-20. Defaults to the current year.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        run_server(args.host, args.port, args.db)
        return 0

    with connect(args.db) as connection:
        repository = TaskRepository(connection)

        if args.command == "add":
            task = repository.add_task(
                args.title,
                args.due,
                category=args.category,
                description=args.description,
            )
            print(
                f"Added task {task.id}: {task.title} "
                f"(due {task.due_date}, status {task.status})"
            )
            return 0

        if args.command == "seed-week1":
            count = seed_week_one_program(repository, args.year)
            print(
                f"Loaded {count} new Week 1 task(s) "
                f"for September 14-20, {args.year}."
            )
            return 0

        if args.command in {"list", "today"}:
            target_date = date.today() if args.command == "today" else resolve_target_date(args)
            print(f"Pending tasks for {target_date.isoformat()}")
            print(format_tasks(repository.pending_for_date(target_date)))
            return 0

        if args.command == "complete":
            task = repository.mark_completed(args.task_id)
            print(f"Task {task.id} is now {task.status}: {task.title}")
            return 0

        if args.command == "dashboard":
            print_dashboard(repository, resolve_target_date(args))
            return 0

        if args.command == "remind":
            notifier = build_notifier(args.channel)
            service = DailyReminderService(repository, notifier)
            count = service.send_for_date(resolve_target_date(args))
            print(f"Reminder channel '{args.channel}' processed {count} pending task(s).")
            return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2

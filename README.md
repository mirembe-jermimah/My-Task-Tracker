# My Task Tracker

A small Python and SQLite task tracker inspired by the clean dashboard reference in
the `image` folder: focused daily work, simple task cards, pending work, and a
reminder flow that can later run on a schedule.

## Features

- Add tasks with a title and due date.
- New tasks start with the `Pending` status.
- Organize tasks with categories and longer descriptions.
- List pending tasks for today or for a specific date.
- Edit, complete, delete, and undo accidental deletes for tasks or plan items.
- View a clean browser app with flexible day, week, month, and year planning.
- Navigate independent Dashboard, Focus, Tasks, Plans, Notifications, and Reminders pages.
- Use the Dashboard for a concise overview of totals, overdue work, and weekly progress.
- Use Focus for overdue items, selected-day tasks, and the next upcoming work.
- Use Notifications for live due-today and overdue alerts.
- Use Reminders for reminder message previews and future reminder delivery setup.
- Toggle dark mode in the browser dashboard.
- Generate/send a daily reminder digest through a pluggable notification layer.
- Uses only the Python standard library.

## Quick Start

```powershell
python main.py add "Review weekly plan" --due 2026-09-23
python main.py add "Send invoice reminder" --due 2026-09-23
python main.py today
python main.py complete 1
python main.py dashboard
python main.py seed-week1 --year 2026
python main.py serve
```

The SQLite database is created automatically as `tasks.db` in this folder. You can
override it with `--db`:

```powershell
python main.py --db .\data\personal-tasks.db list --date 2026-09-23
```

## Commands

```text
add TITLE --due YYYY-MM-DD
list [--date YYYY-MM-DD | --today]
today
complete TASK_ID
dashboard [--date YYYY-MM-DD | --today]
remind [--date YYYY-MM-DD | --today] [--channel console|email|telegram]
serve [--host 127.0.0.1] [--port 8765]
seed-week1 [--year YYYY]
```

## Visual App

Run the browser dashboard:

```powershell
python main.py serve
```

Then open:

```text
http://127.0.0.1:8765/
```

The app uses the same SQLite database as the CLI, with a scrollable left sidebar,
task cards, add forms, edit/delete/undo actions, overview cards, live
notifications, reminder previews, and dark mode. It also supports categories,
descriptions, and an editable planning section that can show a day, week, month,
or year.

Load the Week 1 Python learning program:

```powershell
python main.py seed-week1 --year 2026
```

Then open the task manager. It starts with the current month, and you can switch
between Day, Week, Month, and Year:

```text
http://127.0.0.1:8765/tasks
```

Inside `Plans`, choose Day, Week, Month, or Year, then add your own items with a
title, category, date, and description. Every task and plan item has edit,
complete, and delete controls.

## Reminder Architecture

The reminder service lives in `task_tracker/reminders.py`.

- `DailyReminderService` loads unfinished tasks for a date.
- `ReminderMessageBuilder` turns those tasks into a clean daily digest.
- Notification channels implement one method: `send(subject, message)`.
- `ConsoleNotifier` works immediately.
- `EmailNotifier` and `TelegramNotifier` are ready for scheduled jobs once
  environment variables are configured.

For a daily console reminder:

```powershell
python main.py remind --today --channel console
```

For SMTP email reminders, set:

```powershell
$env:TASK_REMINDER_SMTP_HOST="smtp.example.com"
$env:TASK_REMINDER_SMTP_PORT="587"
$env:TASK_REMINDER_SMTP_USERNAME="your-user"
$env:TASK_REMINDER_SMTP_PASSWORD="your-password"
$env:TASK_REMINDER_EMAIL_FROM="tasks@example.com"
$env:TASK_REMINDER_EMAIL_TO="you@example.com"
python main.py remind --today --channel email
```

For Telegram reminders, set:

```powershell
$env:TASK_REMINDER_TELEGRAM_TOKEN="123456:bot-token"
$env:TASK_REMINDER_TELEGRAM_CHAT_ID="123456789"
python main.py remind --today --channel telegram
```

You can connect the reminder command to Windows Task Scheduler, cron, or any
automation tool that can run a Python command each morning.

## Tests

```powershell
python -m unittest discover
```

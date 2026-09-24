from __future__ import annotations

import json
from datetime import date, timedelta
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from .database import connect
from .models import COMPLETED, PENDING, Task, TaskStats
from .reminders import ReminderMessageBuilder
from .repository import TaskRepository


STATIC_DIR = Path(__file__).resolve().parent / "static"
PAGES = {"dashboard", "focus", "tasks", "program", "reminders"}
PLAN_SCOPES = ("day", "week", "month", "year")


def parse_iso_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.today()


def icon(name: str) -> str:
    icons = {
        "bell": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
        "calendar": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 2v4M16 2v4M3 10h18"/><rect x="3" y="4" width="18" height="18" rx="2"/></svg>',
        "chart": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
        "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>',
        "edit": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
        "list": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/></svg>',
        "menu": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
        "moon": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 7.5A9 9 0 1 1 12 3Z"/></svg>',
        "plus": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
        "program": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5Z"/></svg>',
        "trash": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>',
    }
    return icons.get(name, "")


def format_short_date(day: date) -> str:
    return day.strftime("%b %d").replace(" 0", " ")


def safe_date_label(day: date) -> str:
    return day.strftime("%b %d, %Y").replace(" 0", " ")


def status_class(task: Task) -> str:
    return "is-complete" if task.status == COMPLETED else "is-pending"


def page_path(
    page: str,
    selected_date: date | None = None,
    fragment: str = "",
    scope: str | None = None,
) -> str:
    path = f"/{page}" if page != "dashboard" else "/dashboard"
    params = {}
    if selected_date:
        params["date"] = selected_date.isoformat()
    if scope and scope != "day" and page in {"tasks", "program"}:
        params["scope"] = scope
    if params:
        path = f"{path}?{urlencode(params)}"
    if fragment:
        path = f"{path}#{fragment}"
    return path


def week_bounds(selected_date: date) -> tuple[date, date]:
    week_start = selected_date - timedelta(days=selected_date.weekday())
    return week_start, week_start + timedelta(days=6)


def normalize_scope(value: str | None) -> str:
    return value if value in PLAN_SCOPES else "day"


def range_bounds(selected_date: date, scope: str) -> tuple[date, date]:
    if scope == "week":
        return week_bounds(selected_date)
    if scope == "month":
        start = selected_date.replace(day=1)
        if selected_date.month == 12:
            next_month = date(selected_date.year + 1, 1, 1)
        else:
            next_month = date(selected_date.year, selected_date.month + 1, 1)
        return start, next_month - timedelta(days=1)
    if scope == "year":
        return date(selected_date.year, 1, 1), date(selected_date.year, 12, 31)
    return selected_date, selected_date


def range_label(selected_date: date, scope: str) -> str:
    start, end = range_bounds(selected_date, scope)
    if scope == "day":
        return safe_date_label(selected_date)
    if scope == "month":
        return selected_date.strftime("%B %Y")
    if scope == "year":
        return str(selected_date.year)
    return f"{format_short_date(start)} - {format_short_date(end)}"


def stats_for_tasks(tasks: list[Task]) -> TaskStats:
    pending = sum(1 for task in tasks if task.status == PENDING)
    completed = sum(1 for task in tasks if task.status == COMPLETED)
    return TaskStats(total=len(tasks), pending=pending, completed=completed)


def notification_payload(repository: TaskRepository, selected_date: date) -> dict[str, int | str]:
    due_today = repository.pending_for_date(selected_date)
    overdue = repository.pending_before(selected_date)
    count = len(due_today) + len(overdue)
    if count == 0:
        summary = "No pending notifications."
    elif overdue and due_today:
        summary = f"{len(overdue)} overdue and {len(due_today)} due today."
    elif overdue:
        summary = f"{len(overdue)} overdue task(s)."
    else:
        summary = f"{len(due_today)} task(s) due today."
    return {
        "date": selected_date.isoformat(),
        "count": count,
        "due_today": len(due_today),
        "overdue": len(overdue),
        "summary": summary,
    }


def render_category_options(selected_category: str) -> str:
    categories = ["General", "Learn", "Exercise", "Mini-project", "Target"]
    return "\n".join(
        f'<option value="{escape(category)}"{" selected" if category == selected_category else ""}>{escape(category)}</option>'
        for category in categories
    )


def render_status_options(selected_status: str) -> str:
    return "\n".join(
        f'<option value="{status}"{" selected" if status == selected_status else ""}>{status}</option>'
        for status in (PENDING, COMPLETED)
    )


def render_notice(query: dict[str, list[str]]) -> str:
    notices = query.get("notice", [])
    if not notices:
        return ""
    return f'<div class="notice">{escape(notices[0])}</div>'


def render_progress(stats: TaskStats) -> str:
    value = stats.completion_rate
    return f"""
        <div class="progress-track" aria-label="Completion progress">
            <span style="width: {value}%"></span>
        </div>
        <strong>{value}%</strong>
    """


def page_heading(page: str) -> str:
    headings = {
        "dashboard": "Dashboard",
        "focus": "Focus on what matters now.",
        "tasks": "Manage tasks.",
        "program": "Plan by day, week, month, or year.",
        "reminders": "Review reminder notifications.",
    }
    return headings.get(page, "My Task Tracker")


def render_sidebar(active_page: str, selected_date: date) -> str:
    nav_items = [
        ("dashboard", "Dashboard"),
        ("focus", "Focus"),
        ("tasks", "Tasks"),
        ("program", "Plans"),
        ("reminders", "Reminders"),
    ]
    links = []
    for page, label in nav_items:
        active = "active" if active_page == page else ""
        href = page_path(page, selected_date)
        links.append(
            f'<a class="{active}" href="{href}">{escape(label)}</a>'
        )

    return f"""
        <aside class="sidebar" aria-label="Primary">
            <a class="brand" href="{page_path("dashboard", selected_date)}">
                <span class="brand-mark" aria-hidden="true"></span>
                <strong>My Task Tracker</strong>
            </a>
            <nav>{"".join(links)}</nav>
        </aside>
    """


def render_notification_link(selected_date: date, notification_count: int) -> str:
    badge_class = "notification-badge"
    if notification_count == 0:
        badge_class = f"{badge_class} is-empty"
    label = f"Notifications, {notification_count} pending"
    return f"""
        <a class="top-icon notification-link" href="{page_path("reminders", selected_date)}" title="Notifications" aria-label="{escape(label)}" data-notification-link>
            {icon("bell")}
            <span class="{badge_class}" data-notification-count data-count="{notification_count}">{notification_count}</span>
        </a>
    """


def render_topbar(
    active_page: str,
    selected_date: date,
    scope: str,
    notification_count: int,
) -> str:
    action_page = active_page
    scope_input = ""
    if active_page in {"tasks", "program"}:
        scope_input = f'<input type="hidden" name="scope" value="{escape(scope)}">'
    return f"""
        <header class="topbar">
            <div class="topbar-title">
                <button class="top-icon menu-toggle" id="menu-toggle" type="button" title="Toggle menu" aria-label="Toggle menu" aria-expanded="true">{icon("menu")}</button>
                <div>
                    <p>Hi, welcome back</p>
                    <h1>{page_heading(active_page)}</h1>
                </div>
            </div>
            <div class="topbar-actions">
                <form class="date-filter" method="get" action="/{action_page}">
                    <label for="date">Date</label>
                    <input id="date" name="date" type="date" value="{selected_date.isoformat()}">
                    {scope_input}
                    <button type="submit">{icon("calendar")}View</button>
                </form>
                {render_notification_link(selected_date, notification_count)}
                <button class="top-icon" id="theme-toggle" type="button" title="Toggle dark mode" aria-label="Toggle dark mode">{icon("moon")}</button>
            </div>
        </header>
    """


def render_shell(
    active_page: str,
    selected_date: date,
    scope: str,
    query: dict[str, list[str]],
    content: str,
    notification_count: int,
) -> bytes:
    html = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>My Task Tracker</title>
    <script>
        document.documentElement.dataset.theme = localStorage.getItem("my-task-tracker-theme") || "light";
    </script>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
    <script>
        if (localStorage.getItem("my-task-tracker-sidebar") === "collapsed") {{
            document.body.classList.add("sidebar-collapsed");
        }}
    </script>
    <div class="app-shell">
        {render_sidebar(active_page, selected_date)}
        <button class="sidebar-overlay" id="sidebar-overlay" type="button" aria-label="Close menu"></button>
        <main class="main-panel">
            {render_notice(query)}
            {render_topbar(active_page, selected_date, scope, notification_count)}
            {content}
        </main>
    </div>
    <script>
        const themeButton = document.getElementById("theme-toggle");
        const menuButton = document.getElementById("menu-toggle");
        const sidebarOverlay = document.getElementById("sidebar-overlay");
        const notificationLink = document.querySelector("[data-notification-link]");
        const notificationBadge = document.querySelector("[data-notification-count]");
        const dateInput = document.getElementById("date");
        const mobileMenu = window.matchMedia("(max-width: 900px)");

        const updateMenuButton = () => {{
            const expanded = mobileMenu.matches
                ? document.body.classList.contains("sidebar-open")
                : !document.body.classList.contains("sidebar-collapsed");
            menuButton.setAttribute("aria-expanded", String(expanded));
        }};

        const closeMobileMenu = () => {{
            document.body.classList.remove("sidebar-open");
            updateMenuButton();
        }};

        themeButton?.addEventListener("click", () => {{
            const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
            document.documentElement.dataset.theme = nextTheme;
            localStorage.setItem("my-task-tracker-theme", nextTheme);
        }});

        menuButton?.addEventListener("click", () => {{
            if (mobileMenu.matches) {{
                document.body.classList.toggle("sidebar-open");
            }} else {{
                document.body.classList.toggle("sidebar-collapsed");
                const nextState = document.body.classList.contains("sidebar-collapsed") ? "collapsed" : "open";
                localStorage.setItem("my-task-tracker-sidebar", nextState);
            }}
            updateMenuButton();
        }});

        sidebarOverlay?.addEventListener("click", closeMobileMenu);
        document.querySelectorAll(".sidebar a").forEach((link) => {{
            link.addEventListener("click", closeMobileMenu);
        }});
        mobileMenu.addEventListener("change", () => {{
            document.body.classList.remove("sidebar-open");
            updateMenuButton();
        }});
        updateMenuButton();

        let lastNotificationCount = Number(notificationBadge?.dataset.count || 0);

        const updateNotifications = (payload) => {{
            if (!notificationBadge || !notificationLink) {{
                return;
            }}
            const count = Number(payload.count || 0);
            notificationBadge.textContent = String(count);
            notificationBadge.dataset.count = String(count);
            notificationBadge.classList.toggle("is-empty", count === 0);
            notificationLink.setAttribute("aria-label", `Notifications, ${{count}} pending`);
            notificationLink.setAttribute("title", payload.summary || "Notifications");
            document.title = count > 0 ? `(${{count}}) My Task Tracker` : "My Task Tracker";
            if (
                count > lastNotificationCount &&
                "Notification" in window &&
                Notification.permission === "granted"
            ) {{
                new Notification("My Task Tracker", {{ body: payload.summary || "You have pending tasks." }});
            }}
            lastNotificationCount = count;
        }};

        const refreshNotifications = async () => {{
            if (!dateInput) {{
                return;
            }}
            const params = new URLSearchParams({{ date: dateInput.value }});
            try {{
                const response = await fetch(`/api/notifications?${{params.toString()}}`, {{
                    headers: {{ "Accept": "application/json" }},
                    cache: "no-store"
                }});
                if (response.ok) {{
                    updateNotifications(await response.json());
                }}
            }} catch (error) {{
                console.warn("Notification refresh failed", error);
            }}
        }};

        refreshNotifications();
        setInterval(refreshNotifications, 15000);
        document.addEventListener("visibilitychange", () => {{
            if (!document.hidden) {{
                refreshNotifications();
            }}
        }});
    </script>
</body>
</html>
"""
    return html.encode("utf-8")


def render_task_description(task: Task) -> str:
    if not task.description:
        return ""
    return f'<p class="task-description">{escape(task.description)}</p>'


def render_task_actions(
    task: Task,
    selected_date: date,
    return_page: str,
    scope: str,
) -> str:
    hidden = f"""
        <input type="hidden" name="date" value="{selected_date.isoformat()}">
        <input type="hidden" name="return_page" value="{escape(return_page)}">
        <input type="hidden" name="scope" value="{escape(scope)}">
    """
    complete = ""
    if task.status != COMPLETED:
        complete = f"""
            <form method="post" action="/tasks/{task.id}/complete">
                {hidden}
                <button class="icon-button success" type="submit" title="Complete task" aria-label="Complete {escape(task.title)}">{icon("check")}</button>
            </form>
        """
    return f"""
        <div class="task-actions">
            {complete}
            <a class="icon-button" href="/tasks/{task.id}/edit?date={selected_date.isoformat()}&return_page={escape(return_page)}&scope={escape(scope)}" title="Edit task" aria-label="Edit {escape(task.title)}">{icon("edit")}</a>
            <form method="post" action="/tasks/{task.id}/delete">
                {hidden}
                <button class="icon-button danger" type="submit" title="Delete task" aria-label="Delete {escape(task.title)}" onclick="return confirm('Delete this item?')">{icon("trash")}</button>
            </form>
        </div>
    """


def render_task_card(
    task: Task,
    selected_date: date,
    return_page: str,
    scope: str,
) -> str:
    return f"""
        <article class="task-card {status_class(task)}">
            <div>
                <div class="task-meta">
                    <span class="task-date">{escape(safe_date_label(date.fromisoformat(task.due_date)))}</span>
                    <span class="category-badge">{escape(task.category)}</span>
                </div>
                <h3>{escape(task.title)}</h3>
                <p>{escape(task.status)}</p>
                {render_task_description(task)}
            </div>
            <div class="task-card-footer">
                <span class="status-dot" aria-hidden="true"></span>
                {render_task_actions(task, selected_date, return_page, scope)}
            </div>
        </article>
    """


def render_task_grid(
    tasks: list[Task],
    selected_date: date,
    return_page: str,
    scope: str,
    empty_title: str = "No tasks yet",
    empty_copy: str = "Add a task to build the schedule.",
) -> str:
    if not tasks:
        return f"""
            <section class="empty-state">
                <h3>{escape(empty_title)}</h3>
                <p>{escape(empty_copy)}</p>
            </section>
        """
    return "\n".join(
        render_task_card(task, selected_date, return_page, scope) for task in tasks
    )


def render_stats_grid(stats: TaskStats) -> str:
    return f"""
        <section class="stats-grid" aria-label="Daily task stats">
            <article><span>Pending</span><strong>{stats.pending}</strong><p>Unfinished tasks</p></article>
            <article><span>Completed</span><strong>{stats.completed}</strong><p>Finished items</p></article>
            <article><span>Progress</span><div class="stat-progress">{render_progress(stats)}</div></article>
        </section>
    """


def render_metric_grid(cards: list[tuple[str, int | str, str]]) -> str:
    items = []
    for label, value, caption in cards:
        items.append(
            f"""
            <article>
                <span>{escape(label)}</span>
                <strong>{escape(str(value))}</strong>
                <p>{escape(caption)}</p>
            </article>
            """
        )
    return f'<section class="overview-grid" aria-label="Tracker overview">{"".join(items)}</section>'


def render_compact_task_list(
    tasks: list[Task],
    selected_date: date,
    return_page: str,
    scope: str,
    empty_title: str,
    empty_copy: str,
) -> str:
    if not tasks:
        return f"""
            <section class="empty-state compact-empty">
                <h3>{escape(empty_title)}</h3>
                <p>{escape(empty_copy)}</p>
            </section>
        """

    rows = []
    for task in tasks:
        task_date = date.fromisoformat(task.due_date)
        rows.append(
            f"""
            <article class="compact-task {status_class(task)}">
                <div>
                    <span>{escape(format_short_date(task_date))}</span>
                    <strong>{escape(task.title)}</strong>
                    <p>{escape(task.category)}</p>
                </div>
                {render_task_actions(task, selected_date, return_page, scope)}
            </article>
            """
        )
    return f'<div class="compact-list">{"".join(rows)}</div>'


def render_range_summary(repository: TaskRepository, selected_date: date) -> str:
    labels = {
        "day": "Day",
        "week": "Week",
        "month": "Month",
        "year": "Year",
    }
    cards = []
    for scope in PLAN_SCOPES:
        range_start, range_end = range_bounds(selected_date, scope)
        tasks = repository.between_dates(range_start, range_end)
        stats = stats_for_tasks(tasks)
        cards.append(
            f"""
            <a class="range-card" href="{page_path("tasks", selected_date, scope=scope)}">
                <span>{labels[scope]}</span>
                <strong>{stats.pending}</strong>
                <p>{stats.completed} completed &middot; {stats.completion_rate}% done</p>
            </a>
            """
        )
    return f'<div class="range-summary-grid">{"".join(cards)}</div>'


def render_quick_actions(selected_date: date) -> str:
    return f"""
        <div class="quick-actions">
            <a class="secondary-button" href="{page_path("tasks", selected_date)}">{icon("plus")}Add Task</a>
            <a class="secondary-button" href="{page_path("program", selected_date, scope="week")}">{icon("program")}Add Plan Item</a>
            <a class="secondary-button" href="{page_path("reminders", selected_date)}">{icon("bell")}View Reminders</a>
        </div>
    """


def render_scope_switch(page: str, selected_date: date, active_scope: str) -> str:
    labels = {
        "day": "Day",
        "week": "Week",
        "month": "Month",
        "year": "Year",
    }
    links = []
    for scope in PLAN_SCOPES:
        active = "active" if scope == active_scope else ""
        href = page_path(page, selected_date, scope=scope)
        links.append(f'<a class="{active}" href="{href}">{labels[scope]}</a>')
    return f"""
        <div class="scope-switch" aria-label="Plan range">
            {"".join(links)}
        </div>
    """


def render_add_task_form(selected_date: date, scope: str) -> str:
    range_start, range_end = range_bounds(selected_date, scope)
    return f"""
        <form class="form-panel" method="post" action="/tasks">
            <input type="hidden" name="source" value="task">
            <input type="hidden" name="return_page" value="tasks">
            <input type="hidden" name="scope" value="{escape(scope)}">
            <div class="section-title"><div><p>New task</p><h2>Add Task</h2></div></div>
            <label for="title">Title</label>
            <input id="title" name="title" type="text" required maxlength="120">
            <label for="category">Category</label>
            <select id="category" name="category">{render_category_options("General")}</select>
            <label for="due_date">Due date</label>
            <input id="due_date" name="due_date" type="date" value="{selected_date.isoformat()}" min="{range_start.isoformat()}" max="{range_end.isoformat()}" required>
            <label for="description">Description</label>
            <textarea id="description" name="description" rows="4" maxlength="500"></textarea>
            <button type="submit">{icon("plus")}Add Task</button>
        </form>
    """


def render_program_form(selected_date: date, scope: str) -> str:
    range_start, range_end = range_bounds(selected_date, scope)
    return f"""
        <form class="program-editor" method="post" action="/tasks">
            <input type="hidden" name="source" value="program">
            <input type="hidden" name="return_page" value="program">
            <input type="hidden" name="return_date" value="{selected_date.isoformat()}">
            <input type="hidden" name="scope" value="{escape(scope)}">
            <div class="program-editor-grid">
                <label for="program_title"><span>Title</span><input id="program_title" name="title" type="text" required maxlength="120"></label>
                <label for="program_category"><span>Category</span><select id="program_category" name="category">{render_category_options("Learn")}</select></label>
                <label for="program_due_date"><span>Date</span><input id="program_due_date" name="due_date" type="date" value="{selected_date.isoformat()}" min="{range_start.isoformat()}" max="{range_end.isoformat()}" required></label>
                <label class="program-description-field" for="program_description"><span>Description</span><textarea id="program_description" name="description" rows="3" maxlength="500"></textarea></label>
                <button type="submit">{icon("plus")}Add Plan Item</button>
            </div>
        </form>
    """


def render_program_rows(tasks: list[Task], selected_date: date, scope: str) -> str:
    if not tasks:
        return """
            <section class="empty-state">
                <h3>No plan items yet</h3>
                <p>Add the first item using the fields above.</p>
            </section>
        """

    rows = []
    for task in tasks:
        rows.append(
            f"""
            <article class="program-row {status_class(task)}">
                <time>{escape(format_short_date(date.fromisoformat(task.due_date)))}</time>
                <span class="category-badge">{escape(task.category)}</span>
                <div>
                    <strong>{escape(task.title)}</strong>
                    {render_task_description(task)}
                </div>
                {render_task_actions(task, selected_date, "program", scope)}
            </article>
            """
        )
    return f'<div class="program-list">{"".join(rows)}</div>'


def render_chart(repository: TaskRepository, selected_date: date) -> str:
    start = selected_date - timedelta(days=3)
    days = [start + timedelta(days=offset) for offset in range(7)]
    highest = max((repository.stats_for_date(day).total for day in days), default=1) or 1
    bars = []
    for day in days:
        stats = repository.stats_for_date(day)
        pending_height = max(8, round((stats.pending / highest) * 112)) if stats.pending else 8
        completed_height = max(8, round((stats.completed / highest) * 112)) if stats.completed else 8
        bars.append(
            f"""
            <div class="chart-day">
                <div class="bar-stack" title="{safe_date_label(day)}">
                    <span class="bar-complete" style="height:{completed_height}px"></span>
                    <span class="bar-pending" style="height:{pending_height}px"></span>
                </div>
                <small>{day.strftime("%a")}</small>
            </div>
            """
        )
    return f'<div class="chart">{"".join(bars)}</div>'


def render_reminder_preview(tasks: list[Task], selected_date: date) -> str:
    subject, message = ReminderMessageBuilder().build(
        [task for task in tasks if task.status == PENDING],
        selected_date,
    )
    return f"""
        <div class="reminder-preview">
            <div><span>{icon("bell")}</span><strong>{escape(subject)}</strong></div>
            <pre>{escape(message)}</pre>
        </div>
    """


def render_dashboard_page(repository: TaskRepository, selected_date: date) -> str:
    all_tasks = repository.all_tasks()
    due_today = repository.pending_for_date(selected_date)
    all_stats = stats_for_tasks(all_tasks)
    overdue_tasks = repository.pending_before(selected_date)
    upcoming_candidates = repository.pending_from(selected_date, 8)
    upcoming_tasks = [
        task for task in upcoming_candidates if date.fromisoformat(task.due_date) > selected_date
    ][:3]
    week_start, week_end = week_bounds(selected_date)
    week_stats = stats_for_tasks(repository.between_dates(week_start, week_end))
    attention_tasks = (overdue_tasks + due_today)[:3]
    payload = notification_payload(repository, selected_date)
    return f"""
        <section class="dashboard-intro">
            <div>
                <p>{escape(safe_date_label(selected_date))}</p>
                <h2>Professional overview</h2>
            </div>
            <a class="secondary-button" href="{page_path("focus", selected_date)}">{icon("list")}Open Focus</a>
        </section>
        {render_metric_grid([
            ("Pending", all_stats.pending, "Open tasks in your tracker"),
            ("Overdue", len(overdue_tasks), "Pending before this date"),
            ("Due Today", len(due_today), "Needs attention now"),
            ("Completed", all_stats.completed, "Finished tasks overall"),
        ])}
        <section class="dashboard-clean-grid">
            <div class="panel">
                <div class="section-title"><div><p>Priority</p><h2>Needs Attention</h2></div></div>
                {render_compact_task_list(attention_tasks, selected_date, "dashboard", "day", "Nothing urgent", "No overdue or due-today tasks.")}
            </div>
            <div class="panel">
                <div class="section-title"><div><p>Next</p><h2>Upcoming</h2></div></div>
                {render_compact_task_list(upcoming_tasks, selected_date, "dashboard", "day", "Nothing pending ahead", "Your upcoming queue is clear.")}
            </div>
            <aside class="panel dashboard-status-panel">
                <div class="section-title"><div><p>Status</p><h2>Reminder</h2></div></div>
                <div class="dashboard-reminder">
                    <strong>{payload["count"]}</strong>
                    <p>{escape(str(payload["summary"]))}</p>
                </div>
                <div class="week-progress-card compact-progress">
                    {render_progress(week_stats)}
                    <p>{week_stats.pending} pending this week</p>
                </div>
                <div class="quick-actions compact-actions">
                    <a class="secondary-button" href="{page_path("tasks", selected_date)}">{icon("plus")}Add Task</a>
                    <a class="secondary-button" href="{page_path("reminders", selected_date)}">{icon("bell")}Reminders</a>
                </div>
            </aside>
        </section>
    """


def render_focus_page(repository: TaskRepository, selected_date: date) -> str:
    overdue_tasks = repository.pending_before(selected_date)
    day_tasks = repository.pending_for_date(selected_date)
    upcoming_candidates = repository.pending_from(selected_date, 8)
    next_tasks = [
        task for task in upcoming_candidates if date.fromisoformat(task.due_date) > selected_date
    ][:3]
    return f"""
        <section class="hero-band focus-hero">
            <div>
                <h2>Focus</h2>
                <p>{escape(safe_date_label(selected_date))}</p>
                <a class="hero-link" href="{page_path("tasks", selected_date)}">{icon("plus")}Add Task</a>
            </div>
            <div class="hero-visual" aria-hidden="true"><span></span><span></span><span></span></div>
        </section>
        <section class="focus-grid">
            <div>
                <div class="section-title"><div><p>Late items</p><h2>Overdue</h2></div></div>
                {render_compact_task_list(overdue_tasks, selected_date, "focus", "day", "No overdue tasks", "Everything before this date is handled.")}
            </div>
            <div>
                <div class="section-title"><div><p>{escape(safe_date_label(selected_date))}</p><h2>Focus Tasks</h2></div></div>
                <div class="task-grid focus-task-grid">
                    {render_task_grid(day_tasks, selected_date, "focus", "day", "No focus tasks", "Add something for this date when you are ready.")}
                </div>
            </div>
        </section>
        <section class="dashboard-grid overview-dashboard">
            <div class="panel">
                <div class="section-title"><div><p>Coming up</p><h2>Next Up</h2></div></div>
                {render_compact_task_list(next_tasks, selected_date, "focus", "day", "No upcoming tasks", "Your next queue is clear.")}
            </div>
            <div class="panel">
                <div class="section-title"><div><p>Notification</p><h2>Reminder Preview</h2></div></div>
                {render_reminder_preview(day_tasks, selected_date)}
            </div>
        </section>
    """


def render_tasks_page(repository: TaskRepository, selected_date: date, scope: str) -> str:
    range_start, range_end = range_bounds(selected_date, scope)
    tasks = repository.between_dates(range_start, range_end)
    stats = stats_for_tasks(tasks)
    return f"""
        {render_scope_switch("tasks", selected_date, scope)}
        {render_stats_grid(stats)}
        <section class="management-grid">
            <div>
                <div class="section-title"><div><p>{escape(range_label(selected_date, scope))}</p><h2>Tasks</h2></div></div>
                <div class="task-grid">{render_task_grid(tasks, selected_date, "tasks", scope)}</div>
            </div>
            {render_add_task_form(selected_date, scope)}
        </section>
    """


def render_program_page(repository: TaskRepository, selected_date: date, scope: str) -> str:
    range_start, range_end = range_bounds(selected_date, scope)
    plan_tasks = repository.between_dates(range_start, range_end)
    return f"""
        <section class="weekly-program" id="program">
            <div class="section-title">
                <div><p>{escape(range_label(selected_date, scope))}</p><h2>Plans</h2></div>
            </div>
            {render_scope_switch("program", selected_date, scope)}
            {render_program_form(selected_date, scope)}
            {render_program_rows(plan_tasks, selected_date, scope)}
        </section>
    """


def render_reminders_page(repository: TaskRepository, selected_date: date) -> str:
    tasks = repository.all_for_date(selected_date)
    pending_tasks = [task for task in tasks if task.status == PENDING]
    return f"""
        <section class="reminder-page" id="reminders">
            <div class="section-title"><div><p>{escape(safe_date_label(selected_date))}</p><h2>Reminder Preview</h2></div></div>
            {render_reminder_preview(tasks, selected_date)}
            <div class="task-grid reminder-task-grid">
                {render_task_grid(pending_tasks, selected_date, "reminders", "day", "No pending reminders", "Completed tasks do not appear in the daily reminder.")}
            </div>
        </section>
    """


def render_edit_page(
    task: Task,
    selected_date: date,
    scope: str,
    return_page: str,
    query: dict[str, list[str]],
    notification_count: int,
) -> bytes:
    main = f"""
        <section class="edit-panel">
            <div class="section-title"><div><p>Task #{task.id}</p><h2>Edit Item</h2></div></div>
            <form class="form-panel wide" method="post" action="/tasks/{task.id}/edit">
                <input type="hidden" name="return_page" value="{escape(return_page)}">
                <input type="hidden" name="return_date" value="{selected_date.isoformat()}">
                <input type="hidden" name="scope" value="{escape(scope)}">
                <label for="edit_title">Title</label>
                <input id="edit_title" name="title" type="text" value="{escape(task.title)}" required maxlength="120">
                <label for="edit_category">Category</label>
                <select id="edit_category" name="category">{render_category_options(task.category)}</select>
                <label for="edit_due_date">Due date</label>
                <input id="edit_due_date" name="due_date" type="date" value="{escape(task.due_date)}" required>
                <label for="edit_status">Status</label>
                <select id="edit_status" name="status">{render_status_options(task.status)}</select>
                <label for="edit_description">Description</label>
                <textarea id="edit_description" name="description" rows="6" maxlength="500">{escape(task.description)}</textarea>
                <div class="form-actions">
                    <button type="submit">{icon("check")}Save Changes</button>
                    <a class="secondary-button" href="{page_path(return_page, selected_date, scope=scope)}">Cancel</a>
                </div>
            </form>
        </section>
    """
    active_page = return_page if return_page in PAGES else "tasks"
    return render_shell(active_page, selected_date, scope, query, main, notification_count)


def render_page(
    repository: TaskRepository,
    active_page: str,
    selected_date: date,
    query: dict[str, list[str]],
) -> bytes:
    scope = normalize_scope(query.get("scope", ["day"])[0])
    if active_page == "focus":
        content = render_focus_page(repository, selected_date)
    elif active_page == "tasks":
        content = render_tasks_page(repository, selected_date, scope)
    elif active_page == "program":
        content = render_program_page(repository, selected_date, scope)
    elif active_page == "reminders":
        content = render_reminders_page(repository, selected_date)
    else:
        active_page = "dashboard"
        content = render_dashboard_page(repository, selected_date)
    payload = notification_payload(repository, selected_date)
    return render_shell(active_page, selected_date, scope, query, content, int(payload["count"]))


class DashboardHandler(BaseHTTPRequestHandler):
    database_path: Path

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/static/styles.css":
            self.send_static_file("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/notifications":
            query = parse_qs(parsed.query, keep_blank_values=True)
            selected_date = parse_iso_date(query.get("date", [None])[0])
            with connect(self.database_path) as connection:
                repository = TaskRepository(connection)
                self.send_json(notification_payload(repository, selected_date))
            return
        if parsed.path == "/":
            self.redirect("/dashboard", date=date.today().isoformat())
            return
        if parsed.path == "/today":
            query = parse_qs(parsed.query, keep_blank_values=True)
            selected_date = parse_iso_date(query.get("date", [None])[0])
            scope = normalize_scope(query.get("scope", ["day"])[0])
            self.redirect("/focus", date=selected_date.isoformat(), scope=scope)
            return

        query = parse_qs(parsed.query, keep_blank_values=True)
        selected_date = parse_iso_date(query.get("date", [None])[0])
        scope = normalize_scope(query.get("scope", ["day"])[0])

        if parsed.path.startswith("/tasks/") and parsed.path.endswith("/edit"):
            task_id = self.extract_task_id(parsed.path)
            if task_id is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            return_page = query.get("return_page", ["tasks"])[0]
            with connect(self.database_path) as connection:
                repository = TaskRepository(connection)
                try:
                    task = repository.get_task(task_id)
                except LookupError:
                    self.redirect("/tasks", date=selected_date.isoformat(), notice="Task was not found.")
                    return
                payload = notification_payload(repository, selected_date)
                body = render_edit_page(
                    task,
                    selected_date,
                    scope,
                    return_page,
                    query,
                    int(payload["count"]),
                )
            self.send_html(body)
            return

        page = parsed.path.strip("/") or "dashboard"
        if page not in PAGES:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        with connect(self.database_path) as connection:
            repository = TaskRepository(connection)
            body = render_page(repository, page, selected_date, query)
        self.send_html(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        form = self.read_form()

        if parsed.path == "/tasks":
            self.create_task(form)
            return

        if parsed.path.startswith("/tasks/"):
            task_id = self.extract_task_id(parsed.path)
            if task_id is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if parsed.path.endswith("/complete"):
                self.complete_task(task_id, form)
                return
            if parsed.path.endswith("/delete"):
                self.delete_task(task_id, form)
                return
            if parsed.path.endswith("/edit"):
                self.update_task(task_id, form)
                return

        self.send_error(HTTPStatus.NOT_FOUND)

    def read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(data, keep_blank_values=True)
        return {key: values[0] for key, values in parsed.items()}

    def extract_task_id(self, path: str) -> int | None:
        parts = path.strip("/").split("/")
        if len(parts) < 2 or parts[0] != "tasks":
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None

    def create_task(self, form: dict[str, str]) -> None:
        title = form.get("title", "")
        due_date = parse_iso_date(form.get("due_date"))
        category = form.get("category", "General")
        description = form.get("description", "")
        return_page = form.get("return_page") or ("program" if form.get("source") == "program" else "tasks")
        return_date = parse_iso_date(form.get("return_date")) if form.get("return_date") else due_date
        scope = normalize_scope(form.get("scope", "day"))
        success_notice = "Plan item added." if return_page == "program" else "Task added."
        fragment = "program" if return_page == "program" else ""

        try:
            with connect(self.database_path) as connection:
                TaskRepository(connection).add_task(
                    title,
                    due_date,
                    category=category,
                    description=description,
                )
            self.redirect_page(return_page, return_date, success_notice, fragment=fragment, scope=scope)
        except ValueError:
            self.redirect_page(return_page, return_date, "Task title is required.", fragment=fragment, scope=scope)

    def complete_task(self, task_id: int, form: dict[str, str]) -> None:
        selected_date, return_page, scope = self.return_context(form)
        try:
            with connect(self.database_path) as connection:
                TaskRepository(connection).mark_completed(task_id)
            notice = "Task completed."
        except LookupError:
            notice = "Task was not found."
        self.redirect_page(return_page, selected_date, notice, scope=scope)

    def delete_task(self, task_id: int, form: dict[str, str]) -> None:
        selected_date, return_page, scope = self.return_context(form)
        try:
            with connect(self.database_path) as connection:
                TaskRepository(connection).delete_task(task_id)
            notice = "Item deleted."
        except LookupError:
            notice = "Task was not found."
        self.redirect_page(return_page, selected_date, notice, scope=scope)

    def update_task(self, task_id: int, form: dict[str, str]) -> None:
        selected_date, return_page, scope = self.return_context(form)
        try:
            with connect(self.database_path) as connection:
                TaskRepository(connection).update_task(
                    task_id,
                    form.get("title", ""),
                    parse_iso_date(form.get("due_date")),
                    form.get("category", "General"),
                    form.get("description", ""),
                    form.get("status", PENDING),
                )
            notice = "Item updated."
        except (LookupError, ValueError) as error:
            notice = str(error)
        self.redirect_page(return_page, selected_date, notice, scope=scope)

    def return_context(self, form: dict[str, str]) -> tuple[date, str, str]:
        selected_date = parse_iso_date(form.get("return_date") or form.get("date"))
        return_page = form.get("return_page", "tasks")
        scope = normalize_scope(form.get("scope", "day"))
        if return_page not in PAGES:
            return_page = "tasks"
        return selected_date, return_page, scope

    def redirect_page(
        self,
        page: str,
        selected_date: date,
        notice: str,
        fragment: str = "",
        scope: str = "day",
    ) -> None:
        path = page_path(page if page in PAGES else "tasks", selected_date, scope=scope)
        query_separator = "&" if "?" in path else "?"
        location = f"{path}{query_separator}{urlencode({'notice': notice})}"
        if fragment:
            location = f"{location}#{fragment}"
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def redirect(self, path: str, fragment: str = "", **query: str) -> None:
        location = path
        if query:
            location = f"{path}?{urlencode(query)}"
        if fragment:
            location = f"{location}#{fragment}"
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def send_html(self, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, int | str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static_file(self, filename: str, content_type: str) -> None:
        path = STATIC_DIR / filename
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def make_handler(db_path: Path) -> type[DashboardHandler]:
    class ConfiguredDashboardHandler(DashboardHandler):
        database_path = db_path

    return ConfiguredDashboardHandler


def run_server(host: str, port: int, db_path: str | Path) -> None:
    resolved_db_path = Path(db_path)
    with connect(resolved_db_path):
        pass

    server = ThreadingHTTPServer((host, port), make_handler(resolved_db_path))
    url = f"http://{host}:{port}"
    print(f"My Task Tracker running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping My Task Tracker.")
    finally:
        server.server_close()

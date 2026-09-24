from __future__ import annotations

import json
import os
import smtplib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from typing import Protocol

from .models import Task
from .repository import TaskRepository


class NotificationChannel(Protocol):
    def send(self, subject: str, message: str) -> None:
        """Deliver a reminder message."""


class ConsoleNotifier:
    def send(self, subject: str, message: str) -> None:
        print(subject)
        print("=" * len(subject))
        print(message)


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipient: str
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> "EmailConfig":
        required = {
            "host": "TASK_REMINDER_SMTP_HOST",
            "username": "TASK_REMINDER_SMTP_USERNAME",
            "password": "TASK_REMINDER_SMTP_PASSWORD",
            "sender": "TASK_REMINDER_EMAIL_FROM",
            "recipient": "TASK_REMINDER_EMAIL_TO",
        }
        values = {key: os.getenv(env_name) for key, env_name in required.items()}
        missing = [env_name for key, env_name in required.items() if not values[key]]
        if missing:
            raise RuntimeError(
                "Missing email reminder settings: " + ", ".join(missing)
            )

        return cls(
            host=values["host"],
            port=int(os.getenv("TASK_REMINDER_SMTP_PORT", "587")),
            username=values["username"],
            password=values["password"],
            sender=values["sender"],
            recipient=values["recipient"],
            use_tls=os.getenv("TASK_REMINDER_SMTP_TLS", "true").lower() != "false",
        )


class EmailNotifier:
    def __init__(self, config: EmailConfig):
        self.config = config

    def send(self, subject: str, message: str) -> None:
        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = self.config.sender
        email["To"] = self.config.recipient
        email.set_content(message)

        with smtplib.SMTP(self.config.host, self.config.port) as smtp:
            if self.config.use_tls:
                smtp.starttls()
            smtp.login(self.config.username, self.config.password)
            smtp.send_message(email)


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        token = os.getenv("TASK_REMINDER_TELEGRAM_TOKEN")
        chat_id = os.getenv("TASK_REMINDER_TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise RuntimeError(
                "Missing Telegram reminder settings: "
                "TASK_REMINDER_TELEGRAM_TOKEN, TASK_REMINDER_TELEGRAM_CHAT_ID"
            )
        return cls(token=token, chat_id=chat_id)


class TelegramNotifier:
    def __init__(self, config: TelegramConfig):
        self.config = config

    def send(self, subject: str, message: str) -> None:
        api_url = f"https://api.telegram.org/bot{self.config.token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.config.chat_id,
                "text": f"{subject}\n\n{message}",
            }
        ).encode("utf-8")
        request = urllib.request.Request(api_url, data=payload, method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
            if not result.get("ok"):
                raise RuntimeError("Telegram did not accept the reminder message.")


class ReminderMessageBuilder:
    def build(self, tasks: list[Task], reminder_date: date) -> tuple[str, str]:
        subject = f"My Task Tracker reminder for {reminder_date.isoformat()}"
        if not tasks:
            return subject, "No pending tasks are scheduled for this date."

        lines = [
            f"You have {len(tasks)} pending task(s) for {reminder_date.isoformat()}:",
            "",
        ]
        lines.extend(f"{task.id}. {task.title}" for task in tasks)
        return subject, "\n".join(lines)


class DailyReminderService:
    def __init__(
        self,
        repository: TaskRepository,
        notifier: NotificationChannel,
        builder: ReminderMessageBuilder | None = None,
    ):
        self.repository = repository
        self.notifier = notifier
        self.builder = builder or ReminderMessageBuilder()

    def send_for_date(self, reminder_date: date) -> int:
        tasks = self.repository.pending_for_date(reminder_date)
        subject, message = self.builder.build(tasks, reminder_date)
        self.notifier.send(subject, message)
        return len(tasks)


def build_notifier(channel: str) -> NotificationChannel:
    normalized = channel.lower()
    if normalized == "console":
        return ConsoleNotifier()
    if normalized == "email":
        return EmailNotifier(EmailConfig.from_env())
    if normalized == "telegram":
        return TelegramNotifier(TelegramConfig.from_env())
    raise ValueError(f"Unsupported reminder channel: {channel}")

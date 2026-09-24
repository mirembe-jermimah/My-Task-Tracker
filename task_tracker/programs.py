from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .repository import TaskRepository


@dataclass(frozen=True)
class ProgramTask:
    title: str
    due_date: date
    category: str
    description: str


def week_one_program(year: int) -> list[ProgramTask]:
    return [
        ProgramTask(
            title="Understand what programming and algorithms are",
            due_date=date(year, 9, 14),
            category="Learn",
            description=(
                "Explain what programming is, what an algorithm is, and what a "
                "program actually does."
            ),
        ),
        ProgramTask(
            title="Practice variables, data types, and operators",
            due_date=date(year, 9, 15),
            category="Learn",
            description=(
                "Learn how Python stores values, represents basic data, and uses "
                "operators to calculate or compare things."
            ),
        ),
        ProgramTask(
            title="Practice conditions, loops, functions, and input/output",
            due_date=date(year, 9, 16),
            category="Learn",
            description=(
                "Use if/else logic, repeat work with loops, organize code with "
                "functions, and read/write simple input/output."
            ),
        ),
        ProgramTask(
            title="Practice errors and debugging",
            due_date=date(year, 9, 17),
            category="Learn",
            description=(
                "Notice common mistakes, read error messages, and explain how to "
                "debug a small Python program."
            ),
        ),
        ProgramTask(
            title="Ask a name and greet the person",
            due_date=date(year, 9, 17),
            category="Exercise",
            description="Write a Python program that asks someone's name and greets them.",
        ),
        ProgramTask(
            title="Calculate someone's age",
            due_date=date(year, 9, 17),
            category="Exercise",
            description="Write a Python program that calculates someone's age from their birth year.",
        ),
        ProgramTask(
            title="Determine whether a number is even or odd",
            due_date=date(year, 9, 18),
            category="Exercise",
            description="Write a Python program that checks whether a number is even or odd.",
        ),
        ProgramTask(
            title="Calculate shopping total price",
            due_date=date(year, 9, 18),
            category="Exercise",
            description="Write a Python program that calculates the total price of shopping items.",
        ),
        ProgramTask(
            title="Check qualification by age",
            due_date=date(year, 9, 18),
            category="Exercise",
            description=(
                "Write a Python program that determines whether someone qualifies "
                "for something based on age."
            ),
        ),
        ProgramTask(
            title="Print numbers from 1 to 100",
            due_date=date(year, 9, 19),
            category="Exercise",
            description="Write a Python program that prints numbers from 1 to 100.",
        ),
        ProgramTask(
            title="Find the largest of three numbers",
            due_date=date(year, 9, 19),
            category="Exercise",
            description="Write a Python program that finds the largest of three numbers.",
        ),
        ProgramTask(
            title="Build Jermi's Simple Calculator",
            due_date=date(year, 9, 20),
            category="Mini-project",
            description=(
                "Build a calculator yourself that supports addition, subtraction, "
                "multiplication, and division. Do not copy a finished calculator."
            ),
        ),
        ProgramTask(
            title="Explain the adult/minor code",
            due_date=date(year, 9, 20),
            category="Target",
            description=(
                'Explain every line of: age = 22; if age >= 18: print("Adult"); '
                'else: print("Minor") in simple English.'
            ),
        ),
    ]


def seed_week_one_program(repository: TaskRepository, year: int) -> int:
    created = 0
    for task in week_one_program(year):
        if repository.task_exists(task.title, task.due_date, task.category):
            continue
        repository.add_task(
            task.title,
            task.due_date,
            category=task.category,
            description=task.description,
        )
        created += 1
    return created

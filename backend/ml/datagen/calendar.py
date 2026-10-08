"""Date helpers for the generator. Weeks run Monday to Sunday (the forecaster's convention)."""

import calendar
from collections.abc import Iterable, Iterator
from datetime import date, timedelta


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def iter_weeks(start: date, end: date) -> Iterator[date]:
    """The Monday of every week touched by [start, end]."""
    current = week_start(start)
    while current <= end:
        yield current
        current += timedelta(days=7)


def iter_month_starts(start: date, end: date) -> Iterator[date]:
    """The first day of every calendar month touched by [start, end]."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield date(year, month, 1)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def day_in_month(year: int, month: int, day: int) -> date:
    """`day` of the month, clamped to its last valid day (30 Feb -> 28/29 Feb)."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def exam_weeks(
    start: date, end: date, *, exam_months: Iterable[int], per_semester: int
) -> set[date]:
    """Mondays of the last `per_semester` weeks (by their Monday) of each exam month in range."""
    months = set(exam_months)
    found: set[date] = set()
    for month_start in iter_month_starts(start, end):
        if month_start.month not in months:
            continue
        last_day = day_in_month(month_start.year, month_start.month, 31)
        mondays = [
            d
            for d in iter_weeks(month_start, last_day)
            if d.month == month_start.month and d.year == month_start.year
        ]
        found.update(mondays[-per_semester:])
    return found

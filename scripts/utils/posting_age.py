"""Helpers for filtering job postings by how recently they were posted."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


_AGE_RE = re.compile(
    r"^\s*(\d+)\s*(d|day|days|w|wk|week|weeks|mo|month|months|h|hr|hour|hours)\s*$",
    re.IGNORECASE,
)


def parse_simplify_age(age_text: str) -> Optional[int]:
    """Parse SimplifyJobs age strings like ``0d``, ``3d``, ``1w``, ``2mo`` into days.

    Returns None if the text cannot be parsed.
    """
    if not age_text:
        return None
    text = age_text.strip().lower()
    match = _AGE_RE.match(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit in {"h", "hr", "hour", "hours"}:
        return 0 if value < 24 else value // 24
    if unit in {"d", "day", "days"}:
        return value
    if unit in {"w", "wk", "week", "weeks"}:
        return value * 7
    if unit in {"mo", "month", "months"}:
        return value * 30
    return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Best-effort parse of common ATS timestamp formats into UTC datetimes."""
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        # Lever uses ms; some APIs use seconds
        ts = float(value)
        if ts > 1e12:  # ms
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Normalize Zulu / trailing Z
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        # Truncate fractional seconds beyond microseconds if present
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in (
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
                "%m/%d/%Y",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(text[:19], fmt)
                    break
                except ValueError:
                    dt = None
            if dt is None:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return None


def extract_posted_at(raw_data: dict, source: str = "") -> Optional[datetime]:
    """Extract a posting timestamp from ATS/scrape raw_data when available."""
    if not raw_data:
        return None

    # Explicit age from Simplify tables
    if "age_days" in raw_data and isinstance(raw_data["age_days"], int):
        return datetime.now(timezone.utc) - timedelta(days=raw_data["age_days"])

    age_text = raw_data.get("age") or raw_data.get("age_text")
    if isinstance(age_text, str):
        days = parse_simplify_age(age_text)
        if days is not None:
            return datetime.now(timezone.utc) - timedelta(days=days)

    # Greenhouse
    for key in ("first_published", "updated_at", "created_at"):
        dt = _parse_datetime(raw_data.get(key))
        if dt:
            return dt

    # Lever
    for key in ("createdAt", "updatedAt"):
        dt = _parse_datetime(raw_data.get(key))
        if dt:
            return dt

    # Ashby
    for key in ("publishedAt", "publishedDate", "updatedAt", "createdAt"):
        dt = _parse_datetime(raw_data.get(key))
        if dt:
            return dt
        nested = raw_data.get(key)
        if isinstance(nested, dict):
            dt = _parse_datetime(nested.get("value") or nested.get("date"))
            if dt:
                return dt

    # Workday / SmartRecruiters common fields
    for key in (
        "postedOn",
        "postedDate",
        "publishedDate",
        "releasedDate",
        "createdOn",
        "startDate",
    ):
        dt = _parse_datetime(raw_data.get(key))
        if dt:
            return dt

    # Nested Workday jobPostingInfo
    info = raw_data.get("jobPostingInfo")
    if isinstance(info, dict):
        for key in ("postedOn", "startDate"):
            dt = _parse_datetime(info.get(key))
            if dt:
                return dt

    return None


def is_within_max_age(
    raw_data: dict,
    max_age_days: Optional[int],
    *,
    source: str = "",
    now: Optional[datetime] = None,
) -> bool:
    """Return True if the posting is fresh enough to keep.

    Undated postings are kept (scraped career pages often lack timestamps).
    When max_age_days is None or <= 0, all postings are kept.
    """
    if max_age_days is None or max_age_days <= 0:
        return True

    posted_at = extract_posted_at(raw_data, source=source)
    if posted_at is None:
        return True

    current = now or datetime.now(timezone.utc)
    age = current - posted_at
    # Compare whole days so Simplify ages like ``2w`` (14d) are inclusive.
    return age.total_seconds() <= (max_age_days * 86400) + 1

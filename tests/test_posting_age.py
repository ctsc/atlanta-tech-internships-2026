"""Tests for posting-age freshness helpers."""

from datetime import datetime, timedelta, timezone

from scripts.utils.posting_age import (
    extract_posted_at,
    is_within_max_age,
    parse_simplify_age,
)


class TestParseSimplifyAge:
    def test_days(self):
        assert parse_simplify_age("0d") == 0
        assert parse_simplify_age("3d") == 3
        assert parse_simplify_age("14 days") == 14

    def test_weeks(self):
        assert parse_simplify_age("1w") == 7
        assert parse_simplify_age("2w") == 14

    def test_months(self):
        assert parse_simplify_age("1mo") == 30

    def test_invalid(self):
        assert parse_simplify_age("") is None
        assert parse_simplify_age("soon") is None


class TestIsWithinMaxAge:
    def test_undated_kept(self):
        assert is_within_max_age({}, 14) is True

    def test_fresh_kept(self):
        posted = datetime.now(timezone.utc) - timedelta(days=3)
        raw = {"first_published": posted.isoformat()}
        assert is_within_max_age(raw, 14) is True

    def test_stale_dropped(self):
        posted = datetime.now(timezone.utc) - timedelta(days=21)
        raw = {"first_published": posted.isoformat()}
        assert is_within_max_age(raw, 14) is False

    def test_simplify_age_days(self):
        assert is_within_max_age({"age": "2w"}, 14) is True
        assert is_within_max_age({"age": "1mo"}, 14) is False

    def test_disabled(self):
        posted = datetime.now(timezone.utc) - timedelta(days=90)
        raw = {"first_published": posted.isoformat()}
        assert is_within_max_age(raw, 0) is True
        assert is_within_max_age(raw, None) is True


class TestExtractPostedAt:
    def test_greenhouse(self):
        dt = extract_posted_at({"first_published": "2026-09-08T12:00:00-04:00"})
        assert dt is not None
        assert dt.year == 2026

    def test_lever_ms(self):
        ms = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
        dt = extract_posted_at({"createdAt": ms})
        assert dt is not None
        assert dt.day == 1

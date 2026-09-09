"""Tests for the morning digest email script."""

from datetime import date, datetime
from unittest.mock import patch

from scripts.send_digest import (
    _build_email_html,
    _passes_board_filters,
    send_digest,
)
from scripts.utils.models import (
    JobListing,
    JobsDatabase,
    ListingStatus,
    ListingType,
    RoleCategory,
    SponsorshipStatus,
)


def _listing(**overrides) -> JobListing:
    defaults = {
        "id": "digest1",
        "company": "Acme",
        "company_slug": "acme",
        "role": "Software Engineer Intern",
        "category": RoleCategory.SWE,
        "locations": ["Atlanta, GA"],
        "apply_url": "https://example.com/apply",
        "sponsorship": SponsorshipStatus.UNKNOWN,
        "date_added": date(2026, 9, 1),
        "date_last_verified": date(2026, 9, 1),
        "source": "greenhouse_api",
        "status": ListingStatus.OPEN,
        "season": "spring_2027",
        "listing_type": ListingType.INTERNSHIP,
    }
    defaults.update(overrides)
    return JobListing(**defaults)


class TestPassesBoardFilters:
    def test_se_open_swe_passes(self):
        assert _passes_board_filters(_listing(), {"spring_2027", "summer_2027"}) is True

    def test_remote_only_fails(self):
        listing = _listing(locations=["Remote"], remote_friendly=True)
        assert _passes_board_filters(listing, {"spring_2027"}) is False

    def test_dropped_title_fails(self):
        listing = _listing(role="Hardware Engineer Intern")
        assert _passes_board_filters(listing, {"spring_2027"}) is False

    def test_wrong_season_fails(self):
        listing = _listing(season="summer_2026")
        assert _passes_board_filters(listing, {"spring_2027"}) is False


class TestBuildEmailHtml:
    def test_includes_company_and_link(self):
        html = _build_email_html([_listing()])
        assert "Acme" in html
        assert "Software Engineer Intern" in html
        assert "https://example.com/apply" in html


class TestSendDigest:
    def test_seeds_empty_snapshot_without_sending(self, tmp_path):
        snap = tmp_path / "digest_snapshot.json"
        snap.write_text('{"listing_ids": [], "updated_at": null}', encoding="utf-8")
        jobs_db = JobsDatabase(
            listings=[_listing()],
            last_updated=datetime(2026, 9, 9),
            total_open=1,
        )
        empty_db = JobsDatabase(
            listings=[],
            last_updated=datetime(2026, 9, 9),
            total_open=0,
        )

        def _load(path):
            return empty_db if "el.json" in str(path) else jobs_db

        with (
            patch("scripts.send_digest.load_database", side_effect=_load),
            patch("scripts.send_digest._send_resend_email") as mock_send,
            patch("scripts.send_digest.JOBS_PATH", tmp_path / "jobs.json"),
            patch("scripts.send_digest.EL_JOBS_PATH", tmp_path / "el.json"),
        ):
            stats = send_digest(snapshot_path=snap)

        assert stats["seeded"] is True
        assert stats["sent"] is False
        assert stats["skipped"] is True
        mock_send.assert_not_called()
        data = snap.read_text(encoding="utf-8")
        assert "digest1" in data

    def test_skips_email_when_no_new(self, tmp_path):
        snap = tmp_path / "digest_snapshot.json"
        snap.write_text(
            '{"listing_ids": ["digest1"], "updated_at": "2026-09-08T00:00:00+00:00"}',
            encoding="utf-8",
        )
        jobs_db = JobsDatabase(
            listings=[_listing()],
            last_updated=datetime(2026, 9, 9),
            total_open=1,
        )
        empty_db = JobsDatabase(
            listings=[],
            last_updated=datetime(2026, 9, 9),
            total_open=0,
        )

        def _load(path):
            return empty_db if "el.json" in str(path) else jobs_db

        with (
            patch("scripts.send_digest.load_database", side_effect=_load),
            patch("scripts.send_digest._send_resend_email") as mock_send,
            patch("scripts.send_digest.JOBS_PATH", tmp_path / "jobs.json"),
            patch("scripts.send_digest.EL_JOBS_PATH", tmp_path / "el.json"),
        ):
            stats = send_digest(snapshot_path=snap)

        assert stats["new_count"] == 0
        assert stats["skipped"] is True
        mock_send.assert_not_called()

    def test_sends_when_new_listing(self, tmp_path):
        snap = tmp_path / "digest_snapshot.json"
        snap.write_text(
            '{"listing_ids": ["old1"], "updated_at": "2026-09-08T00:00:00+00:00"}',
            encoding="utf-8",
        )
        jobs_db = JobsDatabase(
            listings=[_listing(id="digest1")],
            last_updated=datetime(2026, 9, 9),
            total_open=1,
        )
        empty_db = JobsDatabase(
            listings=[],
            last_updated=datetime(2026, 9, 9),
            total_open=0,
        )

        def _load(path):
            return empty_db if "entry_level" in str(path) or "el.json" in str(path) else jobs_db

        with (
            patch("scripts.send_digest.load_database", side_effect=_load),
            patch("scripts.send_digest._send_resend_email", return_value=True) as mock_send,
            patch("scripts.send_digest.JOBS_PATH", tmp_path / "jobs.json"),
            patch("scripts.send_digest.EL_JOBS_PATH", tmp_path / "el.json"),
        ):
            stats = send_digest(snapshot_path=snap)

        assert stats["new_count"] == 1
        assert stats["sent"] is True
        mock_send.assert_called_once()
        assert "digest1" in snap.read_text(encoding="utf-8")

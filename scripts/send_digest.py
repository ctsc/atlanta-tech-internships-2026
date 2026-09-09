"""Morning digest: email newly added board-scoped roles via Resend.

Compares current open listings in jobs.json + entry_level_jobs.json against
data/digest_snapshot.json. On the first run (empty snapshot), seeds the
snapshot without sending. Subsequent runs email only net-new roles that pass
the same geo / season / category filters as the README.

Usage:
    python -m scripts.send_digest
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from scripts.utils.config import PROJECT_ROOT, get_config, get_secret
from scripts.utils.db_io import load_database
from scripts.utils.models import (
    JobListing,
    ListingStatus,
    ListingType,
    RoleCategory,
)
from scripts.utils.readme_renderer import _is_southeast_listing
from scripts.validate import DROPPED_CATEGORIES, _is_dropped_domain_title

logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
JOBS_PATH = DATA_DIR / "jobs.json"
EL_JOBS_PATH = DATA_DIR / "entry_level_jobs.json"
SNAPSHOT_PATH = DATA_DIR / "digest_snapshot.json"

KEPT_CATEGORIES: set[RoleCategory] = {
    RoleCategory.SWE,
    RoleCategory.ML_AI,
    RoleCategory.PM,
    RoleCategory.PRODUCT_ENGINEER,
    RoleCategory.OTHER,
}


def _load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    """Load digest snapshot JSON."""
    if not path.exists():
        return {"listing_ids": [], "updated_at": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("listing_ids"), list):
            data["listing_ids"] = []
        return data
    except Exception as exc:
        logger.warning("Could not read digest snapshot: %s", exc)
        return {"listing_ids": [], "updated_at": None}


def _save_snapshot(listing_ids: set[str], path: Path = SNAPSHOT_PATH) -> None:
    """Persist current open listing IDs to the snapshot file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "listing_ids": sorted(listing_ids),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)
    logger.info("Wrote digest snapshot (%d ids) to %s", len(listing_ids), path)


def _get_active_seasons() -> set[str]:
    try:
        return set(get_config().project.active_seasons)
    except Exception:
        return {"spring_2027", "summer_2027"}


def _passes_board_filters(listing: JobListing, active_seasons: set[str]) -> bool:
    """Match README visibility rules for digest eligibility."""
    if listing.status != ListingStatus.OPEN:
        return False
    if _is_dropped_domain_title(listing.role):
        return False
    if listing.category in DROPPED_CATEGORIES:
        return False
    if listing.category not in KEPT_CATEGORIES and listing.category not in DROPPED_CATEGORIES:
        # Unknown future categories still allowed if not explicitly dropped
        pass
    if listing.listing_type != ListingType.ENTRY_LEVEL:
        if listing.season not in active_seasons:
            return False
    if not _is_southeast_listing(listing):
        return False
    return True


def _collect_open_filtered() -> list[JobListing]:
    """Load both DBs and return board-filtered open listings."""
    active_seasons = _get_active_seasons()
    listings: list[JobListing] = []
    for path in (JOBS_PATH, EL_JOBS_PATH):
        db = load_database(path)
        for listing in db.listings:
            if _passes_board_filters(listing, active_seasons):
                listings.append(listing)
    return listings


def _format_listing_html(listing: JobListing) -> str:
    """Format one listing as an HTML list item."""
    locs = ", ".join(listing.locations) if listing.locations else "Unknown"
    extra = ""
    if listing.listing_type == ListingType.ENTRY_LEVEL:
        extra = f" | {listing.seniority or 'new_grad'}"
    else:
        extra = f" | {listing.season}"
    return (
        f"<li><strong>{listing.company}</strong> — {listing.role} "
        f"({locs}{extra}) — "
        f"<a href=\"{listing.apply_url}\">Apply</a></li>"
    )


def _build_email_html(new_listings: list[JobListing]) -> str:
    """Build HTML body for the digest email."""
    internships = [
        x for x in new_listings if x.listing_type != ListingType.ENTRY_LEVEL
    ]
    entry_level = [
        x for x in new_listings if x.listing_type == ListingType.ENTRY_LEVEL
    ]

    parts = [
        "<html><body>",
        f"<h2>Atlanta Tech Internships — {len(new_listings)} new role(s)</h2>",
        "<p>New Georgia / Southeast / Texas roles since yesterday.</p>",
    ]
    if internships:
        parts.append("<h3>Internships</h3><ul>")
        parts.extend(_format_listing_html(x) for x in internships)
        parts.append("</ul>")
    if entry_level:
        parts.append("<h3>Entry-Level</h3><ul>")
        parts.extend(_format_listing_html(x) for x in entry_level)
        parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


def _send_resend_email(subject: str, html: str) -> bool:
    """Send email via Resend HTTP API. Returns True on success."""
    api_key = get_secret("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY", "")
    to_email = get_secret("DIGEST_TO_EMAIL") or os.environ.get("DIGEST_TO_EMAIL", "")
    from_email = (
        get_secret("RESEND_FROM_EMAIL")
        or os.environ.get("RESEND_FROM_EMAIL", "")
        or "onboarding@resend.dev"
    )

    if not api_key or not to_email:
        logger.error(
            "Missing RESEND_API_KEY or DIGEST_TO_EMAIL — cannot send digest"
        )
        return False

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 400:
            logger.error("Resend API error %s: %s", resp.status_code, resp.text)
            return False
        logger.info("Digest email sent to %s (status %s)", to_email, resp.status_code)
        return True
    except Exception as exc:
        logger.exception("Failed to send digest email: %s", exc)
        return False


def send_digest(
    *,
    snapshot_path: Path = SNAPSHOT_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Compute new listings vs snapshot and optionally email them.

    Returns a stats dict with keys: new_count, seeded, sent, skipped.
    """
    listings = _collect_open_filtered()
    current_ids = {x.id for x in listings}
    snapshot = _load_snapshot(snapshot_path)
    previous_ids = set(snapshot.get("listing_ids") or [])

    # First run: seed snapshot, do not spam historical backlog
    if not previous_ids:
        _save_snapshot(current_ids, snapshot_path)
        logger.info(
            "Seeded digest snapshot with %d listings — no email sent",
            len(current_ids),
        )
        return {
            "new_count": 0,
            "seeded": True,
            "sent": False,
            "skipped": True,
        }

    new_listings = [x for x in listings if x.id not in previous_ids]
    # Always refresh snapshot to current open set
    _save_snapshot(current_ids, snapshot_path)

    if not new_listings:
        logger.info("No new board-scoped roles since last digest — skipping email")
        return {
            "new_count": 0,
            "seeded": False,
            "sent": False,
            "skipped": True,
        }

    subject = f"Atlanta Tech Internships — {len(new_listings)} new role(s)"
    html = _build_email_html(new_listings)

    if dry_run:
        logger.info("Dry run: would email %d new roles", len(new_listings))
        return {
            "new_count": len(new_listings),
            "seeded": False,
            "sent": False,
            "skipped": False,
            "dry_run": True,
        }

    sent = _send_resend_email(subject, html)
    return {
        "new_count": len(new_listings),
        "seeded": False,
        "sent": sent,
        "skipped": False,
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    stats = send_digest()
    if stats.get("sent") is False and stats.get("new_count", 0) > 0 and not stats.get("skipped"):
        sys.exit(1)


if __name__ == "__main__":
    main()

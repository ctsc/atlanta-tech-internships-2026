"""Markdown table generation logic for rendering the README from job data.

Transforms internship and entry-level JobsDatabases into a formatted README.md
with categorized tables and stats. Only includes Georgia / Southeast / Texas
listings (remote alone is not enough — remote must include a SE/TX signal).
Internship tables are further limited to configured active seasons.
"""

import logging
from datetime import date

from scripts.utils.config import get_config
from scripts.utils.models import (
    JobListing,
    JobsDatabase,
    ListingStatus,
    ListingType,
    RoleCategory,
)

logger = logging.getLogger(__name__)

# Category display order and metadata
CATEGORY_INFO: list[tuple[RoleCategory, str, str, str]] = [
    (RoleCategory.SWE, "Software Engineering", "-software-engineering", "💻"),
    (RoleCategory.PRODUCT_ENGINEER, "Product Engineering", "-product-engineering", "🛠️"),
    (RoleCategory.PM, "Product Management", "-product-management", "📱"),
    (RoleCategory.ML_AI, "ML / AI", "-ml--ai", "🤖"),
    (RoleCategory.OTHER, "Other", "-other", "🔹"),
]

# Categories removed from display — fold into OTHER if any slip through
_FOLDED_CATEGORIES: set[RoleCategory] = {
    RoleCategory.QUANT,
    RoleCategory.DATA_SCIENCE,
    RoleCategory.HARDWARE,
}

SEASON_BADGES: dict[str, str] = {
    "summer_2026": "S26",
    "fall_2026": "F26",
    "spring_2027": "Sp27",
    "summer_2027": "S27",
}

SENIORITY_LABELS: dict[str, str] = {
    "new_grad": "New Grad",
    "swe1": "SWE I",
    "swe2": "SWE II",
}


def _format_locations(locations: list[str], max_display: int = 3) -> str:
    """Format a list of locations, truncating if needed."""
    if not locations:
        return "Unknown"
    if len(locations) <= max_display:
        return ", ".join(locations)
    displayed = ", ".join(locations[:max_display])
    remaining = len(locations) - max_display
    return f"{displayed} and {remaining} more"


def _format_season(season: str) -> str:
    """Format a season string as a short badge."""
    return SEASON_BADGES.get(season, season)


def _format_seniority(seniority: str) -> str:
    """Format entry-level seniority for display."""
    if not seniority:
        return "—"
    return SENIORITY_LABELS.get(seniority, seniority)


def _format_class_years(listing: JobListing) -> str:
    """Format preferred class years / degree level for the Level column."""
    years = [y.lower() for y in listing.preferred_class_years]
    grad = {"masters", "phd"}
    undergrad = {"freshman", "sophomore", "junior", "senior"}

    has_grad = listing.requires_advanced_degree or listing.graduate_friendly or bool(
        set(years) & grad
    )
    has_undergrad = bool(set(years) & undergrad)

    if has_grad and has_undergrad:
        return "All"
    if has_grad:
        if "phd" in years and "masters" not in years and not listing.graduate_friendly:
            return "PhD"
        if "phd" in years:
            return "MS/PhD"
        return "MS/PhD"
    if has_undergrad:
        # Compact undergrad markers when specific years are known
        mapping = {
            "freshman": "Fr",
            "sophomore": "So",
            "junior": "Jr",
            "senior": "Sr",
        }
        badges = [mapping[y] for y in ("freshman", "sophomore", "junior", "senior") if y in years]
        if set(years) >= undergrad or len(badges) == 4:
            return "Undergrad"
        if badges:
            return "/".join(badges)
        return "Undergrad"
    return "—"


def _format_relative_date(d: date) -> str:
    """Format a date as relative time (e.g., 'today', '2d ago', '3w ago')."""
    delta = (date.today() - d).days
    if delta <= 0:
        return "today"
    if delta == 1:
        return "1d ago"
    if delta < 7:
        return f"{delta}d ago"
    if delta < 30:
        weeks = delta // 7
        return f"{weeks}w ago"
    if delta < 365:
        months = delta // 30
        return f"{months}mo ago"
    years = delta // 365
    return f"{years}y ago"


def _escape_markdown_cell(text: str) -> str:
    """Escape pipe characters in text destined for a markdown table cell."""
    return text.replace("|", "\\|")


def _get_active_seasons() -> set[str]:
    """Return configured active internship seasons."""
    try:
        config = get_config()
        return set(config.project.active_seasons)
    except Exception:
        logger.warning("Could not load active_seasons; defaulting to spring/summer 2027")
        return {"spring_2027", "summer_2027"}


def _is_active_internship(listing: JobListing, active_seasons: set[str]) -> bool:
    """Internship listings must be in an active season."""
    if listing.listing_type == ListingType.ENTRY_LEVEL:
        return True
    return listing.season in active_seasons


def _format_listing_row(
    listing: JobListing,
    *,
    include_season: bool = True,
    include_level: bool = False,
    include_seniority: bool = False,
) -> str:
    """Format a single listing as a markdown table row."""
    company = f"**{_escape_markdown_cell(listing.company)}**"
    if listing.is_faang_plus:
        company = f"🔥 {company}"

    role = _escape_markdown_cell(listing.role)
    flags = []
    if listing.status == ListingStatus.CLOSED:
        flags.append("🔒")
    if listing.open_to_international:
        flags.append("🌍")
    if listing.remote_friendly:
        flags.append("🏠")
    if listing.graduate_friendly or listing.requires_advanced_degree:
        flags.append("🎓")
    if flags:
        role = f"{role} {''.join(flags)}"

    locations = _format_locations(listing.locations)
    date_str = _format_relative_date(listing.date_added)
    apply_url = str(listing.apply_url)

    if listing.status == ListingStatus.CLOSED:
        apply_link = "🔒 Closed"
    else:
        apply_link = f"[Apply]({apply_url})"

    parts = [company, role]
    if include_level:
        parts.append(_format_class_years(listing))
    if include_seniority:
        parts.append(_format_seniority(listing.seniority))
    parts.append(locations)
    if include_season:
        parts.append(_format_season(listing.season))
    parts.extend([apply_link, date_str])

    return "| " + " | ".join(parts) + " |"


def _render_category_section(
    category: RoleCategory,
    emoji: str,
    title: str,
    listings: list[JobListing],
    *,
    include_season: bool = True,
    include_level: bool = True,
    include_seniority: bool = False,
) -> str:
    """Render a single category section with its table."""
    lines = [
        f"## {emoji} {title}",
        "",
    ]

    open_listings = [x for x in listings if x.status == ListingStatus.OPEN]
    closed_listings = [x for x in listings if x.status == ListingStatus.CLOSED]

    sorted_listings = sorted(
        open_listings + closed_listings,
        key=lambda x: x.date_added,
        reverse=True,
    )

    if not sorted_listings:
        lines.append("No listings yet. Check back soon!")
        lines.append("")
        return "\n".join(lines)

    headers = ["Company", "Role"]
    dividers = ["---------", "------"]
    if include_level:
        headers.append("Level")
        dividers.append("-------")
    if include_seniority:
        headers.append("Seniority")
        dividers.append("-----------")
    headers.append("Location")
    dividers.append("----------")
    if include_season:
        headers.append("Season")
        dividers.append("--------")
    headers.extend(["Apply", "Posted"])
    dividers.extend(["-------", "--------"])

    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(dividers) + "|")
    for listing in sorted_listings:
        lines.append(
            _format_listing_row(
                listing,
                include_season=include_season,
                include_level=include_level,
                include_seniority=include_seniority,
            )
        )
    lines.append("")
    return "\n".join(lines)


SOUTHEAST_PATTERNS: dict[str, list[str]] = {
    "states": [
        ", ga", ", fl", ", al", ", tx", ", sc", ", nc", ", tn",
        "georgia", "florida", "alabama", "texas",
        "south carolina", "north carolina", "tennessee",
    ],
    "cities": [
        "atlanta", "alpharetta", "marietta", "savannah", "augusta",
        "miami", "orlando", "tampa", "jacksonville",
        "birmingham", "huntsville",
        "dallas", "austin", "houston", "san antonio",
        "charlotte", "raleigh", "durham", "research triangle",
        "charleston", "greenville", "columbia",
        "nashville", "knoxville", "memphis", "chattanooga",
    ],
}


def _location_has_southeast_signal(loc_lower: str) -> bool:
    """Return True if a single location string signals GA / SE / TX."""
    for pattern in SOUTHEAST_PATTERNS["states"]:
        if pattern in loc_lower:
            return True
    for city in SOUTHEAST_PATTERNS["cities"]:
        if city in loc_lower:
            return True
    return False


def _is_southeast_listing(listing: JobListing) -> bool:
    """Check if a listing is in Georgia / Southeast / Texas.

    Bare remote / remote_friendly alone does NOT qualify — remote is included
    only when a location string also carries a SE/TX/GA signal
    (e.g. \"Remote; Atlanta, GA\").
    """
    for loc in listing.locations:
        loc_lower = loc.lower()
        if _location_has_southeast_signal(loc_lower):
            return True
    return False


def _count_open(
    listings: list[JobListing],
    category: RoleCategory,
    active_seasons: set[str] | None = None,
) -> int:
    """Count open SE listings for a given category."""
    return len([
        x for x in listings
        if x.category == category
        and x.status == ListingStatus.OPEN
        and _is_southeast_listing(x)
        and (active_seasons is None or _is_active_internship(x, active_seasons))
    ])


def _count_open_faang(
    listings: list[JobListing],
    active_seasons: set[str] | None = None,
) -> int:
    """Count open SE listings that are FAANG+/big tech."""
    return len([
        x for x in listings
        if x.is_faang_plus
        and x.status == ListingStatus.OPEN
        and _is_southeast_listing(x)
        and (active_seasons is None or _is_active_internship(x, active_seasons))
    ])


GEORGIA_PATTERNS: dict[str, list[str]] = {
    "states": [", ga", "georgia"],
    "cities": [
        "atlanta", "alpharetta", "marietta", "savannah", "augusta",
        "roswell", "sandy springs", "johns creek", "kennesaw",
        "lawrenceville", "duluth", "peachtree", "decatur",
        "athens", "columbus", "macon", "warner robins",
    ],
}


def _is_georgia_listing(listing: JobListing) -> bool:
    """Check if a listing has a Georgia location."""
    for loc in listing.locations:
        loc_lower = loc.lower()
        for pattern in GEORGIA_PATTERNS["states"]:
            if pattern in loc_lower:
                return True
        for city in GEORGIA_PATTERNS["cities"]:
            if city in loc_lower:
                return True
    return False


def _count_open_georgia(
    listings: list[JobListing],
    active_seasons: set[str] | None = None,
) -> int:
    """Count open listings in Georgia."""
    return len([
        x for x in listings
        if x.status == ListingStatus.OPEN
        and _is_georgia_listing(x)
        and (active_seasons is None or _is_active_internship(x, active_seasons))
    ])


def _count_open_graduate(
    listings: list[JobListing],
    active_seasons: set[str],
) -> int:
    """Count open SE graduate-friendly internship listings."""
    return len([
        x for x in listings
        if x.status == ListingStatus.OPEN
        and _is_southeast_listing(x)
        and _is_active_internship(x, active_seasons)
        and (x.graduate_friendly or x.requires_advanced_degree
             or any(y in ("masters", "phd") for y in x.preferred_class_years))
    ])


def _filter_internships(
    listings: list[JobListing],
    active_seasons: set[str],
) -> list[JobListing]:
    """Keep internship listings in active seasons only."""
    return [
        x for x in listings
        if x.listing_type != ListingType.ENTRY_LEVEL
        and _is_active_internship(x, active_seasons)
    ]


def render_readme(
    jobs_db: JobsDatabase,
    entry_level_db: JobsDatabase | None = None,
) -> str:
    """Render a complete README.md from internship and entry-level databases.

    Only includes listings in the Southeast region (GA, FL, AL, TX, SC, NC, TN)
    plus remote-friendly roles. Internship rows are limited to active seasons.

    Args:
        jobs_db: Internship jobs database.
        entry_level_db: Optional entry-level jobs database.

    Returns:
        A string containing the full README markdown.
    """
    try:
        config = get_config()
        repo = config.project.github_repo
    except Exception:
        logger.warning("Could not load config, using defaults for README rendering")
        repo = "ctsc/atlanta-tech-internships-2026"

    active_seasons = _get_active_seasons()
    jobs_db.compute_stats()
    listings = _filter_internships(jobs_db.listings, active_seasons)
    el_listings = entry_level_db.listings if entry_level_db is not None else []

    from datetime import timezone, timedelta
    est = timezone(timedelta(hours=-5))
    last_updated_est = jobs_db.last_updated.replace(tzinfo=timezone.utc).astimezone(est)
    timestamp = last_updated_est.strftime("%B %d, %Y at %I:%M %p EST")

    category_counts: dict[RoleCategory, int] = {}
    for cat, _, _, _ in CATEGORY_INFO:
        count = _count_open(listings, cat, active_seasons)
        if cat == RoleCategory.OTHER:
            for folded in _FOLDED_CATEGORIES:
                count += _count_open(listings, folded, active_seasons)
        category_counts[cat] = count
    total_open = sum(category_counts.values())

    el_ga_count = _count_open_georgia(el_listings)
    el_total = len([
        x for x in el_listings
        if x.status == ListingStatus.OPEN and _is_southeast_listing(x)
    ])
    graduate_count = _count_open_graduate(listings, active_seasons)

    issue_url = f"https://github.com/{repo}/issues/new?template=new-internship.yml"

    parts: list[str] = []
    parts.append("# Atlanta Tech Internships 🚀")
    parts.append("")
    parts.append(f"> 🤖 **Auto-updated every 6 hours** | Last updated: {timestamp}")
    parts.append(">")
    parts.append("> Catered to Georgia / Southeast ⭐ Leave a star on the repo if you enjoy this project :)")
    parts.append(">")
    parts.append("> Built and maintained by [Carter](https://github.com/ctsc)")
    parts.append("")
    parts.append(
        "Use this repo to discover and track **Spring 2027 / Summer 2027 tech internships** "
        "and **entry-level SWE roles** (new grad, SWE I, SWE II) across software engineering, "
        "ML/AI, data science, and more."
    )
    parts.append("")
    parts.append(
        "[View all tracked companies](COMPANIES.md)"
    )
    parts.append("")
    parts.append("---")
    parts.append("")

    # --- Stats Table ---
    parts.append("### 📊 Stats")
    parts.append("")
    parts.append("| Category | Open Roles |")
    parts.append("|----------|-----------|")
    for cat, title, anchor, emoji in CATEGORY_INFO:
        count = category_counts[cat]
        if cat == RoleCategory.OTHER and count == 0:
            continue
        parts.append(f"| {emoji} [{title}](#{anchor}) | {count} |")

    big_tech_count = _count_open_faang(listings, active_seasons)
    georgia_count = _count_open_georgia(listings, active_seasons)
    parts.append(f"| 🔥 [Big Tech in the Southeast](#-big-tech-in-the-southeast) | {big_tech_count} |")
    parts.append(f"| 🍑 [Roles Open in GA](#-roles-open-in-ga) | {georgia_count} |")
    parts.append(f"| 🎓 Graduate-Friendly Internships | {graduate_count} |")
    parts.append(f"| 💼 [Entry-Level Roles in GA](#-entry-level-roles-in-ga) | {el_ga_count} |")
    parts.append(f"| 💼 Entry-Level (Southeast) | {el_total} |")

    parts.append(f"| **Total Internships** | **{total_open}** |")
    parts.append("")
    parts.append("---")
    parts.append("")

    # --- Roles Open in GA ---
    ga_listings = [
        x for x in listings
        if _is_georgia_listing(x)
    ]
    ga_section = _render_category_section(
        RoleCategory.OTHER, "🍑", "Roles Open in GA", ga_listings,
        include_season=True, include_level=True,
    )
    parts.append(ga_section)
    parts.append("---")
    parts.append("")

    # --- Big Tech in the Southeast ---
    big_tech_listings = [
        x for x in listings
        if x.is_faang_plus and _is_southeast_listing(x)
    ]
    big_tech_section = _render_category_section(
        RoleCategory.SWE, "🔥", "Big Tech in the Southeast", big_tech_listings,
        include_season=True, include_level=True,
    )
    parts.append(big_tech_section)
    parts.append("---")
    parts.append("")

    # --- Category Sections (SE-only) ---
    for cat, title, anchor, emoji in CATEGORY_INFO:
        cat_listings = [
            x for x in listings
            if (x.category == cat or (cat == RoleCategory.OTHER and x.category in _FOLDED_CATEGORIES))
            and _is_southeast_listing(x)
        ]
        if cat == RoleCategory.OTHER and not cat_listings:
            continue
        section = _render_category_section(
            cat, emoji, title, cat_listings,
            include_season=True, include_level=True,
        )
        parts.append(section)
        parts.append("---")
        parts.append("")

    # --- Entry-Level Sections ---
    if el_listings or True:
        parts.append("## 💼 Entry-Level Roles")
        parts.append("")
        parts.append(
            "Full-time new-grad and early-career SWE / PE / PM / ML-AI roles "
            "(SWE / SWE I / SWE II, ~0–2 years). Georgia and Southeast focused."
        )
        parts.append("")

        el_ga = [x for x in el_listings if _is_georgia_listing(x)]
        el_ga_section = _render_category_section(
            RoleCategory.OTHER, "💼", "Entry-Level Roles in GA", el_ga,
            include_season=False, include_level=False, include_seniority=True,
        )
        parts.append(el_ga_section)
        parts.append("---")
        parts.append("")

        for cat, title, anchor, emoji in CATEGORY_INFO:
            cat_listings = [
                x for x in el_listings
                if (x.category == cat or (cat == RoleCategory.OTHER and x.category in _FOLDED_CATEGORIES))
                and _is_southeast_listing(x)
            ]
            if not cat_listings:
                continue
            section = _render_category_section(
                cat, emoji, f"Entry-Level {title}", cat_listings,
                include_season=False, include_level=False, include_seniority=True,
            )
            parts.append(section)
            parts.append("---")
            parts.append("")

    # --- How This Works ---
    parts.append("## How This Works")
    parts.append("")
    parts.append("This repo is **automatically maintained by AI**. Every 6 hours:")
    parts.append("1. Scripts scan 100+ company career pages and job board APIs")
    parts.append("2. Gemini AI validates Spring/Summer 2027 internships and entry-level SWE roles")
    parts.append("3. Dead links are detected and removed")
    parts.append("4. The README is regenerated with fresh data")
    parts.append("")

    # --- Contributing ---
    parts.append("## Contributing")
    parts.append("")
    parts.append(f"Found a listing we missed? [Submit an issue]({issue_url})!")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("⭐ **Star this repo** to stay updated!")
    parts.append("")

    readme = "\n".join(parts)
    logger.info(
        "README rendered: %d internship listings, %d entry-level, %d open internships",
        len(listings),
        len(el_listings),
        total_open,
    )
    return readme

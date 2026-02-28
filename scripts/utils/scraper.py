"""Generic career page scraper and GitHub repo monitor.

Provides GenericScraper for scraping career pages via httpx + BeautifulSoup,
and monitor_github_repo for tracking new listings from other GitHub repos.
"""

import asyncio
import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scripts.utils.config import GitHubMonitor, ScrapeSource, get_config, PROJECT_ROOT
from scripts.utils.models import RawListing

logger = logging.getLogger(__name__)

USER_AGENT = (
    "InternshipTracker/1.0 "
    "(github.com/ctsc/atlanta-tech-internships-2026)"
)

# Default intern-related keywords used to identify internship links/titles.
INTERN_KEYWORDS = ("intern", "internship", "co-op", "coop")


class _DomainRateLimiter:
    """Tracks per-domain request timestamps to enforce rate limits."""

    def __init__(self, max_per_second: float = 2.0):
        self._min_interval = 1.0 / max_per_second
        self._last_request: dict[str, float] = {}

    async def wait(self, domain: str) -> None:
        now = time.monotonic()
        last = self._last_request.get(domain, 0.0)
        elapsed = now - last
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request[domain] = time.monotonic()


class GenericScraper:
    """Scrapes career pages for internship listings.

    Uses httpx.AsyncClient with rate limiting, retries, and randomized delays.
    Parses HTML with BeautifulSoup + lxml to find intern-related links.
    """

    def __init__(self) -> None:
        self._rate_limiter = _DomainRateLimiter(max_per_second=2.0)
        self._config = get_config()
        self._intern_keywords: list[str] = (
            self._config.filters.keywords_include or list(INTERN_KEYWORDS)
        )
        self._exclude_keywords: list[str] = (
            self._config.filters.keywords_exclude or []
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape_career_page(
        self, source: ScrapeSource
    ) -> list[RawListing]:
        """Scrape a single career page for internship listings.

        Args:
            source: A ScrapeSource from config with company, url, is_faang_plus.

        Returns:
            List of RawListing objects discovered from the page.
        """
        logger.info("Scraping career page for %s: %s", source.company, source.url)

        # Respect robots.txt
        allowed = await self.check_robots_txt(source.url)
        if not allowed:
            logger.warning(
                "Blocked by robots.txt for %s — skipping", source.url
            )
            return []

        try:
            html = await self._fetch_page(source.url)
        except Exception:
            logger.exception(
                "Failed to fetch career page for %s", source.company
            )
            return []

        if not html:
            logger.warning("Empty response from %s", source.url)
            return []

        # Randomized delay between scrapes
        await asyncio.sleep(random.uniform(1, 3))

        soup = BeautifulSoup(html, "lxml")
        listings = self._extract_listings(soup, source)
        logger.info(
            "Found %d intern listings on %s career page",
            len(listings),
            source.company,
        )
        return listings

    async def check_robots_txt(self, base_url: str) -> bool:
        """Check if our User-Agent is allowed by robots.txt.

        Args:
            base_url: The URL whose domain we check robots.txt for.

        Returns:
            True if scraping is allowed or robots.txt doesn't exist.
        """
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        domain = parsed.netloc

        await self._rate_limiter.wait(domain)

        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=10.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(robots_url)

            if resp.status_code != 200:
                # No robots.txt or error fetching — allow by default
                return True

            return self._parse_robots_txt(resp.text)

        except (httpx.HTTPError, httpx.TimeoutException):
            # If we can't fetch robots.txt, assume allowed
            logger.debug(
                "Could not fetch robots.txt for %s — assuming allowed", domain
            )
            return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _fetch_page(self, url: str) -> str:
        """Fetch a URL with retries and rate limiting.

        Returns the response text body.
        """
        domain = urlparse(url).netloc
        await self._rate_limiter.wait(domain)

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    def _extract_listings(
        self, soup: BeautifulSoup, source: ScrapeSource
    ) -> list[RawListing]:
        """Parse HTML and extract internship-related links.

        Looks for <a> tags whose text or href contains intern keywords.
        Also searches common job listing container patterns.
        """
        results: list[RawListing] = []
        seen_urls: set[str] = set()

        base_url = source.url
        company_slug = re.sub(r"[^a-z0-9]+", "-", source.company.lower()).strip("-")

        # Strategy 1: Find all <a> tags with intern keywords in text or href
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            link_text = anchor.get_text(strip=True)

            # Combine text + href for keyword matching
            searchable = f"{link_text} {href}".lower()

            if not self._matches_intern_keywords(searchable):
                continue

            if self._matches_exclude_keywords(searchable):
                continue

            # Resolve relative URLs
            full_url = urljoin(base_url, href)

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Try to extract location from nearby elements
            location = self._extract_nearby_location(anchor)

            listing = RawListing(
                company=source.company,
                company_slug=company_slug,
                title=link_text or "Unknown Role",
                location=location,
                url=full_url,
                source="scrape",
                is_faang_plus=source.is_faang_plus,
                raw_data={"link_text": link_text, "href": href},
            )
            results.append(listing)

        # Strategy 2: Look for common job listing containers
        # (div/li with class containing "job", "position", "opening", "listing")
        job_containers = soup.find_all(
            ["div", "li", "article", "tr"],
            class_=re.compile(
                r"job|position|opening|listing|posting|career|role|opportunity",
                re.IGNORECASE,
            ),
        )

        for container in job_containers:
            text = container.get_text(" ", strip=True).lower()
            if not self._matches_intern_keywords(text):
                continue
            if self._matches_exclude_keywords(text):
                continue

            # Find the first link inside this container
            link = container.find("a", href=True)
            if not link:
                continue

            full_url = urljoin(base_url, link["href"])
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            title = link.get_text(strip=True)
            if not title:
                # Try the first heading or strong tag
                heading = container.find(["h1", "h2", "h3", "h4", "strong"])
                title = heading.get_text(strip=True) if heading else "Unknown Role"

            location = self._extract_location_from_container(container)

            listing = RawListing(
                company=source.company,
                company_slug=company_slug,
                title=title,
                location=location,
                url=full_url,
                source="scrape",
                is_faang_plus=source.is_faang_plus,
                raw_data={"container_text": text[:500]},
            )
            results.append(listing)

        return results

    def _matches_intern_keywords(self, text: str) -> bool:
        """Check if text contains any intern-related keywords."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self._intern_keywords)

    def _matches_exclude_keywords(self, text: str) -> bool:
        """Check if text contains any excluded keywords (senior, staff, etc.)."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self._exclude_keywords)

    def _extract_nearby_location(self, anchor) -> str:
        """Try to find a location string near an anchor element.

        Looks at parent and sibling elements for location-like text.
        """
        # Check parent for location elements
        parent = anchor.parent
        if parent:
            # Common patterns: a sibling span/div with class "location"
            loc_el = parent.find(
                ["span", "div", "p"],
                class_=re.compile(r"location|city|place|region", re.IGNORECASE),
            )
            if loc_el:
                return loc_el.get_text(strip=True)

            # Check grandparent too
            grandparent = parent.parent
            if grandparent:
                loc_el = grandparent.find(
                    ["span", "div", "p"],
                    class_=re.compile(
                        r"location|city|place|region", re.IGNORECASE
                    ),
                )
                if loc_el:
                    return loc_el.get_text(strip=True)

        return "Unknown"

    def _extract_location_from_container(self, container) -> str:
        """Extract location from a job listing container element."""
        loc_el = container.find(
            ["span", "div", "p", "td"],
            class_=re.compile(r"location|city|place|region", re.IGNORECASE),
        )
        if loc_el:
            return loc_el.get_text(strip=True)

        # Look for text that looks like "City, ST" pattern
        text = container.get_text(" ", strip=True)
        match = re.search(
            r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2})", text
        )
        if match:
            return match.group(1)

        return "Unknown"

    def _parse_robots_txt(self, content: str) -> bool:
        """Simple robots.txt parser. Returns True if our agent is allowed.

        Checks User-Agent blocks for our bot name. Defaults to allowing
        if no specific Disallow rules match.
        """
        lines = content.strip().splitlines()
        applies_to_us = False
        applies_to_all = False

        # Two passes: first check for our specific user-agent, then wildcard
        for line in lines:
            line = line.strip()
            if line.startswith("#") or not line:
                continue

            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip().lower()
                if "internshiptracker" in agent:
                    applies_to_us = True
                    applies_to_all = False
                elif agent == "*":
                    if not applies_to_us:
                        applies_to_all = True
                else:
                    applies_to_us = False
                    applies_to_all = False
            elif (applies_to_us or applies_to_all) and line.lower().startswith(
                "disallow:"
            ):
                path = line.split(":", 1)[1].strip()
                if path == "/" or path == "/*":
                    return False

        return True


# ======================================================================
# GitHub Repo Monitor
# ======================================================================


async def monitor_github_repo(monitor: GitHubMonitor) -> list[RawListing]:
    """Monitor a GitHub repo's README for new internship listings.

    Fetches the raw README markdown, parses tables for job listings,
    diffs against previously seen URLs (stored in data/monitor_state.json),
    and returns only newly added entries.

    Args:
        monitor: A GitHubMonitor config with repo, branch, file.

    Returns:
        List of RawListing objects for newly discovered entries.
    """
    raw_url = (
        f"https://raw.githubusercontent.com/{monitor.repo}"
        f"/{monitor.branch}/{monitor.file}"
    )

    logger.info(
        "Monitoring GitHub repo %s (branch: %s, file: %s)",
        monitor.repo,
        monitor.branch,
        monitor.file,
    )

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            resp = await client.get(raw_url)
            resp.raise_for_status()
            content = resp.text
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Failed to fetch %s — HTTP %d", raw_url, exc.response.status_code
        )
        return []
    except (httpx.HTTPError, httpx.TimeoutException):
        logger.exception("Error fetching GitHub repo %s", monitor.repo)
        return []

    # Parse markdown tables for job listings
    current_entries = _parse_readme_table(content, monitor.repo)

    # Load previous state
    state_path = PROJECT_ROOT / "data" / "monitor_state.json"
    previous_urls = _load_monitor_state(state_path, monitor.repo)

    # Diff: only new entries
    current_urls = {entry["url"] for entry in current_entries}
    new_urls = current_urls - previous_urls

    new_listings: list[RawListing] = []
    for entry in current_entries:
        if entry["url"] in new_urls:
            company_slug = re.sub(
                r"[^a-z0-9]+", "-", entry["company"].lower()
            ).strip("-")
            listing = RawListing(
                company=entry["company"],
                company_slug=company_slug,
                title=entry["role"],
                location=entry.get("location", "Unknown"),
                url=entry["url"],
                source="github_monitor",
                is_faang_plus=False,
                raw_data={
                    "source_repo": monitor.repo,
                    "branch": monitor.branch,
                },
            )
            new_listings.append(listing)

    # Save updated state
    _save_monitor_state(state_path, monitor.repo, current_urls)

    logger.info(
        "GitHub monitor %s: %d total entries, %d new",
        monitor.repo,
        len(current_entries),
        len(new_listings),
    )
    return new_listings


def _parse_readme_table(content: str, repo_name: str) -> list[dict]:
    """Parse markdown tables from a README to extract job listing rows.

    Handles both markdown links [text](url) and HTML links <a href="url">.
    Carries forward company names for continuation rows (↳ prefix).

    Returns a list of dicts with keys: company, role, location, url.
    """
    entries: list[dict] = []
    last_company = ""

    # Match markdown table rows (lines starting and ending with |)
    table_row_pattern = re.compile(r"^\|(.+)\|$", re.MULTILINE)

    for match in table_row_pattern.finditer(content):
        row = match.group(1)
        cells = [c.strip() for c in row.split("|")]

        # Skip header/separator rows
        if not cells or all(
            c.startswith("-") or c.startswith(":") or not c for c in cells
        ):
            continue

        # Need at least 3 cells (company, role, location or link)
        if len(cells) < 3:
            continue

        # Try to find an apply URL in cells (search right-to-left so the
        # "Application/Apply" column is found before the company-name link).
        # Supports both markdown [text](url) and HTML <a href="url">.
        apply_url = None
        for cell in reversed(cells):
            md_match = re.search(r"\[([^\]]*)\]\((https?://[^)]+)\)", cell)
            if md_match:
                apply_url = md_match.group(2)
                break
            html_match = re.search(r'href="(https?://[^"]+)"', cell)
            if html_match:
                apply_url = html_match.group(1)
                break

        if not apply_url:
            continue

        # Extract company from first cell (strip formatting)
        company = _strip_markup(cells[0])

        # Handle continuation rows (↳ = same company, different role)
        if not company or company == "↳":
            company = last_company
        else:
            last_company = company

        if not company:
            continue

        # Extract role from second cell if available
        role = _strip_markup(cells[1]) if len(cells) > 1 else "Unknown Role"

        # Extract location from third cell if available
        location = _strip_markup(cells[2]) if len(cells) > 2 else "Unknown"

        # Skip obviously non-job rows (like header, legend)
        if company.lower() in ("company", "symbol", "legend", "---"):
            continue

        entries.append(
            {
                "company": company,
                "role": role,
                "location": location,
                "url": apply_url,
            }
        )

    return entries


def _strip_markup(text: str) -> str:
    """Remove markdown and HTML formatting from a string."""
    # Remove HTML tags but keep inner text
    text = re.sub(r"<[^>]+>", "", text)
    # Remove bold/italic markdown
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Remove markdown links, keeping text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Remove emoji
    text = re.sub(
        r"[\U0001f300-\U0001f9ff\u2600-\u26ff\u2700-\u27bf\U0001fa00-\U0001faff]+",
        "",
        text,
    )
    # Remove leading/trailing whitespace and special chars
    text = text.strip().strip("↳").strip()
    return text


def _load_monitor_state(
    state_path: Path, repo: str
) -> set[str]:
    """Load previously seen URLs for a monitored repo.

    Args:
        state_path: Path to monitor_state.json.
        repo: The repo identifier (e.g., "SimplifyJobs/Summer2026-Internships").

    Returns:
        Set of previously seen URLs.
    """
    if not state_path.exists():
        return set()

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return set(state.get(repo, {}).get("urls", []))
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not load monitor state from %s", state_path)
        return set()


def _save_monitor_state(
    state_path: Path, repo: str, current_urls: set[str]
) -> None:
    """Save current URLs for a monitored repo to state file.

    Merges with existing state for other repos.

    Args:
        state_path: Path to monitor_state.json.
        repo: The repo identifier.
        current_urls: Set of all URLs currently in the repo's README.
    """
    state: dict = {}
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read existing monitor state — overwriting")
            state = {}

    state[repo] = {
        "urls": sorted(current_urls),
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }

    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    logger.debug("Saved monitor state for %s (%d URLs)", repo, len(current_urls))

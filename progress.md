# Project Progress -- Atlanta Tech Internships

**Repo**: https://github.com/ctsc/atlanta-tech-internships-2026
**Owner**: Carter
**Python**: 3.12+
**AI Backend**: Google Gemini 2.0 Flash (free tier)

---

## Phase 1: Foundation -- COMPLETE

Data models, configuration, and project scaffold.

**Key files created:**
- `scripts/utils/models.py` -- Pydantic v2 models (RoleCategory, SponsorshipStatus, ListingStatus, ATSType, InternSeason, Company, JobListing, JobsDatabase, RawListing)
- `scripts/utils/config.py` -- YAML config loader with validation
- `config.yaml` -- All discovery sources, filters, Georgia focus settings
- `data/jobs.json`, `data/archived.json`, `data/companies.json` -- Data files
- `requirements.txt`, `LICENSE` (MIT), `.gitignore`

**Tests:** 93 (test_models.py: 47, test_config.py: 46)

---

## Phase 2: Discovery Engine -- COMPLETE

ATS API clients, web scraper, and discovery orchestrator.

**Key files created:**
- `scripts/utils/ats_clients.py` -- Greenhouse, Lever, and Ashby async API clients with rate limiting and retry logic
- `scripts/utils/scraper.py` -- Generic career page scraper (httpx + BeautifulSoup)
- `scripts/discover.py` -- Main discovery orchestrator; runs all sources in parallel with asyncio, isolates errors per source

**Tests:** 61 (test_discover.py: 61) | **Running total:** 154

---

## Phase 3: AI Validation + Deduplication -- COMPLETE

Gemini-powered validation, metadata enrichment, and duplicate detection.

**Key files created:**
- `scripts/utils/ai_enrichment.py` -- Gemini API integration with response caching and budget cap (200 calls/run)
- `scripts/validate.py` -- Validates raw listings as real internships, rejects low-confidence results (<0.7)
- `scripts/deduplicate.py` -- SHA-256 content hash dedup, URL dedup, and fuzzy matching (thefuzz)

**Tests:** 177 (test_ai_enrichment.py: 57, test_validate.py: 71, test_deduplicate.py: 49) | **Running total:** 331

---

## Phase 4: README Generation + Link Checking + Archival -- COMPLETE

Output generation, link health monitoring, and stale listing cleanup.

**Key files created:**
- `scripts/utils/readme_renderer.py` -- Markdown table renderer with emoji indicators, stats table, and legend
- `scripts/generate_readme.py` -- Loads jobs.json and writes README.md
- `scripts/check_links.py` -- Async HEAD requests with 2-consecutive-failure requirement before closing
- `scripts/archive_stale.py` -- Moves closed (>7 days) and stale (>120 days) listings to archived.json

**Tests:** 135 (test_generate_readme.py: 62, test_check_links.py: 43, test_archive_stale.py: 30) | **Running total:** 466

---

## Phase 5: Community Submissions + GitHub Integration -- COMPLETE

Issue-based submissions, GitHub Actions workflow, and contributing guide.

**Key files created:**
- `.github/workflows/update.yml` -- Cron workflow (every 6 hours) + manual trigger + issue trigger
- `.github/ISSUE_TEMPLATE/new-internship.yml` -- Structured issue form for community submissions
- `scripts/utils/github_utils.py` -- GitHub API helpers (fetch issues, comment, close)
- `scripts/process_issues.py` -- Parses issue form data, validates, adds to jobs.json, comments and closes
- `CONTRIBUTING.md` -- How to submit listings via issue template

**Tests:** 83 (test_github_utils.py: 27, test_process_issues.py: 56) | **Running total:** 549

---

## Phase 6: Integration Testing + Polish -- COMPLETE

CLI entry point, linting, and final integration.

**Key files created:**
- `main.py` -- CLI entry point with argparse (`--full`, `--discover-only`, `--readme-only`, `--check-links-only`)
- `progress.md` -- This file

**Work completed:**
- Full pipeline integration verified (discover -> validate -> deduplicate -> check_links -> archive_stale -> generate_readme)
- Ruff linting pass across all source and test files
- Docstrings and type hints verified on all modules

---

## Multi-Season Refactoring

The project was originally scoped as "Summer 2026 Tech Internships" but was expanded to support multiple internship seasons via the `InternSeason` enum in `scripts/utils/models.py`:

| Season | Enum Value |
|--------|------------|
| Summer 2026 | `summer_2026` |
| Fall 2026 | `fall_2026` |
| Spring 2027 | `spring_2027` |
| Summer 2027 | `summer_2027` |

Active seasons are configured in `config.yaml` under `project.active_seasons`. The project name was rebranded to **"Atlanta Tech Internships"** to reflect the broader scope and geographic focus on Georgia.

Filter keywords in `config.yaml` were expanded to match all active seasons (e.g., "fall 2026", "spring 27", "summer 2027").

---

## Final Stats

| Metric | Count |
|--------|-------|
| Total tests | 549+ |
| Source files (scripts/) | 14 |
| Test files (tests/) | 11 |
| Greenhouse boards configured | 118 |
| Lever boards configured | 22 |
| Ashby boards configured | 18 |
| Scrape sources configured | 39 |
| **Total companies configured** | **197** |
| Georgia-focused employers | 14 |

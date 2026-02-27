# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

**Repo**: https://github.com/ctsc/atlanta-tech-internships-2026
**Owner**: Carter
**Python**: 3.12+ required
**Status**: Pre-build — project is in specification phase, no code implemented yet

### Build Commands (once project is scaffolded)
```bash
pip install -r requirements.txt          # Install dependencies
python -m pytest tests/                  # Run all tests
python -m pytest tests/test_models.py    # Run a single test file
python -m pytest tests/ -k "test_name"   # Run a specific test
python main.py --full                    # Run full pipeline
python main.py --discover-only           # Discovery only
python main.py --readme-only             # Regenerate README only
python main.py --check-links-only        # Link checking only
ruff check scripts/ tests/               # Lint
```

### Architecture Overview
Multi-phase pipeline that runs every 6 hours via GitHub Actions:
1. **Discover** (`scripts/discover.py`) — Scrape Greenhouse/Lever/Ashby APIs + career pages
2. **Validate** (`scripts/validate.py`) — Gemini AI confirms listings are real Summer 2026 internships
3. **Deduplicate** (`scripts/deduplicate.py`) — Content-hash + fuzzy dedup
4. **Check Links** (`scripts/check_links.py`) — Async HEAD requests to verify apply URLs
5. **Archive** (`scripts/archive_stale.py`) — Move closed/stale listings to `data/archived.json`
6. **Generate README** (`scripts/generate_readme.py`) — Render `data/jobs.json` → `README.md`
7. **Process Issues** (`scripts/process_issues.py`) — Ingest community submissions from GitHub Issues

Data flows: ATS APIs/scraping → `data/jobs.json` (source of truth) → `README.md` (public face)

### Key Conventions
- **Data models**: Pydantic v2 in `scripts/utils/models.py` — all data must go through these
- **Config**: `config.yaml` loaded via `scripts/utils/config.py` — never hardcode company lists or API settings
- **HTTP**: Always use `httpx.AsyncClient`, never `requests`. Rate limit to 2 req/sec per domain
- **Logging**: Python `logging` module only, never `print()`
- **Error isolation**: One source failing must never crash the entire pipeline run
- **Secrets**: Environment variables only (`GEMINI_API_KEY`, `GITHUB_TOKEN`). `.env` is gitignored. See `.env.example`
- **Geographic focus**: Heavy emphasis on Georgia (Atlanta, Alpharetta, statewide) internships

### Data Files
- `data/jobs.json` — Source of truth for all active listings
- `data/archived.json` — Closed/expired listings
- `data/companies.json` — Company metadata (ATS type, career page URL)
- `data/link_health.json` — Tracks consecutive link failures (2 failures required before marking closed)
- `data/.cache/` — Gemini API response cache (keyed by content hash)

### Testing
- Framework: `pytest` + `pytest-asyncio`
- Mock all HTTP calls and Gemini API responses in tests
- Target: 80%+ coverage per module

---

## Full Project Specification

> **Architecture**: Multi-phase Ralph Wiggum loop with Claude Code
> **Goal**: Build the entire project autonomously. Zero manual steps after initial setup.

github repo link: https://github.com/ctsc/atlanta-tech-internships-2026

---

## 1. PROJECT VISION

Build a GitHub repository that automatically discovers, validates, and publishes Summer 2026 tech internship listings. The repo auto-updates every 6 hours via GitHub Actions, with Gemini AI handling discovery, enrichment, deduplication, and README generation. The end result is a beautifully maintained public resource that rivals SimplifyJobs/Summer2026-Internships — but fully automated.

I want a specific way to specify tech internships opn in Georgia -- this is essential and I also want a heavy focus in general locations like Atlanta and Alpheretta and entirely the state of Georgia, USA

### Key Differentiators vs Simplify
- **Auto-updated every 6 hours** (not dependent on community PRs)
- **AI-verified links** — dead links auto-removed each cycle
- **Structured metadata** — sponsorship, remote policy, tech stack extracted by AI
- **Categorized by role type** — SWE, ML/AI, Data Science, Quant, PM, Hardware
- **Stale posting cleanup** — auto-archived when listings close
- **Freshness timestamps** — users always know when data was last verified

---

## 2. REPO STRUCTURE (Build This Exactly)

```
summer2026-internships/
├── README.md                          # Auto-generated master table (THE public face)
├── CONTRIBUTING.md                    # How humans can submit via Issues
├── LICENSE                            # MIT
├── .github/
│   ├── workflows/
│   │   └── update.yml                 # GitHub Actions cron — runs every 6hrs
│   └── ISSUE_TEMPLATE/
│       └── new-internship.yml         # Structured issue form for community submissions
├── data/
│   ├── jobs.json                      # Source of truth — all listings
│   ├── companies.json                 # Company metadata (ATS type, career page URL)
│   └── archived.json                  # Closed/expired listings
├── scripts/
│   ├── discover.py                    # Phase 1: Scrape & discover new listings
│   ├── validate.py                    # Phase 2: Gemini validates & enriches
│   ├── deduplicate.py                 # Phase 3: Content-hash dedup
│   ├── generate_readme.py             # Phase 4: Render JSON → markdown tables
│   ├── check_links.py                 # Phase 5: Verify all apply links still work
│   ├── archive_stale.py              # Phase 6: Move closed listings to archived.json
│   ├── process_issues.py             # Phase 7: Ingest community-submitted issues
│   └── utils/
│       ├── __init__.py
│       ├── ats_clients.py            # Greenhouse, Lever, Ashby, Workday API clients
│       ├── scraper.py                # Generic career page scraper
│       ├── ai_enrichment.py          # Gemini API calls for enrichment
│       ├── models.py                 # Pydantic models for all data structures
│       ├── readme_renderer.py        # Markdown table generation logic
│       ├── github_utils.py           # GitHub API helpers (issues, commits)
│       └── config.py                 # Load config.yaml
├── config.yaml                        # All configuration — sources, filters, API settings
├── requirements.txt                   # Python dependencies
├── tests/
│   ├── test_discover.py
│   ├── test_validate.py
│   ├── test_deduplicate.py
│   ├── test_generate_readme.py
│   ├── test_models.py
│   └── conftest.py                   # Shared fixtures
├── PRD.md                            # Product Requirements Document for Ralph
└── progress.md                       # Ralph tracks completed work here
```

---

## 3. DATA MODELS (Pydantic — `scripts/utils/models.py`)

These models are the backbone. Get them right first.

```python
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Literal
from datetime import datetime, date
from enum import Enum

class RoleCategory(str, Enum):
    SWE = "swe"
    ML_AI = "ml_ai"
    DATA_SCIENCE = "data_science"
    QUANT = "quant"
    PM = "pm"
    HARDWARE = "hardware"
    OTHER = "other"

class SponsorshipStatus(str, Enum):
    SPONSORS = "sponsors"
    NO_SPONSORSHIP = "no_sponsorship"
    US_CITIZENSHIP = "us_citizenship"
    UNKNOWN = "unknown"

class ListingStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"

class ATSType(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    SMARTRECRUITERS = "smartrecruiters"
    ICIMS = "icims"
    CUSTOM = "custom"

class Company(BaseModel):
    name: str
    slug: str                              # kebab-case identifier
    careers_url: Optional[HttpUrl] = None
    ats_type: Optional[ATSType] = None
    ats_identifier: Optional[str] = None   # e.g., greenhouse board token
    is_faang_plus: bool = False            # 🔥 indicator

class JobListing(BaseModel):
    id: str                                # content hash of (company + role + location)
    company: str
    company_slug: str
    role: str
    category: RoleCategory
    locations: list[str]                   # ["SF", "Remote", "NYC"]
    apply_url: HttpUrl
    sponsorship: SponsorshipStatus = SponsorshipStatus.UNKNOWN
    requires_us_citizenship: bool = False
    is_faang_plus: bool = False
    requires_advanced_degree: bool = False  # Master's/PhD
    remote_friendly: bool = False
    date_added: date
    date_last_verified: date
    source: str                            # "greenhouse_api", "lever_api", "scrape", "community"
    status: ListingStatus = ListingStatus.OPEN
    tech_stack: list[str] = []             # ["Python", "React", "AWS"]
    season: str = "summer_2026"

class JobsDatabase(BaseModel):
    listings: list[JobListing]
    last_updated: datetime
    total_open: int = 0
    
    def compute_stats(self):
        self.total_open = len([j for j in self.listings if j.status == ListingStatus.OPEN])
```

---

## 4. CONFIGURATION (`config.yaml`)

```yaml
project:
  name: "Summer 2026 Tech Internships"
  season: "summer_2026"
  github_repo: "carter/summer2026-internships"

# ── ATS API Sources ──────────────────────────────────────────────
# These are companies with known Greenhouse/Lever/Ashby boards
# The discover script hits these APIs directly (no scraping needed)
greenhouse_boards:
  - token: "anthropic"
    company: "Anthropic"
    is_faang_plus: false
  - token: "stripe"
    company: "Stripe"
    is_faang_plus: false
  - token: "figma"
    company: "Figma"
    is_faang_plus: false
  - token: "notion"
    company: "Notion"
    is_faang_plus: false
  - token: "vercel"
    company: "Vercel"
    is_faang_plus: false
  - token: "ramp"
    company: "Ramp"
    is_faang_plus: false
  - token: "coinbase"
    company: "Coinbase"
    is_faang_plus: false
  - token: "openai"
    company: "OpenAI"
    is_faang_plus: true
  - token: "datadog"
    company: "Datadog"
    is_faang_plus: false
  - token: "plaid"
    company: "Plaid"
    is_faang_plus: false
  - token: "scaleai"
    company: "Scale AI"
    is_faang_plus: false
  - token: "brex"
    company: "Brex"
    is_faang_plus: false
  - token: "discord"
    company: "Discord"
    is_faang_plus: false
  - token: "palantir"
    company: "Palantir"
    is_faang_plus: false
  # Add 50+ more — Claude should expand this list significantly

lever_boards:
  - company_slug: "netflix"
    company: "Netflix"
    is_faang_plus: true
  # Add more Lever companies

ashby_boards:
  - company_slug: "zip"
    company: "Zip"
    is_faang_plus: false
  # Add more Ashby companies

# ── Workday / Custom Scrape Sources ──────────────────────────────
# These require scraping (no clean API)
scrape_sources:
  - company: "Google"
    url: "https://www.google.com/about/careers/applications/jobs/results/?q=intern+software+engineer"
    is_faang_plus: true
  - company: "Microsoft"
    url: "https://careers.microsoft.com/"
    is_faang_plus: true
  - company: "Amazon"
    url: "https://amazon.jobs/en/search?base_query=intern+software"
    is_faang_plus: true
  - company: "Apple"
    url: "https://jobs.apple.com/"
    is_faang_plus: true
  - company: "Meta"
    url: "https://www.metacareers.com/jobs"
    is_faang_plus: true
  # Add more — prioritize top companies students care about

# ── GitHub Repo Monitors ─────────────────────────────────────────
# Monitor other repos for new additions (diff against last run)
github_monitors:
  - repo: "SimplifyJobs/Summer2026-Internships"
    branch: "dev"
    file: "README.md"

# ── Filtering ─────────────────────────────────────────────────────
filters:
  keywords_include:
    - "intern"
    - "internship"
    - "co-op"
    - "coop"
    - "summer 2026"
    - "summer 26"
  keywords_exclude:
    - "senior"
    - "staff"
    - "principal"
    - "director"
    - "manager"
    - "lead engineer"
  role_categories:
    swe: ["software engineer", "software developer", "backend", "frontend", "full stack", "fullstack", "web developer", "mobile engineer", "ios engineer", "android engineer", "platform engineer", "infrastructure engineer", "devops", "sre", "site reliability"]
    ml_ai: ["machine learning", "ml engineer", "ai engineer", "deep learning", "nlp", "computer vision", "data scientist", "research engineer", "research scientist"]
    data_science: ["data analyst", "data engineer", "business intelligence", "analytics"]
    quant: ["quantitative", "quant", "algorithmic trading", "systematic"]
    pm: ["product manager", "program manager", "technical program manager", "tpm"]
    hardware: ["hardware engineer", "embedded", "firmware", "fpga", "asic", "chip design", "electrical engineer"]
  exclude_companies:
    - "Revature"
    - "Infosys"
    - "Wipro"
    - "TCS"
    - "Cognizant"

# ── AI Enrichment ─────────────────────────────────────────────────
ai:
  model: "gemini-2.0-flash"
  max_tokens: 1024
  enrichment_prompt: |
    Analyze this job listing and extract structured metadata.
    Return JSON only, no markdown, no explanation.
    {
      "is_internship": true/false,
      "is_summer_2026": true/false,
      "category": "swe|ml_ai|data_science|quant|pm|hardware|other",
      "locations": ["city, state abbreviation"],
      "sponsorship": "sponsors|no_sponsorship|us_citizenship|unknown",
      "requires_advanced_degree": true/false,
      "remote_friendly": true/false,
      "tech_stack": ["Python", "React", ...],
      "confidence": 0.0-1.0
    }

# ── Schedule ──────────────────────────────────────────────────────
schedule:
  update_interval_hours: 6
  link_check_interval_hours: 24
  archive_after_days: 7  # days after link goes dead
```

---

## 5. SCRIPT SPECIFICATIONS

### 5.1 `scripts/discover.py` — Discovery Engine

**Purpose**: Find new internship listings from all configured sources.

**Implementation Details**:

```
FUNCTION discover_all() -> list[RawListing]:
    results = []
    
    # 1. Greenhouse API
    for board in config.greenhouse_boards:
        GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs
        Filter by title keywords (intern/internship/co-op)
        Filter out excluded keywords (senior, staff, etc.)
        Extract: title, location, absolute_url, updated_at
        Append to results
    
    # 2. Lever API  
    for board in config.lever_boards:
        GET https://api.lever.co/v0/postings/{company_slug}
        Same filtering logic
        Extract: text (title), categories.location, hostedUrl
        Append to results
    
    # 3. Ashby API
    for board in config.ashby_boards:
        POST https://jobs.ashbyhq.com/api/non-user-graphql
        Query: {jobBoard {jobs {title, locationName, applicationUrl}}}
        Same filtering
        Append to results
    
    # 4. Web scraping (for Workday/custom sites)
    for source in config.scrape_sources:
        Use httpx + BeautifulSoup
        Respect robots.txt
        Extract job listing data
        Append to results
    
    # 5. GitHub repo monitoring
    for monitor in config.github_monitors:
        Fetch raw README content
        Parse markdown table
        Diff against last known state (stored in data/monitor_state.json)
        Extract new entries only
        Append to results
    
    return results
```

**Critical Requirements**:
- Rate limit all requests: max 2 requests/second per domain
- Randomized delays between 1-3 seconds
- User-Agent header: "InternshipTracker/1.0 (github.com/carter/summer2026-internships)"
- Retry with exponential backoff (3 attempts max)
- Log every request with timestamp and status code
- Never crash on a single failed source — isolate errors per source
- Save raw discovery results to `data/raw_discovery_{timestamp}.json` for debugging

### 5.2 `scripts/validate.py` — AI Validation & Enrichment

**Purpose**: Use Claude to validate each listing is a real Summer 2026 internship and extract metadata.

**Implementation Details**:

```
FUNCTION validate_and_enrich(raw_listings: list[RawListing]) -> list[JobListing]:
    validated = []
    
    for listing in raw_listings:
        # Skip if already in jobs.json (by content hash)
        if listing.content_hash in existing_hashes:
            continue
        
        # Call Gemini API with the enrichment prompt from config
        response = call_gemini(
            system=config.ai.enrichment_prompt,
            user=f"Company: {listing.company}\nTitle: {listing.title}\nLocation: {listing.location}\nURL: {listing.url}"
        )
        
        metadata = parse_json(response)
        
        # Reject if not an internship or not summer 2026
        if not metadata.is_internship or not metadata.is_summer_2026:
            log(f"Rejected: {listing.title} at {listing.company} — not a valid summer 2026 internship")
            continue
        
        # Reject if confidence < 0.7
        if metadata.confidence < 0.7:
            log(f"Low confidence ({metadata.confidence}): {listing.title} — skipping")
            continue
        
        # Build JobListing from raw + enriched data
        job = JobListing(
            id=listing.content_hash,
            company=listing.company,
            role=listing.title,
            category=metadata.category,
            locations=metadata.locations,
            apply_url=listing.url,
            sponsorship=metadata.sponsorship,
            # ... etc
        )
        validated.append(job)
    
    return validated
```

**Critical Requirements**:
- Batch Gemini API calls: process in groups of 10 with 1-second delays between batches
- Total API budget per run: max 200 calls (safety cap)
- Cache Claude responses locally to avoid re-processing on retry
- If Gemini API is down, skip validation but don't lose raw data

### 5.3 `scripts/deduplicate.py` — Deduplication

**Purpose**: Prevent duplicate listings from appearing.

**Dedup Strategy**:
1. **Primary key**: SHA-256 hash of `lowercase(company) + lowercase(role_title) + sorted(locations)`
2. **Fuzzy match**: If company names are similar (Levenshtein distance < 3) AND role titles are similar (> 80% token overlap), flag as potential duplicate
3. **URL dedup**: Same apply_url = same listing, always
4. **Repost detection**: If a company re-lists the same role (same title, same location) after it was archived, treat as new listing with note "re-posted"

### 5.4 `scripts/generate_readme.py` — README Generator

**Purpose**: Transform jobs.json into the beautiful README.md.

**Output Format** (match Simplify's proven format):

```markdown
# Summer 2026 Tech Internships 🚀

> 🤖 **Auto-updated every 6 hours** | Last updated: {timestamp}
> 
> Built and maintained by [Carter](https://github.com/carter) | President, IEEE @ Georgia State

Use this repo to discover and track **Summer 2026 tech internships** across software engineering, ML/AI, data science, quant, and more.

---

### 📊 Stats

| Category | Open Roles |
|----------|-----------|
| 💻 [Software Engineering](#-software-engineering) | {count} |
| 🤖 [ML / AI / Data Science](#-ml--ai--data-science) | {count} |
| 📈 [Quantitative Finance](#-quantitative-finance) | {count} |
| 📱 [Product Management](#-product-management) | {count} |
| 🔧 [Hardware Engineering](#-hardware-engineering) | {count} |
| **Total** | **{total}** |

---

### Legend

| Symbol | Meaning |
|--------|---------|
| 🔥 | FAANG+ company |
| 🛂 | Does NOT offer sponsorship |
| 🇺🇸 | Requires U.S. Citizenship |
| 🔒 | Application closed |
| 🎓 | Advanced degree required |
| 🏠 | Remote friendly |

---

## 💻 Software Engineering

| Company | Role | Location | Apply | Date Added |
|---------|------|----------|-------|------------|
{for each SWE listing, sorted by date_added desc}
| {🔥 if faang} **{company}** | {role} {🛂🇺🇸🎓🏠 as applicable} | {locations joined} | [Apply]({url}) | {date} |

## 🤖 ML / AI / Data Science
{same table format}

## 📈 Quantitative Finance
{same table format}

## 📱 Product Management
{same table format}

## 🔧 Hardware Engineering
{same table format}

---

## How This Works

This repo is **automatically maintained by AI**. Every 6 hours:
1. Scripts scan 100+ company career pages and job board APIs
2. Gemini AI validates each listing is a real Summer 2026 internship
3. Dead links are detected and removed
4. The README is regenerated with fresh data

## Contributing

Found a listing we missed? [Submit an issue]({issue_template_url})!

---

⭐ **Star this repo** to stay updated!
```

**Critical Requirements**:
- Sort listings within each category by `date_added` (newest first)
- Closed listings (status=closed) get the 🔒 emoji and stay visible for 7 days, then move to archived
- Truncate locations to max 3, show "and {n} more" if > 3
- Company names should be bold
- The README must be valid markdown — test rendering before commit
- Include a "Last updated" timestamp in UTC

### 5.5 `scripts/check_links.py` — Link Health Checker

**Purpose**: Verify all apply URLs still return 200.

```
FUNCTION check_all_links():
    for listing in jobs.json where status == OPEN:
        response = HEAD request to listing.apply_url (with redirect following)
        
        if response.status == 200:
            listing.date_last_verified = today
        elif response.status in [404, 410, 403]:
            listing.status = CLOSED
            listing.date_closed = today
            log(f"CLOSED: {listing.company} — {listing.role}")
        elif response.status in [429, 500, 502, 503]:
            # Transient error — don't mark as closed
            log(f"TRANSIENT ERROR {response.status}: {listing.company}")
        else:
            # Unknown status — flag for review
            log(f"UNKNOWN {response.status}: {listing.company} — {listing.apply_url}")
```

**Critical Requirements**:
- Use HEAD requests (not GET) to minimize bandwidth
- Timeout: 10 seconds per request
- Parallelize with asyncio: max 10 concurrent checks
- Don't mark a link as dead on first failure — require 2 consecutive failures across 2 runs

### 5.6 `scripts/archive_stale.py` — Archival

- Move listings from `jobs.json` → `archived.json` when:
  - `status == CLOSED` AND `date_closed` was > 7 days ago
  - `date_added` > 120 days ago (stale even if link still works)
- Keep archived listings in `data/archived.json` for historical record
- Update counts in README

### 5.7 `scripts/process_issues.py` — Community Submissions

- Fetch open issues with label "new-internship"
- Parse structured issue form data
- Run through the same validation pipeline
- If valid: add to jobs.json, close issue with "✅ Added!" comment
- If invalid: close issue with explanation

---

## 6. GITHUB ACTIONS WORKFLOW (`.github/workflows/update.yml`)

```yaml
name: Update Internship Listings
on:
  schedule:
    - cron: '0 */6 * * *'      # Every 6 hours
  workflow_dispatch:             # Manual trigger
  issues:
    types: [opened, labeled]    # Trigger on new community submissions

permissions:
  contents: write
  issues: write

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Cache pip packages
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Discover new listings
        run: python scripts/discover.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        continue-on-error: true
      
      - name: Validate & enrich with Claude
        run: python scripts/validate.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        continue-on-error: true
      
      - name: Deduplicate
        run: python scripts/deduplicate.py
      
      - name: Check link health
        run: python scripts/check_links.py
        continue-on-error: true
      
      - name: Archive stale listings
        run: python scripts/archive_stale.py
      
      - name: Process community submissions
        if: github.event_name == 'issues'
        run: python scripts/process_issues.py
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Generate README
        run: python scripts/generate_readme.py
      
      - name: Commit & push
        run: |
          git config user.name "internship-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/ README.md
          if git diff --staged --quiet; then
            echo "No changes to commit"
          else
            STATS=$(python -c "import json; d=json.load(open('data/jobs.json')); print(f\"{len([j for j in d['listings'] if j['status']=='open'])} open roles\")")
            git commit -m "🔄 Update listings — $STATS — $(date -u +%Y-%m-%d)"
            git push
          fi
```

---

## 7. ISSUE TEMPLATE (`.github/ISSUE_TEMPLATE/new-internship.yml`)

```yaml
name: New Internship Submission
description: Submit an internship listing we missed
title: "[New] {Company} — {Role}"
labels: ["new-internship"]
body:
  - type: input
    id: company
    attributes:
      label: Company Name
      placeholder: e.g., Stripe
    validations:
      required: true
  - type: input
    id: role
    attributes:
      label: Role Title
      placeholder: e.g., Software Engineer Intern
    validations:
      required: true
  - type: input
    id: url
    attributes:
      label: Application URL
      placeholder: https://...
    validations:
      required: true
  - type: input
    id: location
    attributes:
      label: Location(s)
      placeholder: e.g., San Francisco, CA / Remote
    validations:
      required: true
  - type: dropdown
    id: category
    attributes:
      label: Role Category
      options:
        - Software Engineering
        - ML / AI / Data Science
        - Quantitative Finance
        - Product Management
        - Hardware Engineering
        - Other
    validations:
      required: true
  - type: checkboxes
    id: flags
    attributes:
      label: Additional Info
      options:
        - label: Offers visa sponsorship
        - label: Requires U.S. citizenship
        - label: Remote friendly
        - label: Requires advanced degree (Master's/PhD)
```

---

## 8. DEPENDENCIES (`requirements.txt`)

```
httpx>=0.27.0
beautifulsoup4>=4.12.0
pydantic>=2.5.0
google-genai>=1.0.0
pyyaml>=6.0
aiohttp>=3.9.0
tenacity>=8.2.0         # Retry logic
python-dateutil>=2.8.0
thefuzz>=0.22.0         # Fuzzy string matching for dedup
lxml>=5.0.0             # HTML parsing
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## 9. RALPH WIGGUM EXECUTION PLAN

This project is built in **6 phases** using Ralph Wiggum loops. Each phase runs as a separate `/ralph-loop` invocation. Complete them in order.

### Phase 1: Foundation (Data Models + Config + Project Scaffold)

```bash
/ralph-loop "
Read CLAUDE.md thoroughly. You are building Phase 1 of the Autonomous Internship Board.

TASKS:
1. Initialize the git repo with proper .gitignore (Python, IDE files, __pycache__, .env, *.pyc)
2. Create the full directory structure from Section 2 of CLAUDE.md
3. Implement scripts/utils/models.py EXACTLY as specified in Section 3 (Pydantic models)
4. Create config.yaml with ALL the configuration from Section 4 — expand the company lists to at least 80 Greenhouse boards, 20 Lever boards, 15 Ashby boards, and 30 scrape sources covering the most popular tech companies students want to work at
5. Create scripts/utils/config.py to load and validate config.yaml
6. Create requirements.txt from Section 8
7. Create LICENSE (MIT)
8. Write tests for all models in tests/test_models.py
9. Run tests — they must all pass

SUCCESS CRITERIA:
- All files from the directory structure exist
- models.py has all Pydantic models with proper validation
- config.yaml loads successfully with 100+ companies configured
- All tests pass
- No linter errors

After verifying all criteria, output <promise>PHASE1_DONE</promise>
" --max-iterations 25
```

### Phase 2: Discovery Engine

```bash
/ralph-loop "
Read CLAUDE.md Section 5.1. You are building Phase 2: the Discovery Engine.

TASKS:
1. Implement scripts/utils/ats_clients.py:
   - GreenhouseClient: hits boards-api.greenhouse.io/v1/boards/{token}/jobs
   - LeverClient: hits api.lever.co/v0/postings/{slug}
   - AshbyClient: hits jobs.ashbyhq.com GraphQL API
   - All clients use httpx with async support
   - All clients implement rate limiting (2 req/sec per domain)
   - All clients implement retry with tenacity (3 attempts, exponential backoff)
   - All clients filter by intern/internship keywords from config

2. Implement scripts/utils/scraper.py:
   - GenericScraper class using httpx + BeautifulSoup
   - Handles Workday-style career pages
   - Respects robots.txt
   - Randomized delays 1-3 seconds between requests
   - Proper User-Agent header

3. Implement scripts/discover.py:
   - Main entry point that orchestrates all clients
   - Runs all sources in parallel with asyncio
   - Isolates errors per source (one failure doesn't kill the run)
   - Saves raw results to data/raw_discovery_{timestamp}.json
   - Logs everything with structured logging (timestamp, source, count found)

4. Write tests:
   - tests/test_discover.py with mocked HTTP responses
   - Test each ATS client independently
   - Test error isolation (one source failing doesn't crash others)
   - Test rate limiting behavior

SUCCESS CRITERIA:
- discover.py runs without errors when called standalone
- Each ATS client handles 200, 404, 429, 500 responses gracefully
- Rate limiting is enforced
- Tests pass with >80% coverage on discovery code
- Raw output JSON is valid and matches RawListing schema

After verifying all criteria, output <promise>PHASE2_DONE</promise>
" --max-iterations 30
```

### Phase 3: AI Validation + Deduplication

```bash
/ralph-loop "
Read CLAUDE.md Sections 5.2 and 5.3. You are building Phase 3: Validation and Deduplication.

TASKS:
1. Implement scripts/utils/ai_enrichment.py:
   - Function: enrich_listing(raw_listing) -> EnrichedMetadata
   - Calls Gemini API with the enrichment prompt from config.yaml
   - Parses JSON response with error handling
   - Caches responses to data/.cache/ directory (keyed by content hash)
   - Budget cap: tracks API calls per run, stops at 200
   - Graceful degradation: if API is down, returns raw data without enrichment

2. Implement scripts/validate.py:
   - Loads raw discovery results
   - Loads existing jobs.json
   - For each new listing: call AI enrichment
   - Reject non-internships, non-summer-2026, low-confidence (<0.7)
   - Build JobListing objects from validated results
   - Append to jobs.json
   - Save updated jobs.json

3. Implement scripts/deduplicate.py:
   - Content hash dedup (primary): SHA-256 of company+role+locations
   - URL dedup: same apply_url = same listing
   - Fuzzy dedup: thefuzz library for similar company names + role titles
   - Log all dedup decisions

4. Write tests:
   - Mock Gemini API responses
   - Test validation logic (accept/reject scenarios)
   - Test dedup with known duplicates and near-duplicates
   - Test cache hit/miss behavior
   - Test budget cap enforcement

SUCCESS CRITERIA:
- validate.py processes a batch of raw listings and produces valid jobs.json
- Dedup correctly catches exact and fuzzy duplicates
- API budget cap is enforced
- Cache prevents redundant API calls
- All tests pass

After verifying all criteria, output <promise>PHASE3_DONE</promise>
" --max-iterations 30
```

### Phase 4: README Generation + Link Checking + Archival

```bash
/ralph-loop "
Read CLAUDE.md Sections 5.4, 5.5, 5.6. You are building Phase 4: Output generation.

TASKS:
1. Implement scripts/utils/readme_renderer.py:
   - Function: render_readme(jobs_db: JobsDatabase) -> str
   - Generates the EXACT markdown format from Section 5.4
   - Categories: SWE, ML/AI, Data Science, Quant, PM, Hardware
   - Proper emoji indicators (🔥🛂🇺🇸🔒🎓🏠)
   - Sort by date_added desc within each category
   - Stats table with counts per category
   - Legend table
   - Truncate locations to max 3

2. Implement scripts/generate_readme.py:
   - Load jobs.json
   - Call readme_renderer
   - Write to README.md
   - Validate markdown output (no broken tables)

3. Implement scripts/check_links.py:
   - Async HEAD requests to all open listing URLs
   - Max 10 concurrent requests
   - 10-second timeout
   - Mark CLOSED on 404/410/403
   - Don't mark dead on transient errors (429/5xx)
   - Require 2 consecutive failures before closing (track in data/link_health.json)

4. Implement scripts/archive_stale.py:
   - Move closed listings > 7 days to archived.json
   - Move listings > 120 days old to archived.json
   - Update jobs.json after archival

5. Write tests for all of the above.

SUCCESS CRITERIA:
- generate_readme.py produces valid, beautiful markdown matching the spec
- README renders correctly (test by checking for valid table syntax)
- Link checker handles all HTTP status codes correctly
- Archival logic works correctly with edge cases
- All tests pass

After verifying all criteria, output <promise>PHASE4_DONE</promise>
" --max-iterations 30
```

### Phase 5: Community Submissions + GitHub Integration

```bash
/ralph-loop "
Read CLAUDE.md Sections 6 and 7. You are building Phase 5: GitHub integration.

TASKS:
1. Create .github/workflows/update.yml EXACTLY as specified in Section 6
2. Create .github/ISSUE_TEMPLATE/new-internship.yml from Section 7
3. Implement scripts/process_issues.py:
   - Fetch open issues with 'new-internship' label via GitHub API
   - Parse structured issue form fields
   - Run through validation pipeline (same as validate.py)
   - If valid: add to jobs.json, comment '✅ Added!', close issue
   - If invalid: comment with reason, close issue
   - Use GITHUB_TOKEN from environment
4. Implement scripts/utils/github_utils.py:
   - Functions: fetch_issues(), comment_on_issue(), close_issue(), get_file_content()
   - All using httpx with GitHub API v3
5. Create CONTRIBUTING.md:
   - Explain how to submit via issue template
   - Explain the auto-validation process
   - Link to the issue template
6. Write tests for issue processing

SUCCESS CRITERIA:
- GitHub Actions workflow is valid YAML
- Issue template renders correctly
- process_issues.py handles valid and invalid submissions
- CONTRIBUTING.md is clear and helpful
- All tests pass

After verifying all criteria, output <promise>PHASE5_DONE</promise>
" --max-iterations 25
```

### Phase 6: Integration Testing + Polish

```bash
/ralph-loop "
You are building Phase 6: Final integration and polish.

TASKS:
1. Run the FULL pipeline end-to-end:
   - discover.py → validate.py → deduplicate.py → check_links.py → archive_stale.py → generate_readme.py
   - Fix any integration issues between scripts
   
2. Create a main.py entry point that runs the full pipeline:
   - python main.py --full (runs everything)
   - python main.py --discover-only
   - python main.py --readme-only
   - python main.py --check-links-only
   - Uses argparse

3. Seed the repo with REAL data:
   - Run discover.py against at least 20 real Greenhouse boards
   - Generate an initial README with actual listings
   - Commit the seeded data

4. Polish:
   - Ensure all scripts have proper docstrings
   - Ensure all functions have type hints
   - Run a linter (ruff) and fix all issues
   - Add logging throughout (use Python logging module, INFO level)
   - Add a progress.md documenting all completed phases

5. Final README review:
   - Ensure the generated README looks professional
   - Stats are accurate
   - Tables render correctly
   - All links are formatted properly

SUCCESS CRITERIA:
- Full pipeline runs end-to-end without errors
- main.py works with all CLI flags
- README contains real listings from real companies
- No linter errors
- All tests pass
- Code is clean, documented, and production-ready

After verifying all criteria, output <promise>PROJECT_COMPLETE</promise>
" --max-iterations 40
```

---

## 10. RALPH EXECUTION SCRIPT

Save this as `build.sh` and run it overnight:

```bash
#!/bin/bash
set -e

PROJECT_DIR="$(pwd)/summer2026-internships"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
git init

# Copy CLAUDE.md into the project
cp ../CLAUDE.md ./CLAUDE.md

echo "🚀 Starting Phase 1: Foundation..."
claude -p "/ralph-loop \"$(cat <<'PROMPT'
Read CLAUDE.md thoroughly. You are building Phase 1 of the Autonomous Internship Board.
[Phase 1 prompt from Section 9]
PROMPT
)\" --max-iterations 25"

echo "🚀 Starting Phase 2: Discovery Engine..."
claude -p "/ralph-loop \"$(cat <<'PROMPT'
Read CLAUDE.md Section 5.1. You are building Phase 2: the Discovery Engine.
[Phase 2 prompt from Section 9]
PROMPT
)\" --max-iterations 30"

echo "🚀 Starting Phase 3: AI Validation..."
claude -p "/ralph-loop \"$(cat <<'PROMPT'
Read CLAUDE.md Sections 5.2 and 5.3. You are building Phase 3.
[Phase 3 prompt from Section 9]
PROMPT
)\" --max-iterations 30"

echo "🚀 Starting Phase 4: README + Links..."
claude -p "/ralph-loop \"$(cat <<'PROMPT'
Read CLAUDE.md Sections 5.4, 5.5, 5.6. You are building Phase 4.
[Phase 4 prompt from Section 9]
PROMPT
)\" --max-iterations 30"

echo "🚀 Starting Phase 5: GitHub Integration..."
claude -p "/ralph-loop \"$(cat <<'PROMPT'
Read CLAUDE.md Sections 6 and 7. You are building Phase 5.
[Phase 5 prompt from Section 9]
PROMPT
)\" --max-iterations 25"

echo "🚀 Starting Phase 6: Integration + Polish..."
claude -p "/ralph-loop \"$(cat <<'PROMPT'
You are building Phase 6: Final integration and polish.
[Phase 6 prompt from Section 9]
PROMPT
)\" --max-iterations 40"

echo "✅ PROJECT COMPLETE"
echo "📊 Check the generated README.md"
echo "🚀 Push to GitHub and enable Actions!"
```

---

## 11. POST-BUILD: GOING LIVE

After Ralph finishes all 6 phases:

1. **Create GitHub repo**: `gh repo create summer2026-internships --public`
2. **Add secrets**: `gh secret set GEMINI_API_KEY`
3. **Push**: `git remote add origin ... && git push -u origin main`
4. **Enable Actions**: They start running automatically on the cron schedule
5. **Seed initial data**: Trigger a manual workflow run via `gh workflow run update.yml`
6. **Share**: Post to r/csMajors, your IEEE chapter, CS Discord servers

---

## 12. QUALITY GUARDRAILS FOR CLAUDE

When building this project, Claude must:

- **Never hardcode API keys** — always use environment variables
- **Never skip error handling** — every external call needs try/except
- **Never use print() for logging** — use Python's `logging` module
- **Always write tests** — minimum 80% coverage per module
- **Always validate data** — use Pydantic models everywhere
- **Always use type hints** — every function signature must be typed
- **Always handle edge cases** — empty responses, malformed JSON, network timeouts
- **Never commit secrets** — .gitignore must include .env, *.key, data/.cache/
- **Always use async** — httpx.AsyncClient for all HTTP calls in discover/check_links
- **Always log decisions** — especially validation accepts/rejects and dedup results

---

## 13. ESTIMATED API COSTS

| Component | Calls/Run | Cost/Run | Daily (4 runs) | Monthly |
|-----------|-----------|----------|-----------------|---------|
| Gemini Flash (validation) | ~200 | $0.00 | $0.00 | **$0** |
| GitHub Actions | 1 run | Free | Free | Free |
| **Total** | | | | **~$12/month** |

Using Gemini 2.0 Flash (free tier) for all validation and enrichment. Free tier allows 15 RPM / 1M TPM / 1500 RPD.

---

## 14. SUCCESS METRICS

After 30 days of running:
- [ ] 500+ listings in the repo
- [ ] Zero dead links in README
- [ ] Auto-updates running successfully 4x/day
- [ ] Community submissions being processed
- [ ] README renders beautifully on GitHub
- [ ] 100+ GitHub stars
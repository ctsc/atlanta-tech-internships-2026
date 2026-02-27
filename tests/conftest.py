"""Shared pytest fixtures for internship board tests."""

import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from scripts.utils.models import (
    JobListing,
    JobsDatabase,
    ListingStatus,
    RoleCategory,
    SponsorshipStatus,
)


@pytest.fixture
def sample_job_listing_data():
    """Raw dict for creating a valid JobListing."""
    return {
        "id": "abc123hash",
        "company": "Anthropic",
        "company_slug": "anthropic",
        "role": "Software Engineer Intern",
        "category": RoleCategory.SWE,
        "locations": ["San Francisco, CA"],
        "apply_url": "https://boards.greenhouse.io/anthropic/jobs/123",
        "sponsorship": SponsorshipStatus.UNKNOWN,
        "requires_us_citizenship": False,
        "is_faang_plus": False,
        "requires_advanced_degree": False,
        "remote_friendly": False,
        "date_added": date(2026, 1, 15),
        "date_last_verified": date(2026, 2, 20),
        "source": "greenhouse_api",
        "status": ListingStatus.OPEN,
        "tech_stack": ["Python", "React"],
        "season": "summer_2026",
    }


@pytest.fixture
def sample_job_listing(sample_job_listing_data):
    """A valid JobListing instance."""
    return JobListing(**sample_job_listing_data)


@pytest.fixture
def sample_jobs_database(sample_job_listing):
    """A JobsDatabase with one open listing."""
    return JobsDatabase(
        listings=[sample_job_listing],
        last_updated=datetime(2026, 2, 20, 12, 0, 0),
    )


@pytest.fixture
def minimal_config_dict():
    """Minimal valid config dict for AppConfig."""
    return {
        "project": {
            "name": "Test Project",
            "season": "summer_2026",
            "github_repo": "test/repo",
        },
    }


@pytest.fixture
def full_config_dict():
    """A full config dict with all sections populated."""
    return {
        "project": {
            "name": "Summer 2026 Tech Internships",
            "season": "summer_2026",
            "github_repo": "ctsc/atlanta-tech-internships-2026",
        },
        "georgia_focus": {
            "priority_locations": ["Atlanta, GA", "Alpharetta, GA"],
            "highlight_georgia": True,
            "georgia_section_in_readme": True,
        },
        "greenhouse_boards": [
            {"token": "anthropic", "company": "Anthropic", "is_faang_plus": False},
            {"token": "openai", "company": "OpenAI", "is_faang_plus": True},
        ],
        "lever_boards": [
            {"company_slug": "netflix", "company": "Netflix", "is_faang_plus": True},
        ],
        "ashby_boards": [
            {"company_slug": "ramp", "company": "Ramp", "is_faang_plus": False},
        ],
        "scrape_sources": [
            {
                "company": "Google",
                "url": "https://careers.google.com/jobs",
                "is_faang_plus": True,
            },
        ],
        "github_monitors": [
            {
                "repo": "SimplifyJobs/Summer2026-Internships",
                "branch": "dev",
                "file": "README.md",
            },
        ],
        "filters": {
            "keywords_include": ["intern", "internship"],
            "keywords_exclude": ["senior", "staff"],
            "role_categories": {
                "swe": ["software engineer", "backend"],
                "ml_ai": ["machine learning"],
            },
            "exclude_companies": ["Revature"],
        },
        "ai": {
            "model": "gemini-2.0-flash",
            "max_tokens": 1024,
            "enrichment_prompt": "Analyze this job listing.",
        },
        "schedule": {
            "update_interval_hours": 6,
            "link_check_interval_hours": 24,
            "archive_after_days": 7,
        },
    }


@pytest.fixture
def config_yaml_file(full_config_dict):
    """Write a full config dict to a temp YAML file and return its Path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        yaml.dump(full_config_dict, f, default_flow_style=False)
        return Path(f.name)


@pytest.fixture
def minimal_config_yaml_file(minimal_config_dict):
    """Write a minimal config dict to a temp YAML file and return its Path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        yaml.dump(minimal_config_dict, f, default_flow_style=False)
        return Path(f.name)

"""GitHub API v3 helpers for issues, comments, and file operations.

Provides async functions for interacting with the GitHub API:
- Fetching open issues by label
- Posting comments on issues
- Closing issues
- Reading file content from a repository
"""

import base64
import logging
from typing import Optional

import httpx

from scripts.utils.config import get_secret

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 15.0


def _build_headers(token: Optional[str] = None) -> dict[str, str]:
    """Build HTTP headers for GitHub API requests.

    Args:
        token: GitHub personal access token. If None, reads from environment.

    Returns:
        Dict of HTTP headers including Accept and optionally Authorization.
    """
    headers = {
        "Accept": "application/vnd.github+v3+json",
        "User-Agent": "InternshipTracker/1.0",
    }
    resolved_token = token or get_secret("GITHUB_TOKEN")
    if resolved_token:
        headers["Authorization"] = f"Bearer {resolved_token}"
    else:
        logger.warning("No GITHUB_TOKEN available — requests may be rate-limited")
    return headers


async def fetch_issues(
    repo: str,
    label: str = "new-internship",
    token: Optional[str] = None,
) -> list[dict]:
    """Fetch open issues with the given label from a GitHub repo.

    Args:
        repo: Repository in 'owner/name' format.
        label: Issue label to filter by.
        token: Optional GitHub token. Falls back to GITHUB_TOKEN env var.

    Returns:
        List of issue dicts from the GitHub API, or empty list on error.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues"
    params = {"labels": label, "state": "open", "per_page": 100}
    headers = _build_headers(token)

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url, headers=headers, params=params)
            logger.info(
                "GET %s — status %d (%d issues)",
                url,
                response.status_code,
                len(response.json()) if response.status_code == 200 else 0,
            )
            if response.status_code == 200:
                return response.json()
            logger.error(
                "Failed to fetch issues from %s: HTTP %d",
                repo,
                response.status_code,
            )
            return []
    except httpx.HTTPError as exc:
        logger.error("HTTP error fetching issues from %s: %s", repo, exc)
        return []
    except Exception as exc:
        logger.error("Unexpected error fetching issues from %s: %s", repo, exc)
        return []


async def comment_on_issue(
    repo: str,
    issue_number: int,
    body: str,
    token: Optional[str] = None,
) -> bool:
    """Post a comment on a GitHub issue.

    Args:
        repo: Repository in 'owner/name' format.
        issue_number: The issue number to comment on.
        body: The comment text (markdown supported).
        token: Optional GitHub token. Falls back to GITHUB_TOKEN env var.

    Returns:
        True if the comment was posted successfully, False otherwise.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{issue_number}/comments"
    headers = _build_headers(token)
    payload = {"body": body}

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(url, headers=headers, json=payload)
            logger.info(
                "POST %s — status %d",
                url,
                response.status_code,
            )
            if response.status_code == 201:
                return True
            logger.error(
                "Failed to comment on %s#%d: HTTP %d",
                repo,
                issue_number,
                response.status_code,
            )
            return False
    except httpx.HTTPError as exc:
        logger.error(
            "HTTP error commenting on %s#%d: %s", repo, issue_number, exc
        )
        return False
    except Exception as exc:
        logger.error(
            "Unexpected error commenting on %s#%d: %s", repo, issue_number, exc
        )
        return False


async def close_issue(
    repo: str,
    issue_number: int,
    token: Optional[str] = None,
) -> bool:
    """Close a GitHub issue.

    Args:
        repo: Repository in 'owner/name' format.
        issue_number: The issue number to close.
        token: Optional GitHub token. Falls back to GITHUB_TOKEN env var.

    Returns:
        True if the issue was closed successfully, False otherwise.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{issue_number}"
    headers = _build_headers(token)
    payload = {"state": "closed"}

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.patch(url, headers=headers, json=payload)
            logger.info(
                "PATCH %s — status %d",
                url,
                response.status_code,
            )
            if response.status_code == 200:
                return True
            logger.error(
                "Failed to close %s#%d: HTTP %d",
                repo,
                issue_number,
                response.status_code,
            )
            return False
    except httpx.HTTPError as exc:
        logger.error(
            "HTTP error closing %s#%d: %s", repo, issue_number, exc
        )
        return False
    except Exception as exc:
        logger.error(
            "Unexpected error closing %s#%d: %s", repo, issue_number, exc
        )
        return False


async def get_file_content(
    repo: str,
    path: str,
    branch: str = "main",
    token: Optional[str] = None,
) -> Optional[str]:
    """Get raw file content from a GitHub repo.

    Fetches the file via the Contents API and decodes base64 content.

    Args:
        repo: Repository in 'owner/name' format.
        path: File path within the repository.
        branch: Branch or ref to read from.
        token: Optional GitHub token. Falls back to GITHUB_TOKEN env var.

    Returns:
        Decoded file content as a string, or None on error.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}"
    params = {"ref": branch}
    headers = _build_headers(token)

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url, headers=headers, params=params)
            logger.info(
                "GET %s — status %d",
                url,
                response.status_code,
            )
            if response.status_code == 200:
                data = response.json()
                content_b64 = data.get("content", "")
                return base64.b64decode(content_b64).decode("utf-8")
            logger.error(
                "Failed to get file %s/%s: HTTP %d",
                repo,
                path,
                response.status_code,
            )
            return None
    except httpx.HTTPError as exc:
        logger.error(
            "HTTP error getting file %s/%s: %s", repo, path, exc
        )
        return None
    except Exception as exc:
        logger.error(
            "Unexpected error getting file %s/%s: %s", repo, path, exc
        )
        return None

"""Tests for GitHub API utility functions.

Tests cover:
- fetch_issues: success, empty result, HTTP error, no token, non-200 status
- comment_on_issue: success, HTTP error, non-201 status
- close_issue: success, HTTP error, non-200 status
- get_file_content: success with base64 decode, file not found, HTTP error
- _build_headers: with token, without token, from environment
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from scripts.utils.github_utils import (
    _build_headers,
    close_issue,
    comment_on_issue,
    fetch_issues,
    get_file_content,
)


def _mock_async_client(**method_returns):
    """Build a mock httpx.AsyncClient usable as an async context manager.

    Args:
        **method_returns: Mapping of method name to mock response, e.g.
            get=mock_response.  Use get=Exception("boom") for side effects.

    Returns:
        A MagicMock that, when called (i.e. ``httpx.AsyncClient(...)``),
        returns an async context manager whose ``__aenter__`` yields a
        mock client with the requested methods.
    """
    client_instance = MagicMock()

    for method_name, value in method_returns.items():
        mock_method = AsyncMock()
        if isinstance(value, Exception):
            mock_method.side_effect = value
        else:
            mock_method.return_value = value
        setattr(client_instance, method_name, mock_method)

    # Make the constructor return an async context manager
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client_instance)
    cm.__aexit__ = AsyncMock(return_value=False)

    constructor = MagicMock(return_value=cm)
    return constructor, client_instance


def _mock_response(status_code: int, json_data=None):
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


# ======================================================================
# _build_headers
# ======================================================================


class TestBuildHeaders:
    """Tests for _build_headers."""

    def test_with_explicit_token(self):
        """When a token is provided, Authorization header is set."""
        headers = _build_headers(token="ghp_test123")
        assert headers["Authorization"] == "Bearer ghp_test123"
        assert headers["Accept"] == "application/vnd.github+v3+json"

    def test_without_token_reads_env(self):
        """When no token is passed, reads GITHUB_TOKEN from environment."""
        with patch("scripts.utils.github_utils.get_secret", return_value="ghp_env"):
            headers = _build_headers()
        assert headers["Authorization"] == "Bearer ghp_env"

    def test_no_token_anywhere(self):
        """When no token is available, Authorization header is absent."""
        with patch("scripts.utils.github_utils.get_secret", return_value=None):
            headers = _build_headers()
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/vnd.github+v3+json"

    def test_user_agent_set(self):
        """User-Agent header is always present."""
        headers = _build_headers(token="ghp_test")
        assert "User-Agent" in headers


# ======================================================================
# fetch_issues
# ======================================================================


class TestFetchIssues:
    """Tests for fetch_issues."""

    @pytest.mark.asyncio
    async def test_success_returns_issues(self):
        """A 200 response returns the list of issue dicts."""
        mock_issues = [
            {"number": 1, "title": "Test issue", "body": "body"},
            {"number": 2, "title": "Another", "body": "body2"},
        ]
        resp = _mock_response(200, mock_issues)
        constructor, client = _mock_async_client(get=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await fetch_issues("owner/repo", token="ghp_test")

        assert result == mock_issues
        client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_result(self):
        """A 200 with empty list returns empty list."""
        resp = _mock_response(200, [])
        constructor, client = _mock_async_client(get=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await fetch_issues("owner/repo", token="ghp_test")

        assert result == []

    @pytest.mark.asyncio
    async def test_http_404_returns_empty(self):
        """A 404 response returns empty list."""
        resp = _mock_response(404, {"message": "Not Found"})
        constructor, client = _mock_async_client(get=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await fetch_issues("owner/repo", token="ghp_test")

        assert result == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self):
        """An httpx.HTTPError returns empty list."""
        constructor, client = _mock_async_client(
            get=httpx.ConnectError("Connection refused")
        )

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await fetch_issues("owner/repo", token="ghp_test")

        assert result == []

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_empty(self):
        """An unexpected exception returns empty list."""
        constructor, client = _mock_async_client(get=RuntimeError("boom"))

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await fetch_issues("owner/repo", token="ghp_test")

        assert result == []

    @pytest.mark.asyncio
    async def test_custom_label(self):
        """Custom label is passed to the API."""
        resp = _mock_response(200, [])
        constructor, client = _mock_async_client(get=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            await fetch_issues("owner/repo", label="custom-label", token="ghp_test")

        call_kwargs = client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["labels"] == "custom-label"

    @pytest.mark.asyncio
    async def test_no_token_still_works(self):
        """When no token is provided, the function still makes the request."""
        resp = _mock_response(200, [])
        constructor, client = _mock_async_client(get=resp)

        with (
            patch("scripts.utils.github_utils.httpx.AsyncClient", constructor),
            patch("scripts.utils.github_utils.get_secret", return_value=None),
        ):
            result = await fetch_issues("owner/repo")

        assert result == []


# ======================================================================
# comment_on_issue
# ======================================================================


class TestCommentOnIssue:
    """Tests for comment_on_issue."""

    @pytest.mark.asyncio
    async def test_success_returns_true(self):
        """A 201 response returns True."""
        resp = _mock_response(201)
        constructor, client = _mock_async_client(post=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await comment_on_issue("owner/repo", 42, "Nice!", token="ghp_test")

        assert result is True

    @pytest.mark.asyncio
    async def test_non_201_returns_false(self):
        """A non-201 status returns False."""
        resp = _mock_response(403)
        constructor, client = _mock_async_client(post=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await comment_on_issue("owner/repo", 42, "Test", token="ghp_test")

        assert result is False

    @pytest.mark.asyncio
    async def test_http_error_returns_false(self):
        """An HTTP error returns False."""
        constructor, client = _mock_async_client(
            post=httpx.ConnectError("Connection refused")
        )

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await comment_on_issue("owner/repo", 42, "Test", token="ghp_test")

        assert result is False

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_false(self):
        """An unexpected exception returns False."""
        constructor, client = _mock_async_client(post=RuntimeError("boom"))

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await comment_on_issue("owner/repo", 42, "Test", token="ghp_test")

        assert result is False

    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        """The comment body is sent as JSON payload."""
        resp = _mock_response(201)
        constructor, client = _mock_async_client(post=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            await comment_on_issue("owner/repo", 7, "Hello world", token="ghp_test")

        call_kwargs = client.post.call_args
        json_payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_payload == {"body": "Hello world"}


# ======================================================================
# close_issue
# ======================================================================


class TestCloseIssue:
    """Tests for close_issue."""

    @pytest.mark.asyncio
    async def test_success_returns_true(self):
        """A 200 response returns True."""
        resp = _mock_response(200)
        constructor, client = _mock_async_client(patch=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await close_issue("owner/repo", 42, token="ghp_test")

        assert result is True

    @pytest.mark.asyncio
    async def test_non_200_returns_false(self):
        """A non-200 status returns False."""
        resp = _mock_response(404)
        constructor, client = _mock_async_client(patch=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await close_issue("owner/repo", 42, token="ghp_test")

        assert result is False

    @pytest.mark.asyncio
    async def test_http_error_returns_false(self):
        """An HTTP error returns False."""
        constructor, client = _mock_async_client(
            patch=httpx.ConnectError("fail")
        )

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await close_issue("owner/repo", 42, token="ghp_test")

        assert result is False

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_false(self):
        """An unexpected exception returns False."""
        constructor, client = _mock_async_client(patch=RuntimeError("boom"))

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await close_issue("owner/repo", 42, token="ghp_test")

        assert result is False

    @pytest.mark.asyncio
    async def test_sends_closed_state(self):
        """The PATCH request sends state=closed."""
        resp = _mock_response(200)
        constructor, client = _mock_async_client(patch=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            await close_issue("owner/repo", 7, token="ghp_test")

        call_kwargs = client.patch.call_args
        json_payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_payload == {"state": "closed"}


# ======================================================================
# get_file_content
# ======================================================================


class TestGetFileContent:
    """Tests for get_file_content."""

    @pytest.mark.asyncio
    async def test_success_decodes_base64(self):
        """A 200 response with base64 content is decoded correctly."""
        content = "Hello, world!"
        encoded = base64.b64encode(content.encode()).decode()
        resp = _mock_response(200, {"content": encoded})
        constructor, client = _mock_async_client(get=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await get_file_content("owner/repo", "README.md", token="ghp_test")

        assert result == content

    @pytest.mark.asyncio
    async def test_multiline_content(self):
        """Multi-line base64 content is decoded properly."""
        content = "line1\nline2\nline3"
        encoded = base64.b64encode(content.encode()).decode()
        resp = _mock_response(200, {"content": encoded})
        constructor, client = _mock_async_client(get=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await get_file_content("owner/repo", "file.txt", token="ghp_test")

        assert result == content

    @pytest.mark.asyncio
    async def test_file_not_found_returns_none(self):
        """A 404 response returns None."""
        resp = _mock_response(404)
        constructor, client = _mock_async_client(get=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await get_file_content("owner/repo", "nope.txt", token="ghp_test")

        assert result is None

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        """An HTTP error returns None."""
        constructor, client = _mock_async_client(
            get=httpx.ConnectError("fail")
        )

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await get_file_content("owner/repo", "file.txt", token="ghp_test")

        assert result is None

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_none(self):
        """An unexpected exception returns None."""
        constructor, client = _mock_async_client(get=RuntimeError("boom"))

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await get_file_content("owner/repo", "file.txt", token="ghp_test")

        assert result is None

    @pytest.mark.asyncio
    async def test_custom_branch(self):
        """Custom branch is passed as ref parameter."""
        content = "dev content"
        encoded = base64.b64encode(content.encode()).decode()
        resp = _mock_response(200, {"content": encoded})
        constructor, client = _mock_async_client(get=resp)

        with patch("scripts.utils.github_utils.httpx.AsyncClient", constructor):
            result = await get_file_content(
                "owner/repo", "file.txt", branch="dev", token="ghp_test"
            )

        assert result == content
        call_kwargs = client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["ref"] == "dev"

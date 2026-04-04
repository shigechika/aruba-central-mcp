"""Tests for ArubaClient."""

import httpx
import pytest
import respx

from aruba_central_mcp.client import (
    ArubaAPIError,
    ArubaAuthError,
    ArubaClient,
    TOKEN_URL,
)

BASE_URL = "apigw-test.central.arubanetworks.com"


@pytest.fixture
def token_mock():
    """Mock the OAuth2 token endpoint."""
    with respx.mock:
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "test-token", "expires_in": 7200},
            )
        )
        yield


@pytest.fixture
def client(token_mock):
    """Create an ArubaClient with mocked auth."""
    c = ArubaClient(BASE_URL, "test-id", "test-secret")
    return c


class TestAuthentication:
    def test_successful_auth(self, token_mock):
        """OAuth2 authentication returns a valid token."""
        c = ArubaClient(BASE_URL, "test-id", "test-secret")
        token = c._get_token()
        assert token == "test-token"

    def test_auth_failure(self):
        """Authentication failure raises ArubaAuthError."""
        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(401, json={"error": "invalid_client"})
            )
            c = ArubaClient(BASE_URL, "bad-id", "bad-secret")
            with pytest.raises(ArubaAuthError):
                c._get_token()

    def test_token_reuse(self, client):
        """Token is reused when not expired."""
        token1 = client._get_token()
        token2 = client._get_token()
        assert token1 == token2


class TestGet:
    def test_successful_get(self, client):
        """GET request returns parsed JSON."""
        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"access_token": "test-token", "expires_in": 7200},
                )
            )
            respx.get(f"https://{BASE_URL}/test/path").mock(
                return_value=httpx.Response(200, json={"items": [{"id": 1}]})
            )
            result = client.get("/test/path")
            assert result == {"items": [{"id": 1}]}

    def test_get_with_params(self, client):
        """GET request includes query parameters."""
        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"access_token": "test-token", "expires_in": 7200},
                )
            )
            route = respx.get(f"https://{BASE_URL}/test/path").mock(
                return_value=httpx.Response(200, json={"items": []})
            )
            client.get("/test/path", params={"limit": 10, "offset": 0})
            assert route.called

    def test_get_api_error(self, client):
        """API error raises ArubaAPIError."""
        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"access_token": "test-token", "expires_in": 7200},
                )
            )
            respx.get(f"https://{BASE_URL}/bad/path").mock(
                return_value=httpx.Response(500, text="Internal Server Error")
            )
            with pytest.raises(ArubaAPIError):
                client.get("/bad/path")


class TestFetchAll:
    def test_single_page(self, client):
        """Fetch all items from a single page."""
        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"access_token": "test-token", "expires_in": 7200},
                )
            )
            respx.get(f"https://{BASE_URL}/test").mock(
                return_value=httpx.Response(
                    200,
                    json={"items": [{"id": 1}, {"id": 2}], "total": 2},
                )
            )
            items = client.fetch_all("/test", limit=10)
            assert len(items) == 2

    def test_multiple_pages(self, client):
        """Fetch items across multiple pages."""
        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"access_token": "test-token", "expires_in": 7200},
                )
            )
            call_count = 0

            def side_effect(request):
                nonlocal call_count
                offset = int(request.url.params.get("offset", 0))
                if offset == 0:
                    call_count += 1
                    return httpx.Response(
                        200,
                        json={"items": [{"id": 1}, {"id": 2}], "total": 3},
                    )
                else:
                    call_count += 1
                    return httpx.Response(
                        200,
                        json={"items": [{"id": 3}], "total": 3},
                    )

            respx.get(f"https://{BASE_URL}/test").mock(side_effect=side_effect)
            items = client.fetch_all("/test", limit=2)
            assert len(items) == 3
            assert call_count == 2

    def test_empty_response(self, client):
        """Empty response returns empty list."""
        with respx.mock:
            respx.post(TOKEN_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"access_token": "test-token", "expires_in": 7200},
                )
            )
            respx.get(f"https://{BASE_URL}/test").mock(
                return_value=httpx.Response(
                    200,
                    json={"items": [], "total": 0},
                )
            )
            items = client.fetch_all("/test")
            assert items == []


class TestContextManager:
    def test_context_manager(self, token_mock):
        """Client works as a context manager."""
        with ArubaClient(BASE_URL, "test-id", "test-secret") as c:
            assert c._get_token() == "test-token"

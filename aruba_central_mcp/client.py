"""Aruba Central API client with OAuth2 and automatic pagination.

Uses GreenLake New Central API (/network-monitoring/v1/).
Authentication via OAuth2 Client Credentials (GreenLake SSO).
"""

from __future__ import annotations

import logging
import time

import httpx

TOKEN_URL = "https://sso.common.cloud.hpe.com/as/token.oauth2"

PATH_APS = "/network-monitoring/v1/aps"
PATH_SWITCHES = "/network-monitoring/v1/switches"
PATH_CLIENTS = "/network-monitoring/v1/clients"

logger = logging.getLogger(__name__)


class ArubaClientError(Exception):
    """Base exception for ArubaClient errors."""


class ArubaAuthError(ArubaClientError):
    """Authentication failure."""


class ArubaAPIError(ArubaClientError):
    """API request failure."""


class ArubaClient:
    """GreenLake New Central API client.

    Args:
        base_url: Aruba Central base URL (e.g. "apigw-uswest4.central.arubanetworks.com").
        client_id: GreenLake OAuth2 client ID.
        client_secret: GreenLake OAuth2 client secret.
    """

    def __init__(self, base_url: str, client_id: str, client_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.Client(timeout=120)
        self._token: str | None = None
        self._token_expires: float = 0

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> ArubaClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _authenticate(self) -> str:
        """Obtain an OAuth2 access token via client credentials grant."""
        try:
            resp = self._http.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ArubaAuthError(f"OAuth2 authentication failed: {e}") from e

        body = resp.json()
        self._token = body["access_token"]
        expires_in = body.get("expires_in", 7200)
        self._token_expires = time.monotonic() + expires_in - 60
        logger.info("GreenLake OAuth2 authentication successful")
        return self._token

    def _get_token(self) -> str:
        """Return a valid token, refreshing if expired."""
        if self._token is None or time.monotonic() >= self._token_expires:
            return self._authenticate()
        return self._token

    def get(self, path: str, params: dict | None = None) -> dict:
        """Send a GET request to the Aruba Central API.

        Raises:
            ArubaAPIError: On HTTP errors.
        """
        url = f"https://{self.base_url}{path}"
        token = self._get_token()
        try:
            resp = self._http.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ArubaAPIError(f"API error ({path}): {e}") from e
        return resp.json()

    def fetch_all(
        self, path: str, limit: int = 1000, max_pages: int = 20,
    ) -> list[dict]:
        """Fetch all items from a paginated API endpoint.

        Args:
            path: API path (e.g. PATH_APS).
            limit: Items per page.
            max_pages: Maximum number of pages to fetch.

        Returns:
            List of item dicts.
        """
        all_items: list[dict] = []
        seen_ids: set[str] = set()
        offset = 0
        for _ in range(max_pages):
            resp = self.get(path, params={"limit": limit, "offset": offset})
            items = resp.get("items", [])
            total = resp.get("total", 0)
            n = len(items)
            logger.debug("fetch_all: offset=%d, n=%d, total=%d", offset, n, total)
            if n == 0:
                break
            new_count = 0
            for item in items:
                item_id = item.get("id") or item.get("macAddress") or ""
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                all_items.append(item)
                new_count += 1
            if new_count == 0:
                # All items were duplicates — API ignores offset
                logger.debug(
                    "fetch_all: no new items on page (API may not support offset). "
                    "Returning %d of %d total.", len(all_items), total,
                )
                break
            offset += n
            if n < limit or (total and offset >= total):
                break
        return all_items

"""Classic Aruba Central API client (read-only use), for firmware data the New Central API lacks.

AOS-8 Instant APs in Classic Central groups are upgraded from Classic Central,
and only its ``/firmware/v1/*`` API reports a swarm's upgrade state with a
reason and the group's compliance version. The Classic API gateway uses its own
OAuth: an API-gateway application gives a client id and secret, and access
tokens (about 2 hours) are renewed with a refresh token that is replaced on
every refresh -- the old one stops working.

Several processes (one per MCP session) may share one token file, so a refresh
takes an exclusive lock, re-reads the file (another process may have refreshed
already) and writes the new pair back atomically. Tokens never reach a log line.
See docs/firmware-api-notes.md for what the API documents and what it does not.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time

import httpx

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows: no cross-process lock
    fcntl = None

PATH_OAUTH_TOKEN = "/oauth2/token"
PATH_FW_SWARMS = "/firmware/v1/swarms"
PATH_FW_VERSIONS = "/firmware/v1/versions"
PATH_FW_STATUS = "/firmware/v1/status"
PATH_FW_COMPLIANCE = "/firmware/v1/upgrade/compliance_version"

#: Refresh this many seconds before the access token's stated expiry.
EXPIRY_MARGIN = 120

logger = logging.getLogger(__name__)


class ClassicError(Exception):
    """Classic Central API failure."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ClassicAuthError(ClassicError):
    """The token pair cannot be used or renewed; the operator must re-bootstrap the token file."""


def _host(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if base.lower().startswith(prefix):
            base = base[len(prefix):]
    return base


class ClassicClient:
    """GET-only client for the Classic Central API gateway.

    Args:
        base_url: Classic API gateway host, e.g. "apigw-<region>.central.arubanetworks.com"
            (a scheme prefix is accepted and dropped).
        client_id / client_secret: the API-gateway application's credentials.
        token_file: JSON file holding ``access_token``, ``refresh_token`` and, once
            this client has refreshed, ``expires_at`` (epoch seconds).
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        token_file: str,
        http: httpx.Client | None = None,
    ) -> None:
        self.base_url = _host(base_url)
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = token_file
        self._http = http or httpx.Client(timeout=60)

    def close(self) -> None:
        self._http.close()

    # -- token file ---------------------------------------------------------

    def _read(self) -> dict:
        try:
            with open(self.token_file, encoding="utf-8") as f:
                doc = json.load(f)
        except FileNotFoundError as e:
            raise ClassicAuthError(
                f"token file {self.token_file} does not exist; bootstrap it with an access "
                "and refresh token from the Classic Central API Gateway"
            ) from e
        except (OSError, ValueError) as e:
            raise ClassicAuthError(f"token file {self.token_file} cannot be read as JSON ({type(e).__name__})") from e
        if not isinstance(doc, dict) or not doc.get("refresh_token"):
            raise ClassicAuthError(f"token file {self.token_file} has no refresh_token; re-bootstrap it")
        return doc

    def _write(self, doc: dict) -> None:
        directory = os.path.dirname(os.path.abspath(self.token_file))
        fd, tmp = tempfile.mkstemp(prefix=".classic-token-", dir=directory)
        try:
            os.chmod(tmp, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            os.replace(tmp, self.token_file)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    @contextlib.contextmanager
    def _locked(self):
        """Exclusive lock beside the token file (no-op where fcntl is missing)."""
        if fcntl is None:
            yield
            return
        with open(self.token_file + ".lock", "a", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def _fresh(doc: dict) -> bool:
        expires_at = doc.get("expires_at")
        return (
            bool(doc.get("access_token"))
            and isinstance(expires_at, (int, float))
            and time.time() < expires_at - EXPIRY_MARGIN
        )

    def _refresh(self, stale_access: str | None) -> str:
        """Renew the pair under the lock unless another process already did."""
        with self._locked():
            doc = self._read()
            if doc.get("access_token") and doc.get("access_token") != stale_access and self._fresh(doc):
                return doc["access_token"]
            try:
                resp = self._http.post(
                    f"https://{self.base_url}{PATH_OAUTH_TOKEN}",
                    params={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": doc["refresh_token"],
                    },
                    timeout=30,
                )
            except httpx.HTTPError as e:
                raise ClassicError(f"token refresh failed ({type(e).__name__})") from e
            if resp.status_code in (400, 401, 403):
                raise ClassicAuthError(
                    f"token refresh rejected (HTTP {resp.status_code}); the refresh token is no longer "
                    f"valid -- re-bootstrap {self.token_file} with a new token pair from the Classic "
                    "Central API Gateway",
                    status_code=resp.status_code,
                )
            if resp.status_code != 200:
                raise ClassicError(f"token refresh failed (HTTP {resp.status_code})", status_code=resp.status_code)
            try:
                body = resp.json()
                access, refresh = body["access_token"], body["refresh_token"]
            except (ValueError, KeyError, TypeError) as e:
                raise ClassicError("token refresh returned no access_token/refresh_token") from e
            expires_in = body.get("expires_in") if isinstance(body.get("expires_in"), (int, float)) else 7200
            self._write({"access_token": access, "refresh_token": refresh, "expires_at": int(time.time() + expires_in)})
            logger.info("Classic Central token refreshed")
            return access

    def access_token(self) -> str:
        """A usable access token, refreshing first when the stored one is (nearly) expired."""
        doc = self._read()
        if self._fresh(doc):
            return doc["access_token"]
        return self._refresh(doc.get("access_token"))

    # -- requests -----------------------------------------------------------

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET a Classic API path; a 401 triggers one refresh and one retry."""
        token = self.access_token()
        for attempt in (1, 2):
            try:
                resp = self._http.get(
                    f"https://{self.base_url}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as e:
                raise ClassicError(f"Classic API error ({path}): {type(e).__name__}") from e
            if resp.status_code == 401 and attempt == 1:
                token = self._refresh(token)
                continue
            if resp.status_code != 200:
                detail = ""
                try:
                    body = resp.json()
                    if isinstance(body, dict):
                        detail = str(body.get("description") or body.get("message") or "")[:200]
                except ValueError:
                    pass
                raise ClassicError(
                    f"Classic API error ({path}): HTTP {resp.status_code}" + (f" {detail}" if detail else ""),
                    status_code=resp.status_code,
                )
            try:
                return resp.json()
            except ValueError as e:
                raise ClassicError(f"Classic API error ({path}): response is not JSON") from e
        raise ClassicError(f"Classic API error ({path}): unauthorized after refresh")  # pragma: no cover

    def list_swarms(self, group: str = "", page_size: int = 1000, max_pages: int = 20) -> list[dict]:
        """Every swarm of ``/firmware/v1/swarms`` (optionally one group), following offset paging."""
        swarms: list[dict] = []
        offset = 0
        for _ in range(max_pages):
            params: dict = {"limit": page_size, "offset": offset}
            if group:
                params["group"] = group
            doc = self.get(PATH_FW_SWARMS, params)
            page = doc.get("swarms") or []
            if not isinstance(page, list):
                raise ClassicError(f"Classic API error ({PATH_FW_SWARMS}): swarms is not a list")
            swarms.extend(s for s in page if isinstance(s, dict))
            total = doc.get("swarm_count")
            if not page or len(page) < page_size or (isinstance(total, int) and len(swarms) >= total):
                break
            offset += len(page)
        return swarms

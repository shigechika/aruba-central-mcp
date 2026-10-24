"""Classic Aruba Central API client (read-only use), for firmware data the New Central API lacks.

AOS-8 Instant APs in Classic Central groups are upgraded from Classic Central,
and only its ``/firmware/v1/*`` API reports a swarm's upgrade state with a
reason and the group's compliance version. The Classic API gateway uses its own
OAuth: an API-gateway application gives a client id and secret, and access
tokens (about 2 hours) are renewed with a refresh token that is replaced on
every refresh -- the old one stops working.

Several processes (one per MCP session) may share one token file, so a refresh
takes an exclusive lock, re-reads the file (another process may have refreshed
already) and writes the new pair back durably (fsync, atomic rename, directory
fsync). Before refreshing it checks that the new pair can be written, because
after a refresh the file's old refresh token is dead. Tokens never reach a log
line or an error message: the refresh sends them as URL query parameters (as
the API documents), so httpx's request logging is lowered to WARNING and a
filter masks token-bearing query values in anything those loggers emit.
See docs/firmware-api-notes.md for what the API documents and what it does not.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sys
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

#: Loggers that could print a request URL carrying the refresh credentials.
HTTP_LOGGERS = ("httpx", "httpcore")

_SECRET_QUERY = re.compile(r"(?i)\b(client_secret|refresh_token|access_token|client_id)=[^&\s'\"]+")


def redact(text: str) -> str:
    """Mask the values of token-bearing query parameters in ``text``."""
    return _SECRET_QUERY.sub(lambda m: f"{m.group(1)}=***", text)


class _RedactFilter(logging.Filter):
    """Rewrites a record's message with token-bearing query values masked."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a malformed record is left to the handler
            return True
        masked = redact(message)
        if masked != message:
            record.msg, record.args = masked, None
        return True


_REDACT_FILTER = _RedactFilter()

#: This module's own logger writes to stderr explicitly and does not propagate:
#: stdout is the JSON-RPC channel while the stdio server runs.
logger = logging.getLogger(__name__)
if not logger.handlers:
    _stderr = logging.StreamHandler(sys.stderr)
    _stderr.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    _stderr.addFilter(_REDACT_FILTER)
    logger.addHandler(_stderr)
    logger.propagate = False


def quiet_http_logging() -> None:
    """Keep httpx/httpcore request lines (which include URLs) out of INFO logs, and mask any that get through."""
    for name in HTTP_LOGGERS:
        lg = logging.getLogger(name)
        if lg.level == logging.NOTSET or lg.level < logging.WARNING:
            lg.setLevel(logging.WARNING)
        if _REDACT_FILTER not in lg.filters:
            lg.addFilter(_REDACT_FILTER)


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
            this client has refreshed, ``expires_at`` (epoch seconds). A freshly
            bootstrapped file without ``expires_at`` is used as is until the
            first HTTP 401, then refreshed once.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        token_file: str,
        http: httpx.Client | None = None,
    ) -> None:
        quiet_http_logging()
        self.base_url = _host(base_url)
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = token_file
        self._http = http or httpx.Client(timeout=60)
        #: A refreshed pair that could not be written back (the file now holds a dead refresh token).
        self._unsaved: dict | None = None
        #: Operator-facing message while ``_unsaved`` is set.
        self.persist_error: str | None = None

    def close(self) -> None:
        self._http.close()

    # -- token file ---------------------------------------------------------

    def _read(self) -> dict:
        if self._unsaved is not None:
            return self._unsaved
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

    def _directory(self) -> str:
        return os.path.dirname(os.path.abspath(self.token_file))

    def _check_writable(self) -> None:
        """Refuse to refresh when the new pair could not be saved (the old refresh token dies on refresh)."""
        directory = self._directory()
        if not os.access(directory, os.W_OK | os.X_OK):
            raise ClassicError(
                f"cannot refresh: {directory} is not writable by this user, so the rotated token pair "
                f"could not be saved and the one in {self.token_file} would be lost; make the directory "
                "writable, then retry"
            )

    def _write(self, doc: dict) -> None:
        """Atomically and durably replace the token file (0600)."""
        directory = self._directory()
        fd, tmp = tempfile.mkstemp(prefix=".classic-token-", dir=directory)
        try:
            if sys.platform != "win32":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.token_file)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        if sys.platform != "win32":
            dfd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)

    @contextlib.contextmanager
    def _locked(self):
        """Exclusive lock beside the token file (no-op where fcntl is missing)."""
        if fcntl is None:
            yield
            return
        try:
            lock = open(self.token_file + ".lock", "a", encoding="utf-8")
        except OSError as e:
            raise ClassicError(f"cannot open the lock file next to {self.token_file} ({type(e).__name__})") from e
        with lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def _fresh(doc: dict) -> bool:
        if not doc.get("access_token"):
            return False
        expires_at = doc.get("expires_at")
        if expires_at is None:
            return True  # freshly bootstrapped: trust it until the API says 401
        return isinstance(expires_at, (int, float)) and time.time() < expires_at - EXPIRY_MARGIN

    def _refresh(self, stale_access: str | None) -> str:
        """Renew the pair under the lock unless another process already did."""
        with self._locked():
            doc = self._read()
            current = doc.get("access_token")
            if current and current != stale_access and self._fresh(doc):
                return current
            if self._unsaved is None:
                self._check_writable()
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
            new = {"access_token": access, "refresh_token": refresh, "expires_at": int(time.time() + expires_in)}
            try:
                self._write(new)
            except OSError as e:
                # The old refresh token is dead now; this process holds the only valid pair.
                self._unsaved = new
                self.persist_error = (
                    f"the refreshed Classic token pair could not be written to {self.token_file} "
                    f"({type(e).__name__}); this process keeps it in memory and retries the write on the "
                    "next refresh. Fix the file/directory (permissions, free space) now: if this process "
                    "stops first, re-bootstrap the file with a new token pair from the Classic Central API Gateway"
                )
                logger.error(self.persist_error)
            else:
                self._unsaved = None
                self.persist_error = None
            return access

    def access_token(self) -> str:
        """A usable access token, refreshing first when the stored one is (nearly) expired."""
        doc = self._read()
        if self._fresh(doc):
            return doc["access_token"]
        return self._refresh(doc.get("access_token"))

    # -- requests -----------------------------------------------------------

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET a Classic API path; a 401 triggers one refresh and one retry. Returns a JSON object."""
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
                        detail = redact(str(body.get("description") or body.get("message") or ""))[:200]
                except ValueError:
                    pass
                raise ClassicError(
                    f"Classic API error ({path}): HTTP {resp.status_code}" + (f" {detail}" if detail else ""),
                    status_code=resp.status_code,
                )
            try:
                body = resp.json()
            except ValueError as e:
                raise ClassicError(f"Classic API error ({path}): response is not JSON") from e
            if not isinstance(body, dict):
                raise ClassicError(f"Classic API error ({path}): response is not a JSON object")
            return body
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

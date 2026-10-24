"""Tests for the Classic Central client (token file handling and firmware reads)."""

import json
import os
import sys
import time

import httpx
import pytest
import respx

from aruba_central_mcp import classic as classic_mod
from aruba_central_mcp.classic import (
    PATH_FW_SWARMS,
    PATH_OAUTH_TOKEN,
    ClassicAuthError,
    ClassicClient,
    ClassicError,
)

HOST = "apigw-test.central.example.invalid"
BASE = f"https://{HOST}"


def write_tokens(path, **doc):
    path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def token_file(tmp_path):
    p = tmp_path / "classic-token.json"
    write_tokens(p, access_token="old-access", refresh_token="old-refresh", expires_at=int(time.time()) + 3600)
    return p


def make(token_file):
    return ClassicClient(f"https://{HOST}/", "cid", "csecret", str(token_file))


class TestTokens:
    def test_fresh_token_is_used_without_refresh(self, token_file):
        with respx.mock:
            route = respx.post(f"{BASE}{PATH_OAUTH_TOKEN}")
            assert make(token_file).access_token() == "old-access"
            assert not route.called

    def test_expired_token_is_refreshed_and_the_rotated_pair_written_back(self, token_file):
        write_tokens(token_file, access_token="old-access", refresh_token="old-refresh", expires_at=1)
        with respx.mock:
            route = respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(
                return_value=httpx.Response(
                    200,
                    json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 7200},
                )
            )
            assert make(token_file).access_token() == "new-access"
        params = route.calls.last.request.url.params
        assert params["grant_type"] == "refresh_token" and params["refresh_token"] == "old-refresh"
        assert params["client_id"] == "cid"
        doc = json.loads(token_file.read_text(encoding="utf-8"))
        assert doc["access_token"] == "new-access" and doc["refresh_token"] == "new-refresh"
        assert doc["expires_at"] > time.time() + 7000

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file mode")
    def test_written_file_is_private(self, token_file):
        write_tokens(token_file, refresh_token="old-refresh")
        with respx.mock:
            respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(
                return_value=httpx.Response(200, json={"access_token": "a", "refresh_token": "r"})
            )
            make(token_file).access_token()
        assert os.stat(token_file).st_mode & 0o777 == 0o600

    def test_another_process_already_refreshed(self, token_file, monkeypatch):
        """After taking the lock the file is re-read; a pair renewed meanwhile is used, not refreshed again."""
        write_tokens(token_file, access_token="old-access", refresh_token="old-refresh", expires_at=1)
        c = make(token_file)
        real_locked = c._locked

        def locked_after_other_refresh():
            write_tokens(
                token_file, access_token="other-access", refresh_token="other-refresh", expires_at=int(time.time()) + 3600
            )
            return real_locked()

        monkeypatch.setattr(c, "_locked", locked_after_other_refresh)
        with respx.mock:
            route = respx.post(f"{BASE}{PATH_OAUTH_TOKEN}")
            assert c.access_token() == "other-access"
            assert not route.called

    @pytest.mark.skipif(classic_mod.fcntl is None, reason="no fcntl")
    def test_refresh_takes_the_lock_file(self, token_file):
        write_tokens(token_file, refresh_token="old-refresh")
        with respx.mock:
            respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(
                return_value=httpx.Response(200, json={"access_token": "a", "refresh_token": "r"})
            )
            make(token_file).access_token()
        assert os.path.exists(str(token_file) + ".lock")

    def test_rejected_refresh_asks_to_rebootstrap(self, token_file):
        write_tokens(token_file, refresh_token="dead", expires_at=1)
        with respx.mock:
            respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
            with pytest.raises(ClassicAuthError, match="re-bootstrap"):
                make(token_file).access_token()

    def test_missing_file_asks_to_bootstrap(self, tmp_path):
        with pytest.raises(ClassicAuthError, match="bootstrap"):
            ClassicClient(HOST, "cid", "csecret", str(tmp_path / "absent.json")).access_token()

    def test_token_never_appears_in_errors(self, token_file):
        write_tokens(token_file, access_token="secret-access", refresh_token="secret-refresh", expires_at=1)
        with respx.mock:
            respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(return_value=httpx.Response(500, text="boom"))
            with pytest.raises(ClassicError) as exc:
                make(token_file).access_token()
        assert "secret" not in str(exc.value)


class TestRequests:
    def test_401_refreshes_once_and_retries(self, token_file):
        with respx.mock:
            respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(
                return_value=httpx.Response(200, json={"access_token": "new-access", "refresh_token": "new-refresh"})
            )
            route = respx.get(f"{BASE}{PATH_FW_SWARMS}").mock(
                side_effect=[httpx.Response(401), httpx.Response(200, json={"swarms": [], "swarm_count": 0})]
            )
            assert make(token_file).get(PATH_FW_SWARMS) == {"swarms": [], "swarm_count": 0}
        assert route.calls[1].request.headers["Authorization"] == "Bearer new-access"

    def test_error_carries_the_api_description(self, token_file):
        with respx.mock:
            respx.get(f"{BASE}{PATH_FW_SWARMS}").mock(
                return_value=httpx.Response(
                    400, json={"service_name": "fw", "error_code": "0004", "description": "invalid query parameter"}
                )
            )
            with pytest.raises(ClassicError, match="HTTP 400 invalid query parameter"):
                make(token_file).get(PATH_FW_SWARMS)

    def test_list_swarms_follows_offset_paging_and_group(self, token_file):
        page1 = {"swarms": [{"swarm_id": f"s{i}", "swarm_name": f"n{i}"} for i in range(2)], "swarm_count": 3}
        page2 = {"swarms": [{"swarm_id": "s2", "swarm_name": "n2"}], "swarm_count": 3}
        with respx.mock:
            route = respx.get(f"{BASE}{PATH_FW_SWARMS}").mock(
                side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
            )
            swarms = make(token_file).list_swarms(group="G1", page_size=2)
        assert [s["swarm_id"] for s in swarms] == ["s0", "s1", "s2"]
        assert route.calls[0].request.url.params["group"] == "G1"
        assert route.calls[1].request.url.params["offset"] == "2"


class TestSecretsStayOutOfLogs:
    def test_refresh_logs_no_secret_even_at_debug(self, token_file, caplog):
        import logging

        write_tokens(token_file, access_token="old-access", refresh_token="SECRET-REFRESH", expires_at=1)
        c = make(token_file)
        c.client_secret = "SECRET-CLIENT"
        caplog.set_level(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.DEBUG)  # someone turned request logging on
        try:
            with respx.mock:
                respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(
                    return_value=httpx.Response(200, json={"access_token": "SECRET-NEW", "refresh_token": "SECRET-R2"})
                )
                c.access_token()
            logging.getLogger("httpx").info(
                "HTTP Request: POST %s", f"{BASE}/oauth2/token?client_secret=SECRET-CLIENT&refresh_token=SECRET-REFRESH"
            )
        finally:
            logging.getLogger("httpx").setLevel(logging.WARNING)
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "SECRET" not in text
        assert "client_secret=***" in text

    def test_http_loggers_are_quiet_by_default(self, token_file):
        import logging

        make(token_file)
        assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
        assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


class TestDurability:
    def test_bootstrapped_file_without_expiry_is_used_until_401(self, token_file):
        write_tokens(token_file, access_token="boot-access", refresh_token="boot-refresh")
        with respx.mock:
            refresh = respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(
                return_value=httpx.Response(200, json={"access_token": "new", "refresh_token": "new-r"})
            )
            route = respx.get(f"{BASE}{PATH_FW_SWARMS}").mock(
                side_effect=[httpx.Response(401), httpx.Response(200, json={"swarms": []})]
            )
            make(token_file).get(PATH_FW_SWARMS)
        assert refresh.call_count == 1
        assert route.calls[0].request.headers["Authorization"] == "Bearer boot-access"

    @pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="POSIX permissions, not root")
    def test_unwritable_directory_refuses_to_refresh(self, tmp_path):
        d = tmp_path / "ro"
        d.mkdir()
        f = d / "t.json"
        write_tokens(f, access_token="a", refresh_token="r", expires_at=1)
        os.chmod(d, 0o500)
        try:
            with respx.mock:
                route = respx.post(f"{BASE}{PATH_OAUTH_TOKEN}")
                with pytest.raises(ClassicError):
                    make(f).access_token()
                assert not route.called  # the old refresh token is not spent
        finally:
            os.chmod(d, 0o700)

    def test_failed_write_keeps_the_new_pair_in_memory_and_says_so(self, token_file, monkeypatch):
        write_tokens(token_file, access_token="old", refresh_token="old-r", expires_at=1)
        c = make(token_file)

        def boom(doc):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(c, "_write", boom)
        with respx.mock:
            refresh = respx.post(f"{BASE}{PATH_OAUTH_TOKEN}").mock(
                return_value=httpx.Response(
                    200, json={"access_token": "new", "refresh_token": "new-r", "expires_in": 7200}
                )
            )
            assert c.access_token() == "new"
            assert c.access_token() == "new"  # served from memory, no second refresh
        assert refresh.call_count == 1
        assert c.persist_error and "re-bootstrap" in c.persist_error and "new-r" not in c.persist_error
        assert json.loads(token_file.read_text(encoding="utf-8"))["refresh_token"] == "old-r"

    def test_write_fsyncs_and_replaces(self, token_file, monkeypatch):
        synced = []
        real_fsync = os.fsync
        monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd)))
        make(token_file)._write({"access_token": "a", "refresh_token": "r", "expires_at": 1})
        assert len(synced) >= (1 if sys.platform == "win32" else 2)  # file, then directory
        assert json.loads(token_file.read_text(encoding="utf-8"))["refresh_token"] == "r"

    @pytest.mark.skipif(classic_mod.fcntl is None, reason="no fcntl")
    def test_unopenable_lock_file_is_a_classic_error(self, token_file, monkeypatch):
        write_tokens(token_file, access_token="a", refresh_token="r", expires_at=1)
        c = make(token_file)
        real_open = open

        def fake_open(path, *a, **k):
            if str(path).endswith(".lock"):
                raise PermissionError("denied")
            return real_open(path, *a, **k)

        monkeypatch.setattr("builtins.open", fake_open)
        with pytest.raises(ClassicError, match="lock file"):
            c.access_token()


class TestGroups:
    def test_list_groups_reads_list_of_lists_and_pages(self, token_file):
        from aruba_central_mcp.classic import PATH_CONFIG_GROUPS

        page1 = {"data": [[f"g{i}"] for i in range(2)], "total": 3}
        page2 = {"data": [["g2"]], "total": 3}
        with respx.mock:
            route = respx.get(f"{BASE}{PATH_CONFIG_GROUPS}").mock(
                side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
            )
            assert make(token_file).list_groups(page_size=2) == ["g0", "g1", "g2"]
        assert route.calls[1].request.url.params["offset"] == "2"

    def test_list_groups_rejects_a_non_list(self, token_file):
        from aruba_central_mcp.classic import PATH_CONFIG_GROUPS

        with respx.mock:
            respx.get(f"{BASE}{PATH_CONFIG_GROUPS}").mock(return_value=httpx.Response(200, json={"data": "x"}))
            with pytest.raises(ClassicError, match="not a list"):
                make(token_file).list_groups()

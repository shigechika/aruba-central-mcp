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

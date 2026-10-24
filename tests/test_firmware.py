"""Tests for the firmware tools (New Central firmware details + optional Classic Central).

Response shapes follow docs/firmware-api-notes.md. New Central ``firmware-details``
items and Classic ``/firmware/v1/swarms`` fields are from the published specs;
the value strings of Classic ``status.state`` / ``status.reason`` are NOT
documented, so the ones used here are made up for the test.
"""

import asyncio
import os
from unittest.mock import patch

import pytest

from aruba_central_mcp import server
from aruba_central_mcp.classic import PATH_FW_COMPLIANCE, PATH_FW_VERSIONS, ClassicError
from aruba_central_mcp.client import PATH_APS, PATH_FIRMWARE_DETAILS, ArubaAPIError

APS = [
    {"deviceName": "ap-a1", "serialNumber": "SA1", "status": "ONLINE", "siteName": "Site A",
     "deviceGroupName": "Group-One", "clusterId": "c1", "clusterName": "swarm-a", "firmwareVersion": "8.10.0.14_1"},
    {"deviceName": "ap-a2", "serialNumber": "SA2", "status": "OFFLINE", "siteName": "Site A",
     "deviceGroupName": "Group-One", "clusterId": "c1", "clusterName": "swarm-a", "firmwareVersion": "8.10.0.14_1"},
    {"deviceName": "ap-b1", "serialNumber": "SB1", "status": "ONLINE", "siteName": "Site B",
     "deviceGroupName": "Group-Two", "clusterId": "c2", "clusterName": "swarm-b", "firmwareVersion": "8.13.3.1_2"},
]
FW_DETAILS = [
    {"serialNumber": "SA1", "firmwareVersion": "8.10.0.14_1", "recommendedVersion": "8.10.0.24_3",
     "upgradeStatus": "Upgrade Available", "deviceType": "ACCESS_POINT", "siteName": "Site A"},
    {"serialNumber": "SB1", "firmwareVersion": "8.13.3.1_2", "recommendedVersion": "8.13.3.1_2",
     "upgradeStatus": "Up To Date", "deviceType": "ACCESS_POINT", "siteName": "Site B"},
]


class FakeNewCentral:
    def __init__(self, fw_error=False):
        self.fw_error = fw_error
        self.calls = []

    def fetch_all(self, path, limit=1000, params=None):
        self.calls.append((path, params))
        if path == PATH_APS:
            return APS
        if path == PATH_FIRMWARE_DETAILS:
            if self.fw_error:
                raise ArubaAPIError("API error: 403", status_code=403)
            return FW_DETAILS
        return []

    def close(self):
        pass


class FakeClassic:
    def __init__(self, fail=False):
        self.fail = fail
        self.groups_asked = []

    def list_swarms(self, group=""):
        if self.fail:
            raise ClassicError("Classic API error (/firmware/v1/swarms): HTTP 500")
        return [
            {"swarm_id": "c1", "swarm_name": "swarm-a", "firmware_version": "8.10.0.14_1", "recommended": "8.10.0.24_3",
             "upgrade_required": True, "status": {"state": "example-failed-state", "reason": "example reason text",
                                                   "firmware_scheduled_at": 0}},
        ]

    def get(self, path, params=None):
        if path == PATH_FW_COMPLIANCE:
            self.groups_asked.append(params["group"])
            return {"firmware_compliance_version": "8.13.3.1_2"}
        if path == PATH_FW_VERSIONS:
            return {"data": [{"firmware_version": "8.13.3.1_2", "release_status": "release", "create_date": "2026-10-20"}]}
        return {}

    def close(self):
        pass


@pytest.fixture(autouse=True)
def reset():
    server._reset_client()
    yield
    server._reset_client()


def run(new_central=None, classic=None, **kwargs):
    with patch.object(server, "_get_client", return_value=new_central or FakeNewCentral()), \
            patch.object(server, "_get_classic", return_value=classic):
        return server.firmware_status(**kwargs)


class TestFirmwareStatus:
    def test_one_line_per_swarm_with_group_site_and_versions(self):
        out = run()
        assert out.startswith("# Firmware Status (2 swarms, 3 APs)")
        line_a = next(line for line in out.splitlines() if "swarm-a" in line)
        assert "group=Group-One(2)" in line_a and "site=Site A(2)" in line_a
        assert "aps=1/2 online" in line_a and "fw=8.10.0.14_1(2)" in line_a
        assert "recommended=8.10.0.24_3(1)" in line_a and "upgrade_status=Upgrade Available(1)" in line_a
        assert "classic:" not in out  # Classic not configured

    @pytest.mark.parametrize(
        "kwargs, expected",
        [
            ({"group": "group-one"}, ["swarm-a"]),
            ({"site": "SITE B"}, ["swarm-b"]),
            ({"swarm_name": "Swarm-A"}, ["swarm-a"]),
            ({"group": "Group-One", "site": "Site B"}, []),
        ],
    )
    def test_filters_combine_case_insensitively(self, kwargs, expected):
        out = run(**kwargs)
        if not expected:
            assert out == "No swarms matched."
            return
        names = [n for n in ("swarm-a", "swarm-b") if f"**{n}**" in out]
        assert names == expected

    def test_new_central_firmware_failure_is_visible(self):
        out = run(new_central=FakeNewCentral(fw_error=True))
        assert "## Notes" in out and "firmware details unavailable" in out
        assert "fw=8.10.0.14_1(2)" in out  # still reported from the AP listing

    def test_classic_adds_state_reason_and_group_compliance(self):
        classic = FakeClassic()
        out = run(classic=classic)
        line_a = next(line for line in out.splitlines() if "swarm-a" in line)
        assert "classic: state=example-failed-state reason=example reason text" in line_a
        assert "upgrade_required=True" in line_a
        line_b = next(line for line in out.splitlines() if "swarm-b" in line)
        assert "classic: not found" in line_b
        assert "## Group compliance (Classic, IAP)" in out and "- Group-One: 8.13.3.1_2" in out
        assert sorted(classic.groups_asked) == ["Group-One", "Group-Two"]

    def test_classic_failure_is_visible_not_silent(self):
        out = run(classic=FakeClassic(fail=True))
        assert "Classic Central swarm firmware unavailable" in out


class TestFirmwareVersions:
    def test_lists_versions(self):
        with patch.object(server, "_get_classic", return_value=FakeClassic()):
            out = server.firmware_versions("iap")
        assert out.startswith("# Firmware Versions (device_type=IAP, 1 total)") and "8.13.3.1_2 release" in out

    def test_bad_device_type_is_refused(self):
        with patch.object(server, "_get_classic", return_value=FakeClassic()):
            with pytest.raises(ValueError, match="device_type"):
                server.firmware_versions("AP")

    def test_not_configured_is_an_error(self):
        with patch.object(server, "_get_classic", return_value=None):
            with pytest.raises(ValueError, match="not configured"):
                server.firmware_versions()


def _tool_names(target):
    async def names():
        return {t.name for t in await target.list_tools()}

    return asyncio.run(names())


class TestRegistration:
    def test_firmware_versions_absent_without_classic_env(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ARUBA_CLASSIC_")}
        fresh = server._Server("t")
        with patch.dict(os.environ, env, clear=True):
            server._register_optional_tools(fresh)
        assert "firmware_versions" not in _tool_names(fresh)
        assert "firmware_status" in _tool_names(server.mcp)

    def test_firmware_versions_present_with_classic_env(self):
        fresh = server._Server("t")
        with patch.dict(os.environ, {name: "x" for name in server.CLASSIC_ENV}):
            server._register_optional_tools(fresh)
        assert "firmware_versions" in _tool_names(fresh)


class TestHealthCheckClassic:
    class TokenClient:
        def _get_token(self):
            return "t"

        def close(self):
            pass

    def test_not_configured(self):
        with patch.object(server, "_get_client", return_value=self.TokenClient()), \
                patch.object(server, "_get_classic", return_value=None):
            result = server.health_check()
        assert result["classic"] == "not-configured" and result["status"] == "healthy"

    def test_classic_error_degrades(self):
        class Broken:
            def access_token(self):
                raise ClassicError("token refresh rejected (HTTP 400)")

        with patch.object(server, "_get_client", return_value=self.TokenClient()), \
                patch.object(server, "_get_classic", return_value=Broken()):
            result = server.health_check()
        assert result["classic"] == "error" and result["status"] == "degraded"
        assert "refresh" in result["classic_detail"]

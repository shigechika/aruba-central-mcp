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
from aruba_central_mcp.classic import PATH_FW_COMPLIANCE, PATH_FW_VERSIONS, ClassicAuthError, ClassicError
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
    persist_error = None

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

    def test_classic_failure_is_visible_and_stops_classic_calls(self):
        classic = FakeClassic(fail=True)
        out = run(classic=classic)
        assert "Classic Central request failed at group Group-One" in out and "skipped" in out
        assert classic.groups_asked == []  # no compliance call after the failure
        assert "classic:" not in out.split("## Notes")[0]  # no per-swarm Classic column
        assert "fw=8.10.0.14_1(2)" in out  # New Central data kept

    def test_classic_auth_failure_is_reported_once(self):
        class AuthBroken(FakeClassic):
            calls = 0

            def list_swarms(self, group=""):
                AuthBroken.calls += 1
                raise ClassicAuthError("token refresh rejected (HTTP 400)")

        out = run(classic=AuthBroken())
        assert AuthBroken.calls == 1 and out.count("authentication failed") == 1

    def test_classic_os_error_does_not_escape(self):
        class DiskBroken(FakeClassic):
            def list_swarms(self, group=""):
                raise PermissionError("lock file")

        out = run(classic=DiskBroken())
        assert "Classic Central request failed" in out and "lock file" in out

    def test_classic_asked_per_group_with_exact_names(self):
        classic = FakeClassic()
        classic.list_groups = []
        orig = classic.list_swarms

        def spy(group=""):
            classic.list_groups.append(group)
            return orig(group)

        classic.list_swarms = spy
        run(classic=classic, group="group-one")
        assert classic.list_groups == ["Group-One"]

    def test_duplicate_classic_names_are_ambiguous(self):
        class Dup(FakeClassic):
            def list_swarms(self, group=""):
                return [
                    {"swarm_id": "x1", "swarm_name": "swarm-b", "status": {}},
                    {"swarm_id": "x2", "swarm_name": "swarm-b", "status": {}},
                ]

        out = run(classic=Dup(), swarm_name="swarm-b")
        assert "classic: ambiguous (2 swarms named swarm-b)" in out

    def test_aps_without_a_cluster_are_grouped_per_group_and_site(self):
        loose = [
            {"deviceName": "x1", "serialNumber": "X1", "status": "ONLINE", "siteName": "S1", "deviceGroupName": "G1"},
            {"deviceName": "x2", "serialNumber": "X2", "status": "ONLINE", "siteName": "S2", "deviceGroupName": "G1"},
        ]
        nc = FakeNewCentral()
        nc.fetch_all = lambda path, limit=1000, params=None: loose if path == PATH_APS else []
        out = run(new_central=nc)
        assert "(no swarm: group=G1 site=S1)" in out and "(no swarm: group=G1 site=S2)" in out
        assert out.startswith("# Firmware Status (2 swarms, 2 APs)")

    def test_site_filter_narrows_the_firmware_details_read(self):
        nc = FakeNewCentral()
        run(new_central=nc, site="site b")
        fw_params = [p for path, p in nc.calls if path == PATH_FIRMWARE_DETAILS][0]
        assert fw_params["filter"] == "deviceType eq 'ACCESS_POINT' and siteName in ('Site B')"

    def test_no_filter_reads_every_ap(self):
        nc = FakeNewCentral()
        run(new_central=nc)
        fw_params = [p for path, p in nc.calls if path == PATH_FIRMWARE_DETAILS][0]
        assert fw_params["filter"] == "deviceType eq 'ACCESS_POINT'"


class TestEpochText:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (1761300000, "2025-10-24T"),
            (1761300000000, "2025-10-24T"),  # milliseconds
            (0, ""),
            (None, ""),
            (True, ""),
        ],
    )
    def test_seconds_and_milliseconds(self, value, expected):
        assert server._epoch_text(value).startswith(expected)

    def test_out_of_range_returns_the_raw_value(self):
        assert server._epoch_text(1e300) == str(1e300)


class TestFirmwareVersions:
    def test_lists_versions(self):
        with patch.object(server, "_get_classic", return_value=FakeClassic()):
            out = server.firmware_versions("iap")
        assert out.startswith("# Firmware Versions (device_type=IAP, 1 total)") and "8.13.3.1_2 release" in out

    def test_bad_device_type_is_refused(self):
        with patch.object(server, "_get_classic", return_value=FakeClassic()):
            with pytest.raises(ValueError, match="device_type"):
                server.firmware_versions("AP")

    def test_duplicate_names_are_refused(self):
        class Dup(FakeClassic):
            def list_swarms(self, group=""):
                return [{"swarm_id": "x1", "swarm_name": "vc"}, {"swarm_id": "x2", "swarm_name": "VC"}]

        with patch.object(server, "_get_classic", return_value=Dup()):
            out = server.firmware_versions(swarm_name="vc")
        assert out.startswith("Ambiguous: 2 swarms") and "x1" in out and "swarm_id" in out

    def test_swarm_id_wins(self):
        with patch.object(server, "_get_classic", return_value=FakeClassic()):
            out = server.firmware_versions(swarm_id="c1", swarm_name="ignored")
        assert out.startswith("# Firmware Versions (swarm_id=c1, 1 total)")

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

    def test_partial_classic_config_is_misconfigured(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ARUBA_CLASSIC_")}
        env.update({"ARUBA_CLASSIC_BASE_URL": "x", "ARUBA_CLASSIC_CLIENT_ID": "y"})
        with patch.dict(os.environ, env, clear=True), \
                patch.object(server, "_get_client", return_value=self.TokenClient()):
            result = server.health_check()
        assert result["classic"] == "misconfigured" and result["status"] == "degraded"
        assert "ARUBA_CLASSIC_TOKEN_FILE" in result["classic_detail"] and "detail" in result

    def test_classic_os_error_is_reported_not_raised(self):
        class DiskBroken:
            persist_error = None

            def access_token(self):
                raise PermissionError("cannot create lock")

        with patch.object(server, "_get_client", return_value=self.TokenClient()), \
                patch.object(server, "_get_classic", return_value=DiskBroken()):
            result = server.health_check()
        assert result["classic"] == "error" and result["status"] == "degraded"
        assert result["detail"].startswith("Classic Central:")

    def test_unsaved_rotated_pair_is_an_error(self):
        class Unsaved:
            persist_error = "could not be written"

            def access_token(self):
                return "t"

        with patch.object(server, "_get_client", return_value=self.TokenClient()), \
                patch.object(server, "_get_classic", return_value=Unsaved()):
            result = server.health_check()
        assert result["classic"] == "error" and "could not be written" in result["classic_detail"]

    def test_classic_error_degrades(self):
        class Broken:
            persist_error = None

            def access_token(self):
                raise ClassicError("token refresh rejected (HTTP 400)")

        with patch.object(server, "_get_client", return_value=self.TokenClient()), \
                patch.object(server, "_get_classic", return_value=Broken()):
            result = server.health_check()
        assert result["classic"] == "error" and result["status"] == "degraded"
        assert "refresh" in result["classic_detail"]


class TestMultiPageFirmwareDetails:
    """firmware-details through the real ArubaClient cursor paging (respx at the transport)."""

    def test_later_pages_reach_the_summary_and_keep_the_filter(self):
        import httpx
        import respx

        from aruba_central_mcp.client import TOKEN_URL, ArubaClient

        base = "apigw-test.central.example.invalid"
        aps = [
            {"deviceName": f"ap{i}", "serialNumber": f"S{i}", "status": "ONLINE", "siteName": "Site A",
             "deviceGroupName": "G", "clusterId": "c1", "clusterName": "swarm-a", "firmwareVersion": "old"}
            for i in range(3)
        ]
        page1 = {"items": [{"serialNumber": "S0", "firmwareVersion": "8.13.3.1_2", "upgradeStatus": "Up To Date"},
                           {"serialNumber": "S1", "firmwareVersion": "8.13.3.1_2", "upgradeStatus": "Up To Date"}],
                 "count": 2, "total": 3, "next": "2"}
        page2 = {"items": [{"serialNumber": "S2", "firmwareVersion": "8.10.0.24_3", "upgradeStatus": "Upgrade Available"}],
                 "count": 1, "total": 3, "next": None}
        with respx.mock:
            respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 7200}))
            respx.get(f"https://{base}{PATH_APS}").mock(
                return_value=httpx.Response(200, json={"items": aps, "count": 3, "total": 3, "next": None})
            )
            fw = respx.get(f"https://{base}{PATH_FIRMWARE_DETAILS}").mock(
                side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
            )
            real = ArubaClient(base, "id", "secret")
            out = run(new_central=real, site="site a")
        assert fw.call_count == 2
        second = fw.calls[1].request.url.params
        assert second["next"] == "2" and "siteName in ('Site A')" in second["filter"]
        assert "fw=8.13.3.1_2(2), 8.10.0.24_3(1)" in out
        assert "upgrade_status=Up To Date(2), Upgrade Available(1)" in out

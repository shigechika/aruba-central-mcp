"""Tests for the firmware tools (New Central firmware details + optional Classic Central).

Response shapes follow docs/firmware-api-notes.md. Classic shapes are the ones
seen live: ``/configuration/v2/groups`` ``data`` is a list of one-element lists;
``/firmware/v1/swarms`` rows carry no group; the compliance answer has
``compliance_scheduled_at`` only when an upgrade is scheduled. The value
strings of Classic ``status.state`` / ``status.reason`` are made up for the test.
"""

import asyncio
import os
import time
from unittest.mock import patch

import pytest

from aruba_central_mcp import server
from aruba_central_mcp.classic import (
    PATH_FW_COMPLIANCE,
    ClassicAuthError,
    ClassicDeadline,
    ClassicError,
)
from aruba_central_mcp.client import PATH_APS, PATH_FIRMWARE_DETAILS, ArubaAPIError

# AOS-8 APs as New Central lists them: no deviceGroupName.
APS = [
    {"deviceName": "ap-a1", "serialNumber": "SA1", "status": "ONLINE", "siteName": "Site A",
     "clusterId": "c1", "clusterName": "swarm-a", "firmwareVersion": "8.10.0.14_1"},
    {"deviceName": "ap-a2", "serialNumber": "SA2", "status": "OFFLINE", "siteName": "Site A",
     "clusterId": "c1", "clusterName": "swarm-a", "firmwareVersion": "8.10.0.14_1"},
    {"deviceName": "ap-b1", "serialNumber": "SB1", "status": "ONLINE", "siteName": "Site B",
     "clusterId": "c2", "clusterName": "swarm-b", "firmwareVersion": "8.13.3.1_2"},
]
FW_DETAILS = [
    {"serialNumber": "SA1", "firmwareVersion": "8.10.0.14_1", "recommendedVersion": "8.10.0.24_3",
     "upgradeStatus": "Upgrade Available", "deviceType": "ACCESS_POINT", "siteName": "Site A"},
    {"serialNumber": "SB1", "firmwareVersion": "8.13.3.1_2", "recommendedVersion": "8.13.3.1_2",
     "upgradeStatus": "Up To Date", "deviceType": "ACCESS_POINT", "siteName": "Site B"},
]
SCHEDULED = 1793000000  # epoch seconds

#: Classic data per group, rows without a group key (as the API returns them).
CLASSIC_GROUPS = {
    "grp-one": [
        {"swarm_id": "c1", "swarm_name": "swarm-a", "aps_count": 2, "device_status": "Up",
         "firmware_version": "8.10.0.14_1", "recommended": "8.10.0.24_3", "upgrade_required": True,
         "status": {"state": "example-state", "reason": "example reason text"}},
        {"swarm_id": "stale1", "swarm_name": "old-vc", "aps_count": 0, "device_status": "Down",
         "firmware_version": "8.6.0.16_1", "recommended": "8.10.0.24_3", "upgrade_required": True, "status": {}},
    ],
    "grp-two": [
        {"swarm_id": "c2", "swarm_name": "swarm-b", "aps_count": 1, "device_status": "Up",
         "firmware_version": "8.13.3.1_2", "recommended": "8.13.3.1_2", "upgrade_required": False,
         "status": {"state": "example-ok", "reason": "Firmware version upto date"}},
    ],
    "grp-empty": [],
    "grp-stale": [
        {"swarm_id": "stale2", "swarm_name": "gone-vc", "aps_count": 0, "device_status": "Down",
         "firmware_version": "8.6.0.16_1", "recommended": "8.10.0.24_3", "upgrade_required": True, "status": {}},
    ],
}
COMPLIANCE = {
    "grp-one": {"firmware_compliance_version": "8.10.0.24_3", "compliance_scheduled_at": SCHEDULED},
    "grp-two": {"firmware_compliance_version": "8.13.3.1_2"},
    "grp-empty": {"firmware_compliance_version": ""},
    "grp-stale": {"firmware_compliance_version": "8.10.0.24_3"},
}


class FakeNewCentral:
    def __init__(self, fw_error=False, aps=None):
        self.fw_error = fw_error
        self.aps = APS if aps is None else aps
        self.calls = []

    def fetch_all(self, path, limit=1000, params=None, deadline=None):
        self.calls.append((path, params))
        if path == PATH_APS:
            return self.aps
        if path == PATH_FIRMWARE_DETAILS:
            if self.fw_error:
                raise ArubaAPIError("API error: 403", status_code=403)
            return FW_DETAILS
        return []

    def close(self):
        pass


class FakeClassic:
    persist_error = None

    def __init__(self, fail=False, fail_group=None, groups=None, compliance_fail=None, deadline_after=None):
        self.fail = fail
        self.fail_group = fail_group
        self.compliance_fail = compliance_fail
        self.deadline_after = deadline_after  # raise ClassicDeadline after this many swarm reads
        self.groups = CLASSIC_GROUPS if groups is None else groups
        self.calls = []

    def list_groups(self, deadline=None):
        self.calls.append(("groups", None))
        if self.fail:
            raise ClassicError("Classic API error (/configuration/v2/groups): HTTP 500")
        return list(self.groups)

    def list_swarms(self, group="", deadline=None):
        reads = len([c for c in self.calls if c[0] == "swarms"])
        if self.deadline_after is not None and reads >= self.deadline_after:
            raise ClassicDeadline("time budget used up")
        self.calls.append(("swarms", group))
        if group == self.fail_group:
            raise ClassicError("Classic API error (/firmware/v1/swarms): HTTP 500")
        if group:
            return self.groups.get(group, [])
        return [row for rows in self.groups.values() for row in rows]

    def get(self, path, params=None, deadline=None):
        if path == PATH_FW_COMPLIANCE:
            self.calls.append(("compliance", params["group"]))
            if params["group"] == self.compliance_fail:
                raise ClassicError("Classic API error (/firmware/v1/upgrade/compliance_version): HTTP 400")
            return COMPLIANCE.get(params["group"], {})
        return {}

    def list_versions(self, params, deadline=None):
        self.calls.append(("versions", params, deadline))
        return [{"firmware_version": "8.13.3.1_2", "release_status": "release", "create_date": "2026-10-20"}]

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


def line_of(out, name):
    return next(line for line in out.splitlines() if f"**{name}**" in line)


class TestFirmwareStatus:
    def test_one_line_per_swarm_with_site_and_versions(self):
        out = run()
        assert out.startswith("# Firmware Status (2 swarms, 3 APs)")
        line_a = line_of(out, "swarm-a")
        assert "group=-" in line_a and "site=Site A(2)" in line_a  # New Central has no group
        assert "aps=1/2 online" in line_a and "fw=8.10.0.14_1(2)" in line_a
        assert "recommended=8.10.0.24_3(1)" in line_a and "upgrade_status=Upgrade Available(1)" in line_a
        assert "classic:" not in out

    def test_new_central_firmware_failure_is_visible(self):
        out = run(new_central=FakeNewCentral(fw_error=True))
        assert "## Notes" in out and "firmware details unavailable" in out
        assert "fw=8.10.0.14_1(2)" in out

    def test_classic_join_by_id_adds_group_compliance_and_state(self):
        out = run(classic=FakeClassic())
        line_a = line_of(out, "swarm-a")
        assert "group=grp-one(2)" in line_a  # the Classic group, via swarm_id
        assert "classic: group=grp-one compliance=8.10.0.24_3 (pending: running 8.10.0.14_1(2))" in line_a
        assert "scheduled=" in line_a and "+00:00" in line_a and "(local " in line_a
        assert "state=example-state reason=example reason text upgrade_required=True" in line_a
        line_b = line_of(out, "swarm-b")
        assert "compliance=8.13.3.1_2 (matches running)" in line_b and "scheduled=" not in line_b

    def test_compliance_older_than_running_and_recommended_is_said_plainly(self):
        comp = {"grp-one": {"version": "8.6.0.16_1"}}
        text = server._compliance_text(
            comp["grp-one"],
            server.collections.Counter({"8.10.0.14_1": 2}),
            server.collections.Counter({"8.10.0.24_3": 2}),
        )
        assert "pending" in text and "older than running" in text and "older than recommended 8.10.0.24_3" in text

    def test_compliance_sections_and_classic_only_swarms(self):
        out = run(classic=FakeClassic())
        assert "## Group compliance (Classic, IAP)" in out
        assert "- grp-two: 8.13.3.1_2" in out and "- grp-empty: none" in out
        assert "## Classic-only swarms (2;" in out and "old-vc id=stale1 group=grp-one aps=0 device_status=Down" in out

    def test_classic_only_hidden_when_site_or_swarm_filter_given(self):
        assert "Classic-only" not in run(classic=FakeClassic(), site="Site A")
        assert "Classic-only" not in run(classic=FakeClassic(), swarm_name="swarm-a")

    def test_group_filter_uses_the_classic_group(self):
        out = run(classic=FakeClassic(), group="GRP-ONE")
        assert "**swarm-a**" in out and "**swarm-b**" not in out
        assert "old-vc" in out  # Classic-only swarm of that group
        assert "- grp-one: 8.10.0.24_3" in out and "grp-two" not in out

    def test_group_filter_without_classic_explains_itself(self):
        out = run(group="grp-one")
        assert out.startswith("No swarms matched.") and "Classic Central" in out

    def test_name_fallback_within_group_and_ambiguity(self):
        groups = {
            "grp-one": [{"swarm_id": "other-id", "swarm_name": "swarm-a", "status": {}}],
            "grp-two": [{"swarm_id": "x1", "swarm_name": "swarm-b", "status": {}},
                        {"swarm_id": "x2", "swarm_name": "swarm-b", "status": {}}],
        }
        aps = [dict(ap, deviceGroupName="grp-one" if ap["clusterId"] == "c1" else "grp-two") for ap in APS]
        out = run(new_central=FakeNewCentral(aps=aps), classic=FakeClassic(groups=groups))
        assert "classic: group=grp-one" in line_of(out, "swarm-a")  # joined by name within its group
        assert "classic: ambiguous (2 swarms named swarm-b)" in line_of(out, "swarm-b")

    def test_group_map_is_cached(self):
        classic = FakeClassic()
        run(classic=classic)
        first = list(classic.calls)
        run(classic=classic)
        assert classic.calls == first  # nothing re-read within the TTL, and no extra whole-list read
        assert not [c for c in first if c == ("swarms", "")]

    def test_cache_expires(self):
        classic = FakeClassic()
        run(classic=classic)
        server._classic_cache["groups_at"] -= server.CLASSIC_CACHE_TTL + 1
        for entry in server._classic_cache["read"].values():
            entry["at"] -= server.CLASSIC_CACHE_TTL + 1
        out = run(classic=classic)
        assert len([c for c in classic.calls if c[0] == "groups"]) == 2
        assert "s old" not in out

    def test_partial_group_failure_is_reported(self):
        classic = FakeClassic(fail_group="grp-two")
        out = run(classic=classic)
        assert "Classic groups not read yet (1 of 4): grp-two" in out
        assert "classic: group=grp-one" in line_of(out, "swarm-a")
        assert "not found in the groups read (1 not read yet)" in line_of(out, "swarm-b")
        assert set(server._classic_cache["read"]) == {"grp-one", "grp-empty", "grp-stale"}  # what was read is kept

    def test_partial_reads_rotate_and_converge(self):
        first = FakeClassic(deadline_after=1)
        out = run(classic=first)
        assert "time budget used up" in out
        read_first = {c[1] for c in first.calls if c[0] == "swarms"}
        assert len(read_first) == 1
        second = FakeClassic()
        out = run(classic=second)
        read_second = {c[1] for c in second.calls if c[0] == "swarms"}
        assert read_second == set(CLASSIC_GROUPS) - read_first  # continues with what was not read
        assert "not read yet" not in out

    def test_compliance_failure_keeps_the_swarm_mapping(self):
        out = run(classic=FakeClassic(compliance_fail="grp-two"))
        line_b = line_of(out, "swarm-b")
        assert "classic: group=grp-two compliance=unavailable" in line_b and "state=example-ok" in line_b
        assert "compliance version unavailable for 1 group(s): grp-two" in out
        assert "not read yet" not in out
        assert "- grp-two: unavailable" in out

    def test_time_budget_leaves_groups_unread(self, monkeypatch):
        monkeypatch.setattr(server, "TOOL_BUDGET_SECONDS", 1)
        out = run(classic=FakeClassic())
        assert "Classic groups not read yet (4 of 4)" in out and "time budget used up" in out

    def test_classic_failure_keeps_new_central_data(self):
        out = run(classic=FakeClassic(fail=True))
        assert "Classic Central request failed" in out and "Classic columns skipped" in out
        assert "classic:" not in out.split("## Notes")[0]
        assert "fw=8.10.0.14_1(2)" in out

    def test_classic_auth_failure_stops_all_classic_calls(self):
        class AuthBroken(FakeClassic):
            def list_groups(self, deadline=None):
                self.calls.append(("groups", None))
                raise ClassicAuthError("token refresh rejected (HTTP 400)")

        classic = AuthBroken()
        out = run(classic=classic)
        assert classic.calls == [("groups", None)] and out.count("authentication failed") == 1

    def test_classic_os_error_does_not_escape(self):
        class DiskBroken(FakeClassic):
            def list_groups(self, deadline=None):
                raise PermissionError("lock file")

        out = run(classic=DiskBroken())
        assert "Classic Central request failed" in out and "lock file" in out

    def test_name_fallback_needs_a_known_matching_group(self):
        # swarm-a (New Central group grp-one, id not in Classic) must not join a same-named swarm of another group
        groups = {"grp-one": [], "grp-two": [{"swarm_id": "zz", "swarm_name": "swarm-a", "status": {}}]}
        aps = [dict(APS[0], deviceGroupName="grp-one", clusterId="nc-only")]
        out = run(new_central=FakeNewCentral(aps=aps), classic=FakeClassic(groups=groups))
        assert "classic: not found" in line_of(out, "swarm-a")

    def test_versions_are_compared_normalised(self):
        comp = {"version": "8.13.3.1"}
        text = server._compliance_text(
            comp, server.collections.Counter({"8.13.3.1_2": 1}), server.collections.Counter({"8.13.3.1_2": 1})
        )
        assert text == "compliance=8.13.3.1 (matches running)"
        assert server._same_version("8.10.0.24_97188", "8.10.0.24")
        assert not server._same_version("8.10.0.24_1", "8.10.0.24_2")
        assert server._older("8.10.0.14_1", "8.10.0.24_3") and not server._older("8.13.3.1", "8.13.3.1_2")

    def test_classic_configured_but_failing_shows_the_failure(self):
        out = run(classic=FakeClassic(fail=True), group="grp-one")
        assert "configure Classic" not in out
        assert out.startswith("No swarms matched.") and "Classic Central request failed" in out

    def test_compliance_section_matches_groups_case_insensitively(self):
        aps = [dict(ap, deviceGroupName="GRP-ONE") for ap in APS[:2]]
        out = run(new_central=FakeNewCentral(aps=aps), classic=FakeClassic(), group="grp-one")
        assert "- grp-one: 8.10.0.24_3" in out

    def test_empty_ap_result_still_lists_classic_only_swarms(self):
        out = run(classic=FakeClassic(), group="grp-stale")
        assert out.startswith("# Firmware Status (0 swarms, 0 APs) [group=grp-stale]")
        assert "gone-vc id=stale2 group=grp-stale aps=0 device_status=Down" in out
        assert "- grp-stale: 8.10.0.24_3" in out

    def test_aps_without_a_cluster_are_grouped_per_group_and_site(self):
        loose = [
            {"deviceName": "x1", "serialNumber": "X1", "status": "ONLINE", "siteName": "S1", "deviceGroupName": "G1"},
            {"deviceName": "x2", "serialNumber": "X2", "status": "ONLINE", "siteName": "S2", "deviceGroupName": "G1"},
        ]
        out = run(new_central=FakeNewCentral(aps=loose))
        assert "(no swarm: group=G1 site=S1)" in out and "(no swarm: group=G1 site=S2)" in out
        assert out.startswith("# Firmware Status (2 swarms, 2 APs)")

    @pytest.mark.parametrize(
        "kwargs, expected",
        [({"site": "SITE B"}, ["swarm-b"]), ({"swarm_name": "Swarm-A"}, ["swarm-a"]), ({"site": "nowhere"}, [])],
    )
    def test_filters_are_case_insensitive(self, kwargs, expected):
        out = run(**kwargs)
        if not expected:
            assert out == "No swarms matched."
            return
        assert [n for n in ("swarm-a", "swarm-b") if f"**{n}**" in out] == expected

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

    def test_iso_with_offsets_and_no_zone_name(self):
        import re

        text = server._epoch_text(1761300000)
        assert re.fullmatch(r"2025-10-24T10:00:00\+00:00 \(local \d{4}-\d\d-\d\dT\d\d:\d\d[+-]\d\d:\d\d\)", text)

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
            def list_swarms(self, group="", deadline=None):
                return [{"swarm_id": "x1", "swarm_name": "vc"}, {"swarm_id": "x2", "swarm_name": "VC"}]

        with patch.object(server, "_get_classic", return_value=Dup()):
            out = server.firmware_versions(swarm_name="vc")
        assert out.startswith("Ambiguous: 2 swarms") and "x1" in out and "swarm_id" in out

    def test_swarm_id_wins(self):
        with patch.object(server, "_get_classic", return_value=FakeClassic()):
            out = server.firmware_versions(swarm_id="c1", swarm_name="ignored")
        assert out.startswith("# Firmware Versions (swarm_id=c1, 1 total)")

    def test_versions_read_runs_under_the_tool_deadline(self):
        fake = FakeClassic()
        before = time.monotonic()
        with patch.object(server, "_get_classic", return_value=fake):
            server.firmware_versions("iap")
        _, params, deadline = fake.calls[-1]
        assert params == {"device_type": "IAP"}
        assert before < deadline <= time.monotonic() + server.TOOL_BUDGET_SECONDS

    def test_empty_list_says_so(self):
        class Empty(FakeClassic):
            def list_versions(self, params, deadline=None):
                return []

        with patch.object(server, "_get_classic", return_value=Empty()):
            assert server.firmware_versions() == "No firmware versions returned (device_type=IAP)."

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
            # APs of one swarm split across two inventory pages (cursor paging).
            ap_route = respx.get(f"https://{base}{PATH_APS}").mock(
                side_effect=[
                    httpx.Response(200, json={"items": aps[:2], "count": 2, "total": 3, "next": "p2"}),
                    httpx.Response(200, json={"items": aps[2:], "count": 1, "total": 3, "next": None}),
                ]
            )
            fw = respx.get(f"https://{base}{PATH_FIRMWARE_DETAILS}").mock(
                side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
            )
            real = ArubaClient(base, "id", "secret")
            out = run(new_central=real, site="site a")
        assert ap_route.call_count == 2 and ap_route.calls[1].request.url.params["next"] == "p2"
        assert "aps=3/3 online" in out  # both inventory pages reached the swarm line
        assert fw.call_count == 2
        second = fw.calls[1].request.url.params
        assert second["next"] == "2" and "siteName in ('Site A')" in second["filter"]
        assert "fw=8.13.3.1_2(2), 8.10.0.24_3(1)" in out
        assert "upgrade_status=Up To Date(2), Upgrade Available(1)" in out

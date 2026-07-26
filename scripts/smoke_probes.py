"""Probe specs for this server's tools — the Central-specific half of the smoke test.

Every registered tool needs an entry here (the harness fails on a tool with no
spec), so adding a tool forces a decision: how would we know it works?

Three constraints shape everything below.

**Read-only.** Every tool here reads; nothing in Central is configured or
changed. A future tool that writes must be listed as state-changing and
skipped, and the test suite enforces that.

**No network-specific values in this file.** This repository is public, so a
probe may not name an access point, a site, an SSID or a client. The four tools
that need such an argument get it from an ``args_factory`` that discovers one
at run time, and skip when the network has none to offer.

**Bounded.** The ranking tools take a ``limit``; each probe passes a small
explicit one rather than the interactive default.

Assertions are shape-first: these tools answer with formatted text whose empty
case is a sentence ("No radios found."), not an error, so a probe pins the
header line it must produce. An empty answer is worth accepting on its own —
a network with no swarms configured is a real deployment, not a malfunction —
but a *lookup* that was handed a name discovered seconds earlier must not come
back empty, and those probes say so explicitly.
"""

from __future__ import annotations

import re
from typing import Any

from smoke_harness import Caller, Probe, SkipProbe


def _first_field(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


async def _first_ap(call: Caller) -> dict[str, Any]:
    """Discover an access point name at run time for the per-AP tool."""
    payload = await call("list_aps", {})
    # "- **<name>** [ONLINE] model=... site=... ip=... fw=... mac=..."
    name = _first_field(str(payload), r"^- \*\*(.+?)\*\* \[")
    if not name:
        raise SkipProbe("list_aps returned no access point to probe with")
    return {"ap_name": name}


async def _first_serial(call: Caller) -> dict[str, Any]:
    """Discover an AP serial number at run time for the throughput tool.

    From the radio list rather than the AP list: the AP rendering does not
    carry a serial, and every AP with a radio has one.
    """
    payload = await call("list_radios", {})
    serial = _first_field(str(payload), r"serial=(\S+)")
    if not serial:
        raise SkipProbe("list_radios returned no serial number to probe with")
    return {"serial_number": serial}


async def _first_client_mac(call: Caller) -> dict[str, Any]:
    """Discover a connected client's MAC at run time for the per-client tools."""
    payload = await call("list_clients", {})
    mac = _first_field(str(payload), r"\bmac=([0-9A-Fa-f:]{17})\b")
    if not mac:
        raise SkipProbe("no connected client to trace")
    return {"mac_address": mac}


#: Sentences a tool prints instead of answering. Most tools here do NOT render
#: their failures: an API error raises ArubaAPIError and the harness reports the
#: exception, so this guard is inert for them and kept only so a tool that
#: starts rendering errors is covered from the day it does. The two that
#: genuinely answer with text on failure are find_client_by_mac (its "not
#: found" branch) and daily_brief, which are guarded by name below.
NO_ERROR = (r"^(Error|Failed|Missing environment variable|Invalid)",)


PROBES: dict[str, Probe] = {
    # -- server / backend health ------------------------------------------
    "health_check": Probe(
        require_keys=("status", "service"),
        must_match=(r'"status": "(healthy|degraded)"',),
        allow_empty=True,
    ),
    # -- inventory ----------------------------------------------------------
    # A campus with zero APs would be a broken tenant rather than a quiet one,
    # but that is the deployment's business, not this test's: each probe
    # asserts that the tool rendered one of its two known answers.
    "list_aps": Probe(
        must_match=(r"^# Access Points \(\d+ total, \d+ online, \d+ offline\)|^No access points found\.",),
        must_not_match=NO_ERROR,
    ),
    "list_switches": Probe(
        must_match=(r"^# Switches \(\d+ total, \d+ online, \d+ offline\)|^No switches found\.",),
        must_not_match=NO_ERROR,
    ),
    "list_clients": Probe(
        must_match=(r"^# Wireless Clients \(\d+ total\)|^No clients found\.",),
        must_not_match=NO_ERROR,
    ),
    "list_radios": Probe(
        must_match=(r"^# Radios \(\d+ total\)|^No radios found\.",),
        must_not_match=NO_ERROR,
    ),
    "list_bssids": Probe(
        must_match=(r"^# BSSIDs \(\d+ total\)|^No BSSIDs found\.",),
        must_not_match=NO_ERROR,
    ),
    "list_wlans": Probe(
        must_match=(r"^# WLANs \(\d+ total\)|^No WLANs found\.",),
        must_not_match=NO_ERROR,
    ),
    "list_swarms": Probe(
        must_match=(r"^# Swarms \(\d+ total\)|^No swarms found\.",),
        must_not_match=NO_ERROR,
    ),
    "get_site_summary": Probe(
        must_match=(r"^# Site Summary \(\d+ sites, \d+ APs, \d+ clients\)|^No site data available\.",),
        must_not_match=NO_ERROR,
    ),
    # -- lookups: the argument was discovered moments ago -------------------
    # "not found" here would mean the two tools disagree about what a name is,
    # so unlike the listings above these probes refuse the empty answer.
    "get_ap_status": Probe(
        args_factory=_first_ap,
        must_match=(r"^# ",),
        must_not_match=(*NO_ERROR, r"^No access point found with name"),
    ),
    "find_client_by_mac": Probe(
        args_factory=_first_client_mac,
        must_match=(r"^# Client: ",),
        must_not_match=(*NO_ERROR, r"^No client found with MAC address"),
    ),
    # -- time-series --------------------------------------------------------
    # These read a metrics store rather than the device inventory, and a window
    # with no samples is an ordinary answer, so the empty case stays allowed.
    "get_ap_throughput": Probe(
        args_factory=_first_serial,
        args={"interface_type": "WIRELESS"},
        must_match=(r"^# AP Throughput: |^No throughput data for AP",),
        must_not_match=NO_ERROR,
    ),
    "get_client_mobility_trail": Probe(
        args_factory=_first_client_mac,
        must_match=(r"^# Mobility Trail: |^No mobility trail found for client",),
        must_not_match=NO_ERROR,
    ),
    "get_clients_trend": Probe(
        args={"group_by": "TYPE", "client_type": "ALL"},
        # The empty answer here is a paragraph of advice rather than a short
        # sentence, and it is a legitimate one: the analytics entitlement is
        # licensed separately from the inventory APIs.
        must_match=(r"^# Client Trend \(group_by=TYPE, type=ALL\)|^No client trend data available\.",),
        must_not_match=NO_ERROR,
    ),
    "get_top_aps": Probe(
        args={"usage_type": "total", "limit": 5},
        must_match=(r"^# Top APs by total usage|^No top APs data available",),
        must_not_match=NO_ERROR,
    ),
    "get_top_clients_by_usage": Probe(
        args={"limit": 5},
        must_match=(r"^# Top Clients by Usage|^No top clients data available\.",),
        must_not_match=NO_ERROR,
    ),
    # -- morning patrol ------------------------------------------------------
    # The one tool here that swallows every backend failure into an answer:
    # it catches Exception and returns its own header followed by "## CRITICAL
    # — API error: ...". That still satisfies a header assertion, so a dead
    # backend read as a healthy brief until this line existed.
    "daily_brief": Probe(
        args={"offline_threshold": 10.0},
        must_match=(r"^## daily_brief — ",),
        must_not_match=(*NO_ERROR, r"^## CRITICAL — API error:"),
        timeout=300,
    ),
}

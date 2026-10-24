"""MCP server exposing Aruba Central device and client status.

Provides read-only tools for querying Aruba Central via the
GreenLake New Central API (/network-monitoring/v1/, /network-services/v1/).
When ARUBA_CLASSIC_* is set, firmware tools also read the Classic Central
API (/firmware/v1/) for what New Central does not report (upgrade state with
its reason, group compliance version, available versions).

STDIO transport is used for JSON-RPC communication.
"""

from __future__ import annotations

import collections
import datetime
import functools
import inspect
import os
import re
import time
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError

from aruba_central_mcp import __version__
from aruba_central_mcp.classic import (
    PATH_FW_COMPLIANCE,
    PATH_FW_VERSIONS,
    ClassicAuthError,
    ClassicClient,
    ClassicDeadline,
    ClassicError,
)
from aruba_central_mcp.client import (
    ArubaAPIError,
    ArubaClient,
    ArubaClientError,
    PATH_APS,
    PATH_BSSIDS,
    PATH_CLIENTS,
    PATH_CLIENTS_TOPN_USAGE,
    PATH_CLIENTS_TREND,
    PATH_FIRMWARE_DETAILS,
    PATH_RADIOS,
    PATH_SWITCHES,
    PATH_SWARMS,
    PATH_WLANS,
)

def _expose_errors(fn):
    """Wrap a tool so any exception reaches the model as a ToolError with its message.

    mcp 1.x returned the exception text for every failing tool. mcp 2.x hides it
    (the model sees only "Error executing tool <name>") unless a ToolError is raised.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except (ToolError, MCPError):
                raise
            except Exception as exc:
                raise ToolError(str(exc) or type(exc).__name__) from exc

    else:

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (ToolError, MCPError):
                raise
            except Exception as exc:
                raise ToolError(str(exc) or type(exc).__name__) from exc

    return wrapper


class _Server(MCPServer):
    """MCPServer whose tools report their exception messages (see _expose_errors)."""

    def tool(self, *args, **kwargs):
        register = super().tool(*args, **kwargs)

        def decorator(fn):
            register(_expose_errors(fn))
            return fn

        return decorator


mcp = _Server("aruba-central", version=__version__)

_client: ArubaClient | None = None


def _get_client() -> ArubaClient:
    """Return a shared ArubaClient instance, created on first call.

    Configuration is read from environment variables:
        ARUBA_CENTRAL_BASE_URL: API gateway URL.
        ARUBA_CENTRAL_CLIENT_ID: OAuth2 client ID.
        ARUBA_CENTRAL_CLIENT_SECRET: OAuth2 client secret.
    """
    global _client
    if _client is not None:
        return _client

    base_url = os.environ.get("ARUBA_CENTRAL_BASE_URL", "")
    client_id = os.environ.get("ARUBA_CENTRAL_CLIENT_ID", "")
    client_secret = os.environ.get("ARUBA_CENTRAL_CLIENT_SECRET", "")

    if not all([base_url, client_id, client_secret]):
        raise ValueError(
            "Missing environment variables. Set ARUBA_CENTRAL_BASE_URL, "
            "ARUBA_CENTRAL_CLIENT_ID, and ARUBA_CENTRAL_CLIENT_SECRET."
        )

    _client = ArubaClient(base_url, client_id, client_secret)
    return _client


def _reset_client() -> None:
    """Reset the shared client (for testing)."""
    global _client, _classic
    if _client is not None:
        _client.close()
    _client = None
    if _classic is not None:
        _classic.close()
    _classic = None
    _reset_classic_cache()


CLASSIC_ENV = (
    "ARUBA_CLASSIC_BASE_URL",
    "ARUBA_CLASSIC_CLIENT_ID",
    "ARUBA_CLASSIC_CLIENT_SECRET",
    "ARUBA_CLASSIC_TOKEN_FILE",
)

_classic: ClassicClient | None = None


#: Errors a Classic call can raise besides ClassicError (token-file I/O, odd JSON shapes).
CLASSIC_FAILURES = (ClassicError, OSError, ValueError, AttributeError, TypeError)


def classic_configured() -> bool:
    """True when every ARUBA_CLASSIC_* variable is set (the Classic tools are offered only then)."""
    return all(os.environ.get(name) for name in CLASSIC_ENV)


def classic_missing() -> list[str]:
    """The unset ARUBA_CLASSIC_* names when some but not all are set; [] when all or none are."""
    missing = [name for name in CLASSIC_ENV if not os.environ.get(name)]
    return missing if 0 < len(missing) < len(CLASSIC_ENV) else []


def _get_classic() -> ClassicClient | None:
    """The shared Classic Central client, or None when ARUBA_CLASSIC_* is incomplete."""
    global _classic
    if _classic is not None:
        return _classic
    if not classic_configured():
        return None
    _classic = ClassicClient(*(os.environ[name] for name in CLASSIC_ENV))
    return _classic


# A MAC is 12 hex digits, or 6 colon-separated hex octets (dashes are
# normalised to colons first). A charset-only check would wrongly accept
# structurally-invalid values like ":" or "::::".
_MAC_RE = re.compile(r"[0-9a-f]{12}|(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")
# Must start with an alphanumeric so a bare "." / ".." (a path-traversal
# segment) is rejected — a serial goes straight into a URL path segment.
_SERIAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _odata_literal(value: str) -> str:
    """Escape a value for an OData v4 single-quoted string literal.

    A single quote terminates the literal, so it must be doubled; otherwise an
    LLM-supplied filter value (site/SSID name, timestamp) could alter the
    filter expression.
    """
    return value.replace("'", "''")


def _safe_mac(mac_address: str) -> str:
    """Normalise a MAC and validate it before it goes into a URL path segment.

    Rejects anything outside hex/colon so an LLM-supplied value cannot inject a
    new path segment or query string. Raises ``ArubaClientError`` on a bad value.
    """
    mac = mac_address.lower().replace("-", ":")
    if not _MAC_RE.fullmatch(mac):
        raise ArubaClientError(f"invalid MAC address: {mac_address!r}")
    return mac


def _safe_serial(serial: str) -> str:
    """Validate an AP serial before it goes into a URL path segment."""
    if not _SERIAL_RE.fullmatch(serial):
        raise ArubaClientError(f"invalid serial number: {serial!r}")
    return serial


def _build_odata_filter(**kwargs: str) -> Optional[str]:
    """Build an OData v4.0 filter string from keyword arguments.

    Only non-empty values are included. All values use the 'eq' operator.
    Returns None if no filters apply.
    """
    clauses = [
        f"{field} eq '{_odata_literal(value)}'"
        for field, value in kwargs.items()
        if value
    ]
    return " and ".join(clauses) if clauses else None


@mcp.tool()
def health_check() -> dict:
    """Report server version and Aruba Central backend authentication.

    Call this at session start (or after a tool-call timeout) to confirm the MCP
    is up, see which version is running, and verify the Aruba Central backend can
    be authenticated. Lightweight: it builds the client and obtains an OAuth2
    access token (GreenLake SSO, reusing the cached token) — it does NOT fetch
    APs, switches, clients, or any other data endpoint.

    Always returns the same keys: ``status`` (healthy / degraded / error),
    ``service``, ``version``, ``base_url`` (the configured
    ARUBA_CENTRAL_BASE_URL, empty string if unset), ``auth`` (ok / error /
    missing-env) and ``classic`` (not-configured / ok / error / misconfigured:
    the optional Classic Central token used by the firmware tools;
    ``misconfigured`` means some ARUBA_CLASSIC_* variables are set and others
    are not). ``error`` and ``misconfigured`` make the status degraded and add
    ``classic_detail``. On a degraded or error result, ``detail`` carries the
    reason (the New Central one first when both fail).
    """

    # Fixed shape: every key is present regardless of outcome, so callers can
    # read it uniformly and rely on `status` to judge health.
    result: dict = {
        "status": "healthy",
        "service": "aruba-central-mcp",
        "version": __version__,
        "base_url": os.environ.get("ARUBA_CENTRAL_BASE_URL", ""),
        "auth": "unknown",
        "classic": "not-configured",
    }

    # Backend: build the client and obtain an OAuth2 token. Reuse the cached
    # singleton so this is one cheap round trip (or none if already valid).
    try:
        client = _get_client()
        client._get_token()
        result["auth"] = "ok"
    except ValueError as e:
        # _get_client raises ValueError when required env vars are unset.
        result["status"] = "error"
        result["auth"] = "missing-env"
        result["detail"] = str(e)
    except ArubaClientError as e:
        # Token request failed (auth rejected / network / API error).
        _reset_client()
        result["status"] = "degraded"
        result["auth"] = "error"
        result["detail"] = f"Aruba Central error: {e}"

    # Optional Classic Central access (firmware tools). Probed only when configured;
    # a failure degrades the server but never hides the New Central result above.
    classic_problem = None
    missing = classic_missing()
    if missing:
        result["classic"] = "misconfigured"
        classic_problem = f"Classic Central partly configured, missing: {', '.join(missing)}"
    else:
        classic = _get_classic()
        if classic is not None:
            try:
                classic.access_token()
                result["classic"] = "ok"
                if classic.persist_error:
                    result["classic"] = "error"
                    classic_problem = classic.persist_error
            except CLASSIC_FAILURES as e:
                result["classic"] = "error"
                classic_problem = str(e) or type(e).__name__
    if classic_problem:
        result["classic_detail"] = classic_problem
        if result["status"] == "healthy":
            result["status"] = "degraded"
        result.setdefault("detail", f"Classic Central: {classic_problem}")

    return result


# -- Format helpers ----------------------------------------------------------


def _format_ap(ap: dict) -> str:
    """Format a single AP record as a readable string."""
    name = ap.get("deviceName", "unknown")
    status = ap.get("status", "unknown")
    model = ap.get("model", "")
    site = ap.get("siteName", "")
    ip = ap.get("ipv4", "")
    fw = ap.get("firmwareVersion", "")
    mac = ap.get("macAddress", "")
    return (
        f"- **{name}** [{status}] model={model} site={site} "
        f"ip={ip} fw={fw} mac={mac}"
    )


def _format_switch(sw: dict) -> str:
    """Format a single switch record as a readable string."""
    name = sw.get("deviceName", "unknown")
    status = sw.get("status", "unknown")
    model = sw.get("model", "")
    ip = sw.get("ipv4", "")
    fw = sw.get("firmwareVersion", "")
    mac = sw.get("macAddress", "")
    sw_type = sw.get("switchType", "")
    return (
        f"- **{name}** [{status}] model={model} type={sw_type} "
        f"ip={ip} fw={fw} mac={mac}"
    )


def _format_client(cl: dict) -> str:
    """Format a single wireless client record as a readable string."""
    name = cl.get("clientName") or cl.get("macAddress", "unknown")
    mac = cl.get("macAddress", "")
    ip = cl.get("ipv4", "")
    ssid = cl.get("wlanName", "")
    band = cl.get("wirelessBand", "")
    signal = cl.get("snr", "")
    ap_name = cl.get("connectedTo", "")
    auth = cl.get("authenticationType", "")
    site = cl.get("siteName", "")
    return (
        f"- **{name}** mac={mac} ip={ip} ssid={ssid} "
        f"band={band} snr={signal}dB ap={ap_name} auth={auth} site={site}"
    )


def _format_radio(radio: dict) -> str:
    """Format a single radio record as a readable string."""
    name = radio.get("deviceName", "unknown")
    band = radio.get("band", "")
    status = radio.get("status", "")
    serial = radio.get("serialNumber", "")
    mac = radio.get("macAddress", "")
    site = radio.get("siteName", "")
    channel = radio.get("channel", "")
    utilization = radio.get("channelUtilization", "")
    noise = radio.get("noiseFloor", "")
    tx_power = radio.get("txPower", "")
    return (
        f"- **{name}** [{status}] band={band} ch={channel} "
        f"util={utilization}% noise={noise}dBm txPower={tx_power}dBm "
        f"serial={serial} mac={mac} site={site}"
    )


def _format_bssid(bssid: dict) -> str:
    """Format a single BSSID record as a readable string."""
    name = bssid.get("deviceName", "unknown")
    mac = bssid.get("macAddress", "")
    bssid_val = bssid.get("bssid", "")
    wlan = bssid.get("wlanName", "")
    band = bssid.get("band", "")
    radio_mac = bssid.get("radioMacAddress", "")
    site = bssid.get("siteName", "")
    return (
        f"- **{name}** bssid={bssid_val} wlan={wlan} band={band} "
        f"radioMac={radio_mac} apMac={mac} site={site}"
    )


def _format_wlan(wlan: dict) -> str:
    """Format a single WLAN record as a readable string."""
    name = wlan.get("wlanName", "unknown")
    band = wlan.get("band", "")
    status = wlan.get("status", "")
    security = wlan.get("securityLevel", wlan.get("security", ""))
    vlan = wlan.get("vlan", "")
    return (
        f"- **{name}** [{status}] band={band} security={security} vlan={vlan}"
    )


def _format_swarm(swarm: dict) -> str:
    """Format a single swarm (AP cluster) record as a readable string."""
    name = swarm.get("clusterName", "unknown")
    cluster_id = swarm.get("clusterId", "")
    conductor = swarm.get("conductorDeviceName", "")
    conductor_serial = swarm.get("conductorSerialNumber", "")
    site = swarm.get("siteName", "")
    ip = swarm.get("ipv4", "")
    fw = swarm.get("firmwareVersion", swarm.get("softwareVersion", ""))
    return (
        f"- **{name}** id={cluster_id} conductor={conductor}({conductor_serial}) "
        f"site={site} ip={ip} fw={fw}"
    )


# -- MCP tools ---------------------------------------------------------------


@mcp.tool()
def list_aps(site: str = "", status: str = "") -> str:
    """List access points with device-level overview.

    Use this for AP inventory and availability checks. For RF details
    (channel, utilization, noise floor), use list_radios instead.

    Args:
        site: Filter by site name (exact match, server-side). Empty for all.
        status: Filter by status (e.g. "ONLINE", "OFFLINE"). Empty for all.
    """
    client = _get_client()
    odata = _build_odata_filter(siteName=site, status=status.upper() if status else "")
    params = {"filter": odata} if odata else None
    items = client.fetch_all(PATH_APS, params=params)

    if not items:
        return "No access points found."

    total_online = sum(1 for ap in items if (ap.get("status") or "").upper() == "ONLINE")
    total_offline = len(items) - total_online
    header = f"# Access Points ({len(items)} total, {total_online} online, {total_offline} offline)\n\n"
    return header + "\n".join(_format_ap(ap) for ap in items)


@mcp.tool()
def list_switches() -> str:
    """List all switches from Aruba Central.

    Returns switch name, status, model, type, IP, firmware, and MAC address.
    """
    client = _get_client()
    items = client.fetch_all(PATH_SWITCHES, limit=100)

    if not items:
        return "No switches found."

    total_online = sum(1 for sw in items if (sw.get("status") or "").upper() == "ONLINE")
    total_offline = len(items) - total_online
    header = f"# Switches ({len(items)} total, {total_online} online, {total_offline} offline)\n\n"
    return header + "\n".join(_format_switch(sw) for sw in items)


@mcp.tool()
def list_clients(ssid: str = "", band: str = "") -> str:
    """List connected wireless clients with connection details.

    Returns client name, MAC, IP, SSID, band, SNR, connected AP, and auth type.
    For a single client's full details, use find_client_by_mac instead.

    Args:
        ssid: Filter by SSID name (exact match, server-side). Empty for all.
        band: Filter by wireless band (exact match, server-side). Empty for all.
    """
    client = _get_client()
    odata = _build_odata_filter(wlanName=ssid, wirelessBand=band)
    params = {"filter": odata} if odata else None
    items = client.fetch_all(PATH_CLIENTS, params=params)

    if not items:
        return "No clients found."

    header = f"# Wireless Clients ({len(items)} total)\n\n"
    return header + "\n".join(_format_client(cl) for cl in items)


@mcp.tool()
def find_client_by_mac(mac_address: str) -> str:
    """Look up a single client by MAC address (wireless or wired).

    Returns detailed info including OS, manufacturer, VLAN, and connection
    status. Uses direct API lookup (no full-list scan).

    Args:
        mac_address: Client MAC address (e.g. "aa:bb:cc:dd:ee:ff").
    """
    client = _get_client()
    mac = _safe_mac(mac_address)
    try:
        data = client.get(f"{PATH_CLIENTS}/{mac}")
    except ArubaAPIError as e:
        if e.status_code == 404:
            return f"No client found with MAC address {mac_address}."
        raise
    lines = [f"# Client: {data.get('clientName') or mac}"]
    for key, label in [
        ("macAddress", "MAC"),
        ("ipv4", "IPv4"),
        ("clientType", "Type"),
        ("wlanName", "SSID"),
        ("wirelessBand", "Band"),
        ("snr", "SNR (dB)"),
        ("connectedTo", "AP"),
        ("authenticationType", "Auth"),
        ("siteName", "Site"),
        ("status", "Status"),
        ("vlan", "VLAN"),
        ("os", "OS"),
        ("manufacturer", "Manufacturer"),
    ]:
        val = data.get(key)
        if val is not None:
            lines.append(f"- **{label}**: {val}")
    return "\n".join(lines)


@mcp.tool()
def get_ap_status(ap_name: str) -> str:
    """Get detailed status of a specific access point by name.

    Args:
        ap_name: AP device name (case-insensitive).
    """
    client = _get_client()
    items = client.fetch_all(PATH_APS)

    name_lower = ap_name.lower()
    matches = [
        ap for ap in items
        if (ap.get("deviceName") or "").lower() == name_lower
    ]

    if not matches:
        return f"No access point found with name '{ap_name}'."

    ap = matches[0]
    lines = [f"# {ap.get('deviceName', ap_name)}"]
    for key, label in [
        ("status", "Status"),
        ("model", "Model"),
        ("serialNumber", "Serial"),
        ("macAddress", "MAC"),
        ("ipv4", "IPv4"),
        ("publicIpv4", "Public IPv4"),
        ("firmwareVersion", "Firmware"),
        ("siteName", "Site"),
        ("deviceGroupName", "Group"),
        ("deployment", "Deployment"),
    ]:
        val = ap.get(key)
        if val is not None:
            lines.append(f"- **{label}**: {val}")
    return "\n".join(lines)


@mcp.tool()
def get_site_summary() -> str:
    """Get a summary of all sites with AP and client counts.

    Aggregates data across all APs and clients, grouped by site name.
    Shows total APs, online/offline counts, and client count per site.
    """
    client = _get_client()
    ap_items = client.fetch_all(PATH_APS)
    client_items = client.fetch_all(PATH_CLIENTS)

    # Aggregate APs by site
    sites: dict[str, dict] = {}
    for ap in ap_items:
        site = ap.get("siteName") or "(no site)"
        if site not in sites:
            sites[site] = {"aps": 0, "aps_online": 0, "aps_offline": 0, "clients": 0}
        sites[site]["aps"] += 1
        if (ap.get("status") or "").upper() == "ONLINE":
            sites[site]["aps_online"] += 1
        else:
            sites[site]["aps_offline"] += 1

    # Aggregate clients by site (New Central API provides siteName directly)
    for cl in client_items:
        site = cl.get("siteName") or "(no site)"
        if site not in sites:
            sites[site] = {"aps": 0, "aps_online": 0, "aps_offline": 0, "clients": 0}
        sites[site]["clients"] += 1

    if not sites:
        return "No site data available."

    lines = [
        f"# Site Summary ({len(sites)} sites, {len(ap_items)} APs, {len(client_items)} clients)\n",
        "| Site | APs | Online | Offline | Clients |",
        "|------|-----|--------|---------|---------|",
    ]
    for site_name in sorted(sites):
        s = sites[site_name]
        lines.append(
            f"| {site_name} | {s['aps']} | {s['aps_online']} | {s['aps_offline']} | {s['clients']} |"
        )
    return "\n".join(lines)


@mcp.tool()
def list_radios(site: str = "", band: str = "") -> str:
    """List AP radios with RF details.

    Use this for RF troubleshooting: channel assignment, channel utilization,
    noise floor, and TX power. Each AP typically has 2-3 radios (one per band).

    Args:
        site: Filter by site name (exact match, server-side). Empty for all.
        band: Filter by band (e.g. "2.4 GHz", "5 GHz"). Empty for all.
    """
    client = _get_client()
    odata = _build_odata_filter(siteName=site, band=band)
    params = {"filter": odata} if odata else None
    items = client.fetch_all(PATH_RADIOS, params=params)

    if not items:
        return "No radios found."

    header = f"# Radios ({len(items)} total)\n\n"
    return header + "\n".join(_format_radio(r) for r in items)


@mcp.tool()
def list_bssids(site: str = "") -> str:
    """List all BSSIDs (per-radio, per-SSID broadcast identifiers).

    Useful for identifying which radio on which AP is broadcasting a
    specific SSID. Each AP radio broadcasts one BSSID per WLAN.

    Args:
        site: Filter by site name (exact match, server-side). Empty for all.
    """
    client = _get_client()
    odata = _build_odata_filter(siteName=site)
    params = {"filter": odata} if odata else None
    items = client.fetch_all(PATH_BSSIDS, params=params)

    if not items:
        return "No BSSIDs found."

    header = f"# BSSIDs ({len(items)} total)\n\n"
    return header + "\n".join(_format_bssid(b) for b in items)


@mcp.tool()
def list_wlans(site_id: str = "", serial_number: str = "") -> str:
    """List configured WLANs (SSIDs) with security and VLAN settings.

    Shows each WLAN's name, band, operational status, security level,
    and VLAN assignment.

    Args:
        site_id: Filter by site ID. Empty for all.
        serial_number: Filter by AP serial number. Empty for all.
    """
    client = _get_client()
    params: dict = {}
    if site_id:
        params["site-id"] = site_id
    if serial_number:
        params["serial-number"] = serial_number
    items = client.fetch_all(PATH_WLANS, params=params or None)

    if not items:
        return "No WLANs found."

    header = f"# WLANs ({len(items)} total)\n\n"
    return header + "\n".join(_format_wlan(w) for w in items)


@mcp.tool()
def list_swarms(site: str = "") -> str:
    """List all AP swarms (clusters) from Aruba Central.

    Returns cluster name, conductor AP, site, IP, and firmware version.

    Args:
        site: Filter by site name (exact match, server-side). Empty for all.
    """
    client = _get_client()
    odata = _build_odata_filter(siteName=site)
    params = {"filter": odata} if odata else None
    items = client.fetch_all(PATH_SWARMS, params=params)

    if not items:
        return "No swarms found."

    header = f"# Swarms ({len(items)} total)\n\n"
    return header + "\n".join(_format_swarm(s) for s in items)


# -- firmware ------------------------------------------------------------------

#: Device types the Classic firmware API accepts.
CLASSIC_DEVICE_TYPES = ("IAP", "MAS", "HP", "CX", "CONTROLLER")


def _matches(value: str, wanted: str) -> bool:
    """Exact, case-insensitive name match; an empty ``wanted`` matches everything."""
    return not wanted or (value or "").strip().lower() == wanted.strip().lower()


def _top(counter: collections.Counter) -> str:
    """'a(3), b(1)' for a counter, most common first; '-' when empty."""
    return ", ".join(f"{k}({n})" for k, n in counter.most_common()) if counter else "-"


def _epoch_text(value: object) -> str:
    """An epoch timestamp (seconds, or milliseconds when that large) as ISO 8601: UTC, then the server's local offset.

    Returns "" for a missing or non-positive value, and the raw value when it cannot be converted.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return ""
    seconds = value / 1000 if value > 1e11 else value
    try:
        utc = datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc)
        local = utc.astimezone()
    except (ValueError, OverflowError, OSError):
        return str(value)
    return f"{utc.isoformat(timespec='seconds')} (local {local.isoformat(timespec='minutes')})"


def _version_parts(version: str) -> tuple:
    """(numeric dotted part, build number or None): "8.10.0.24_97188" -> ((8, 10, 0, 24), 97188)."""
    base, _, build = (version or "").strip().partition("_")
    numbers = tuple(int(n) for n in re.findall(r"\d+", base))
    return numbers, (int(build) if build.isdigit() else None)


def _same_version(a: str, b: str) -> bool:
    """Equal dotted parts, and equal builds when both carry one ("8.10.0.24" == "8.10.0.24_97188")."""
    (na, ba), (nb, bb) = _version_parts(a), _version_parts(b)
    return na == nb and (ba is None or bb is None or ba == bb)


def _older(a: str, b: str) -> bool:
    """True when version ``a`` is lower than ``b`` (builds compared only when both carry one)."""
    (na, ba), (nb, bb) = _version_parts(a), _version_parts(b)
    if na != nb:
        return na < nb
    return ba is not None and bb is not None and ba < bb


#: Longest OData filter the firmware-details endpoint accepts.
FILTER_MAX_LEN = 256
#: Seconds one firmware_status call may run in total (under a 60 s client cutoff).
TOOL_BUDGET_SECONDS = 48
#: Seconds a Classic group's swarms and compliance are reused within one process.
CLASSIC_CACHE_TTL = 300
#: Classic-only swarms listed at most.
MAX_CLASSIC_ONLY = 30

#: Classic group list and per-group reads, shared by calls in this process.
_classic_cache: dict = {"groups": None, "groups_at": 0.0, "read": {}}


def _reset_classic_cache() -> None:
    _classic_cache.update(groups=None, groups_at=0.0, read={})


def _classic_group_map(classic: ClassicClient, deadline: float) -> dict:
    """What Classic knows per group: its swarms (rows carry no group) and its IAP compliance version.

    Lists the groups (/configuration/v2/groups), then reads /firmware/v1/swarms?group=
    and the compliance version for each group whose cached read is older than
    CLASSIC_CACHE_TTL -- never-read groups first, then the oldest -- until
    ``deadline``. Whatever was read is cached, so a tenant too large for one call
    converges over a few calls. A compliance failure is recorded on its own and
    does not make the group's swarms unknown. ClassicAuthError propagates.
    """
    cache = _classic_cache
    now = time.monotonic()
    if cache["groups"] is None or now - cache["groups_at"] >= CLASSIC_CACHE_TTL:
        groups = classic.list_groups(deadline=deadline)
        cache.update(groups=groups, groups_at=time.monotonic())
        cache["read"] = {g: e for g, e in cache["read"].items() if g in groups}
    groups = cache["groups"]

    def age(g: str) -> float:
        entry = cache["read"].get(g)
        return float("inf") if entry is None else time.monotonic() - entry["at"]

    todo = sorted((g for g in groups if age(g) >= CLASSIC_CACHE_TTL), key=lambda g: -age(g))
    errors: dict[str, str] = {}
    out_of_time = False
    read_now = 0
    for g in todo:
        if deadline - time.monotonic() < 2:
            out_of_time = True
            break
        try:
            swarms = classic.list_swarms(group=g, deadline=deadline)
        except ClassicAuthError:
            raise
        except ClassicDeadline:
            out_of_time = True
            break
        except CLASSIC_FAILURES as e:
            errors[g] = str(e) or type(e).__name__
            continue
        entry = {"at": time.monotonic(), "swarms": swarms, "compliance": None, "compliance_error": None}
        cache["read"][g] = entry
        read_now += 1
        try:
            doc = classic.get(PATH_FW_COMPLIANCE, {"device_type": "IAP", "group": g}, deadline)
            entry["compliance"] = {
                "version": doc.get("firmware_compliance_version") or "",
                "scheduled_at": doc.get("compliance_scheduled_at"),
            }
        except ClassicAuthError:
            raise
        except CLASSIC_FAILURES as e:
            entry["compliance_error"] = str(e) or type(e).__name__

    now = time.monotonic()
    read = {g: e for g, e in cache["read"].items() if g in groups and now - e["at"] < CLASSIC_CACHE_TTL}
    unread = [g for g in groups if g not in read]
    return {
        "groups": groups,
        "rows": [(g, row) for g, e in read.items() for row in e["swarms"] if isinstance(row, dict)],
        "compliance": {g: e["compliance"] for g, e in read.items() if e["compliance"] is not None},
        "compliance_errors": {g: e["compliance_error"] for g, e in read.items() if e["compliance_error"]},
        "unread": unread,
        "errors": {g: errors.get(g, "time budget used up" if out_of_time else "not read") for g in unread},
        "read_now": read_now,
        "oldest_age": int(max((now - e["at"] for e in read.values()), default=0)),
    }


def _in_filter(field: str, values: list[str]) -> Optional[str]:
    """``field in ('a','b')`` for the values, or None when there are none."""
    if not values:
        return None
    return f"{field} in (" + ",".join(f"'{_odata_literal(v)}'" for v in values) + ")"


def _swarm_key(ap: dict, group: str) -> tuple:
    if ap.get("clusterId") or ap.get("clusterName"):
        return ("swarm", ap.get("clusterId") or "", ap.get("clusterName") or "")
    # APs without a cluster are grouped by where they are, never all together.
    return ("none", group, ap.get("siteName") or "")


def _swarm_label(key: tuple) -> str:
    if key[0] == "swarm":
        return key[2] or key[1]
    return f"(no swarm: group={key[1] or '-'} site={key[2] or '-'})"


def _compliance_text(comp: Optional[dict], running: collections.Counter, recommended: collections.Counter) -> str:
    """'compliance=V (...)' comparing the group's compliance version with what runs and what is recommended."""
    if comp is None:
        return "compliance=unknown"
    version = comp.get("version") or ""
    if not version:
        return "compliance=none"
    marks = []
    if running and all(_same_version(version, v) for v in running):
        marks.append("matches running")
    else:
        marks.append(f"pending: running {_top(running)}")
        if any(_older(version, v) for v in running):
            marks.append("older than running")
    if recommended:
        rec = recommended.most_common(1)[0][0]
        if _older(version, rec):
            marks.append(f"older than recommended {rec}")
    when = _epoch_text(comp.get("scheduled_at"))
    return f"compliance={version} ({'; '.join(marks)})" + (f" scheduled={when}" if when else "")


@mcp.tool()
def firmware_status(group: str = "", site: str = "", swarm_name: str = "") -> str:
    """Firmware of every AP swarm (cluster): running versions, upgrade status, group and site.

    Use this to see which swarms still need a firmware upgrade and what Central
    will do next. Read-only. The whole call is bounded (about 48 s); what could
    not be read in time is named under Notes.

    One line per swarm with its group(s) and site(s), AP count and how many are
    online, the running versions with AP counts, the recommended version and
    New Central's per-AP upgrade status (/network-services/v1/firmware-details).
    APs that belong to no swarm are listed per group and site.

    When Classic Central is configured (ARUBA_CLASSIC_*), each swarm also gets
    its Classic group, the group's compliance version (the version Central
    keeps the group's swarms on: an upgrade of a Classic IAP group happens when
    the compliance version changes, and ``scheduled`` is when that is set to
    run; a site-level upgrade in the UI does not change it), marked "matches
    running" or "pending", and "older than ..." when it is lower than the
    running or recommended version, plus Classic's upgrade ``state``,
    ``reason`` and ``upgrade_required``. New Central reports no group for
    AOS-8 APs, so the group comes from Classic; Classic data is cached per
    group for a few minutes. Swarms Classic knows but New Central does not
    (e.g. 0 APs, Down) are listed at the end when no site or swarm filter is
    given. A Classic failure is reported under Notes; the New Central data is
    still shown.

    Filters combine (all must match); each is an exact name, case-insensitive.
    Empty means no filter. ``group`` uses the Classic group when New Central has none.

    Args:
        group: Central group name.
        site: Site name.
        swarm_name: Swarm (cluster) name.
    """
    deadline = time.monotonic() + TOOL_BUDGET_SECONDS
    client = _get_client()
    all_aps = client.fetch_all(PATH_APS, deadline=deadline)
    notes: list[str] = []

    classic = _get_classic()
    missing = classic_missing()
    if missing:
        notes.append(f"Classic Central partly configured (missing: {', '.join(missing)}); Classic columns skipped")
    cmap: Optional[dict] = None
    if classic is not None:
        if classic.persist_error:
            notes.append(f"Classic Central: {classic.persist_error}")
        try:
            cmap = _classic_group_map(classic, deadline)
        except CLASSIC_FAILURES as e:
            kind = "authentication" if isinstance(e, ClassicAuthError) else "request"
            notes.append(f"Classic Central {kind} failed: {str(e) or type(e).__name__}; Classic columns skipped")
        if cmap is not None:
            if cmap["unread"]:
                detail = ", ".join(f"{g} ({cmap['errors'][g]})" for g in cmap["unread"][:10])
                notes.append(
                    f"Classic groups not read yet ({len(cmap['unread'])} of {len(cmap['groups'])}): {detail}; "
                    "their swarms show no Classic group (the next call continues with them)"
                )
            if cmap["compliance_errors"]:
                detail = ", ".join(f"{g} ({err})" for g, err in sorted(cmap["compliance_errors"].items())[:10])
                notes.append(f"Classic compliance version unavailable for {len(cmap['compliance_errors'])} group(s): {detail}")
            if cmap["oldest_age"] > 0:
                notes.append(f"Classic data up to {cmap['oldest_age']} s old (cached per group)")

    swarm_group: dict[str, str] = {}
    by_id: dict[str, tuple] = {}
    by_name: dict[str, list[tuple]] = collections.defaultdict(list)
    for g, row in (cmap or {}).get("rows", []):
        if row.get("swarm_id"):
            swarm_group[row["swarm_id"]] = g
            by_id[row["swarm_id"]] = (g, row)
        if row.get("swarm_name"):
            by_name[row["swarm_name"].lower()].append((g, row))

    def ap_group(ap: dict) -> str:
        return ap.get("deviceGroupName") or swarm_group.get(ap.get("clusterId") or "", "")

    aps = [
        ap for ap in all_aps
        if _matches(ap_group(ap), group)
        and _matches(ap.get("siteName"), site)
        and _matches(ap.get("clusterName"), swarm_name)
    ]

    fw_by_serial: dict[str, dict] = {}
    if aps:
        # With a filter, narrow the firmware-details read to the matched APs' sites
        # when the expression fits the endpoint's limit; otherwise read every AP.
        fw_filter = "deviceType eq 'ACCESS_POINT'"
        if group or site or swarm_name:
            sites_expr = _in_filter("siteName", sorted({ap["siteName"] for ap in aps if ap.get("siteName")}))
            narrowed = f"{fw_filter} and {sites_expr}" if sites_expr else ""
            if narrowed and len(narrowed) <= FILTER_MAX_LEN:
                fw_filter = narrowed
        try:
            for item in client.fetch_all(PATH_FIRMWARE_DETAILS, params={"filter": fw_filter}, deadline=deadline):
                if item.get("serialNumber"):
                    fw_by_serial[item["serialNumber"]] = item
        except ArubaClientError as e:
            notes.append(f"New Central firmware details unavailable: {e}")

    swarms: dict[tuple, dict] = {}
    for ap in aps:
        g = ap_group(ap)
        key = _swarm_key(ap, g)
        sw = swarms.setdefault(
            key,
            {
                "key": key,
                "name": _swarm_label(key),
                "id": key[1] if key[0] == "swarm" else "",
                "groups": collections.Counter(),
                "sites": collections.Counter(),
                "aps": 0,
                "online": 0,
                "versions": collections.Counter(),
                "recommended": collections.Counter(),
                "upgrade": collections.Counter(),
            },
        )
        sw["aps"] += 1
        if (ap.get("status") or "").upper() == "ONLINE":
            sw["online"] += 1
        if g:
            sw["groups"][g] += 1
        if ap.get("siteName"):
            sw["sites"][ap["siteName"]] += 1
        detail = fw_by_serial.get(ap.get("serialNumber") or "", {})
        version = detail.get("firmwareVersion") or ap.get("firmwareVersion")
        if version:
            sw["versions"][version] += 1
        if detail.get("recommendedVersion"):
            sw["recommended"][detail["recommendedVersion"]] += 1
        if detail.get("upgradeStatus"):
            sw["upgrade"][detail["upgradeStatus"]] += 1

    swarm_lines: list[str] = []
    joined: set[str] = set()
    shown_groups: set[str] = set()
    for sw in sorted(swarms.values(), key=lambda x: (x["name"].lower(), x["id"])):
        shown_groups.update(g.lower() for g in sw["groups"])
        line = (
            f"- **{sw['name']}** id={sw['id']} group={_top(sw['groups'])} site={_top(sw['sites'])} "
            f"aps={sw['online']}/{sw['aps']} online fw={_top(sw['versions'])} "
            f"recommended={_top(sw['recommended'])} upgrade_status={_top(sw['upgrade'])}"
        )
        if cmap is not None and sw["key"][0] == "swarm":
            column, swarm_id = _classic_column(sw, by_id, by_name, cmap)
            if swarm_id:
                joined.add(swarm_id)
            line += column
        swarm_lines.append(line)

    compliance_lines: list[str] = []
    if cmap is not None:
        wanted = {group.strip().lower()} if group else shown_groups
        for g in cmap["groups"]:
            if (group or site or swarm_name) and g.lower() not in wanted:
                continue
            if g in cmap["compliance"]:
                comp = cmap["compliance"][g]
                when = _epoch_text(comp.get("scheduled_at"))
                compliance_lines.append(f"- {g}: {comp.get('version') or 'none'}" + (f" scheduled={when}" if when else ""))
            elif g in cmap["compliance_errors"]:
                compliance_lines.append(f"- {g}: unavailable")

    extra_lines: list[str] = []
    if cmap is not None and not (site or swarm_name):
        nc_ids = {sw["id"] for sw in swarms.values() if sw["id"]} | {ap.get("clusterId") for ap in all_aps if ap.get("clusterId")}
        extra = [
            (g, row) for g, row in cmap["rows"]
            if row.get("swarm_id") not in joined and row.get("swarm_id") not in nc_ids and _matches(g, group)
        ]
        if extra:
            extra_lines.append(f"## Classic-only swarms ({len(extra)}; not seen in New Central, e.g. 0 APs or Down)")
            for g, row in extra[:MAX_CLASSIC_ONLY]:
                extra_lines.append(
                    f"- {row.get('swarm_name') or '?'} id={row.get('swarm_id') or ''} group={g} "
                    f"aps={row.get('aps_count')} device_status={row.get('device_status') or '-'} "
                    f"fw={row.get('firmware_version') or '-'}"
                )
            if len(extra) > MAX_CLASSIC_ONLY:
                extra_lines.append(f"- ... {len(extra) - MAX_CLASSIC_ONLY} more")

    if not swarm_lines and not extra_lines:
        if group and classic is None and not missing and not any(ap.get("deviceGroupName") for ap in all_aps):
            return (
                "No swarms matched. New Central reports no group for these APs; "
                "configure Classic Central (ARUBA_CLASSIC_*) to filter by group."
            )
        if not notes:
            return "No swarms matched."

    total_aps = sum(sw["aps"] for sw in swarms.values())
    filters = ", ".join(f"{k}={v}" for k, v in (("group", group), ("site", site), ("swarm", swarm_name)) if v)
    if swarm_lines or extra_lines:
        lines = [f"# Firmware Status ({len(swarms)} swarms, {total_aps} APs)" + (f" [{filters}]" if filters else ""), ""]
    else:
        lines = ["No swarms matched."]
    lines += swarm_lines
    if compliance_lines:
        lines += ["", "## Group compliance (Classic, IAP)"] + compliance_lines
    if extra_lines:
        lines += [""] + extra_lines
    if notes:
        lines += ["", "## Notes"] + [f"- {n}" for n in notes]
    return "\n".join(lines)


def _classic_column(sw: dict, by_id: dict[str, tuple], by_name: dict[str, list[tuple]], cmap: dict) -> tuple:
    """(text, joined swarm_id or "") for one swarm line.

    Joined by swarm_id (New Central clusterId equals Classic swarm_id). Otherwise by
    name, only to a Classic swarm whose group is known and is one of this swarm's
    groups; several such swarms are reported as ambiguous, never picked.
    """
    hit = by_id.get(sw["id"]) if sw["id"] else None
    if hit is None and sw["groups"]:
        groups = {g.lower() for g in sw["groups"]}
        candidates = {
            row.get("swarm_id") or id(row): (g, row)
            for g, row in by_name.get(sw["key"][2].lower(), [])
            if g.lower() in groups
        }
        if len(candidates) > 1:
            return f" | classic: ambiguous ({len(candidates)} swarms named {sw['key'][2]})", ""
        hit = next(iter(candidates.values()), None)
    if hit is None:
        if cmap.get("unread"):
            return f" | classic: not found in the groups read ({len(cmap['unread'])} not read yet)", ""
        return " | classic: not found in /firmware/v1/swarms", ""
    g, row = hit
    comp = cmap.get("compliance", {}).get(g)
    if comp is None and g in cmap.get("compliance_errors", {}):
        comp_text = "compliance=unavailable"
    else:
        comp_text = _compliance_text(comp, sw["versions"], sw["recommended"])
    st = row.get("status") if isinstance(row.get("status"), dict) else {}
    when = _epoch_text(st.get("firmware_scheduled_at"))
    text = (
        f" | classic: group={g} {comp_text}"
        f" state={st.get('state') or '-'} reason={st.get('reason') or '-'}"
        + (f" swarm_scheduled={when}" if when else "")
        + f" upgrade_required={row.get('upgrade_required')}"
    )
    return text, row.get("swarm_id") or ""


def firmware_versions(device_type: str = "IAP", swarm_name: str = "", group: str = "", swarm_id: str = "") -> str:
    """Firmware versions Classic Central offers for a device type or one swarm.

    Read-only (/firmware/v1/versions). Registered only when Classic Central is
    configured (ARUBA_CLASSIC_*). Pick the target version of an upgrade from
    this list; release_status "beta" marks a version not yet released.

    Args:
        device_type: One of IAP (Instant AP swarms), MAS, HP, CX, CONTROLLER.
            Used when no swarm is named.
        swarm_name: Swarm (cluster) name, exact and case-insensitive; lists the
            versions that swarm supports. If several swarms share the name, the
            call is refused: narrow it with ``group`` or pass ``swarm_id``.
        group: Central group name used to narrow ``swarm_name`` (exact name as in Central).
        swarm_id: Swarm id (from firmware_status); wins over ``swarm_name``.
    """
    classic = _get_classic()
    if classic is None:
        raise ValueError("Classic Central is not configured (set ARUBA_CLASSIC_*).")
    device_type = (device_type or "").strip().upper()
    if device_type not in CLASSIC_DEVICE_TYPES:
        raise ValueError(f"device_type must be one of {', '.join(CLASSIC_DEVICE_TYPES)}")
    params: dict = {"device_type": device_type}
    label = f"device_type={device_type}"
    swarm_id = (swarm_id or "").strip()
    if swarm_id:
        params, label = {"swarm_id": swarm_id}, f"swarm_id={swarm_id}"
    elif swarm_name:
        deadline = time.monotonic() + TOOL_BUDGET_SECONDS
        swarms = classic.list_swarms(group=(group or "").strip(), deadline=deadline)
        found = [s for s in swarms if _matches(s.get("swarm_name"), swarm_name)]
        if not found:
            return f"No swarm named '{swarm_name}' in Classic Central" + (f" group {group}." if group else ".")
        if len(found) > 1:
            ids = ", ".join(str(s.get("swarm_id")) for s in found[:10])
            return (
                f"Ambiguous: {len(found)} swarms are named '{swarm_name}' ({ids}). "
                "Pass swarm_id, or group to narrow the name."
            )
        params = {"swarm_id": found[0].get("swarm_id")}
        label = f"swarm={found[0].get('swarm_name')}"
    doc = classic.get(PATH_FW_VERSIONS, params)
    items = [v for v in (doc.get("data") or []) if isinstance(v, dict)]
    if not items:
        return f"No firmware versions returned ({label})."
    lines = [f"# Firmware Versions ({label}, {len(items)} total)", ""]
    for v in items:
        lines.append(
            f"- {v.get('firmware_version', '?')} {v.get('release_status', '')} created={v.get('create_date', '')}".rstrip()
        )
    return "\n".join(lines)


def _register_optional_tools(target: MCPServer | None = None) -> None:
    """Register the tools that need optional configuration (firmware_versions: ARUBA_CLASSIC_*)."""
    if classic_configured():
        (target or mcp).tool()(firmware_versions)


_register_optional_tools()


@mcp.tool()
def get_top_aps(
    usage_type: str = "total",
    site_id: str = "",
    limit: int = 10,
    start_at: str = "",
    end_at: str = "",
) -> str:
    """Get top access points ranked by bandwidth usage over a time range.

    Returns a ranked list of APs sorted by descending bandwidth consumption.

    Args:
        usage_type: "wireless" (Wi-Fi traffic), "wired" (uplink traffic),
                    or "total" (wireless + wired combined). Default: "total".
        site_id: Filter by site ID. Empty for all sites.
        limit: Maximum number of APs to return (1-25, default 10).
        start_at: Start time in RFC 3339 format (e.g. "2025-01-01T00:00:00Z").
                  Max 30 days range. Defaults to 24 hours ago if omitted.
        end_at: End time in RFC 3339 format. Defaults to current time if omitted.
    """
    path_map = {
        "wireless": "/network-monitoring/v1/top-aps-by-wireless-usage",
        "wired": "/network-monitoring/v1/top-aps-by-wired-usage",
        "total": "/network-monitoring/v1/top-aps-by-usage",
    }
    usage_type_lower = usage_type.lower()
    if usage_type_lower not in path_map:
        return f"Invalid usage_type '{usage_type}'. Use 'wireless', 'wired', or 'total'."

    client = _get_client()
    params: dict = {"limit": min(max(1, limit), 25)}
    if site_id:
        params["site-id"] = site_id
    if start_at:
        params["start-at"] = start_at
    if end_at:
        params["end-at"] = end_at

    data = client.get(path_map[usage_type_lower], params=params)
    items = data.get("items", [])

    if not items:
        return f"No top APs data available for usage_type='{usage_type}'."

    lines = [f"# Top APs by {usage_type} usage\n"]
    for i, ap in enumerate(items, 1):
        serial = ap.get("serialNumber", "unknown")
        usage = ap.get("usage", ap.get("bandwidth", ""))
        name = ap.get("deviceName", "")
        entry = f"{i}. serial={serial}"
        if name:
            entry += f" name={name}"
        if usage != "":
            entry += f" usage={usage}"
        lines.append(entry)
    return "\n".join(lines)


@mcp.tool()
def get_ap_throughput(
    serial_number: str,
    interface_type: str = "WIRELESS",
    start_at: str = "",
    end_at: str = "",
) -> str:
    """Get throughput trend for a specific AP as a time-series table.

    Returns timestamped TX/RX throughput in bps. Defaults to last 3 hours.

    Args:
        serial_number: AP serial number (use list_aps or get_ap_status to find it).
        interface_type: "WIRELESS" (Wi-Fi), "WIRED" (Ethernet uplink), or "LTE".
        start_at: Start time in RFC 3339 format. Defaults to 3 hours ago.
        end_at: End time in RFC 3339 format. Defaults to current time.
    """
    client = _get_client()
    path = f"{PATH_APS}/{_safe_serial(serial_number)}/throughput-trends"
    params: dict = {"interface-type": interface_type.upper()}
    filters = []
    if start_at:
        filters.append(f"timestamp gt '{_odata_literal(start_at)}'")
    if end_at:
        filters.append(f"timestamp lt '{_odata_literal(end_at)}'")
    if filters:
        params["filter"] = " and ".join(filters)

    data = client.get(path, params=params)
    items = data.get("items", [])

    if not items:
        return f"No throughput data for AP '{serial_number}'."

    lines = [f"# AP Throughput: {serial_number} ({interface_type})\n"]
    lines.append("| Timestamp | TX (bps) | RX (bps) |")
    lines.append("|-----------|----------|----------|")
    for point in items:
        ts = point.get("timestamp", "")
        tx = point.get("tx", point.get("txBytes", ""))
        rx = point.get("rx", point.get("rxBytes", ""))
        lines.append(f"| {ts} | {tx} | {rx} |")
    return "\n".join(lines)


@mcp.tool()
def get_clients_trend(
    site_id: str = "",
    site_name: str = "",
    start_at: str = "",
    end_at: str = "",
    group_by: str = "TYPE",
    client_type: str = "ALL",
) -> str:
    """Get client count trend over time, grouped by a chosen dimension.

    Useful for capacity planning and usage pattern analysis.

    Args:
        site_id: Filter by site ID. Empty for all.
        site_name: Filter by site name. Empty for all.
        start_at: Start time in RFC 3339 format (max 1 month range).
                  Must not be in the future.
        end_at: End time in RFC 3339 format. Must not be in the future.
        group_by: Dimension to group by. Supported values:
                  - Any client_type: TYPE, ROLE, VLAN
                  - WIRELESS only: WLAN, RADIO, SECURITY, PROTOCOL
                  Default is TYPE.
        client_type: Client category: ALL, WIRELESS, or WIRED. Default is ALL.
                     Must be WIRELESS when group_by is WLAN, RADIO, SECURITY,
                     or PROTOCOL (the API returns 400 otherwise).
    """
    group_by_upper = group_by.upper()
    client_type_upper = client_type.upper()

    wireless_only_groups = {"WLAN", "RADIO", "SECURITY", "PROTOCOL"}
    if group_by_upper in wireless_only_groups and client_type_upper != "WIRELESS":
        return (
            f"Invalid combination: group_by='{group_by}' requires "
            f"client_type='WIRELESS' (got '{client_type}'). "
            f"WLAN, RADIO, SECURITY, and PROTOCOL are wireless-only dimensions."
        )

    client = _get_client()
    params: dict = {"group-by": group_by_upper, "type": client_type_upper}
    if site_id:
        params["site-id"] = site_id
    if site_name:
        params["site-name"] = site_name
    if start_at:
        params["start-at"] = start_at
    if end_at:
        params["end-at"] = end_at

    data = client.get(PATH_CLIENTS_TREND, params=params)
    items = data.get("items", [])

    if not items:
        return (
            "No client trend data available. "
            "If this is unexpected, check: (1) start_at/end_at range (≤ 1 month, "
            "not in future), (2) site_id/site_name filter, "
            "(3) API entitlement/license for analytics."
        )

    lines = [f"# Client Trend (group_by={group_by}, type={client_type})\n"]
    for point in items:
        ts = point.get("timestamp", "")
        count = point.get("count", "")
        group = point.get("group", point.get(group_by.lower(), ""))
        entry = f"- {ts}: count={count}"
        if group:
            entry += f" group={group}"
        lines.append(entry)
    return "\n".join(lines)


@mcp.tool()
def get_top_clients_by_usage(
    site_id: str = "",
    site_name: str = "",
    start_at: str = "",
    end_at: str = "",
    limit: int = 5,
) -> str:
    """Get top clients ranked by bandwidth usage.

    Args:
        site_id: Filter by site ID. Empty for all.
        site_name: Filter by site name. Empty for all.
        start_at: Start time in RFC 3339 format (max 1 month range).
        end_at: End time in RFC 3339 format.
        limit: Maximum number of clients to return (1-100, default 5).
    """
    client = _get_client()
    params: dict = {"limit": min(max(1, limit), 100)}
    if site_id:
        params["site-id"] = site_id
    if site_name:
        params["site-name"] = site_name
    if start_at:
        params["start-at"] = start_at
    if end_at:
        params["end-at"] = end_at

    data = client.get(PATH_CLIENTS_TOPN_USAGE, params=params)
    items = data.get("items", [])

    if not items:
        return "No top clients data available."

    lines = ["# Top Clients by Usage\n"]
    for i, cl in enumerate(items, 1):
        name = cl.get("clientName") or cl.get("macAddress", "unknown")
        mac = cl.get("macAddress", "")
        usage = cl.get("usage", cl.get("bandwidth", ""))
        entry = f"{i}. **{name}** mac={mac}"
        if usage != "":
            entry += f" usage={usage}"
        lines.append(entry)
    return "\n".join(lines)


@mcp.tool()
def get_client_mobility_trail(
    mac_address: str,
    start_at: str = "",
    end_at: str = "",
) -> str:
    """Get roaming history for a wireless client as a time-series table.

    Shows which APs the client connected to, when, and on which SSID.
    Useful for troubleshooting connectivity issues or tracking movement.
    Defaults to last 3 hours.

    Args:
        mac_address: Client MAC address (e.g. "aa:bb:cc:dd:ee:ff").
        start_at: Start time in RFC 3339 format. Defaults to 3 hours ago.
        end_at: End time in RFC 3339 format. Defaults to current time.
    """
    client = _get_client()
    mac = _safe_mac(mac_address)
    path = f"{PATH_CLIENTS}/{mac}/mobility-trail"
    params: dict = {}
    if start_at:
        params["start-at"] = start_at
    if end_at:
        params["end-at"] = end_at

    # limit=100: this endpoint caps the page size where the device/client
    # listings do not, and answers 400 ("The limit value was either less than 1
    # or greater than the maximum") to fetch_all's default of 1000 — which made
    # every call to this tool fail. 100 is the highest value it accepts.
    items = client.fetch_all(path, limit=100, params=params or None)

    if not items:
        return f"No mobility trail found for client {mac_address}."

    lines = [f"# Mobility Trail: {mac_address}\n"]
    lines.append("| Time | AP | Site | SSID |")
    lines.append("|------|----|------|------|")
    for event in items:
        ts = event.get("occurredAt", event.get("timestamp", ""))
        ap = event.get("connectedTo", event.get("apName", ""))
        site = event.get("siteName", "")
        ssid = event.get("wlanName", "")
        lines.append(f"| {ts} | {ap} | {site} | {ssid} |")
    return "\n".join(lines)


@mcp.tool()
def daily_brief(offline_threshold: float = 10.0) -> str:
    """Run a morning AP health check across all sites.

    Fetches all access points and aggregates their online/offline status by
    site.  Sites whose offline AP ratio is *strictly greater than*
    ``offline_threshold`` percent are flagged as WARNING (uses ``>``, so a
    site with exactly ``offline_threshold`` % offline is still OK).

    Args:
        offline_threshold: Percentage of offline APs that triggers a WARNING
                           (default 10.0).  Sites at or below this threshold
                           appear in the OK section.  Pass 0.0 to flag any
                           site with at least one offline AP.

    Output tiers:
    - CRITICAL — API connection failure
    - WARNING  — offline AP ratio strictly above threshold
    - OK       — offline ratio at or below threshold

    Returns a Markdown summary with site-level AP counts and anomaly details.
    """
    now_str = (
        datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z").strip()
    )

    try:
        client = _get_client()
        ap_items = client.fetch_all(PATH_APS)
    except Exception as exc:
        return (
            f"## daily_brief — {now_str}\n"
            f"## CRITICAL — API error: {exc}"
        )

    sites: dict[str, dict] = {}
    for ap in ap_items:
        site = ap.get("siteName") or "(no site)"
        if site not in sites:
            sites[site] = {"aps": 0, "online": 0, "offline": 0}
        sites[site]["aps"] += 1
        if (ap.get("status") or "").upper() == "ONLINE":
            sites[site]["online"] += 1
        else:
            sites[site]["offline"] += 1

    if not sites:
        return f"## daily_brief — {now_str}\nNo AP data available."

    n_critical = 0
    warnings: list[dict] = []
    oks: list[str] = []
    for site_name in sorted(sites):
        s = sites[site_name]
        total = s["aps"]
        offline = s["offline"]
        pct = (offline / total * 100) if total > 0 else 0.0
        if pct > offline_threshold:
            warnings.append(
                {
                    "site": site_name,
                    "aps": total,
                    "online": s["online"],
                    "offline": offline,
                    "pct": pct,
                }
            )
        else:
            oks.append(site_name)

    total_sites = len(sites)
    lines: list[str] = [
        f"## daily_brief — {now_str}",
        f"## {total_sites} sites: "
        f"{len(oks)} OK, {len(warnings)} WARNING, {n_critical} CRITICAL",
        "",
    ]

    if warnings:
        lines.append("### WARNINGS")
        for row in warnings:
            lines.append(f"#### {row['site']}")
            lines.append(
                f"- [AP-OFFLINE] {row['offline']}/{row['aps']} APs offline "
                f"({row['pct']:.0f}%)"
            )
        lines.append("")

    ok_names = ", ".join(oks)
    lines.append(f"### OK sites ({len(oks)})")
    if ok_names:
        lines.append(ok_names)

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")

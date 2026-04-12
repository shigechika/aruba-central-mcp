"""MCP server exposing Aruba Central device and client status.

Provides read-only tools for querying Aruba Central via the
GreenLake New Central API (/network-monitoring/v1/).

STDIO transport is used for JSON-RPC communication.
"""

from __future__ import annotations

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from aruba_central_mcp.client import (
    ArubaAPIError,
    ArubaClient,
    PATH_APS,
    PATH_BSSIDS,
    PATH_CLIENTS,
    PATH_CLIENTS_TOPN_USAGE,
    PATH_CLIENTS_TREND,
    PATH_RADIOS,
    PATH_SWITCHES,
    PATH_SWARMS,
    PATH_WLANS,
)

mcp = FastMCP("aruba-central")

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
    global _client
    if _client is not None:
        _client.close()
    _client = None


def _build_odata_filter(**kwargs: str) -> Optional[str]:
    """Build an OData v4.0 filter string from keyword arguments.

    Only non-empty values are included. All values use the 'eq' operator.
    Returns None if no filters apply.
    """
    clauses = [
        f"{field} eq '{value}'"
        for field, value in kwargs.items()
        if value
    ]
    return " and ".join(clauses) if clauses else None


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
    """List all access points from Aruba Central.

    Returns AP name, status, model, site, IP, firmware, and MAC address.

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
    """List connected wireless clients from Aruba Central.

    Returns client name, MAC, IP, SSID, band, signal strength, AP name,
    and authentication type.

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
    """Find a client (wireless or wired) by MAC address.

    Performs a direct lookup using the MAC address.

    Args:
        mac_address: Client MAC address (e.g. "aa:bb:cc:dd:ee:ff").
    """
    client = _get_client()
    mac = mac_address.lower().replace("-", ":")
    try:
        data = client.get(f"{PATH_CLIENTS}/{mac}")
    except ArubaAPIError as e:
        if "404" in str(e):
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
    """List all AP radios from Aruba Central.

    Returns radio band, status, channel, utilization, noise floor, and TX power.

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
    """List all BSSIDs from Aruba Central.

    Returns BSSID, WLAN name, band, radio MAC, and AP information.

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
    """List all WLANs from Aruba Central.

    Returns WLAN name, band, status, security level, and VLAN.

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


@mcp.tool()
def get_top_aps(
    usage_type: str = "total",
    site_id: str = "",
    limit: int = 10,
    start_at: str = "",
    end_at: str = "",
) -> str:
    """Get top access points ranked by bandwidth usage.

    Args:
        usage_type: Type of usage to rank by: "wireless", "wired", or "total".
        site_id: Filter by site ID. Empty for all sites.
        limit: Maximum number of APs to return (1-25, default 10).
        start_at: Start time in RFC 3339 format (e.g. "2025-01-01T00:00:00Z").
                  Defaults to 24 hours ago if omitted.
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
    """Get throughput trend data for a specific access point.

    Returns TX/RX throughput over time (defaults to last 3 hours).

    Args:
        serial_number: AP serial number.
        interface_type: Interface type: "WIRELESS", "WIRED", or "LTE".
        start_at: Start time in RFC 3339 format. Defaults to 3 hours ago.
        end_at: End time in RFC 3339 format. Defaults to current time.
    """
    client = _get_client()
    path = f"{PATH_APS}/{serial_number}/throughput-trends"
    params: dict = {"interface-type": interface_type.upper()}
    filters = []
    if start_at:
        filters.append(f"timestamp gt '{start_at}'")
    if end_at:
        filters.append(f"timestamp lt '{end_at}'")
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
    """Get client count trend over time.

    Args:
        site_id: Filter by site ID. Empty for all.
        site_name: Filter by site name. Empty for all.
        start_at: Start time in RFC 3339 format (max 1 month range).
        end_at: End time in RFC 3339 format.
        group_by: Group results by: TYPE, ROLE, VLAN, WLAN, RADIO, SECURITY,
                  or PROTOCOL. Default is TYPE.
        client_type: Client category: ALL, WIRELESS, or WIRED. Default is ALL.
    """
    client = _get_client()
    params: dict = {"group-by": group_by.upper(), "type": client_type.upper()}
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
        return "No client trend data available."

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
    """Get mobility trail (roaming history) for a wireless client.

    Shows the sequence of APs a client has connected to over time.

    Args:
        mac_address: Client MAC address (e.g. "aa:bb:cc:dd:ee:ff").
        start_at: Start time in RFC 3339 format. Defaults to 3 hours ago.
        end_at: End time in RFC 3339 format. Defaults to current time.
    """
    client = _get_client()
    mac = mac_address.lower().replace("-", ":")
    path = f"{PATH_CLIENTS}/{mac}/mobility-trail"
    params: dict = {}
    if start_at:
        params["start-at"] = start_at
    if end_at:
        params["end-at"] = end_at

    items = client.fetch_all(path, params=params or None)

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


if __name__ == "__main__":
    mcp.run(transport="stdio")

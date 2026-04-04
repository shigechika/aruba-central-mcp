"""MCP server exposing Aruba Central device and client status.

Provides read-only tools for querying Aruba Central via the
GreenLake New Central API (/network-monitoring/v1/).

STDIO transport is used for JSON-RPC communication.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from aruba_central_mcp.client import (
    ArubaClient,
    PATH_APS,
    PATH_CLIENTS,
    PATH_SWITCHES,
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
    name = cl.get("name", cl.get("macAddress", "unknown"))
    mac = cl.get("macAddress", "")
    ip = cl.get("ip", "")
    ssid = cl.get("network", "")
    band = cl.get("band", "")
    signal = cl.get("signal_db", "")
    ap_name = cl.get("associatedDeviceName", "")
    auth = cl.get("authentication_type", "")
    return (
        f"- **{name}** mac={mac} ip={ip} ssid={ssid} "
        f"band={band}GHz signal={signal}dBm ap={ap_name} auth={auth}"
    )


@mcp.tool()
def list_aps(site: str = "", status: str = "") -> str:
    """List all access points from Aruba Central.

    Returns AP name, status, model, site, IP, firmware, and MAC address.

    Args:
        site: Filter by site name (case-insensitive substring match). Empty for all.
        status: Filter by status (e.g. "ONLINE", "OFFLINE"). Empty for all.
    """
    client = _get_client()
    items = client.fetch_all(PATH_APS)

    if site:
        site_lower = site.lower()
        items = [ap for ap in items if site_lower in (ap.get("siteName") or "").lower()]
    if status:
        status_upper = status.upper()
        items = [ap for ap in items if (ap.get("status") or "").upper() == status_upper]

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
        ssid: Filter by SSID name (case-insensitive substring match). Empty for all.
        band: Filter by band ("2.4" or "5.0"). Empty for all.
    """
    client = _get_client()
    items = client.fetch_all(PATH_CLIENTS)

    if ssid:
        ssid_lower = ssid.lower()
        items = [cl for cl in items if ssid_lower in (cl.get("network") or "").lower()]
    if band:
        items = [cl for cl in items if cl.get("band") == band]

    if not items:
        return "No clients found."

    header = f"# Wireless Clients ({len(items)} total)\n\n"
    return header + "\n".join(_format_client(cl) for cl in items)


@mcp.tool()
def find_client_by_mac(mac_address: str) -> str:
    """Find a wireless client by MAC address.

    Searches connected clients for a matching MAC address
    (case-insensitive, colon-separated format).

    Args:
        mac_address: Client MAC address (e.g. "aa:bb:cc:dd:ee:ff").
    """
    client = _get_client()
    items = client.fetch_all(PATH_CLIENTS)

    mac_lower = mac_address.lower().replace("-", ":")
    matches = [
        cl for cl in items
        if (cl.get("macAddress") or "").lower() == mac_lower
    ]

    if not matches:
        return f"No client found with MAC address {mac_address}."

    return "\n".join(_format_client(cl) for cl in matches)


@mcp.tool()
def get_ap_status(ap_name: str) -> str:
    """Get detailed status of a specific access point by name.

    Args:
        ap_name: AP device name (case-insensitive exact match).
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

    # Aggregate clients by associated AP's site
    ap_site_map = {
        (ap.get("deviceName") or "").lower(): ap.get("siteName") or "(no site)"
        for ap in ap_items
    }
    for cl in client_items:
        ap_name = (cl.get("associatedDeviceName") or "").lower()
        site = ap_site_map.get(ap_name, "(unknown site)")
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


if __name__ == "__main__":
    mcp.run(transport="stdio")

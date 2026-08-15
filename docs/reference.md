# Reference

## `health_check()`

Five keys are present on every call:

| Key | Meaning |
|---|---|
| `status` | `healthy` / `degraded` / `error` |
| `service` | Always `aruba-central-mcp` |
| `version` | Package version |
| `base_url` | Configured `ARUBA_CENTRAL_BASE_URL` (empty string when unset) |
| `auth` | `unknown` / `ok` / `error` / `missing-env` |

`detail` is added only on `degraded` or `error`, with the reason: a missing
environment variable, or the Aruba Central error for a genuine authentication
failure.

Lightweight by design: it builds the client and obtains an OAuth2 access
token (GreenLake SSO, reusing the cached token when still valid) — it does
NOT fetch APs, switches, clients, or any other data endpoint. Safe to call at
session start or after a tool-call timeout.

## Tool index

### Access points

| Tool | Purpose |
|---|---|
| `list_aps(site="", status="")` | List access points, with optional site/status filter (server-side) |
| `get_ap_status(ap_name)` | Detailed status of one AP by name (case-insensitive) |
| `list_radios(site="", band="")` | AP radios: channel, utilization, noise floor, TX power |
| `list_bssids(site="")` | BSSIDs — which radio on which AP broadcasts which SSID |
| `list_wlans(site_id="", serial_number="")` | Configured WLANs: SSID, band, security, VLAN |
| `list_swarms(site="")` | AP swarms/clusters: conductor AP, site, IP, firmware |
| `get_ap_throughput(serial_number, interface_type="WIRELESS", start_at="", end_at="")` | TX/RX throughput time series for one AP (default: last 3 hours) |
| `get_top_aps(usage_type="total", site_id="", limit=10, start_at="", end_at="")` | Top APs by bandwidth (`wireless` / `wired` / `total`), default last 24h |

### Clients

| Tool | Purpose |
|---|---|
| `list_clients(ssid="", band="")` | Connected wireless clients, with optional SSID/band filter |
| `find_client_by_mac(mac_address)` | Direct API lookup of one client by MAC (wireless or wired) |
| `get_clients_trend(site_id="", site_name="", start_at="", end_at="", group_by="TYPE", client_type="ALL")` | Client count trend, grouped by `TYPE`/`ROLE`/`VLAN` (any) or `WLAN`/`RADIO`/`SECURITY`/`PROTOCOL` (wireless only) |
| `get_top_clients_by_usage(site_id="", site_name="", start_at="", end_at="", limit=5)` | Top clients ranked by bandwidth usage |
| `get_client_mobility_trail(mac_address, start_at="", end_at="")` | Roaming history for one client: which AP, when, which SSID (default: last 3 hours) |

### Infrastructure

| Tool | Purpose |
|---|---|
| `list_switches()` | All switches: name, status, model, type, IP, firmware, MAC |
| `get_site_summary()` | Per-site AP counts (online/offline) and client counts |

### Morning patrol

| Tool | Purpose |
|---|---|
| `health_check()` | Server version + backend auth probe, no data fetch |
| `daily_brief(offline_threshold=10.0)` | Morning AP health check: sites whose offline-AP ratio exceeds `offline_threshold`% are flagged WARNING; an API failure renders CRITICAL |

## `daily_brief`

One Markdown report bucketing every access point by `siteName` and comparing
each site's offline ratio against `offline_threshold` (default 10.0%,
strictly greater-than, so a site sitting exactly at the threshold stays OK).
A backend connection failure renders the whole report as `## CRITICAL — API
error: <exception>` instead of a partial brief with sites silently missing.
Pass `offline_threshold=0.0` to flag any site with at least one offline AP.

## Server-side filtering

`list_aps`, `list_clients`, `list_radios`, `list_bssids`, and `list_swarms`
build an [OData v4](https://www.odata.org/) filter from their `site` /
`ssid` / `band` arguments and send it to Aruba Central, rather than fetching
everything and filtering locally — the query stays cheap regardless of
tenant size. Listings that can return many pages (`fetch_all` in the
client) paginate automatically.

## CLI

```bash
aruba-central-mcp            # start the MCP server (stdio; default, no arguments)
aruba-central-mcp --version  # print version and exit
aruba-central-mcp --help     # show usage and required environment variables
aruba-central-mcp --check    # verify environment and authentication, then exit
```

Exit codes for `--check`: `0` success, `1` a required environment variable is
missing, `2` authentication failed.

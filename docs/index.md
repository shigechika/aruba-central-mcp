# aruba-central-mcp

MCP server for [Aruba Central](https://www.arubanetworks.com/products/network-management-operations/central/) (GreenLake New Central API).

Exposes access point, switch, and wireless client status to MCP-compatible AI
assistants (Claude Code, Claude Desktop, etc.) via STDIO transport — built for
a morning `daily_brief` AP health check and for the moment someone asks "is
this AP online" or "where did this client roam."

## Tools by area

| Area | Tools |
|---|---|
| Access points | `list_aps`, `get_ap_status`, `list_radios`, `list_bssids`, `list_wlans`, `list_swarms`, `get_ap_throughput`, `get_top_aps` |
| Clients | `list_clients`, `find_client_by_mac`, `get_clients_trend`, `get_top_clients_by_usage`, `get_client_mobility_trail` |
| Infrastructure | `list_switches`, `get_site_summary` |
| Morning patrol | `health_check`, `daily_brief` |

**Every tool reads.** Nothing in Aruba Central is configured through this
server — there is no write path, so it can be handed to Claude without
granting any ability to change device or client state. See
[Reference](reference.md) for the full tool index.

## Design notes

**OAuth2 Client Credentials, and nothing more privileged.** The server
authenticates against GreenLake SSO with a Personal API client (client ID and
secret), not an interactive user session, and caches the resulting token
until it is close to expiry. There is no username/password login flow and no
tool that could touch account or admin state — only the
`/network-monitoring/v1/` read endpoints.

**Server-side filtering, not client-side scanning.** Tools that take a
`site`, `ssid`, or `band` argument build an OData v4 filter and send it to
Central, so a scoped query stays cheap on a tenant with thousands of
APs and clients instead of pulling everything and filtering in Python.
Listings that can run long are paginated automatically.

**A resolved MAC or serial number is validated before it reaches a URL.**
`find_client_by_mac`, `get_ap_throughput`, and `get_client_mobility_trail`
take a MAC address or serial number that goes straight into a request path;
each is checked against a strict pattern first; a malformed value raises a
clear error rather than composing an unexpected URL.

## Next steps

- [Setup](setup.md) — install, GreenLake API credentials, environment variables, MCP client registration
- [Reference](reference.md) — every tool, the `health_check` contract, CLI, exit codes

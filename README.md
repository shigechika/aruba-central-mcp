<!-- mcp-name: io.github.shigechika/aruba-central-mcp -->

# aruba-central-mcp

English | [日本語](README.ja.md)

MCP server for [Aruba Central](https://www.arubanetworks.com/products/network-management-operations/central/) (GreenLake New Central API).

Exposes access point, switch, and wireless client status to MCP-compatible AI assistants (Claude Code, Claude Desktop, etc.) via STDIO transport.

Documentation: <https://shigechika.github.io/aruba-central-mcp/>

## Features

### Access Points

| Tool | Description |
|------|-------------|
| `list_aps` | List all access points (with optional site/status filter) |
| `list_radios` | List AP radios (channel, utilization, noise floor, TX power) |
| `list_bssids` | List all BSSIDs |
| `list_wlans` | List WLANs (SSID, security, VLAN) |
| `list_swarms` | List AP swarms/clusters |
| `get_ap_status` | Get detailed status of a specific AP |
| `get_ap_throughput` | Get AP throughput trend (TX/RX over time) |
| `get_top_aps` | Top APs by bandwidth usage (wireless/wired/total) |

### Clients

| Tool | Description |
|------|-------------|
| `list_clients` | List connected wireless clients (with optional SSID/band filter) |
| `find_client_by_mac` | Find a client by MAC address (direct API lookup) |
| `get_clients_trend` | Client count trend over time |
| `get_top_clients_by_usage` | Top clients by bandwidth usage |
| `get_client_mobility_trail` | Client roaming history |

### Infrastructure

| Tool | Description |
|------|-------------|
| `list_switches` | List all switches |
| `get_site_summary` | Aggregated site-level summary (AP counts, client counts) |
| `health_check` | Report server version and verify Aruba Central authentication (no data fetch) |

### Highlights

- **Server-side OData filtering** for efficient queries
- **OAuth2 Client Credentials** authentication (GreenLake SSO)
- **Automatic pagination** for large result sets
- **Token auto-refresh** before expiration
- Lightweight: only `mcp` SDK + `httpx` (no pandas)

## Prerequisites

- Python 3.10+
- Aruba Central account with API access (GreenLake New Central API)
- OAuth2 client credentials (client ID and secret)

## Setup

```bash
# uv
uv pip install aruba-central-mcp

# pip
pip install aruba-central-mcp
```

Or run without installing:

```bash
uvx aruba-central-mcp
```

From source:

```bash
git clone https://github.com/shigechika/aruba-central-mcp.git
cd aruba-central-mcp

# uv
uv sync

# pip
pip install -e .
```

## Configuration

Set the following environment variables:

| Variable | Description | Example |
|---|---|---|
| `ARUBA_CENTRAL_BASE_URL` | API gateway URL | `apigw-uswest4.central.arubanetworks.com` |
| `ARUBA_CENTRAL_CLIENT_ID` | OAuth2 client ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `ARUBA_CENTRAL_CLIENT_SECRET` | OAuth2 client secret | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |

### How to obtain API credentials

1. Log in to [HPE GreenLake Platform](https://common.cloud.hpe.com/)
2. Go to **Manage Workspace** > **Personal API clients**
3. Click **Create Personal API client**
4. Enter a nickname and select **Aruba Central** as the service
5. Copy the `client_id` and `client_secret` — **the secret is shown only once**

For details, see:
- [OAuth APIs for Access Token](https://developer.arubanetworks.com/hpe-aruba-networking-central/docs/api-oauth-access-token)
- [Making API Calls](https://developer.arubanetworks.com/new-central/docs/making-api-calls)

## Usage

### Claude Code (plugin)

This repository doubles as a single-plugin marketplace, so Claude Code can install
the server for you:

```
/plugin marketplace add shigechika/aruba-central-mcp
/plugin install aruba-central-mcp@aruba-central-mcp
```

The plugin launches `uvx aruba-central-mcp` and reads the same three environment
variables described in [Configuration](#configuration); export them before
starting Claude Code.

`uvx` must be on the `PATH` of the process that runs Claude Code — a login
shell usually has it, but a GUI-launched app may not; install
[uv](https://docs.astral.sh/uv/) system-wide if the plugin fails to start.

### Claude Code (manual)

```bash
claude mcp add aruba-central \
  -e ARUBA_CENTRAL_BASE_URL=apigw-uswest4.central.arubanetworks.com \
  -e ARUBA_CENTRAL_CLIENT_ID=your-client-id \
  -e ARUBA_CENTRAL_CLIENT_SECRET=your-client-secret \
  -- uvx aruba-central-mcp
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "aruba-central": {
      "command": "uvx",
      "args": ["aruba-central-mcp"],
      "env": {
        "ARUBA_CENTRAL_BASE_URL": "apigw-uswest4.central.arubanetworks.com",
        "ARUBA_CENTRAL_CLIENT_ID": "your-client-id",
        "ARUBA_CENTRAL_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aruba-central": {
      "command": "uvx",
      "args": ["aruba-central-mcp"],
      "env": {
        "ARUBA_CENTRAL_BASE_URL": "apigw-uswest4.central.arubanetworks.com",
        "ARUBA_CENTRAL_CLIENT_ID": "your-client-id",
        "ARUBA_CENTRAL_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### Direct execution

```bash
export ARUBA_CENTRAL_BASE_URL="apigw-uswest4.central.arubanetworks.com"
export ARUBA_CENTRAL_CLIENT_ID="your-client-id"
export ARUBA_CENTRAL_CLIENT_SECRET="your-client-secret"
python3 -m aruba_central_mcp
```

### CLI Options

```bash
aruba-central-mcp --version   # Print version and exit
aruba-central-mcp --help      # Show usage and required environment variables
aruba-central-mcp --check     # Verify environment variables and OAuth2 authentication, then exit
aruba-central-mcp             # Start MCP server (STDIO, default)
```

With no options, the process runs as an MCP STDIO server (the mode used by MCP clients).

`--check` exit codes: `0` success, `1` config error, `2` auth error.

## Development

```bash
git clone https://github.com/shigechika/aruba-central-mcp.git
cd aruba-central-mcp

# uv
uv sync --dev
uv run pytest -v

# pip
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest -v
```

### Live smoke test

The unit suite mocks Central at the transport layer, which is what makes it
fast — and also what makes it blind to a tool that has stopped returning real
data. `scripts/smoke_test.py` runs **every registered tool** against the
configured tenant and fails on empty, malformed or error answers:

```bash
# needs the same ARUBA_CENTRAL_* environment variables as the server
uv run python scripts/smoke_test.py
uv run python scripts/smoke_test.py --only radios --traceback
```

- **Read-only.** Every tool here reads; nothing in Central is configured. A
  future tool that writes must be listed as state-changing and skipped, and a
  test enforces that.
- **No payloads in the report.** Tool names, statuses and row counts only;
  error text is redacted too, since an error routinely quotes the device,
  client MAC or site it was asked about.
- **Nothing network-specific in the specs.** The AP, the serial number and the
  client MAC that the per-device tools need are discovered at run time from the
  listings, and skipped when the network has none to offer. Two tests keep it
  that way: one refuses those parameters as literals, the other bans anything
  address-shaped anywhere in the file, because this repository is public.
- Empty answers pass for the listings and the time-series tools — a site with
  no swarms configured is a real deployment — but a *lookup* handed a name
  discovered seconds earlier must not come back empty, and those probes say so.
- CI enforces the cheap half: a tool registered without a probe spec fails the
  build (`tests/test_smoke_probes.py`), so adding a tool forces the question
  "how would we know it works?".
- `scripts/smoke_harness.py` is the engine and holds no Central knowledge: it
  is kept identical across the servers that share it, so fix engine bugs once
  and sync the file rather than patching this copy.

Its first run found a real one: `get_client_mobility_trail` was requesting a
page size the endpoint rejects, so the tool had been failing for every client.

## API Reference

This server uses the [GreenLake New Central API](https://developer.arubanetworks.com/):

- `/network-monitoring/v1/aps` — Access points
- `/network-monitoring/v1/radios` — AP radios
- `/network-monitoring/v1/bssids` — BSSIDs
- `/network-monitoring/v1/wlans` — WLANs
- `/network-monitoring/v1/swarms` — AP swarms/clusters
- `/network-monitoring/v1/switches` — Switches
- `/network-monitoring/v1/clients` — Clients
- `/network-monitoring/v1/clients-trend` — Client count trends
- `/network-monitoring/v1/clients-topn-usage` — Top clients by usage
- `/network-monitoring/v1/top-aps-by-usage` — Top APs by usage

## License

[MIT](LICENSE)

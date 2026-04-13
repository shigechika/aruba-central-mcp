<!-- mcp-name: io.github.shigechika/aruba-central-mcp -->

# aruba-central-mcp

English | [日本語](README.ja.md)

MCP server for [Aruba Central](https://www.arubanetworks.com/products/network-management-operations/central/) (GreenLake New Central API).

Exposes access point, switch, and wireless client status to MCP-compatible AI assistants (Claude Code, Claude Desktop, etc.) via STDIO transport.

## Features

- **15 tools** for querying Aruba Central infrastructure:

  **Access Points**
  - `list_aps` — List all access points (with optional site/status filter)
  - `list_radios` — List AP radios (channel, utilization, noise floor, TX power)
  - `list_bssids` — List all BSSIDs
  - `list_wlans` — List WLANs (SSID, security, VLAN)
  - `list_swarms` — List AP swarms/clusters
  - `get_ap_status` — Get detailed status of a specific AP
  - `get_ap_throughput` — Get AP throughput trend (TX/RX over time)
  - `get_top_aps` — Top APs by bandwidth usage (wireless/wired/total)

  **Clients**
  - `list_clients` — List connected wireless clients (with optional SSID/band filter)
  - `find_client_by_mac` — Find a client by MAC address (direct API lookup)
  - `get_clients_trend` — Client count trend over time
  - `get_top_clients_by_usage` — Top clients by bandwidth usage
  - `get_client_mobility_trail` — Client roaming history

  **Infrastructure**
  - `list_switches` — List all switches
  - `get_site_summary` — Aggregated site-level summary (AP counts, client counts)

- **Server-side OData filtering** for efficient queries
- **OAuth2 Client Credentials** authentication (GreenLake SSO)
- **Automatic pagination** for large result sets
- **Token auto-refresh** before expiration
- Lightweight: only `mcp` SDK + `httpx` (no pandas)

## Prerequisites

- Python 3.10+
- Aruba Central account with API access (GreenLake New Central API)
- OAuth2 client credentials (client ID and secret)

## Installation

```bash
pip install aruba-central-mcp
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uvx aruba-central-mcp
```

For development:

```bash
git clone https://github.com/shigechika/aruba-central-mcp.git
cd aruba-central-mcp
pip install -e ".[test]"
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

### Claude Code

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

### CLI options

```bash
aruba-central-mcp --version   # Print version and exit
aruba-central-mcp --help      # Show usage and required environment variables
aruba-central-mcp --check     # Verify env vars + OAuth2 authentication, then exit
aruba-central-mcp             # Start the MCP server on STDIO (default)
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest -v
```

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

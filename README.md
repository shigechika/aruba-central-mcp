# aruba-central-mcp

English | [日本語](README.ja.md)

MCP server for [Aruba Central](https://www.arubanetworks.com/products/network-management-operations/central/) (GreenLake New Central API).

Exposes access point, switch, and wireless client status to MCP-compatible AI assistants (Claude Code, Claude Desktop, etc.) via STDIO transport.

## Features

- **6 tools** for querying Aruba Central infrastructure:
  - `list_aps` — List all access points (with optional site/status filter)
  - `list_switches` — List all switches
  - `list_clients` — List connected wireless clients (with optional SSID/band filter)
  - `find_client_by_mac` — Find a wireless client by MAC address
  - `get_ap_status` — Get detailed status of a specific AP
  - `get_site_summary` — Aggregated site-level summary (AP counts, client counts)
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

### Claude Code

Add to your MCP settings (`.claude/settings.json` or project-level):

```json
{
  "mcpServers": {
    "aruba-central": {
      "command": "python3",
      "args": ["-m", "aruba_central_mcp"],
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
      "command": "python3",
      "args": ["-m", "aruba_central_mcp"],
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

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest -v
```

## API Reference

This server uses the [GreenLake New Central API](https://developer.arubanetworks.com/):

- `/network-monitoring/v1/aps` — Access points
- `/network-monitoring/v1/switches` — Switches
- `/network-monitoring/v1/clients` — Wireless clients

## License

[MIT](LICENSE)

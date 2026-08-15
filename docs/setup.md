# Setup

## Prerequisites

- Python 3.10+
- Aruba Central account with API access (GreenLake New Central API)
- OAuth2 client credentials (client ID and secret)

## Install

```bash
uv pip install aruba-central-mcp
# or
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
uv sync          # or: pip install -e .
```

## How to obtain API credentials

1. Log in to [HPE GreenLake Platform](https://common.cloud.hpe.com/).
2. Go to **Manage Workspace** > **Personal API clients**.
3. Click **Create Personal API client**.
4. Enter a nickname and select **Aruba Central** as the service.
5. Copy the `client_id` and `client_secret` — **the secret is shown only
   once**.

For details, see:

- [OAuth APIs for Access Token](https://developer.arubanetworks.com/hpe-aruba-networking-central/docs/api-oauth-access-token)
- [Making API Calls](https://developer.arubanetworks.com/new-central/docs/making-api-calls)

## Environment variables

| Variable | Description | Example |
|---|---|---|
| `ARUBA_CENTRAL_BASE_URL` | API gateway URL | `apigw-uswest4.central.arubanetworks.com` |
| `ARUBA_CENTRAL_CLIENT_ID` | OAuth2 client ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `ARUBA_CENTRAL_CLIENT_SECRET` | OAuth2 client secret | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |

All three are required — the server raises an error at first use if any is
unset. There is no config file and no file-path variable; every setting
comes from the environment, so it drops into a plugin's own `.mcp.json`
`env` block without any extra wiring.

## Verify before wiring it into anything

```bash
export ARUBA_CENTRAL_BASE_URL="apigw-uswest4.central.arubanetworks.com"
export ARUBA_CENTRAL_CLIENT_ID="your-client-id"
export ARUBA_CENTRAL_CLIENT_SECRET="your-client-secret"
aruba-central-mcp --check
```

Exit `0` means authentication succeeded; `1` is a missing environment
variable, `2` an authentication error. Running this once turns "the tool
returns nothing" into a question you have already answered.

## Register with an MCP client

### Claude Code (plugin)

This repository doubles as a single-plugin marketplace:

```
/plugin marketplace add shigechika/aruba-central-mcp
/plugin install aruba-central-mcp@aruba-central-mcp
```

Export the three environment variables above before starting Claude Code —
the plugin launches `uvx aruba-central-mcp` and reads the same variables as
every other transport.

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

`claude_desktop_config.json` takes the same `env` block under `command`:

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

No-argument mode is the normal one — that is how MCP clients launch it.

## Next

[Reference](reference.md) lists every tool, the `health_check` contract, the
CLI, and exit codes.

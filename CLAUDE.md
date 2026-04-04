# CLAUDE.md

## Overview

MCP server for Aruba Central (GreenLake New Central API).
Exposes AP, switch, and wireless client status to AI assistants via STDIO transport.

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest -v               # run all tests
.venv/bin/pytest -v tests/test_client.py  # client tests only
.venv/bin/pytest -v tests/test_server.py  # server tests only
python3 -m py_compile aruba_central_mcp/client.py  # syntax check
```

## Architecture

- `aruba_central_mcp/client.py` — `ArubaClient`: OAuth2 Client Credentials + httpx + automatic pagination
- `aruba_central_mcp/server.py` — FastMCP server with 6 tools (list_aps, list_switches, list_clients, find_client_by_mac, get_ap_status, get_site_summary)
- Environment variables for configuration: `ARUBA_CENTRAL_BASE_URL`, `ARUBA_CENTRAL_CLIENT_ID`, `ARUBA_CENTRAL_CLIENT_SECRET`

## Conventions

- Public repository: comments, commit messages, and documentation in English
- Docstrings in English
- Python 3.10+ compatible (no `X | Y` union syntax in runtime code; use `from __future__ import annotations`)
- Tests use `respx` for HTTP mocking and `unittest.mock` for server-level mocking

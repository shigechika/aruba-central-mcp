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
- `aruba_central_mcp/server.py` — FastMCP server with 17 tools: AP tools (list_aps, list_radios, list_bssids, list_wlans, list_swarms, get_ap_status, get_ap_throughput, get_top_aps), Client tools (list_clients, find_client_by_mac, get_clients_trend, get_top_clients_by_usage, get_client_mobility_trail), Infrastructure (list_switches, get_site_summary), plus health_check (server version + backend auth probe) and daily_brief (site-level AP online/offline health summary; buckets APs by siteName, threshold-gated)
- `aruba_central_mcp/__main__.py` — console-script entry point (`aruba-central-mcp`, per `pyproject.toml`); `--check` verifies env vars + OAuth2 auth and exits; its `KeyboardInterrupt` handler calls `os._exit(0)` deliberately to bypass normal interpreter shutdown, because FastMCP's stdio reader daemon thread can crash with `_enter_buffered_busy` on Python 3.14
- Environment variables for configuration: `ARUBA_CENTRAL_BASE_URL`, `ARUBA_CENTRAL_CLIENT_ID`, `ARUBA_CENTRAL_CLIENT_SECRET`

## Conventions

- Public repository: comments, commit messages, and documentation in English
- Docstrings in English
- Python 3.10+ compatible (no `X | Y` union syntax in runtime code; use `from __future__ import annotations`)
- Tests use `respx` for HTTP mocking and `unittest.mock` for server-level mocking
- `scripts/` holds the live smoke test: `smoke_test.py` (CLI), its per-tool
  specs in `smoke_probes.py`, and `smoke_harness.py` — the server-agnostic
  engine, kept identical across the servers that share it, so fix engine bugs
  once and sync the file rather than patching this copy. It runs every
  registered tool against a real tenant (see README);
  `tests/test_smoke_probes.py` is the offline half and needs only the tool
  registry. Adding a tool without a probe spec fails CI: decide when you add
  the tool how anyone would know it works. Probes stay read-only and name no
  network-specific value — the AP name, serial and client MAC come from an
  `args_factory` that reads the listings at run time.

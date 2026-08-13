# Repository overview

`aruba-central-mcp` is an MCP (Model Context Protocol) server exposing Aruba
Central (GreenLake New Central API) data — APs, switches, wireless clients —
to AI assistants over **stdio transport**. Built on the official `mcp` Python
SDK's `FastMCP` (`aruba_central_mcp/server.py`), with `ArubaClient`
(`aruba_central_mcp/client.py`) handling OAuth2 Client Credentials auth,
`httpx`, and automatic pagination.

See `CLAUDE.md` for the authoritative command list and architecture notes —
read it before reviewing changes to `client.py`, `server.py`, or
`__main__.py`.

# Build & validate

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest -v                        # all tests
.venv/bin/pytest -v tests/test_client.py   # client tests only
.venv/bin/pytest -v tests/test_server.py   # server tests only
python3 -m py_compile aruba_central_mcp/client.py   # syntax check
```

This mirrors `.github/workflows/test.yml` (`pip install -e ".[test]"` +
`pytest tests/ -v`, matrix over Python 3.10–3.14, plus one Windows job
specifically to catch stdio newline regressions —
see `modelcontextprotocol/python-sdk#2433`), plus a `lint` job running
`ruff check .` at the pinned version. Lint findings are therefore already
enforced and not worth restating; formatting is not gated, so `ruff format`
nits are still noise.

# What to focus review on in this repo

## 1. This is a stdio MCP server — stdout is a JSON-RPC channel, not a log

Any `print()` or library logging that writes to stdout (instead of stderr)
corrupts the protocol stream for the connected client. Flag any new code
path that writes to stdout directly, uses a logger without an explicit
stderr handler, or lets a dependency's default logging config leak through.
This exact bug class is why CI runs a dedicated Windows job (stdio newline
handling is platform-sensitive) — treat it as a real, previously-hit failure
mode, not a theoretical one.

## 2. FastMCP already wraps tool returns — don't ask for manual envelope code

`server.py`'s `@mcp.tool()`-decorated functions can return plain Python
values/dicts; FastMCP handles the MCP content-envelope wrapping and derives
`isError` from raised exceptions. Do **not** suggest that a tool handler
manually construct `{"content": [...], "isError": ...}` — that's a
hand-rolled-stdio-server pattern (relevant in other repos in this family,
not this one) and would be redundant/wrong here. The existing convention,
per `server.py`, is: let unexpected exceptions propagate (`raise`) so
FastMCP turns them into an MCP error; only convert to a plain string/dict
return for a specific, anticipated condition the caller should see as a
normal result rather than a tool failure (e.g. `find_client_by_mac` catching
a 404 `ArubaAPIError` and returning "No client found..." instead of
raising). A new tool that catches a broad `except Exception` and returns
`None`/an empty result *without* re-raising or producing a visible error
message is swallowing a real failure — flag it. (`daily_brief`'s broad
except-and-report-in-the-output pattern is a deliberate exception for a
summary tool that should still return partial output on API failure, not a
precedent to copy elsewhere.)

## 3. OAuth2 credentials and API responses are the sensitive surface

- `ARUBA_CENTRAL_CLIENT_ID` / `ARUBA_CENTRAL_CLIENT_SECRET` /
  `ARUBA_CENTRAL_BASE_URL` are read from the environment. Flag any diff that
  logs a request/response containing the `Authorization` header, the client
  secret, or a raw access token — including at `DEBUG` log level.
  `ArubaClient`'s token refresh path is the highest-risk spot for this.
- Tool inputs (MAC addresses, site/AP names, filters) come from an LLM
  acting on a user's behalf — treat them as adversarial. Check that values
  interpolated into API query parameters go through `httpx`'s params
  handling (not manual string formatting into a URL). Note the current code
  only does this for the `params` dict: `_build_odata_filter` builds
  `f"{field} eq '{value}'"` with the single quotes unescaped (`server.py`),
  and `find_client_by_mac`, `get_ap_throughput`, and
  `get_client_mobility_trail` interpolate the MAC/serial straight into the
  URL path (`f"{PATH_CLIENTS}/{mac}"`), with `get_ap_throughput` also
  inlining `start_at`/`end_at` into the filter string. Treat that as the
  existing (unescaped) surface, not adherence — an unescaped quote in a
  `site`/`ssid` value alters the OData filter, path segments are
  unvalidated, and a new tool copying `_build_odata_filter` inherits this.
- A new `@mcp.tool()`'s name and docstring are what the calling model uses
  to decide whether/how to invoke it — flag a vague name (`get_data`) or a
  docstring that omits parameter formats an LLM would otherwise have to
  guess (e.g. the MAC address format `client.py` expects).

## 4. Python 3.10 compatibility is a project convention, follow it as written

Per `CLAUDE.md`: no `X | Y` union syntax in runtime code; every runtime
module (`server.py`, `client.py`, `__main__.py`) uses
`from __future__ import annotations` instead. (PEP 604 union syntax itself
runs fine on 3.10+ without the import — this rule is this codebase's own
consistency convention, not a runtime-error workaround, so don't invent a
`TypeError` justification when reviewing against it.) Flag a diff that adds
a bare `X | Y` annotation inconsistent with the rest of the file.

## 5. Test conventions

- HTTP-level tests mock via `respx` (not `unittest.mock` for the HTTP
  layer); server-level/tool-dispatch tests use `unittest.mock`. A new
  `client.py` test that hand-mocks `httpx` calls instead of using `respx`
  is inconsistent with the existing suite — flag it.
- New tools need a test exercising both a successful API response and at
  least one error/edge case (empty result set, pagination boundary, 4xx
  from the API). `client.fetch_all` (cursor-based: follows the `next` field,
  stops when `next` is absent, the page is empty, or `total` is reached) has
  a real history of pagination bugs in this codebase — the offset-based
  approach it replaced was buggy enough to need multiple fixes. Any new or
  modified call to `fetch_all` needs a test covering a multi-page response
  (not just a single page), verified against the actual stop conditions in
  the current implementation, not assumed ones.

- `tests/test_smoke_probes.py` guards `scripts/smoke_test.py`, which
  exercises every registered tool against a real tenant. It asserts what
  can be checked without one: every registered tool has a probe spec, no
  spec targets a removed tool, state-changing tools stay skipped, and no
  network-specific literal (AP name, serial, MAC, site, SSID) is written
  into the specs — this repository is public. A new tool therefore needs
  an entry in `scripts/smoke_probes.py` or CI fails; that is deliberate,
  not an obstacle to route around. Its first run found a real defect the
  mocked suite could not see (a page size the endpoint rejects), which is
  the kind of gap it exists to close.

## 6. `__main__.py` shuts down via `os._exit(0)` on purpose

The console-script entry point (`aruba-central-mcp`; also `--check`, which
verifies env vars + OAuth2 auth and exits) catches `KeyboardInterrupt` and
calls `os._exit(0)` instead of a graceful shutdown: FastMCP's stdio reader
runs in a daemon thread blocked on `sys.stdin`, and joining it at interpreter
shutdown can crash with `_enter_buffered_busy` on Python 3.14 (which the CI
matrix covers). Flag a cleanup diff that "fixes" this into `sys.exit(0)` or a
graceful join — it reintroduces a real, CI-caught crash.

# Out of scope for review comments

- Formatting nits: CI does gate `ruff check .` (see "Build & validate"
  above), but `ruff format` deliberately is not gated — see `ruff.toml`.
  There is no `black` or `mypy` step either. So don't hold this repo to a
  formatting or typing standard it hasn't opted into, and don't restate
  lint findings `ruff check` already enforces.
- `release-please.yml`'s use of `secrets.RELEASE_PLEASE_TOKEN` instead of
  `GITHUB_TOKEN` is intentional (`GITHUB_TOKEN`-authored tags/releases don't
  trigger downstream workflows) — don't suggest reverting it.

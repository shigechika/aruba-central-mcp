# Review rules for this repository

Severity rules for the AI reviewer. The reasoning behind them lives in
`.github/copilot-instructions.md` and `CLAUDE.md`, which the reviewer
also receives — this file only decides what is blocking and what is
noise.

## Always blocking

- Anything reaching **stdout** other than the JSON-RPC stream: a
  `print()`, a logger without an explicit stderr handler, or a
  dependency whose default logging configuration writes there. This is
  a stdio MCP server, so stdout is the protocol channel; corrupting it
  breaks every connected client.
- A credential or token reaching a log line or a tool response — the
  `Authorization` header, `ARUBA_CENTRAL_CLIENT_SECRET`, or a raw
  access token — at any level, `DEBUG` included.
- A network-identifying literal (AP name, serial number, MAC, site,
  SSID) committed anywhere, `scripts/smoke_probes.py` especially. This
  repository is public, and `tests/test_smoke_probes.py` exists to stop
  exactly this.
- Turning `__main__.py`'s `os._exit(0)` into `sys.exit(0)` or a
  graceful join. That reintroduces an interpreter-shutdown crash the CI
  matrix has actually caught.
- A tool handler that catches a broad `except Exception` and returns
  `None` or an empty result without re-raising or surfacing a visible
  error, so a real failure reads to the caller as a normal empty
  answer. (`daily_brief` reporting failures inside its own summary
  output is the deliberate exception, not a precedent to copy.)

## Report even though the default focus would not

- **Tool name and docstring accuracy.** An LLM picks a tool by reading
  these, so a docstring that misstates a parameter, a default, or what
  the tool returns is a functional defect here — report it even though
  comment and docstring accuracy is normally out of scope when
  reviewing code.
- **Missing tests on the two paths with a real bug history**, as
  advisory: a new or changed `client.fetch_all` call with no
  multi-page test, and a newly registered tool with no entry in
  `scripts/smoke_probes.py`. Report these even though a missing test is
  not itself a bug the diff introduces.

## Never report

- Formatting nits. `ruff check .` is gated in CI at a pinned version,
  but `ruff format` deliberately is not — see `ruff.toml`. This
  repository has not opted into a formatter.
- Suggestions to hand-build an MCP content envelope
  (`{"content": [...], "isError": ...}`) inside a tool handler.
  FastMCP wraps return values and derives `isError` from raised
  exceptions already.
- `release-please.yml` using `secrets.RELEASE_PLEASE_TOKEN` instead of
  `GITHUB_TOKEN`. Deliberate: a `GITHUB_TOKEN`-authored tag or release
  does not trigger downstream workflows.
- A runtime-error justification for the no-`X | Y` convention. Report an
  annotation inconsistent with the rest of a module if you see one, but
  PEP 604 syntax runs fine on Python 3.10+ — the rule is this
  codebase's own consistency choice, not a compatibility fix.

# Review rules for this repository

Review rules for this repository, on top of the reviewer's default
focus. Three things: which findings are blocking here, which classes to
report that the default focus would otherwise skip, and which are
noise. The reasoning behind the rules lives in
`.github/copilot-instructions.md` and `CLAUDE.md`, which the reviewer
also receives.

## Always blocking

- Anything reaching **stdout** from code that runs while the stdio
  server is serving — `server.py`, `client.py`, and `__main__.py` after
  `mcp.run()` is entered: a `print()`, a logger without an explicit
  stderr handler, or a dependency whose default logging configuration
  writes there. Stdout is the JSON-RPC channel there, and corrupting it
  breaks every connected client. This does **not** cover code that
  never runs alongside the server: `--check` returns before `mcp.run()`
  and prints its result to stdout on purpose, and `scripts/smoke_test.py`
  is a standalone CLI whose report *is* its stdout.
- A credential or token reaching a log line or a tool response — the
  `Authorization` header, `ARUBA_CENTRAL_CLIENT_SECRET`, or a raw
  access token — at any level, `DEBUG` included.
- A network-identifying literal (AP name, serial number, MAC, site,
  SSID) committed anywhere, `scripts/smoke_probes.py` especially. This
  repository is public, and `tests/test_smoke_probes.py` exists to stop
  exactly this.
- Turning `__main__.py`'s `os._exit(0)` into `sys.exit(0)` or a
  graceful join. FastMCP's stdio reader runs in a daemon thread blocked
  on `sys.stdin`, and joining it at interpreter shutdown can crash with
  `_enter_buffered_busy` on Python 3.14, which the CI matrix covers.
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
- **A change to `client.fetch_all`'s own pagination logic, or to a
  `fetch_all` call site, where the same diff touches `tests/` without
  covering a multi-page response**, as advisory. Cursor-based
  pagination has a real bug history here and nothing in CI enforces the
  coverage, so a single-page test passes while leaving the stop
  conditions (`next` absent, empty page, `total` reached) unexercised.
  Judge this only from the diff: a pull request that does not touch
  `tests/` at all may well be covered by tests you were not given, so
  do not infer absence from what is missing from the prompt.

## Never report

- Formatting nits. `ruff check .` is gated in CI at a pinned version,
  but `ruff format` deliberately is not — see `ruff.toml`. This
  repository has not opted into a formatter.
- A tool registered without an entry in `scripts/smoke_probes.py`.
  `tests/test_smoke_probes.py` already fails the build for it, so a
  review comment costs a round trip and carries no information. This
  covers the missing-probe assertion only — **not** the
  network-identifying-literal assertion in that same file, which stays
  blocking above: a leak into a public repository is worth catching
  twice.
- Suggestions to hand-build an MCP content envelope
  (`{"content": [...], "isError": ...}`) inside a tool handler.
  FastMCP wraps return values and derives `isError` from raised
  exceptions already.
- Suggestions to *replace* `release-please.yml`'s
  `secrets.RELEASE_PLEASE_TOKEN` with `GITHUB_TOKEN`. Preferring the
  dedicated token is deliberate, because a `GITHUB_TOKEN`-authored tag
  or release does not trigger downstream workflows. (The line is a
  `||` fallback, not an either/or, so a finding about the fallback arm
  itself is still fair game.)
- A `TypeError` or compatibility justification attached to the
  no-`X | Y` convention. PEP 604 syntax runs fine on Python 3.10+; the
  rule is this codebase's own consistency choice. (An annotation
  inconsistent with the rest of its module is still reportable — as a
  convention violation, on the strength of the convention alone.)

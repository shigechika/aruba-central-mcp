# Review rules for this repository

Review rules for this repository, on top of the reviewer's default
focus. Three things: which findings are blocking here, which classes to
report that the default focus would otherwise skip, and which are
noise. The reasoning behind the rules lives in
`.github/copilot-instructions.md` and `CLAUDE.md`, which the reviewer
also receives.

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
- **A new or changed `client.fetch_all` call with no multi-page test**,
  as advisory. Cursor-based pagination has a real bug history here, and
  nothing in CI enforces the coverage: a single-page test passes while
  leaving the stop conditions (`next` absent, empty page, `total`
  reached) unexercised. Report it even though a missing test is not
  itself a bug the diff introduces.

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
- `release-please.yml` using `secrets.RELEASE_PLEASE_TOKEN` instead of
  `GITHUB_TOKEN`. Deliberate: a `GITHUB_TOKEN`-authored tag or release
  does not trigger downstream workflows.
- A `TypeError` or compatibility justification attached to the
  no-`X | Y` convention. PEP 604 syntax runs fine on Python 3.10+; the
  rule is this codebase's own consistency choice. (An annotation
  inconsistent with the rest of its module is still reportable — as a
  convention violation, on the strength of the convention alone.)

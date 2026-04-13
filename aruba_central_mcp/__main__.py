"""Allow running as: python -m aruba_central_mcp"""

from __future__ import annotations

import argparse
import os
import sys

from aruba_central_mcp import __version__
from aruba_central_mcp.server import _get_client, mcp


def _check_config() -> int:
    """Verify environment variables and OAuth2 authentication."""
    try:
        client = _get_client()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    try:
        client._get_token()
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return 2
    print(f"OK: authenticated to {client.base_url}")
    return 0


def main() -> None:
    """Entry point for console_scripts."""
    parser = argparse.ArgumentParser(
        prog="aruba-central-mcp",
        description=(
            "MCP server for Aruba Central. "
            "Runs a STDIO JSON-RPC server exposing AP, switch, "
            "and wireless client status tools to AI assistants."
        ),
        epilog=(
            "Required environment variables: "
            "ARUBA_CENTRAL_BASE_URL, ARUBA_CENTRAL_CLIENT_ID, "
            "ARUBA_CENTRAL_CLIENT_SECRET."
        ),
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify environment variables and OAuth2 authentication, then exit.",
    )
    args = parser.parse_args()

    if args.check:
        sys.exit(_check_config())

    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        # Bypass normal interpreter shutdown: FastMCP's stdio reader runs in a
        # daemon thread blocked on sys.stdin, and joining it at shutdown can
        # crash with "_enter_buffered_busy" on Python 3.14.
        os._exit(0)


if __name__ == "__main__":
    main()

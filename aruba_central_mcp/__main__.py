"""Allow running as: python -m aruba_central_mcp"""

from aruba_central_mcp.server import mcp


def main():
    """Entry point for console_scripts."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

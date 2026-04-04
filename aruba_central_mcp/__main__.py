"""Allow running as: python -m aruba_central_mcp"""

from aruba_central_mcp.server import mcp

mcp.run(transport="stdio")

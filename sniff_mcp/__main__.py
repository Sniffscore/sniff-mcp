"""Console entry point: `sniff-mcp`, `python -m sniff_mcp`, or `uvx sniff-mcp`.

Runs the Streamable-HTTP MCP server (needs the release data on disk / via R2 —
see ARCHITECTURE.md). The hosted endpoint at https://mcp.sniff.world/mcp/ is the
zero-setup path; self-hosting is for air-gapped or high-volume use.
"""
from .server import main

if __name__ == "__main__":
    main()

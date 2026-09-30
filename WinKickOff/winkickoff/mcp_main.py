"""Console entry of the portable build (WinKickOff-mcp.exe): a stdio MCP server unless another flag is given."""

from __future__ import annotations

import sys

from winkickoff.mcp.cli import main

if __name__ == "__main__":
    sys.exit(main())

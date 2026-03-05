"""
meta_suppressor MCP server — thin FastMCP wrapper around suppressor_suite.meta_suppressor.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any
from mcp.server.fastmcp import FastMCP
from suppressor_suite.meta_suppressor import suppress as _suppress

mcp = FastMCP("meta_suppressor")


@mcp.tool()
def suppress(
    agent_turn: dict[str, Any],
    run: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run one or more suppressors over a single agent turn.

    Parameters
    ----------
    agent_turn : dict
        May contain any of: "prompt", "json_data", "tool_response", "grounding".
    run : list[str]
        Which suppressors to run: "prompt", "json", "tool_response", "grounding",
        or "all". Defaults to ["all"].

    Returns
    -------
    dict with keys: results, total_violations, summary
    """
    return _suppress(agent_turn=agent_turn, run=run)


if __name__ == "__main__":
    mcp.run()

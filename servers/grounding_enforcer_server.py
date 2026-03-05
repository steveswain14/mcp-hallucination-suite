"""
grounding_enforcer MCP server — thin FastMCP wrapper around suppressor_suite.grounding_enforcer.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any
from mcp.server.fastmcp import FastMCP
from suppressor_suite.grounding_enforcer import suppress as _suppress

mcp = FastMCP("grounding_enforcer")


@mcp.tool()
def suppress(
    model_output: str,
    retrieved_sources: list[dict],
    mode: str = "all",
) -> dict[str, Any]:
    """
    Check model_output against retrieved_sources for grounding violations.

    Parameters
    ----------
    model_output : str
        The assistant's response text to be checked.
    retrieved_sources : list[dict]
        Normalised source objects with keys: id, url, title, snippet, content, metadata.
    mode : str
        "strict", "lenient", or "all".

    Returns
    -------
    dict with keys: clean_text, violations, summary
    """
    return _suppress(
        model_output=model_output,
        retrieved_sources=retrieved_sources,
        mode=mode,
    )


if __name__ == "__main__":
    mcp.run()

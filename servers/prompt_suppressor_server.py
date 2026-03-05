"""
prompt_suppressor MCP server — thin FastMCP wrapper around suppressor_suite.prompt_suppressor.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Literal
from fastmcp import FastMCP
from suppressor_suite.prompt_suppressor import suppress as _suppress

mcp = FastMCP("prompt_suppressor")


@mcp.tool()
def suppress(
    conversation: list[dict[str, str]],
    canonical_system_prompt: str,
    mode: Literal["A", "B", "C", "all"] = "all",
) -> dict[str, Any]:
    """
    Suppress prompt injection and hallucination patterns in a conversation.

    Parameters
    ----------
    conversation : list
        List of message objects with 'role' and 'content' fields.
    canonical_system_prompt : str
        The authoritative system prompt defined by the developer.
    mode : str
        "A", "B", "C", or "all".

    Returns
    -------
    dict with keys: clean_conversation, violations, summary
    """
    return _suppress(
        conversation=conversation,
        canonical_system_prompt=canonical_system_prompt,
        mode=mode,
    )


if __name__ == "__main__":
    mcp.run()

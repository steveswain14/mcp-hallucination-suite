"""
tool_response_suppressor MCP server — thin FastMCP wrapper around suppressor_suite.tool_response_suppressor.
"""


from typing import Any, Literal
from fastmcp import FastMCP
from suppressor_suite.tool_response_suppressor import suppress as _suppress

mcp = FastMCP("tool_response_suppressor")


@mcp.tool()
def suppress(
    tool_responses: list[dict[str, Any]],
    schema: dict[str, Any],
    mode: Literal["A", "B", "C", "all"] = "all",
    assistant_commentary: str = "",
) -> dict[str, Any]:
    """
    Validate and clean tool responses against a schema and actual outputs.

    Parameters
    ----------
    tool_responses : list
        Each entry has: tool_name, actual_output, reported_output.
    schema : dict
        JSON Schema for the expected tool output structure.
    mode : str
        "A", "B", "C", or "all".
    assistant_commentary : str
        Free-form assistant text scanned for hallucination phrases (Layer C).

    Returns
    -------
    dict with keys: clean_output, violations, summary
    """
    return _suppress(
        tool_responses=tool_responses,
        schema=schema,
        mode=mode,
        assistant_commentary=assistant_commentary,
    )


if __name__ == "__main__":
    mcp.run()

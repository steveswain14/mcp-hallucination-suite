"""
json_suppressor MCP server — thin FastMCP wrapper around suppressor_suite.json_suppressor.
"""


from mcp.server.fastmcp import FastMCP
from suppressor_suite.json_suppressor import validate as _validate

mcp = FastMCP("json_suppressor")


@mcp.tool()
def validate(input: str, mode: str = "strict") -> dict:
    """
    Parse, repair, or extract JSON from a text string.

    Parameters
    ----------
    input : str
        The raw text to process.
    mode : str
        "strict", "lenient", or "extract".

    Returns
    -------
    dict with keys: mode_used, clean_data, violations
    """
    return _validate(input=input, mode=mode)


if __name__ == "__main__":
    mcp.run()

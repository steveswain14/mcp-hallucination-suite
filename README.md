# mcp-hallucination-suite

A structural anti-hallucination middleware suite for AI agent pipelines.

Most hallucination tools check whether content is true. This suite checks whether your pipeline is structurally sound - validating prompts, tool responses, structured outputs, and source grounding before hallucinated data can propagate through your system.

## The four suppressors

- **JSON Suppressor** - validates and cleans structured data against a schema, removing invented fields and coercing bad types.
- **Prompt Suppressor** - enforces clean prompt structure, strips model-invented instructions, and detects capability hallucinations.
- **Tool Response Suppressor** - verifies that what an agent claims a tool returned matches what the tool actually returned.
- **Grounding Enforcer** - cross-checks model output against retrieved sources, flagging any claim that cannot be traced back to a real source.

## Installation
```bash
pip install mcp-hallucination-suite
```

Or install from source:
```bash
git clone https://github.com/yourusername/mcp-hallucination-suite
cd mcp-hallucination-suite
pip install -e .
```

## Quick start

Add individual suppressors to your Claude Desktop config:
```json
{
  "mcpServers": {
    "json_suppressor": {
      "command": "python3",
      "args": ["/path/to/mcp-hallucination-suite/servers/json_suppressor_server.py"]
    },
    "grounding_enforcer": {
      "command": "python3",
      "args": ["/path/to/mcp-hallucination-suite/servers/grounding_enforcer_server.py"]
    }
  }
}
```

Or use the meta suppressor to run all four in one call:
```json
{
  "mcpServers": {
    "meta_suppressor": {
      "command": "python3",
      "args": ["/path/to/mcp-hallucination-suite/servers/meta_suppressor_server.py"]
    }
  }
}
```

## The meta suppressor

The meta suppressor orchestrates all four tools in a single call. Pass it an agent turn and specify which suppressors to run:
```python
from suppressor_suite.meta_suppressor import suppress

result = suppress(
    agent_turn={
        "prompt": {
            "conversation": [...],
            "canonical_system_prompt": "You are a helpful assistant."
        },
        "grounding": {
            "model_output": "According to McKinsey, 67% of companies...",
            "retrieved_sources": [...]
        }
    },
    run=["prompt", "grounding"]
)
```

It returns a unified result containing:
- a cleaned version of the agent turn
- all violations from every suppressor that ran
- a single summary describing the structural integrity of the turn

## Use it as a Python library

Every suppressor is available as plain Python with no MCP dependency:
```python
from suppressor_suite.json_suppressor import validate
from suppressor_suite.grounding_enforcer import suppress
```

## Contributing

Contributions are welcome. Please open an issue before submitting a PR so we can discuss the change first.

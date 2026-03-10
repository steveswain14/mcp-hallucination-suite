"""
meta_suppressor — runs multiple suppressors over a single agent turn.

Main entry point: suppress(agent_turn, run)
"""

from __future__ import annotations

from typing import Any

from suppressor_suite import json_suppressor, prompt_suppressor, tool_response_suppressor, grounding_enforcer


def suppress(
    agent_turn: dict[str, Any],
    run: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run one or more suppressors over a single agent turn.

    Parameters
    ----------
    agent_turn : dict
        May contain any of the following keys:
          - "prompt": dict with "conversation" and "canonical_system_prompt"
          - "json_data": dict with "input", "mode" (optional)
          - "tool_response": dict with "tool_responses", "schema", and optionally
            "mode" and "assistant_commentary"
          - "grounding": dict with "model_output", "retrieved_sources", and
            optionally "mode"
    run : list[str]
        Which suppressors to run. Values: "prompt", "json", "tool_response",
        "grounding", or "all". Defaults to ["all"].

    Returns
    -------
    dict with keys:
        results        - dict keyed by suppressor name, value is suppressor output
        total_violations - int, sum of all violations across all suppressors
        summary        - human-readable combined summary string
    """
    if run is None:
        run = ["all"]

    run_all = "all" in run
    run_prompt = run_all or "prompt" in run
    run_json = run_all or "json" in run
    run_tool = run_all or "tool_response" in run or "tool" in run
    run_grounding = run_all or "grounding" in run

    results: dict[str, Any] = {}
    total_violations = 0
    summary_parts: list[str] = []

    # ── Prompt suppressor ───────────────────────────────────────────────────
    if run_prompt and "prompt" in agent_turn:
        p = agent_turn["prompt"]
        # Support {content, source} shorthand as well as the full {conversation} format
        if "content" in p and "conversation" not in p:
            conversation = [{"role": "user", "content": p["content"]}]
        else:
            conversation = p.get("conversation", [])
        result = prompt_suppressor.suppress(
            conversation=conversation,
            canonical_system_prompt=p.get("canonical_system_prompt", ""),
            mode=p.get("mode", "all"),
        )
        results["prompt"] = result
        count = len(result.get("violations", []))
        total_violations += count
        summary_parts.append(f"prompt: {count} violation(s)")

    # ── JSON suppressor ─────────────────────────────────────────────────────
    if run_json and ("json_data" in agent_turn or "json" in agent_turn):
        j = agent_turn.get("json_data") or agent_turn.get("json")
        result = json_suppressor.validate(
            input=j.get("input", ""),
            mode=j.get("mode", "strict"),
        )
        results["json"] = result
        count = len(result.get("violations", []))
        total_violations += count
        summary_parts.append(f"json: {count} violation(s)")

    # ── Tool response suppressor ────────────────────────────────────────────
    if run_tool and ("tool_response" in agent_turn or "tool" in agent_turn):
        t = agent_turn.get("tool_response") or agent_turn.get("tool")
        result = tool_response_suppressor.suppress(
            tool_responses=t.get("tool_responses", []),
            schema=t.get("schema", {}),
            mode=t.get("mode", "all"),
            assistant_commentary=t.get("assistant_commentary", ""),
        )
        results["tool_response"] = result
        count = len(result.get("violations", []))
        total_violations += count
        summary_parts.append(f"tool_response: {count} violation(s)")

    # ── Grounding enforcer ──────────────────────────────────────────────────
    if run_grounding and "grounding" in agent_turn:
        g = agent_turn["grounding"]
        result = grounding_enforcer.suppress(
            model_output=g.get("model_output", ""),
            retrieved_sources=g.get("retrieved_sources", []),
            mode=g.get("mode", "all"),
        )
        results["grounding"] = result
        count = len(result.get("violations", []))
        total_violations += count
        summary_parts.append(f"grounding: {count} violation(s)")

    summary = (
        f"Total violations across all suppressors: {total_violations}. "
        + (", ".join(summary_parts) if summary_parts else "No suppressors ran.")
    )

    return {
        "results": results,
        "total_violations": total_violations,
        "summary": summary,
    }

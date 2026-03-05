"""
json_suppressor core logic.

Main entry point: validate(input, mode)
"""

from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repair_json(text: str) -> tuple[str, list[str]]:
    repairs: list[str] = []

    repaired = re.sub(r',(\s*[}\]])', r'\1', text)
    if repaired != text:
        repairs.append("trailing_comma: removed trailing comma(s) before } or ]")
        text = repaired

    repaired = re.sub(
        r'(?<=[{,])\s*([A-Za-z_]\w*)\s*:',
        lambda m: f' "{m.group(1)}":',
        text,
    )
    if repaired != text:
        repairs.append("unquoted_keys: added quotes around unquoted object key(s)")
        text = repaired

    return text, repairs


def _coerce_values(data: Any, violations: list[str], path: str = "root") -> Any:
    if isinstance(data, dict):
        return {k: _coerce_values(v, violations, f"{path}.{k}") for k, v in data.items()}
    if isinstance(data, list):
        return [_coerce_values(item, violations, f"{path}[{i}]") for i, item in enumerate(data)]
    if isinstance(data, str):
        low = data.lower()
        if low == "true":
            violations.append(f"{path}: coerced string 'true' to boolean true")
            return True
        if low == "false":
            violations.append(f"{path}: coerced string 'false' to boolean false")
            return False
        if re.fullmatch(r"-?\d+", data):
            v = int(data)
            violations.append(f"{path}: coerced string '{data}' to integer {v}")
            return v
        if re.fullmatch(r"-?\d+\.\d*([eE][+-]?\d+)?|-?\d*\.\d+([eE][+-]?\d+)?", data):
            v = float(data)
            violations.append(f"{path}: coerced string '{data}' to float {v}")
            return v
    return data


def _extract_json_text(text: str) -> str | None:
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        if candidate.startswith(("{", "[")):
            return candidate

    for start_ch, end_ch in [("{", "}"), ("[", "]")]:
        idx = text.find(start_ch)
        if idx == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(idx, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_ch:
                depth += 1
            elif ch == end_ch:
                depth -= 1
                if depth == 0:
                    return text[idx : i + 1]

    return None


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def validate(
    input: str,
    mode: str = "strict",
) -> dict:
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
    mode = mode.strip().lower()
    if mode not in ("strict", "lenient", "extract"):
        return {
            "mode_used": mode,
            "clean_data": None,
            "violations": [
                f"unknown_mode: '{mode}' is not valid — use strict, lenient, or extract"
            ],
        }

    if mode == "strict":
        try:
            clean_data = json.loads(input)
            return {"mode_used": "strict", "clean_data": clean_data, "violations": []}
        except json.JSONDecodeError as exc:
            return {
                "mode_used": "strict",
                "clean_data": None,
                "violations": [f"parse_error: {exc}"],
            }

    if mode == "lenient":
        violations: list[str] = []
        try:
            clean_data = json.loads(input)
        except json.JSONDecodeError as initial_err:
            repaired, repairs = _repair_json(input)
            if not repairs:
                return {
                    "mode_used": "lenient",
                    "clean_data": None,
                    "violations": [f"parse_error: {initial_err}"],
                }
            violations.extend(repairs)
            try:
                clean_data = json.loads(repaired)
            except json.JSONDecodeError as exc:
                return {
                    "mode_used": "lenient",
                    "clean_data": None,
                    "violations": violations + [f"parse_error: {exc}"],
                }
        clean_data = _coerce_values(clean_data, violations)
        return {"mode_used": "lenient", "clean_data": clean_data, "violations": violations}

    # extract
    extracted = _extract_json_text(input)
    if extracted is None:
        return {
            "mode_used": "extract",
            "clean_data": None,
            "violations": ["extract_error: no JSON object or array found in input"],
        }
    try:
        clean_data = json.loads(extracted)
        return {"mode_used": "extract", "clean_data": clean_data, "violations": []}
    except json.JSONDecodeError as exc:
        return {
            "mode_used": "extract",
            "clean_data": None,
            "violations": [f"parse_error: {exc}"],
        }

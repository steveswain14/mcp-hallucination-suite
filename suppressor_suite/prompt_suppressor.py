"""
prompt_suppressor core logic.

Main entry point: suppress(conversation, canonical_system_prompt, mode)
"""

from __future__ import annotations

import re
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Option A helpers
# ---------------------------------------------------------------------------

INSTRUCTION_PREFIXES = (
    "You must",
    "You should",
    "You are",
    "I will",
    "I am",
    "I cannot",
    "I must",
    "As an AI",
)


def _contains_instruction_language(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(prefix) for prefix in INSTRUCTION_PREFIXES):
            return True
    return False


def _duplicates_system_prompt(text: str, canonical: str) -> bool:
    if canonical in text or text in canonical:
        return True
    sentences = [s.strip() for s in re.split(r"[.!?]+", canonical) if len(s.strip()) > 20]
    for sentence in sentences:
        if sentence.lower() in text.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Option B helpers
# ---------------------------------------------------------------------------

_ROLE_DIRECTIVE_PATTERNS = [
    re.compile(r"\bYour role is\b", re.IGNORECASE),
    re.compile(r"\bYour job is\b", re.IGNORECASE),
    re.compile(r"\bYour purpose is\b", re.IGNORECASE),
    re.compile(r"\bYour goal is\b", re.IGNORECASE),
    re.compile(r"\bYour task is\b", re.IGNORECASE),
]

_NUMBERED_RULE = re.compile(r"^\s*(\d+[\.\)]\s+|\*\s+|-\s+).+", re.MULTILINE)

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|above) instructions?", re.IGNORECASE),
    re.compile(r"disregard (all )?(previous|prior|above) instructions?", re.IGNORECASE),
    re.compile(r"forget (all )?(previous|prior|above) instructions?", re.IGNORECASE),
    re.compile(r"override (the )?(system )?(prompt|instructions?)", re.IGNORECASE),
    re.compile(r"new (system )?(prompt|instructions?)[\s:]+", re.IGNORECASE),
    re.compile(r"from now on[,\s]+you (are|must|will|should)", re.IGNORECASE),
    re.compile(r"act as (a |an )?(?!assistant)", re.IGNORECASE),
    re.compile(r"pretend (you are|to be)", re.IGNORECASE),
    re.compile(r"your (new |updated )?(instructions?|rules?|directives?) (are|follow)", re.IGNORECASE),
]


def _is_structured_directive(text: str) -> bool:
    matches = _NUMBERED_RULE.findall(text)
    return len(matches) >= 3 and _has_role_directive(text)


def _has_role_directive(text: str) -> bool:
    return any(p.search(text) for p in _ROLE_DIRECTIVE_PATTERNS)


def _is_prompt_extension(text: str, canonical: str) -> bool:
    return _is_structured_directive(text)


def _has_injection_attempt(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# Option C helpers
# ---------------------------------------------------------------------------

_CAPABILITY_PATTERNS = [
    re.compile(r"\bI can browse\b", re.IGNORECASE),
    re.compile(r"\bI can access\b", re.IGNORECASE),
    re.compile(r"\bI can see your screen\b", re.IGNORECASE),
    re.compile(r"\bI can run code\b", re.IGNORECASE),
    re.compile(r"\bI can scrape\b", re.IGNORECASE),
    re.compile(r"\bI have access to\b", re.IGNORECASE),
    re.compile(r"\bI can search the (web|internet)\b", re.IGNORECASE),
    re.compile(r"\bI can execute\b", re.IGNORECASE),
    re.compile(r"\bI can (read|write|modify) (files?|your (files?|system|disk))\b", re.IGNORECASE),
    re.compile(r"\bI can access your (files?|system|disk|data|documents?)\b", re.IGNORECASE),
    re.compile(r"\baccess your (files?|system|disk|data|documents?)\b", re.IGNORECASE),
    re.compile(r"\bI('m| am) able to (browse|access|search|scrape|execute|run)\b", re.IGNORECASE),
    re.compile(r"\bI have the ability to (browse|access|search|scrape|execute|run)\b", re.IGNORECASE),
]

_ROLE_HALLUCINATION_PATTERNS = [
    re.compile(r"\bI am now\b", re.IGNORECASE),
    re.compile(r"\bI will now act as\b", re.IGNORECASE),
    re.compile(r"\bI have been configured as\b", re.IGNORECASE),
    re.compile(r"\bI am acting as\b", re.IGNORECASE),
    re.compile(r"\bI('ve| have) been (instructed|told|directed|asked) to (be|act as|pretend)\b", re.IGNORECASE),
]

_SAFETY_HALLUCINATION_PATTERNS = [
    re.compile(r"\bI must adhere to\b", re.IGNORECASE),
    re.compile(r"\bI am programmed to\b", re.IGNORECASE),
    re.compile(r"\bmy training requires\b", re.IGNORECASE),
    re.compile(r"\bI am required to\b", re.IGNORECASE),
    re.compile(r"\bmy (programming|design|architecture) (requires?|mandates?|forces?)\b", re.IGNORECASE),
    re.compile(r"\bI('m| am) (hard[- ]?coded|wired|built) to\b", re.IGNORECASE),
]


def _match_patterns(text: str, patterns: list[re.Pattern]) -> list[str]:
    return [p.pattern for p in patterns if p.search(text)]


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

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
    run_a = mode in ("A", "all")
    run_b = mode in ("B", "all")
    run_c = mode in ("C", "all")

    clean_conversation: list[dict[str, str]] = []
    violations: list[dict[str, Any]] = []

    for i, message in enumerate(conversation):
        role = message.get("role", "")
        content = message.get("content", "")
        cleaned_content = content

        if role == "system":
            if run_a and content != canonical_system_prompt:
                violations.append({
                    "index": i,
                    "role": role,
                    "type": "system_prompt_replaced",
                    "original": content,
                    "detail": "System message replaced with canonical system prompt.",
                })
            clean_conversation.append({"role": "system", "content": canonical_system_prompt})
            continue

        if role == "assistant":
            if run_a:
                if _duplicates_system_prompt(content, canonical_system_prompt):
                    violations.append({
                        "index": i,
                        "role": role,
                        "type": "system_prompt_duplication",
                        "original": content,
                        "detail": "Assistant message duplicates or paraphrases the system prompt.",
                    })
                    cleaned_content = ""

                if _contains_instruction_language(content):
                    violations.append({
                        "index": i,
                        "role": role,
                        "type": "instruction_language_detected",
                        "original": content,
                        "detail": "Assistant message contains instruction-like language.",
                    })

            if run_b:
                if _is_structured_directive(content) or _has_role_directive(content):
                    detail = (
                        "Assistant message contains structured directives or role-defining language."
                    )
                    if _is_prompt_extension(content, canonical_system_prompt):
                        detail = "Assistant message appears to rewrite or extend the system prompt."
                    violations.append({
                        "index": i,
                        "role": role,
                        "type": "role_boundary_violation",
                        "original": content,
                        "detail": detail,
                    })

            if run_c:
                cap_hits = _match_patterns(content, _CAPABILITY_PATTERNS)
                if cap_hits:
                    violations.append({
                        "index": i,
                        "role": role,
                        "type": "capability_hallucination",
                        "original": content,
                        "detail": f"Capability hallucination detected. Matched: {cap_hits}",
                    })

                role_hits = _match_patterns(content, _ROLE_HALLUCINATION_PATTERNS)
                if role_hits:
                    violations.append({
                        "index": i,
                        "role": role,
                        "type": "role_hallucination",
                        "original": content,
                        "detail": f"Role hallucination detected. Matched: {role_hits}",
                    })

                safety_hits = _match_patterns(content, _SAFETY_HALLUCINATION_PATTERNS)
                if safety_hits:
                    violations.append({
                        "index": i,
                        "role": role,
                        "type": "safety_hallucination",
                        "original": content,
                        "detail": f"Safety hallucination detected. Matched: {safety_hits}",
                    })

            clean_conversation.append({"role": "assistant", "content": cleaned_content})
            continue

        if role == "user":
            if run_b and _has_injection_attempt(content):
                violations.append({
                    "index": i,
                    "role": role,
                    "type": "role_boundary_violation",
                    "original": content,
                    "detail": "User message contains embedded instruction block attempting to override the system prompt.",
                })

        clean_conversation.append({"role": role, "content": content})

    def _count(vtype: str) -> int:
        return sum(1 for v in violations if v["type"] == vtype)

    parts = [f"Processed {len(conversation)} message(s). Mode: {mode}."]
    if run_a:
        parts.append(
            f"[A] System replaced: {_count('system_prompt_replaced')}, "
            f"Duplications: {_count('system_prompt_duplication')}, "
            f"Instruction language: {_count('instruction_language_detected')}."
        )
    if run_b:
        parts.append(f"[B] Role-boundary violations: {_count('role_boundary_violation')}.")
    if run_c:
        parts.append(
            f"[C] Capability hallucinations: {_count('capability_hallucination')}, "
            f"Role hallucinations: {_count('role_hallucination')}, "
            f"Safety hallucinations: {_count('safety_hallucination')}."
        )
    parts.append(f"Total violations: {len(violations)}.")

    return {
        "clean_conversation": clean_conversation,
        "violations": violations,
        "summary": " ".join(parts),
    }

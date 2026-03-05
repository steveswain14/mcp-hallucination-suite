"""
grounding_enforcer core logic.

Main entry point: suppress(model_output, retrieved_sources, mode)
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "it", "of",
    "in", "on", "at", "to", "for", "and", "or", "but", "with",
    "this", "that",
}

ASSERTION_VERBS = {
    "shows", "proves", "confirms", "indicates", "reveals",
    "states", "reports", "found", "concluded",
}

RETRIEVAL_PATTERNS = [
    r"I checked the website",
    r"I scraped",
    r"the API returned",
    r"I queried",
    r"I accessed the",
    r"the search returned",
    r"I browsed",
]

ATTRIBUTION_PATTERNS = [
    r"According to ([A-Z][^\.,]+?)(?:[,\.]|$)",
    r"([A-Z][A-Za-z\s]+?) reports",
    r"([A-Z][A-Za-z\s]+?) found",
    r"([A-Z][A-Za-z\s]+?) states",
    r"([A-Z][A-Za-z\s]+?) says",
    r"([A-Z][A-Za-z\s]+?) concluded",
]

STATISTIC_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(%|million|billion|thousand)\b",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(
    r"https?://[^\s\)\]>\"\']+",
    re.IGNORECASE,
)

VIOLATION_LABELS = {
    "ungrounded_claim": "ungrounded claims",
    "ungrounded_statistic": "ungrounded statistics",
    "ungrounded_url": "ungrounded URLs",
    "ungrounded_quote": "ungrounded quotes",
    "ungrounded_attribution": "ungrounded attributions",
    "fabricated_retrieval_claim": "fabricated retrieval claims",
    "ambiguous_grounding": "ambiguous grounding",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_source_contents(retrieved_sources: list[dict]) -> list[str]:
    return [s.get("content", "") for s in retrieved_sources if s.get("content")]


def _source_ids_containing(text: str, retrieved_sources: list[dict]) -> list[str]:
    matched = []
    for src in retrieved_sources:
        content = src.get("content", "")
        if text in content:
            matched.append(src.get("id", ""))
    return matched


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _non_stopwords(sentence: str) -> list[str]:
    tokens = re.findall(r"\b[a-zA-Z]+\b", sentence)
    return [t.lower() for t in tokens if t.lower() not in STOPWORDS]


def _has_trigger(sentence: str) -> bool:
    has_named_entity = bool(re.search(r"\b[A-Z][a-z]+\b", sentence))
    has_number = bool(re.search(r"\b\d+\b", sentence))
    lower = sentence.lower()
    has_assertion = any(v in lower.split() for v in ASSERTION_VERBS)
    return has_named_entity or has_number or has_assertion


def _terms_present_in_content(terms: list[str], content: str) -> int:
    content_lower = content.lower()
    return sum(1 for t in terms if t in content_lower)


def _source_ids_with_enough_terms(terms: list[str], retrieved_sources: list[dict]) -> list[str]:
    matched = []
    for src in retrieved_sources:
        content = src.get("content", "")
        if _terms_present_in_content(terms, content) >= 3:
            matched.append(src.get("id", ""))
    return matched


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def _check_quotes(model_output: str, retrieved_sources: list[dict]) -> list[dict]:
    violations = []
    pattern = re.compile(r'(?:"([^"]+)"|\'([^\']+)\')')
    for m in pattern.finditer(model_output):
        quoted_text = m.group(1) or m.group(2)
        source_ids = _source_ids_containing(quoted_text, retrieved_sources)
        if not source_ids:
            violations.append({
                "type": "ungrounded_quote",
                "span": m.group(0),
                "explanation": f"The quoted text \"{quoted_text}\" was not found verbatim in any source.",
                "source_ids": [],
            })
    return violations


def _check_urls(model_output: str, retrieved_sources: list[dict]) -> list[dict]:
    violations = []
    source_urls = {s.get("url") for s in retrieved_sources if s.get("url")}
    for m in URL_PATTERN.finditer(model_output):
        url = m.group(0)
        if url not in source_urls:
            violations.append({
                "type": "ungrounded_url",
                "span": url,
                "explanation": f"URL '{url}' does not appear in any retrieved source.",
                "source_ids": [],
            })
    return violations


def _check_statistics(model_output: str, retrieved_sources: list[dict]) -> list[dict]:
    violations = []
    for m in STATISTIC_PATTERN.finditer(model_output):
        number = m.group(1)
        unit = m.group(2).lower()
        span = m.group(0)

        start = m.start()
        window_start = max(0, start - 80)
        window_end = min(len(model_output), m.end() + 80)
        context_text = model_output[window_start:window_end]
        nearby_terms = [
            t.lower() for t in re.findall(r"\b[a-zA-Z]{3,}\b", context_text)
            if t.lower() not in STOPWORDS
        ]

        found_in_any = False
        source_ids = []
        for src in retrieved_sources:
            content = src.get("content", "")
            if number in content and unit in content.lower():
                if any(t in content.lower() for t in nearby_terms):
                    found_in_any = True
                    source_ids.append(src.get("id", ""))

        if not found_in_any:
            violations.append({
                "type": "ungrounded_statistic",
                "span": span,
                "explanation": f"Statistic '{span}' with surrounding context not found in any source.",
                "source_ids": source_ids,
            })
    return violations


def _check_claims(model_output: str, retrieved_sources: list[dict]) -> list[dict]:
    violations = []
    sentences = _split_sentences(model_output)
    for sentence in sentences:
        if not _has_trigger(sentence):
            continue
        terms = _non_stopwords(sentence)
        if len(terms) < 3:
            continue
        matched_ids = _source_ids_with_enough_terms(terms, retrieved_sources)
        if not matched_ids:
            violations.append({
                "type": "ungrounded_claim",
                "span": sentence,
                "explanation": "Sentence contains named entity, number, or assertion verb but fewer than 3 of its key terms appear together in any single source.",
                "source_ids": [],
            })
    return violations


def _check_attributions(model_output: str, retrieved_sources: list[dict]) -> list[dict]:
    violations = []
    all_titles = [s.get("title", "") or "" for s in retrieved_sources]
    all_meta_values: list[str] = []
    for s in retrieved_sources:
        meta = s.get("metadata", {}) or {}
        all_meta_values.extend(str(v) for v in meta.values())

    for pat in ATTRIBUTION_PATTERNS:
        for m in re.finditer(pat, model_output):
            entity = m.group(1).strip()
            entity_lower = entity.lower()
            matched = any(entity_lower in t.lower() for t in all_titles if t)
            if not matched:
                matched = any(entity_lower in v.lower() for v in all_meta_values if v)
            if not matched:
                violations.append({
                    "type": "ungrounded_attribution",
                    "span": m.group(0),
                    "explanation": f"Attribution to '{entity}' could not be matched to any source title or metadata.",
                    "source_ids": [],
                })
    return violations


def _check_retrieval_claims(model_output: str, retrieved_sources: list[dict]) -> list[dict]:
    violations = []
    source_urls = [s.get("url", "") or "" for s in retrieved_sources]

    has_any_url = any(source_urls)
    for pat in RETRIEVAL_PATTERNS:
        for m in re.finditer(pat, model_output, re.IGNORECASE):
            span = m.group(0)
            if not has_any_url:
                violations.append({
                    "type": "fabricated_retrieval_claim",
                    "span": span,
                    "explanation": f"Retrieval process claim '{span}' has no corresponding source URL or metadata to support it.",
                    "source_ids": [],
                })
            else:
                violations.append({
                    "type": "ambiguous_grounding",
                    "span": span,
                    "explanation": f"Retrieval process claim '{span}' could not be tied to a specific source.",
                    "source_ids": [],
                })
    return violations


# ---------------------------------------------------------------------------
# Mode application
# ---------------------------------------------------------------------------

def _apply_strict(model_output: str, violations: list[dict]) -> str:
    REPLACEMENT = "This claim could not be verified against the provided sources."
    sentences = _split_sentences(model_output)
    ungrounded_spans = {v["span"] for v in violations if v["type"] != "fabricated_retrieval_claim"}

    result_parts = []
    for sentence in sentences:
        if any(span in sentence for span in ungrounded_spans):
            result_parts.append(REPLACEMENT)
        else:
            result_parts.append(sentence)
    return " ".join(result_parts)


def _apply_lenient(model_output: str, violations: list[dict]) -> str:
    text = model_output
    seen = set()
    for v in violations:
        if v["type"] == "fabricated_retrieval_claim":
            continue
        span = v["span"]
        if span in seen or span not in text:
            continue
        seen.add(span)
        hedged = re.sub(
            r"\b(is|are|was|were)\b",
            lambda m: f"may {m.group(0)},",
            span,
            count=1,
        )
        if hedged == span:
            hedged = span + ", but this is not confirmed by the provided sources"
        else:
            hedged += ", but this is not confirmed by the provided sources"
        text = text.replace(span, hedged, 1)
    return text


def _apply_all(model_output: str, violations: list[dict]) -> str:
    text = model_output
    for v in violations:
        if v["type"] == "fabricated_retrieval_claim":
            text = text.replace(v["span"], "[retrieval claim removed]", 1)
    return text


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _build_summary(violations: list[dict], modified: bool) -> str:
    counts: dict[str, int] = {}
    for v in violations:
        counts[v["type"]] = counts.get(v["type"], 0) + 1

    total = sum(counts.values())
    parts = []
    for vtype, label in VIOLATION_LABELS.items():
        c = counts.get(vtype, 0)
        if c > 0:
            parts.append(f"{c} {label}")

    modification_note = "modified" if modified else "not modified"
    if parts:
        detail = ", ".join(parts)
        return f"{total} violations detected: {detail}. Output {modification_note}."
    else:
        return f"0 violations detected. Output {modification_note}."


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

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
        One of "strict", "lenient", or "all" (default "all").

    Returns
    -------
    dict with keys: clean_text, violations, summary
    """
    if mode not in {"strict", "lenient", "all"}:
        raise ValueError(f"Invalid mode '{mode}'. Must be 'strict', 'lenient', or 'all'.")

    violations: list[dict] = []
    violations.extend(_check_quotes(model_output, retrieved_sources))
    violations.extend(_check_urls(model_output, retrieved_sources))
    violations.extend(_check_statistics(model_output, retrieved_sources))
    violations.extend(_check_claims(model_output, retrieved_sources))
    violations.extend(_check_attributions(model_output, retrieved_sources))
    violations.extend(_check_retrieval_claims(model_output, retrieved_sources))

    if mode == "strict":
        clean_text = _apply_strict(model_output, violations)
    elif mode == "lenient":
        clean_text = _apply_lenient(model_output, violations)
    else:
        clean_text = _apply_all(model_output, violations)

    modified = clean_text != model_output

    return {
        "clean_text": clean_text,
        "violations": violations,
        "summary": _build_summary(violations, modified),
    }

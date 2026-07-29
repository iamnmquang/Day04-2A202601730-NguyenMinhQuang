from __future__ import annotations

import re
from collections import Counter
from typing import Any

from tools._shared import err, terms


DEFAULT_SOURCE_FIELDS = ("summary", "content", "body", "text", "article", "markdown", "description", "excerpt")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s+", " ", str(value)).strip()


def _truncate(text: str, max_chars: int) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    clipped = cleaned[: max(1, max_chars - 1)].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (clipped or cleaned[: max(1, max_chars - 1)]).rstrip() + "..."


def _split_sentences(text: str) -> list[str]:
    raw = re.sub(r"\r\n?", "\n", _clean_text(text))
    if not raw:
        return []

    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    segments: list[str] = []

    if len(lines) > 1:
        for line in lines:
            cleaned = re.sub(r"^[\-*\d\.\)\]]+\s*", "", line).strip()
            if not cleaned:
                continue
            parts = re.split(r"(?<=[.!?])\s+", cleaned)
            for part in parts:
                part = part.strip()
                if part:
                    segments.append(part)
        if segments:
            return segments

    parts = re.split(r"(?<=[.!?])\s+", raw.replace("\n", " "))
    return [part.strip() for part in parts if part.strip()]


def _keywords(text: str, limit: int = 5) -> list[str]:
    counts = Counter(terms(text))
    return [term for term, _ in counts.most_common(max(0, limit))]


def _first_non_empty(item: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, str]:
    for field in fields:
        value = _clean_text(item.get(field))
        if value:
            return field, value
    return "", ""


def _summarize_item(item: dict[str, Any], *, max_sentences: int, max_chars: int, max_points: int) -> dict[str, Any]:
    summary_field, source_text = _first_non_empty(item, DEFAULT_SOURCE_FIELDS)
    title = _clean_text(item.get("title"))
    url = _clean_text(item.get("url"))
    source = _clean_text(item.get("source"))
    section = _clean_text(item.get("section"))

    fallback_notes: list[str] = []
    if not source_text and title:
        source_text = title
        summary_field = "title"
        fallback_notes.append("title_fallback")

    sentences = _split_sentences(source_text)
    selected = sentences[: max(1, max_sentences)] if sentences else []

    if selected:
        summary_text = " ".join(selected)
    else:
        summary_text = source_text

    if not summary_text and title:
        summary_text = title

    raw_summary_text = _clean_text(summary_text)
    char_truncated = bool(raw_summary_text and len(raw_summary_text) > max_chars)
    summary_text = _truncate(raw_summary_text, max_chars) if raw_summary_text else ""
    source_excerpt = _truncate(source_text, max(240, min(max_chars * 2, 800))) if source_text else ""
    key_points = [_truncate(sentence, 160) for sentence in selected[: max(0, max_points)]]
    keywords = _keywords(" ".join([title, summary_text, source_text]), limit=5)

    source_note = summary_field or "none"

    if not source_text:
        fallback_notes.append("missing_text")

    return {
        "title": title,
        "url": url,
        "source": source,
        "section": section,
        "summary": summary_text or title,
        "source_excerpt": source_excerpt,
        "summary_source_field": source_note,
        "summary_mode": "extractive",
        "key_points": key_points,
        "keywords": keywords,
        "summary_chars": len(summary_text or ""),
        "source_chars": len(source_text or ""),
        "truncated": char_truncated,
        "fallback_notes": fallback_notes,
        "original_item": {
            key: value
            for key, value in item.items()
            if key not in {"summary", "content", "body", "text", "article", "markdown", "description", "excerpt"}
        },
    }


def summarize_news(
    items: list[dict[str, Any]] | None = None,
    max_sentences: int = 2,
    max_chars: int = 360,
    max_points: int = 3,
) -> dict[str, Any]:
    try:
        source_items = items or []
        max_sentences = max(1, int(max_sentences or 1))
        max_chars = max(60, int(max_chars or 360))
        max_points = max(1, int(max_points or 1))

        if not source_items:
            return {
                "tool": "summarize_news",
                "status": "empty",
                "passed": False,
                "items_checked": 0,
                "items_summarized": 0,
                "items": [],
                "issues": [{"severity": "warning", "problem": "no_items", "message": "No items were provided."}],
                "stats": {
                    "warning_count": 1,
                    "error_count": 0,
                    "total_source_chars": 0,
                    "total_summary_chars": 0,
                    "compression_ratio": 0.0,
                    "summary_source_fields": {},
                    "truncated_items": 0,
                    "fallback_title_count": 0,
                },
                "summary": "No items to summarize.",
            }

        summarized_items: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        source_field_counts: Counter[str] = Counter()
        total_source_chars = 0
        total_summary_chars = 0
        truncated_items = 0
        fallback_title_count = 0

        for index, item in enumerate(source_items):
            if not isinstance(item, dict):
                issues.append({
                    "index": index,
                    "severity": "error",
                    "problem": "invalid_item_type",
                    "message": "Each item must be an object.",
                    "item": item,
                })
                continue

            summarized = _summarize_item(
                item,
                max_sentences=max_sentences,
                max_chars=max_chars,
                max_points=max_points,
            )

            source_field = summarized.get("summary_source_field") or "none"
            source_field_counts[source_field] += 1
            total_source_chars += int(summarized.get("source_chars") or 0)
            total_summary_chars += int(summarized.get("summary_chars") or 0)

            if "title_fallback" in summarized.get("fallback_notes", []):
                fallback_title_count += 1
                issues.append({
                    "index": index,
                    "severity": "warning",
                    "problem": "title_fallback",
                    "message": "No body text was available, so the title was used as the digest summary.",
                    "title": summarized.get("title") or "",
                })

            if summarized.get("truncated"):
                truncated_items += 1
                issues.append({
                    "index": index,
                    "severity": "warning",
                    "problem": "truncated",
                    "message": "Summary was truncated to fit the configured character limit.",
                    "title": summarized.get("title") or "",
                })

            summarized_items.append(summarized)

        warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
        error_count = sum(1 for issue in issues if issue.get("severity") == "error")
        status = "ok" if error_count == 0 else "needs_fix"
        passed = error_count == 0
        compression_ratio = round(total_summary_chars / total_source_chars, 4) if total_source_chars else 0.0
        summary = (
            f"Summarized {len(summarized_items)} item(s) into concise digest-ready summaries."
        )
        if warning_count:
            summary += f" {warning_count} warning(s) generated."

        return {
            "tool": "summarize_news",
            "status": status,
            "passed": passed,
            "items_checked": len(source_items),
            "items_summarized": len(summarized_items),
            "max_sentences": max_sentences,
            "max_chars": max_chars,
            "max_points": max_points,
            "items": summarized_items,
            "issues": issues[:20],
            "stats": {
                "warning_count": warning_count,
                "error_count": error_count,
                "total_source_chars": total_source_chars,
                "total_summary_chars": total_summary_chars,
                "compression_ratio": compression_ratio,
                "summary_source_fields": dict(source_field_counts),
                "truncated_items": truncated_items,
                "fallback_title_count": fallback_title_count,
            },
            "summary": summary,
        }
    except Exception as exc:
        return err("summarize_news", exc)

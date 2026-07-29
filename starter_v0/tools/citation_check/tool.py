from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from tools._shared import domain, err


DEFAULT_REQUIRED_FIELDS = ("title", "url", "source", "summary")


def _clean_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    for key in ("title", "url", "source", "summary", "section"):
        if key in normalized:
            normalized[key] = _clean_text(normalized.get(key))

    url = str(normalized.get("url") or "").strip()
    source = str(normalized.get("source") or "").strip()
    inferred_source = domain(url) if url else ""

    if not source and inferred_source:
        normalized["source"] = inferred_source
        normalized["source_inferred"] = True
    elif source:
        normalized["source_inferred"] = False

    if url:
        normalized["url_host"] = inferred_source or domain(url)

    return normalized


def citation_check(
    items: list[dict[str, Any]] | None = None,
    required_fields: list[str] | None = None,
    max_issues: int = 20,
) -> dict[str, Any]:
    try:
        source_items = items or []
        fields = [str(field).strip() for field in (required_fields or list(DEFAULT_REQUIRED_FIELDS)) if str(field).strip()]
        normalized_items: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        complete_count = 0
        inferred_source_count = 0

        if not source_items:
            return {
                "tool": "citation_check",
                "status": "empty",
                "passed": False,
                "items_checked": 0,
                "required_fields": fields,
                "issues": [{"severity": "warning", "problem": "no_items", "message": "No items were provided."}],
                "items": [],
                "stats": {
                    "complete_items": 0,
                    "incomplete_items": 0,
                    "inferred_sources": 0,
                    "warning_count": 1,
                    "error_count": 0,
                },
                "summary": "No items to check.",
                "ready_for_format": False,
            }

        for index, item in enumerate(source_items):
            if not isinstance(item, dict):
                issues.append({
                    "index": index,
                    "severity": "error",
                    "problem": "invalid_item_type",
                    "message": "Each item must be an object.",
                    "item": item,
                })
                normalized_items.append({
                    "raw_item": item,
                    "citation_ok": False,
                    "citation_status": "invalid",
                })
                continue

            normalized = _normalize_item(item)
            url = str(normalized.get("url") or "").strip()
            host = str(normalized.get("url_host") or "").strip()
            item_had_error = False

            if normalized.get("source_inferred"):
                inferred_source_count += 1
                issues.append({
                    "index": index,
                    "severity": "warning",
                    "problem": "source_inferred",
                    "message": f"Source inferred from URL host: {host}.",
                    "url": url,
                    "source": host,
                })

            if url:
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    issues.append({
                        "index": index,
                        "severity": "error",
                        "problem": "invalid_url",
                        "message": "URL is not valid.",
                        "url": url,
                    })
                    item_had_error = True

            missing_fields = [field for field in fields if not _has_value(normalized.get(field))]
            if missing_fields:
                item_had_error = True
                issues.append({
                    "index": index,
                    "severity": "error",
                    "problem": "missing_fields",
                    "missing_fields": sorted(set(missing_fields)),
                    "message": "Missing required citation fields.",
                    "title": normalized.get("title") or "",
                    "url": url,
                    "source": normalized.get("source") or "",
                })

            if item_had_error:
                normalized["citation_ok"] = False
                normalized["citation_status"] = "incomplete"
            else:
                complete_count += 1
                normalized["citation_ok"] = True
                normalized["citation_status"] = "complete"

            normalized_items.append(normalized)

        error_count = sum(1 for issue in issues if issue.get("severity") == "error")
        warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
        status = "ok" if error_count == 0 else "needs_fix"
        ready_for_format = error_count == 0
        incomplete_count = len(normalized_items) - complete_count
        if ready_for_format:
            summary = f"All {len(normalized_items)} items are citation-ready."
            if warning_count:
                summary += f" {warning_count} warning(s) remain."
        else:
            summary = f"{complete_count}/{len(normalized_items)} items are citation-ready; fix {error_count} error(s) before formatting."

        issue_limit = max(0, int(max_issues or 0))

        return {
            "tool": "citation_check",
            "status": status,
            "passed": ready_for_format,
            "items_checked": len(normalized_items),
            "required_fields": fields,
            "issues": issues[:issue_limit],
            "items": normalized_items,
            "stats": {
                "complete_items": complete_count,
                "incomplete_items": incomplete_count,
                "inferred_sources": inferred_source_count,
                "warning_count": warning_count,
                "error_count": error_count,
            },
            "summary": summary,
            "ready_for_format": ready_for_format,
        }
    except Exception as exc:
        return err("citation_check", exc)

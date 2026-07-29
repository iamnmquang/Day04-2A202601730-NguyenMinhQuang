from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlparse, urlunparse

from tools._shared import domain, err, fold_text, terms


DEFAULT_DEDUPE_BY = ("url", "title")
_INTERNAL_FIELDS = {"normalized_url", "title_signature", "source_bucket"}


def _clean_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""
    if path not in {"", "/"}:
        path = path.rstrip("/")
    else:
        path = ""
    return urlunparse((scheme, host, path, "", "", ""))


def _title_signature(item: dict[str, Any]) -> str:
    title = str(item.get("title") or item.get("summary") or "").strip()
    if not title:
        return ""
    token_terms = sorted(terms(title))
    if token_terms:
        return " ".join(token_terms)
    return fold_text(title)


def _source_bucket(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    source = str(item.get("source") or "").strip()
    url_domain = domain(url) if url else ""
    if url_domain:
        return url_domain
    if source:
        return fold_text(source)
    return ""


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    for key in ("title", "url", "source", "summary", "section"):
        if key in normalized:
            normalized[key] = _clean_text(normalized.get(key))
    normalized["normalized_url"] = _normalize_url(str(normalized.get("url") or ""))
    normalized["title_signature"] = _title_signature(normalized)
    normalized["source_bucket"] = _source_bucket(normalized)
    return normalized


def source_dedupe(
    items: list[dict[str, Any]] | None = None,
    dedupe_by: list[str] | None = None,
    keep_per_source: int = 2,
    max_issues: int = 20,
) -> dict[str, Any]:
    try:
        source_items = items or []
        strategies = [
            str(strategy).strip().lower()
            for strategy in (dedupe_by or list(DEFAULT_DEDUPE_BY))
            if str(strategy).strip()
        ]
        source_limit = max(1, int(keep_per_source or 1))
        issue_limit = max(0, int(max_issues or 0))

        if not source_items:
            return {
                "tool": "source_dedupe",
                "status": "empty",
                "passed": True,
                "items_checked": 0,
                "items_kept": 0,
                "duplicates_removed": 0,
                "dedupe_by": strategies,
                "keep_per_source": source_limit,
                "items": [],
                "duplicates": [],
                "issues": [{"severity": "warning", "problem": "no_items", "message": "No items were provided."}],
                "stats": {
                    "unique_sources": 0,
                    "duplicate_groups": 0,
                    "warning_count": 1,
                    "error_count": 0,
                    "weak_identity_count": 0,
                    "duplicate_reasons": {},
                    "source_counts": {},
                },
                "summary": "No items to dedupe.",
            }

        kept_items: list[dict[str, Any]] = []
        duplicate_items: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        seen_keys: dict[str, int] = {}
        source_counts: Counter[str] = Counter()
        source_owner: dict[str, int] = {}
        duplicate_reasons: Counter[str] = Counter()
        weak_identity_count = 0

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

            normalized = _normalize_item(item)
            url_key = normalized.get("normalized_url") or ""
            title_key = normalized.get("title_signature") or ""
            source_bucket = normalized.get("source_bucket") or ""

            if not (url_key or title_key or source_bucket):
                weak_identity_count += 1
                issues.append({
                    "index": index,
                    "severity": "warning",
                    "problem": "weak_identity",
                    "message": "Item has no stable URL/title/source identifier; keeping it as-is.",
                    "item": {
                        "title": normalized.get("title") or "",
                        "url": normalized.get("url") or "",
                        "source": normalized.get("source") or "",
                    },
                })

            duplicate_of: int | None = None
            duplicate_reason = ""
            matched_key = ""

            for strategy in strategies:
                if strategy == "url" and url_key:
                    key = f"url:{url_key}"
                elif strategy == "title" and title_key:
                    key = f"title:{title_key}"
                elif strategy == "source" and source_bucket:
                    key = f"source:{source_bucket}"
                else:
                    continue
                if key in seen_keys:
                    duplicate_of = seen_keys[key]
                    duplicate_reason = f"same_{strategy}"
                    matched_key = key
                    break

            if duplicate_of is None and source_bucket and source_counts[source_bucket] >= source_limit:
                duplicate_of = source_owner.get(source_bucket)
                duplicate_reason = "source_limit"
                matched_key = f"source:{source_bucket}"

            if duplicate_of is not None:
                duplicate_reasons[duplicate_reason] += 1
                duplicate_items.append({
                    "index": index,
                    "duplicate_of": duplicate_of,
                    "reason": duplicate_reason,
                    "dedupe_key": matched_key,
                    "title": normalized.get("title") or "",
                    "url": normalized.get("url") or "",
                    "source": normalized.get("source") or source_bucket,
                })
                continue

            kept_index = len(kept_items)
            kept_item = {
                key: value
                for key, value in normalized.items()
                if key not in _INTERNAL_FIELDS
            }
            kept_item["dedupe_key"] = url_key or title_key or source_bucket or f"fallback:{index}"
            kept_item["dedupe_reason"] = "primary"
            kept_item["is_primary"] = True
            kept_items.append(kept_item)

            if url_key:
                seen_keys[f"url:{url_key}"] = kept_index
            if title_key:
                seen_keys[f"title:{title_key}"] = kept_index
            if source_bucket:
                seen_keys[f"source:{source_bucket}"] = kept_index
                source_counts[source_bucket] += 1
                source_owner.setdefault(source_bucket, kept_index)

        duplicate_count = len(duplicate_items)
        unique_sources = len(source_counts)
        warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
        error_count = sum(1 for issue in issues if issue.get("severity") == "error")
        status = "ok" if error_count == 0 else "needs_fix"
        summary = (
            f"Kept {len(kept_items)} of {len(source_items)} items after dedupe"
            f" across {unique_sources} source bucket(s)."
        )
        if duplicate_count:
            summary += f" Removed {duplicate_count} duplicate item(s)."
        if weak_identity_count:
            summary += f" {weak_identity_count} item(s) had weak identifiers."

        return {
            "tool": "source_dedupe",
            "status": status,
            "passed": error_count == 0,
            "items_checked": len(source_items),
            "items_kept": len(kept_items),
            "duplicates_removed": duplicate_count,
            "dedupe_by": strategies,
            "keep_per_source": source_limit,
            "items": kept_items,
            "duplicates": duplicate_items[:issue_limit],
            "issues": issues[:issue_limit],
            "stats": {
                "unique_sources": unique_sources,
                "duplicate_groups": len(duplicate_reasons),
                "warning_count": warning_count,
                "error_count": error_count,
                "weak_identity_count": weak_identity_count,
                "duplicate_reasons": dict(duplicate_reasons),
                "source_counts": dict(source_counts.most_common(10)),
            },
            "summary": summary,
        }
    except Exception as exc:
        return err("source_dedupe", exc)

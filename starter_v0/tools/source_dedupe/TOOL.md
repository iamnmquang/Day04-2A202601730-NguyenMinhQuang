---
name: source_dedupe
track: bonus
kind: control
provider: local
requires_env: []
inputs: [items, dedupe_by, keep_per_source, max_issues]
outputs: [items, duplicates, issues, status, passed, summary, stats, items_checked, items_kept, duplicates_removed]
side_effect: false
---
# source_dedupe

Removes obvious duplicate news items before the digest is formatted. It keeps
the first item for duplicate URLs or titles and can cap how many items from the
same source bucket are retained.

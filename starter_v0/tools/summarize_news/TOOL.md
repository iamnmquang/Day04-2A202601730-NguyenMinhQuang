---
name: summarize_news
track: bonus
kind: local_formatter
provider: local
requires_env: []
inputs: [items, max_sentences, max_chars, max_points]
outputs: [items, issues, status, passed, summary, stats, items_checked, items_summarized]
side_effect: false
---
# summarize_news

Turns fetched or lookup-based news items into short digest-ready summaries.
Use it after `fetch` and before `format` when the raw source text is too long
for the final digest.

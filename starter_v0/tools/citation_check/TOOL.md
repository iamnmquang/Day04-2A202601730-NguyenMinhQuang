---
name: citation_check
track: bonus
kind: control
provider: local
requires_env: []
inputs: [items, required_fields, max_issues]
outputs: [items, issues, status, passed, summary, stats, items_checked, required_fields, ready_for_format]
side_effect: false
---
# citation_check

Checks whether news items have usable citation metadata before they are
formatted into a digest. Use it after `lookup` and/or `fetch`, and before
`format`.

It can infer `source` from the URL host when needed, but it still flags the
item so the agent knows the citation is weaker than a fully provided source
label.

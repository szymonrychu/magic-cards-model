---
name: never-recall-mtg-rules-from-memory
description: "MTG rules and CR numbers must always be verified with knowledge_search, never recalled from training data"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6a8b5028-7888-40c6-89b6-15ddd250140a
  modified: 2026-08-26T20:40:26.105Z
---

Never state an MTG rule or a Comprehensive Rules number from training data. Every
rule and every CR citation must be verified in-session with
`knowledge_search(q="...", type="rules")` on the `spellslinger` MCP server before
being written down. This applies even when confident - especially when confident.

**Why:** the CR is revised with every set release. Rule numbers get reassigned,
wording changes, sections move. Training data is a snapshot of an unknown past
version, and the failure mode is plausible-and-wrong, which no amount of care
catches by feel. Two real cases in this repo: ability categories are CR 113.3,
not the remembered 112.3; damage to a player is CR 119.2 / 120.3a and conceding
is CR 104.3a, not the remembered 119.3c and 800.4a.

**How to apply:** put this in VERY STRONG language in every subagent prompt that
touches rules. Writing a CR number that was not looked up counts as a defect even
if it happens to be correct. If a rule cannot be confirmed, mark the code
`unparsed` or the test `xfail` and report it. Card text likewise goes through
`resolve_cards`, never memory. See [[no-mocks-scenario-tests]] and
[[magic-cards-model-engine-goal]].

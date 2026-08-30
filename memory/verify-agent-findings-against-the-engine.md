---
name: verify-agent-findings-against-the-engine
description: Adjudicator and reviewer subagents each produce confident wrong findings - check every claim against the running engine before acting on it
metadata:
  type: feedback
---

Subagent findings in this project are **plausible-and-wrong often enough that
none of them may be acted on unchecked** - including findings from the expensive
adjudicator models, and including findings about the engine rather than about
the rules.

**Why:** in the first playtest fix wave (2026-08-29) two of the highest-quality
reports each carried exactly one confident, well-argued, false claim:

- An opus adjudicator reported that the CR 605.3b off-stack mana path "adds mana
  without tapping the permanent or paying the rest of the cost", naming four
  cards. A test that actually ran the path showed every cost paid: Tinder Farm
  went to the graveyard, Sunbaked Canyon took the life, Arena of Glory tapped
  and exerted. The claim came from reading code, not running it.
- A sonnet reviewer reported a *blocking* bug: Wastes would tap for nothing,
  because `intrinsic_land_ability` builds colours from the five basic land types
  and omits Wastes. In fact Wastes has **no subtypes at all** (its type line is
  bare `Basic Land`) and prints `{T}: Add {C}.` as real rules text, so it takes
  the printed path. Returning None for it is correct.

Both reports were otherwise excellent and both findings were the kind that reads
as obviously true. Neither was caught by argument - only by running the engine.

**How to apply:** before acting on any subagent finding, reproduce it. For a
claim about behaviour, run the real path and paste the observed values; for a
claim about a card, check it with `resolve_cards`; for a claim about a rule,
look it up with `knowledge_search`. Brief agents to settle disagreements with
"evidence you actually ran, not a code read" - that phrasing is what produced
the correction in both cases above. When two agents disagree, do not pick the
more senior model; make one of them run the thing.

Related: [[never-recall-mtg-rules-from-memory]], [[autonomous-playtest-loop]],
[[agent-playtest-launch]].

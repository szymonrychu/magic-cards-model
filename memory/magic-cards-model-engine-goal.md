---
name: magic-cards-model-engine-goal
description: "magic-cards-model aims to be a complete MTG rules engine, not a card database"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a8b5028-7888-40c6-89b6-15ddd250140a
  modified: 2026-08-26T20:21:51.896Z
---

magic-cards-model is being built as a **full MTG rules engine** capable of
playing real PvP games, not a card data model with helpers. Scope decisions
should be judged against that: does this get closer to a playable game.

As of 2026-08-26 the casting subsystem is complete (announcement, costs, stack,
priority, countering, land drops, lethal damage), and combat, player damage,
deck setup, turn-based actions, triggered/activated abilities, and the layer
system are not built. `docs/engine-coverage.md` in the repo is the live status -
read it rather than trusting this date-stamped summary.

Rules research goes through the `spellslinger` MCP server configured in
`.mcp.json` (`knowledge_search` for CR text, `reveries_search` for corner cases),
not from memory. See [[no-mocks-scenario-tests]].

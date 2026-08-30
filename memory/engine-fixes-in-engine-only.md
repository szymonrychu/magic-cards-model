---
name: engine-fixes-in-engine-only
description: "Rules gaps get fixed in the engine, never papered over in the API/frontend layer"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 81b92459-9c29-49f8-b31e-2a7dbe5fd83f
  modified: 2026-08-28T10:38:16.832Z
---

When a rules bug surfaces through the API or web frontend, the fix must land
in `magic-cards-model` (the engine) - never as a workaround in
`magic-cards-model-api` (seeding pools, filtering serializers, duplicating
logic) or the frontend.

**Why:** the user said it flatly after I proposed API-side fixes for floating
mana not paying for casts: "engine fixes MUST land only on engine.. no API
shenanigans and workarounds and techdebt.. only the MOST CORRECT
implementation". The API is a thin remote control over the engine; anything
the API has to fix up is engine debt wearing a disguise, and it leaves the
engine wrong for every other caller (the scenario harness included).

**How to apply:** when a gap shows up via the app, find the engine seam and
fix it there, with scenario tests in the engine repo. The API may only *wire*
to existing engine behavior (calling `Game.activate_ability` is wiring;
copying a player's mana pool into a payment is a workaround). If the engine
file is owned by a running agent, queue the fix for after it lands rather
than patching around it. See also [[magic-cards-model-engine-goal]].

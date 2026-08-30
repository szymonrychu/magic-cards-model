---
name: subagents-on-cheaper-model
description: "Dispatch subagents on the cheaper model (Sonnet), not the session model"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 81b92459-9c29-49f8-b31e-2a7dbe5fd83f
  modified: 2026-08-28T07:19:55.562Z
---

When dispatching subagents (Agent tool), pass `model: "sonnet"` instead of
letting them inherit the session model.

**Why:** the user asked for this explicitly mid-session ("switch to sonets!",
"kill existing agents and use cheaper model (e.g. sonnet)") after two agents
were launched on the inherited model — they had me kill both and relaunch on
Sonnet. Subagent work here is well-scoped mechanical work (audits, single-mechanic
implementation against a written brief) that Sonnet handles, and the session
model is the expensive one.

**How to apply:** every Agent call in this project gets `model: "sonnet"`
unless the user says otherwise for that specific dispatch. Applies to future
waves too, not just the batch that prompted it. See also
[[magic-cards-model-engine-goal]].

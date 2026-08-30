---
name: user-examples-become-testcases
description: "Every gameplay example the user reports becomes a scenario test, not just a fix"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 81b92459-9c29-49f8-b31e-2a7dbe5fd83f
  modified: 2026-08-28T11:18:51.655Z
---

When the user reports a rules bug or edge case from their own play-testing
(e.g. "Azusa, Lost but Seeking should let me play two additional lands"), the
report itself is test material: convert the exact example into a scenario test
in the engine repo alongside the fix - real printings, the board state they
described, the outcome they expected.

**Why:** the user said it as a standing instruction while play-testing the web
app: "When I'm providing you these examples, always convert them to testcases!"
Their examples are the highest-value regression tests available - they are real
interactions a human expected to work, found by using the engine rather than
reading the rules.

**How to apply:** for every user-reported example, before or with the fix,
write the scenario test that encodes it (the described board, the action, the
expected allow/refuse). If the fix is queued behind an in-flight agent, the
test goes in the same brief. See also [[engine-fixes-in-engine-only]] and
[[no-mocks-scenario-tests]].

---
name: ironsmith-compare-process-boundary
description: "The MCM vs ironsmith comparison talks to ironsmith only as separate processes, locally, and commits nothing of ironsmith's"
metadata:
  node_type: memory
  type: decision
  modified: 2026-11-11
---

2026-11-11 (T-109 step 2, `scripts/ironsmith_compare/`, `docs/ironsmith-compare.md`).

MCM is MIT; ironsmith (github.com/Chiplis/ironsmith) is `BUSL-1.1 OR AGPL-3.0-or-later`.
The comparison CLI keeps the two separate programs:

- It never imports, links, vendors, copies or ports ironsmith code or text. ironsmith's
  own unmodified binaries (`sync_registry_db`, `sync_card_status_db`) are started as
  subprocesses on our data file (a Scryfall card array); their output (status SQLite) is
  read back as data. The status reader
  never selects `compiled_text` or `compiled_card_definition`.
- No generated glue: nothing of ours, generated or committed, imports ironsmith.
- It runs only on the user's machine, on demand, against a checkout pinned in
  `scripts/ironsmith_compare/pin.toml` (bumped only by a reviewed PR); `doctor` refuses
  a dirty or wrong-sha checkout. It never runs in CI and no agent clones, builds or runs
  ironsmith in a pod.
- Tests use hand-written fixtures in ironsmith's documented output shape (a SQLite with
  only the status columns), never ironsmith output.

**Why:** the user's decisions (engine stays MCM; ironsmith is a reference only; local
on-demand compare; T-109 plan questions Q1 A, Q2 A, Q3 B, Q4 A). The GPL FAQ treats
programs talking over pipes, files and command-line arguments as separate works, and
AGPL s.13 binds only a modified version offered over a network; we elect AGPL and run
an unmodified copy locally, so nothing of ours becomes a combined work. Option Q2 B (a
Node driver of ours importing ironsmith's WASM) was declined for exactly that reason.

2026-11-11 update: the behaviour diff (MCM goldens replayed in ironsmith's scenario
runner) was dropped. Its test runner has no data-file entry point, so it needed a generated
`.mjs` shim importing `scripts/mage-port-runner.mjs`, which breaks the strict boundary above.
Only coverage and the worklist remain.

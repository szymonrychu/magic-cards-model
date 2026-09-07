---
name: game-schema-version-fail-closed
description: T9 of stateless-library added Game.schema_version (a required, no-default int) refusing decode on mismatch or absence via a mode="before" validator raising a non-ValueError so pydantic never rewraps it
metadata:
  type: project
---

**2026-09-07.** `Game.schema_version` (`models/game.py`) is a purpose-built
counter, deliberately not `magic_cards_model.__version__` - the package
version changes for packaging reasons unrelated to whether a decoded
snapshot still means what it meant when written, and would either force
spurious bumps or miss the change that actually matters (an `EFFECTS`/
`abilities.py`/`delayed.py`/`layers.py` registry entry changing what a
decoded state's own pending stack object does).

Two design problems worth remembering if this needs touching again:

1. **Defaulted field + "check on validate" silently accepts missing data as
   current.** A field `schema_version: int = CURRENT_SCHEMA_VERSION` lets a
   dict missing the key fill in the default before any check runs - exactly
   the silent-default shape `silent-default-dispatch-tables.md` warns about.
   Fix: no default (required field) plus a `mode="before"` validator that
   inspects the *raw* input dict for key presence before pydantic could fill
   anything in. This is also why every one of the ~5 fresh-construction call
   sites in this repo (`Match.start_game`, the scenario harness, three bare
   `Game(players=...)` test sites) now passes `schema_version=Game.
   CURRENT_SCHEMA_VERSION` explicitly - a `mode="before"` validator cannot
   tell "fresh code construction forgot to pass it" from "decoded dict never
   had it", so both must supply the key.

2. **A `mode="before"`/`"after"` validator that raises `ValueError` gets
   swallowed and rewrapped into a generic `pydantic.ValidationError`** -
   verified empirically, not assumed. A caller wanting to catch a version
   mismatch specifically (the future Postgres persistence/replay layer will)
   cannot catch a `ValueError` subclass raised this way; only `pydantic_core.
   ValidationError` propagates. Fix: `SchemaVersionMismatch` subclasses
   `RuntimeError`, which pydantic-core does not intercept, so it propagates
   as itself - verified through a bare `Game.model_validate` call and through
   `Game` nested as an element of `Match.games` (a `mode="before"` validator
   is compiled into the type's own core schema, so it fires for a nested
   decode too, unlike overriding the `model_validate` classmethod, which only
   fires on a direct top-level call).

Related: [[silent-default-dispatch-tables]],
[[delayed-trigger-serialization-game-py-isolation]].

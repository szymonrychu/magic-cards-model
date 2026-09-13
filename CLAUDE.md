# magic-cards-model

Building a **full Magic: the Gathering rules engine** on pydantic. Not a card
database with helpers - the target is an engine that plays the game correctly,
including the corner cases.

That target sets the standard for tests. A mechanic is not done when the happy
path works; it is done when the interactions around it are covered. See
`docs/engine-coverage.md` for what is modelled and what is not - keep it current,
and check it before writing a scenario, because a mechanic listed as missing
needs an `xfail` test rather than a test bent until it passes.

## NEVER state a rule from memory. Look EVERY rule up. No exceptions.

**Your training data is WRONG about the Comprehensive Rules.** Not vague - wrong.
The CR is revised with every set release: rule numbers get reassigned, wording
changes, whole sections move. What you remember is a snapshot of some past
version and you cannot tell which one.

**Every rule you rely on, and every CR number you write, MUST be verified with
`knowledge_search(q="...", type="rules")` in this session, before you write it.**
Not "when unsure" - you cannot tell when you are unsure. The rule you are most
confident about is exactly the one that quietly renumbered.

This is not hypothetical. Both of these already happened in this repo:

- Ability categories are **CR 113.3**. An agent confidently wrote **112.3** from
  memory. Wrong - the parser docstring now records the correction.
- Damage to a player is **CR 119.2 / 120.3a**; conceding is **CR 104.3a**. An
  agent wrote **119.3c** and **800.4a** from memory. Both wrong, both plausible.

Plausible-and-wrong is the whole problem. You will not catch it by feel.

### When `knowledge_search` is not enough

It **truncates long rules**. CR 305.7 came back cut at "and any" on every
phrasing tried, and the missing tail - "Note that this doesn't remove any
abilities that were granted to the land by other effects" - was the whole
answer to the question being asked. A truncated rule reads like a complete one.

So there is a second source, the primary one, on disk:

```sh
mise run rules:pull          # latest CR from wizards.com, into .rules/ (gitignored)
mise run rules:find 305.7    # that rule and its subrules, in full
```

`rules:find` reads only that local `.rules/` copy, which is gitignored, so a
fresh clone or worktree has none: run `rules:pull` there once before the first
`rules:find`, which otherwise stops with "no local rules file".

`rules:pull` scrapes the current download link rather than pinning a URL,
because the filename carries the release date and moves with every update.

`knowledge_search` stays the first stop - it is faster and it searches by
meaning, not just by number. Reach for `rules:find` when a rule comes back cut
off, when you need a rule's exact full wording, or when you already know the
number and want to read it whole. Both are lookups; neither is memory.

If **neither** can confirm a rule, say so in your report and mark the code
`unparsed` or the test `xfail`. **Writing a CR number you did not look up is a
defect even when the number turns out to be right** - it means the next one
will not be.

Card text is the same: verify with `resolve_cards`, never from memory.

### The tools

- `knowledge_search(q="...", type="rules")` - **the rules. Use constantly.**
- `resolve_cards`, `card_search` - card lookup. The card database has holes, so
  a miss does not mean the card is not real; check Scryfall.
- `reveries_search` - **do not use.** It holds deck-analysis notes, not rules,
  and burns large amounts of context returning irrelevant documents.

The verified state of each tool, and its traps, are in `docs/mcp-tools.md`.

## Layout

- `src/magic_cards_model/models/` - data. `card.py` mirrors the gameplay subset
  of the Scryfall card object; `card_state.py` is one physical card in a game;
  `player.py`, `game.py`, `match.py` are the containers; `mana.py` is costs and
  the pool; `zone.py` is the seven rules zones plus the sideboard.
- `src/magic_cards_model/machines/` - state machines. `turn.py` is the turn
  structure, `priority.py` is CR 117, `casting.py` is CR 601.2 announcement,
  `cost.py` is paying, `abilities.py` parses mana abilities off oracle text,
  `effects.py` is what a spell does when it resolves, `decisions.py` is CR
  608.2d's mid-resolution questions plus the pause/replay tape, and
  `legal_actions.py` enumerates every action a player may legally take right
  now.
- `src/magic_cards_model/ids.py` - the one place every object id is minted,
  deterministically per game when a `Game` method opens
  `_id_allocator_scope()`.
- `tests/scenarios/` - scenario tests. See below.

## What this library owes its consumers

This is a stateless library (`ROADMAP.md`), and it owes whatever holds a
`Game` two guarantees plus the invariant that makes both trustworthy.

**Decode any game state.** Every persisted model is data: no callables survive
on a model. A spell's or ability's stored behaviour - `ContinuousEffect`'s
`condition`/`selector`/`modification` (`machines/layers.py`),
`DelayedTrigger.effect` (`machines/delayed.py`), and `AbilityOnStack`'s
`keyword_activation`/`unless_payment` - is a pydantic discriminated union on
`kind`, which refuses an unknown tag at decode instead of silently resolving
to nothing (see `memory/callables-became-discriminated-unions.md` for why a
name-keyed registry was rejected). `Game.schema_version` refuses to decode a
game written by a different engine (`SchemaVersionMismatch`) rather than
defaulting a missing field to current. Object ids are deterministic per
`game_uid` (`ids.py`), so the same commands replayed from the same decoded
state mint the same ids.

**Enumerate every legal action.** `legal_actions(game, player, *,
pending=None)` in `machines/legal_actions.py` returns frozen `Action` records
(`models/action.py`) - ids only, never a live `CardState`/`Player`/`Card` - what
`player` may do right now, including while a `Decision` is pending. It never
gates on affordability (CR 118.6: an unpayable cast is still a legal one) -
an unaffordable action is still enumerated, carrying an `Affordability`
verdict alongside it instead of being dropped.

**The round-trip/replay invariant** is what makes trusting either guarantee
possible instead of merely hoping it holds; see `tests/scenarios/conftest.py`
below.

## Target the mechanic, never the card

**Every ability is parsed from oracle text.** MTG uses a strict templating
language: the same mechanic is printed with the same words on every card that
carries it. That is what makes this tractable, and it is the whole design.

A fix aims at **every card sharing a characteristic**, not at the specific card
that exposed the gap. The card named in a bug report is a symptom, never the
specification. Implement "exile a card from your hand as an additional cost",
not "Solitude"; implement the `Investigate` keyword action once, and every
current and future card that says the word gets it for free.

**Banned, without exception:**

- A card-name-to-behaviour dictionary. Rows keyed by card name in
  `EFFECTS` / `TRIGGER_EFFECTS` / `ACTIVATED_EFFECTS` - read each registry's own
  docstring in `machines/effects.py`. Most of their old rows are **gone on
  purpose**, now read by a parser instead. Never push that count back up.
- Any `if card.name == "..."` or name-set membership test that gates behaviour.
- A regex written so tightly around one card's exact printed sentence that a
  differently-worded card with the same mechanic misses it.

**Prove generality, do not assert it.** A wave that closes a mechanic
demonstrates it on a card that was *not* the reported one and is *not* in the
deck pool - added with `scripts/add_card.py` as a genuine Scryfall printing, and
played through the engine in a scenario test. Pick one whose wording differs
(different cost shape, zone, count or rider) so the test exercises the parser
rather than re-confirming the one sentence it was built against.

**The narrow, documented exception.** A handful of cards genuinely resist
templating - Emrakul, the Promised End's "control your opponent's next turn" is
the canonical example. Those are allowed as *documented* special cases: argued
explicitly, with the reason it resists templating, and a row in
`docs/engine-coverage.md`. "It was quicker this way" is not a reason. Failing
closed with a notice plus a coverage row is the honest alternative to a
hardcode, and is always the better of the two.

`machines/abilities.py` parses `{T}: Add ...` from oracle text, covering mana
abilities only. Triggered, activated, and static abilities are read by the
dispatchers in `machines/effects.py` (`effect_for`, `trigger_effect_for`,
`activated_effect_for`) and their parsers.

`scripts/sweep_pool.py` is how this is measured: `--effects` sorts every clause
into handled / notice / static_unaudited / **silent**, and `--keywords` lists
keywords that parse but that no machine executes. Silent falling while notice
climbs to meet it is not progress.

## No mocks. Ever.

Mocks, stubs, fakes, and hand-written card data are **banned in this project**.
Every test builds a real board state and plays it through the engine using real
Scryfall printings from `tests/fixtures/cards/`. A mocked test proves the mock
behaves, not that the rules do.

Add a card with `uv run python scripts/add_card.py "Card Name"`. If you find
yourself wanting to fake something, the thing you want to fake is the thing that
needs building.

### Decklists must be real too

A deck in a test is a **real tournament decklist**, pulled with
`statistics_decks(format="modern", date_from="...", include_cards="full")`, with
its pilot and tournament date recorded in the test.

**Never build a decklist out of `statistics_archetypes` `core_cards`.** That is
an aggregate across many decks over a time window - it is not a deck anybody
registered, the counts are averages, and **the window can predate a ban**. It
listed Phlage, Titan of Fire's Fury in boros aggro at 90% inclusion; Phlage is
banned in Modern. Grief is banned too and appears in older aggregates. An
assembled-from-averages decklist is a mock wearing real card names.

**Verify legality before using any list**: `resolve_cards(names=[...],
format="modern", fields="legality")`. The bans move, so check, do not remember.
`Deck.check_legality` then enforces the 60/15 and 4-copy rules on top.

Rigged libraries are fine and expected - stacking a known card on top to reach a
specific turn is staging, not mocking, as long as every card is a real printing
from a real list.

## Scenario tests - read `docs/scenario-tests.md` before writing tests

Scenario tests set up a real board state and play it through the model. They are
the primary way this project tests mechanics, and they target **one mechanic per
file, with the corner cases as the bulk of the file**.

When asked to cover a mechanic, an edge case, or a rules interaction, write a
scenario test, not a unit test. Unit tests in `tests/test_*.py` cover a single
machine in isolation and are already in place; new rules coverage belongs in
`tests/scenarios/`.

### Every scenario proves it round-trips and replays

`tests/scenarios/conftest.py`'s `pytest_pyfunc_call` runs every scenario test
twice: once live, then again with any `harness.checkpoint`ed `Game` swapped
for a decode of its own initial snapshot, and asserts the two final games are
byte-identical, as well as that every checkpointed game dumps, decodes, and
re-dumps identically. This is what actually backs the two guarantees above -
a decode that merely doesn't crash is not the same claim as a decode that
replays to the same game. Nothing opts in: a new scenario gets this for free.
`MTG_SCENARIO_REPLAY=0` drops the replay half only (the round-trip dump/
decode/re-dump check still runs). A scenario that cannot replay is an engine
defect, not a test to exempt - the only exemption is `@pytest.mark.no_replay`,
for an assertion about CPython object identity (`id(x) == id(y)`), which a
JSON decode can never reproduce and which is not game state to begin with.

```python
scenario = Scenario().player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"]).build()
scenario.start_at(Step.PRECOMBAT_MAIN)
(mountain,) = scenario.untapped_sources("Mountain")
bolt = scenario.cast_and_resolve("Lightning Bolt", mountain)
assert bolt.zone is Zone.GRAVEYARD
```

Card data is always a real Scryfall printing from `tests/fixtures/cards/`. Never
hand-write card json. Add a card with:

```sh
uv run python scripts/add_card.py "Card Name"
```

If a scenario cannot be expressed because the model is missing a rule, write the
test as `xfail` with a reason and say so. Do not reshape the scenario until it
passes.

## Conventions

- Python 3.13, ruff for lint and format, pytest for tests, config in
  `pyproject.toml`.
- `mise run test`, `mise run lint`, `mise run fmt`.
- `Card` is the immutable Scryfall printing. Anything mutable in a game belongs
  on `CardState` or above - do not add game state to `Card`.
- Legality is clamped to standard, pioneer, and modern. Print, market, and
  collector fields are deliberately absent from `Card`.

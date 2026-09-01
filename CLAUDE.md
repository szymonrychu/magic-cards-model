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
  `effects.py` is what a spell does when it resolves.
- `tests/scenarios/` - scenario tests. See below.

## Two registries that need feeding

- **`machines/effects.py`** keys a spell's effect by card name. A card with no
  entry resolves and does nothing. Adding a card to the test pool does not teach
  the model its text - add the effect too, or the scenario passes for the wrong
  reason.
- **`machines/abilities.py`** parses `{T}: Add ...` from oracle text, covering
  mana abilities only. Triggered, activated, and static abilities are not parsed.

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

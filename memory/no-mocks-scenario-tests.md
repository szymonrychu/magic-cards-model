---
name: no-mocks-scenario-tests
description: Mocks are banned in magic-cards-model; all tests are scenario tests using real Scryfall card data
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6a8b5028-7888-40c6-89b6-15ddd250140a
  modified: 2026-08-26T21:03:26.606Z
---

No mocks, stubs, or fakes are allowed in magic-cards-model. Every test is a
scenario test that builds a real board state and plays it through the engine,
using real Scryfall printings from `tests/fixtures/cards/`. Hand-written card
data is banned too - add cards with `scripts/add_card.py`.

**Why:** the project is a full MTG rules engine, and a mocked test proves the
mock behaves, not that the rules do. The interesting bugs live in real cards
interacting at real points in the turn, which a mock cannot reproduce.

Decklists count as data too: use real tournament lists from
`statistics_decks`, never a list assembled from `statistics_archetypes`
`core_cards`. That aggregate averages many decks over a window that can predate
a ban - it listed the banned Phlage, Titan of Fire's Fury at 90% inclusion in
boros aggro. An assembled-from-averages decklist is a mock wearing real card
names. Always confirm legality with `resolve_cards(..., fields="legality")`.

**How to apply:** write tests in `tests/scenarios/` using the `Scenario` harness.
One mechanic per file, corner cases as the bulk of it. Put this instruction in
every subagent prompt that writes tests here. If a mechanic is not modelled yet,
write the test as `@pytest.mark.xfail(strict=True)` with a reason rather than
reshaping it until it passes. Rigged libraries are staging, not mocking - fine,
as long as every card is a real printing from a real list. See
[[magic-cards-model-engine-goal]] and [[never-recall-mtg-rules-from-memory]].

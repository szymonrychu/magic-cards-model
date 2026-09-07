"""Scenario: The Darkness Crystal's "{4}{B}{B}, {T}: Put target creature
card exiled with The Darkness Crystal onto the battlefield tapped under your
control with two additional +1/+1 counters on it."

"Exiled with `<name>`" (CR 201.5's self-reference by printed name) is a real,
checked target (CR 115.1) - not a definite reference like Ugin's Labyrinth's
"the exiled card" - so `machines/targeting.py`'s `TargetRequirement.exiled_
with_source` is what makes "target ... card exiled with `<this>`" a legal
target at all, reusing `ExileMarker.IMPRINTED`/`ExileAnnotation.linked_
permanent_id`, the same link `_parse_imprint_clause` (Ugin's Labyrinth)
already writes.

This card's own *second* paragraph - "If a nontoken creature an opponent
controls would die, instead exile it and you gain 2 life" - is a replacement
effect `docs/engine-coverage.md`'s "Which replacement effects exist at all"
row already records as unbuilt (it mixes an exile this engine can do with a
life gain, the same gap Kalitas, Traitor of Ghet's own row describes). That
paragraph is untouched here (CR 113.3, paragraph-atomic) - this file exiles a
creature card "with" The Darkness Crystal directly, by setting `exile_
annotation` in scenario setup, the same real-state staging `test_imprint.py`
uses to test one paragraph's target without depending on another paragraph
this engine does not build yet.

Every rule cited here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 201.5** - "if an object's text uses its own name, it is referring to
  that particular object."
- **CR 406.4** - the annotated-exile-pile shape this reuses.
- **CR 122.6** - counters an effect adds once a permanent is already on the
  battlefield.
- **CR 608.2b** - a target rechecked at resolution.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter, ExileAnnotation, ExileMarker

from .harness import Scenario


def _scenario() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["The Darkness Crystal"],
            battlefield=["Swamp"] * 10,
        )
        .player("bob", graveyard=["Goblin Guide"])
    )


def _exile_from_graveyard_with(scenario: Scenario, card_state, linked_to) -> None:
    """Real engine state, staged by hand: the card is really in exile, really
    annotated `IMPRINTED`, and really linked to `linked_to`'s id - the same
    shape `machines/effects.py`'s own imprint clause produces, only written
    directly here because the card's own exiling paragraph is unbuilt (see
    the module docstring)."""
    owner = scenario.player(card_state.owner or "bob")
    owner.cards_in(Zone.GRAVEYARD).remove(card_state)
    # `CardState.move_to` mints the card's own `zone_change_stamp` with no
    # `Game` method's `_id_allocator_scope` open around it here.
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        card_state.move_to(Zone.EXILE)
    card_state.exile_annotation = ExileAnnotation(
        marker=ExileMarker.IMPRINTED, owner=card_state.owner, linked_permanent_id=linked_to.id
    )
    scenario.game.exile.append(card_state)


def test_putting_the_exiled_creature_onto_the_battlefield_tapped_with_two_counters():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    crystal = scenario.cast_and_resolve("The Darkness Crystal", *sources)

    goblin = scenario.find("Goblin Guide", Zone.GRAVEYARD, "bob")
    _exile_from_graveyard_with(scenario, goblin, crystal)

    activation_sources = scenario.untapped_sources(
        "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"
    )
    scenario.activate(crystal, *activation_sources, targets=[goblin])
    scenario.resolve_top()

    assert goblin.zone is Zone.BATTLEFIELD
    assert goblin.controller == "alice"
    assert goblin.tapped
    assert goblin.counters[Counter.PLUS_ONE] == 2


def test_a_creature_card_exiled_with_a_different_permanent_is_not_a_legal_target():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    crystal = scenario.cast_and_resolve("The Darkness Crystal", *sources)

    goblin = scenario.find("Goblin Guide", Zone.GRAVEYARD, "bob")
    # Linked to a made-up id, standing in for "some other permanent" -
    # `linked_permanent_id`'s own docstring notes a stale link (nothing on
    # the battlefield answering to the id) reads the same way an id "with a
    # different permanent" would: no live permanent claims the card.
    _exile_from_graveyard_with(scenario, goblin, crystal)
    goblin.exile_annotation = goblin.exile_annotation.model_copy(
        update={"linked_permanent_id": None}
    )

    activation_sources = scenario.untapped_sources(
        "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"
    )
    with pytest.raises(ValueError):
        scenario.activate(crystal, *activation_sources, targets=[goblin])


def test_a_creature_card_still_in_the_graveyard_is_not_a_legal_target():
    """The link alone is not enough - CR 115.2's zone still has to match, so
    a creature card exiled with a *different* card and only coincidentally
    named the same is not confused with one still sitting in a graveyard."""
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    crystal = scenario.cast_and_resolve("The Darkness Crystal", *sources)

    goblin = scenario.find("Goblin Guide", Zone.GRAVEYARD, "bob")

    activation_sources = scenario.untapped_sources(
        "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"
    )
    with pytest.raises(ValueError):
        scenario.activate(crystal, *activation_sources, targets=[goblin])

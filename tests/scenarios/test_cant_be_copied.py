"""A spell that can't be copied, and Choreographed Sparks' two copy modes.

CR 113.6g, read whole with `mise run rules:find` in the session that wrote
this file: "An object's ability that states it can't be countered or can't
be copied functions on the stack." Choreographed Sparks and See Double (the
off-pool proof) each print "This spell can't be copied." - so storm, a
"copy that spell" trigger, or another copy spell aimed at them makes no copy
at all (CR 707.10: to copy a spell "means to put a copy of it onto the
stack").

Choreographed Sparks: "Choose one or both - • Copy target instant or sorcery
spell you control. You may choose new targets for the copy. • Copy target
creature spell you control. The copy gains haste and 'At the beginning of
the end step, sacrifice this token.'" CR 707.10f: "Some effects copy a
permanent spell. As that copy resolves, it ceases being a copy of a spell
and becomes a token permanent." CR 400.7b's permanent-spell exception keeps
what the copy gained as it becomes that token. No other printing carries the
"The copy gains ..." rider (searched on Scryfall, `o:"copy gains"`), so the
rider is proven on Sparks alone; the reader takes any keyword list and any
quoted ability rather than this one sentence.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting_restrictions import cannot_be_copied
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

SPARKS = "Choreographed Sparks"


def board(*hand: str, battlefield: tuple[str, ...] = ()) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            library=["Mountain"] * 5,
            battlefield=[*battlefield, *["Mountain"] * 6, "Forest", "Forest"],
        )
        .player("bob", life=20, hand=["Lightning Bolt"], battlefield=["Grizzly Bears", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def resolve_everything(scenario: PlayedScenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def named_on_stack(scenario: PlayedScenario, name: str) -> list:
    return [item for item in scenario.game.stack if getattr(item, "name", "") == name]


def test_the_static_is_read_off_the_printing():
    assert cannot_be_copied(card(SPARKS))
    assert cannot_be_copied(card("See Double"))
    assert not cannot_be_copied(card("Lightning Bolt"))


# -- mode 1: copy target instant or sorcery spell you control ------------------------


def test_sparks_copies_your_own_bolt():
    scenario = board(SPARKS, "Lightning Bolt")
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    casting = scenario.cast(SPARKS)
    casting.choose_modes([1])
    casting.choose_targets([bolt])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    resolve_everything(scenario)
    assert scenario.player("bob").life == 14


def test_sparks_copy_may_choose_new_targets():
    scenario = board(SPARKS, "Lightning Bolt")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_take_the_may(True, username="alice", source=SPARKS)
    scenario.will_choose_targets(bears, username="alice", source=SPARKS)
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    casting = scenario.cast(SPARKS)
    casting.choose_modes([1])
    casting.choose_targets([bolt])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    resolve_everything(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_sparks_cannot_target_an_opponents_spell():
    scenario = board(SPARKS)
    scenario.pass_priority("alice")
    (bobs_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bobs_mountain, username="bob", targets=["alice"]
    )
    casting = scenario.cast(SPARKS, username="alice")
    casting.choose_modes([1])
    with pytest.raises(ValueError):
        casting.choose_targets([bolt])


# -- mode 2: copy target creature spell you control, with haste and a sacrifice -------


def cast_bears_then_sparks(scenario: PlayedScenario, modes: list[int], targets: list):
    casting = scenario.cast(SPARKS)
    casting.choose_modes(modes)
    casting.choose_targets(targets)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    return scenario.put_on_stack(casting)


def test_sparks_copies_a_creature_spell_into_a_hasty_token():
    scenario = board(SPARKS, "Grizzly Bears")
    bears = scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    cast_bears_then_sparks(scenario, [2], [bears])
    resolve_everything(scenario)
    tokens = [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if permanent.name == "Grizzly Bears" and permanent.token
    ]
    assert len(tokens) == 1
    token = tokens[0]
    assert scenario.can_attack(token)


def test_the_hasty_token_is_sacrificed_at_the_end_step():
    scenario = board(SPARKS, "Grizzly Bears")
    bears = scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    cast_bears_then_sparks(scenario, [2], [bears])
    resolve_everything(scenario)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    resolve_everything(scenario)
    names = [p.name for p in scenario.game.permanents_controlled_by("alice") if p.token]
    assert names == []
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_both_modes_copy_an_instant_and_a_creature_spell():
    scenario = board(SPARKS, "Grizzly Bears", "Lightning Bolt")
    bears = scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    cast_bears_then_sparks(scenario, [1, 2], [bolt, bears])
    resolve_everything(scenario)
    assert scenario.player("bob").life == 14
    assert len([p for p in scenario.game.battlefield if p.name == "Grizzly Bears" and p.token]) == 1


# -- "This spell can't be copied." -----------------------------------------------------


def test_storm_cannot_copy_sparks():
    """Under Prismari, the Inspiration, Sparks has storm; its storm trigger
    resolves and makes nothing."""
    scenario = board("Lightning Bolt", SPARKS, battlefield=("Prismari, the Inspiration",))
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.resolve_top()  # Bolt's own storm trigger (nothing before it)
    casting = scenario.cast(SPARKS)
    casting.choose_modes([1])
    casting.choose_targets([bolt])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Sparks' storm trigger: one earlier spell, no copy
    assert len(named_on_stack(scenario, SPARKS)) == 1


def test_a_copy_that_spell_trigger_cannot_copy_see_double():
    """Mica sacrifices the artifact - the cost is paid - but See Double makes
    no copy."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["See Double", "Lightning Bolt"],
            battlefield=["Mica, Reader of Ruins", "Ornithopter", "Island", "Island", "Island"]
            + ["Island", "Mountain"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.will_take_the_may(False, username="alice", source="Mica, Reader of Ruins")
    scenario.resolve_top()  # Mica's trigger for the Bolt: declined
    scenario.will_take_the_may(True, username="alice", source="Mica, Reader of Ruins")
    casting = scenario.cast("See Double")
    casting.choose_modes([1])
    casting.choose_targets([bolt])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 4))
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Mica's trigger for See Double
    assert len(named_on_stack(scenario, "See Double")) == 1
    resolve_everything(scenario)
    assert scenario.player("bob").life == 14  # See Double itself still copies the Bolt


def test_a_copy_spell_aimed_at_sparks_makes_nothing():
    """A second Sparks targeting the first: a legal target (an instant spell
    you control), and no copy is made."""
    scenario = board(SPARKS, SPARKS, "Lightning Bolt")
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    first = cast_bears_then_sparks(scenario, [1], [bolt])
    cast_bears_then_sparks(scenario, [1], [first])
    scenario.resolve_top()  # the second Sparks
    assert len(named_on_stack(scenario, SPARKS)) == 1

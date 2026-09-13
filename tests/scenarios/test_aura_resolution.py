"""A resolving Aura spell attaching to what it targeted (CR 608.3c).

CR 608.3c: "If the object that's resolving is an Aura spell, it becomes a
permanent and is put onto the battlefield under the control of the spell's
controller attached to the player or object it was targeting." Nothing is
chosen at resolution - CR 608.3b already rechecked the announced target's
legality, and this attaches to whichever one is still there.

Before this file, `Game.resolve_top` ran every permanent spell through
`enter_the_battlefield` identically. An Aura landed on the battlefield with no
attachment at all, and `machines/keywords.aura_state_based_actions` correctly
put it straight into its owner's graveyard a moment later (CR 704.5m) - the
state-based action was right, the missing step was CR 608.3c's attach.
Casting Utopia Sprawl onto your own Forest lost the card entirely, which is
what this file is a regression test for.

`test_enchant.py` covers what an Aura may target and be attached to (CR 702.5).
`test_aura_attachment.py` covers CR 704.5m against an attachment made by hand.
This file is the missing middle: casting and resolving a real Aura spell, the
whole way from the stack to a legal attachment (or, correctly, to a
graveyard).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def test_hyena_umbra_attaches_to_the_creature_it_targeted():
    """The happy path: `Enchant creature`, cast and resolved for real."""
    scenario = (
        Scenario()
        .player("alice", hand=["Hyena Umbra"], battlefield=["Grizzly Bears", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    umbra = scenario.cast_and_resolve("Hyena Umbra", plains, targets=[bears])

    assert umbra.zone is Zone.BATTLEFIELD
    assert umbra.attached_to == bears.id
    assert scenario.state_based_actions() == [], "a legally attached Aura survives the check"


def test_utopia_sprawl_attaches_to_the_forest_it_targeted():
    """The reported defect: Utopia Sprawl cast on the caster's own Forest.

    It used to resolve into the graveyard - `enter_the_battlefield` had no way
    to attach it, so CR 704.5m destroyed it the moment state-based actions were
    next checked. It now attaches and stays on the battlefield.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")

    sprawl = scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])

    assert sprawl.zone is Zone.BATTLEFIELD
    assert sprawl.attached_to == forest.id
    assert scenario.state_based_actions() == []
    # Not destroyed by the SBA check that used to catch it unattached.
    assert sprawl.zone is Zone.BATTLEFIELD


def test_utopia_sprawl_adds_the_chosen_color_when_the_forest_is_tapped():
    """CR 508.1b's whole point: enchanted Forest taps for an extra mana of the
    chosen color. Attaching correctly is necessary but not sufficient - this is
    the assertion that would pass for the wrong reason if it only checked
    `attached_to` and stopped there.

    The chosen color is blue, deliberately not green - Utopia Sprawl sits on a
    Forest, so "add {G}" would make the pool go to 2 with the CR 614.12a choice
    still never made, and the symptom would pass for the wrong reason. Asserting
    on both colors separately is what catches that: a green-defaulting bug still
    gets the total right but the blue count wrong.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.will_choose(Color.BLUE.value, source="Utopia Sprawl")
    scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])

    pool_before = dict(scenario.player("alice").mana_pool.floating)
    scenario.activate(forest)

    pool_after = scenario.player("alice").mana_pool.floating
    assert pool_after.get(Color.GREEN, 0) == pool_before.get(Color.GREEN, 0) + 1, (
        "the Forest's own {G}"
    )
    assert pool_after.get(Color.BLUE, 0) == pool_before.get(Color.BLUE, 0) + 1, (
        "Utopia Sprawl's chosen color, not the Forest's own"
    )


def test_utopia_sprawls_bonus_mana_pays_for_a_spell():
    """Not just an inspect-the-pool assertion: the bonus mana has to be able to
    pay a real cost, or a fix that only wrote to the wrong pool during a cast
    would still pass a pool-only check.

    CR 605.4a resolves Utopia Sprawl's triggered mana ability the moment the
    Forest's own mana ability does, off the stack, so tapping the Forest ahead
    of casting leaves both mana floating in `player.mana_pool` (CR 106.4), and
    `CostPayment.begin` opens the later payment's pool as a copy of it. Tapping
    it during the payment instead puts both into that payment's pool
    (`scenarios/test_triggered_mana_abilities.py`).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl", "Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.will_choose(Color.BLUE.value, source="Utopia Sprawl")
    scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])

    # Tap the enchanted Forest *before* casting anything - not as part of
    # Grizzly Bears' own payment. Its trigger has already resolved (CR 605.4a).
    scenario.activate(forest)
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1, Color.BLUE: 1}

    # Grizzly Bears costs {1}{G}: the floating {G} pays the colored symbol,
    # the floating {U} pays the generic one - no further land is tapped.
    bears = scenario.cast_and_resolve("Grizzly Bears")

    assert bears.zone is Zone.BATTLEFIELD


def test_pariah_attaches_to_the_creature_it_targeted():
    """The third Aura in scope: `Enchant creature`, same generic path."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pariah"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")

    pariah = scenario.cast_and_resolve("Pariah", *sources, targets=[bears])

    assert pariah.zone is Zone.BATTLEFIELD
    assert pariah.attached_to == bears.id


def test_an_aura_may_be_cast_at_a_creature_its_controller_does_not_control():
    """CR 303.4e: an Aura's controller and the enchanted permanent's controller
    need not be the same. Alice's Umbra resolving onto bob's bear is legal, and
    it attaches to bob's creature while staying under alice's control.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hyena Umbra"], battlefield=["Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    umbra = scenario.cast_and_resolve("Hyena Umbra", plains, targets=[theirs])

    assert umbra.zone is Zone.BATTLEFIELD
    assert umbra.controller == "alice"
    assert umbra.attached_to == theirs.id


def test_an_aura_fizzles_if_its_target_leaves_before_it_resolves():
    """CR 608.3b, 608.2b: a target gone by resolution stops the whole spell.

    Bob exiles his own bear with Swords to Plowshares in response to Hyena
    Umbra targeting it. The Umbra never resolves at all - it fizzles straight
    to alice's graveyard rather than entering the battlefield unattached.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hyena Umbra"], battlefield=["Plains"])
        .player("bob", hand=["Swords to Plowshares"], battlefield=["Grizzly Bears", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (alice_plains,) = scenario.untapped_sources("Plains", username="alice")
    (bob_plains,) = scenario.untapped_sources("Plains", username="bob")

    umbra = scenario.cast_onto_stack("Hyena Umbra", alice_plains, username="alice", targets=[bears])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Swords to Plowshares", bob_plains, username="bob", targets=[bears])
    scenario.pass_until_resolved()  # Swords resolves; the bear is exiled

    assert bears.zone is Zone.EXILE
    assert scenario.game.spell_fizzles(umbra)

    scenario.pass_until_resolved()  # the Umbra is removed from the stack unresolved

    assert umbra.zone is Zone.GRAVEYARD
    assert umbra.id in scenario.game.fizzled
    assert "Hyena Umbra" not in scenario.battlefield_names()


def test_an_aura_is_binned_once_its_enchanted_creature_dies():
    """The loop CR 608.3c and CR 704.5m close together: attach on resolution,
    then the state-based action polices it once the host is gone - now
    exercised end to end from a real cast rather than a hand-attach.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hyena Umbra"], battlefield=["Grizzly Bears", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    umbra = scenario.cast_and_resolve("Hyena Umbra", plains, targets=[bears])
    assert umbra.zone is Zone.BATTLEFIELD

    scenario.game.destroy(bears)
    scenario.state_based_actions()

    assert umbra.zone is Zone.GRAVEYARD
    assert "Hyena Umbra" not in scenario.battlefield_names()

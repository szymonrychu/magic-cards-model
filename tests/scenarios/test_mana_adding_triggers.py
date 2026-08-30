""" "Whenever [something] is tapped for mana, add[s] an additional ..." (CR
605.1b, CR 106.12a).

CR 605.1b: "A triggered ability is a mana ability if it meets all of the
following criteria: it doesn't require a target ..., it triggers from the
activation or resolution of an activated mana ability or from mana being
added to a player's mana pool, ... and it could put mana into a player's mana
pool when it resolves." CR 106.12a: "An ability that triggers whenever a
permanent 'is tapped for mana' ... triggers whenever such a mana ability
resolves and produces mana."

Before this file, three pool cards printed exactly this shape - Utopia
Sprawl, Leyline of Abundance, Badgermole Cub - and none of them added
anything: `machines/effects.py` had no `TRIGGER_EFFECTS` row for the event and
no clause parser read "adds an additional ..." at all, so the trigger reached
the stack (`test_tap_for_mana_triggers.py`) and resolved doing nothing.

`_parse_mana_adding_trigger` is a text-template parser reached through
`trigger_effect_for`'s ordinary fallback - not a per-card row - so Leyline of
Abundance and Badgermole Cub prove the fix off the same code Utopia Sprawl
does, with no chosen color involved at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects import TRIGGER_EFFECTS
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def test_the_mana_clause_is_not_a_per_card_registry_row():
    """A `TRIGGER_EFFECTS` row keyed by one of these three card names would
    make Utopia Sprawl's own reported defect look fixed while Leyline of
    Abundance and Badgermole Cub stayed silent - the same shadowing
    `test_registry_is_minimal.py` polices for other shapes in this codebase.
    Nothing here should key on `TriggerEvent.TAPPED_FOR_MANA` at all; the whole
    effect is `_parse_mana_adding_trigger`'s fallback.
    """
    keyed_cards = {
        name for (name, event, _marker) in TRIGGER_EFFECTS if event is TriggerEvent.TAPPED_FOR_MANA
    }
    assert keyed_cards == set()


def test_leyline_of_abundance_adds_an_extra_green_when_a_creature_is_tapped():
    """The standalone activation path (CR 605.3b): Llanowar Elves taps itself
    for its own {T}: Add {G}, and Leyline of Abundance's own trigger resolves
    off the stack and adds a second green - no chosen color anywhere in this
    card's text.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leyline of Abundance", "Llanowar Elves"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")

    scenario.activate(elves)
    scenario.pass_until_resolved()

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_badgermole_cub_adds_extra_mana_left_floating_after_it_pays_for_a_spell():
    """`CostPayment.tap_for_mana`'s call site: tapping a creature to help pay
    for casting a second one. The trigger goes on the stack *above* the spell
    (`test_tap_for_mana_triggers.py`) and so resolves only after the spell's
    own cost is already paid in full - CR 605.4a's stackless resolution is a
    documented simplification this engine does not implement
    (`docs/engine-coverage.md`) - so the bonus mana cannot help pay for the
    very cast that produced it. It still has to go somewhere real:
    `player.mana_pool`, floating, once the trigger itself resolves.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Llanowar Elves"],
            battlefield=["Badgermole Cub", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tapper = scenario.creature("Llanowar Elves", "alice")

    scenario.cast_onto_stack("Llanowar Elves", tapper)
    assert scenario.stack_names() == ["Llanowar Elves", "Badgermole Cub's triggered ability"]

    new_elf = scenario.resolve_top()  # Badgermole Cub's trigger
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}

    new_elf = scenario.resolve_top()  # Llanowar Elves itself
    assert new_elf.zone is Zone.BATTLEFIELD


def test_an_opponents_creature_tapped_for_mana_never_reaches_badgermole_cub():
    """ "you tap" excludes the opponent's own taps (CR 106.12a's trigger still
    has to fire in the first place; `test_tap_for_mana_triggers.py` already
    covers that it does not). Restated here as a resolution-level guard so a
    future change to the event-matching side cannot silently start crediting
    the wrong player's pool.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Badgermole Cub"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()  # into bob's turn, past his summoning sickness
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.activate(elves, username="bob")

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.total == 0
    assert scenario.player("bob").mana_pool.floating == {Color.GREEN: 1}


def test_utopia_sprawls_bonus_mana_goes_to_the_enchanted_lands_controller():
    """CR 303.4e: an Aura's controller and the permanent it enchants need not
    be the same player. Alice's Utopia Sprawl enchants bob's Forest, so
    "its controller adds an additional mana" means *bob*, not alice - the
    identical case the reported defect never separated, since the original
    report had Utopia Sprawl on the caster's own land.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (alice_forest,) = scenario.untapped_sources("Forest", username="alice")
    (bobs_forest,) = scenario.untapped_sources("Forest", username="bob")
    scenario.will_choose(Color.BLUE.value, source="Utopia Sprawl")

    sprawl = scenario.cast_and_resolve(
        "Utopia Sprawl", alice_forest, username="alice", targets=[bobs_forest]
    )
    assert sprawl.attached_to == bobs_forest.id
    assert sprawl.controller == "alice"

    scenario.pass_priority("alice")
    scenario.activate(bobs_forest, username="bob")
    scenario.pass_until_resolved()

    assert scenario.player("alice").mana_pool.total == 0
    assert scenario.player("bob").mana_pool.floating == {Color.GREEN: 1, Color.BLUE: 1}

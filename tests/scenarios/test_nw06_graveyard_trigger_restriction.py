"""A trigger restricted to where its source is: "This ability triggers only if
<condition>." (Quakebringer).

Quakebringer: "At the beginning of your upkeep, Quakebringer deals 2 damage
to each opponent. This ability triggers only if Quakebringer is on the
battlefield or if Quakebringer is in your graveyard and you control a Giant."

Two rules meet here. CR 113.6b: "An ability that states which zones it
functions in functions only from those zones." - the restriction names the
battlefield and the graveyard, so the ability functions from both (and from
no other zone). And the restriction is checked as the trigger event occurs,
the way CR 603.2h's "This ability triggers only if its source's controller has
not yet taken the indicated action that turn" and CR 702.169c's "This ability
triggers only if this Case is solved" are: unlike CR 603.4's intervening "if"
("this rule only applies to an "if" that immediately follows a trigger
condition"), it is not asked again on resolution.

`machines/abilities.py` strips the sentence into `TriggeredAbility.
triggers_only_if`; `machines/triggers/collect.py` reads the zones it names and
gates the trigger on `Game.condition_holds`. Quakebringer is the only
Modern/Pioneer/Standard printing with this sentence (an oracle-wide search for
"triggers only if" returns it alone), so the reader is proven on its own
printing's corner cases; see the dated MEMORY.md line.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.triggers import triggered_abilities_of
from tests.cards import card
from tests.scenarios.harness import Scenario

TRIGGER = "Quakebringer's triggered ability"


def _upkeep(alice: dict, bob: dict | None = None):
    scenario = Scenario().player("alice", library=["Forest"], **alice)
    scenario = scenario.player("bob", library=["Forest"], **(bob or {})).build()
    scenario.advance()  # untap -> upkeep
    assert scenario.step is Step.UPKEEP
    return scenario


def test_the_restriction_is_read_off_the_effect():
    (upkeep,) = [
        ability
        for ability in triggered_abilities_of(card("Quakebringer"))
        if "upkeep" in ability.condition
    ]
    assert upkeep.effect == "Quakebringer deals 2 damage to each opponent."
    assert upkeep.triggers_only_if == (
        "Quakebringer is on the battlefield or if Quakebringer is in your graveyard "
        "and you control a Giant"
    )
    assert len(parse_abilities(card("Quakebringer"))) >= 2


def test_on_the_battlefield_it_triggers_and_deals_damage():
    scenario = _upkeep({"battlefield": ["Quakebringer"]})
    bob = scenario.player("bob")

    assert scenario.stack_names() == [TRIGGER]
    scenario.pass_until_resolved()

    assert bob.life == 18


def test_in_the_graveyard_with_a_giant_it_triggers():
    scenario = _upkeep({"graveyard": ["Quakebringer"], "battlefield": ["Craven Hulk"]})
    bob = scenario.player("bob")

    assert scenario.stack_names() == [TRIGGER]
    scenario.pass_until_resolved()

    assert bob.life == 18


def test_in_the_graveyard_without_a_giant_it_does_not_trigger():
    scenario = _upkeep({"graveyard": ["Quakebringer"], "battlefield": ["Grizzly Bears"]})

    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20


def test_an_opponents_giant_does_not_count():
    """ "you control a Giant" - bob's Giant is not alice's."""
    scenario = _upkeep({"graveyard": ["Quakebringer"]}, {"battlefield": ["Craven Hulk"]})

    assert scenario.stack_names() == []


def test_in_exile_with_a_giant_it_does_not_trigger():
    """CR 113.6b: the ability names the battlefield and the graveyard only."""
    scenario = _upkeep({"exile": ["Quakebringer"], "battlefield": ["Craven Hulk"]})

    assert scenario.stack_names() == []


def test_in_hand_with_a_giant_it_does_not_trigger():
    scenario = _upkeep({"hand": ["Quakebringer"], "battlefield": ["Craven Hulk"]})

    assert scenario.stack_names() == []


def test_it_does_not_trigger_in_an_opponents_upkeep():
    scenario = (
        Scenario()
        .player("bob", library=["Forest"])
        .player("alice", library=["Forest"], battlefield=["Quakebringer"])
        .build()
    )
    scenario.advance()

    assert scenario.stack_names() == []


def test_the_restriction_is_not_checked_again_on_resolution():
    """Not an intervening "if" (CR 603.4): losing the Giant after it triggered
    does not stop the ability from resolving."""
    scenario = _upkeep({"graveyard": ["Quakebringer"], "battlefield": ["Craven Hulk"]})
    bob = scenario.player("bob")
    assert scenario.stack_names() == [TRIGGER]

    scenario.game.destroy(scenario.creature("Craven Hulk", "alice"))
    scenario.pass_until_resolved()

    assert bob.life == 18


def test_the_giant_quakebringer_on_the_battlefield_counts_for_another_in_the_graveyard():
    """A second Quakebringer is itself a Giant: both trigger, 4 damage."""
    scenario = _upkeep({"graveyard": ["Quakebringer"], "battlefield": ["Quakebringer"]})
    bob = scenario.player("bob")

    assert scenario.stack_names() == [TRIGGER, TRIGGER]
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bob.life == 16

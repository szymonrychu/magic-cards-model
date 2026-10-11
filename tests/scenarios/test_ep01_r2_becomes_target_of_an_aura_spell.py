"""Scenario: Brine Comber // Brinebound Gift (a listed disturb card) -
"Whenever this creature enters or becomes the target of an Aura spell, create
a 1/1 white Spirit creature token with flying." and its back face's
"Whenever this Aura enters or enchanted creature becomes the target of an
Aura spell, ...".

CR 115.1/CR 303.4a: an Aura spell targets the object it will enchant as it is
cast, so casting one at the creature is the trigger event; a non-Aura spell
targeting it is not. CR 603.1b: the enters half is a trigger condition of its
own.

Wild Defiance (Modern, not a listed card and in no api deck): "Whenever a
creature you control becomes the target of an instant or sorcery spell, that
creature gets +3/+3 until end of turn." - the second printing of the quality
read off the targeting spell: an Aura spell is not an instant or sorcery.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

COMBER = "Brine Comber"


def _board(alice: dict, bob: dict | None = None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", **{"library": ["Island"] * 10, **alice})
        .player("bob", **{"library": ["Island"] * 10, **(bob or {})})
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _spirits(scenario):
    return [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and "Spirit" in state.subtypes
    ]


def _cast_at(scenario, name, target, *lands):
    casting = scenario.cast(name, targets=[target])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*lands))
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()


def test_an_aura_spell_targeting_brine_comber_makes_a_spirit():
    scenario = _board({"battlefield": [COMBER, "Plains", "Plains"], "hand": ["Pacifism"]})
    comber = scenario.creature(COMBER)

    _cast_at(scenario, "Pacifism", comber, "Plains", "Plains")

    assert scenario.stack_names()[-1] == f"{COMBER}'s triggered ability"
    scenario.resolve_top()
    assert len(_spirits(scenario)) == 1


def test_a_non_aura_spell_targeting_brine_comber_makes_nothing():
    scenario = _board({"battlefield": [COMBER, "Forest"], "hand": ["Giant Growth"]})
    comber = scenario.creature(COMBER)

    _cast_at(scenario, "Giant Growth", comber, "Forest")

    assert scenario.stack_names() == ["Giant Growth"]


def test_an_aura_spell_at_the_creature_brinebound_gift_enchants_makes_a_spirit():
    scenario = _board(
        {
            "graveyard": [COMBER],
            "battlefield": ["Plains", "Island", "Plains", "Plains", "Grizzly Bears"],
            "hand": ["Pacifism"],
        }
    )
    bears = scenario.creature("Grizzly Bears")
    casting = scenario.cast(COMBER, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Disturb")
    casting.choose_targets([bears])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Island"))
    scenario.put_on_stack(casting)
    gift = scenario.resolve_top()
    assert gift.name == "Brinebound Gift"
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # the enters half
    assert len(_spirits(scenario)) == 1

    _cast_at(scenario, "Pacifism", bears, "Plains", "Plains")

    assert scenario.stack_names()[-1] == "Brinebound Gift's triggered ability"
    scenario.resolve_top()
    assert len(_spirits(scenario)) == 2


def test_an_aura_spell_at_another_creature_does_not_trigger_brinebound_gift():
    scenario = _board(
        {
            "graveyard": [COMBER],
            "battlefield": ["Plains", "Island", "Plains", "Plains", "Grizzly Bears", "Hill Giant"],
            "hand": ["Pacifism"],
        }
    )
    bears = scenario.creature("Grizzly Bears")
    casting = scenario.cast(COMBER, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Disturb")
    casting.choose_targets([bears])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    _cast_at(scenario, "Pacifism", scenario.creature("Hill Giant"), "Plains", "Plains")

    assert scenario.stack_names() == ["Pacifism"]


def test_brine_comber_entering_makes_a_spirit():
    scenario = _board({"hand": [COMBER], "battlefield": ["Plains", "Island", "Island"]})

    scenario.cast_and_resolve(COMBER, *scenario.untapped_sources("Plains", "Island", "Island"))
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == [f"{COMBER}'s triggered ability"]
    scenario.resolve_top()
    assert len(_spirits(scenario)) == 1


def test_wild_defiance_pumps_a_creature_targeted_by_an_instant():
    scenario = _board(
        {"battlefield": ["Wild Defiance", "Grizzly Bears", "Forest"], "hand": ["Giant Growth"]}
    )
    bears = scenario.creature("Grizzly Bears")

    _cast_at(scenario, "Giant Growth", bears, "Forest")

    assert scenario.stack_names()[-1] == "Wild Defiance's triggered ability"
    scenario.resolve_top()
    assert scenario.game.power_of(bears) == 5


def test_wild_defiance_ignores_an_aura_spell():
    scenario = _board(
        {
            "battlefield": ["Wild Defiance", "Grizzly Bears", "Plains", "Plains"],
            "hand": ["Pacifism"],
        }
    )

    _cast_at(scenario, "Pacifism", scenario.creature("Grizzly Bears"), "Plains", "Plains")

    assert scenario.stack_names() == ["Pacifism"]

"""CR 110.4a: "permanent card" means an artifact, battle, creature,
enchantment, land, or planeswalker card - an instant or sorcery card in a
graveyard is never one, whatever else its target phrase says.

Found when the behavioural sweep began driving loyalty "-X" costs at X=1:
Tamiyo, Compleated Sage's "-X: Exile target nonland permanent card with mana
value X from your graveyard. Create a token that's a copy of that card." took
Lightning Bolt (mana value 1) as its target and made a token copy of an
instant on the battlefield.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _graveyard(cards):
    scenario = (
        Scenario()
        .player("alice", graveyard=list(cards), library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _rejects(scenario, phrase, name):
    requirement = profile_for_text(phrase).requirements[0]
    card = scenario.find(name, Zone.GRAVEYARD, "alice")
    return requirement.rejects(card, "alice", scenario.game)


def test_nonland_permanent_card_refuses_an_instant():
    scenario = _graveyard(["Lightning Bolt", "Memnite"])
    phrase = "Exile target nonland permanent card with mana value 1 from your graveyard."

    assert _rejects(scenario, phrase, "Lightning Bolt") is not None


def test_nonland_permanent_card_still_takes_a_creature_and_refuses_a_land():
    scenario = _graveyard(["Llanowar Elves", "Forest"])
    phrase = "Exile target nonland permanent card from your graveyard."

    assert _rejects(scenario, phrase, "Llanowar Elves") is None
    assert _rejects(scenario, phrase, "Forest") is not None


def test_permanent_card_takes_a_land_and_refuses_a_sorcery():
    scenario = _graveyard(["Forest", "Duress"])
    phrase = "Return target permanent card from your graveyard to your hand."

    assert _rejects(scenario, phrase, "Forest") is None
    assert _rejects(scenario, phrase, "Duress") is not None

""" "If you can't, <fallback>" after a mandatory "put/return a <quality> card".

Two printings, two readers, one fallback rule: the fallback runs exactly
when the instruction before it moved no card.

- Temporal Conqueror (trk): "mill three cards. Then return a land card from
  your graveyard to your hand. If you can't, create a Treasure token." - the
  return reads the *whole* graveyard, so a land that was there before the
  mill counts.
- Patient Naturalist (otj): "mill three cards. Put a land card from among
  the milled cards into your hand. If you can't, create a Treasure token." -
  only the cards this mill moved count (CR 701.17c), so a land already in
  the graveyard does not.

CR rules looked up with `mise run rules:find` in the writing session:

- CR 608.2c: the controller follows the instructions in the order written,
  and "later text on the card may modify the meaning of earlier text".
- CR 101.3: "Any part of an instruction that's impossible to perform is
  ignored. (In many cases the card will specify consequences for this; if it
  doesn't, there's no effect.)" - "If you can't" is that specified
  consequence.
- CR 608.2d: a choice made while applying the effect; an illegal or
  impossible option can't be chosen.
- CR 701.17a / 701.17c: milling, and an effect finding a milled card in the
  public zone it moved to.
- CR 111.10a: a Treasure token is a colorless Treasure artifact token with
  "{T}, Sacrifice this token: Add one mana of any color."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _names(cards) -> list[str]:
    return [card.name for card in cards]


def _enters(creature: str, *, library: list[str], graveyard: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", hand=[creature], library=library, graveyard=graveyard or [])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_enters_trigger(scenario, creature: str) -> None:
    scenario.put_onto_battlefield(creature, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _treasures(scenario) -> list[str]:
    return [name for name in scenario.battlefield_names() if name == "Treasure Token"]


# -- Temporal Conqueror: "return a land card from your graveyard" -----------


def test_temporal_conqueror_returns_a_milled_land_and_makes_no_treasure() -> None:
    scenario = _enters("Temporal Conqueror", library=["Opt", "Forest", "Shock", "Island"])
    _resolve_enters_trigger(scenario, "Temporal Conqueror")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Forest"]
    assert sorted(_names(alice.graveyard)) == ["Opt", "Shock"]
    assert _treasures(scenario) == []


def test_temporal_conqueror_returns_a_land_that_was_already_in_the_graveyard() -> None:
    """ "From your graveyard" is the whole graveyard after the mill, so a land
    that was there before counts and no Treasure is made."""
    scenario = _enters(
        "Temporal Conqueror", library=["Opt", "Shock", "Opt"], graveyard=["Mountain"]
    )
    _resolve_enters_trigger(scenario, "Temporal Conqueror")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Mountain"]
    assert _treasures(scenario) == []


def test_temporal_conqueror_with_no_land_anywhere_creates_a_treasure() -> None:
    """No land card to return: the return is impossible (CR 101.3) and the
    printed consequence, a Treasure, happens instead."""
    scenario = _enters("Temporal Conqueror", library=["Opt", "Shock", "Opt", "Forest"])
    _resolve_enters_trigger(scenario, "Temporal Conqueror")

    alice = scenario.player("alice")
    assert alice.hand == []
    assert _treasures(scenario) == ["Treasure Token"]
    treasure = scenario.find("Treasure Token", Zone.BATTLEFIELD, "alice")
    assert treasure.controller == "alice"
    assert _names(alice.library) == ["Forest"], "only three cards are milled"


def test_temporal_conqueror_with_an_empty_library_still_reads_the_graveyard() -> None:
    """Nothing to mill (CR 701.17b) does not stop the return; with no land
    either, the Treasure is made."""
    scenario = _enters("Temporal Conqueror", library=[])
    _resolve_enters_trigger(scenario, "Temporal Conqueror")

    assert _treasures(scenario) == ["Treasure Token"]


def test_temporal_conqueror_with_two_lands_asks_which_one() -> None:
    """Two candidates: the controller chooses one (CR 608.2d); the other
    stays in the graveyard and no Treasure is made."""
    scenario = _enters("Temporal Conqueror", library=["Forest", "Island", "Opt"])
    island = scenario.player("alice").library[1]
    scenario.will_choose_cards(island, source="Temporal Conqueror")
    _resolve_enters_trigger(scenario, "Temporal Conqueror")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Island"]
    assert sorted(_names(alice.graveyard)) == ["Forest", "Opt"]
    assert _treasures(scenario) == []
    assert [q.kind for q in scenario.questions_asked() if q.source == "Temporal Conqueror"] == [
        DecisionKind.CHOOSE_CARDS
    ]


# -- Patient Naturalist: "from among the milled cards" ----------------------


def test_patient_naturalist_puts_a_milled_land_into_hand_and_makes_no_treasure() -> None:
    scenario = _enters("Patient Naturalist", library=["Opt", "Forest", "Shock", "Island"])
    _resolve_enters_trigger(scenario, "Patient Naturalist")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Forest"]
    assert _treasures(scenario) == []


def test_patient_naturalist_ignores_a_land_that_was_already_in_the_graveyard() -> None:
    """ "From among the milled cards" (CR 701.17c) is only what this mill
    moved: the Mountain already there is no candidate, so the put is
    impossible and the Treasure is made."""
    scenario = _enters(
        "Patient Naturalist", library=["Opt", "Shock", "Opt"], graveyard=["Mountain"]
    )
    _resolve_enters_trigger(scenario, "Patient Naturalist")

    alice = scenario.player("alice")
    assert alice.hand == []
    assert "Mountain" in _names(alice.graveyard)
    assert _treasures(scenario) == ["Treasure Token"]


def test_patient_naturalist_with_no_land_milled_creates_a_treasure() -> None:
    scenario = _enters("Patient Naturalist", library=["Opt", "Shock", "Grizzly Bears"])
    _resolve_enters_trigger(scenario, "Patient Naturalist")

    assert scenario.player("alice").hand == []
    assert _treasures(scenario) == ["Treasure Token"]


def test_patient_naturalist_with_two_milled_lands_takes_the_chosen_one() -> None:
    scenario = _enters("Patient Naturalist", library=["Forest", "Opt", "Island"])
    forest = scenario.player("alice").library[0]
    scenario.will_choose_cards(forest, source="Patient Naturalist")
    _resolve_enters_trigger(scenario, "Patient Naturalist")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Forest"]
    assert sorted(_names(alice.graveyard)) == ["Island", "Opt"]
    assert _treasures(scenario) == []

"""Predefined token rows carry CR 111.10's wording, nothing added (NW01-F1).

Rules, looked up with `mise run rules:find 111.10` in the session that wrote
this file:

- **CR 111.10f** - "A Clue token is a colorless Clue artifact token with
  '{2}, Sacrifice this token: Draw a card.'" There is no {T} in the cost, so a
  tapped Clue can still be sacrificed and activating it never taps it.
- Every other predefined row in `models/token.py` is compared to its CR 111.10
  line one by one below; Clue was the only one that deviated.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.token import PREDEFINED
from tests.scenarios.harness import Scenario

CR_TEXT = {
    "Treasure": "{T}, Sacrifice this token: Add one mana of any color.",
    "Food": "{2}, {T}, Sacrifice this token: You gain 3 life.",
    "Shard": "{2}, Sacrifice this token: Scry 1, then draw a card.",
    "Clue": "{2}, Sacrifice this token: Draw a card.",
    "Powerstone": "{T}: Add {C}. This mana can't be spent to cast a nonartifact spell.",
    "Map": (
        "{1}, {T}, Sacrifice this token: Target creature you control explores. "
        "Activate only as a sorcery."
    ),
    "Lander": (
        "{2}, {T}, Sacrifice this token: Search your library for a basic land card, "
        "put it onto the battlefield tapped, then shuffle."
    ),
    "Mutagen": (
        "{1}, {T}, Sacrifice this token: Put a +1/+1 counter on target creature. "
        "Activate only as a sorcery."
    ),
    "Heartwood": "{T}: Add {R} or {G}.",
}


@pytest.mark.parametrize("name", sorted(CR_TEXT))
def test_predefined_token_text_matches_cr_111_10(name):
    assert PREDEFINED[name].rules_text == CR_TEXT[name]


def test_tapped_clue_can_still_be_sacrificed_to_draw():
    """Tamiyo investigates; the Clue is tapped; {2} + sacrifice still draws."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Tamiyo, Inquisitive Student", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Tamiyo, Inquisitive Student", "alice"))
    scenario.pass_until_resolved()
    clue = scenario.find("Clue Token", Zone.BATTLEFIELD)
    clue.tapped = True
    before = len(scenario.player("alice").hand)

    scenario.activate(clue, index=0, username="alice", auto=True)
    scenario.resolve_top()

    assert clue.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == before + 1


def test_activating_clue_does_not_tap_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Tamiyo, Inquisitive Student", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Tamiyo, Inquisitive Student", "alice"))
    scenario.pass_until_resolved()
    clue = scenario.find("Clue Token", Zone.BATTLEFIELD)
    assert not clue.tapped

    scenario.activate(clue, index=0, username="alice", auto=True)

    assert not clue.tapped

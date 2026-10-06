"""Investigate: CR 701.16a, a bare CR 701 keyword action, and CR 111.10f's Clue.

"Investigate" means "Create a Clue token" - the same shape as amass or fight
(CR 701.47a, CR 701.14a), a keyword *action* embedded in another ability's
effect text rather than a keyword ability printed on its own line. Read
generically off the printed sentence in `machines/effects.py`'s
`_parse_investigate_clause`, not by card name, so any card that says the word
gets it - proved here on two differently-shaped cards: Tamiyo, Inquisitive
Student's bare "investigate" off a combat trigger, and Armed with Proof's
"investigate twice" off an enters-the-battlefield trigger.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def test_tamiyo_investigates_when_she_attacks():
    """Tamiyo, Inquisitive Student: "Whenever Tamiyo attacks, investigate."
    (Create a Clue token. It's an artifact with "{2}, Sacrifice this token:
    Draw a card.")

    CR 111.10f, in full: "A Clue token is a colorless Clue artifact token with
    '{2}, Sacrifice this token: Draw a card.'"
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tamiyo, Inquisitive Student"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    tamiyo = scenario.creature("Tamiyo, Inquisitive Student", "alice")

    scenario.attack_with(tamiyo)
    scenario.pass_until_resolved()

    clue = scenario.find("Clue Token", Zone.BATTLEFIELD)
    assert clue.card.types == [Type.ARTIFACT]
    assert clue.card.subtypes == ["Clue"]
    assert clue.controller == "alice"


def test_armed_with_proof_investigates_twice():
    """Armed with Proof: "When this enchantment enters, investigate twice."

    A different card, a different trigger event, and a fixed multiplier this
    card's own text spells out as a word rather than a digit - the same
    reader has to carry both.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Armed with Proof"], battlefield=["Plains", "Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")

    scenario.cast_and_resolve("Armed with Proof", *sources, username="alice")
    scenario.pass_until_resolved()

    clues = [state for state in scenario.game.battlefield if state.name == "Clue Token"]
    assert len(clues) == 2
    assert all(clue.controller == "alice" for clue in clues)


def test_investigating_creates_a_working_clue():
    """The Clue's own text is CR 111.10f's, not a stub - sacrificing it for
    {2} draws a card, same as any other Clue in the format.
    """
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
    tamiyo = scenario.creature("Tamiyo, Inquisitive Student", "alice")
    scenario.attack_with(tamiyo)
    scenario.pass_until_resolved()
    clue = scenario.find("Clue Token", Zone.BATTLEFIELD)
    before = len(scenario.player("alice").hand)

    scenario.activate(clue, index=0, username="alice", auto=True)
    scenario.resolve_top()

    assert clue.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == before + 1

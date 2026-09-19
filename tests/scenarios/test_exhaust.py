"""Exhaust: CR 702.177's own once-ever activation limit.

CR 702.177a: "Exhaust is a keyword that adds additional rules to the
activated ability that follows it. 'Exhaust — [Cost]: [Effect]' means
'[Cost]: [Effect]. Activate only once.'" Not new to Reality Fracture (S10
survey, 2026-09-19), but this engine had never read it (`grep -ri exhaust`
matched nothing before this wave).

The restriction it adds is a different shape from CR 602.5b's "Activate only
once each turn" (`test_activation_limits.py`): it is never cleared on a new
turn, so the same ability cannot be activated again for the rest of the
object's existence on the battlefield - `Game.exhausted`, keyed the same way
`Game.activations` is but never reset at cleanup.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[],
            library=["Swamp"] * 10,
            battlefield=[
                "Liliana the Repentant",
                *(["Swamp"] * 12),
            ],
            graveyard=["Grizzly Bears", "Hill Giant"],
        )
        .player("bob", library=["Swamp"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_exhaust_can_be_activated_once():
    """Liliana the Repentant: "Exhaust — {5}{B}: Return target creature or
    planeswalker card from your graveyard to the battlefield. Put a +1/+1
    counter on Liliana. Activate only as a sorcery." A first activation is
    legal and goes onto the stack.

    Only the cost and the exhaust restriction are this stream's scope (S10):
    the effect body itself, "return ... to the battlefield ... with a
    +1/+1 counter", is S8's reanimation-shape territory and stays untested
    here - Liliana is also on S8's own card list for exactly that clause.
    """
    scenario = _board()
    liliana = scenario.creature("Liliana the Repentant", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)
    sources = scenario.untapped_sources(*(["Swamp"] * 6), username="alice")

    assert scenario.why_cannot_activate(liliana) is None
    ability = scenario.activate(liliana, *sources, targets=[bears])
    assert ability is not None
    scenario.pass_until_resolved()


def test_exhaust_refuses_a_second_activation_even_with_a_new_legal_target():
    """CR 702.177a's "Activate only once": a second target (Hill Giant) and
    plenty of mana still refuse the activation."""
    scenario = _board()
    liliana = scenario.creature("Liliana the Repentant", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD)
    first_sources = scenario.untapped_sources(*(["Swamp"] * 6), username="alice")
    scenario.activate(liliana, *first_sources, targets=[bears])
    scenario.pass_until_resolved()

    refusal = scenario.why_cannot_activate(liliana)
    assert refusal is not None
    assert "already been activated" in refusal
    assert "CR 702.177a" in refusal

    with pytest.raises(ValueError, match="already been activated"):
        scenario.activate(liliana, targets=[giant])


def test_exhaust_is_not_confused_with_the_once_each_turn_restriction():
    """A fresh turn does not un-exhaust the ability - unlike `activations`,
    `exhausted` is never cleared at cleanup."""
    scenario = _board()
    liliana = scenario.creature("Liliana the Repentant", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD)
    sources = scenario.untapped_sources(*(["Swamp"] * 6), username="alice")
    scenario.activate(liliana, *sources, targets=[bears])
    scenario.pass_until_resolved()

    # Two turn boundaries: bob's turn, then back to alice's, so the ability's
    # own "Activate only as a sorcery" restriction is not what refuses it.
    for _ in range(2):
        turns = scenario.turn.turns_taken
        while scenario.turn.turns_taken == turns:
            scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    refusal = scenario.why_cannot_activate(liliana)
    assert refusal is not None
    assert "CR 702.177a" in refusal
    with pytest.raises(ValueError, match="already been activated"):
        scenario.activate(liliana, targets=[giant])


# -- generality: a different card, a different set, with no unread effect ---


def test_greenbelt_guardian_generalizes_exhaust_to_a_second_printing():
    """Greenbelt Guardian (Aetherdrift): "{G}: Target creature gains trample
    until end of turn. Exhaust — {3}{G}: Put three +1/+1 counters on this
    creature." A different card in a different set, with a *readable* effect
    body, so this proves both halves at once: the keyword restriction, and
    that Exhaust does not disturb the ordinary mana ability sharing the card
    (index 0, no Exhaust prefix at all)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 10,
            battlefield=["Greenbelt Guardian", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.creature("Greenbelt Guardian", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice")

    assert scenario.why_cannot_activate(guardian, index=1) is None
    scenario.activate(guardian, *sources, index=1)
    scenario.pass_until_resolved()

    assert guardian.counters[Counter.PLUS_ONE] == 3

    refusal = scenario.why_cannot_activate(guardian, index=1)
    assert refusal is not None
    assert "CR 702.177a" in refusal
    with pytest.raises(ValueError, match="already been activated"):
        scenario.activate(guardian, index=1)


def test_greenbelt_guardians_ordinary_ability_is_unaffected_by_exhaust():
    """Index 0 - the plain "{G}: ... trample" ability - carries no Exhaust
    restriction at all and can be activated freely."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 10,
            battlefield=["Greenbelt Guardian", "Grizzly Bears", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.creature("Greenbelt Guardian", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")

    scenario.activate(guardian, sources[0], index=0, targets=[bears])
    scenario.activate(guardian, sources[1], index=0, targets=[bears])

    assert scenario.why_cannot_activate(guardian, index=0) is None

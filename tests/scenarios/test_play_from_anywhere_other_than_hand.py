"""Scenario: "Whenever you [play a land or] cast a spell from anywhere other
than your hand" triggers on a card played out of any zone but the hand, and
never on one played from the hand.

CR 601.1a: "Playing a card" means playing that card as a land or casting
that card as a spell. CR 116.2a: a land is played from the zone it was in,
usually its owner's hand. CR 603.2: the ability triggers only when the event
matches - so the origin zone is part of the trigger event, not a check made
later.

Shadow of the Goblin is the card the behavioural sweep found silent (its
"play a land or cast a spell" read as a cast of a land spell, which no cast
is). Vega, the Watcher prints the cast-only half with a different effect and
is in no decklist here - the generality proof.

Every card here is a real printing; nothing is targeted by name.
"""

from __future__ import annotations

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

LANDS = ["Mountain"] * 4 + ["Forest"] * 2


def _board(
    permanent: str,
    *,
    hand: list[str],
    graveyard: list[str] | None = None,
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=[permanent, *LANDS],
            graveyard=graveyard or [],
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario: PlayedScenario, name: str, *, adventure: bool = False) -> None:
    casting = scenario.cast(name, "alice", from_zone=Zone.HAND if adventure else Zone.EXILE)
    if not adventure:
        casting.use_keyword("Adventure")  # CR 715.4's permission from exile
    else:
        # Stomp, aimed at the opponent (CR 715.3).
        casting.cast_as_adventure()
        casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)


def _from_exile(scenario: PlayedScenario) -> None:
    """Stomp from the hand (CR 715.3), resolved into exile (CR 715.4), then
    the Giant cast from exile."""
    _cast(scenario, "Bonecrusher Giant", adventure=True)
    scenario.game.resolve_top()
    _cast(scenario, "Bonecrusher Giant")
    scenario.game.put_triggers_on_stack()


def _triggered(scenario: PlayedScenario, source: str) -> list[str]:
    """The sources of the abilities on the stack that `source` put there."""
    scenario.game.put_triggers_on_stack()
    return [
        item.source_name
        for item in scenario.game.stack
        if isinstance(item, AbilityOnStack) and item.source_name == source
    ]


def test_shadow_of_the_goblin_ignores_a_spell_cast_from_the_hand():
    scenario = _board("Shadow of the Goblin", hand=["Lightning Bolt"])

    casting = scenario.cast("Lightning Bolt", "alice", targets=["bob"])
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)

    assert _triggered(scenario, "Shadow of the Goblin") == []


def test_shadow_of_the_goblin_triggers_on_a_spell_cast_from_exile():
    scenario = _board("Shadow of the Goblin", hand=["Bonecrusher Giant"])

    _from_exile(scenario)

    assert _triggered(scenario, "Shadow of the Goblin") == ["Shadow of the Goblin"]
    life = scenario.game.player("bob").life
    while _triggered(scenario, "Shadow of the Goblin"):
        scenario.game.resolve_top()
    assert scenario.game.player("bob").life == life - 1


def test_the_adventure_cast_from_the_hand_does_not_trigger_it():
    """Stomp itself is cast from the hand (CR 715.3) - only the Giant's cast
    from exile afterwards is from anywhere other than the hand."""
    scenario = _board("Shadow of the Goblin", hand=["Bonecrusher Giant"])

    _cast(scenario, "Bonecrusher Giant", adventure=True)

    assert _triggered(scenario, "Shadow of the Goblin") == []


def test_shadow_of_the_goblin_ignores_a_land_played_from_the_hand():
    scenario = _board("Shadow of the Goblin", hand=["Mountain"])

    scenario.play_land("Mountain", "alice")

    assert _triggered(scenario, "Shadow of the Goblin") == []


def test_shadow_of_the_goblin_triggers_on_a_land_played_from_the_graveyard():
    """CR 601.1a: playing a land is playing a card too. The permission to play
    it from the graveyard (CR 116.2a) is the engine's own primitive every
    "you may play that card" effect grants through."""
    scenario = _board("Shadow of the Goblin", hand=[], graveyard=["Mountain"])
    (buried,) = scenario.player("alice").graveyard
    scenario.game.grant_play_permission(
        buried, "alice", action=PlayAction.PLAY, zone=Zone.GRAVEYARD, source_name="a test"
    )

    scenario.play_land("Mountain", "alice", from_zone=Zone.GRAVEYARD)

    assert _triggered(scenario, "Shadow of the Goblin") == ["Shadow of the Goblin"]


def test_vega_draws_for_a_spell_cast_from_exile():
    """Generality: the cast-only half, worded without "play a land"."""
    scenario = _board("Vega, the Watcher", hand=["Bonecrusher Giant"])

    _from_exile(scenario)

    assert _triggered(scenario, "Vega, the Watcher") == ["Vega, the Watcher"]


def test_vega_ignores_a_spell_cast_from_the_hand():
    scenario = _board("Vega, the Watcher", hand=["Bonecrusher Giant"])

    _cast(scenario, "Bonecrusher Giant", adventure=True)

    assert _triggered(scenario, "Vega, the Watcher") == []

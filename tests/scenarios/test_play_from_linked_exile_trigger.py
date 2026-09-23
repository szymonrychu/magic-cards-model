"""Scenario: "When you play a card exiled with this creature" (CR 607.2a,
CR 601.1a).

Voltaic Visionary // Volt-Charged Berserker: "{T}: This creature deals 2
damage to you. Exile the top card of your library. You may play that card
this turn. Activate only as a sorcery.\nWhen you play a card exiled with this
creature, transform this creature." // "This creature can't block."

- CR 601.1a: "'Playing a card' means playing that card as a land or casting
  that card as a spell, whichever is appropriate" - so a land played from the
  pile triggers the same as a spell cast from it.
- CR 607.2a: the trigger's "exiled with this creature" is linked to the
  activated ability's exile, and only to that - a card exiled by anything
  else, a second Visionary included, does not trigger this one.
- CR 400.7: a Visionary that left the battlefield and returned is a new
  object, so the card its earlier self exiled is not "exiled with" it, even
  though the play permission (which is the player's) still lets that card be
  cast.
- CR 509.1b: the back face's "This creature can't block." restriction.

A card_search for "you play a card exiled with" on 2026-09-23 found Voltaic
Visionary alone, so no second printing carries this trigger condition; that
is recorded in MEMORY.md.

CR numbers verified with `mise run rules:find` this session: 601.1a, 607.2a,
400.7, 509.1b, 701.27a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState

from .harness import PlayedScenario, Scenario


def _board(*, library: list[str], battlefield: list[str] | None = None, hand=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Voltaic Visionary", "Mountain", "Mountain", *(battlefield or [])],
            library=library,
            hand=hand or [],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for visionary in scenario.game.permanents_controlled_by("alice"):
        visionary.summoning_sick = False
    return scenario


def _activate(scenario: PlayedScenario, visionary: CardState) -> CardState:
    """The Visionary's own {T} ability: 2 damage to alice, the top card of her
    library exiled, and a play permission for this turn."""
    top = scenario.player("alice").library[0]
    scenario.activate(visionary)
    scenario.pass_until_resolved()
    assert top.zone is Zone.EXILE
    return top


def test_casting_the_exiled_card_transforms_the_visionary():
    scenario = _board(library=["Lightning Bolt", "Forest", "Forest"])
    visionary = scenario.creature("Voltaic Visionary", "alice")
    bolt = _activate(scenario, visionary)
    assert scenario.player("alice").life == 18

    (mountain, *_) = scenario.untapped_sources("Mountain", username="alice")
    casting = scenario.cast("Lightning Bolt", "alice", from_zone=Zone.EXILE, targets=["bob"])
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)

    assert scenario.stack_names()[-1].startswith("Voltaic Visionary"), "the trigger is on top"
    scenario.pass_until_resolved()
    assert visionary.name == "Volt-Charged Berserker"
    assert scenario.game.characteristics_of(visionary).power == 4
    scenario.pass_until_resolved()
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_playing_the_exiled_land_transforms_the_visionary():
    """CR 601.1a: playing a land is playing a card too."""
    scenario = _board(library=["Forest", "Lightning Bolt"])
    visionary = scenario.creature("Voltaic Visionary", "alice")
    _activate(scenario, visionary)

    forest = scenario.play_land("Forest", "alice", from_zone=Zone.EXILE)

    assert forest.zone is Zone.BATTLEFIELD
    (trigger,) = scenario.stack_names()
    assert trigger.startswith("Voltaic Visionary")
    scenario.pass_until_resolved()
    assert visionary.name == "Volt-Charged Berserker"


def test_a_card_exiled_by_another_visionary_transforms_only_that_one():
    """Two Visionaries, two piles (CR 607.2a): playing the card the second one
    exiled triggers the second one alone."""
    scenario = _board(
        library=["Forest", "Mountain", "Lightning Bolt"], battlefield=["Voltaic Visionary"]
    )
    first, second = scenario.creatures("Voltaic Visionary", "Voltaic Visionary", username="alice")
    _activate(scenario, first)
    _activate(scenario, second)

    scenario.play_land("Mountain", "alice", from_zone=Zone.EXILE)
    scenario.pass_until_resolved()

    assert second.name == "Volt-Charged Berserker"
    assert first.name == "Voltaic Visionary"


def test_casting_a_card_from_hand_does_not_transform_it():
    scenario = _board(library=["Forest", "Forest"], hand=["Lightning Bolt"])
    visionary = scenario.creature("Voltaic Visionary", "alice")
    _activate(scenario, visionary)

    (mountain, *_) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.stack_names() == ["Lightning Bolt"]
    scenario.pass_until_resolved()
    assert visionary.name == "Voltaic Visionary"


def test_a_visionary_that_left_and_returned_does_not_read_its_old_pile():
    """CR 400.7: after Ephemerate the Visionary is a new object. The Bolt its
    earlier self exiled can still be cast - the permission is alice's - but it
    is not exiled with *this* Visionary, so nothing transforms."""
    scenario = _board(
        library=["Lightning Bolt", "Forest"], battlefield=["Plains"], hand=["Ephemerate"]
    )
    visionary = scenario.creature("Voltaic Visionary", "alice")
    _activate(scenario, visionary)

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Ephemerate", plains, username="alice", targets=[visionary])
    returned = scenario.creature("Voltaic Visionary", "alice")

    (mountain, *_) = scenario.untapped_sources("Mountain", username="alice")
    casting = scenario.cast("Lightning Bolt", "alice", from_zone=Zone.EXILE, targets=["bob"])
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)

    assert scenario.stack_names() == ["Lightning Bolt"]
    scenario.pass_until_resolved()
    assert returned.name == "Voltaic Visionary"


def test_the_transformed_berserker_cannot_block():
    """The back face's static "This creature can't block." (CR 509.1b),
    reached through the trigger rather than a direct flip: on bob's next
    turn his Grizzly Bears attacks and the Berserker may not block it."""
    scenario = _board(library=["Forest"] * 6)
    visionary = scenario.creature("Voltaic Visionary", "alice")
    _activate(scenario, visionary)
    scenario.play_land("Forest", "alice", from_zone=Zone.EXILE)
    scenario.pass_until_resolved()
    assert visionary.name == "Volt-Charged Berserker"

    # The Visionary tapped to exile the land, so bob's *second* turn is the
    # first one it faces untapped (CR 502.3).
    seen = 0
    for _ in range(80):
        if scenario.turn.active_player == "bob" and scenario.step is Step.DECLARE_ATTACKERS:
            seen += 1
            if seen == 2:
                break
        scenario.advance()
    assert not visionary.tapped
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears)
    scenario.advance("bob")

    assert not scenario.game.can_block(visionary, bears)
    reason = scenario.game.why_cannot_block(visionary, bears)
    assert reason is not None and "CR 509.1b" in reason

"""Processors: "you may put a card an opponent owns from exile into that
player's graveyard. If you do, <targeted effect>."

- **Wasteland Strangler** (the listed card): "When this creature enters, you
  may put a card an opponent owns from exile into that player's graveyard.
  If you do, target creature gets -3/-3 until end of turn."
- **Murk Strider** (the second printing: not a listed card, not in any api
  deck): the same processing, with "return target creature to its owner's
  hand" as the payoff.

The ordering is CR 118.12's "[A player] may [do something]. If [that player]
[does], [effect]": putting the card into the graveyard is a cost paid as the
ability resolves, and the payoff happens only if the player chose to pay it.
The payoff's target, though, is chosen when the trigger is put on the stack
(CR 603.3d), before anyone knows whether the cost will be paid - and if that
target is illegal on resolution the ability doesn't resolve at all (CR
608.2b), so no card is processed either.

Only a card an *opponent* owns is eligible; the controller's own exiled cards
are not. With nothing eligible there is nothing to pay, so there is no
question and no payoff.

A face-down exiled card can be processed too, but can't be looked at (CR
406.3): its owner's face-down cards form a pile, and the card is taken from
that pile at random rather than picked.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 118.12, 406.3, 603.3d, 608.2b, 704.5f.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

STRANGLER = "Wasteland Strangler"
STRIDER = "Murk Strider"


def _resolve_all(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _board(
    processor: str,
    *,
    bob_exile: list[str] | None = None,
    alice_exile: list[str] | None = None,
    bob_battlefield: list[str] | None = None,
) -> PlayedScenario:
    lands = ["Swamp", "Swamp", "Swamp"] if processor == STRANGLER else ["Island"] * 4
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[processor], battlefield=lands, exile=alice_exile or [])
        .player(
            "bob",
            battlefield=bob_battlefield if bob_battlefield is not None else ["Serra Angel"],
            exile=bob_exile or [],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario: PlayedScenario, processor: str, target) -> None:
    scenario.choose_trigger_targets(processor, [target])
    lands = scenario.untapped_sources(
        *(["Swamp"] * 3 if processor == STRANGLER else ["Island"] * 4)
    )
    scenario.cast_and_resolve(processor, *lands)


def _exiled(scenario: PlayedScenario, owner: str) -> list[str]:
    return [c.card.name for c in scenario.game.exile if c.owner == owner]


def _processing_questions(scenario: PlayedScenario, source: str):
    return [q for q in scenario.questions_asked() if q.source == source]


def test_processing_a_card_gives_the_target_minus_three():
    scenario = _board(STRANGLER, bob_exile=["Lightning Bolt"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    bolt = scenario.find("Lightning Bolt", Zone.EXILE, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRANGLER)

    _cast(scenario, STRANGLER, angel)
    _resolve_all(scenario)

    # One eligible card is no choice at all, so no card question is put.
    assert [
        q for q in _processing_questions(scenario, STRANGLER) if q.kind is DecisionKind.CHOOSE_CARDS
    ] == []
    assert bolt.zone is Zone.GRAVEYARD
    assert bolt in scenario.player("bob").graveyard
    assert (scenario.game.power_of(angel), scenario.game.toughness_of(angel)) == (1, 1)


def test_the_minus_three_lasts_until_end_of_turn():
    scenario = _board(STRANGLER, bob_exile=["Lightning Bolt"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRANGLER)

    _cast(scenario, STRANGLER, angel)
    _resolve_all(scenario)
    scenario.game.cleanup_step()

    assert (scenario.game.power_of(angel), scenario.game.toughness_of(angel)) == (4, 4)


def test_a_small_target_dies():
    """CR 704.5f: toughness 0 or less is put into its owner's graveyard."""
    scenario = _board(STRANGLER, bob_exile=["Lightning Bolt"], bob_battlefield=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRANGLER)

    _cast(scenario, STRANGLER, bears)
    _resolve_all(scenario)
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD


def test_declining_processes_nothing_and_does_nothing():
    """CR 118.12: no cost paid, no payoff."""
    scenario = _board(STRANGLER, bob_exile=["Lightning Bolt"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(False, username="alice", source=STRANGLER)

    _cast(scenario, STRANGLER, angel)
    _resolve_all(scenario)

    assert _exiled(scenario, "bob") == ["Lightning Bolt"]
    assert (scenario.game.power_of(angel), scenario.game.toughness_of(angel)) == (4, 4)


def test_your_own_exiled_cards_cannot_be_processed():
    scenario = _board(STRANGLER, alice_exile=["Lightning Bolt"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRANGLER)

    _cast(scenario, STRANGLER, angel)
    _resolve_all(scenario)

    assert _exiled(scenario, "alice") == ["Lightning Bolt"]
    assert (scenario.game.power_of(angel), scenario.game.toughness_of(angel)) == (4, 4)
    assert _processing_questions(scenario, STRANGLER) == []


def test_an_empty_exile_asks_nothing_and_does_nothing():
    scenario = _board(STRANGLER)
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")

    _cast(scenario, STRANGLER, angel)
    _resolve_all(scenario)

    assert (scenario.game.power_of(angel), scenario.game.toughness_of(angel)) == (4, 4)
    assert _processing_questions(scenario, STRANGLER) == []
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_the_target_is_chosen_on_the_stack_and_an_illegal_one_stops_the_whole_ability():
    """CR 603.3d then CR 608.2b: the target was locked in before the cost
    was offered; with it gone, the ability doesn't resolve and nothing is
    processed."""
    scenario = _board(STRANGLER, bob_exile=["Lightning Bolt"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRANGLER)
    scenario.choose_trigger_targets(STRANGLER, [angel])
    scenario.cast_and_resolve(STRANGLER, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    scenario.game.put_triggers_on_stack()
    assert [item.source_name for item in scenario.game.stack] == [STRANGLER]
    (trigger,) = scenario.game.stack
    assert [t.card_id for t in trigger.targets] == [angel.id]

    scenario.game.destroy(angel)
    _resolve_all(scenario)

    assert _exiled(scenario, "bob") == ["Lightning Bolt"]


def test_the_strangler_can_shrink_itself():
    """ "Target creature" is any creature, its own source included."""
    scenario = _board(STRANGLER, bob_exile=["Lightning Bolt"], bob_battlefield=[])
    scenario.will_take_the_may(True, username="alice", source=STRANGLER)
    strangler = scenario.find(STRANGLER, Zone.HAND, "alice")
    scenario.will_choose_targets(strangler, username="alice", source=STRANGLER)
    scenario.cast_and_resolve(STRANGLER, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    _resolve_all(scenario)
    scenario.state_based_actions()

    assert strangler.zone is Zone.GRAVEYARD


def test_a_face_down_card_is_taken_at_random_from_its_pile():
    """CR 406.3: face-down exiled cards can't be looked at, so after Doomsday
    Excruciator exiles bob's library face down the processed card is taken
    at random from that pile - and lands face up in bob's graveyard."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Doomsday Excruciator", STRANGLER],
            battlefield=["Swamp"] * 9,
            library=["Forest"] * 7,
        )
        .player(
            "bob",
            battlefield=["Serra Angel"],
            library=["Lightning Bolt", "Memnite", "Island"] + ["Forest"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources(*["Swamp"] * 9)
    scenario.cast_and_resolve("Doomsday Excruciator", *swamps[:6])
    _resolve_all(scenario)
    face_down = [c for c in scenario.game.exile if c.owner == "bob"]
    assert len(face_down) == 3 and all(c.face_down for c in face_down)

    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRANGLER)
    scenario.choose_trigger_targets(STRANGLER, [angel])
    scenario.cast_and_resolve(STRANGLER, *swamps[6:])
    _resolve_all(scenario)

    graveyard = scenario.player("bob").graveyard
    assert len(graveyard) == 1
    assert graveyard[0].face_up
    assert graveyard[0].card.name in {"Lightning Bolt", "Memnite", "Island"}
    assert len([c for c in scenario.game.exile if c.owner == "bob"]) == 2
    assert (scenario.game.power_of(angel), scenario.game.toughness_of(angel)) == (1, 1)
    choices = [
        q for q in _processing_questions(scenario, STRANGLER) if q.kind is DecisionKind.CHOOSE_CARDS
    ]
    # One pile, so there is nothing to choose between: no card question.
    assert choices == []


def test_several_eligible_cards_are_a_choice():
    scenario = _board(STRANGLER, bob_exile=["Lightning Bolt", "Memnite"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    memnite = scenario.find("Memnite", Zone.EXILE, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRANGLER)
    scenario.will_choose_cards(memnite, username="alice", source=STRANGLER)

    _cast(scenario, STRANGLER, angel)
    _resolve_all(scenario)

    assert _exiled(scenario, "bob") == ["Lightning Bolt"]
    assert [c.name for c in scenario.player("bob").graveyard] == ["Memnite"]


# -- Murk Strider: the same processing, a bounce payoff ----------------------


def test_murk_strider_processes_and_bounces():
    scenario = _board(STRIDER, bob_exile=["Lightning Bolt"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRIDER)

    _cast(scenario, STRIDER, angel)
    _resolve_all(scenario)

    assert angel.zone is Zone.HAND
    assert [c.name for c in scenario.player("bob").graveyard] == ["Lightning Bolt"]


def test_murk_strider_declined_leaves_the_target_alone():
    scenario = _board(STRIDER, bob_exile=["Lightning Bolt"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(False, username="alice", source=STRIDER)

    _cast(scenario, STRIDER, angel)
    _resolve_all(scenario)

    assert angel.zone is Zone.BATTLEFIELD
    assert _exiled(scenario, "bob") == ["Lightning Bolt"]


def test_murk_strider_with_nothing_to_process_bounces_nothing():
    scenario = _board(STRIDER, alice_exile=["Lightning Bolt"])
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice", source=STRIDER)

    _cast(scenario, STRIDER, angel)
    _resolve_all(scenario)

    assert angel.zone is Zone.BATTLEFIELD

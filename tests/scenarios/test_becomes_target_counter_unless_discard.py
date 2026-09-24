""" "Whenever this creature becomes the target of a spell an opponent controls,
counter that spell unless its controller discards a card." - Reality Smasher,
and the same trigger with any printed cost: Frost Titan's "a spell or ability
an opponent controls, counter that spell or ability unless its controller
pays {2}."

CR 118.12a: ""[Do something] unless [a player does something else]" means
the same thing as "[A player may do something else]. If [that player
doesn't], [do something]."" - the targeting spell's controller is asked as
the trigger resolves, and a cost they cannot pay (an empty hand for a
discard) is simply not paid.

CR 701.9a: the discard is theirs to choose (CR 701.9b's own "the player
chooses" is `Game.may_pay_unless_cost`'s `CHOOSE_CARDS`). CR 701.6a: a
countered spell is put into its owner's graveyard without resolving.

CR 115.1 lets a spell or an ability target; Reality Smasher's condition names
only "a spell", so an ability targeting it triggers nothing, while Frost
Titan's names both.

Reality Smasher is the listed card; Frost Titan (Modern legal, in no api
deck) is the proof printing - a different subject, a different cost, and a
targeting object that may be an ability.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

SMASHER = "Reality Smasher"
TITAN = "Frost Titan"


def _bolted(target_name: str, bob_hand: list[str], bob_lands: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", battlefield=[target_name])
        .player(
            "bob",
            hand=["Lightning Bolt", *bob_hand],
            battlefield=["Mountain", *(bob_lands or [])],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    target = scenario.creature(target_name)
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[target],
    )
    assert scenario.stack_names() == ["Lightning Bolt", f"{target_name}'s triggered ability"]
    return scenario, bolt, target


def test_both_printings_are_fully_supported() -> None:
    for name in (SMASHER, TITAN):
        statuses = {clause.status for clause in card_support(card(name)).clauses}
        assert statuses == {"handled"}, (name, card_support(card(name)).clauses)


def test_discarding_a_card_lets_the_spell_resolve() -> None:
    scenario, bolt, smasher = _bolted(SMASHER, ["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.will_take_the_may(True, username="bob")
    scenario.will_choose_cards(bears, username="bob")

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.STACK
    scenario.resolve_top()
    assert smasher.damage == 3


def test_declining_to_discard_counters_the_spell() -> None:
    """CR 701.6a: countered, the Bolt goes to the graveyard having done
    nothing - and the card bob kept is still in hand."""
    scenario, bolt, smasher = _bolted(SMASHER, ["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.will_take_the_may(False, username="bob")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.HAND
    assert smasher.damage == 0
    assert scenario.stack_names() == []


def test_an_empty_hand_cannot_pay_so_the_spell_is_countered() -> None:
    """CR 118.3: a cost can't be paid without the resources - with nothing
    to discard, the only legal answer bob is offered is "no"."""
    scenario, bolt, _smasher = _bolted(SMASHER, [])
    asked = len(scenario.questions_asked())

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    offered = scenario.questions_asked()[asked:]
    assert [question.affirmative_is_legal for question in offered] == [False]


def test_its_controllers_own_spell_does_not_trigger_it() -> None:
    """ "a spell *an opponent* controls"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=[SMASHER, "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    smasher = scenario.creature(SMASHER)

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[smasher]
    )

    assert scenario.stack_names() == ["Lightning Bolt"]


def test_an_ability_targeting_it_does_not_trigger_it() -> None:
    """CR 115.1: Mogg Fanatic's ability targets, but Reality Smasher's
    condition names only a spell."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[SMASHER])
        .player("bob", battlefield=["Mogg Fanatic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    smasher = scenario.creature(SMASHER)
    fanatic = scenario.creature("Mogg Fanatic", "bob")

    scenario.activate(fanatic, username="bob", sacrificing=[fanatic], targets=[smasher])

    assert scenario.stack_names() == ["Mogg Fanatic's activated ability"]


def test_the_spell_already_gone_leaves_nothing_to_counter() -> None:
    """The targeting spell left the stack before the trigger resolved (here
    exiled in response): nothing to counter, nobody asked to discard."""
    scenario, bolt, _smasher = _bolted(SMASHER, ["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.game.exile_from_stack(bolt)
    asked = len(scenario.questions_asked())

    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert len(scenario.questions_asked()) == asked


def test_frost_titan_counters_unless_two_mana_is_paid() -> None:
    """The proof printing: "unless its controller pays {2}" - bob, tapped out
    after the Bolt, cannot pay and the Bolt is countered."""
    scenario, bolt, titan = _bolted(TITAN, [])

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert titan.damage == 0


def test_frost_titan_lets_the_spell_through_when_paid() -> None:
    scenario, bolt, titan = _bolted(TITAN, [], bob_lands=["Mountain", "Mountain"])
    scenario.will_pay_the_mana_cost(True, username="bob")

    scenario.resolve_top()

    assert bolt.zone is Zone.STACK
    assert all(land.tapped for land in scenario.game.battlefield if land.controller == "bob")
    scenario.resolve_top()
    assert titan.damage == 3


def test_frost_titan_also_answers_an_ability() -> None:
    """ "a spell or ability": Mogg Fanatic's activated ability targeting the
    Titan triggers it, and unpaid, the ability is countered."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[TITAN])
        .player("bob", battlefield=["Mogg Fanatic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    titan = scenario.creature(TITAN)
    fanatic = scenario.creature("Mogg Fanatic", "bob")

    scenario.activate(fanatic, username="bob", sacrificing=[fanatic], targets=[titan])
    assert scenario.stack_names()[-1] == f"{TITAN}'s triggered ability"

    scenario.resolve_top()

    assert scenario.stack_names() == []
    assert titan.damage == 0

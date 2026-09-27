"""CR 701.68a/701.68b performed by someone other than the ability's own
controller - "each opponent blights N" (High Perfect Morcant's own Elf-tribal
ETB) and "target opponent blights N" (Champion of the Weird's own activated
ability). `test_blight_positions.py` covers every position the controller's
own "you may blight N" prints in; this file is only about the blighting
player being someone else.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_each_opponent_blights_on_elf_etb():
    """High Perfect Morcant: "Whenever High Perfect Morcant or another Elf
    you control enters, each opponent blights 1." (They each put a -1/-1
    counter on a creature they control.) - CR 701.68a performed by each
    opponent in turn (CR 101.4's APNAP order), never targeted."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["High Perfect Morcant"],
            battlefield=["Swamp", "Swamp", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Forest", "Forest", username="alice")

    scenario.will_choose_cards(bears, username="bob")
    scenario.cast_and_resolve("High Perfect Morcant", *sources, username="alice")
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 1


def test_an_opponent_with_no_creature_cannot_be_made_to_blight():
    """CR 701.68b: an opponent instructed to blight who controls no creature
    at all simply blights nothing - the mandatory instruction, unlike a
    "you may", has no legal object to put a counter on and does not crash or
    ask a question that has no legal answer."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["High Perfect Morcant"],
            battlefield=["Swamp", "Swamp", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Forest", "Forest", username="alice")

    scenario.cast_and_resolve("High Perfect Morcant", *sources, username="alice")
    scenario.pass_until_resolved()

    assert scenario.game.permanents_controlled_by("bob") == []


def test_target_opponent_blights_from_an_activated_ability():
    """Champion of the Weird: "Pay 1 life, Blight 2: Target opponent blights
    2. Activate only as a sorcery." The cost half (paying 1 life and
    blighting 2 of the activator's own creatures) is `machines/cost.py`'s
    existing "Pay N life"/blight-as-a-cost reading; this proves the *effect*
    half - the targeted opponent blighting their own creature for 2 - reads
    and runs.
    """
    scenario = (
        Scenario()
        # Both 2/10s, not 2/2s - each survives being blighted for 2 (CR
        # 704.5f would otherwise put a 0-toughness creature into the
        # graveyard as a new object, CR 400.7, with no counters left on it).
        .player("alice", battlefield=["Champion of the Weird", "Indomitable Ancients"])
        .player("bob", battlefield=["Indomitable Ancients"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    weird = scenario.creature("Champion of the Weird", "alice")
    weird.summoning_sick = False
    own_ancients = scenario.creature("Indomitable Ancients", "alice")
    their_ancients = scenario.creature("Indomitable Ancients", "bob")
    life_before = scenario.player("alice").life

    scenario.will_choose_cards(own_ancients, username="alice")
    scenario.will_choose_cards(their_ancients, username="bob")
    scenario.activate(weird, targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == life_before - 1
    assert own_ancients.counters[Counter.MINUS_ONE] == 2
    assert their_ancients.counters[Counter.MINUS_ONE] == 2


def test_casting_champion_of_the_weird_pays_behold_and_exile():
    """Champion of the Weird's own casting cost: "As an additional cost to
    cast this spell, behold a Goblin and exile it." CR 701.4a's behold
    (reveal a Goblin from hand, or choose one already on the battlefield) is
    layered with a second verb on the same object, CR 118.8/601.2f's "and
    exile it" - `machines/cost.py`'s `_PHRASE_BEHOLD` now reads the optional
    trailing "and exile it" clause and `pay` exiles the beheld object exactly
    like an ordinary exile cost. This proves the casting cost end-to-end;
    `test_target_opponent_blights_from_an_activated_ability` above already
    proves the activated ability's own blight effect on a Champion staged
    straight onto the battlefield.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champion of the Weird", "Goblin Guide"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.find("Goblin Guide", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")

    casting = scenario.cast("Champion of the Weird", username="alice", beholding=[goblin])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert goblin.zone is Zone.EXILE
    weird = scenario.creature("Champion of the Weird", "alice")
    assert weird.zone is Zone.BATTLEFIELD


def test_casting_champion_of_the_weird_beholds_a_battlefield_goblin():
    """CR 701.4a's other half: the beheld Goblin can be one already on the
    battlefield rather than one revealed from hand (CR 701.4b), and CR
    118.8's second verb ("and exile it") then moves it from there instead."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Champion of the Weird"],
            battlefield=["Goblin Guide", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Goblin Guide", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")

    casting = scenario.cast("Champion of the Weird", username="alice", beholding=[goblin])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert goblin.zone is Zone.EXILE

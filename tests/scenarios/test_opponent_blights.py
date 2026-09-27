"""CR 701.68a/701.68b performed by someone other than the ability's own
controller - "each opponent blights N" (High Perfect Morcant's own Elf-tribal
ETB) and "target opponent blights N" (Champion of the Weird's own activated
ability). `test_blight_positions.py` covers every position the controller's
own "you may blight N" prints in; this file is only about the blighting
player being someone else.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

import pytest

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


@pytest.mark.xfail(
    strict=True,
    reason="Champion of the Weird's own casting cost - 'As an additional cost to "
    "cast this spell, behold a Goblin and exile it.' - is genuinely unpayable today: "
    "machines/cost.py's `_PHRASE_BEHOLD` only reads a bare 'behold a <quality>' "
    "phrase, and 'behold a Goblin and exile it' raises "
    "\"Champion of the Weird's additional cost 'behold a Goblin and exile it' could "
    'not be read, so it cannot be paid (CR 118.3, 601.2f)" straight out of '
    "`mandatory_additional_costs` (verified this session). This is 270-ecl's own "
    "T4 task's 'behold-and-exile audit', named as this task's one dependency in "
    "the round notes ('merge after T4 or rebase on it before final sweep') - not "
    "a gap in this file's own blight-effect readers. Once T4 lands, this should "
    "legally exile the beheld Goblin, pay Blight 2 and 1 life for the activation, "
    "and blight bob's own creature for 2, the same way "
    "test_target_opponent_blights_from_an_activated_ability already proves the "
    "activated ability's own effect half works on a Champion of the Weird staged "
    "straight onto the battlefield.",
)
def test_casting_champion_of_the_weird_pays_behold_and_exile():
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

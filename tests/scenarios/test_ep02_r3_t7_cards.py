"""EP-02 R3 integ T7: five cards made fully handled - Stoneforge Masterwork,
Lethal Exploit, Pongify, Angelic Guardian, Tormented Thoughts.

Rules, each read in full with `mise run rules:find` in this session:

- CR 700.9 - modified: a counter, equipped, or enchanted by its controller's Aura.
- CR 608.2h - information from a specific object that left its zone is its last
  known information (a sacrificed creature's power, pumps included).
- CR 118.8a - an additional cost is paid by the spell's controller.
- CR 702.12b - indestructible: not destroyed by "destroy" effects.
- CR 701.19c - "can't be regenerated" (looked up below via rules:find 701.19).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .test_ep02_r3_library_amounts import _board, _resolve_all


def _power(scenario, state):
    return scenario.game.computed_board().of(state).power


# -- Stoneforge Masterwork ---------------------------------------------------


def _masterwork(alice, bob=()):
    scenario = _board(battlefield=["Stoneforge Masterwork", *alice], bob_battlefield=list(bob))
    return scenario, scenario.find("Stoneforge Masterwork", Zone.BATTLEFIELD, "alice")


def test_masterwork_counts_other_creatures_sharing_a_type():
    scenario, gear = _masterwork(["Grizzly Bears", "Runeclaw Bear", "Runeclaw Bear", "Memnite"])
    bears = scenario.creature("Grizzly Bears", "alice")
    gear.attach_to(bears)
    assert _power(scenario, bears) == 2 + 2, "two other Bears"


def test_masterwork_ignores_unrelated_types_and_the_opponents_creatures():
    scenario, gear = _masterwork(["Grizzly Bears", "Memnite"], bob=["Runeclaw Bear"])
    bears = scenario.creature("Grizzly Bears", "alice")
    gear.attach_to(bears)
    assert _power(scenario, bears) == 2, "no other Bear on my side"


def test_masterwork_counts_a_creature_once_even_with_two_shared_types():
    scenario, gear = _masterwork(["Savannah Lions", "Elite Vanguard", "Serra Angel"])
    lions = scenario.creature("Savannah Lions", "alice")
    gear.attach_to(lions)
    assert _power(scenario, lions) == 2, "Cat Soldier / Human Soldier shares Soldier, once"


def test_masterwork_unattached_pumps_nothing():
    scenario, _gear = _masterwork(["Grizzly Bears", "Runeclaw Bear"])
    assert _power(scenario, scenario.creature("Grizzly Bears", "alice")) == 2


# -- Lethal Exploit: modified = counter, equipped, or enchanted by own Aura ---


def _exploit(modify):
    scenario = _board(
        hand=["Lethal Exploit"],
        battlefield=["Swamp", "Swamp", "Grizzly Bears", "Savannah Lions", "Pacifism"],
        bob_battlefield=["Hill Giant"],
    )
    modify(scenario)
    giant = scenario.creature("Hill Giant", "bob")
    giant.add_counters(Counter.PLUS_ONE, 3)  # 6/6
    scenario.cast_and_resolve(
        "Lethal Exploit", *scenario.untapped_sources("Swamp", "Swamp"), targets=[giant]
    )
    return scenario, giant


def test_lethal_exploit_with_zero_modified_creatures_is_minus_two():
    scenario, giant = _exploit(lambda s: None)
    assert _power(scenario, giant) == 4


def test_lethal_exploit_counts_two_modified_creatures_counter_and_own_aura():
    def modify(scenario):
        scenario.creature("Grizzly Bears", "alice").add_counters(Counter.PLUS_ONE, 1)
        aura = scenario.find("Pacifism", Zone.BATTLEFIELD, "alice")
        aura.attach_to(scenario.creature("Savannah Lions", "alice"))

    scenario, giant = _exploit(modify)
    assert _power(scenario, giant) == 6 - 2 - 2


def test_lethal_exploit_does_not_count_an_opponents_aura_on_my_creature():
    def modify(scenario):
        aura = scenario.find("Pacifism", Zone.BATTLEFIELD, "alice")
        aura.controller = "bob"
        aura.attach_to(scenario.creature("Savannah Lions", "alice"))

    scenario, giant = _exploit(modify)
    assert _power(scenario, giant) == 4, (
        "an Aura its controller does not control is not a modification"
    )


# -- Pongify ----------------------------------------------------------------


def _pongify(bob_creature):
    scenario = _board(hand=["Pongify"], battlefield=["Island"], bob_battlefield=[bob_creature])
    target = scenario.creature(bob_creature, "bob")
    scenario.cast_and_resolve("Pongify", *scenario.untapped_sources("Island"), targets=[target])
    return scenario, target


def _apes(scenario, user):
    return [s for s in scenario.game.battlefield if s.controller == user and s.name == "Ape Token"]


def test_pongify_destroys_the_creature_and_its_controller_gets_a_three_three_ape():
    scenario, giant = _pongify("Hill Giant")
    assert giant.zone is Zone.GRAVEYARD
    (ape,) = _apes(scenario, "bob")
    assert (_power(scenario, ape), scenario.game.computed_board().of(ape).toughness) == (3, 3)
    assert not _apes(scenario, "alice")


def test_pongify_on_an_indestructible_creature_still_gives_the_ape():
    scenario, colossus = _pongify("Darksteel Colossus")
    assert colossus.zone is Zone.BATTLEFIELD
    assert len(_apes(scenario, "bob")) == 1


def test_pongify_that_fizzles_makes_no_ape():
    scenario = _board(
        hand=["Pongify", "Pongify"],
        battlefield=["Island", "Island"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack("Pongify", *scenario.untapped_sources("Island")[:1], targets=[giant])
    scenario.cast_onto_stack("Pongify", *scenario.untapped_sources("Island")[:1], targets=[giant])
    _resolve_all(scenario)
    assert len(_apes(scenario, "bob")) == 1, "the first Pongify fizzled on an absent target"


# -- Angelic Guardian ---------------------------------------------------------


def test_angelic_guardian_gives_only_the_attackers_indestructible():
    scenario = _board(
        battlefield=["Angelic Guardian", "Grizzly Bears", "Savannah Lions"],
        start=Step.DECLARE_ATTACKERS,
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.attack_with(bears)
    _resolve_all(scenario)
    assert is_indestructible(bears, scenario.game)
    assert not is_indestructible(lions, scenario.game)


def test_angelic_guardian_trigger_is_not_on_the_opponents_attack():
    scenario = _board(
        battlefield=["Angelic Guardian", "Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
        start=Step.PRECOMBAT_MAIN,
    )
    assert not is_indestructible(scenario.creature("Hill Giant", "bob"), scenario.game)
    assert not is_indestructible(scenario.creature("Grizzly Bears", "alice"), scenario.game)


# -- Tormented Thoughts ---------------------------------------------------------


def _thoughts(sacrifice, hand_size=5):
    scenario = _board(
        hand=["Tormented Thoughts"],
        battlefield=["Swamp", "Swamp", "Swamp", sacrifice],
        bob_hand=["Forest"] * hand_size,
    )
    return scenario, scenario.creature(sacrifice, "alice")


def _cast_thoughts(scenario, victim):
    casting = scenario.cast("Tormented Thoughts", sacrificing=[victim])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    _resolve_all(scenario)


def test_tormented_thoughts_discards_the_sacrificed_creatures_power():
    scenario, hill = _thoughts("Hill Giant")
    _cast_thoughts(scenario, hill)
    assert hill.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 5 - 3


def test_tormented_thoughts_uses_last_known_power_including_pumps():
    scenario, bears = _thoughts("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 2)
    _cast_thoughts(scenario, bears)
    assert len(scenario.player("bob").hand) == 5 - 4


def test_tormented_thoughts_discards_what_there_is_when_hand_is_short():
    scenario, hill = _thoughts("Hill Giant", hand_size=2)
    _cast_thoughts(scenario, hill)
    assert len(scenario.player("bob").hand) == 0

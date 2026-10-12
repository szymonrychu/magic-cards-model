"""Scenario: control-change triggers, control of an attached permanent, and
"return ... to the battlefield transformed under your control[ attached to
<target>]" death triggers (EP-01-R3 task T5).

Shapes, each read by a template reader and proven on a second printing that is
in no deck list here:

- A recurring "<player> gains control of <this>[, untaps it][, and puts N
  <kind> counters on it]. [It gains haste until end of turn.]" trigger -
  Alexios, Deimos of Kosmos ("that player" is the player whose upkeep it is)
  and Loxodon Peacekeeper ("the player with the lowest life total", with its
  own tie-break choice). CR 613.1b: layer 2 applies control-changing effects;
  CR 611.2a: with no duration stated the change lasts until the end of the
  game, so it outlives the turn and is only overwritten by a later, newer
  control change (CR 613.7's timestamp order inside a layer). CR 701.26b
  untaps, CR 122.6 puts the counter on, CR 702.10b haste lets the new
  controller attack at once.
- "with power less than this creature's power" on a target - Vodalian
  Mindsinger's ETB steal (CR 611.2b "for as long as" duration) and Unliving
  Psychopath's activated destroy. The bound is the source's *current* power,
  read off the layer system at announcement and again at resolution
  (CR 608.2b).
- "Kicker {X}. X can't be 0." - Thieving Skydiver. CR 107.3a: an additional
  cost with {X} in it has X announced while casting; "X can't be 0" bounds
  that choice only when the kicker is actually paid (CR 702.33a/702.33d). The
  ETB reads X back off the cast and "If that artifact is an Equipment, attach
  it to this creature" (CR 701.3a). Tamiyo's Compleation proves the
  "If it's an Equipment, unattach it" sibling (CR 701.3d).
- "You control enchanted Equipment." with "When this Aura enters, unattach
  enchanted Equipment." - Carry Away (CR 613.1b, CR 701.3d).
- "When <this creature|enchanted creature> dies, return <it|this card> to the
  battlefield transformed under your control[ attached to <target>]." -
  Accursed Witch, Radiant Grace, Skin Invasion; proven on Vengeful Strangler
  (target creature or planeswalker an opponent controls) and Journey to
  Eternity (the enchanted creature comes back first, then the Aura).
  CR 712.14a: the card enters with its back face up. CR 303.4f: an Aura put
  onto the battlefield by an effect that names what it will enchant enters
  attached to that object or player. CR 400.7: the card that died is a new
  object in the graveyard, and only that card is returned.

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file: 613.1b, 611.2a, 611.2b, 613.7, 701.26b, 122.6, 702.10b,
608.2b, 107.3a, 702.33a, 702.33d, 701.3a, 701.3d, 712.14a, 303.4f, 400.7,
603.3d, 704.5m.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import pool
from tests.scenarios.harness import Scenario, mana_from

T5_CARDS = [
    "Alexios, Deimos of Kosmos",
    "Vodalian Mindsinger",
    "Thieving Skydiver",
    "Carry Away",
    "Accursed Witch // Infectious Curse",
    "Radiant Grace // Radiant Restraints",
    "Skin Invasion // Skin Shedder",
]

PROOF_CARDS = [
    "Loxodon Peacekeeper",
    "Unliving Psychopath",
    "Tamiyo's Compleation",
    "Vengeful Strangler // Strangling Grasp",
    "Journey to Eternity // Atzal, Cave of Eternity",
]


@pytest.mark.parametrize("name", T5_CARDS + PROOF_CARDS)
def test_every_clause_of_the_card_is_handled(name):
    support = card_support(pool()[name])
    unhandled = [(c.kind, c.status, c.text) for c in support.clauses if c.status != "handled"]
    assert support.status == "handled", unhandled
    assert not unhandled


def _to_upkeep_of(scenario, username: str) -> None:
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == username):
        scenario.advance()


def _offered_targets(scenario) -> set:
    """The card ids the last CHOOSE_TARGETS question offered."""
    asked = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_TARGETS]
    assert asked, "a target was asked for"
    return {ref.card_id for ref in asked[-1].targets if ref.is_card}


def _resolve_all(scenario) -> None:
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()


# -- Alexios, Deimos of Kosmos: "At the beginning of each player's upkeep, that
# player gains control of Alexios, untaps it, and puts a +1/+1 counter on it. It
# gains haste until end of turn." ------------------------------------------------


def _alexios_board():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 6, battlefield=["Alexios, Deimos of Kosmos"])
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    return scenario, scenario.creature("Alexios, Deimos of Kosmos", "alice")


def test_alexios_stays_with_its_controller_on_their_own_upkeep_and_grows():
    scenario, alexios = _alexios_board()
    alexios.tapped = True
    scenario.advance()  # alice's upkeep (the untap step untapped it already)
    alexios.tapped = True
    _resolve_all(scenario)

    assert alexios.controller == "alice"
    assert not alexios.tapped, "CR 701.26b: it untaps"
    assert alexios.counters[Counter.PLUS_ONE] == 1
    assert scenario.game.computed_board().of(alexios).has_ability("Haste")


def test_alexios_goes_to_the_player_whose_upkeep_it_is():
    scenario, alexios = _alexios_board()
    scenario.advance()
    _resolve_all(scenario)
    alexios.tapped = True
    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)

    board = scenario.game.computed_board()
    assert alexios.controller == "bob"
    assert board.of(alexios).controller == "bob"
    assert alexios.owner == "alice", "CR 108.3: ownership never changes"
    assert not alexios.tapped
    assert alexios.counters[Counter.PLUS_ONE] == 2
    assert board.of(alexios).has_ability("Haste"), "CR 702.10b: haste until end of turn"


def test_alexios_comes_back_on_its_owners_next_upkeep_and_haste_wore_off():
    scenario, alexios = _alexios_board()
    scenario.advance()
    _resolve_all(scenario)
    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)
    scenario.start_at(Step.END_STEP)
    _resolve_all(scenario)
    scenario.advance()  # cleanup: CR 514.2 ends "until end of turn"
    assert not scenario.game.computed_board().of(alexios).has_ability("Haste")
    assert alexios.controller == "bob", "CR 611.2a: no duration, the change stays"

    _to_upkeep_of(scenario, "alice")
    _resolve_all(scenario)
    assert alexios.controller == "alice"
    assert alexios.counters[Counter.PLUS_ONE] == 3


def test_alexios_that_left_the_battlefield_gives_nobody_anything():
    """CR 400.7: the trigger's object is gone, so no control change happens."""
    scenario, alexios = _alexios_board()
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.game.exile_permanent(alexios)
    _resolve_all(scenario)
    assert alexios.zone is Zone.EXILE
    assert alexios.counters[Counter.PLUS_ONE] == 0


# -- Loxodon Peacekeeper (proof): "At the beginning of your upkeep, the player
# with the lowest life total gains control of this creature. If two or more
# players are tied for lowest life total, you choose one of them, and that
# player gains control of this creature." ---------------------------------------


def _peacekeeper(alice_life: int, bob_life: int, charlie_life: int | None = None):
    builder = (
        Scenario()
        .player(
            "alice", life=alice_life, library=["Forest"] * 6, battlefield=["Loxodon Peacekeeper"]
        )
        .player("bob", life=bob_life, library=["Forest"] * 6)
    )
    if charlie_life is not None:
        builder = builder.player("charlie", life=charlie_life, library=["Forest"] * 6)
    scenario = builder.build()
    scenario.start_at(Step.UNTAP)
    return scenario, scenario.creature("Loxodon Peacekeeper", "alice")


def test_peacekeeper_goes_to_the_player_with_the_lowest_life():
    scenario, keeper = _peacekeeper(20, 7)
    scenario.advance()
    _resolve_all(scenario)
    assert keeper.controller == "bob"
    assert keeper.owner == "alice"


def test_peacekeeper_stays_when_its_controller_is_lowest():
    scenario, keeper = _peacekeeper(3, 20)
    scenario.advance()
    _resolve_all(scenario)
    assert keeper.controller == "alice"


def test_peacekeeper_tie_is_its_controllers_choice_among_the_tied():
    scenario, keeper = _peacekeeper(20, 5, 5)
    scenario.will_choose_players("charlie", username="alice")
    scenario.advance()
    _resolve_all(scenario)
    asked = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_PLAYERS]
    assert asked, "the tie is a choice, not a default"
    assert set(asked[-1].players) == {"bob", "charlie"}, "only the tied players are offered"
    assert keeper.controller == "charlie"


def test_peacekeeper_does_not_trigger_on_an_opponents_upkeep():
    scenario, keeper = _peacekeeper(20, 20)
    scenario.will_choose_players("alice", username="alice")
    scenario.advance()
    _resolve_all(scenario)
    assert keeper.controller == "alice"
    scenario.player("alice").life = 2
    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)
    assert keeper.controller == "alice", "your upkeep only"


# -- "with power less than this creature's power" -------------------------------


def _mindsinger(kicks: tuple[str, ...], bob_creatures: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 3,
            hand=["Vodalian Mindsinger", "Shock"],
            battlefield=["Island"] * 3 + ["Mountain", "Mountain", "Forest", "Forest"],
        )
        .player("bob", library=["Island"] * 3, battlefield=bob_creatures)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Vodalian Mindsinger", Zone.HAND, "alice")
    lands = scenario.untapped_sources(
        "Island",
        "Island",
        "Island",
        *(["Mountain", "Forest"][: len(kicks)] * 2)[: 2 * len(kicks)],
        username="alice",
    )
    return scenario, card, lands


def test_a_doubly_kicked_mindsinger_steals_a_smaller_creature_for_as_long_as_it_stays():
    scenario, card, _ = _mindsinger(("{1}{R}", "{1}{G}"), ["Hill Giant", "Craw Wurm"])
    giant = scenario.creature("Hill Giant", "bob")
    lands = scenario.untapped_sources(
        "Island", "Island", "Island", "Mountain", "Mountain", "Forest", "Forest", username="alice"
    )
    scenario.will_choose_targets(giant)
    scenario.game.cast(card, "alice", kicker_costs=["{1}{R}", "{1}{G}"], mana_sources=lands)
    _resolve_all(scenario)
    mindsinger = scenario.creature("Vodalian Mindsinger", "alice")
    assert scenario.game.computed_board().of(mindsinger).power == 6
    assert giant.controller == "alice"

    scenario.game.destroy(mindsinger)
    _resolve_all(scenario)
    assert giant.controller == "bob", "CR 611.2b: the duration ended with the Mindsinger"


def test_an_unkicked_mindsinger_can_only_target_power_below_two():
    scenario, card, _ = _mindsinger((), ["Llanowar Elves", "Grizzly Bears"])
    elves = scenario.creature("Llanowar Elves", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    lands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.will_choose_targets(elves)
    scenario.game.cast(card, "alice", mana_sources=lands)
    _resolve_all(scenario)
    offered = _offered_targets(scenario)
    assert elves.id in offered
    assert bears.id not in offered, "power 2 is not less than the Mindsinger's 2"
    assert elves.controller == "alice"


def test_mindsinger_steal_is_rechecked_against_its_power_on_resolution():
    """CR 608.2b: the target grew to the Mindsinger's power in response."""
    scenario, card, _ = _mindsinger((), ["Llanowar Elves"])
    elves = scenario.creature("Llanowar Elves", "bob")
    lands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.will_choose_targets(elves)
    scenario.game.cast(card, "alice", mana_sources=lands)
    scenario.pass_until_resolved()  # the creature spell
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names(), "the steal is waiting on the stack"
    scenario.game.add_counters(elves, Counter.PLUS_ONE, 1)
    _resolve_all(scenario)
    assert elves.controller == "bob", "an illegal target on resolution: nothing happens"


def _psychopath(bob_creature: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Swamp"], battlefield=["Unliving Psychopath"] + ["Swamp"] * 3)
        .player("bob", library=["Swamp"], battlefield=[bob_creature])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Unliving Psychopath", "alice")


def test_psychopath_at_zero_power_has_nothing_smaller_to_destroy():
    """A 0/4: not even a 0-power Ornithopter has power less than 0."""
    scenario, psycho = _psychopath("Ornithopter")
    thopter = scenario.creature("Ornithopter", "bob")
    (swamp, *_) = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    with pytest.raises(ValueError, match="power less than 0"):
        scenario.activate(psycho, swamp, index=1, username="alice", targets=[thopter])
    assert thopter.zone is Zone.BATTLEFIELD


def test_psychopath_pumped_by_its_own_ability_reads_its_current_power():
    """CR 613.5: two "{B}: This creature gets +1/-1" make it a 2/2, and the
    1-power Llanowar Elves is now a legal target - but a 2-power Grizzly Bears
    still is not."""
    scenario, psycho = _psychopath("Llanowar Elves")
    elves = scenario.creature("Llanowar Elves", "bob")
    first, second, third = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    with pytest.raises(ValueError):
        scenario.activate(psycho, first, index=1, username="alice", targets=[elves])
    for swamp in (first, second):
        scenario.activate(psycho, swamp, index=0, username="alice")
        _resolve_all(scenario)
    assert scenario.game.computed_board().of(psycho).power == 2
    scenario.activate(psycho, third, index=1, username="alice", targets=[elves])
    _resolve_all(scenario)
    assert elves.zone is Zone.GRAVEYARD


# -- Thieving Skydiver: "Kicker {X}. X can't be 0." and its kicked ETB ----------


def _skydiver(bob_battlefield: list[str], lands: int = 5):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", library=["Island"], hand=["Thieving Skydiver"], battlefield=["Island"] * lands
        )
        .player("bob", library=["Island"], battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find("Thieving Skydiver", Zone.HAND, "alice")


def test_skydiver_unkicked_is_cast_for_its_mana_cost_and_steals_nothing():
    scenario, card = _skydiver(["Ornithopter"])
    thopter = scenario.creature("Ornithopter", "bob")
    lands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.game.cast(card, "alice", mana_sources=lands)
    _resolve_all(scenario)
    assert card.zone is Zone.BATTLEFIELD
    assert thopter.controller == "bob", "not kicked: the ETB's intervening if is false"


def test_skydiver_kicked_with_x_zero_is_refused():
    scenario, card = _skydiver(["Ornithopter"])
    lands = scenario.untapped_sources("Island", "Island", username="alice")
    with pytest.raises(ValueError, match="X can't be 0"):
        scenario.game.cast(card, "alice", x_value=0, kicker=1, mana_sources=lands)


def test_skydiver_kicked_for_x_steals_an_equipment_and_wears_it():
    scenario, card = _skydiver(["Bonesplitter", "Grizzly Bears"])
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    splitter.attach_to(bears)
    lands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.will_choose_targets(splitter)
    scenario.game.cast(card, "alice", x_value=1, kicker=1, mana_sources=lands)
    assert all(land.tapped for land in lands), "{1}{U} plus kicker {X} with X=1"
    _resolve_all(scenario)
    skydiver = scenario.creature("Thieving Skydiver", "alice")
    assert splitter.controller == "alice"
    assert splitter.attached_to == skydiver.id, "CR 701.3a: attached to this creature"
    assert scenario.game.computed_board().of(skydiver).power == 4


def test_skydiver_steals_a_plain_artifact_without_attaching_it():
    scenario, card = _skydiver(["Ornithopter"])
    thopter = scenario.creature("Ornithopter", "bob")
    lands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.will_choose_targets(thopter)
    scenario.game.cast(card, "alice", x_value=1, kicker=1, mana_sources=lands)
    _resolve_all(scenario)
    assert thopter.controller == "alice"
    assert thopter.attachment is None


def test_skydiver_x_bounds_the_artifacts_mana_value():
    scenario, card = _skydiver(["Cranial Plating", "Ornithopter"])
    plating = scenario.find("Cranial Plating", Zone.BATTLEFIELD, "bob")
    thopter = scenario.creature("Ornithopter", "bob")
    lands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.will_choose_targets(thopter)
    scenario.game.cast(card, "alice", x_value=1, kicker=1, mana_sources=lands)
    _resolve_all(scenario)
    assert plating.id not in _offered_targets(scenario), "mana value 2 is more than X=1"
    assert plating.controller == "bob"


# -- Tamiyo's Compleation (proof): "When this Aura enters, tap enchanted
# permanent. If it's an Equipment, unattach it." --------------------------------


def _compleation(bob_battlefield: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", library=["Island"], hand=["Tamiyo's Compleation"], battlefield=["Island"] * 4
        )
        .player("bob", library=["Island"], battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_compleation_taps_and_unattaches_an_equipment():
    scenario = _compleation(["Bonesplitter", "Grizzly Bears"])
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    splitter.attach_to(bears)
    scenario.cast_and_resolve(
        "Tamiyo's Compleation",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
        targets=[splitter],
    )
    _resolve_all(scenario)
    assert splitter.tapped
    assert splitter.attachment is None, "CR 701.3d: unattached"
    assert scenario.game.computed_board().of(bears).power == 2


def test_compleation_on_a_creature_taps_it_and_unattaches_nothing():
    scenario = _compleation(["Bonesplitter", "Grizzly Bears"])
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    splitter.attach_to(bears)
    scenario.cast_and_resolve(
        "Tamiyo's Compleation",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
        targets=[bears],
    )
    _resolve_all(scenario)
    assert bears.tapped
    assert splitter.attached_to == bears.id, "not an Equipment: nothing unattaches"


# -- Carry Away: "When this Aura enters, unattach enchanted Equipment." / "You
# control enchanted Equipment." ---------------------------------------------------


def _carry_away():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"],
            hand=["Carry Away", "Nature's Claim"],
            battlefield=["Island", "Island", "Forest", "Grizzly Bears"],
        )
        .player("bob", library=["Island"], battlefield=["Bonesplitter", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")
    giant = scenario.creature("Hill Giant", "bob")
    splitter.attach_to(giant)
    scenario.cast_and_resolve(
        "Carry Away", *scenario.untapped_sources("Island", "Island"), targets=[splitter]
    )
    _resolve_all(scenario)
    return scenario, splitter, giant


def test_carry_away_takes_the_equipment_off_its_creature_and_gives_it_to_you():
    scenario, splitter, giant = _carry_away()
    carry = scenario.find("Carry Away", Zone.BATTLEFIELD, "alice")
    assert carry.attached_to == splitter.id
    assert splitter.attachment is None, "CR 701.3d: unattached from the Hill Giant"
    assert scenario.game.computed_board().of(giant).power == 3
    assert splitter.controller == "alice"
    assert splitter.owner == "bob"


def test_the_stolen_equipment_can_be_equipped_by_its_new_controller():
    scenario, splitter, _ = _carry_away()
    bears = scenario.creature("Grizzly Bears", "alice")
    activation = equip_activation(scenario.game, splitter, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Forest"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    _resolve_all(scenario)
    assert splitter.attached_to == bears.id
    assert scenario.game.computed_board().of(bears).power == 4


def test_control_returns_when_carry_away_leaves():
    """CR 611.3a: the static stops applying with its source gone."""
    scenario, splitter, giant = _carry_away()
    carry = scenario.find("Carry Away", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve(
        "Nature's Claim", *scenario.untapped_sources("Forest"), targets=[carry]
    )
    assert carry.zone is Zone.GRAVEYARD
    assert splitter.controller == "bob"
    assert splitter.attachment is None, "it does not jump back onto the Giant"


def test_steal_artifact_still_reads_the_same_static():
    """The widened "You control enchanted <noun>" reader on its original noun."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"], hand=["Steal Artifact"], battlefield=["Island"] * 4)
        .player("bob", library=["Island"], battlefield=["Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "bob")
    scenario.cast_and_resolve(
        "Steal Artifact",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
        targets=[thopter],
    )
    assert thopter.controller == "alice"


# -- "return ... to the battlefield transformed under your control[ attached to
# <target>]" ---------------------------------------------------------------------


def test_accursed_witch_returns_as_a_curse_on_the_targeted_opponent():
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"] * 6, battlefield=["Accursed Witch"])
        .player("bob", library=["Swamp"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    witch = scenario.creature("Accursed Witch", "alice")
    scenario.will_choose_targets("bob")
    scenario.game.destroy(witch)
    _resolve_all(scenario)

    assert witch.zone is Zone.BATTLEFIELD
    assert witch.transformed
    assert witch.name == "Infectious Curse"
    assert witch.controller == "alice"
    assert witch.attachment is not None and not witch.attachment.is_card
    assert witch.attachment.username == "bob", "CR 303.4f: attached to the target opponent"

    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


def test_accursed_witch_exiled_from_the_graveyard_in_response_stays_exiled():
    """CR 400.7: a card that left the graveyard is a new object."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Swamp"], battlefield=["Accursed Witch"])
        .player("bob", library=["Swamp"], battlefield=["Tormod's Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    witch = scenario.creature("Accursed Witch", "alice")
    scenario.will_choose_targets("bob")
    scenario.game.destroy(witch)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()
    scenario.resolve_top()
    assert witch.zone is Zone.EXILE
    assert "Infectious Curse" not in scenario.battlefield_names()


def _radiant(host_owner: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Plains"],
            hand=["Radiant Grace", "Shock"],
            battlefield=["Plains", "Mountain", "Grizzly Bears"],
        )
        .player(
            "bob",
            library=["Plains"],
            hand=["Llanowar Elves"],
            battlefield=["Llanowar Elves", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    host = scenario.creature(
        "Grizzly Bears" if host_owner == "alice" else "Llanowar Elves", host_owner
    )
    scenario.cast_and_resolve("Radiant Grace", *scenario.untapped_sources("Plains"), targets=[host])
    grace = scenario.find("Radiant Grace", Zone.BATTLEFIELD, "alice")
    return scenario, grace, host


def test_radiant_grace_returns_as_restraints_on_the_targeted_opponent():
    scenario, grace, host = _radiant("alice")
    assert scenario.game.computed_board().of(host).power == 3
    scenario.will_choose_targets("bob")
    scenario.game.destroy(host)
    _resolve_all(scenario)

    assert grace.zone is Zone.BATTLEFIELD
    assert grace.name == "Radiant Restraints"
    assert grace.controller == "alice"
    assert grace.attachment is not None and grace.attachment.username == "bob"

    elves = scenario.find("Llanowar Elves", Zone.HAND, "bob")
    scenario.game.put_onto_battlefield(elves, "bob")
    assert elves.tapped, "Creatures enchanted player controls enter tapped"


def test_radiant_grace_on_an_opponents_creature_still_comes_back_under_your_control():
    scenario, grace, host = _radiant("bob")
    scenario.will_choose_targets("bob")
    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=[host])
    _resolve_all(scenario)
    assert grace.name == "Radiant Restraints"
    assert grace.controller == "alice", '"under your control" - the Aura\'s controller'
    assert grace.attachment.username == "bob"


def test_skin_invasion_comes_back_as_skin_shedder():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Mountain"],
            hand=["Skin Invasion", "Shock"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", library=["Mountain"], battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "bob")
    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Skin Invasion", first, targets=[elves])
    invasion = scenario.find("Skin Invasion", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve("Shock", second, targets=[elves])
    _resolve_all(scenario)

    assert invasion.zone is Zone.BATTLEFIELD
    assert invasion.transformed
    assert invasion.name == "Skin Shedder"
    assert invasion.controller == "alice"
    assert invasion.attachment is None
    board = scenario.game.computed_board()
    assert (board.of(invasion).power, board.of(invasion).toughness) == (3, 4)


def test_skin_invasion_that_was_not_on_the_creature_stays_put():
    """Only the death of the creature it enchants triggers it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Mountain"],
            hand=["Skin Invasion", "Shock"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", library=["Mountain"], battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Skin Invasion", first, targets=[bears])
    invasion = scenario.find("Skin Invasion", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve("Shock", second, targets=[elves])
    _resolve_all(scenario)
    assert invasion.name == "Skin Invasion"
    assert invasion.attached_to == bears.id


def _strangler(bob_battlefield: list[str]):
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"] * 6, battlefield=["Vengeful Strangler", "Swamp"])
        .player("bob", library=["Swamp"] * 6, battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Vengeful Strangler", "alice")


def test_vengeful_strangler_returns_attached_to_an_opponents_creature():
    scenario, strangler = _strangler(["Grizzly Bears", "Ornithopter", "Swamp"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears)
    scenario.game.destroy(strangler)
    _resolve_all(scenario)

    assert strangler.name == "Strangling Grasp"
    assert strangler.controller == "alice"
    assert strangler.attached_to == bears.id

    _to_upkeep_of(scenario, "bob")
    _resolve_all(scenario)
    assert scenario.player("bob").life == 20, "your upkeep only - not bob's"
    thopter = scenario.creature("Ornithopter", "bob")
    scenario.will_choose_cards(thopter, username="bob")
    _to_upkeep_of(scenario, "alice")
    _resolve_all(scenario)
    assert thopter.zone is Zone.GRAVEYARD, "the enchanted permanent's controller chose"
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 19, "then that player loses 1 life"
    assert scenario.player("alice").life == 20


def test_vengeful_strangler_with_no_legal_target_stays_in_the_graveyard():
    """CR 603.3d: a trigger with no legal target is removed from the stack."""
    scenario, strangler = _strangler(["Swamp"])
    scenario.game.destroy(strangler)
    _resolve_all(scenario)
    assert strangler.zone is Zone.GRAVEYARD


def test_journey_to_eternity_returns_the_creature_then_itself_as_atzal():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Swamp"],
            hand=["Journey to Eternity", "Shock"],
            battlefield=["Swamp", "Forest", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Journey to Eternity",
        *scenario.untapped_sources("Swamp", "Forest", "Mountain"),
        targets=[bears],
    )
    journey = scenario.find("Journey to Eternity", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=[bears])
    _resolve_all(scenario)

    assert bears.zone is Zone.BATTLEFIELD and bears.controller == "alice"
    assert journey.zone is Zone.BATTLEFIELD
    assert journey.name == "Atzal, Cave of Eternity"
    assert journey.attachment is None

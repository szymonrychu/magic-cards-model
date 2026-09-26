"""Scenario: "becomes prepared" / "becomes unprepared" in every trigger
position Secrets of Strixhaven prints it (CR 722.3a, 722.3b).

CR 722.3a: "Some spells and abilities cause a permanent with a prepare spell
to become prepared ... A permanent can't gain this designation unless it has
a prepare spell. Additionally, a permanent can't gain this designation if the
permanent already has it." CR 722.3b: "A rule or effect may cause a permanent
to become 'unprepared.' This removes the prepared designation from that
permanent." CR 722.3c: the exile copy "remains in exile for as long as the
prepared permanent remains on the battlefield and has the prepared
designation."

- **Emeritus of Ideation** - "Whenever this creature attacks, you may exile
  eight cards from your graveyard. If you do, this creature becomes
  prepared." CR 118.12 makes the exile a cost paid on resolution; CR 118.3
  forbids paying it without eight cards to exile.
- **Emeritus of Truce** - "When this creature enters, target player creates a
  1/1 white and black Inkling creature token with flying. Then if an
  opponent controls more creatures than you, this creature becomes
  prepared." The condition is read after the token exists (CR 608.2c), so
  handing the token to the opponent can be what prepares it.
- **Biblioplex Tomekeeper** - "When this creature enters, choose up to one -
  Target creature becomes prepared. / Target creature becomes unprepared."
  (CR 700.2b, 603.3c: choosing no mode removes the ability.)

Generality: **Hunted Horror** (Modern) - "When this creature enters, target
opponent creates two 3/3 green Centaur creature tokens with protection from
black." - now read by the same clause-level "target player creates" reader
Emeritus of Truce's trigger needs. **Aegis Sculptor** (Standard) - "At the beginning of your upkeep,
you may exile two cards from your graveyard. If you do, put a +1/+1 counter
on this creature." - the same exile-from-graveyard cost with a different
count, trigger and consequence. "Target creature becomes unprepared." is
printed on Biblioplex Tomekeeper alone (no other printing in any format
carries it), so its reader is proven on every kind of target it can meet
here: prepared, never prepared, and an opponent's permanent.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.effects import NO_FURTHER_MODES
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import PlayedScenario, Scenario

IDEATION = "Emeritus of Ideation"
TRUCE = "Emeritus of Truce"
TOMEKEEPER = "Biblioplex Tomekeeper"
PREPARE_MODE = "Target creature becomes prepared."
UNPREPARE_MODE = "Target creature becomes unprepared."


def _copies_of(scenario: PlayedScenario, permanent) -> list:
    return [state for state in scenario.game.exile if state.id == permanent.prepared_copy_id]


# -- Emeritus of Ideation: "you may exile eight ... If you do, ... prepared" --


def _ideation_board(graveyard: int) -> tuple[PlayedScenario, object]:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[IDEATION], graveyard=["Island"] * graveyard)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emeritus = scenario.creature(IDEATION)
    scenario.game.become_unprepared(emeritus)
    assert emeritus.prepared is False
    return scenario, emeritus


def _attack(scenario: PlayedScenario, creature) -> None:
    scenario.advance()
    scenario.advance()
    scenario.attack_with(creature)
    scenario.pass_until_resolved()


def test_exiling_eight_cards_prepares_the_attacker():
    scenario, emeritus = _ideation_board(graveyard=9)
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(*scenario.player("alice").graveyard[:8], username="alice")

    _attack(scenario, emeritus)

    assert len(scenario.player("alice").graveyard) == 1
    assert emeritus.prepared is True
    (copy,) = _copies_of(scenario, emeritus)
    assert copy.name == "Ancestral Recall"


def test_declining_exiles_nothing_and_leaves_it_unprepared():
    scenario, emeritus = _ideation_board(graveyard=8)
    scenario.will_take_the_may(False, username="alice")

    _attack(scenario, emeritus)

    assert len(scenario.player("alice").graveyard) == 8
    assert emeritus.prepared is False


def test_with_fewer_than_eight_cards_the_cost_cannot_be_paid():
    """CR 118.3: no question is asked and nothing is exiled."""
    scenario, emeritus = _ideation_board(graveyard=7)

    _attack(scenario, emeritus)

    assert len(scenario.player("alice").graveyard) == 7
    assert emeritus.prepared is False
    assert not [q for q in scenario.questions_asked() if q.source == IDEATION]


def test_an_already_prepared_attacker_still_pays_but_gains_no_second_copy():
    """CR 722.3a: the designation can't be gained twice; CR 118.12's cost is
    still the player's to pay."""
    scenario, emeritus = _ideation_board(graveyard=8)
    scenario.game.become_prepared(emeritus)
    first_copy = emeritus.prepared_copy_id
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(*scenario.player("alice").graveyard[:8], username="alice")

    _attack(scenario, emeritus)

    assert len(scenario.player("alice").graveyard) == 0
    assert emeritus.prepared_copy_id == first_copy
    assert len([s for s in scenario.game.exile if s.card.id == emeritus.card.id]) == 1


def test_aegis_sculptor_pays_the_same_cost_for_a_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Aegis Sculptor"],
            graveyard=["Island"] * 3,
            library=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    sculptor = scenario.creature("Aegis Sculptor")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(*scenario.player("alice").graveyard[:2], username="alice")

    while scenario.step is not Step.UPKEEP:
        scenario.advance()
    scenario.pass_until_resolved()

    assert sculptor.counters[Counter.PLUS_ONE] == 1
    assert len(scenario.player("alice").graveyard) == 1


def test_aegis_sculptor_with_one_card_gets_no_counter():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Aegis Sculptor"], graveyard=["Island"], library=["Island"] * 3
        )
        .player("bob")
        .build()
    )
    sculptor = scenario.creature("Aegis Sculptor")

    while scenario.step is not Step.UPKEEP:
        scenario.advance()
    scenario.pass_until_resolved()

    assert sculptor.counters[Counter.PLUS_ONE] == 0
    assert len(scenario.player("alice").graveyard) == 1


# -- Emeritus of Truce: token, then an intervening-free "then if" ------------


def _truce_board(bob_creatures: list[str]) -> PlayedScenario:
    scenario = (
        Scenario().player("alice", hand=[TRUCE]).player("bob", battlefield=bob_creatures).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_truce(scenario: PlayedScenario, target_player: str):
    scenario.will_choose_targets(target_player, username="alice")
    emeritus = scenario.put_onto_battlefield(TRUCE, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    return emeritus


def _inklings(scenario: PlayedScenario, username: str) -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if is_token(state) and state.name.startswith("Inkling")
    ]


def test_truce_gives_you_the_inkling_and_prepares_when_you_are_still_behind():
    scenario = _truce_board(["Grizzly Bears", "Grizzly Bears", "Grizzly Bears"])

    emeritus = _enter_truce(scenario, "alice")

    assert len(_inklings(scenario, "alice")) == 1
    assert emeritus.prepared is True, "2 creatures against 3"
    (copy,) = _copies_of(scenario, emeritus)
    assert copy.name == "Swords to Plowshares"


def test_truce_does_not_prepare_once_the_inkling_evens_the_count():
    scenario = _truce_board(["Grizzly Bears", "Grizzly Bears"])

    emeritus = _enter_truce(scenario, "alice")

    assert len(_inklings(scenario, "alice")) == 1
    assert emeritus.prepared is False, "2 creatures against 2 is not more"


def test_truce_handing_the_inkling_to_the_opponent_is_what_prepares_it():
    """CR 608.2c: the condition is read after the token is created."""
    scenario = _truce_board(["Grizzly Bears"])

    emeritus = _enter_truce(scenario, "bob")

    assert len(_inklings(scenario, "bob")) == 1
    assert _inklings(scenario, "alice") == []
    assert emeritus.prepared is True, "bob's 2 creatures against alice's 1"


def test_truce_inkling_is_a_flying_1_1():
    scenario = _truce_board([])

    _enter_truce(scenario, "alice")

    (inkling,) = _inklings(scenario, "alice")
    computed = scenario.game.characteristics_of(inkling)
    assert (computed.power, computed.toughness) == (1, 1)
    assert has_keyword(inkling, Keyword.FLYING, scenario.game)


def test_hunted_horror_reads_the_same_target_player_creates_clause():
    """The clause-level "target opponent creates <token>" reader Emeritus of
    Truce's trigger needs is the one Hunted Horror's whole ETB now goes
    through too (Modern, not a listed card, not in a deck)."""
    scenario = Scenario().player("alice", hand=["Hunted Horror"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob", username="alice")

    scenario.put_onto_battlefield("Hunted Horror", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    centaurs = [
        state
        for state in scenario.game.permanents_controlled_by("bob")
        if is_token(state) and state.name.startswith("Centaur")
    ]
    assert len(centaurs) == 2
    assert all(scenario.game.characteristics_of(c).power == 3 for c in centaurs)
    assert [s for s in scenario.game.permanents_controlled_by("alice") if is_token(s)] == []


# -- Biblioplex Tomekeeper: choose up to one ------------------------------------


def _tomekeeper_board(alice: list[str], bob: list[str] | None = None) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[TOMEKEEPER], battlefield=alice)
        .player("bob", battlefield=bob or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_tomekeeper(scenario: PlayedScenario) -> None:
    scenario.put_onto_battlefield(TOMEKEEPER, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_tomekeeper_prepares_a_creature_with_a_prepare_spell():
    scenario = _tomekeeper_board(["Scathing Shadelock"])
    shadelock = scenario.creature("Scathing Shadelock")
    scenario.will_choose_mode(PREPARE_MODE, username="alice")
    scenario.will_choose_targets(shadelock, username="alice")

    _enter_tomekeeper(scenario)

    assert shadelock.prepared is True
    (copy,) = _copies_of(scenario, shadelock)
    assert copy.name == "Venomous Words"


def test_tomekeeper_unprepares_a_prepared_creature_and_its_copy_goes():
    """CR 722.3b, and CR 722.3c's "for as long as" - the exile copy leaves
    with the designation."""
    scenario = _tomekeeper_board([], bob=["Scathing Shadelock"])
    shadelock = scenario.creature("Scathing Shadelock", "bob")
    copy = scenario.game.become_prepared(shadelock)
    assert copy is not None
    scenario.will_choose_mode(UNPREPARE_MODE, username="alice")
    scenario.will_choose_targets(shadelock, username="alice")

    _enter_tomekeeper(scenario)

    assert shadelock.prepared is False
    assert shadelock.prepared_copy_id is None
    assert copy not in scenario.game.exile
    assert scenario.game.play_permission_for(copy, "bob") is None


def test_tomekeeper_unpreparing_an_unprepared_creature_does_nothing():
    scenario = _tomekeeper_board(["Scathing Shadelock"])
    shadelock = scenario.creature("Scathing Shadelock")
    scenario.will_choose_mode(UNPREPARE_MODE, username="alice")
    scenario.will_choose_targets(shadelock, username="alice")

    _enter_tomekeeper(scenario)

    assert shadelock.prepared is False
    assert scenario.stack_names() == []


def test_tomekeeper_preparing_a_creature_with_no_prepare_spell_does_nothing():
    """CR 722.3a: "A permanent can't gain this designation unless it has a
    prepare spell.\""""
    scenario = _tomekeeper_board(["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    exile_before = len(scenario.game.exile)
    scenario.will_choose_mode(PREPARE_MODE, username="alice")
    scenario.will_choose_targets(bears, username="alice")

    _enter_tomekeeper(scenario)

    assert bears.prepared is False
    assert len(scenario.game.exile) == exile_before


def test_tomekeeper_may_choose_no_mode_at_all():
    """CR 700.2b / 603.3c: with no mode chosen the ability is removed."""
    scenario = _tomekeeper_board(["Scathing Shadelock"])
    shadelock = scenario.creature("Scathing Shadelock")
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")

    scenario.put_onto_battlefield(TOMEKEEPER, "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert shadelock.prepared is False

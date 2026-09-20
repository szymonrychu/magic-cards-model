"""fra-final-audit batch A item 5: the 7 "enters prepared" fronts the audit
found with no scenario test naming them by name - `scripts/sweep_pool.py`'s
own `static_unaudited` report (before this file, and before the classifier
fix in `tests/test_sweep_pool.py`) could not tell these apart from a card
whose "enters prepared" line was genuinely unread, because nothing anywhere
played them through the engine.

CR 722.3a: "Some spells and abilities cause a permanent with a prepare spell
to become prepared or state that a permanent enters prepared. ... this gives
the permanent the 'prepared' designation." CR 722.3c: "As a permanent with a
prepare spell gains the prepared designation ..., its controller creates a
copy of that object in exile, except that copy has only the characteristics
of that permanent's prepare spell. ... For as long as the copy remains in
exile, the prepared permanent's controller may cast the copy."

Each test below proves both halves the audit asked for: the permanent enters
prepared with its CR 722.3c exile copy, and that copy is castable (a real
`Game.play_permission_for` grant, the same proof `tests/scenarios/
test_prepare.py::test_a_creature_that_enters_prepared_gets_the_designation_
and_an_exile_copy` already uses for Emergency Phytomedic). Every CR number
here was verified this session with `mise run rules:find`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def _assert_enters_prepared_and_copy_is_castable(scenario: Scenario, front: object) -> None:
    assert front.zone is Zone.BATTLEFIELD
    assert front.prepared is True, "CR 722.3a: enters prepared"
    assert front.prepared_copy_id is not None

    copies = [state for state in scenario.game.exile if state.id == front.prepared_copy_id]
    assert len(copies) == 1, "CR 722.3c: a copy of that object in exile"
    (copy,) = copies
    assert copy.is_copy is True

    permission = scenario.game.play_permission_for(copy, "alice")
    assert permission is not None, "CR 722.3c: the controller may cast the copy"
    assert permission.action is PlayAction.CAST
    assert permission.pays_mana_cost is True
    assert permission.zone is Zone.EXILE


def test_blossom_blessed_angel_enters_prepared_and_seed_suture_is_castable():
    scenario = (
        Scenario()
        .player("alice", hand=["Blossom-Blessed Angel"], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.cast_and_resolve(
        "Blossom-Blessed Angel", *scenario.untapped_sources(*(["Plains"] * 4))
    )
    _assert_enters_prepared_and_copy_is_castable(scenario, angel)
    copy = scenario.game.find_by_id(angel.prepared_copy_id)
    assert copy.name == "Seed Suture"
    assert copy.mana_cost == "{G/W}"


def test_diviner_of_victory_enters_prepared_and_unwind_history_is_castable():
    scenario = (
        Scenario()
        .player("alice", hand=["Diviner of Victory"], battlefield=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diviner = scenario.cast_and_resolve("Diviner of Victory", *scenario.untapped_sources("Island"))
    _assert_enters_prepared_and_copy_is_castable(scenario, diviner)
    copy = scenario.game.find_by_id(diviner.prepared_copy_id)
    assert copy.name == "Unwind History"
    assert copy.mana_cost == "{1}{U}"


def test_fatehold_chronologist_enters_prepared_and_peer_review_is_castable():
    scenario = (
        Scenario()
        .player("alice", hand=["Fatehold Chronologist"], battlefield=["Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chronologist = scenario.cast_and_resolve(
        "Fatehold Chronologist", *scenario.untapped_sources("Island", "Island")
    )
    _assert_enters_prepared_and_copy_is_castable(scenario, chronologist)
    copy = scenario.game.find_by_id(chronologist.prepared_copy_id)
    assert copy.name == "Peer Review"
    assert copy.mana_cost == "{2}{W/U}"


def test_hallway_heckler_enters_prepared_and_vicious_verse_is_castable():
    scenario = (
        Scenario()
        .player("alice", hand=["Hallway Heckler"], battlefield=["Mountain"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    heckler = scenario.cast_and_resolve(
        "Hallway Heckler", *scenario.untapped_sources(*(["Mountain"] * 3))
    )
    _assert_enters_prepared_and_copy_is_castable(scenario, heckler)
    copy = scenario.game.find_by_id(heckler.prepared_copy_id)
    assert copy.name == "Vicious Verse"
    assert copy.mana_cost == "{B/R}"


def test_konstrari_improviser_enters_prepared_and_soul_tether_is_castable():
    scenario = (
        Scenario()
        .player("alice", hand=["Konstrari Improviser"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    improviser = scenario.cast_and_resolve(
        "Konstrari Improviser", *scenario.untapped_sources("Mountain", "Mountain")
    )
    _assert_enters_prepared_and_copy_is_castable(scenario, improviser)
    copy = scenario.game.find_by_id(improviser.prepared_copy_id)
    assert copy.name == "Soul Tether"
    assert copy.mana_cost == "{2}{R/G}"


def test_pompous_battlemage_enters_prepared_and_improvised_act_is_castable():
    scenario = (
        Scenario()
        .player("alice", hand=["Pompous Battlemage"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlemage = scenario.cast_and_resolve(
        "Pompous Battlemage", *scenario.untapped_sources("Mountain")
    )
    _assert_enters_prepared_and_copy_is_castable(scenario, battlemage)
    copy = scenario.game.find_by_id(battlemage.prepared_copy_id)
    assert copy.name == "Improvised Act"
    assert copy.mana_cost == "{R}"


def test_semester_foreseer_enters_prepared_and_peer_review_is_castable():
    scenario = (
        Scenario()
        .player("alice", hand=["Semester Foreseer"], battlefield=["Island"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    foreseer = scenario.cast_and_resolve(
        "Semester Foreseer", *scenario.untapped_sources(*(["Island"] * 4))
    )
    _assert_enters_prepared_and_copy_is_castable(scenario, foreseer)
    copy = scenario.game.find_by_id(foreseer.prepared_copy_id)
    assert copy.name == "Peer Review"
    assert copy.mana_cost == "{2}{W/U}"

"""Saga chapters printed with a chapter name, on a line that lists more than
one chapter number, and a final chapter that sends the Saga back front face up.

Jill, Shiva's Dominant // Shiva, Warden of Ice (oracle text confirmed against
the Scryfall printing in `data/printings`):

    I, II - Mesmerize - Target creature can't be blocked this turn.
    III - Cold Snap - Tap all lands your opponents control. Exile Shiva, then
    return it to the battlefield (front face up).

Second printings, neither a listed card nor in any deck list, legality checked
on Scryfall (Modern, Pioneer and Standard legal):

- **Summon: Fat Chocobo** - "I - Wark - Create a 2/2 green Bird creature
  token ..." / "II, III, IV - Kerplunk - Creatures you control gain trample
  until end of turn." Three chapter numbers on one named line, on a Saga that
  is not double-faced and is sacrificed after IV.
- **Summon: Primal Garuda** - "I - Aerial Blast - This creature deals 4 damage
  to target tapped creature an opponent controls." / "II, III - Slipstream -
  Another target creature you control gets +1/+0 and gains flying until end
  of turn." A named pair whose ability targets, so each copy picks its own.
- **Clive, Ifrit's Dominant // Ifrit, Warden of Inferno** - "I - Lunge - Ifrit
  fights up to one other target creature." / "II, III - Brimstone - Add
  {R}{R}{R}{R}. If Ifrit has three or more lore counters on it, exile it, then
  return it to the battlefield (front face up)." The multi-chapter line is the
  *later* pair here, and the front-face return sits behind an "If" that only
  chapter III satisfies.
- **Joshua, Phoenix's Dominant // Phoenix, Warden of Fire** - "III - Flames
  of Rebirth - Return any number of target creature cards with total mana
  value 6 or less from your graveyard to the battlefield. Exile Phoenix, then
  return it to the battlefield (front face up)." The same unconditional
  trailing return behind a different leading effect.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 714.2b** - "'{rN}-[Effect]' means 'When one or more lore counters are
  put onto this Saga, if the number of lore counters on it was less than N and
  became at least N, [effect].'"
- **CR 714.2c** - "'{rN1}, {rN2}-[Effect]' means the same as '{rN1}-[Effect]'
  and '{rN2}-[Effect].'" - two separate abilities, each with its own threshold.
- **CR 207.2d** - flavor words "have no special rules meaning": "Mesmerize"
  is not part of the effect.
- **CR 714.3a** - a Saga without read ahead enters with a lore counter.
- **CR 714.4** - a Saga at its final chapter number is sacrificed only once it
  is no longer the source of a chapter ability waiting on the stack.
- **CR 712.14** - a double-faced card put onto the battlefield from a zone
  other than the stack enters front face up by default.
- **CR 400.7** - the returned permanent is a new object.
- **CR 122.1d** - a stun counter stops the permanent from untapping.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.combat import Keyword, evasion_restriction_refusal, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState, Counter
from tests.cards import card
from tests.scenarios.harness import Scenario

JILL = "Jill, Shiva's Dominant"
SHIVA = "Shiva, Warden of Ice"


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _shiva(*, alice_extra=(), bob_battlefield=("Grizzly Bears", "Mountain", "Mountain")):
    """Jill transformed by her own activation, so Shiva arrives the way a real
    game brings her in - CR 714.3a's lore counter goes on as she enters and
    chapter I triggers off it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[JILL, "Watchwolf", *alice_extra] + ["Island"] * 5,
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jill = scenario.find(JILL, Zone.BATTLEFIELD, "alice")
    scenario.activate(jill, auto=True)
    return scenario, jill


def test_the_flavor_word_is_not_part_of_a_chapters_effect():
    """CR 207.2d: "Mesmerize" and "Cold Snap" carry no rules meaning, so the
    effect each chapter ability resolves is only the text after them."""
    effects = {
        ability.chapter: ability.effect
        for ability in parse_abilities(card(JILL))
        if getattr(ability, "chapter", None) is not None
    }
    assert effects[1] == "Target creature can't be blocked this turn."
    assert effects[2] == "Target creature can't be blocked this turn."
    assert effects[3].startswith("Tap all lands your opponents control.")


def test_mesmerize_fires_at_chapter_one_as_shiva_enters():
    scenario, jill = _shiva()
    wolf = scenario.creature("Watchwolf", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets(SHIVA, [wolf])
    scenario.pass_until_resolved()
    _resolve_everything(scenario)

    assert jill.name == SHIVA
    assert jill.counters[Counter.LORE] == 1
    assert evasion_restriction_refusal(scenario.game, wolf, bears) is not None


def test_mesmerize_fires_again_at_chapter_two():
    """CR 714.2c: the "I, II" line is two abilities, so the second lore
    counter triggers the same effect a second time, with its own target."""
    scenario, jill = _shiva()
    wolf = scenario.creature("Watchwolf", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets(SHIVA, [bears])
    scenario.pass_until_resolved()
    _resolve_everything(scenario)
    assert evasion_restriction_refusal(scenario.game, wolf, bears) is None

    scenario.game.saga_lore_step()
    assert jill.counters[Counter.LORE] == 2
    scenario.choose_trigger_targets(SHIVA, [wolf])
    _resolve_everything(scenario)

    assert evasion_restriction_refusal(scenario.game, wolf, bears) is not None
    assert jill.zone is Zone.BATTLEFIELD and jill.name == SHIVA


def test_each_threshold_fires_once_when_two_lore_counters_arrive_together():
    """CR 714.2b: two counters taking Shiva from 1 to 3 cross both the II and
    the III threshold at once, and never I's again."""
    scenario, jill = _shiva()
    wolf = scenario.creature("Watchwolf", "alice")
    scenario.choose_trigger_targets(SHIVA, [wolf])
    scenario.pass_until_resolved()
    _resolve_everything(scenario)

    scenario.game.add_counters(jill, Counter.LORE, 2)

    chapters = sorted(
        pending.ability.chapter
        for pending in scenario.pending_triggers
        if getattr(pending.ability, "chapter", None) is not None
    )
    assert chapters == [2, 3]


def _to_chapter_three(scenario: Scenario, jill: CardState) -> None:
    wolf = scenario.creature("Watchwolf", "alice")
    scenario.choose_trigger_targets(SHIVA, [wolf])
    scenario.pass_until_resolved()
    _resolve_everything(scenario)
    scenario.game.saga_lore_step()
    scenario.choose_trigger_targets(SHIVA, [wolf])
    _resolve_everything(scenario)
    assert jill.counters[Counter.LORE] == 2


def test_cold_snap_taps_only_the_opponents_lands():
    scenario, jill = _shiva()
    _to_chapter_three(scenario, jill)
    alice_islands = [
        state for state in scenario.game.permanents_controlled_by("alice") if state.name == "Island"
    ]
    for island in alice_islands:
        island.tapped = False

    scenario.game.saga_lore_step()
    scenario.choose_trigger_targets(JILL, [])
    _resolve_everything(scenario)

    bob_lands = [
        state for state in scenario.game.permanents_controlled_by("bob") if state.name == "Mountain"
    ]
    assert bob_lands and all(land.tapped for land in bob_lands)
    assert not any(island.tapped for island in alice_islands)
    assert not scenario.creature("Grizzly Bears", "bob").tapped


def test_cold_snap_returns_jill_front_face_up_as_a_new_object():
    """The trailing return: exiled, then back front face up (CR 712.14) as a
    new object (CR 400.7) - no lore counters, not transformed, and Jill's own
    enters trigger fires because Jill is what entered."""
    scenario, jill = _shiva(bob_battlefield=("Grizzly Bears", "Mountain"))
    _to_chapter_three(scenario, jill)
    stamp_as_shiva = jill.zone_change_stamp

    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert jill.zone is Zone.BATTLEFIELD
    assert jill.transformed is False
    assert jill.name == JILL
    assert jill.zone_change_stamp != stamp_as_shiva
    assert jill.counters[Counter.LORE] == 0
    assert [getattr(item, "source_name", None) for item in scenario.game.stack] == [JILL]


def test_the_returned_jill_is_not_a_saga_so_nothing_sacrifices_it():
    """CR 714.4 only looks at a Saga with chapter abilities; Jill has none."""
    scenario, jill = _shiva()
    _to_chapter_three(scenario, jill)
    scenario.game.saga_lore_step()
    scenario.choose_trigger_targets(JILL, [])
    _resolve_everything(scenario)
    scenario.state_based_actions()

    assert jill.zone is Zone.BATTLEFIELD
    assert jill.name == JILL


# -- Summon: Fat Chocobo: three chapter numbers on one named line ---------


def _resolve_chapter(scenario: Scenario, saga: CardState, targets=None) -> None:
    scenario.game.saga_lore_step()
    if targets is not None:
        scenario.choose_trigger_targets(saga.name, targets)
    _resolve_everything(scenario)


def _fat_chocobo():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Summon: Fat Chocobo"], battlefield=["Watchwolf"])
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.put_onto_battlefield("Summon: Fat Chocobo", "alice")
    _resolve_everything(scenario)
    return scenario, saga


def _has_trample(scenario: Scenario, creature: CardState) -> bool:
    return has_keyword(creature, Keyword.TRAMPLE, scenario.game)


def test_wark_makes_the_bird_at_chapter_one_and_nothing_else_fires():
    scenario, saga = _fat_chocobo()
    assert saga.counters[Counter.LORE] == 1
    assert len([s for s in scenario.game.permanents_controlled_by("alice") if s.token]) == 1
    assert not _has_trample(scenario, scenario.creature("Watchwolf", "alice"))


@pytest.mark.parametrize("chapter", [2, 3, 4])
def test_kerplunk_fires_at_each_of_its_three_numbers(chapter):
    """CR 714.2c for a line naming three chapters: each is its own ability."""
    scenario, saga = _fat_chocobo()
    fired: list[int] = []
    for _ in range(chapter - 1):
        scenario.game.saga_lore_step()
        fired = [
            pending.ability.chapter
            for pending in scenario.pending_triggers
            if getattr(pending.ability, "chapter", None) is not None
        ]
        assert fired == [saga.counters[Counter.LORE]]
        _resolve_everything(scenario)
    assert fired == [chapter]
    assert _has_trample(scenario, scenario.creature("Watchwolf", "alice"))


def test_fat_chocobo_is_sacrificed_only_after_chapter_four():
    scenario, saga = _fat_chocobo()
    for _ in range(2):
        _resolve_chapter(scenario, saga)
        scenario.state_based_actions()
        assert saga.zone is Zone.BATTLEFIELD
    _resolve_chapter(scenario, saga)
    scenario.state_based_actions()
    assert saga.zone is Zone.GRAVEYARD


# -- Summon: Primal Garuda: a named "II, III" line with its own target -----


def test_slipstream_fires_at_two_and_three_with_a_fresh_target_each_time():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Summon: Primal Garuda"], battlefield=["Watchwolf", "Grizzly Bears"])
        .player("bob", battlefield=["Llanowar Elves"], library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "bob")
    elves.tapped = True
    scenario.choose_trigger_targets("Summon: Primal Garuda", [elves])
    saga = scenario.put_onto_battlefield("Summon: Primal Garuda", "alice")
    _resolve_everything(scenario)
    assert elves.zone is Zone.GRAVEYARD

    wolf = scenario.creature("Watchwolf", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _resolve_chapter(scenario, saga, [wolf])
    board = scenario.game.computed_board()
    assert board.of(wolf).power == 4 and has_keyword(wolf, Keyword.FLYING, scenario.game)
    _resolve_chapter(scenario, saga, [bears])
    board = scenario.game.computed_board()
    assert board.of(bears).power == 3 and has_keyword(bears, Keyword.FLYING, scenario.game)


# -- Joshua // Phoenix: a named final chapter that returns front face up ---


def test_flames_of_rebirth_reanimates_then_returns_joshua_front_face_up():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Joshua, Phoenix's Dominant", "Mountain"] + ["Plains"] * 4,
            graveyard=["Grizzly Bears"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    joshua = scenario.find("Joshua, Phoenix's Dominant", Zone.BATTLEFIELD, "alice")
    scenario.activate(joshua, auto=True)
    scenario.pass_until_resolved()
    _resolve_everything(scenario)
    assert joshua.name == "Phoenix, Warden of Fire"
    _resolve_chapter(scenario, joshua)
    stamp = joshua.zone_change_stamp
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    _resolve_chapter(scenario, joshua, [bears])

    assert bears.zone is Zone.BATTLEFIELD
    assert joshua.zone is Zone.BATTLEFIELD
    assert joshua.name == "Joshua, Phoenix's Dominant"
    assert joshua.transformed is False
    assert joshua.zone_change_stamp != stamp
    assert joshua.counters[Counter.LORE] == 0


# -- Clive // Ifrit: "II, III" with a conditional front-face return --------


def _ifrit():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Clive, Ifrit's Dominant", "Watchwolf"] + ["Mountain"] * 6,
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clive = scenario.find("Clive, Ifrit's Dominant", Zone.BATTLEFIELD, "alice")
    scenario.activate(clive, auto=True)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Ifrit, Warden of Inferno", [bears])
    scenario.pass_until_resolved()
    _resolve_everything(scenario)
    return scenario, clive


def test_lunge_fights_at_chapter_one():
    scenario, clive = _ifrit()
    assert clive.name == "Ifrit, Warden of Inferno"
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None


def test_brimstone_at_chapter_two_adds_mana_and_keeps_ifrit():
    """ "If Ifrit has three or more lore counters on it" is false at II."""
    scenario, clive = _ifrit()
    stamp = clive.zone_change_stamp
    scenario.game.saga_lore_step()
    _resolve_everything(scenario)

    assert scenario.player("alice").mana_pool.total >= 4
    assert clive.name == "Ifrit, Warden of Inferno"
    assert clive.zone_change_stamp == stamp


def test_brimstone_at_chapter_three_returns_clive_front_face_up():
    scenario, clive = _ifrit()
    scenario.game.saga_lore_step()
    _resolve_everything(scenario)
    stamp = clive.zone_change_stamp

    scenario.game.saga_lore_step()
    _resolve_everything(scenario)

    assert clive.zone is Zone.BATTLEFIELD
    assert clive.name == "Clive, Ifrit's Dominant"
    assert clive.transformed is False
    assert clive.zone_change_stamp != stamp


@pytest.mark.parametrize(
    "name",
    [
        JILL,
        "Summon: Fat Chocobo",
        "Summon: Primal Garuda",
        "Clive, Ifrit's Dominant",
        "Joshua, Phoenix's Dominant",
    ],
)
def test_every_chapter_line_is_read(name):
    from magic_cards_model.support import classify_clauses

    chapter_outcomes = [
        outcome.category
        for outcome in classify_clauses(card(name))
        if outcome.source == "triggered" and " — " in outcome.text[:8]
    ]
    assert chapter_outcomes
    assert set(chapter_outcomes) == {"handled"}

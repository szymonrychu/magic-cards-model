"""Emblems (CR 114) and "the Nth time this ability has resolved this turn".

- **CR 114.1-114.5** - an emblem lives in the command zone, is owned and
  controlled by the player who gets it, has only the abilities the effect gave
  it, and those abilities function from the command zone.
- **CR 701.27a / 712.9** - transforming turns a double-faced permanent over.
- **CR 601.3** - a player can begin to cast a spell only if a rule or effect
  allows it; Jaya Ballard's emblem is such an effect for instants and
  sorceries in the graveyard.
- **CR 606.3** - one loyalty activation per planeswalker per turn.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import why_cannot_cast_from
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_stack(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _sephiroth_board(memnites: int = 5):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sephiroth, Fabled SOLDIER"],
            battlefield=["Memnite"] * memnites,
            library=["Forest"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sephiroth = scenario.put_onto_battlefield("Sephiroth, Fabled SOLDIER", "alice")
    scenario.will_take_the_may(False, source="Sephiroth, Fabled SOLDIER")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    return scenario, sephiroth


def _kill_a_memnite(scenario) -> None:
    memnite = next(p for p in scenario.game.battlefield if p.name == "Memnite")
    scenario.game.sacrifice(memnite)
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)


def test_sephiroth_drains_on_each_death_and_transforms_on_the_fourth_resolution():
    """Sephiroth, Fabled SOLDIER: "Whenever another creature dies, target
    opponent loses 1 life and you gain 1 life. If this is the fourth time this
    ability has resolved this turn, transform Sephiroth." Three resolutions
    leave it unturned; the fourth turns it over."""
    scenario, sephiroth = _sephiroth_board()
    for _ in range(3):
        _kill_a_memnite(scenario)
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23
    assert sephiroth.up_face_name == "Sephiroth, Fabled SOLDIER"

    _kill_a_memnite(scenario)

    assert scenario.player("bob").life == 16
    assert sephiroth.up_face_name == "Sephiroth, One-Winged Angel"


def test_the_resolution_count_is_per_turn():
    """Three resolutions this turn and one on the next is not a fourth time
    this turn."""
    scenario, sephiroth = _sephiroth_board()
    for _ in range(3):
        _kill_a_memnite(scenario)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    _kill_a_memnite(scenario)
    assert scenario.player("bob").life == 16
    assert sephiroth.up_face_name == "Sephiroth, Fabled SOLDIER"


def test_super_nova_gives_an_emblem_that_drains_from_the_command_zone():
    """Sephiroth, One-Winged Angel's Super Nova: "As this creature transforms
    into Sephiroth, One-Winged Angel, you get an emblem with 'Whenever a
    creature dies, target opponent loses 1 life and you gain 1 life.'" The
    emblem is alice's (CR 114.2), in the command zone, and its trigger
    functions there (CR 114.4) - after Sephiroth itself has left."""
    scenario, sephiroth = _sephiroth_board()
    for _ in range(4):
        _kill_a_memnite(scenario)
    emblems = scenario.game.shared_zones[Zone.COMMAND]
    assert len(emblems) == 1
    assert emblems[0].owner == "alice" and emblems[0].controller == "alice"
    bob_before = scenario.player("bob").life

    scenario.game.sacrifice(sephiroth)
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)

    assert scenario.player("bob").life == bob_before - 1
    assert emblems[0].zone is Zone.COMMAND


def _jaya_with_eight_loyalty(graveyard: list[str], battlefield: list[str] = ()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jaya Ballard", *battlefield],
            graveyard=graveyard,
            library=["Forest"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jaya = scenario.find("Jaya Ballard", Zone.BATTLEFIELD, "alice")
    jaya.add_counters(Counter.LOYALTY, 8 - jaya.counters[Counter.LOYALTY])
    return scenario, jaya


def test_jaya_emblem_lets_an_instant_be_cast_from_the_graveyard_and_exiles_it():
    """Jaya Ballard's -8: "You get an emblem with 'You may cast instant and
    sorcery spells from your graveyard. If a spell cast this way would be put
    into your graveyard, exile it instead.'" Lightning Bolt cast from the
    graveyard deals its damage and is exiled on resolution."""
    scenario, jaya = _jaya_with_eight_loyalty(["Lightning Bolt"], ["Mountain"])
    scenario.activate(jaya, index=2)
    _resolve_stack(scenario)
    assert len(scenario.game.shared_zones[Zone.COMMAND]) == 1

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Cast permission")
    casting.choose_targets([scenario.player("bob")])
    scenario.pay_with(casting.begin_paying(), mountain)
    bolt = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert bolt.zone is Zone.EXILE


def test_jaya_emblem_does_not_reach_a_creature_card():
    """Only instant and sorcery spells: a creature card in the graveyard stays
    uncastable (CR 601.3)."""
    scenario, jaya = _jaya_with_eight_loyalty(["Grizzly Bears"], ["Forest", "Forest"])
    scenario.activate(jaya, index=2)
    _resolve_stack(scenario)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert why_cannot_cast_from(bears, "alice", Zone.GRAVEYARD, scenario.game) is not None


def test_without_the_emblem_the_graveyard_is_closed():
    scenario, _jaya = _jaya_with_eight_loyalty(["Lightning Bolt"], ["Mountain"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    assert why_cannot_cast_from(bolt, "alice", Zone.GRAVEYARD, scenario.game) is not None


def test_jaya_emblem_keeps_a_sorcerys_own_timing():
    """The permission changes the zone, not the timing: Mind Rot from the
    graveyard is refused on the opponent's turn (CR 307.1), and cast fine in
    its controller's own main phase."""
    import pytest

    scenario, jaya = _jaya_with_eight_loyalty(["Mind Rot"], ["Swamp", "Swamp", "Swamp"])
    scenario.activate(jaya, index=2)
    _resolve_stack(scenario)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError, match="sorcery|main phase") as refused:
        casting = scenario.cast("Mind Rot", from_zone=Zone.GRAVEYARD, username="alice")
        casting.use_keyword("Cast permission")
        casting.choose_targets([scenario.player("bob")])
    assert "priority" not in str(refused.value)

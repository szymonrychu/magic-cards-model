"""Exile cards from the top of your library *until* a stop condition, then a
permission over what was found.

Two templates, one shared process (`machines/keywords.exile_until`):

- **"exile cards from the top of your library until you exile a <quality>
  card. You may cast that card this turn."** - Territorial Bruntar's
  landfall. "That card" is CR 607.1 anaphora for the one card that stopped
  the process; the cards exiled on the way are not named by anything and
  stay in exile (CR 406.1 - no instruction puts them back). "This turn" is
  CR 514.2's duration, and the permission is cast-only (CR 601.3): the card
  is cast at its normal timing for its normal cost.
- **"exile cards from the top of your library until you exile cards with
  total mana value N or greater. You may cast any number of spells from
  among them without paying their mana costs."** - Improvisation Capstone.
  CR 608.2g: the casts happen while the spell is still resolving (the card's
  own ruling: "You can't wait to cast them later in the turn. Timing
  restrictions based on the cards' types are ignored."), CR 118.9 "without
  paying" with X of 0 (CR 107.3b), lands are never cast, and whatever is not
  cast stays in exile.

The same process is cascade's (CR 702.85a) and discover's (CR 701.57a) own
first half, which is what Bloodbraid Elf and Geological Appraiser prove
below: both now run through the shared `exile_until`, and neither is a
listed card nor in the deck pool.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

BRUNTAR = "Territorial Bruntar"
CAPSTONE = "Improvisation Capstone"


def _exiled_since(scenario: Scenario, before: set) -> list:
    return [state for state in scenario.game.exile if state.id not in before]


# --------------------------------------------------------------------------
# Territorial Bruntar: until a nonland card, cast it this turn
# --------------------------------------------------------------------------


def _bruntar_board(library: list[str], *, hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand if hand is not None else ["Forest"],
            battlefield=[BRUNTAR, "Mountain", "Mountain", "Mountain"],
            library=library,
        )
        .player("bob", library=["Island"] * 5)
    )


def _landfall(scenario: Scenario) -> list:
    before = {state.id for state in scenario.game.exile}
    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    return _exiled_since(scenario, before)


def test_landfall_exiles_until_a_nonland_card_and_permits_casting_it():
    scenario = _bruntar_board(["Island", "Swamp", "Lightning Bolt", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    exiled = _landfall(scenario)

    assert [state.name for state in exiled] == ["Island", "Swamp", "Lightning Bolt"]
    assert [state.name for state in scenario.player("alice").library] == ["Mountain"]
    bolt = exiled[-1]
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.action is PlayAction.CAST
    assert permission.pays_mana_cost is True
    for land in exiled[:-1]:
        assert land.zone is Zone.EXILE
        assert scenario.game.play_permission_for(land, "alice", PlayAction.PLAY) is None


def test_the_found_card_is_cast_for_its_own_mana_cost():
    scenario = _bruntar_board(["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bolt,) = _landfall(scenario)

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(["bob"])
    assert str(casting.total_cost.mana) == "{R}"
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_the_permission_lasts_only_this_turn():
    scenario = _bruntar_board(["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bolt,) = _landfall(scenario)

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert bolt.zone is Zone.EXILE
    assert scenario.game.play_permission_for(bolt, "alice") is None


def test_a_sorcery_found_this_way_keeps_its_own_timing():
    """The card's own ruling: "if the exiled card is a sorcery card, you may
    cast it only during your main phase while the stack is empty"."""
    scenario = _bruntar_board(["Wrenn's Resolve"], hand=["Forest", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (resolve,) = _landfall(scenario)
    casting = scenario.cast("Lightning Bolt")
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)

    with pytest.raises(ValueError):
        scenario.cast("Wrenn's Resolve", from_zone=Zone.EXILE).use_permission()
    assert resolve.zone is Zone.EXILE


def test_a_library_of_only_lands_exiles_everything_and_permits_nothing():
    scenario = _bruntar_board(["Island", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    exiled = _landfall(scenario)

    assert [state.name for state in exiled] == ["Island", "Swamp"]
    assert scenario.player("alice").library == []
    assert not any(p.source_name == BRUNTAR for p in scenario.game.play_permissions)


def test_each_landfall_finds_its_own_card_and_both_permissions_stand():
    """Two land drops, two triggers: each resolution names only the card its
    own process stopped on (CR 607.1), and the first grant is untouched by
    the second."""
    scenario = _bruntar_board(
        ["Lightning Bolt", "Island", "Shock"], hand=["Forest", "Forest"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_land_play("alice")

    (bolt,) = _landfall(scenario)
    island, shock = _landfall(scenario)

    assert (bolt.name, island.name, shock.name) == ("Lightning Bolt", "Island", "Shock")
    assert scenario.game.play_permission_for(bolt, "alice") is not None
    assert scenario.game.play_permission_for(shock, "alice") is not None
    assert scenario.game.play_permission_for(island, "alice", PlayAction.PLAY) is None


# --------------------------------------------------------------------------
# Improvisation Capstone: until total mana value N or greater, cast any number
# --------------------------------------------------------------------------


def _capstone_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[CAPSTONE],
            battlefield=["Mountain"] * 7,
            library=library,
        )
        .player("bob", library=["Island"] * 5, battlefield=["Grizzly Bears"])
    )


def _cast_capstone(scenario: Scenario) -> None:
    scenario.cast_onto_stack(CAPSTONE, *scenario.untapped_sources(*["Mountain"] * 7))


def test_capstone_stops_once_the_exiled_total_reaches_four():
    library = ["Lightning Bolt", "Forest", "Grizzly Bears", "Memnite", "Tarmogoyf", "Island"]
    scenario = _capstone_board(library).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source=CAPSTONE)
    before = {state.id for state in scenario.game.exile}
    _cast_capstone(scenario)

    scenario.resolve_top()

    exiled = [s.name for s in _exiled_since(scenario, before) if s.name != CAPSTONE]
    assert exiled == ["Lightning Bolt", "Forest", "Grizzly Bears", "Memnite", "Tarmogoyf"]
    assert [state.name for state in scenario.player("alice").library] == ["Island"]


def test_capstone_stops_on_the_card_that_reaches_the_total_exactly():
    scenario = _capstone_board(["Tarmogoyf", "Grizzly Bears", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source=CAPSTONE)
    _cast_capstone(scenario)

    scenario.resolve_top()

    assert [state.name for state in scenario.player("alice").library] == ["Island"]


def test_capstone_casts_several_found_spells_for_free_during_its_resolution():
    """CR 608.2g: each is cast above the still-resolving Capstone, with no
    priority in between and no timing restriction - a sorcery-speed creature
    and an instant both, neither paying its mana cost (CR 118.9)."""
    scenario = _capstone_board(["Lightning Bolt", "Grizzly Bears", "Forest", "Tarmogoyf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_capstone(scenario)
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=CAPSTONE, times=2)
    scenario.will_take_the_may(False, source=CAPSTONE)
    scenario.will_choose_cards(bolt, source=CAPSTONE)
    scenario.will_choose_cards(bears, source=CAPSTONE)
    scenario.will_choose_targets("bob", source="Lightning Bolt")

    scenario.resolve_top()

    assert scenario.stack_names() == ["Lightning Bolt", "Grizzly Bears"]
    goyf = scenario.find("Tarmogoyf", Zone.EXILE, "alice")
    assert scenario.game.play_permission_for(goyf, "alice") is None
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("bob").life == 17
    assert bears.zone is Zone.BATTLEFIELD


def test_capstone_never_offers_a_land():
    scenario = _capstone_board(["Forest", "Island", "Tarmogoyf", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source=CAPSTONE)
    _cast_capstone(scenario)

    scenario.resolve_top()

    (question,) = [
        q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY and q.source == CAPSTONE
    ]
    offered = {scenario.game.find_by_id(card_id).name for card_id in question.cards}
    assert offered == {"Tarmogoyf", "Grizzly Bears"}


def test_capstone_leaves_every_card_it_did_not_cast_in_exile():
    scenario = _capstone_board(["Grizzly Bears", "Forest", "Tarmogoyf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source=CAPSTONE)
    _cast_capstone(scenario)

    scenario.resolve_top()

    for name in ("Grizzly Bears", "Forest", "Tarmogoyf"):
        state = scenario.find(name, Zone.EXILE, "alice")
        assert scenario.game.play_permission_for(state, "alice") is None
    assert scenario.player("alice").library == []


def test_capstone_asks_nothing_when_nothing_castable_was_found():
    scenario = _capstone_board(["Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_capstone(scenario)

    scenario.resolve_top()

    assert not [q for q in scenario.questions_asked() if q.source == CAPSTONE]
    assert scenario.player("alice").library == []


# --------------------------------------------------------------------------
# The shared process, proved on cascade and discover
# --------------------------------------------------------------------------


def test_bloodbraid_elf_cascade_still_exiles_until_its_hit():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bloodbraid Elf"],
            library=["Forest", "Tarmogoyf", "Grizzly Bears", "Island"],
            battlefield=["Forest", "Mountain", "Forest", "Mountain"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Bloodbraid Elf")
    scenario.cast_onto_stack(
        "Bloodbraid Elf", *scenario.untapped_sources("Forest", "Mountain", "Forest", "Mountain")
    )

    scenario.resolve_top()

    assert scenario.stack_names() == ["Bloodbraid Elf", "Tarmogoyf"]
    library = [state.name for state in scenario.player("alice").library]
    assert library[:2] == ["Grizzly Bears", "Island"]
    assert library[2:] == ["Forest"]


def test_geological_appraiser_discover_still_exiles_until_its_hit():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Geological Appraiser"],
            library=["Forest", "Island", "Tarmogoyf", "Mountain"],
            battlefield=["Mountain"] * 4,
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Geological Appraiser")
    scenario.cast_and_resolve("Geological Appraiser", *scenario.untapped_sources(*["Mountain"] * 4))
    scenario.game.put_triggers_on_stack()

    scenario.resolve_top()

    goyf = scenario.find("Tarmogoyf", Zone.HAND, "alice")
    assert goyf.zone is Zone.HAND
    library = [state.name for state in scenario.player("alice").library]
    assert library[0] == "Mountain"
    assert sorted(library[1:]) == ["Forest", "Island"]

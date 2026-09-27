"""Scenario: exile cards from the top of a library "until" a condition, then
cast what was exiled without paying its mana cost (ECL).

- **Dream Harvest** - "Each opponent exiles cards from the top of their
  library until they have exiled cards with total mana value 5 or greater
  this way. Until end of turn, you may cast cards exiled this way without
  paying their mana costs." CR 202.3: a card's mana value (a land's is 0);
  CR 601.3: a permission to cast; CR 118.9: without paying its mana cost;
  CR 514.2: "until end of turn" ends in the cleanup step. Timing still
  applies to a card cast this way (CR 117.1a). Proof printing for the
  total-mana-value exile: Tasha's Hideous Laughter.
- **Bre of Clan Stoutarm** - "At the beginning of your end step, if you
  gained life this turn, exile cards from the top of your library until you
  exile a nonland card. You may cast that card without paying its mana cost
  if the spell's mana value is less than or equal to the amount of life you
  gained this turn. Otherwise, put it into your hand." CR 603.4: the
  intervening "if"; CR 608.2g: the cast happens during the resolution. Proof
  printings: Solstice Revelations ("... if the spell's mana value is less
  than the number of Mountains you control. If you don't cast that card this
  way, put it into your hand.") and Breaching Dragonstorm ("You may cast it
  without paying its mana cost if that spell's mana value is 8 or less. If
  you don't, put that card into your hand.").

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 202.3, CR 601.3, CR 118.9, CR 514.2, CR 117.1a,
CR 603.4, CR 608.2g.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

_HARVEST_LANDS = ["Island", "Island", "Island", "Swamp", "Swamp", "Swamp", "Swamp"]


def _harvest_board(bob_library):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dream Harvest"],
            battlefield=[*_HARVEST_LANDS, "Mountain", "Forest"],
            library=["Island"] * 5,
        )
        .player("bob", library=list(bob_library))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*_HARVEST_LANDS, username="alice")
    scenario.cast_and_resolve("Dream Harvest", *lands, username="alice")
    return scenario


def _cast_free(scenario, name, targets=None):
    casting = scenario.cast(name, username="alice", from_zone=Zone.EXILE)
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    return scenario.put_on_stack(casting)


def _exiled(scenario, name):
    return [c for c in scenario.game.exile if c.name == name]


def test_harvest_exiles_until_the_total_reaches_five_and_stops_there():
    scenario = _harvest_board(
        ["Island", "Lightning Bolt", "Grizzly Bears", "Hill Giant", "Craw Wurm"]
    )
    assert sorted(c.name for c in scenario.game.exile) == [
        "Grizzly Bears",
        "Hill Giant",
        "Island",
        "Lightning Bolt",
    ], "0 + 1 + 2 + 4 = 7: the Giant brings it past 5, the Wurm stays"
    assert [c.name for c in scenario.player("bob").library] == ["Craw Wurm"]


def test_the_exiled_spells_can_be_cast_free_this_turn():
    scenario = _harvest_board(["Lightning Bolt", "Grizzly Bears", "Hill Giant"])
    (bears,) = _exiled(scenario, "Grizzly Bears")
    casting = scenario.cast("Grizzly Bears", username="alice", from_zone=Zone.EXILE)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    assert all(not land.tapped for land in scenario.game.battlefield if land.name == "Forest")
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "alice"


def test_an_exiled_land_cannot_be_cast():
    scenario = _harvest_board(["Island", "Hill Giant", "Craw Wurm"])
    with pytest.raises(ValueError):
        _cast_free(scenario, "Island")


def test_the_permission_ends_with_the_turn():
    """CR 514.2: "until end of turn" ends in the cleanup step."""
    scenario = _harvest_board(["Grizzly Bears", "Hill Giant"])
    scenario.game.cleanup_step()
    with pytest.raises(ValueError):
        _cast_free(scenario, "Grizzly Bears")


def test_timing_still_applies_to_a_creature_cast_this_way():
    """CR 117.1a: a creature spell still waits for an empty stack in a main
    phase - the permission changes the cost, not the timing."""
    scenario = _harvest_board(["Lightning Bolt", "Grizzly Bears", "Hill Giant"])
    (bolt,) = _exiled(scenario, "Lightning Bolt")
    _cast_free(scenario, "Lightning Bolt", targets=["bob"])
    assert bolt.zone is Zone.STACK
    with pytest.raises(ValueError):
        _cast_free(scenario, "Grizzly Bears")


def test_a_short_library_is_exiled_whole():
    scenario = _harvest_board(["Lightning Bolt", "Island"])
    assert scenario.player("bob").library == []
    assert sorted(c.name for c in scenario.game.exile) == ["Island", "Lightning Bolt"]


def test_tashas_hideous_laughter_exiles_until_twenty():
    """The proof printing for the total-mana-value exile: "until that
    player has exiled cards with total mana value 20 or greater", and no
    cast permission at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tasha's Hideous Laughter"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob", library=["Craw Wurm"] * 4 + ["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Tasha's Hideous Laughter", auto=True, username="alice")

    assert len(scenario.game.exile) == 4, "4 x Craw Wurm (mana value 5) is 20"
    assert [c.name for c in scenario.player("bob").library] == ["Grizzly Bears", "Hill Giant"]
    with pytest.raises(ValueError):
        _cast_free(scenario, "Craw Wurm")


# -- Bre of Clan Stoutarm ----------------------------------------------------


def _bre_board(library, *, gained: int = 0, battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bre of Clan Stoutarm", *battlefield],
            library=list(library),
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if gained:
        scenario.game.gain_life(scenario.player("alice"), gained)
    return scenario


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        scenario.advance()


def test_bre_casts_the_nonland_card_free_when_its_mana_value_fits():
    scenario = _bre_board(["Island", "Lightning Bolt", "Grizzly Bears"], gained=3)
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets("bob", username="alice")
    _to_end_step(scenario)
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert [c.name for c in scenario.game.exile] == ["Island"]
    assert [c.name for c in scenario.player("alice").library] == ["Grizzly Bears"]


def test_bre_puts_a_card_too_expensive_into_the_hand():
    scenario = _bre_board(["Hill Giant", "Island"], gained=2)
    _to_end_step(scenario)
    while scenario.game.stack:
        scenario.resolve_top()

    assert [c.name for c in scenario.player("alice").hand] == ["Hill Giant"]


def test_declining_the_free_cast_puts_it_into_the_hand():
    scenario = _bre_board(["Lightning Bolt"], gained=5)
    scenario.will_take_the_may(False, username="alice")
    _to_end_step(scenario)
    while scenario.game.stack:
        scenario.resolve_top()

    assert [c.name for c in scenario.player("alice").hand] == ["Lightning Bolt"]


def test_no_life_gained_means_no_trigger():
    """CR 603.4: the intervening "if" is false, so it never triggers."""
    scenario = _bre_board(["Lightning Bolt"])
    _to_end_step(scenario)
    assert scenario.stack_names() == []
    assert [c.name for c in scenario.player("alice").library] == ["Lightning Bolt"]


def test_solstice_revelations_compares_strictly_with_mountains():
    """The proof printing: "less than the number of Mountains you control" -
    two Mountains allow mana value 1 (Lightning Bolt) but not 2."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Solstice Revelations"],
            battlefield=["Mountain", "Mountain", "Swamp"],
            library=["Grizzly Bears", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Solstice Revelations", auto=True, username="alice")

    assert [c.name for c in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_breaching_dragonstorm_casts_a_fitting_spell_on_entering():
    """The proof printing: "You may cast it ... if that spell's mana value is
    8 or less. If you don't, put that card into your hand." on an enters
    trigger."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Breaching Dragonstorm"],
            battlefield=["Mountain"] * 5,
            library=["Island", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets("bob", username="alice")
    scenario.cast_and_resolve("Breaching Dragonstorm", auto=True, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").life == 17


# -- End-Blaze Epiphany ------------------------------------------------------
#
# "End-Blaze Epiphany deals X damage to target creature. When that creature
# dies this turn, exile a number of cards from the top of your library equal
# to its power, then choose a card exiled this way. Until the end of your
# next turn, you may play that card." CR 603.7: the second sentence creates
# a delayed triggered ability; CR 603.10a: a dies trigger looks back, so
# "its power" is the creature's power as it last existed on the battlefield
# (CR 608.2h). CR 611.2a: "until the end of your next turn". Proof printing
# for the delayed "when that creature dies this turn" pair: Burn Away
# ("Burn Away deals 6 damage to target creature. When that creature dies
# this turn, exile its controller's graveyard.").


def _end_blaze_board(*, target="Hill Giant", lands=4, library=None, bob_graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["End-Blaze Epiphany"],
            battlefield=["Mountain"] * lands,
            library=list(library or ["Island", "Lightning Bolt", "Grizzly Bears", "Opt"]),
        )
        .player("bob", battlefield=[target], graveyard=list(bob_graveyard))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_free_from_exile(scenario, name, targets=None):
    return _cast_free(scenario, name, targets=targets)


def _cast_end_blaze(scenario, x_value, target_name="Hill Giant"):
    target = scenario.creature(target_name, "bob")
    card = scenario.find("End-Blaze Epiphany", Zone.HAND, "alice")
    mountains = scenario.untapped_sources(*(["Mountain"] * (x_value + 1)), username="alice")
    scenario.game.cast(card, "alice", x_value=x_value, targets=[target], mana_sources=mountains)
    scenario.resolve_top()
    scenario.state_based_actions()
    return target


def test_end_blaze_exiles_cards_equal_to_the_dead_creatures_power_and_one_is_playable():
    scenario = _end_blaze_board(lands=5)
    lightning = scenario.player("alice").library[1]
    scenario.will_choose_cards(lightning, username="alice")
    giant = _cast_end_blaze(scenario, 3)
    assert giant.zone is Zone.GRAVEYARD
    while scenario.game.stack:
        scenario.resolve_top()

    assert sorted(c.name for c in scenario.game.exile) == [
        "Grizzly Bears",
        "Island",
        "Lightning Bolt",
    ]
    assert [c.name for c in scenario.player("alice").library] == ["Opt"]
    _cast_free_from_exile(scenario, "Lightning Bolt", targets=["bob"])
    scenario.resolve_top()
    assert scenario.player("bob").life == 17


def test_its_power_is_the_power_the_creature_last_had():
    """CR 603.10a: the creature's power as it last existed counts - three
    +1/+1 counters make the 3/3 Hill Giant a 6/6, and six cards are
    exiled."""
    scenario = _end_blaze_board(lands=7, library=["Island"] * 7)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.add_counters(giant, Counter.PLUS_ONE, 3)
    scenario.will_choose_cards(scenario.player("alice").library[0], username="alice")
    _cast_end_blaze(scenario, 6)
    assert giant.zone is Zone.GRAVEYARD
    while scenario.game.stack:
        scenario.resolve_top()
    assert len(scenario.game.exile) == 6


def test_a_creature_that_survives_triggers_nothing():
    scenario = _end_blaze_board()
    giant = _cast_end_blaze(scenario, 1)
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == []
    assert scenario.game.exile == []


def test_the_chosen_card_stays_playable_through_the_next_turn_only():
    scenario = _end_blaze_board(library=["Island", "Opt", "Opt"])
    island = scenario.player("alice").library[0]
    scenario.will_choose_cards(island, username="alice")
    _cast_end_blaze(scenario, 3)
    while scenario.game.stack:
        scenario.resolve_top()
    permissions = [p for p in scenario.game.play_permissions if p.names(island)]
    assert len(permissions) == 1
    assert permissions[0].expires_end_of_next_turn
    assert permissions[0].action.value == "play"


def test_burn_away_exiles_the_dead_creatures_controllers_graveyard():
    """The proof printing: the same "When that creature dies this turn"
    pair with a different consequence, "its controller" being the dead
    creature's controller."""
    scenario = (
        Scenario()
        .player("alice", hand=["Burn Away"], battlefield=["Mountain"] * 5, graveyard=["Opt"])
        .player("bob", battlefield=["Hill Giant"], graveyard=["Lightning Bolt", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve("Burn Away", auto=True, targets=[giant])
    scenario.state_based_actions()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").graveyard == []
    assert [c.name for c in scenario.player("alice").graveyard] == ["Opt", "Burn Away"]

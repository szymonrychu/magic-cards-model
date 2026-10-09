"""Scenario: "[This] enters with <counters>" lines that are not gated on a cast
fact - counted ("for each"), typed (-1/-1), and the group replacement "Each
<group> you control enters with an additional <counter>" (EP-01 round 1, T1).

- **CR 614.1c** - "[This permanent] enters with . . . ," is a replacement
  effect; an effect of another permanent can add counters to the entering
  object the same way (the group form).
- **CR 614.12** - the replacement is judged on the permanent as it would exist
  on the battlefield, so the entering creature's own subtypes decide a group.
- **CR 122.6** - counters a permanent "enters with" are put on it as it enters.
- **CR 700.4** - "dies" counts a creature put into a graveyard from the
  battlefield (Bloodcrazed Paladin counts them).

Every number was looked up with `mise run rules:find <n>`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _board(**kwargs):
    scenario = Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def test_dragonstorm_globe_adds_a_counter_to_a_dragon_entering():
    played = _board(battlefield=["Dragonstorm Globe"], hand=["Hellkite Whelp"])
    whelp = played.put_onto_battlefield("Hellkite Whelp")
    assert whelp.counters[Counter.PLUS_ONE] == 1


def test_dragonstorm_globe_ignores_a_non_dragon():
    played = _board(battlefield=["Dragonstorm Globe"], hand=["Elvish Warrior"])
    warrior = played.put_onto_battlefield("Elvish Warrior")
    assert warrior.counters[Counter.PLUS_ONE] == 0


def test_dragonstorm_globe_does_not_help_an_opponents_dragon():
    played = _board(battlefield=["Dragonstorm Globe"])
    scenario = Scenario().manual_turn_based_actions()
    scenario.player("alice", battlefield=["Dragonstorm Globe"]).player("bob", hand=["Hellkite Whelp"])
    opp = scenario.build()
    opp.start_at(Step.PRECOMBAT_MAIN)
    whelp = opp.put_onto_battlefield("Hellkite Whelp", "bob")
    assert whelp.counters[Counter.PLUS_ONE] == 0
    assert played is not None


def test_bramblewood_paragon_helps_other_warriors_but_not_itself():
    played = _board(hand=["Bramblewood Paragon", "Elvish Warrior"])
    paragon = played.put_onto_battlefield("Bramblewood Paragon")
    assert paragon.counters[Counter.PLUS_ONE] == 0
    warrior = played.put_onto_battlefield("Elvish Warrior")
    assert warrior.counters[Counter.PLUS_ONE] == 1


def test_oath_of_gideon_adds_a_loyalty_counter_to_a_planeswalker():
    played = _board(battlefield=["Oath of Gideon"], hand=["Jace Beleren"])
    jace = played.put_onto_battlefield("Jace Beleren")
    printed = int(jace.card.loyalty)
    assert jace.counters["loyalty"] == printed + 1


def test_squad_captain_counts_each_other_creature_you_control():
    played = _board(
        battlefield=["Elvish Warrior", "Goblin Piker"], hand=["Squad Captain"]
    )
    captain = played.put_onto_battlefield("Squad Captain")
    assert captain.counters[Counter.PLUS_ONE] == 2


def test_squad_captain_alone_enters_with_no_counters():
    played = _board(hand=["Squad Captain"])
    captain = played.put_onto_battlefield("Squad Captain")
    assert captain.counters[Counter.PLUS_ONE] == 0


def test_hamlet_vanguard_counts_two_per_other_nontoken_human():
    played = _board(battlefield=["Elite Vanguard", "Youthful Knight"], hand=["Hamlet Vanguard"])
    vanguard = played.put_onto_battlefield("Hamlet Vanguard")
    assert vanguard.counters[Counter.PLUS_ONE] == 4


def test_bloodcrazed_paladin_counts_creatures_that_died_this_turn():
    played = _board(hand=["Bloodcrazed Paladin"])
    played.game.creatures_died_this_turn = 3
    paladin = played.put_onto_battlefield("Bloodcrazed Paladin")
    assert paladin.counters[Counter.PLUS_ONE] == 3


def test_patched_plaything_cast_from_hand_enters_with_two_minus_counters():
    played = _board(hand=["Patched Plaything"], battlefield=["Plains", "Forest", "Forest"])
    thing = played.cast_and_resolve("Patched Plaything", auto=True)
    assert thing.zone is Zone.BATTLEFIELD
    assert thing.counters[Counter.MINUS_ONE] == 2


def test_patched_plaything_put_onto_the_battlefield_has_none():
    played = _board(hand=["Patched Plaything"])
    thing = played.put_onto_battlefield("Patched Plaything")
    assert thing.counters[Counter.MINUS_ONE] == 0

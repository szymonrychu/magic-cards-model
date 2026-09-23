"""Scenario: Mirror Box's three statics, and the readers they share.

Mirror Box: "The "legend rule" doesn't apply to permanents you control. /
Each legendary creature you control gets +1/+1. / Each nontoken creature you
control gets +1/+1 for each other creature you control with the same name as
that creature."

- The legendary anthem is the supertype qualifier (CR 205.4d) on the
  singular "each ... creature you control gets" subject. Arvad the Cursed
  ("Other legendary creatures you control get +2/+2.") is the second printing
  of the same qualifier on the plural subject.
- The same-name count is **per object**: "that creature" is each creature
  the effect applies to, so each one counts the *other* creatures sharing its
  own name (CR 201.2a: "Two or more objects have the same name if they have
  at least one name in common"). Heroes' Podium ("Each legendary creature you
  control gets +1/+1 for each other legendary creature you control.") is the
  second printing of the same per-object "for each other ... creature you
  control" count. No other printing legal in Modern, Pioneer or Standard
  carries the same-name clause itself (Scryfall search, 2026-09-23).
- "Nontoken" excludes a token (CR 111.1) from the group, not from the count:
  a token copy still has the name (CR 707.2) and still counts for the card
  it shares it with. Always Watching ("Nontoken creatures you control get
  +1/+1 and have vigilance.") is the second printing of the qualifier.

CR 611.3a keeps every group and count live, and every pump is layer 7c
(CR 613.4c). The legend-rule static (CR 704.5j) is pinned here too, since the
same card carries it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.token import token_copy_of
from tests.scenarios.harness import Scenario


def pt(scenario, state):
    chars = scenario.game.characteristics_of(state)
    return chars.power, chars.toughness


def printed(state):
    return int(state.card.power), int(state.card.toughness)


def plus(state, n):
    power, toughness = printed(state)
    return power + n, toughness + n


def board(alice=(), bob=()):
    scenario = (
        Scenario().player("alice", battlefield=list(alice)).player("bob", battlefield=list(bob))
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# --------------------------------------------------------------------------
# "Each legendary creature you control gets +1/+1."
# --------------------------------------------------------------------------


def test_mirror_box_pumps_a_legendary_creature_and_not_a_nonlegendary_one():
    scenario = board(alice=["Mirror Box", "Zurgo Bellstriker", "Grizzly Bears"])
    zurgo = scenario.creature("Zurgo Bellstriker")
    bears = scenario.creature("Grizzly Bears")

    assert pt(scenario, zurgo) == plus(zurgo, 1)
    assert pt(scenario, bears) == printed(bears)


def test_mirror_box_skips_an_opponents_legendary_creature():
    scenario = board(alice=["Mirror Box"], bob=["Zurgo Bellstriker"])
    theirs = scenario.creature("Zurgo Bellstriker", "bob")

    assert pt(scenario, theirs) == printed(theirs)


def test_arvad_pumps_other_legendary_creatures_but_not_itself():
    scenario = board(alice=["Arvad the Cursed", "Zurgo Bellstriker", "Grizzly Bears"])
    arvad = scenario.creature("Arvad the Cursed")
    zurgo = scenario.creature("Zurgo Bellstriker")
    bears = scenario.creature("Grizzly Bears")

    assert pt(scenario, zurgo) == plus(zurgo, 2)
    assert pt(scenario, arvad) == printed(arvad)
    assert pt(scenario, bears) == printed(bears)


# --------------------------------------------------------------------------
# The legend rule static, still handled
# --------------------------------------------------------------------------


def test_two_legends_with_one_name_both_stay_and_both_get_both_bonuses():
    """The legend rule (CR 704.5j) does not apply to alice's permanents, so the
    second Zurgo stays; each is legendary (+1/+1) and has one other creature
    sharing its name (+1/+1)."""
    scenario = board(alice=["Mirror Box", "Zurgo Bellstriker", "Zurgo Bellstriker"])

    scenario.game.check_state_based_actions()

    first, second = scenario.creatures("Zurgo Bellstriker", "Zurgo Bellstriker")
    assert first.zone is Zone.BATTLEFIELD and second.zone is Zone.BATTLEFIELD
    assert pt(scenario, first) == plus(first, 2)
    assert pt(scenario, second) == plus(second, 2)


def test_the_legend_rule_still_applies_to_the_opponent():
    scenario = board(alice=["Mirror Box"], bob=["Zurgo Bellstriker", "Zurgo Bellstriker"])

    scenario.game.check_state_based_actions()

    survivors = [
        state
        for state in scenario.game.permanents_controlled_by("bob")
        if state.name == "Zurgo Bellstriker"
    ]
    assert len(survivors) == 1


# --------------------------------------------------------------------------
# "... for each other creature you control with the same name as that creature."
# --------------------------------------------------------------------------


def test_each_creature_counts_the_others_sharing_its_own_name():
    scenario = board(
        alice=["Mirror Box", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Savannah Lions"]
    )
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears")
    lions = scenario.creature("Savannah Lions")

    for each in bears:
        assert pt(scenario, each) == plus(each, 2), "two other Grizzly Bears each"
    assert pt(scenario, lions) == printed(lions), "no other Savannah Lions"


def test_a_lone_creature_gets_nothing_from_the_count():
    scenario = board(alice=["Mirror Box", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")

    assert pt(scenario, bears) == printed(bears)


def test_an_opponents_creature_with_the_same_name_is_not_counted():
    """ "Other creature **you control**"."""
    scenario = board(alice=["Mirror Box", "Grizzly Bears"], bob=["Grizzly Bears"])
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    assert pt(scenario, mine) == printed(mine)
    assert pt(scenario, theirs) == printed(theirs)


def test_a_token_copy_counts_for_the_card_but_is_not_pumped_itself():
    """CR 707.2: the token copy has the name, so the card counts it; it is a
    token (CR 111.1), so "each nontoken creature" leaves it out."""
    scenario = board(alice=["Mirror Box", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    (token,) = token_copy_of(scenario.game, bears, "alice")

    assert pt(scenario, bears) == plus(bears, 1)
    assert pt(scenario, token) == printed(bears)


def test_the_count_updates_when_a_copy_leaves():
    scenario = board(alice=["Mirror Box", "Grizzly Bears", "Grizzly Bears"])
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears")
    assert pt(scenario, first) == plus(first, 1)

    scenario.game.put_into_graveyard(second)

    assert pt(scenario, first) == printed(first)


def test_both_bonuses_stop_when_mirror_box_leaves():
    scenario = board(alice=["Mirror Box", "Zurgo Bellstriker", "Grizzly Bears", "Grizzly Bears"])
    box = scenario.find("Mirror Box", Zone.BATTLEFIELD, "alice")
    zurgo = scenario.creature("Zurgo Bellstriker")
    first, _ = scenario.creatures("Grizzly Bears", "Grizzly Bears")

    scenario.game.put_into_graveyard(box)

    assert pt(scenario, zurgo) == printed(zurgo)
    assert pt(scenario, first) == printed(first)


def test_heroes_podium_counts_the_other_legendary_creatures_per_object():
    """Second printing of the per-object "for each other ... creature you
    control" count: each legend counts the *other* legends, so two legends get
    +1/+1 each and a lone one gets nothing; a nonlegendary creature is outside
    the group."""
    scenario = board(
        alice=["Heroes' Podium", "Zurgo Bellstriker", "Edgar, Moonlit Sovereign", "Grizzly Bears"]
    )
    zurgo = scenario.creature("Zurgo Bellstriker")
    edgar = scenario.creature("Edgar, Moonlit Sovereign")
    bears = scenario.creature("Grizzly Bears")

    assert pt(scenario, zurgo) == plus(zurgo, 1)
    assert pt(scenario, edgar) == plus(edgar, 1)
    assert pt(scenario, bears) == printed(bears)

    scenario.game.put_into_graveyard(edgar)

    assert pt(scenario, zurgo) == printed(zurgo)


# --------------------------------------------------------------------------
# "Nontoken creatures you control" - Always Watching
# --------------------------------------------------------------------------


def test_always_watching_pumps_and_grants_vigilance_to_nontoken_creatures_only():
    scenario = board(alice=["Always Watching", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    (token,) = token_copy_of(scenario.game, bears, "alice")

    assert pt(scenario, bears) == plus(bears, 1)
    assert has_keyword(bears, Keyword.VIGILANCE, scenario.game)
    assert pt(scenario, token) == printed(bears)
    assert not has_keyword(token, Keyword.VIGILANCE, scenario.game)

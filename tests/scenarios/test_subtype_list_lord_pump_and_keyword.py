"""Scenario: a lord over a serial list of creature subtypes that also grants a
keyword in the same sentence - "<subtype list> you control get +N/+N and have
<keyword>." (CR 613.4c layer 7c for the pump, CR 613.1f layer 6 for the
keyword, CR 613.6: one ability applying in more than one layer).

Raphael, Fiendish Savior: "Other Demons, Devils, Imps, and Tieflings you
control get +1/+1 and have lifelink." - an Oxford-comma four-item list with
"other" (Raphael himself, a Devil, is excluded).

Gisa, the Hellraiser (second, differently-shaped real printing - a two-item
list with no "other", no Oxford comma): "Skeletons and Zombies you control
get +1/+1 and have menace." Gisa is a Human, so nothing about her own
subtypes matters here; she proves the reader off the specific list Raphael
was reported on.

CR 205.3m: Demon, Devil, Imp, Tiefling, Skeleton, and Zombie are each their
own single-word creature type. CR 611.3a: the group is re-read live, not
"locked in" at resolution.
"""

from magic_cards_model.machines.combat import Keyword, has_keyword
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


# --------------------------------------------------------------------------
# Raphael, Fiendish Savior: four-item Oxford-comma list, "other", lifelink
# --------------------------------------------------------------------------


def test_raphael_pumps_and_grants_lifelink_to_each_listed_subtype():
    """Footlight Fiend is a Devil, Eccentric Apprentice a Tiefling, Arbiter of
    Woe a Demon - each is in the four-item list and gets both the pump and
    lifelink; Grizzly Bears (no listed subtype) gets neither."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Raphael, Fiendish Savior",
                "Footlight Fiend",
                "Eccentric Apprentice",
                "Arbiter of Woe",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )
    devil = scenario.creature("Footlight Fiend")
    tiefling = scenario.creature("Eccentric Apprentice")
    demon = scenario.creature("Arbiter of Woe")
    bears = scenario.creature("Grizzly Bears")

    for creature in (devil, tiefling, demon):
        assert pt(scenario, creature) == plus(creature, 1)
        assert has_keyword(creature, Keyword.LIFELINK, scenario.game)

    assert pt(scenario, bears) == printed(bears)
    assert not has_keyword(bears, Keyword.LIFELINK, scenario.game)


def test_raphael_does_not_pump_himself():
    """ "Other": Raphael is a Devil, and is excluded by identity."""
    scenario = (
        Scenario().player("alice", battlefield=["Raphael, Fiendish Savior"]).player("bob").build()
    )
    raphael = scenario.creature("Raphael, Fiendish Savior")

    assert pt(scenario, raphael) == printed(raphael)
    assert not has_keyword(raphael, Keyword.LIFELINK, scenario.game)


def test_raphaels_grant_skips_an_opponents_matching_creature():
    """ "you control" - bob's Devil is outside the group."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raphael, Fiendish Savior"])
        .player("bob", battlefield=["Footlight Fiend"])
        .build()
    )
    theirs = scenario.creature("Footlight Fiend", "bob")

    assert pt(scenario, theirs) == printed(theirs)
    assert not has_keyword(theirs, Keyword.LIFELINK, scenario.game)


# --------------------------------------------------------------------------
# Gisa, the Hellraiser: second, differently-shaped printing - two-item list,
# no "other", menace instead of lifelink
# --------------------------------------------------------------------------


def test_gisa_pumps_and_grants_menace_to_skeletons_and_zombies():
    """Cult Conscript is a Skeleton, Carrion Feeder a Zombie - both get the
    pump and menace; Grizzly Bears (neither) gets nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Gisa, the Hellraiser",
                "Cult Conscript",
                "Carrion Feeder",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )
    skeleton = scenario.creature("Cult Conscript")
    zombie = scenario.creature("Carrion Feeder")
    bears = scenario.creature("Grizzly Bears")

    for creature in (skeleton, zombie):
        assert pt(scenario, creature) == plus(creature, 1)
        assert has_keyword(creature, Keyword.MENACE, scenario.game)

    assert pt(scenario, bears) == printed(bears)
    assert not has_keyword(bears, Keyword.MENACE, scenario.game)


def test_gisa_pumps_a_zombie_that_arrives_later():
    """CR 611.3a: the group is re-read live, not fixed at resolution. A token
    copy of Carrion Feeder made after Gisa is already on the battlefield is
    still a Zombie and still gets the pump and menace."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gisa, the Hellraiser", "Carrion Feeder"])
        .player("bob")
        .build()
    )
    zombie = scenario.creature("Carrion Feeder")
    (token,) = token_copy_of(scenario.game, zombie, "alice")

    assert pt(scenario, token) == plus(zombie, 1)
    assert has_keyword(token, Keyword.MENACE, scenario.game)

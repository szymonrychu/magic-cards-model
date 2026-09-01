"""Judge scenarios: the ante zone, and the cards that move things into it.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#666** - How does Ante Work?

Ante is still in the Comprehensive Rules (CR 407), and the episode is a tour of
it: the ante zone is a public zone (CR 400.2), only a card's owner may ante a
card (CR 407.4), and an ante card's own ability fails closed when the ante it
depends on cannot happen.

The zone is built - `Zone.ANTE` is CR 400.1's optional eighth, shared and
public, and `Game.ante` is CR 407.4's verb with its owner check - and so is
Jeweled Bird's own ability, read off its printed text by
`machines/effects._parse_ante_self_if_you_do_clause` rather than a card-name
row. Jeweled Bird's real oracle text, confirmed with `resolve_cards`: "Remove
this card from your deck before playing if you're not playing for ante. /
{T}: Ante this artifact. If you do, put all other cards you own from the ante
into your graveyard, then draw a card." Nothing in this file is `xfail` any
more.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_the_seven_rules_zones_are_modelled_and_so_is_ante():
    """CR 400.1: "There are normally seven zones: library, hand, battlefield,
    graveyard, stack, exile, and command. Some older cards also use the ante
    zone."

    The engine models the seven, that optional eighth, and the sideboard - which
    is not a zone at all (CR 400.11a). CR 400.2 makes the ante zone a public
    zone alongside the graveyard, battlefield, stack and exile, which is the
    episode's "all cards in it are face up", and CR 400.1 makes it shared rather
    than one pile per player.
    """
    assert {zone.value for zone in Zone} == {
        "library",
        "hand",
        "battlefield",
        "graveyard",
        "stack",
        "exile",
        "command",
        "ante",
        "sideboard",
    }
    assert Zone.ANTE.is_shared
    assert not Zone.ANTE.is_hidden, "CR 400.2: ante is a public zone"
    assert not Zone.ANTE.is_outside_the_game


def test_only_the_owner_can_ante_a_card():
    """CR 407.4: "To ante an object is to put that object into the ante zone
    from whichever zone it's currently in. The owner of an object is the only
    player who can ante that object."

    The stolen-Bird half of DDR#666, at the level of the verb: bob, who does not
    own the Bird, cannot ante it, and `Game.ante` answers False without moving
    anything - which is what makes Jeweled Bird's own "If you do" false.
    """
    scenario = Scenario().player("alice", battlefield=["Jeweled Bird"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")

    assert scenario.game.ante(bird, "bob") is False
    assert bird.zone is Zone.BATTLEFIELD
    assert scenario.game.ante_zone == []

    assert scenario.game.ante(bird, "alice") is True
    assert bird.zone is Zone.ANTE
    assert scenario.game.ante_zone == [bird]
    assert bird not in scenario.game.battlefield


def test_anteing_a_card_from_a_hidden_zone_takes_it_out_of_that_zone_too():
    """ "from whichever zone it's currently in" - the ante verb is not a
    battlefield-only move, so a card in hand goes just as readily."""
    scenario = Scenario().player("alice", hand=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    assert scenario.game.ante(bears, "alice") is True

    assert bears.zone is Zone.ANTE
    assert [state.name for state in scenario.player("alice").hand] == []


def test_anteing_the_bird_moves_it_out_of_the_battlefield():
    """CR 407.4: "To ante an object is to put that object into the ante zone
    from whichever zone it's currently in."

    Jeweled Bird's own first instruction is to ante itself, so a resolution that
    worked would leave the battlefield without it.
    """
    scenario = Scenario().player("alice", battlefield=["Jeweled Bird"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")

    scenario.activate(bird)
    scenario.resolve_top()

    assert bird.zone is not Zone.BATTLEFIELD


def test_the_owner_antes_the_bird_and_draws_a_card():
    """The half of the episode's Jeweled Bird question that is supposed to work.

    CR 407.4: "The owner of an object is the only player who can ante that
    object" - and here the owner is doing it, so the ante happens, and the "If
    you do" clause that follows it does too. The stolen-Bird case the episode
    actually asks about is the mirror image, and is the test below this one:
    with the ante refused, that same "if you do" is false and *nothing* in the
    ability happens.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Grizzly Bears"], battlefield=["Jeweled Bird"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")

    scenario.activate(bird)
    scenario.resolve_top()

    assert bird.zone is not Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_a_stolen_bird_antes_nothing_and_the_rest_of_its_ability_does_not_happen():
    """DDR#666's actual question: bob has taken control of alice's Jeweled Bird
    and activates it.

    CR 407.4: "The owner of an object is the only player who can ante that
    object." Bob controls the Bird but alice owns it (CR 108.3: "The owner of a
    card in the game is the player who started the game with it in their
    deck"), so the ante is refused. "If you do" is therefore false, and the
    whole rest of the ability - the graveyard sweep and the draw - does not
    happen either: one paragraph, all of it or none of it.
    """
    scenario = (
        Scenario()
        .player("bob", library=["Grizzly Bears"])
        .player("alice", battlefield=["Jeweled Bird"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")
    assert bird.owner == "alice"
    bird.controller = "bob"

    scenario.activate(bird, username="bob")
    scenario.resolve_top()

    assert bird.zone is Zone.BATTLEFIELD
    assert scenario.game.ante_zone == []
    assert [state.name for state in scenario.player("bob").hand] == []


def test_the_bird_sweeps_only_the_owners_other_ante_cards_into_the_graveyard():
    """ "Put all other cards you own from the ante into your graveyard."

    "Other" excludes the Bird itself, which CR 407.4 has just put into the same
    zone, and "you own" excludes an opponent's ante card sitting beside it -
    CR 400.3 would send it to bob's graveyard rather than alice's anyway, and
    the card does not say to move it at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Grizzly Bears"],
            hand=["Llanowar Elves"],
            battlefield=["Jeweled Bird"],
        )
        .player("bob", hand=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    memnite = scenario.find("Memnite", Zone.HAND, "bob")
    assert scenario.game.ante(elves, "alice") is True
    assert scenario.game.ante(memnite, "bob") is True

    scenario.activate(bird)
    scenario.resolve_top()

    assert elves.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.ANTE, "bob owns it, so the Bird does not move it"
    assert bird.zone is Zone.ANTE, "'other' does not include the Bird itself"
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]

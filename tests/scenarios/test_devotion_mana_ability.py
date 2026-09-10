"""Nykthos, Shrine to Nyx's devotion mana ability (CR 605.1a, CR 605.3b, CR 700.5).

"{2}, {T}: Choose a color. Add an amount of mana of that color equal to your
devotion to that color."

It meets every one of CR 605.1a's criteria - no target, it could add mana, it
is not a loyalty ability - so it is a mana ability and CR 605.3b keeps it off
the stack entirely. The only thing that separates it from "Add one mana of any
color" is that the *count* is CR 700.5's devotion, which cannot be known from
the printed text: it is the number of mana symbols of the chosen colour among
the mana costs of permanents its controller controls, counted at the moment
the ability is activated.

CR 605.2 is what makes the zero-devotion case interesting: "A mana ability
remains a mana ability even if the game state doesn't allow it to produce
mana", so activating it for a colour nobody has a symbol of is perfectly
legal and simply adds nothing.

CR 107.4e (a hybrid mana symbol is also a coloured mana symbol) and CR 107.4f
(Phyrexian mana symbols are coloured mana symbols) are why Kitchen Finks'
{G/W}{G/W} is two green symbols *and* two white ones, and why Tamiyo,
Compleated Sage's {G/U/P} counts for both green and blue.

The `{2}` half is CR 602.1a's activation cost, and CR 602.2b imports CR
601.2b-i wholesale, so it has to be really paid before any mana arrives.

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 113.4, CR 605.1a, CR 605.2, CR 605.3b, CR 700.5, CR 107.4e, CR 107.4f,
CR 202.2d, CR 602.1a, CR 602.2, CR 602.2b.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario

NYKTHOS = "Nykthos, Shrine to Nyx"

#: The devotion ability is the card's second printed ability; `{T}: Add {C}.`
#: is the first. Both are activated abilities of the same permanent, so the
#: index is the only thing that tells them apart.
COLORLESS_ABILITY = 0
DEVOTION_ABILITY = 1


def board(
    *,
    alice_battlefield: list[str],
    alice_hand: list[str] | None = None,
    bob_battlefield: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice_battlefield, hand=alice_hand or [])
        .player("bob", battlefield=bob_battlefield or [])
    )


def test_devotion_mana_pays_for_a_spell():
    """The happy path: two green symbols on the board, two green mana out,
    and that mana casts a {1}{G} creature (CR 700.5, CR 605.3b)."""
    scenario = board(
        alice_battlefield=[NYKTHOS, "Forest", "Forest", "Kitchen Finks"],
        alice_hand=["Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(nykthos, *forests, index=DEVOTION_ABILITY, color=Color.GREEN)

    # Kitchen Finks' {1}{G/W}{G/W} is two green symbols (CR 107.4e).
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}

    casting = scenario.cast("Grizzly Bears")
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    bears = scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.floating == {}


def test_a_one_element_colour_sequence_is_the_same_choice_as_a_bare_colour():
    """The colour may be named as a list of one, and it still means "that
    colour" rather than "one mana of it".

    `Action.color_choice_count` is 1 for this ability - the count of colours to
    name, not the count of mana it makes, which CR 700.5's devotion decides
    only at activation - so a caller that reads that field and hands back a
    list of that length is doing exactly what the enumeration asked of it. It
    used to be handed one green mana on a board with devotion 2, silently: the
    worst answer available, since nothing about it looks like a refusal.
    """
    scenario = board(alice_battlefield=[NYKTHOS, "Forest", "Forest", "Kitchen Finks"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(nykthos, *forests, index=DEVOTION_ABILITY, color=[Color.GREEN])

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_the_ability_never_goes_on_the_stack():
    """CR 605.3b: an activated mana ability does not go on the stack at all,
    so there is nothing to respond to and `activate` hands back no ability."""
    scenario = board(alice_battlefield=[NYKTHOS, "Forest", "Forest", "Kitchen Finks"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    returned = scenario.activate(nykthos, *forests, index=DEVOTION_ABILITY, color=Color.GREEN)

    assert returned is None
    assert scenario.stack_names() == []
    assert scenario.game.pending_triggers == []
    # The mana is already in the pool: CR 605.3b resolves it immediately.
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_hybrid_symbols_count_toward_devotion_for_both_of_their_colors():
    """CR 107.4e: "A hybrid mana symbol is also a colored mana symbol." Kitchen
    Finks' {1}{G/W}{G/W} is two green symbols and, on the same board with
    nothing else changing, two white ones (CR 202.2d)."""
    scenario = board(alice_battlefield=[NYKTHOS, "Forest", "Forest", "Kitchen Finks"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(nykthos, *forests, index=DEVOTION_ABILITY, color=Color.WHITE)

    assert scenario.player("alice").mana_pool.floating == {Color.WHITE: 2}


def test_phyrexian_symbols_count_toward_devotion():
    """CR 107.4f: "Phyrexian mana symbols are colored mana symbols." Tamiyo,
    Compleated Sage's {2}{G}{G/U/P}{U} carries two blue symbols - the plain
    {U} and the Phyrexian half of {G/U/P} - so devotion to blue is 2 even
    though nothing else on the board is blue at all."""
    scenario = board(
        alice_battlefield=[NYKTHOS, "Forest", "Forest", "Tamiyo, Compleated Sage"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(nykthos, *forests, index=DEVOTION_ABILITY, color=Color.BLUE)

    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 2}


def test_a_land_has_no_mana_cost_so_it_contributes_nothing():
    """CR 700.5 counts mana symbols "among the mana costs of permanents that
    player controls". A Forest has no mana cost at all, so a board of nothing
    but lands has devotion 0 to green however green those lands are."""
    scenario = board(alice_battlefield=[NYKTHOS, "Forest", "Forest", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(nykthos, *forests, index=DEVOTION_ABILITY, color=Color.GREEN)

    assert scenario.player("alice").mana_pool.floating == {}


def test_zero_devotion_produces_nothing_and_is_still_legal_to_activate():
    """CR 605.2: "A mana ability remains a mana ability even if the game state
    doesn't allow it to produce mana." Alice has green and white symbols and
    no blue one; choosing blue is a legal activation that adds no mana."""
    scenario = board(alice_battlefield=[NYKTHOS, "Forest", "Forest", "Kitchen Finks"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")

    assert scenario.why_cannot_activate(nykthos, DEVOTION_ABILITY) is None

    returned = scenario.activate(nykthos, *forests, index=DEVOTION_ABILITY, color=Color.BLUE)

    assert returned is None
    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {}
    # The cost was still paid in full: the ability happened, it just did nothing.
    assert not nykthos.untapped
    assert all(not forest.untapped for forest in forests)


def test_an_opponents_permanents_do_not_count():
    """CR 700.5 counts only permanents "that player controls". Bob's Kitchen
    Finks is two green symbols on the battlefield and none of them are
    alice's."""
    scenario = board(
        alice_battlefield=[NYKTHOS, "Forest", "Forest"],
        bob_battlefield=["Kitchen Finks"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(nykthos, *forests, index=DEVOTION_ABILITY, color=Color.GREEN)

    assert scenario.player("alice").mana_pool.floating == {}


def test_one_mana_short_leaves_the_ability_unactivated():
    """CR 602.1a's activation cost is `{2}, {T}`, and CR 602.2b imports CR
    601.2h's payment step - so a single Forest is not enough, and the refusal
    rewinds cleanly: Nykthos stays untapped and no mana is left floating."""
    scenario = board(alice_battlefield=[NYKTHOS, "Forest", "Kitchen Finks"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    (forest,) = scenario.untapped_sources("Forest")

    with pytest.raises(ValueError, match="cannot pay"):
        scenario.activate(nykthos, forest, index=DEVOTION_ABILITY, color=Color.GREEN)

    assert nykthos.untapped
    assert scenario.player("alice").mana_pool.floating == {}
    assert scenario.stack_names() == []


def test_the_colorless_ability_is_a_separate_ability_that_still_works():
    """Nykthos prints two abilities. `{T}: Add {C}.` is the first, costs no
    mana, ignores devotion entirely, and is a mana ability in its own right
    (CR 605.1a, CR 605.3b)."""
    scenario = board(alice_battlefield=[NYKTHOS, "Kitchen Finks"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nykthos = scenario.creature(NYKTHOS, "alice")
    returned = scenario.activate(nykthos, index=COLORLESS_ABILITY)

    assert returned is None
    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}
    assert not nykthos.untapped

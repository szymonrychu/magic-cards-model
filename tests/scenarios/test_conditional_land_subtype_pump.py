"""Scenario: a creature's own "gets +N/+N as long as you control a <land
subtype>" static (Wild Nacatl, Kird Ape).

The template is "This creature gets +P/+T as long as you control a <subtype>."
- a self pump in layer 7, sublayer 7c (CR 613.4c: "Effects that modify power
and/or toughness, but don't set power and/or toughness to a specific number or
value"), gated by a live board condition. CR 611.3a: a continuous effect from a
static ability "isn't 'locked in'; it applies at any given moment to whatever
its text indicates", so the condition is re-asked every time the board is
computed (CR 613.5) - it follows a land that enters, leaves, or changes type.
CR 205.3i lists the land types and CR 305.6 names the basic ones (Plains,
Island, Swamp, Mountain, Forest); the condition only reads the subtype, so a dual land such as Stomping Ground
(Mountain Forest) satisfies it too.

**Wild Nacatl** carries two such lines (Mountain and Plains) that stack;
**Kird Ape** (a different subtype, Forest, and a different bonus, +1/+2)
proves the reader is not fitted to Nacatl's wording or numbers.
"""

from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from tests.cards import card_state


def permanent(name: str, controller: str = "alice", **kwargs):
    return card_state(
        name, zone=Zone.BATTLEFIELD, controller=controller, owner=controller, **kwargs
    )


def pt(creature, *others) -> tuple[int, int]:
    cards = [creature, *others]
    view = compute_board(cards, static_effects(cards)).of(creature)
    return view.power, view.toughness


# --- Wild Nacatl --------------------------------------------------------


def test_nacatl_is_a_plain_1_1_with_no_lands():
    assert pt(permanent("Wild Nacatl")) == (1, 1)


def test_nacatl_gets_plus_one_with_a_mountain():
    assert pt(permanent("Wild Nacatl"), permanent("Mountain")) == (2, 2)


def test_nacatl_gets_plus_one_with_a_plains():
    assert pt(permanent("Wild Nacatl"), permanent("Plains")) == (2, 2)


def test_nacatl_gets_both_bonuses_with_mountain_and_plains():
    assert pt(permanent("Wild Nacatl"), permanent("Mountain"), permanent("Plains")) == (3, 3)


def test_two_mountains_are_still_one_bonus():
    assert pt(permanent("Wild Nacatl"), permanent("Mountain"), permanent("Mountain")) == (2, 2)


def test_other_basic_land_types_give_nothing():
    nacatl = permanent("Wild Nacatl")
    assert pt(nacatl, permanent("Forest"), permanent("Island"), permanent("Swamp")) == (1, 1)


def test_an_opponents_mountain_gives_nothing():
    assert pt(permanent("Wild Nacatl"), permanent("Mountain", controller="bob")) == (1, 1)


def test_the_bonus_follows_the_land_leaving():
    """The board is recomputed (CR 613.5), so once the Mountain is no longer
    among the battlefield's permanents the bonus is gone."""
    nacatl, mountain = permanent("Wild Nacatl"), permanent("Mountain")
    assert pt(nacatl, mountain) == (2, 2)
    assert pt(nacatl) == (1, 1)


def test_a_dual_land_with_both_types_gives_both_bonuses():
    """Stomping Ground is a Mountain Forest; Temple Garden a Forest Plains."""
    assert pt(permanent("Wild Nacatl"), permanent("Stomping Ground")) == (2, 2)
    assert pt(permanent("Wild Nacatl"), permanent("Stomping Ground"), permanent("Plains")) == (3, 3)
    assert pt(permanent("Wild Nacatl"), permanent("Temple Garden")) == (2, 2)


def test_a_land_that_changes_type_is_followed_live():
    """Blood Moon (CR 305.7: nonbasic lands become Mountains) turns Temple
    Garden (Forest Plains) into a plain Mountain: Plains is lost, Mountain
    gained, so the +1/+1 stays but only once."""
    nacatl, garden, moon = (
        permanent("Wild Nacatl"),
        permanent("Temple Garden"),
        permanent("Blood Moon"),
    )
    assert pt(nacatl, garden) == (2, 2)
    assert pt(nacatl, garden, moon) == (2, 2)
    cavern = permanent("Cavern of Souls")
    assert pt(nacatl, cavern) == (1, 1)
    assert pt(nacatl, cavern, moon) == (2, 2)


def test_two_nacatls_each_count_the_lands_independently():
    first, second, mountain = (
        permanent("Wild Nacatl"),
        permanent("Wild Nacatl"),
        permanent("Mountain"),
    )
    cards = [first, second, mountain]
    board = compute_board(cards, static_effects(cards))
    assert (board.of(first).power, board.of(second).power) == (2, 2)


# --- Kird Ape (second printing, different subtype and numbers) ------------


def test_kird_ape_gets_plus_one_plus_two_with_a_forest():
    ape = permanent("Kird Ape")
    assert pt(ape) == (1, 1)
    assert pt(ape, permanent("Forest")) == (2, 3)


def test_kird_ape_ignores_non_forests_and_opponents_forests():
    ape = permanent("Kird Ape")
    assert pt(ape, permanent("Mountain"), permanent("Forest", controller="bob")) == (1, 1)


def test_kird_ape_counts_a_dual_land_with_the_forest_type():
    assert pt(permanent("Kird Ape"), permanent("Stomping Ground")) == (2, 3)

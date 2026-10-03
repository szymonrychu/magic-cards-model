"""A land animated by "... It becomes a N/N <type> creature ... It's still a land."

The sentence after the animation, "It's still a land.", is CR 205.1b's
retention phrase read as its own sentence (Nissa, Who Shakes the World prints
it inline as "that's still a land"): the land keeps every prior card type and
subtype, so an animated Mountain is still a Mountain, still a land, still taps
for mana (CR 305.6, CR 106.1).

Cards (real printings):

- Koth of the Hammer +1: "Untap target Mountain. It becomes a 4/4 red
  Elemental creature until end of turn. It's still a land."
- Wakeroot Elemental: "{G}{G}{G}{G}{G}: Untap target land you control. It
  becomes a 5/5 Elemental creature with haste. It's still a land."
- Waker of the Wilds: "{X}{G}{G}: Put X +1/+1 counters on target land you
  control. That land becomes a 0/0 Elemental creature with haste. It's still
  a land."
- Tendril of the Mycotyrant: "{5}{G}{G}: Put seven +1/+1 counters on target
  noncreature land you control. It becomes a 0/0 Fungus creature with haste.
  It's still a land."
- Titania, Gaea Incarnate: "{3}{G}: Put four +1/+1 counters on target land you
  control. It becomes a 0/0 Elemental creature with haste. It's still a land."
- Roaring Earth's Channel: "{X}{G}{G}, Discard this card: Put X +1/+1
  counters on target land you control. It becomes a 0/0 green Spirit
  creature with haste. It's still a land."

Rules: CR 205.1b (retention), CR 611.2a (no duration lasts for the rest of
the game; "until end of turn" ends at cleanup, CR 514.2), CR 613.4b/c (the
0/0 is set in 7b, counters stack in 7c, so the land survives, CR 704.5f),
CR 702.10b (haste), CR 122.1a (+1/+1 counters).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario, mana_from


def _board(alice_battlefield, *, hand=None, bob=None):
    scenario = (
        Scenario()
        .player("alice", hand=hand or [], battlefield=alice_battlefield, library=["Island"] * 5)
        .player("bob", battlefield=bob or [], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _computed(scenario, card):
    return scenario.game.computed_board().of(card)


def _next_turn_of(scenario, username):
    while scenario.game.turn.active_player == username:
        scenario.advance()
    while scenario.game.turn.active_player != username:
        scenario.advance()


def _assert_still_a_land(computed, *types):
    assert computed.is_creature
    assert computed.is_land, "CR 205.1b: it's still a land"
    for each in types:
        assert each in computed.subtypes, f"CR 205.1b keeps {each}"


# -- Koth of the Hammer: untap, 4/4 red Elemental until end of turn ----------


def _koth_plus_one(scenario, mountain):
    koth = scenario.find("Koth of the Hammer", Zone.BATTLEFIELD, "alice")
    scenario.activate(koth, index=0, targets=[mountain])
    scenario.pass_until_resolved()
    return koth


def test_koth_untaps_the_mountain_and_makes_it_a_four_four_red_elemental_land():
    scenario = _board(["Koth of the Hammer", "Mountain", "Forest"])
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    mountain.tapped = True
    koth = _koth_plus_one(scenario, mountain)

    assert koth.loyalty == 4 and not mountain.tapped
    computed = _computed(scenario, mountain)
    _assert_still_a_land(computed, "Mountain", "Elemental")
    assert (computed.power, computed.toughness) == (4, 4)
    assert computed.colors == (Color.RED,)
    assert Type.LAND in computed.types


def test_koth_animation_ends_at_the_end_of_the_turn():
    scenario = _board(["Koth of the Hammer", "Mountain"])
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    _koth_plus_one(scenario, mountain)
    assert _computed(scenario, mountain).is_creature

    _next_turn_of(scenario, "alice")
    computed = _computed(scenario, mountain)
    assert not computed.is_creature and computed.is_land
    assert mountain.zone is Zone.BATTLEFIELD


def test_an_animated_mountain_still_taps_for_mana():
    scenario = _board(["Koth of the Hammer", "Mountain"])
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    _koth_plus_one(scenario, mountain)
    assert mana_from(mountain) == [Color.RED]
    scenario.activate(mountain, index=0)
    assert mountain.tapped
    assert scenario.player("alice").mana_pool.total == 1


def test_koth_cannot_target_a_non_mountain():
    scenario = _board(["Koth of the Hammer", "Forest"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError):
        _koth_plus_one(scenario, forest)


def test_koth_animated_mountain_that_entered_this_turn_needs_haste_it_does_not_have():
    """Koth grants no haste: a Mountain played this turn is a summoning-sick
    creature (CR 302.6)."""
    scenario = _board(["Koth of the Hammer"], hand=["Mountain"])
    fresh = scenario.play_land("Mountain")
    _koth_plus_one(scenario, fresh)
    scenario.advance()
    scenario.advance()
    assert not scenario.can_attack(fresh)


# -- Wakeroot Elemental: untap, 5/5 Elemental with haste, no duration --------


def test_wakeroot_elemental_makes_an_untapped_five_five_hasty_elemental_land():
    scenario = _board(["Wakeroot Elemental"] + ["Forest"] * 5 + ["Island"])
    forests = scenario.untapped_sources(*["Forest"] * 5, username="alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    island.tapped = True
    wakeroot = scenario.find("Wakeroot Elemental", Zone.BATTLEFIELD, "alice")
    scenario.activate(wakeroot, *forests, index=0, targets=[island])
    scenario.pass_until_resolved()

    assert not island.tapped
    computed = _computed(scenario, island)
    _assert_still_a_land(computed, "Island", "Elemental")
    assert (computed.power, computed.toughness) == (5, 5)
    assert computed.has_ability("Haste")


def test_wakeroot_animation_is_permanent_and_a_fresh_land_attacks_at_once():
    scenario = _board(["Wakeroot Elemental"] + ["Forest"] * 5, hand=["Island"])
    forests = scenario.untapped_sources(*["Forest"] * 5, username="alice")
    fresh = scenario.play_land("Island")
    wakeroot = scenario.find("Wakeroot Elemental", Zone.BATTLEFIELD, "alice")
    scenario.activate(wakeroot, *forests, index=0, targets=[fresh])
    scenario.pass_until_resolved()
    scenario.advance()
    scenario.advance()
    assert scenario.can_attack(fresh), "CR 702.10b: haste"

    _next_turn_of(scenario, "alice")
    computed = _computed(scenario, fresh)
    assert computed.is_creature and (computed.power, computed.toughness) == (5, 5)


# -- Waker of the Wilds: X counters, then 0/0 ---------------------------------


def test_waker_of_the_wilds_x_counters_keep_the_zero_zero_land_alive():
    scenario = _board(["Waker of the Wilds", "Forest", "Forest", "Forest", "Forest", "Island"])
    forests = scenario.untapped_sources(*["Forest"] * 4, username="alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    waker = scenario.find("Waker of the Wilds", Zone.BATTLEFIELD, "alice")
    scenario.activate(waker, *forests, index=0, targets=[island], x_value=2)
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert island.counters[Counter.PLUS_ONE] == 2
    computed = _computed(scenario, island)
    _assert_still_a_land(computed, "Island", "Elemental")
    assert (computed.power, computed.toughness) == (2, 2), "0/0 set, counters on top"
    assert computed.has_ability("Haste")
    assert island.zone is Zone.BATTLEFIELD, "CR 704.5f: not 0 toughness"


def test_waker_with_x_zero_leaves_a_zero_zero_land_that_dies():
    scenario = _board(["Waker of the Wilds", "Forest", "Forest", "Island"])
    forests = scenario.untapped_sources(*["Forest"] * 2, username="alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    waker = scenario.find("Waker of the Wilds", Zone.BATTLEFIELD, "alice")
    scenario.activate(waker, *forests, index=0, targets=[island], x_value=0)
    scenario.pass_until_resolved()
    scenario.state_based_actions()
    assert island.zone is Zone.GRAVEYARD, "CR 704.5f: 0/0 with no counters"


# -- Tendril of the Mycotyrant: seven counters on a noncreature land ----------


def test_tendril_of_the_mycotyrant_makes_a_seven_seven_fungus_land():
    scenario = _board(["Tendril of the Mycotyrant"] + ["Forest"] * 7)
    forests = scenario.untapped_sources(*["Forest"] * 7, username="alice")
    target = forests[0]
    tendril = scenario.find("Tendril of the Mycotyrant", Zone.BATTLEFIELD, "alice")
    scenario.activate(tendril, *forests, index=0, targets=[target])
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert target.counters[Counter.PLUS_ONE] == 7
    computed = _computed(scenario, target)
    _assert_still_a_land(computed, "Forest", "Fungus")
    assert (computed.power, computed.toughness) == (7, 7)
    assert computed.has_ability("Haste")
    assert mana_from(target) == [Color.GREEN]


def test_tendril_cannot_target_a_creature_land():
    scenario = _board(["Tendril of the Mycotyrant"] + ["Forest"] * 7)
    forests = scenario.untapped_sources(*["Forest"] * 7, username="alice")
    tendril = scenario.find("Tendril of the Mycotyrant", Zone.BATTLEFIELD, "alice")
    scenario.activate(tendril, *forests, index=0, targets=[forests[0]])
    scenario.pass_until_resolved()
    for each in forests:
        each.tapped = False
    with pytest.raises(ValueError):
        scenario.activate(tendril, *forests, index=0, targets=[forests[0]])


# -- Titania, Gaea Incarnate: four counters ----------------------------------


def test_titania_makes_a_four_four_elemental_land():
    scenario = _board(["Titania, Gaea Incarnate", "Forest", "Forest", "Forest", "Forest", "Island"])
    forests = scenario.untapped_sources(*["Forest"] * 4, username="alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    titania = scenario.find("Titania, Gaea Incarnate", Zone.BATTLEFIELD, "alice")
    scenario.activate(titania, *forests, index=0, targets=[island])
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert island.counters[Counter.PLUS_ONE] == 4
    computed = _computed(scenario, island)
    _assert_still_a_land(computed, "Island", "Elemental")
    assert (computed.power, computed.toughness) == (4, 4)
    assert computed.has_ability("Haste")


# -- Roaring Earth: Channel, X counters, 0/0 green Spirit with haste ---------


def test_roaring_earth_channel_animates_a_land_with_x_counters():
    scenario = _board(["Forest", "Forest", "Forest", "Island"], hand=["Roaring Earth"])
    forests = scenario.untapped_sources(*["Forest"] * 3, username="alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    earth = scenario.find("Roaring Earth", Zone.HAND, "alice")
    activation = off_battlefield_activation(
        scenario.game, earth, "alice", targets=[island], x_value=1
    )
    payment = activation.begin_paying()
    for forest in forests:
        payment.tap_for_mana(forest, mana_from(forest))
    payment.pay()
    activation.activate()
    activation.resolve()
    scenario.state_based_actions()

    assert earth.zone is Zone.GRAVEYARD
    assert island.counters[Counter.PLUS_ONE] == 1
    computed = _computed(scenario, island)
    _assert_still_a_land(computed, "Island", "Spirit")
    assert (computed.power, computed.toughness) == (1, 1)
    assert computed.colors == (Color.GREEN,)
    assert computed.has_ability("Haste")


# -- the retention clause may name a subtype: "It's still a Cave land." ------


def test_cavernous_maw_is_still_a_cave_land_until_end_of_turn():
    """CR 205.1b: "It's still a Cave land." retains land and Cave."""
    scenario = _board(
        ["Cavernous Maw", "Captivating Cave", "Echoing Deeps", "Sunken Citadel", "Forest", "Forest"]
    )
    maw = scenario.find("Cavernous Maw", Zone.BATTLEFIELD, "alice")
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.activate(maw, *forests, index=1)
    scenario.pass_until_resolved()

    computed = _computed(scenario, maw)
    _assert_still_a_land(computed, "Cave", "Elemental")
    assert (computed.power, computed.toughness) == (3, 3)
    _next_turn_of(scenario, "alice")
    assert not _computed(scenario, maw).is_creature


# -- nothing the template names may be left unread ---------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Koth of the Hammer",
        "Roaring Earth",
        "Tendril of the Mycotyrant",
        "Titania, Gaea Incarnate",
        "Waker of the Wilds",
        "Wakeroot Elemental",
        "Cavernous Maw",
    ],
)
def test_the_still_a_land_sentence_is_read_not_dropped(name):
    from magic_cards_model.support import card_support
    from tests.cards import card

    unread = [
        clause.reason
        for clause in card_support(card(name)).clauses
        if "still a" in clause.text and clause.outcome != "handled"
    ]
    assert unread == []

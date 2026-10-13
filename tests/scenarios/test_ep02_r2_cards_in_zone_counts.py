"""Scenario: cards in a hand / graveyard / library counted as an amount, and
"half" of a zone (EP-02 R2 T2).

One reader family, many sentences: "for each card in your hand", "the number
of cards in their hand", "for each card in your opponents' hands", "for each
<type> card in your opponents' graveyards", "for each card with cycling in
your graveyard", and "half the cards in their hand / half their library /
half the creatures they control, rounded up|down".

CR numbers below were read with `mise run rules:find` in the session that
wrote this file:

- **CR 107.1a** - a fractional amount is rounded the way the card says.
- **CR 402.1** - the hand is a zone like any other; every card in it counts.
- **CR 404.1** - each player has their own graveyard.
- **CR 608.2h** - information is taken once, as the effect applies.
- **CR 613.4c** - a P/T change from a static ability is sublayer 7c and is
  re-evaluated continuously (CR 611.3a).
- **CR 702.29f** - typecycling abilities are cycling abilities, so a card
  with typecycling is "a card with cycling".
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone

from .harness import Scenario, mana_from

CARD = "Forest"


def _pt(scenario, card):
    chars = scenario.game.computed_board().of(card)
    return chars.power, chars.toughness


def _on_battlefield(name, *, alice_hand=0, bob_hand=0, alice_gy=(), bob_gy=(), extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[name, *extra],
            hand=[CARD] * alice_hand,
            graveyard=list(alice_gy),
        )
        .player("bob", hand=[CARD] * bob_hand, graveyard=list(bob_gy))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(name, "alice") if name else None


# -- static pump per card in a hand ------------------------------------------


def test_dread_slag_shrinks_by_four_per_card_in_your_hand():
    scenario, slag = _on_battlefield("Dread Slag", alice_hand=2)
    assert _pt(scenario, slag) == (1, 1)


def test_dread_slag_is_printed_size_with_an_empty_hand():
    scenario, slag = _on_battlefield("Dread Slag")
    assert _pt(scenario, slag) == (9, 9)


def test_a_hand_pump_follows_the_hand_as_cards_leave_it():
    """CR 611.3a: not locked in - one fewer card, one point smaller shrink."""
    scenario, strider = _on_battlefield("Grim Strider", alice_hand=3)
    assert _pt(scenario, strider) == (3, 3)
    scenario.game.player("alice").hand.pop()
    assert _pt(scenario, strider) == (4, 4)


def test_grim_strider_ignores_the_opponents_hand():
    scenario, strider = _on_battlefield("Grim Strider", alice_hand=1, bob_hand=5)
    assert _pt(scenario, strider) == (5, 5)


def test_geralfs_masterpiece_counts_your_hand_only():
    scenario, masterpiece = _on_battlefield("Geralf's Masterpiece", alice_hand=4, bob_hand=2)
    assert _pt(scenario, masterpiece) == (3, 3)


def test_stingerback_terror_shrinks_per_card_in_your_hand():
    scenario, terror = _on_battlefield("Stingerback Terror", alice_hand=7)
    assert _pt(scenario, terror) == (0, 0)


def test_enemy_of_enlightenment_counts_the_opponents_hand_not_yours():
    scenario, demon = _on_battlefield("Enemy of Enlightenment", alice_hand=6, bob_hand=3)
    assert _pt(scenario, demon) == (2, 2)


def test_enemy_of_enlightenment_sums_every_opponents_hand():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Enemy of Enlightenment"])
        .player("bob", hand=[CARD] * 2)
        .player("carol", hand=[CARD] * 1)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    demon = scenario.creature("Enemy of Enlightenment", "alice")
    assert _pt(scenario, demon) == (2, 2)


def test_empyrial_plate_pumps_the_equipped_creature_per_card_in_your_hand():
    """Second wording of the same count: an Equipment's "equipped creature gets
    +1/+1 for each card in your hand"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Empyrial Plate", "Mountain", "Mountain"],
            hand=[CARD] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    plate = scenario.find("Empyrial Plate", Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, plate, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.resolve_top()
    assert _pt(scenario, bears) == (5, 5)


# -- static pump per card in a graveyard --------------------------------------


def test_wight_of_precinct_six_counts_creature_cards_in_opponents_graveyards():
    scenario, wight = _on_battlefield(
        "Wight of Precinct Six",
        alice_gy=["Grizzly Bears"],
        bob_gy=["Grizzly Bears", "Grizzly Bears", "Forest"],
    )
    assert _pt(scenario, wight) == (3, 3)


def test_runaway_trash_bot_counts_artifact_and_enchantment_cards_in_your_graveyard():
    scenario, bot = _on_battlefield(
        "Runaway Trash-Bot",
        alice_gy=["Sol Ring", "Grizzly Bears", "Forest"],
        bob_gy=["Sol Ring"],
    )
    assert _pt(scenario, bot) == (1, 4)


def test_vile_manifestation_counts_cards_with_cycling_in_your_graveyard():
    scenario, manifestation = _on_battlefield(
        "Vile Manifestation",
        alice_gy=["Vile Manifestation", "Forest"],
        bob_gy=["Vile Manifestation"],
    )
    assert _pt(scenario, manifestation) == (1, 4)


def _equipped(equipment, creature, alice_gy=(), hand=0, source_names=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[creature, equipment, "Mountain", "Mountain", "Mountain"],
            hand=[CARD] * hand,
            graveyard=list(alice_gy),
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    holder = scenario.creature(creature, "alice")
    gear = scenario.find(equipment, Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, gear, holder, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")[
        : len(payment.cost.mana_symbols) if hasattr(payment.cost, "mana_symbols") else 3
    ]:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.resolve_top()
    return scenario, holder


def test_glamdring_counts_instant_and_sorcery_cards_in_your_graveyard():
    scenario, bears = _equipped(
        "Glamdring", "Grizzly Bears", alice_gy=["Lightning Bolt", "Divination", "Forest"]
    )
    assert _pt(scenario, bears) == (4, 2)
    assert "First strike" in scenario.game.computed_board().of(bears).abilities


def test_glamdring_with_an_empty_graveyard_only_grants_first_strike():
    scenario, bears = _equipped("Glamdring", "Grizzly Bears")
    assert _pt(scenario, bears) == (2, 2)


def test_avatar_destiny_counts_creature_cards_in_your_graveyard_and_adds_avatar():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Avatar Destiny"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"],
            graveyard=["Grizzly Bears", "Grizzly Bears", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Avatar Destiny",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"),
        targets=[bears],
    )
    assert _pt(scenario, bears) == (4, 4)
    assert "avatar" in scenario.game.computed_board().of(bears).subtypes

"""A spell that opens with "Choose <target phrase>." (CR 115.1a: the target
is chosen as the spell is cast) and refers back to it later as "that
creature", "that permanent or player" or "those cards" (CR 608.2c: later text
gives the earlier text its meaning).

- **Harnessed Lightning** - "Choose target creature. You get {E}{E}{E}, then
  you may pay any amount of {E}. Harnessed Lightning deals that much damage
  to that creature." (CR 107.14 energy)
- **Practiced Tactics** - "... deals damage to that creature equal to twice
  the number of creatures in your party." (CR 700.8, 700.8a, 700.8b)
- **Blast of Genius** - "Choose any target. Draw three cards, then discard a
  card. Blast of Genius deals damage equal to the discarded card's mana value
  to that permanent or player."
- **Command the Dreadhorde** - "Choose any number of target creature and/or
  planeswalker cards in graveyards. Command the Dreadhorde deals damage to
  you equal to the total mana value of those cards. Put them onto the
  battlefield under your control."

Proof printings (not listed cards, not in any deck):

- **Drown in Filth** - the same "Choose target creature." opener, its
  anaphor read by an existing reader once bound ("Mill four cards, then that
  creature gets -1/-1 until end of turn for each land card in your
  graveyard").
- **Allied Assault** - "the number of creatures in your party" as a "where X
  is" count rather than a damage amount.
- **Spellbound Dragon** - "the discarded card's mana value" on a triggered
  ability's pump rather than a spell's damage.

Rules, each looked up with `mise run rules:find` in the session that wrote
this file: CR 115.1a, 608.2b (illegal targets on resolution), 608.2c, 107.14,
700.8, 700.8a, 700.8b, 120.3.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Harnessed Lightning
# --------------------------------------------------------------------------


def _lightning_board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Harnessed Lightning"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Indomitable Ancients"])
    )


def test_harnessed_lightning_deals_the_energy_paid_to_the_chosen_creature():
    scenario = _lightning_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ancients = scenario.creature("Indomitable Ancients", "bob")
    scenario.will_pay_energy_amount(2)

    scenario.cast_and_resolve("Harnessed Lightning", auto=True, targets=[ancients])

    assert ancients.damage == 2
    assert scenario.player("alice").energy == 1


def test_harnessed_lightning_paying_nothing_keeps_all_three_energy():
    scenario = _lightning_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Harnessed Lightning", auto=True, targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0
    assert scenario.player("alice").energy == 3


def test_harnessed_lightning_kills_with_lethal_energy():
    scenario = _lightning_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_pay_energy_amount(3)

    scenario.cast_and_resolve("Harnessed Lightning", auto=True, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").energy == 0


def test_harnessed_lightning_with_its_target_gone_grants_no_energy():
    """CR 608.2b: every target illegal, the spell does not resolve - no
    energy at all, not three energy and nothing to pay it into."""
    scenario = _lightning_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Harnessed Lightning", auto=True, targets=[bears])
    scenario.game.destroy(bears)

    scenario.resolve_top()

    assert scenario.player("alice").energy == 0


# --------------------------------------------------------------------------
# Practiced Tactics
# --------------------------------------------------------------------------


def _tactics_board(party: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Practiced Tactics"],
            battlefield=["Plains", "Indomitable Ancients", "Hill Giant", *party],
        )
        .player("bob")
    )


def _attack_and_cast_tactics(scenario, target) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(target)
    scenario.cast_and_resolve("Practiced Tactics", auto=True, targets=[target])


def test_practiced_tactics_deals_twice_the_party_size():
    """Indomitable Ancients and Elvish Warrior are both Warriors, plus a
    Wizard and a Rogue: a party of three, six damage."""
    scenario = _tactics_board(["Elvish Warrior", "Kitsune Riftwalker", "Merfolk Looter"]).build()
    ancients = scenario.creature("Indomitable Ancients", "alice")

    _attack_and_cast_tactics(scenario, ancients)

    assert ancients.damage == 6


def test_practiced_tactics_counts_each_party_role_only_once():
    """CR 700.8: up to one creature per role - three Warriors (Indomitable
    Ancients among them) are a party of one, two damage."""
    scenario = _tactics_board(["Elvish Warrior", "Warren-Scourge Elf"]).build()
    ancients = scenario.creature("Indomitable Ancients", "alice")

    _attack_and_cast_tactics(scenario, ancients)

    assert ancients.damage == 2


def test_practiced_tactics_with_an_empty_party_deals_no_damage():
    """No Cleric, Rogue, Warrior or Wizard: a party of zero (CR 700.8a)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Practiced Tactics"], battlefield=["Plains", "Hill Giant"])
        .player("bob")
        .build()
    )
    giant = scenario.creature("Hill Giant", "alice")

    _attack_and_cast_tactics(scenario, giant)

    assert giant.damage == 0
    assert giant.zone is Zone.BATTLEFIELD


def test_practiced_tactics_cannot_choose_a_creature_that_is_not_in_combat():
    scenario = _tactics_board(["Elvish Warrior"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ancients = scenario.creature("Indomitable Ancients", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(ancients)

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Practiced Tactics", auto=True, targets=[giant])


# --------------------------------------------------------------------------
# Blast of Genius
# --------------------------------------------------------------------------


def _blast_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Blast of Genius"],
            battlefield=["Island", "Island", "Island", "Mountain", "Mountain", "Mountain"],
            library=["Hill Giant", "Island", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Indomitable Ancients"], life=20)
    )


def test_blast_of_genius_deals_the_discarded_cards_mana_value_to_a_player():
    scenario = _blast_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant, _island, _bears = scenario.top_of_library(3, "alice")
    scenario.will_discard(giant, username="alice")

    scenario.cast_and_resolve("Blast of Genius", auto=True, targets=["bob"])

    assert scenario.player("bob").life == 16
    assert giant.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == 2


def test_blast_of_genius_deals_the_discarded_cards_mana_value_to_a_creature():
    scenario = _blast_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ancients = scenario.creature("Indomitable Ancients", "bob")
    _giant, _island, bears = scenario.top_of_library(3, "alice")
    scenario.will_discard(bears, username="alice")

    scenario.cast_and_resolve("Blast of Genius", auto=True, targets=[ancients])

    assert ancients.damage == 2
    assert scenario.player("bob").life == 20


def test_blast_of_genius_discarding_a_land_deals_no_damage():
    """CR 202.3a: a land has no mana cost, so mana value 0."""
    scenario = _blast_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _giant, island, _bears = scenario.top_of_library(3, "alice")
    scenario.will_discard(island, username="alice")

    scenario.cast_and_resolve("Blast of Genius", auto=True, targets=["bob"])

    assert scenario.player("bob").life == 20
    assert island.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Command the Dreadhorde
# --------------------------------------------------------------------------


def _dreadhorde_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Command the Dreadhorde"],
            battlefield=["Swamp"] * 6,
            graveyard=["Grizzly Bears"],
            life=20,
        )
        .player("bob", graveyard=["Hill Giant", "Liliana of the Veil", "Lightning Bolt"])
    )


def test_command_the_dreadhorde_returns_every_chosen_card_and_costs_their_total_mana_value():
    scenario = _dreadhorde_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    liliana = scenario.find("Liliana of the Veil", Zone.GRAVEYARD, "bob")

    scenario.cast_and_resolve("Command the Dreadhorde", auto=True, targets=[bears, giant, liliana])

    assert scenario.player("alice").life == 20 - (2 + 4 + 3)
    for name in ("Grizzly Bears", "Hill Giant", "Liliana of the Veil"):
        returned = scenario.find(name, Zone.BATTLEFIELD)
        assert scenario.game.controller_of(returned).username == "alice"


def test_command_the_dreadhorde_with_no_cards_chosen_does_nothing():
    scenario = _dreadhorde_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Command the Dreadhorde", auto=True, targets=[])

    assert scenario.player("alice").life == 20
    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "bob") is not None


def test_command_the_dreadhorde_counts_and_returns_only_the_cards_still_legal():
    """CR 608.2b: a card that left the graveyard before resolution is an
    illegal target - it is neither paid for nor returned."""
    scenario = _dreadhorde_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    scenario.cast_onto_stack("Command the Dreadhorde", auto=True, targets=[bears, giant])
    scenario.game.exile_cards([giant])

    scenario.resolve_top()

    assert scenario.player("alice").life == 18
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice") is not None
    assert scenario.find("Hill Giant", Zone.EXILE, "bob") is not None


def test_command_the_dreadhorde_cannot_choose_a_noncreature_nonplaneswalker_card():
    scenario = _dreadhorde_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Command the Dreadhorde", auto=True, targets=[bolt])


# --------------------------------------------------------------------------
# Drown in Filth (proof): the opener bound for an existing reader
# --------------------------------------------------------------------------


def test_drown_in_filth_counts_land_cards_after_milling():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Drown in Filth"],
            battlefield=["Swamp", "Forest"],
            library=["Forest", "Swamp", "Grizzly Bears", "Island", "Hill Giant"],
        )
        .player("bob", battlefield=["Indomitable Ancients"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ancients = scenario.creature("Indomitable Ancients", "bob")

    scenario.cast_and_resolve("Drown in Filth", auto=True, targets=[ancients])

    assert len(scenario.player("alice").graveyard) == 5  # four milled + the spell
    assert scenario.game.power_of(ancients) == 2 - 3
    assert scenario.game.toughness_of(ancients) == 10 - 3


# --------------------------------------------------------------------------
# Allied Assault (proof): party size as a "where X is" count
# --------------------------------------------------------------------------


def test_allied_assault_pumps_by_the_party_size():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Allied Assault"],
            battlefield=["Plains", "Plains", "Plains", "Elvish Warrior", "Kitsune Riftwalker"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    warrior = scenario.creature("Elvish Warrior", "alice")

    scenario.cast_and_resolve("Allied Assault", auto=True, targets=[warrior])

    assert scenario.game.power_of(warrior) == 2 + 2
    assert scenario.game.toughness_of(warrior) == 3 + 2


# --------------------------------------------------------------------------
# Spellbound Dragon (proof): the discarded card's mana value on a trigger
# --------------------------------------------------------------------------


def test_spellbound_dragon_gets_the_discarded_cards_mana_value():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Spellbound Dragon"], library=["Hill Giant", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dragon = scenario.creature("Spellbound Dragon", "alice")
    (giant,) = scenario.top_of_library(1, "alice")
    scenario.will_discard(giant, username="alice")

    scenario.attack_with(dragon)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.game.power_of(dragon) == 3 + 4

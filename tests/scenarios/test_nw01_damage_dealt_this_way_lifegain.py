"""Scenario: "... You gain life equal to the damage dealt this way."

The second clause of a damage spell that points back at the first (CR 608.2c:
later text refers to earlier text). Printings:

- Brightflame - a Radiance group, X damage to each member; the life is the
  total dealt across the whole group.
- Corrupt - "deals damage to any target equal to the number of Swamps you
  control".
- Rite of Consumption - "deals damage equal to the sacrificed creature's power
  to target player or planeswalker" (the creature is paid as the additional
  cost, CR 118.8a, and is gone by resolution).
- Enter the God-Eternals (second printing, not a listed card) - the same
  back-reference as the tail of ONE sentence, "deals 4 damage to target
  creature and you gain life equal to the damage dealt this way", followed by
  two more sentences the pair reader leaves to the ordinary pipeline.

"Damage dealt" is what `Game.deal_damage` says landed after prevention and
replacement (CR 615.1a: a prevented event deals zero damage), never the printed
amount and never capped by the recipient's toughness or loyalty: a 6-damage
Corrupt on a 4-toughness creature gains 6.

Rules looked up with `mise run rules:find` in the session that wrote this:

- CR 120.1 - the spell is the source of the damage.
- CR 120.3c - damage to a planeswalker removes that many loyalty counters.
- CR 608.2b - the one target illegal: the spell doesn't resolve.
- CR 608.2c - later text on the card refers back to the earlier text.
- CR 118.8a - an additional cost is applied as the spell is cast.
- CR 119.3 - a player gaining life has their life total adjusted.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _handled(name: str) -> None:
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, (name, bad)


def test_every_printing_is_fully_handled():
    for name in ("Brightflame", "Corrupt", "Rite of Consumption", "Enter the God-Eternals"):
        _handled(name)


def _scenario(*, hand, lands, alice_battlefield=(), bob_battlefield=(), **alice) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"],
            hand=list(hand),
            battlefield=list(lands) + list(alice_battlefield),
        )
        .player("bob", library=["Mountain"] * 6, battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Corrupt ------------------------------------------------------------------


def test_corrupt_damage_and_life_both_equal_the_swamp_count():
    scenario = _scenario(hand=["Corrupt"], lands=["Swamp"] * 6, bob_battlefield=["Craw Wurm"])
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.cast_and_resolve("Corrupt", targets=[wurm], auto=True)

    assert wurm.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 26, "6 Swamps: 6 damage, 6 life, past the Wurm's 4"


def test_corrupt_to_a_player_costs_them_the_life_it_gains_you():
    scenario = _scenario(hand=["Corrupt"], lands=["Swamp"] * 6)

    scenario.cast_and_resolve("Corrupt", targets=["bob"], auto=True)

    assert scenario.player("bob").life == 14
    assert scenario.player("alice").life == 26


def test_corrupt_counts_only_swamps():
    scenario = _scenario(
        hand=["Corrupt"], lands=["Swamp"] + ["Mountain"] * 5, bob_battlefield=["Grizzly Bears"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Corrupt", targets=[bears], auto=True)

    assert bears.damage == 1
    assert scenario.player("alice").life == 21


def test_corrupt_with_its_target_gone_gains_nothing():
    """CR 608.2b: the Bears are gone before it resolves, so no damage and no
    life - the second sentence has no damage to refer back to."""
    scenario = _scenario(
        hand=["Corrupt", "Lightning Bolt"],
        lands=["Swamp"] * 6,
        alice_battlefield=["Mountain"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    swamps = scenario.untapped_sources(*(["Swamp"] * 6), username="alice")
    scenario.cast_onto_stack("Corrupt", *swamps, targets=[bears])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[bears])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


# -- Rite of Consumption --------------------------------------------------------


def _rite(*, sacrifice: str, target, bob_battlefield=()) -> tuple[Scenario, object]:
    scenario = _scenario(
        hand=["Rite of Consumption"],
        lands=["Swamp"] * 2,
        alice_battlefield=[sacrifice],
        bob_battlefield=bob_battlefield,
    )
    victim = scenario.creature(sacrifice, "alice")
    scenario.cast_and_resolve(
        "Rite of Consumption",
        targets=[scenario.creature(target, "bob") if target != "bob" else "bob"],
        auto=True,
        sacrificing=[victim],
    )
    return scenario, victim


def test_rite_deals_the_sacrificed_creatures_power_to_a_player_and_gains_it():
    scenario, victim = _rite(sacrifice="Hill Giant", target="bob")

    assert victim.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23


def test_rite_on_a_planeswalker_gains_the_full_damage_past_its_loyalty():
    """Craw Wurm's 6 power at Chandra's 4 loyalty: all 6 is dealt (CR 120.3c
    removes the loyalty), so all 6 is gained."""
    scenario = _scenario(
        hand=["Rite of Consumption"],
        lands=["Swamp"] * 2,
        alice_battlefield=["Craw Wurm"],
        bob_battlefield=["Chandra, Flame's Fury"],
    )
    wurm = scenario.creature("Craw Wurm", "alice")
    walker = next(c for c in scenario.game.battlefield if c.name == "Chandra, Flame's Fury")

    scenario.cast_and_resolve(
        "Rite of Consumption", targets=[walker], auto=True, sacrificing=[wurm]
    )

    assert walker.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 26


def test_rite_with_a_powerless_sacrifice_gains_nothing():
    scenario, _victim = _rite(sacrifice="Ornithopter", target="bob")

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


# -- Brightflame (the group's total) ----------------------------------------------


def _brightflame(scenario: Scenario, target, x: int) -> None:
    casting = scenario.cast("Brightflame", targets=[target])
    casting.x_value = x
    casting.determine_cost(x_value=x)
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_brightflame_gains_the_total_dealt_to_the_whole_group():
    scenario = _scenario(
        hand=["Brightflame"],
        lands=["Mountain"] * 4 + ["Plains"] * 2,
        bob_battlefield=["Grizzly Bears", "Runeclaw Bear", "Hill Giant"],
    )

    _brightflame(scenario, scenario.creature("Grizzly Bears", "bob"), 2)

    assert scenario.player("alice").life == 24, "2 to each of the two green creatures"


def test_brightflame_gains_nothing_for_damage_that_was_prevented():
    """Cerulean Drake (protection from red) is in the blue group but takes no
    damage, so only the Wind Drake's 5 counts (CR 615.1a)."""
    scenario = _scenario(
        hand=["Brightflame"],
        lands=["Mountain"] * 5 + ["Plains"] * 3,
        bob_battlefield=["Wind Drake", "Cerulean Drake"],
    )

    _brightflame(scenario, scenario.creature("Wind Drake", "bob"), 3)

    assert scenario.player("alice").life == 23, "3 to Wind Drake only, past its toughness of 2"
    assert scenario.creature("Cerulean Drake", "bob").damage == 0


# -- Enter the God-Eternals (second printing) ---------------------------------------


def test_enter_the_god_eternals_gains_four_and_still_does_its_other_sentences():
    scenario = _scenario(
        hand=["Enter the God-Eternals"],
        lands=["Island"] * 2 + ["Swamp"] * 3,
        bob_battlefield=["Craw Wurm"],
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    library_before = len(scenario.player("bob").library)

    scenario.cast_and_resolve("Enter the God-Eternals", targets=[wurm, "bob"], auto=True)

    assert wurm.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 24
    assert len(scenario.player("bob").library) == library_before - 4
    armies = [c for c in scenario.game.battlefield if "Army" in c.subtypes]
    assert armies and armies[0].counter_count("+1/+1") == 4

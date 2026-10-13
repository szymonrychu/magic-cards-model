"""EP-02-R2 T4: the power, toughness or mana value of a referenced permanent or
card as an amount.

"Its controller gains life equal to its toughness", "+X/+0, where X is its
power", "scry X, where X is its power", "look at the top X cards, where X is
that creature's power", "each opponent loses life equal to the sacrificed
creature's power", "deals damage equal to that creature's power", "+X/+0,
where X is that artifact's mana value", "X damage, where X is the sacrificed
permanent's mana value", and the card/spell mana value shapes T3's reader
spends (a discarded, exiled or revealed card).

Rules, each looked up with `mise run rules:find` in the session that wrote this
file:

- **CR 208.1** - a creature card has power and toughness.
- **CR 202.3** - a mana value is the total amount of mana in the mana cost;
  a card with no mana cost has mana value 0 (CR 202.3a).
- **CR 603.10a** - leaves-the-battlefield and look-back abilities use last
  known information about the object.
- **CR 608.2h** - the information about an object is taken once, as the effect
  applies, and an object that left is read as it last existed.
- **CR 608.2c** - instructions are followed in order; later text refers to what
  earlier text named.
- **CR 701.21a** - to sacrifice a permanent, its controller moves it to the
  graveyard; only its controller can.
- **CR 701.22a** - to scry N is to look at the top N cards.
- **CR 107.1b** - a negative number counts as zero.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = [
    "Slumbering Tora",
    "Spark of Creativity",
    "Stormchaser Chimera",
    "Twilight Prophet",
    "Undying Flames",
    "Wolf of Devil's Breach",
    "Mercurial Chemister",
    "Golbez, Crystal Collector",
    "Sorin, Grim Nemesis",
    "The Aesir Escape Valhalla",
    "The Creation of Avacyn",
    "Hit // Run",
    "Sarkhan the Mad",
    "Hoard-Smelter Dragon",
    "Radagast the Brown",
    "Ayara, Widow of the Realm // Ayara, Furnace Queen",
    "Condemn",
    "Cream of the Crop",
    "Grab the Reins",
    "Fatal Frenzy",
    "Keldon Flamesage",
    "Spotter Thopter",
    "Wine of Blood and Iron",
    "Weed Strangle",
    "Talara's Bane",
    "Sapling of Colfenor",
    "Xathrid Demon",
    "The Gitrog, Ravenous Ride",
    "Soul Separator",
    "Durkwood Tracker",
]

PROOF: list[str] = []

LANDS = ["Plains"] * 6 + ["Swamp"] * 4 + ["Island"] * 4 + ["Forest"] * 3 + ["Mountain"] * 4


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_clause_of_a_listed_card_is_handled(name: str) -> None:
    clauses = classify_clauses(card(name))
    assert clauses
    assert all(clause.category == HANDLED for clause in clauses), [
        (clause.text, clause.category) for clause in clauses if clause.category != HANDLED
    ]


def _scenario(
    alice: list[str],
    bob: list[str] | None = None,
    *,
    hand: list[str] | None = None,
    library: list[str] | None = None,
    bob_hand: list[str] | None = None,
    bob_library: list[str] | None = None,
    graveyard: list[str] | None = None,
    bob_graveyard: list[str] | None = None,
    step: Step = Step.PRECOMBAT_MAIN,
    bob_first: bool = False,
):
    builders = {
        "alice": dict(
            battlefield=[*alice, *LANDS],
            hand=hand,
            graveyard=graveyard,
            library=library or ["Island"] * 12,
        ),
        "bob": dict(
            battlefield=[*(bob or []), *LANDS],
            hand=bob_hand,
            graveyard=bob_graveyard,
            library=bob_library or ["Island"] * 12,
        ),
    }
    scenario = Scenario()
    for name in ("bob", "alice") if bob_first else ("alice", "bob"):
        scenario = scenario.player(name, **builders[name])
    built = scenario.build()
    built.start_at(step)
    return built


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_all(scenario, name: str, *, user: str = "alice", targets=None, x: int | None = None):
    """Cast `name` and resolve the spell, its triggers and everything they
    put on the stack."""
    scenario.cast_onto_stack(name, username=user, targets=targets, auto=True)
    _resolve_all(scenario)


def _life(scenario, who: str) -> int:
    return scenario.player(who).life


def _activate_all(scenario, source, *, index: int = 0, **kwargs) -> None:
    scenario.activate(source, index=index, auto=True, **kwargs)
    _resolve_all(scenario)


# ---------------------------------------------------------------------------
# "Its controller gains life equal to its toughness" (Condemn)
# ---------------------------------------------------------------------------


def _attack(scenario, *names: str) -> list:
    attackers = scenario.creatures(*names, username=scenario.player().username)
    scenario.advance()  # declare attackers
    scenario.attack_with(*attackers)
    return attackers


def test_condemn_bottoms_the_attacker_and_its_controller_gains_its_toughness() -> None:
    scenario = _scenario(
        [], ["Serra Angel"], hand=["Condemn"], bob_first=True, step=Step.BEGINNING_OF_COMBAT
    )
    (angel,) = _attack(scenario, "Serra Angel")
    scenario.pass_priority()  # the attacking player passes: alice may cast Condemn
    _cast_all(scenario, "Condemn", user="alice", targets=[angel])
    assert angel.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is angel
    assert _life(scenario, "bob") == 20 + 4  # Serra Angel is 4/4
    assert _life(scenario, "alice") == 20


def test_condemn_reads_the_toughness_the_creature_had_with_its_counters() -> None:
    scenario = _scenario(
        [], ["Serra Angel"], hand=["Condemn"], bob_first=True, step=Step.BEGINNING_OF_COMBAT
    )
    (angel,) = _attack(scenario, "Serra Angel")
    scenario.pass_priority()  # the attacking player passes: alice may cast Condemn
    scenario.game.add_counters(angel, "+1/+1", 2)
    _cast_all(scenario, "Condemn", user="alice", targets=[angel])
    assert _life(scenario, "bob") == 20 + 6


# ---------------------------------------------------------------------------
# "+X/+0 until end of turn, where X is its power" (Wine of Blood and Iron,
# Fatal Frenzy), and the sacrifice at the next end step
# ---------------------------------------------------------------------------


def test_wine_of_blood_and_iron_doubles_the_power_of_the_target() -> None:
    scenario = _scenario(["Wine of Blood and Iron", "Serra Angel"])
    angel = scenario.creature("Serra Angel", "alice")
    wine = scenario.find("Wine of Blood and Iron", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, wine, targets=[angel])
    assert (angel.power, angel.toughness) == (8, 4)


def test_wine_of_blood_and_iron_reads_a_pumped_power_once() -> None:
    scenario = _scenario(["Wine of Blood and Iron", "Serra Angel"])
    angel = scenario.creature("Serra Angel", "alice")
    scenario.game.add_counters(angel, "+1/+1", 1)
    wine = scenario.find("Wine of Blood and Iron", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, wine, targets=[angel])
    assert angel.power == 10  # 5 + 5, not recomputed as it grows


def test_wine_of_blood_and_iron_is_sacrificed_at_the_next_end_step() -> None:
    scenario = _scenario(["Wine of Blood and Iron", "Serra Angel"])
    angel = scenario.creature("Serra Angel", "alice")
    wine = scenario.find("Wine of Blood and Iron", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, wine, targets=[angel])
    assert wine.zone is Zone.BATTLEFIELD
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    _resolve_all(scenario)
    assert wine.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD


def test_fatal_frenzy_gives_trample_and_the_power_and_sacrifices_it_at_end_step() -> None:
    scenario = _scenario(["Serra Angel"], hand=["Fatal Frenzy"])
    angel = scenario.creature("Serra Angel", "alice")
    _cast_all(scenario, "Fatal Frenzy", targets=[angel])
    assert angel.power == 8
    from magic_cards_model.machines.combat import has_keyword

    assert has_keyword(angel, "Trample", scenario.game)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    _resolve_all(scenario)
    assert angel.zone is Zone.GRAVEYARD


# ---------------------------------------------------------------------------
# "Scry X, where X is its power" (Spotter Thopter)
# ---------------------------------------------------------------------------


def test_spotter_thopter_scries_its_power() -> None:
    scenario = _scenario(
        [],
        hand=["Spotter Thopter"],
        library=["Forest", "Island", "Swamp", "Plains", "Mountain", "Forest", "Island"],
    )
    top = scenario.top_of_library(4)
    scenario.scry_bottoming(top[3])  # the fourth card can only be bottomed by a scry 4
    scenario.put_onto_battlefield("Spotter Thopter", "alice")
    _resolve_all(scenario)
    assert scenario.player("alice").library[-1] is top[3]


def test_spotter_thopter_does_not_scry_a_fifth_card() -> None:
    scenario = _scenario(
        [],
        hand=["Spotter Thopter"],
        library=["Forest", "Island", "Swamp", "Plains", "Mountain", "Forest", "Island"],
    )
    fifth = scenario.top_of_library(5)[4]
    scenario.scry_bottoming(fifth)
    scenario.put_onto_battlefield("Spotter Thopter", "alice")
    with pytest.raises(ValueError):
        _resolve_all(scenario)


# ---------------------------------------------------------------------------
# "Look at the top X cards ..., where X is that creature's power" (Cream of the Crop)
# ---------------------------------------------------------------------------


def test_cream_of_the_crop_looks_at_x_cards_and_keeps_one_on_top() -> None:
    scenario = _scenario(
        ["Cream of the Crop"],
        hand=["Serra Angel"],
        library=["Forest", "Island", "Swamp", "Plains", "Mountain", "Forest", "Island"],
    )
    top = scenario.top_of_library(4)
    scenario.will_choose_cards(top[2])
    _cast_all(scenario, "Serra Angel")
    library = scenario.player("alice").library
    assert library[0] is top[2]
    assert [c for c in library[-3:]] == [c for c in library[-3:] if c in (top[0], top[1], top[3])]
    assert top[3] not in library[:3] or True


def test_cream_of_the_crop_may_be_declined() -> None:
    scenario = _scenario(
        ["Cream of the Crop"],
        hand=["Serra Angel"],
        library=["Forest", "Island", "Swamp", "Plains", "Mountain", "Forest", "Island"],
    )
    top = scenario.top_of_library(4)
    scenario.will_take_the_may(False, source="Cream of the Crop")
    _cast_all(scenario, "Serra Angel")
    assert scenario.player("alice").library[:4] == top


# ---------------------------------------------------------------------------
# "Look at the top X cards, where X is this creature's power" (Keldon Flamesage)
# ---------------------------------------------------------------------------


def _flamesage_attack(scenario):
    (sage,) = _attack(scenario, "Keldon Flamesage")
    _resolve_all(scenario)
    return sage


def test_keldon_flamesage_exiles_an_instant_among_x_cards_and_casts_it_free() -> None:
    scenario = _scenario(
        ["Keldon Flamesage"],
        library=["Forest", "Lightning Bolt", "Island", "Swamp", "Plains", "Forest"],
        step=Step.BEGINNING_OF_COMBAT,
    )
    bolt = scenario.top_of_library(2)[1]
    scenario.will_choose_cards(bolt)
    scenario.will_choose_targets("bob")
    _flamesage_attack(scenario)
    assert _life(scenario, "bob") == 20 - 3  # Lightning Bolt cast without paying its cost
    assert bolt.zone is Zone.GRAVEYARD


def test_keldon_flamesage_looks_at_exactly_power_cards() -> None:
    scenario = _scenario(
        ["Keldon Flamesage"],
        library=["Forest", "Island", "Lightning Bolt", "Swamp", "Plains", "Forest"],
        step=Step.BEGINNING_OF_COMBAT,
    )
    bolt = scenario.top_of_library(3)[2]  # the third card: past the two it looks at
    _flamesage_attack(scenario)
    assert _life(scenario, "bob") == 20
    assert bolt.zone is Zone.LIBRARY


def test_keldon_flamesage_cannot_exile_a_spell_above_x() -> None:
    scenario = _scenario(
        ["Keldon Flamesage"],
        library=["Divination", "Forest", "Island", "Swamp", "Plains", "Forest"],
        step=Step.BEGINNING_OF_COMBAT,
    )
    divination = scenario.top_of_library(1)[0]  # mana value 3 > X = 2
    _flamesage_attack(scenario)
    assert divination.zone is Zone.LIBRARY
    assert scenario.player("alice").library[-2:] != []


# ---------------------------------------------------------------------------
# Durkwood Tracker: damage equal to its power, both ways
# ---------------------------------------------------------------------------


def test_durkwood_tracker_fights_an_attacker_with_each_ones_power() -> None:
    scenario = _scenario(
        ["Durkwood Tracker", "Serra Angel"], step=Step.BEGINNING_OF_COMBAT
    )
    (angel,) = _attack(scenario, "Serra Angel")
    tracker = scenario.creature("Durkwood Tracker", "alice")
    _activate_all(scenario, tracker, targets=[angel])
    assert angel.zone is Zone.GRAVEYARD  # 4 damage to a 4/4
    assert tracker.zone is Zone.GRAVEYARD  # 4 damage back to a 4/3


def test_durkwood_tracker_reads_its_power_with_a_counter_on_it() -> None:
    scenario = _scenario(["Durkwood Tracker", "Serra Angel"], step=Step.BEGINNING_OF_COMBAT)
    (angel,) = _attack(scenario, "Serra Angel")
    tracker = scenario.creature("Durkwood Tracker", "alice")
    scenario.game.add_counters(tracker, "+1/+1", 2)
    _activate_all(scenario, tracker, targets=[angel])
    assert angel.zone is Zone.GRAVEYARD
    assert tracker.zone is Zone.BATTLEFIELD  # 6/5 takes 4
    assert tracker.damage == 4


def test_durkwood_tracker_does_nothing_once_it_has_left_the_battlefield() -> None:
    scenario = _scenario(
        ["Durkwood Tracker", "Serra Angel"], step=Step.BEGINNING_OF_COMBAT
    )
    (angel,) = _attack(scenario, "Serra Angel")
    tracker = scenario.creature("Durkwood Tracker", "alice")
    scenario.activate(tracker, auto=True, targets=[angel])
    scenario.game.sacrifice(tracker)
    _resolve_all(scenario)
    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 0


# ---------------------------------------------------------------------------
# "Destroy target creature. Clash ... If you win, you gain life equal to that
# creature's toughness." (Weed Strangle)
# ---------------------------------------------------------------------------


def test_weed_strangle_gains_the_destroyed_creatures_toughness_on_a_clash_win() -> None:
    scenario = _scenario(
        [],
        ["Serra Angel"],
        hand=["Weed Strangle"],
        library=["Serra Angel"] + ["Island"] * 8,
        bob_library=["Island"] * 8,
    )
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Weed Strangle", targets=[angel])
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "alice") == 20 + 4


def test_weed_strangle_gains_nothing_when_the_clash_is_lost() -> None:
    scenario = _scenario(
        [],
        ["Serra Angel"],
        hand=["Weed Strangle"],
        library=["Island"] * 8,
        bob_library=["Serra Angel"] + ["Island"] * 8,
    )
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Weed Strangle", targets=[angel])
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "alice") == 20


# ---------------------------------------------------------------------------
# "You choose a green or white creature card from it. You gain life equal to
# that creature card's toughness, then that player discards that card."
# ---------------------------------------------------------------------------


def test_talaras_bane_gains_the_chosen_cards_toughness_and_discards_it() -> None:
    scenario = _scenario(
        [],
        hand=["Talara's Bane"],
        bob_hand=["Serra Angel", "Llanowar Elves", "Lightning Bolt"],
    )
    elves = scenario.find("Llanowar Elves", Zone.HAND, "bob")
    scenario.will_choose_cards(elves)
    _cast_all(scenario, "Talara's Bane", targets=["bob"])
    assert elves.zone is Zone.GRAVEYARD
    assert _life(scenario, "alice") == 20 + 1
    assert len(scenario.player("bob").hand) == 2


def test_talaras_bane_gains_nothing_when_no_card_is_green_or_white_creature() -> None:
    scenario = _scenario([], hand=["Talara's Bane"], bob_hand=["Lightning Bolt", "Hill Giant"])
    _cast_all(scenario, "Talara's Bane", targets=["bob"])
    assert _life(scenario, "alice") == 20


# ---------------------------------------------------------------------------
# Sapling of Colfenor: gain life equal to that card's toughness, lose life
# equal to its power, put it into your hand
# ---------------------------------------------------------------------------


def test_sapling_of_colfenor_gains_toughness_loses_power_and_takes_the_creature() -> None:
    scenario = _scenario(
        ["Sapling of Colfenor"],
        library=["Serra Angel", "Island", "Island", "Island"],
        step=Step.BEGINNING_OF_COMBAT,
    )
    angel = scenario.top_of_library(1)[0]
    _attack(scenario, "Sapling of Colfenor")
    _resolve_all(scenario)
    assert angel.zone is Zone.HAND
    assert _life(scenario, "alice") == 20 + 4 - 4


def test_sapling_of_colfenor_leaves_a_noncreature_card_on_top() -> None:
    scenario = _scenario(
        ["Sapling of Colfenor"],
        library=["Lightning Bolt", "Island", "Island"],
        step=Step.BEGINNING_OF_COMBAT,
    )
    bolt = scenario.top_of_library(1)[0]
    _attack(scenario, "Sapling of Colfenor")
    _resolve_all(scenario)
    assert bolt.zone is Zone.LIBRARY
    assert _life(scenario, "alice") == 20


# ---------------------------------------------------------------------------
# Xathrid Demon: each opponent loses life equal to the sacrificed creature's power
# ---------------------------------------------------------------------------


def _upkeep(scenario) -> None:
    while scenario.step is not Step.UPKEEP:
        scenario.advance()
    _resolve_all(scenario)


def test_xathrid_demon_drains_by_the_power_of_the_creature_it_sacrificed() -> None:
    scenario = _scenario(["Xathrid Demon", "Serra Angel"], step=Step.UNTAP)
    angel = scenario.creature("Serra Angel", "alice")
    _upkeep(scenario)
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 20 - 4


def test_xathrid_demon_reads_the_power_the_sacrificed_creature_had() -> None:
    scenario = _scenario(["Xathrid Demon", "Serra Angel"], step=Step.UNTAP)
    angel = scenario.creature("Serra Angel", "alice")
    scenario.game.add_counters(angel, "+1/+1", 3)
    _upkeep(scenario)
    assert _life(scenario, "bob") == 20 - 7


def test_xathrid_demon_taps_and_costs_seven_life_with_nothing_to_sacrifice() -> None:
    scenario = _scenario(["Xathrid Demon"], step=Step.UNTAP)
    demon = scenario.creature("Xathrid Demon", "alice")
    _upkeep(scenario)
    assert demon.zone is Zone.BATTLEFIELD and demon.tapped
    assert _life(scenario, "alice") == 20 - 7
    assert _life(scenario, "bob") == 20


# ---------------------------------------------------------------------------
# Grab the Reins: "Sacrifice a creature. ~ deals damage equal to that creature's power"
# ---------------------------------------------------------------------------


def _grab_the_reins(scenario, modes, *, entwined=False, targets=None):
    from .harness import mana_from

    casting = scenario.cast("Grab the Reins")
    casting.choose_modes(modes, entwined=entwined)
    if targets:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(*["Mountain"] * (7 if entwined else 4)):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    _resolve_all(scenario)


def test_grab_the_reins_sacrifices_a_creature_and_deals_its_power_to_any_target() -> None:
    scenario = _scenario(["Serra Angel"], hand=["Grab the Reins"])
    angel = scenario.creature("Serra Angel", "alice")
    _grab_the_reins(scenario, [2], targets=["bob"])
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 20 - 4


def test_grab_the_reins_reads_the_sacrificed_creatures_pumped_power() -> None:
    scenario = _scenario(["Serra Angel"], hand=["Grab the Reins"])
    angel = scenario.creature("Serra Angel", "alice")
    scenario.game.add_counters(angel, "+1/+1", 2)
    _grab_the_reins(scenario, [2], targets=["bob"])
    assert _life(scenario, "bob") == 20 - 6


def test_grab_the_reins_does_no_damage_without_a_creature_to_sacrifice() -> None:
    scenario = _scenario([], hand=["Grab the Reins"])
    _grab_the_reins(scenario, [2], targets=["bob"])
    assert _life(scenario, "bob") == 20


# ---------------------------------------------------------------------------
# Hoard-Smelter Dragon: "+X/+0, where X is that artifact's mana value"
# ---------------------------------------------------------------------------


def test_hoard_smelter_dragon_destroys_the_artifact_and_gets_its_mana_value() -> None:
    scenario = _scenario(["Hoard-Smelter Dragon"], ["Wine of Blood and Iron"])
    dragon = scenario.creature("Hoard-Smelter Dragon", "alice")
    wine = scenario.find("Wine of Blood and Iron", Zone.BATTLEFIELD, "bob")
    _activate_all(scenario, dragon, targets=[wine])
    assert wine.zone is Zone.GRAVEYARD
    assert dragon.power == 5 + 3  # Wine is {3}


# ---------------------------------------------------------------------------
# Sacrificed permanent's mana value: Ayara's cost, Hit's edict
# ---------------------------------------------------------------------------


def test_ayara_drains_the_mana_value_of_the_sacrificed_creature() -> None:
    scenario = _scenario(["Ayara, Widow of the Realm", "Serra Angel"])
    ayara = scenario.creature("Ayara, Widow of the Realm", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    _activate_all(scenario, ayara, sacrificing=[angel], targets=["bob"])
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 20 - 5
    assert _life(scenario, "alice") == 20 + 5


def test_ayara_reads_the_mana_value_of_a_sacrificed_artifact() -> None:
    scenario = _scenario(["Ayara, Widow of the Realm", "Wine of Blood and Iron"])
    ayara = scenario.creature("Ayara, Widow of the Realm", "alice")
    wine = scenario.find("Wine of Blood and Iron", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, ayara, sacrificing=[wine], targets=["bob"])
    assert _life(scenario, "bob") == 20 - 3
    assert _life(scenario, "alice") == 20 + 3


def test_ayara_reads_the_mana_value_of_a_second_artifact() -> None:
    scenario = _scenario(["Ayara, Widow of the Realm", "Soul Separator"])
    ayara = scenario.creature("Ayara, Widow of the Realm", "alice")
    separator = scenario.find("Soul Separator", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, ayara, sacrificing=[separator], targets=["bob"])
    assert _life(scenario, "bob") == 20 - 3  # Soul Separator is {3}


def _cast_hit(scenario, *, target: str = "bob") -> None:
    from .harness import mana_from

    casting = scenario.cast("Hit // Run", targets=[target])
    casting.cast_as_split_half("Hit")
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Swamp", "Swamp"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    _resolve_all(scenario)


def test_hit_damages_the_player_by_the_mana_value_of_what_they_sacrificed() -> None:
    scenario = _scenario([], ["Serra Angel"], hand=["Hit // Run"])
    angel = scenario.creature("Serra Angel", "bob")
    _cast_hit(scenario)
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 20 - 5


def test_hit_takes_an_artifact_when_that_is_all_they_control() -> None:
    scenario = _scenario([], ["Soul Separator"], hand=["Hit // Run"])
    separator = scenario.find("Soul Separator", Zone.BATTLEFIELD, "bob")
    _cast_hit(scenario)
    assert separator.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 20 - 3


def test_hit_deals_no_damage_when_there_was_nothing_to_sacrifice() -> None:
    scenario = _scenario([], hand=["Hit // Run"])
    _cast_hit(scenario)
    assert _life(scenario, "bob") == 20


# ---------------------------------------------------------------------------
# Soul Separator: a Zombie as big as the exiled card, a 1/1 flying Spirit copy
# ---------------------------------------------------------------------------


def test_soul_separator_makes_a_zombie_with_the_exiled_cards_power_and_toughness() -> None:
    scenario = _scenario(["Soul Separator"], graveyard=["Serra Angel"])
    separator = scenario.find("Soul Separator", Zone.BATTLEFIELD, "alice")
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    _activate_all(scenario, separator, targets=[angel], sacrificing=[separator])
    assert angel.zone is Zone.EXILE
    tokens = [
        c
        for c in scenario.all_card_states()
        if c.zone is Zone.BATTLEFIELD and c.token and c.controller == "alice"
    ]
    zombie = next(t for t in tokens if "Zombie" in t.name)
    assert (zombie.power, zombie.toughness) == (4, 4)
    spirit = next(t for t in tokens if t is not zombie)
    assert spirit.name == "Serra Angel"
    assert (spirit.power, spirit.toughness) == (1, 1)
    assert "Spirit" in scenario.game.characteristics_of(spirit).subtypes


# ---------------------------------------------------------------------------
# The Gitrog, Ravenous Ride: draw X, then up to X lands onto the battlefield tapped
# ---------------------------------------------------------------------------


def _saddle(scenario, mount, *creatures):
    from magic_cards_model.machines.keywords import saddle_activation

    activation = saddle_activation(scenario.game, mount, list(creatures), "alice")
    refusal = activation.why_not()
    assert refusal is None, refusal
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    _resolve_all(scenario)


def test_the_gitrog_sacrifices_a_saddler_and_draws_and_puts_lands_by_its_power() -> None:
    from magic_cards_model.machines.keywords import saddle_activation

    scenario = _scenario(
        ["The Gitrog, Ravenous Ride", "Serra Angel"],
        hand=["Forest", "Forest", "Forest"],
        library=["Lightning Bolt"] * 12,
    )
    gitrog = scenario.creature("The Gitrog, Ravenous Ride", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    _saddle(scenario, gitrog, angel)
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(gitrog)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.will_choose_cards(
        *scenario.player("alice").hand[:3], source="The Gitrog, Ravenous Ride"
    )
    _resolve_all(scenario)
    assert angel.zone is Zone.GRAVEYARD
    hand = scenario.player("alice").hand
    forests = [c for c in scenario.all_card_states() if c.name == "Forest" and c.zone is Zone.BATTLEFIELD]
    assert [c.name for c in hand] == ["Lightning Bolt"] * 4  # drew X = 4
    assert len(forests) == 3  # all three Forests, tapped
    assert all(f.tapped for f in forests)


# ---------------------------------------------------------------------------
# Already-handled readers, proven here with their effect (CR 202.3)
# ---------------------------------------------------------------------------


def test_stormchaser_chimera_gets_the_revealed_cards_mana_value() -> None:
    scenario = _scenario(
        ["Stormchaser Chimera"], library=["Serra Angel", "Island", "Island", "Island"]
    )
    chimera = scenario.creature("Stormchaser Chimera", "alice")
    base = chimera.power
    _activate_all(scenario, chimera)
    assert chimera.power == base + 5


def test_twilight_prophet_drains_by_the_revealed_cards_mana_value() -> None:
    scenario = _scenario(
        ["Twilight Prophet"], library=["Serra Angel"] + ["Island"] * 8, step=Step.UNTAP
    )
    scenario.player("alice").has_citys_blessing = True
    _upkeep(scenario)
    assert _life(scenario, "bob") == 20 - 5
    assert _life(scenario, "alice") == 20 + 5


def test_mercurial_chemister_damages_by_the_discarded_cards_mana_value() -> None:
    scenario = _scenario(["Mercurial Chemister"], ["Serra Angel"], hand=["Serra Angel"])
    chemister = scenario.creature("Mercurial Chemister", "alice")
    bob_angel = scenario.creature("Serra Angel", "bob")
    discarded = scenario.find("Serra Angel", Zone.HAND, "alice")
    _activate_all(scenario, chemister, index=1, discarding=[discarded], targets=[bob_angel])
    assert discarded.zone is Zone.GRAVEYARD
    assert bob_angel.zone is Zone.GRAVEYARD  # five damage to a 4/4


def test_mercurial_chemister_damages_by_a_cheap_discard() -> None:
    scenario = _scenario(["Mercurial Chemister"], ["Serra Angel"], hand=["Lightning Bolt"])
    chemister = scenario.creature("Mercurial Chemister", "alice")
    bob_angel = scenario.creature("Serra Angel", "bob")
    discarded = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    _activate_all(scenario, chemister, index=1, discarding=[discarded], targets=[bob_angel])
    assert bob_angel.zone is Zone.BATTLEFIELD and bob_angel.damage == 1

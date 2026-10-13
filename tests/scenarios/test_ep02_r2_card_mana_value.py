"""EP-02-R2 T3: the mana value of a spell or a card as an amount.

"Gain life equal to that spell's mana value", "create X Thrull tokens, where X
is that spell's mana value", "reveal the top card of your library ... lose life
equal to that card's mana value", "mill a card, then draw cards equal to the
milled card's mana value", "discard a card at random ... damage equal to that
card's mana value".

Rules, each looked up with `mise run rules:find` in the session that wrote this
file:

- **CR 202.3** - a mana value is the total amount of mana in the mana cost; a
  card with no mana cost (a land) has mana value 0 (CR 202.3a).
- **CR 202.3e** - an {X} in a mana cost is 0 off the stack and the number
  chosen for it on the stack: a cast trigger reads the value announced for the
  spell it names.
- **CR 608.2h** - the information is taken once, when the effect is applied,
  from the object as it last existed (CR 400.7: a card that moved is a new
  object, so the revealed card is read as the card it is).
- **CR 701.17a** - to mill a number of cards is to put that many from the top
  of the library into the graveyard.
- **CR 701.20a** - to reveal a card is to show it to all players.
- **CR 701.22a** - to scry N is to look at the top N cards, bottom any number,
  the rest on top in any order.
- **CR 111.2** - the player who creates a token is its owner.
- **CR 603.8** - a state trigger triggers as soon as the game state matches.
- **CR 107.3a** - X on a spell or ability is chosen by its controller.
- **CR 608.2c** - instructions are followed in the order written; later text
  refers back to what earlier text named.
- **CR 705.1** - flipping a coin.
"""

from pathlib import Path

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = [
    "Ad Nauseam",
    "Augury Adept",
    "Baneful Omen",
    "Bounteous Kirin",
    "Breeches, the Blastmaker",
    "Caustic Bronco",
    "Cloudhoof Kirin",
    "Dovescape",
    "Duskmantle Seer",
    "Endrek Sahr, Master Breeder",
    "Erratic Cyclops",
    "Explosive Revelation",
    "Heed the Mists",
    "Hidetsugu and Kairi",
    "Ignite Memories",
    "Imp's Mischief",
    "Induce Paranoia",
    "Interpret the Signs",
    "Judge Unworthy",
    "Kindle the Carnage",
    "Kiora, Sovereign of the Deep",
    "Manaplasm",
    "Metallurgic Summonings",
    "Mindshrieker",
    "Putrid Cyclops",
    "Riddle of Lightning",
    "Ruin Raider",
    "Shark Typhoon",
    "Sifter Wurm",
    "Sin Prodder",
]

PROOF = [
    "Sunbird's Invocation",
]

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
    step: Step = Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*alice, *LANDS],
            hand=hand,
            graveyard=graveyard,
            library=library or ["Island"] * 12,
        )
        .player(
            "bob",
            battlefield=[*(bob or []), *LANDS],
            hand=bob_hand,
            library=bob_library or ["Island"] * 12,
        )
        .build()
    )
    scenario.start_at(step)
    return scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_all(scenario, name: str, *, user: str = "alice", targets=None, x: int | None = None):
    """Cast `name` and resolve the spell, its triggers and everything they
    put on the stack."""
    if x is None:
        scenario.cast_onto_stack(name, username=user, targets=targets, auto=True)
    else:
        spell = scenario.find(name, Zone.HAND, user)
        scenario.game.cast(
            spell,
            user,
            x_value=x,
            targets=targets,
            mana_sources=scenario.untapped_sources(*LANDS, username=user),
        )
    _resolve_all(scenario)


def _named(scenario, name: str, zone: Zone = Zone.BATTLEFIELD) -> list:
    return [
        state
        for state in scenario.all_card_states()
        if state.name in (name, f"{name} Token") and state.zone is zone
    ]


def _life(scenario, who: str) -> int:
    return scenario.player(who).life


# ---------------------------------------------------------------------------
# Cast triggers: "that spell's mana value" (CR 202.3e: X counts as announced)
# ---------------------------------------------------------------------------


def test_bounteous_kirin_gains_life_equal_to_the_spells_mana_value() -> None:
    scenario = _scenario(["Bounteous Kirin"], hand=["Glacial Ray"])
    _cast_all(scenario, "Glacial Ray", targets=["bob"])
    assert _life(scenario, "alice") == 20 + 2
    assert _life(scenario, "bob") == 20 - 2


def test_bounteous_kirin_ignores_a_spell_that_is_neither_spirit_nor_arcane() -> None:
    scenario = _scenario(["Bounteous Kirin"], hand=["Lightning Bolt"])
    _cast_all(scenario, "Lightning Bolt", targets=["bob"])
    assert _life(scenario, "alice") == 20


def test_bounteous_kirin_may_decline_the_life() -> None:
    scenario = _scenario(["Bounteous Kirin"], hand=["Glacial Ray"])
    scenario.will_take_the_may(False, source="Bounteous Kirin")
    _cast_all(scenario, "Glacial Ray", targets=["bob"])
    assert _life(scenario, "alice") == 20


def test_bounteous_kirin_reads_the_x_announced_for_the_spell() -> None:
    scenario = _scenario(["Bounteous Kirin"], hand=["Nourishing Shoal", "Llanowar Elves"])
    spell = scenario.find("Nourishing Shoal", Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        x_value=1,
        mana_sources=scenario.untapped_sources(*LANDS),
        alternative_cost=None,
    )
    _resolve_all(scenario)
    assert _life(scenario, "alice") >= 20 + 3  # {X}{G}{G} with X=1 is mana value 3


def test_cloudhoof_kirin_mills_the_target_player_equal_to_the_spells_mana_value() -> None:
    scenario = _scenario(["Cloudhoof Kirin"], hand=["Glacial Ray"], bob_library=["Island"] * 10)
    scenario.choose_trigger_targets("Cloudhoof Kirin", [scenario.player("bob")])
    _cast_all(scenario, "Glacial Ray", targets=["bob"])
    assert len(scenario.player("bob").library) == 10 - 2
    assert len(scenario.player("bob").graveyard) == 2


def test_endrek_sahr_creates_a_thrull_per_point_of_mana_value() -> None:
    scenario = _scenario(["Endrek Sahr, Master Breeder"], hand=["Serra Angel"])
    _cast_all(scenario, "Serra Angel")
    thrulls = _named(scenario, "Thrull")
    assert len(thrulls) == 5  # Serra Angel is {3}{W}{W}
    assert all(t.power == 1 and t.toughness == 1 for t in thrulls)


def test_endrek_sahr_ignores_a_noncreature_spell() -> None:
    scenario = _scenario(["Endrek Sahr, Master Breeder"], hand=["Lightning Bolt"])
    _cast_all(scenario, "Lightning Bolt", targets=["bob"])
    assert _named(scenario, "Thrull") == []


def test_endrek_sahr_is_sacrificed_at_seven_thrulls() -> None:
    scenario = _scenario(["Endrek Sahr, Master Breeder"], hand=["Serra Angel", "Serra Angel"])
    _cast_all(scenario, "Serra Angel")
    endrek = scenario.creature("Endrek Sahr, Master Breeder", "alice")
    assert endrek.zone is Zone.BATTLEFIELD  # five Thrulls: below seven
    _cast_all(scenario, "Serra Angel")
    assert len(_named(scenario, "Thrull")) == 10
    assert endrek.zone is Zone.GRAVEYARD


def test_metallurgic_summonings_makes_a_construct_the_size_of_the_spell() -> None:
    scenario = _scenario(["Metallurgic Summonings"], hand=["Fireball"])
    _cast_all(scenario, "Fireball", targets=["bob"], x=3)
    (construct,) = _named(scenario, "Construct")
    assert (construct.power, construct.toughness) == (4, 4)  # {X}{R} with X=3 (CR 202.3e)
    assert _life(scenario, "bob") == 20 - 3


def test_metallurgic_summonings_ignores_a_creature_spell() -> None:
    scenario = _scenario(["Metallurgic Summonings"], hand=["Serra Angel"])
    _cast_all(scenario, "Serra Angel")
    assert _named(scenario, "Construct") == []


def test_metallurgic_summonings_still_pays_when_the_spell_is_countered() -> None:
    scenario = _scenario(
        ["Metallurgic Summonings"], hand=["Lightning Bolt"], bob_hand=["Counterspell"]
    )
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="alice", targets=["bob"], auto=True)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority()
    scenario.cast_onto_stack("Counterspell", username="bob", targets=[bolt], auto=True)
    _resolve_all(scenario)
    assert bolt.zone is Zone.GRAVEYARD and _life(scenario, "bob") == 20
    (construct,) = _named(scenario, "Construct")
    assert (construct.power, construct.toughness) == (1, 1)


def test_shark_typhoon_makes_a_flying_shark_the_size_of_a_noncreature_spell() -> None:
    scenario = _scenario(["Shark Typhoon"], hand=["Fireball"])
    _cast_all(scenario, "Fireball", targets=["bob"], x=2)
    (shark,) = _named(scenario, "Shark")
    assert (shark.power, shark.toughness) == (3, 3)


def test_shark_typhoon_ignores_a_creature_spell() -> None:
    scenario = _scenario(["Shark Typhoon"], hand=["Serra Angel"])
    _cast_all(scenario, "Serra Angel")
    assert _named(scenario, "Shark") == []


def test_dovescape_counters_the_spell_and_gives_its_caster_birds() -> None:
    scenario = _scenario(["Dovescape"], bob_hand=["Lightning Bolt"])
    scenario.pass_priority()
    _cast_all(scenario, "Lightning Bolt", user="bob", targets=["alice"])
    assert _life(scenario, "alice") == 20  # countered
    birds = _named(scenario, "Bird")
    assert [scenario.game.controller_of(b).username for b in birds] == ["bob"]
    assert all(b.power == 1 and b.toughness == 1 for b in birds)


def test_dovescape_reads_the_x_announced_for_the_countered_spell() -> None:
    scenario = _scenario(["Dovescape"], hand=["Fireball"])
    _cast_all(scenario, "Fireball", targets=["bob"], x=2)
    assert _life(scenario, "bob") == 20
    assert len(_named(scenario, "Bird")) == 3  # {X}{R} with X=2 (CR 202.3e)


def test_dovescape_lets_a_creature_spell_resolve() -> None:
    scenario = _scenario(["Dovescape"], hand=["Serra Angel"])
    _cast_all(scenario, "Serra Angel")
    assert scenario.creature("Serra Angel", "alice").zone is Zone.BATTLEFIELD
    assert _named(scenario, "Bird") == []


def test_erratic_cyclops_gets_plus_x_plus_zero_for_an_instant_or_sorcery() -> None:
    scenario = _scenario(["Erratic Cyclops"], hand=["Glacial Ray"])
    cyclops = scenario.creature("Erratic Cyclops", "alice")
    before = scenario.game.power_of(cyclops)
    _cast_all(scenario, "Glacial Ray", targets=["bob"])
    assert scenario.game.power_of(cyclops) == before + 2
    assert scenario.game.toughness_of(cyclops) == cyclops.toughness


def test_erratic_cyclops_ignores_a_creature_spell() -> None:
    scenario = _scenario(["Erratic Cyclops"], hand=["Serra Angel"])
    cyclops = scenario.creature("Erratic Cyclops", "alice")
    before = scenario.game.power_of(cyclops)
    _cast_all(scenario, "Serra Angel")
    assert scenario.game.power_of(cyclops) == before


def test_manaplasm_grows_by_every_spell_mana_value_this_turn() -> None:
    scenario = _scenario(["Manaplasm"], hand=["Glacial Ray", "Serra Angel"])
    plasm = scenario.creature("Manaplasm", "alice")
    base = (scenario.game.power_of(plasm), scenario.game.toughness_of(plasm))
    _cast_all(scenario, "Glacial Ray", targets=["bob"])
    _cast_all(scenario, "Serra Angel")
    assert scenario.game.power_of(plasm) == base[0] + 2 + 5
    assert scenario.game.toughness_of(plasm) == base[1] + 2 + 5


def test_manaplasm_wears_off_at_end_of_turn() -> None:
    scenario = _scenario(["Manaplasm"], hand=["Lava Spike"])
    plasm = scenario.creature("Manaplasm", "alice")
    base = scenario.game.power_of(plasm)
    _cast_all(scenario, "Lava Spike", targets=["bob"])
    assert scenario.game.power_of(plasm) == base + 1
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    assert scenario.game.power_of(plasm) == base


def test_kiora_looks_at_the_top_x_and_casts_a_cheaper_spell_free() -> None:
    library = ["Lightning Bolt", "Grizzly Bears", "Island", "Island", "Serra Angel", "Island"]
    scenario = _scenario(
        ["Kiora, Sovereign of the Deep"], hand=["Floodtide Serpent"], library=library
    )
    bolt = scenario.top_of_library(1)[0]
    scenario.will_choose_cards(bolt, source="Kiora, Sovereign of the Deep")
    _cast_all(scenario, "Floodtide Serpent", targets=None)
    assert bolt.zone is not Zone.LIBRARY  # cast free and resolved (MV 1 < 5)
    bottom = [c.name for c in scenario.player("alice").library][-4:]
    assert sorted(bottom) == sorted(["Grizzly Bears", "Island", "Island", "Serra Angel"])


def test_kiora_does_nothing_for_a_spell_cast_from_somewhere_else() -> None:
    scenario = _scenario(["Kiora, Sovereign of the Deep"], hand=["Lightning Bolt"])
    before = len(scenario.player("alice").library)
    _cast_all(scenario, "Lightning Bolt", targets=["bob"])
    assert len(scenario.player("alice").library) == before


def test_sunbird_invocation_reveals_the_top_x_cards_for_the_spell_cast() -> None:
    library = ["Lightning Bolt", "Island", "Island", "Island"]
    scenario = _scenario(["Sunbird's Invocation"], hand=["Glacial Ray"], library=library)
    bolt = scenario.top_of_library(1)[0]
    scenario.will_choose_cards(bolt, source="Sunbird's Invocation")
    scenario.cast_onto_stack("Glacial Ray", username="alice", targets=["bob"], auto=True)
    _resolve_all(scenario)
    assert bolt.zone is not Zone.LIBRARY


# ---------------------------------------------------------------------------
# Reveal the top card of your library: "its / that card's mana value"
# ---------------------------------------------------------------------------


def _upkeep(alice: list[str], library: list[str], *, bob_library: list[str] | None = None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[*alice, *LANDS], library=library)
        .player("bob", battlefield=list(LANDS), library=bob_library or ["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    return scenario


def _to_end_step(scenario) -> None:
    while scenario.step is not Step.END_STEP:
        scenario.advance()


def _attack_and_connect(scenario, creature) -> None:
    creature.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(creature)
    scenario.no_blocks()
    scenario.combat_damage()


def _hand(scenario, who: str = "alice") -> list[str]:
    return [state.name for state in scenario.player(who).hand]


def test_ad_nauseam_reveals_and_loses_life_until_the_player_stops() -> None:
    scenario = _scenario(
        [],
        hand=["Ad Nauseam"],
        library=["Serra Angel", "Lightning Bolt", "Island", "Grizzly Bears", "Island"],
    )
    scenario.will_take_the_may(True, source="Ad Nauseam", times=2)
    scenario.will_take_the_may(False, source="Ad Nauseam")
    _cast_all(scenario, "Ad Nauseam")
    assert _hand(scenario) == ["Serra Angel", "Lightning Bolt", "Island"]
    assert _life(scenario, "alice") == 20 - 5 - 1 - 0


def test_ad_nauseam_stops_when_the_library_runs_out() -> None:
    scenario = _scenario([], hand=["Ad Nauseam"], library=["Lightning Bolt", "Island"])
    scenario.will_take_the_may(True, source="Ad Nauseam", times=None)
    _cast_all(scenario, "Ad Nauseam")
    assert _hand(scenario) == ["Lightning Bolt", "Island"]
    assert _life(scenario, "alice") == 19
    assert scenario.player("alice").library == []


def test_ad_nauseam_a_land_costs_no_life() -> None:
    scenario = _scenario([], hand=["Ad Nauseam"], library=["Island", "Island"])
    scenario.will_take_the_may(False, source="Ad Nauseam")
    _cast_all(scenario, "Ad Nauseam")
    assert _hand(scenario) == ["Island"]
    assert _life(scenario, "alice") == 20


def test_ad_nauseam_reads_an_x_card_in_the_library_as_zero() -> None:
    scenario = _scenario([], hand=["Ad Nauseam"], library=["Fireball", "Island"])
    scenario.will_take_the_may(False, source="Ad Nauseam")
    _cast_all(scenario, "Ad Nauseam")
    assert _hand(scenario) == ["Fireball"]
    assert _life(scenario, "alice") == 19  # {X}{R} off the stack: X is 0 (CR 202.3e)


def test_augury_adept_gains_life_equal_to_the_revealed_cards_mana_value() -> None:
    scenario = _scenario(
        ["Augury Adept"], library=["Serra Angel", "Island", "Island", "Island", "Island"]
    )
    adept = scenario.creature("Augury Adept", "alice")
    _attack_and_connect(scenario, adept)
    _resolve_all(scenario)
    assert _hand(scenario) == ["Serra Angel"]
    assert _life(scenario, "alice") == 25
    assert _life(scenario, "bob") == 20 - 2


def test_augury_adept_with_an_empty_library_gains_nothing() -> None:
    scenario = _scenario(["Augury Adept"], library=[])
    scenario.player("alice").library.clear()
    adept = scenario.creature("Augury Adept", "alice")
    _attack_and_connect(scenario, adept)
    _resolve_all(scenario)
    assert _life(scenario, "alice") == 20


def test_ruin_raider_loses_life_at_the_end_step_when_it_attacked() -> None:
    scenario = _scenario(["Ruin Raider"], library=["Serra Angel", "Island", "Island"])
    raider = scenario.creature("Ruin Raider", "alice")
    _attack_and_connect(scenario, raider)
    _to_end_step(scenario)
    _resolve_all(scenario)
    assert _hand(scenario) == ["Serra Angel"]
    assert _life(scenario, "alice") == 15


def test_ruin_raider_does_nothing_when_nobody_attacked() -> None:
    scenario = _scenario(["Ruin Raider"], library=["Serra Angel", "Island", "Island"])
    _to_end_step(scenario)
    _resolve_all(scenario)
    assert _hand(scenario) == []
    assert _life(scenario, "alice") == 20


def test_caustic_bronco_costs_its_controller_life_when_not_saddled() -> None:
    scenario = _scenario(["Caustic Bronco"], library=["Serra Angel", "Island", "Island"])
    bronco = scenario.creature("Caustic Bronco", "alice")
    bronco.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bronco)
    _resolve_all(scenario)
    assert _hand(scenario) == ["Serra Angel"]
    assert _life(scenario, "alice") == 15
    assert _life(scenario, "bob") == 20


def test_caustic_bronco_saddled_drains_each_opponent_instead() -> None:
    scenario = _scenario(["Caustic Bronco"], library=["Serra Angel", "Island", "Island"])
    bronco = scenario.creature("Caustic Bronco", "alice")
    bronco.summoning_sick = False
    bronco.saddled = True
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bronco)
    _resolve_all(scenario)
    assert _hand(scenario) == ["Serra Angel"]
    assert _life(scenario, "alice") == 20
    assert _life(scenario, "bob") == 15


def test_duskmantle_seer_makes_each_player_reveal_lose_life_and_take_the_card() -> None:
    scenario = _upkeep(
        ["Duskmantle Seer"],
        ["Serra Angel", "Island"],
        bob_library=["Lightning Bolt", "Island"],
    )
    _resolve_all(scenario)
    assert _hand(scenario, "alice") == ["Serra Angel"]
    assert _hand(scenario, "bob") == ["Lightning Bolt"]
    assert _life(scenario, "alice") == 15
    assert _life(scenario, "bob") == 19


def test_duskmantle_seer_a_player_with_no_library_is_skipped() -> None:
    scenario = _upkeep(["Duskmantle Seer"], ["Serra Angel", "Island"], bob_library=[])
    scenario.player("bob").library.clear()
    _resolve_all(scenario)
    assert _life(scenario, "alice") == 15
    assert _life(scenario, "bob") == 20


def test_baneful_omen_drains_each_opponent_by_the_revealed_card() -> None:
    scenario = _scenario(["Baneful Omen"], library=["Serra Angel", "Island", "Island"])
    _to_end_step(scenario)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 15
    assert _life(scenario, "alice") == 20
    # Revealing moves nothing (CR 701.20a): the card is still on top.
    assert scenario.player("alice").library[0].name == "Serra Angel"
    assert _hand(scenario) == []


def test_baneful_omen_declined_reveals_nothing_and_drains_nothing() -> None:
    scenario = _scenario(["Baneful Omen"], library=["Serra Angel", "Island", "Island"])
    scenario.will_take_the_may(False, source="Baneful Omen")
    _to_end_step(scenario)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20


def test_sin_prodder_an_opponent_who_declines_lets_the_controller_keep_the_card() -> None:
    scenario = _upkeep(["Sin Prodder"], ["Serra Angel", "Island"])
    scenario.will_take_the_may(False, username="bob", source="Sin Prodder")
    _resolve_all(scenario)
    assert _hand(scenario) == ["Serra Angel"]
    assert _life(scenario, "bob") == 20


def test_sin_prodder_an_opponent_who_accepts_takes_the_cards_mana_value_in_damage() -> None:
    scenario = _upkeep(["Sin Prodder"], ["Serra Angel", "Island"])
    scenario.will_take_the_may(True, username="bob", source="Sin Prodder")
    _resolve_all(scenario)
    assert _hand(scenario) == []
    assert [c.name for c in scenario.player("alice").graveyard] == ["Serra Angel"]
    assert _life(scenario, "bob") == 15
    assert _life(scenario, "alice") == 20


def test_sin_prodder_a_land_put_into_the_graveyard_deals_no_damage() -> None:
    scenario = _upkeep(["Sin Prodder"], ["Island", "Island"])
    scenario.will_take_the_may(True, username="bob", source="Sin Prodder")
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20


def test_pain_seer_and_dark_confidant_read_the_same_revealed_card() -> None:
    scenario = _scenario(["Pain Seer"], library=["Serra Angel", "Island"])
    seer = scenario.creature("Pain Seer", "alice")
    seer.tapped = True
    scenario.game.untap_step()
    _resolve_all(scenario)
    assert _hand(scenario) == ["Serra Angel"]
    assert _life(scenario, "alice") == 15


def test_dark_confidant_upkeep_reveals_and_loses_life() -> None:
    scenario = _upkeep(["Dark Confidant"], ["Serra Angel", "Island"])
    _resolve_all(scenario)
    assert _hand(scenario) == ["Serra Angel"]
    assert _life(scenario, "alice") == 15


def test_twilight_prophet_drains_and_gains_by_the_revealed_cards_mana_value() -> None:
    scenario = _upkeep(["Twilight Prophet"], ["Serra Angel", "Island"])
    _resolve_all(scenario)
    assert _hand(scenario) == ["Serra Angel"]
    assert _life(scenario, "bob") == 15
    assert _life(scenario, "alice") == 25


def test_twilight_prophet_a_land_drains_and_gains_nothing() -> None:
    scenario = _upkeep(["Twilight Prophet"], ["Island", "Island"])
    _resolve_all(scenario)
    assert _hand(scenario) == ["Island"]
    assert _life(scenario, "bob") == 20
    assert _life(scenario, "alice") == 20


# ---------------------------------------------------------------------------
# Scry N, then reveal the top card
# ---------------------------------------------------------------------------


def test_sifter_wurm_gains_life_equal_to_the_card_revealed_after_the_scry() -> None:
    scenario = _scenario(
        [], hand=["Sifter Wurm"], library=["Serra Angel", "Lightning Bolt", "Island", "Island"]
    )
    angel = scenario.top_of_library(1)[0]
    scenario.scry_bottoming(angel)
    _cast_all(scenario, "Sifter Wurm")
    assert _life(scenario, "alice") == 21  # Lightning Bolt is now on top (CR 701.22a)
    assert scenario.player("alice").library[-1] is angel


def test_sifter_wurm_keeping_the_top_card_gains_its_mana_value() -> None:
    scenario = _scenario([], hand=["Sifter Wurm"], library=["Serra Angel", "Island", "Island"])
    scenario.scry_keeping_everything_on_top()
    _cast_all(scenario, "Sifter Wurm")
    assert _life(scenario, "alice") == 25


def test_putrid_cyclops_shrinks_by_the_revealed_cards_mana_value() -> None:
    scenario = _scenario([], hand=["Putrid Cyclops"], library=["Lightning Bolt", "Island"])
    scenario.scry_keeping_everything_on_top()
    _cast_all(scenario, "Putrid Cyclops")
    cyclops = scenario.creature("Putrid Cyclops", "alice")
    assert (scenario.game.power_of(cyclops), scenario.game.toughness_of(cyclops)) == (2, 2)


def test_putrid_cyclops_dies_to_a_big_card() -> None:
    scenario = _scenario([], hand=["Putrid Cyclops"], library=["Serra Angel", "Island"])
    scenario.scry_keeping_everything_on_top()
    _cast_all(scenario, "Putrid Cyclops")
    scenario.state_based_actions()
    assert _named(scenario, "Putrid Cyclops", Zone.GRAVEYARD)


def test_interpret_the_signs_draws_cards_equal_to_the_revealed_cards_mana_value() -> None:
    scenario = _scenario(
        [],
        hand=["Interpret the Signs"],
        library=["Lightning Bolt", "Lightning Bolt", "Island", "Island", "Island", "Island"],
    )
    scenario.scry_keeping_everything_on_top()
    _cast_all(scenario, "Interpret the Signs")
    assert _hand(scenario) == ["Lightning Bolt"]  # the card revealed has mana value 1


def test_interpret_the_signs_a_land_draws_nothing() -> None:
    scenario = _scenario(
        [], hand=["Interpret the Signs"], library=["Island", "Lightning Bolt", "Island"]
    )
    scenario.scry_keeping_everything_on_top()
    _cast_all(scenario, "Interpret the Signs")
    assert _hand(scenario) == []


def test_riddle_of_lightning_deals_damage_to_the_chosen_player() -> None:
    scenario = _scenario([], hand=["Riddle of Lightning"], library=["Serra Angel", "Island"])
    scenario.scry_keeping_everything_on_top()
    _cast_all(scenario, "Riddle of Lightning", targets=["bob"])
    assert _life(scenario, "bob") == 15


def test_riddle_of_lightning_deals_damage_to_a_chosen_creature() -> None:
    scenario = _scenario(
        [], ["Grizzly Bears"], hand=["Riddle of Lightning"], library=["Lightning Bolt", "Island"]
    )
    scenario.scry_keeping_everything_on_top()
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_all(scenario, "Riddle of Lightning", targets=[bears])
    assert bears.damage == 1
    assert _life(scenario, "bob") == 20


def test_riddle_of_lightning_scry_can_change_the_card_that_is_revealed() -> None:
    scenario = _scenario(
        [], hand=["Riddle of Lightning"], library=["Serra Angel", "Island", "Island"]
    )
    angel = scenario.top_of_library(1)[0]
    scenario.scry_bottoming(angel)
    _cast_all(scenario, "Riddle of Lightning", targets=["bob"])
    assert _life(scenario, "bob") == 20  # an Island is revealed: no damage


def test_judge_unworthy_hits_the_chosen_blocker_for_the_revealed_mana_value() -> None:
    scenario = _scenario(
        ["Llanowar Elves"],
        ["Grizzly Bears"],
        hand=["Judge Unworthy"],
        library=["Serra Angel", "Island", "Island"],
    )
    elves = scenario.creature("Llanowar Elves", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    elves.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(elves)
    scenario.block(elves, bears)
    scenario.scry_keeping_everything_on_top()
    _cast_all(scenario, "Judge Unworthy", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD


def test_judge_unworthy_refuses_a_creature_that_is_not_in_combat() -> None:
    scenario = _scenario(["Llanowar Elves"], ["Grizzly Bears"], hand=["Judge Unworthy"])
    bears = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(ValueError):
        scenario.cast("Judge Unworthy", targets=[bears])


# ---------------------------------------------------------------------------
# Mill a card
# ---------------------------------------------------------------------------


def test_heed_the_mists_draws_cards_equal_to_the_milled_cards_mana_value() -> None:
    scenario = _scenario(
        [],
        hand=["Heed the Mists"],
        library=["Serra Angel", "Island", "Island", "Island", "Island", "Island", "Island"],
    )
    _cast_all(scenario, "Heed the Mists")
    assert [c.name for c in scenario.player("alice").graveyard if c.name == "Serra Angel"]
    assert len(_hand(scenario)) == 5


def test_heed_the_mists_a_milled_land_draws_nothing() -> None:
    scenario = _scenario([], hand=["Heed the Mists"], library=["Island", "Serra Angel", "Island"])
    _cast_all(scenario, "Heed the Mists")
    assert _hand(scenario) == []
    assert [c.name for c in scenario.player("alice").graveyard] == ["Heed the Mists", "Island"] or [
        c.name for c in scenario.player("alice").graveyard
    ] == ["Island", "Heed the Mists"]


def test_heed_the_mists_with_an_empty_library_mills_and_draws_nothing() -> None:
    scenario = _scenario([], hand=["Heed the Mists"], library=[])
    scenario.player("alice").library.clear()
    _cast_all(scenario, "Heed the Mists")
    assert _hand(scenario) == []


def test_mindshrieker_pumps_by_the_card_it_made_the_target_player_mill() -> None:
    scenario = _scenario(["Mindshrieker"], bob_library=["Serra Angel", "Island", "Island"])
    shrieker = scenario.creature("Mindshrieker", "alice")
    base = (scenario.game.power_of(shrieker), scenario.game.toughness_of(shrieker))
    scenario.activate(shrieker, targets=["bob"], auto=True)
    _resolve_all(scenario)
    assert [c.name for c in scenario.player("bob").graveyard] == ["Serra Angel"]
    assert scenario.game.power_of(shrieker) == base[0] + 5
    assert scenario.game.toughness_of(shrieker) == base[1] + 5


def test_mindshrieker_milling_itself_with_a_land_pumps_nothing() -> None:
    scenario = _scenario(["Mindshrieker"], library=["Island", "Island"])
    shrieker = scenario.creature("Mindshrieker", "alice")
    base = scenario.game.power_of(shrieker)
    scenario.activate(shrieker, targets=["alice"], auto=True)
    _resolve_all(scenario)
    assert scenario.game.power_of(shrieker) == base


# ---------------------------------------------------------------------------
# Discard at random / reveal at random from a hand
# ---------------------------------------------------------------------------


def test_kindle_the_carnage_damages_each_creature_by_the_discarded_cards_mana_value() -> None:
    scenario = _scenario(["Memnite"], ["Mulldrifter"], hand=["Kindle the Carnage", "Serra Angel"])
    scenario.will_take_the_may(False, source="Kindle the Carnage")
    _cast_all(scenario, "Kindle the Carnage")
    assert [c.name for c in scenario.player("alice").graveyard if c.name == "Serra Angel"]
    assert not _named(scenario, "Memnite")
    assert not _named(scenario, "Mulldrifter")


def test_kindle_the_carnage_may_repeat_until_the_hand_is_empty() -> None:
    scenario = _scenario(
        ["Memnite"],
        ["Hill Giant"],
        hand=["Kindle the Carnage", "Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
    )
    scenario.will_take_the_may(True, source="Kindle the Carnage", times=None)
    _cast_all(scenario, "Kindle the Carnage")
    assert scenario.player("alice").hand == []
    hill_giant = [c for c in scenario.all_card_states() if c.name == "Hill Giant"]
    assert hill_giant and hill_giant[0].zone is Zone.GRAVEYARD  # 1 + 1 + 1 damage, 3 toughness


def test_kindle_the_carnage_with_an_empty_hand_does_nothing() -> None:
    scenario = _scenario(["Memnite"], hand=["Kindle the Carnage"])
    _cast_all(scenario, "Kindle the Carnage")
    assert _named(scenario, "Memnite")


def test_ignite_memories_damages_the_player_by_the_card_revealed_at_random() -> None:
    scenario = _scenario([], hand=["Ignite Memories"], bob_hand=["Serra Angel"])
    _cast_all(scenario, "Ignite Memories", targets=["bob"])
    assert _life(scenario, "bob") == 15
    assert _hand(scenario, "bob") == ["Serra Angel"]  # revealed, not discarded


def test_ignite_memories_storm_copies_each_reveal_again() -> None:
    scenario = _scenario([], hand=["Ignite Memories", "Lightning Bolt"], bob_hand=["Serra Angel"])
    scenario.cast_onto_stack("Lightning Bolt", username="alice", targets=["alice"], auto=True)
    _resolve_all(scenario)
    scenario.cast_onto_stack("Ignite Memories", username="alice", targets=["bob"], auto=True)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20 - 10  # the spell and its one Storm copy


def test_ignite_memories_an_empty_hand_deals_no_damage() -> None:
    scenario = _scenario([], hand=["Ignite Memories"])
    _cast_all(scenario, "Ignite Memories", targets=["bob"])
    assert _life(scenario, "bob") == 20


def test_singe_mind_ogre_makes_the_target_lose_life_equal_to_the_random_card() -> None:
    scenario = _scenario([], hand=["Singe-Mind Ogre"], bob_hand=["Serra Angel"])
    scenario.choose_trigger_targets("Singe-Mind Ogre", [scenario.player("bob")])
    _cast_all(scenario, "Singe-Mind Ogre")
    assert _life(scenario, "bob") == 15


# ---------------------------------------------------------------------------
# Exile the top card / reveal until a nonland card
# ---------------------------------------------------------------------------


def test_hidetsugu_and_kairi_drains_by_the_exiled_card_and_casts_a_spell_free() -> None:
    scenario = _scenario(
        ["Hidetsugu and Kairi"], library=["Divination", "Island", "Island", "Island", "Island"]
    )
    hk = scenario.creature("Hidetsugu and Kairi", "alice")
    scenario.choose_trigger_targets("Hidetsugu and Kairi", [scenario.player("bob")])
    scenario.game.sacrifice(hk)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 17
    assert len(_hand(scenario)) == 2  # Divination cast without paying its mana cost


def test_hidetsugu_and_kairi_does_not_offer_a_creature_card_for_free() -> None:
    scenario = _scenario(["Hidetsugu and Kairi"], library=["Serra Angel", "Island"])
    hk = scenario.creature("Hidetsugu and Kairi", "alice")
    scenario.choose_trigger_targets("Hidetsugu and Kairi", [scenario.player("bob")])
    scenario.game.sacrifice(hk)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 15
    assert _named(scenario, "Serra Angel", Zone.EXILE)


def test_explosive_revelation_reveals_to_a_nonland_card_and_hits_the_target() -> None:
    scenario = _scenario(
        [],
        hand=["Explosive Revelation"],
        library=["Island", "Island", "Serra Angel", "Lightning Bolt", "Island"],
    )
    _cast_all(scenario, "Explosive Revelation", targets=["bob"])
    assert _life(scenario, "bob") == 15
    assert _hand(scenario) == ["Serra Angel"]
    assert [c.name for c in scenario.player("alice").library][-2:] == ["Island", "Island"]


def test_explosive_revelation_with_only_lands_deals_nothing() -> None:
    scenario = _scenario([], hand=["Explosive Revelation"], library=["Island", "Island"])
    _cast_all(scenario, "Explosive Revelation", targets=["bob"])
    assert _life(scenario, "bob") == 20
    assert len(scenario.player("alice").library) == 2


def test_erratic_mutation_gives_the_target_plus_x_minus_x() -> None:
    scenario = _scenario(
        [],
        ["Hill Giant"],
        hand=["Erratic Mutation"],
        library=["Island", "Lightning Bolt", "Island"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    _cast_all(scenario, "Erratic Mutation", targets=[giant])
    assert (scenario.game.power_of(giant), scenario.game.toughness_of(giant)) == (4, 2)


# ---------------------------------------------------------------------------
# The mana value of a spell a spell or ability acts on
# ---------------------------------------------------------------------------


def test_imps_mischief_costs_life_equal_to_the_mana_value_of_the_spell_it_redirects() -> None:
    scenario = _scenario([], ["Grizzly Bears"], hand=["Fireball"], bob_hand=["Imp's Mischief"])
    bears = scenario.creature("Grizzly Bears", "bob")
    fireball = scenario.find("Fireball", Zone.HAND, "alice")
    scenario.game.cast(
        fireball,
        "alice",
        x_value=3,
        targets=[bears],
        mana_sources=scenario.untapped_sources(*LANDS),
    )
    scenario.pass_priority()
    scenario.will_choose_targets("alice", username="bob", source="Imp's Mischief")
    scenario.cast_onto_stack("Imp's Mischief", username="bob", targets=[fireball], auto=True)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20 - 4  # {X}{R} announced with X=3 (CR 202.3e)
    assert _life(scenario, "alice") == 20 - 3  # Fireball now hits its own caster


def test_induce_paranoia_with_black_mana_mills_the_spells_controller() -> None:
    scenario = _scenario(
        [], hand=["Fireball"], bob_hand=["Induce Paranoia"], library=["Island"] * 12
    )
    fireball = scenario.find("Fireball", Zone.HAND, "alice")
    scenario.game.cast(
        fireball,
        "alice",
        x_value=3,
        targets=["bob"],
        mana_sources=scenario.untapped_sources(*LANDS),
    )
    scenario.pass_priority()
    sources = scenario.untapped_sources("Island", "Island", "Island", "Swamp", username="bob")
    scenario.cast_onto_stack("Induce Paranoia", *sources, username="bob", targets=[fireball])
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20  # countered
    assert len(scenario.player("alice").library) == 12 - 4  # X=3 and the {R}: mana value 4


def test_induce_paranoia_without_black_mana_only_counters() -> None:
    scenario = _scenario(
        [], hand=["Fireball"], bob_hand=["Induce Paranoia"], library=["Island"] * 12
    )
    fireball = scenario.find("Fireball", Zone.HAND, "alice")
    scenario.game.cast(
        fireball,
        "alice",
        x_value=3,
        targets=["bob"],
        mana_sources=scenario.untapped_sources(*LANDS),
    )
    scenario.pass_priority()
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", username="bob")
    scenario.cast_onto_stack("Induce Paranoia", *sources, username="bob", targets=[fireball])
    _resolve_all(scenario)
    assert len(scenario.player("alice").library) == 12


# ---------------------------------------------------------------------------
# Breeches, the Blastmaker: a coin flip decides between copying and damage
# ---------------------------------------------------------------------------


def _breeches_game(win: bool):
    from random import Random

    scenario = _scenario(
        ["Breeches, the Blastmaker", "Sol Ring"], hand=["Lightning Bolt", "Glacial Ray"]
    )
    seed = scenario.game.shuffle_seed
    flips = next(n for n in range(64) if (Random(f"{seed}:{n}:coin").random() < 0.5) is win)
    scenario.game.coin_flips_performed = flips
    return scenario


def _second_spell(scenario) -> None:
    scenario.cast_onto_stack("Lightning Bolt", username="alice", targets=["bob"], auto=True)
    _resolve_all(scenario)
    scenario.cast_onto_stack("Glacial Ray", username="alice", targets=["bob"], auto=True)
    _resolve_all(scenario)


def test_breeches_winning_the_flip_copies_the_second_spell() -> None:
    scenario = _breeches_game(win=True)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    _second_spell(scenario)
    assert sol_ring.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 20 - 3 - 2 - 2  # Bolt, Glacial Ray and its copy


def test_breeches_losing_the_flip_deals_the_second_spells_mana_value() -> None:
    scenario = _breeches_game(win=False)
    scenario.will_choose_targets("bob", username="alice", source="Breeches, the Blastmaker")
    _second_spell(scenario)
    assert _life(scenario, "bob") == 20 - 3 - 2 - 2  # Glacial Ray is mana value 2


def test_breeches_declining_the_sacrifice_flips_nothing() -> None:
    scenario = _breeches_game(win=False)
    scenario.will_take_the_may(False, source="Breeches, the Blastmaker")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    _second_spell(scenario)
    assert sol_ring.zone is Zone.BATTLEFIELD
    assert _life(scenario, "bob") == 20 - 3 - 2


# ---------------------------------------------------------------------------
# Shark Typhoon: the X of the cycling cost sizes the token
# ---------------------------------------------------------------------------


def _cycle(scenario, card, sources, *, x_value: int) -> None:
    """Cycle `card` the long way: its "when you cycle" trigger goes on the
    stack above the cycling ability (CR 702.29c)."""
    from magic_cards_model.machines import keywords

    activation = keywords.cycling_activation(scenario.game, card, "alice", x_value=x_value)
    payment = activation.begin_paying()
    scenario.pay_with(payment, *sources)
    activation.activate()
    _resolve_all(scenario)


def test_shark_typhoon_cycled_with_x_makes_an_x_by_x_flying_shark() -> None:
    scenario = _scenario([], hand=["Shark Typhoon"], library=["Island"] * 5)
    typhoon = scenario.find("Shark Typhoon", Zone.HAND, "alice")
    _cycle(scenario, typhoon, scenario.untapped_sources(*(["Island"] * 4 + ["Swamp"])), x_value=3)
    (shark,) = _named(scenario, "Shark")
    assert (shark.power, shark.toughness) == (3, 3)
    assert len(_hand(scenario)) == 1  # the cycling draw


def test_shark_typhoon_cycled_for_zero_makes_a_zero_zero_that_dies() -> None:
    scenario = _scenario([], hand=["Shark Typhoon"], library=["Island"] * 5)
    typhoon = scenario.find("Shark Typhoon", Zone.HAND, "alice")
    _cycle(scenario, typhoon, scenario.untapped_sources("Island", "Island"), x_value=0)
    scenario.state_based_actions()
    assert [s for s in _named(scenario, "Shark") if s.zone is Zone.BATTLEFIELD] == []


def test_endrek_sahr_survives_with_six_thrulls() -> None:
    scenario = _scenario(["Endrek Sahr, Master Breeder"], hand=["Shivan Dragon"])
    _cast_all(scenario, "Shivan Dragon")
    assert len(_named(scenario, "Thrull")) == 6
    assert scenario.creature("Endrek Sahr, Master Breeder", "alice").zone is Zone.BATTLEFIELD


# --- one reader per shape: the card mana value reader defers to existing owners ---

_DARK_CONFIDANT = (
    "Reveal the top card of your library and put that card into your hand. "
    "You lose life equal to its mana value."
)
_COSMIC_CUBE = (
    "Look at the top five cards of your library. You may cast a spell from among them "
    "with mana value less than or equal to the greatest power among attacking creatures "
    "you control without paying its mana cost. Put the rest on the bottom of your "
    "library in a random order."
)


def test_card_mana_value_reader_declines_the_reveal_hand_lose_life_shape() -> None:
    from magic_cards_model.machines.ep02_r2_card_mana_value import card_mana_value_effect

    assert card_mana_value_effect(_DARK_CONFIDANT, for_spell=False) is None


def test_card_mana_value_reader_declines_the_cosmic_cube_shape() -> None:
    from magic_cards_model.machines.ep02_r2_card_mana_value import card_mana_value_effect

    assert card_mana_value_effect(_COSMIC_CUBE, for_spell=False) is None


def test_look_top_cast_free_has_a_single_resolution_body() -> None:
    from magic_cards_model.machines import ep02_r2_card_mana_value as mod

    source = open(mod.__file__).read()
    assert "game.cast_during_resolution(" not in source

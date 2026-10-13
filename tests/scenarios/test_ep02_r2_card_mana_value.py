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
    scenario = _scenario(["Kiora, Sovereign of the Deep"], hand=["Floodtide Serpent"], library=library)
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

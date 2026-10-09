"""EP-01 round 1, task 8: static cast permissions (CR 601.3, CR 611.3d).

One scenario per permission shape, each through the real cast path
(`Casting.use_keyword("Cast permission")`, `why_cannot_cast_from`,
`granted_cast_options`), with the engine's own refusal text where the
permission does not apply and a second, unlisted printing of the same shape.

Shapes:

- a card's own "You may cast this card from your graveyard / exile", plain,
  conditional ("as long as", "if", Max speed), with an additional cost in
  gerund form ("by discarding a card in addition to paying its other costs"),
  and confined ("but not from anywhere else");
- a permanent's "You may cast `<quality>` spells from the top of your
  library" and its variants (once each turn, condition, keywords, additional
  cost, chosen type, shares a card type);
- "You may cast `<quality>` spells as though they had flash" and the
  spell's own conditional flash;
- "You may cast `<quality>` spells without paying their mana costs".

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 601.3 (a rule or effect must allow the cast), CR 604.6 (a static
ability that functions outside the battlefield), CR 611.3d (continuous
effects from static abilities that allow casting), CR 601.2f (additional
costs), CR 702.8a (flash), CR 118.9 (alternative cost of nothing), CR 702.178a
(max speed), CR 700.4 (dies), CR 205.2b (a card with several types).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import (
    Casting,
    conditional_flash_condition,
    granted_cast_options,
    why_cannot_cast_from,
    why_cannot_cast_now,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"
LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest"] * 3


def build(*, alice=None, bob=None, step=Step.PRECOMBAT_MAIN):
    alice = dict(alice or {})
    alice.setdefault("battlefield", [])
    alice["battlefield"] = [*alice["battlefield"], *LANDS]
    alice.setdefault("library", ["Forest"] * 6)
    scenario = (
        Scenario().player("alice", **alice).player("bob", **(bob or {"library": ["Island"] * 6}))
    ).build()
    scenario.start_at(step)
    return scenario


def resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def refusal(scenario, name, zone, caster="alice"):
    card = scenario.find(name, zone, caster if zone is not Zone.EXILE else None)
    return why_cannot_cast_from(card, caster, zone, scenario.game)


def cast_with_permission(
    scenario, name, zone, *, choosing=None, caster="alice", targets=None, **costs
):
    casting = scenario.cast(name, username=caster, from_zone=zone, **costs)
    casting.use_keyword(CAST_PERMISSION, choosing=choosing)
    if targets is not None:
        casting.choose_targets(targets)
    scenario.auto_pay(casting.begin_paying(), username=caster)
    card = scenario.put_on_stack(casting)
    resolve_everything(scenario)
    return card


def on_battlefield(card):
    return card.zone is Zone.BATTLEFIELD


# -- a card's own permission to be cast from its graveyard or exile ----------


def test_a_plain_graveyard_permission_casts_the_card():
    scenario = build(
        alice={"graveyard": ["Skaab Ruinator", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"]}
    )
    bears = [c for c in scenario.player("alice").graveyard if c.name == "Grizzly Bears"]
    ruinator = cast_with_permission(scenario, "Skaab Ruinator", Zone.GRAVEYARD, exiling=bears)
    assert on_battlefield(ruinator)
    assert all(bear.zone is Zone.EXILE for bear in bears)


def test_the_graveyard_permission_does_not_reach_exile():
    scenario = build(alice={"graveyard": ["Skaab Ruinator"]})
    scenario.game.exile_cards([scenario.find("Skaab Ruinator", Zone.GRAVEYARD, "alice")])
    assert refusal(scenario, "Skaab Ruinator", Zone.EXILE).startswith("nothing allows alice")


def test_gravecrawler_needs_a_zombie_to_be_cast_from_the_graveyard():
    scenario = build(alice={"graveyard": ["Gravecrawler"], "battlefield": ["Grizzly Bears"]})
    reason = refusal(scenario, "Gravecrawler", Zone.GRAVEYARD)
    assert reason is not None and "only if you control a Zombie" in reason


def test_gravecrawler_is_cast_from_the_graveyard_while_a_zombie_is_controlled():
    scenario = build(alice={"graveyard": ["Gravecrawler"], "battlefield": ["Skaab Ruinator"]})
    assert refusal(scenario, "Gravecrawler", Zone.GRAVEYARD) is None
    assert on_battlefield(cast_with_permission(scenario, "Gravecrawler", Zone.GRAVEYARD))


def test_marang_river_prowler_needs_a_black_or_green_permanent():
    scenario = build(alice={"graveyard": ["Marang River Prowler"], "battlefield": ["Plains"]})
    reason = refusal(scenario, "Marang River Prowler", Zone.GRAVEYARD)
    assert reason is not None and "black or green permanent" in reason
    scenario = build(alice={"graveyard": ["Marang River Prowler"], "battlefield": ["Grizzly Bears"]})
    assert refusal(scenario, "Marang River Prowler", Zone.GRAVEYARD) is None
    assert on_battlefield(cast_with_permission(scenario, "Marang River Prowler", Zone.GRAVEYARD))


def test_ebondeath_needs_another_creature_to_have_died_this_turn():
    scenario = build(
        alice={"graveyard": ["Ebondeath, Dracolich"], "battlefield": ["Grizzly Bears"]}
    )
    reason = refusal(scenario, "Ebondeath, Dracolich", Zone.GRAVEYARD)
    assert reason is not None and "not named Ebondeath, Dracolich died this turn" in reason
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    assert refusal(scenario, "Ebondeath, Dracolich", Zone.GRAVEYARD) is None
    assert on_battlefield(cast_with_permission(scenario, "Ebondeath, Dracolich", Zone.GRAVEYARD))


def test_ebondeath_does_not_count_its_own_death():
    scenario = build(alice={"battlefield": ["Ebondeath, Dracolich"]})
    scenario.game.destroy(scenario.creature("Ebondeath, Dracolich", "alice"))
    reason = refusal(scenario, "Ebondeath, Dracolich", Zone.GRAVEYARD)
    assert reason is not None and "that is not so" in reason


def test_oathsworn_vampire_needs_life_gained_this_turn():
    scenario = build(alice={"graveyard": ["Oathsworn Vampire"]})
    reason = refusal(scenario, "Oathsworn Vampire", Zone.GRAVEYARD)
    assert reason is not None and "gained life this turn" in reason
    scenario.game.gain_life("alice", 1)
    assert refusal(scenario, "Oathsworn Vampire", Zone.GRAVEYARD) is None
    assert on_battlefield(cast_with_permission(scenario, "Oathsworn Vampire", Zone.GRAVEYARD))


def test_a_max_speed_ability_word_is_the_condition():
    scenario = build(
        alice={"graveyard": ["Lightwheel Enhancements"], "battlefield": ["Grizzly Bears"]}
    )
    reason = refusal(scenario, "Lightwheel Enhancements", Zone.GRAVEYARD)
    assert reason is not None and "you have max speed" in reason
    scenario.game.player("alice").speed = 4
    assert refusal(scenario, "Lightwheel Enhancements", Zone.GRAVEYARD) is None


def test_squee_is_castable_from_the_graveyard_and_from_exile():
    scenario = build(alice={"graveyard": ["Squee, the Immortal"]})
    assert refusal(scenario, "Squee, the Immortal", Zone.GRAVEYARD) is None
    scenario.game.exile_cards([scenario.find("Squee, the Immortal", Zone.GRAVEYARD, "alice")])
    assert refusal(scenario, "Squee, the Immortal", Zone.EXILE) is None
    assert on_battlefield(cast_with_permission(scenario, "Squee, the Immortal", Zone.EXILE))


def test_a_from_exile_only_permission_does_not_open_the_graveyard():
    scenario = build(alice={"graveyard": ["Misthollow Griffin"]})
    assert refusal(scenario, "Misthollow Griffin", Zone.GRAVEYARD).startswith("nothing allows")
    scenario.game.exile_cards([scenario.find("Misthollow Griffin", Zone.GRAVEYARD, "alice")])
    assert refusal(scenario, "Misthollow Griffin", Zone.EXILE) is None
    assert on_battlefield(cast_with_permission(scenario, "Misthollow Griffin", Zone.EXILE))


def test_eternal_scourge_is_cast_from_exile():
    scenario = build(alice={"graveyard": ["Eternal Scourge"]})
    scenario.game.exile_cards([scenario.find("Eternal Scourge", Zone.GRAVEYARD, "alice")])
    assert on_battlefield(cast_with_permission(scenario, "Eternal Scourge", Zone.EXILE))


def test_haakon_is_confined_to_the_graveyard():
    scenario = build(alice={"hand": ["Haakon, Stromgald Scourge"]})
    reason = refusal(scenario, "Haakon, Stromgald Scourge", Zone.HAND)
    assert reason is not None and "only from the graveyard" in reason
    scenario = build(alice={"graveyard": ["Haakon, Stromgald Scourge"]})
    assert refusal(scenario, "Haakon, Stromgald Scourge", Zone.GRAVEYARD) is None
    assert on_battlefield(
        cast_with_permission(scenario, "Haakon, Stromgald Scourge", Zone.GRAVEYARD)
    )


# -- the permission's own additional cost, worded as a gerund ----------------


def test_alien_symbiosis_discards_a_card_to_be_cast_from_the_graveyard():
    scenario = build(
        alice={"graveyard": ["Alien Symbiosis"], "hand": ["Island"], "battlefield": ["Grizzly Bears"]}
    )
    island = scenario.find("Island", Zone.HAND, "alice")
    cast_with_permission(
        scenario,
        "Alien Symbiosis",
        Zone.GRAVEYARD,
        choosing=[island],
        targets=[scenario.creature("Grizzly Bears", "alice")],
    )
    assert island.zone is Zone.GRAVEYARD


def test_rona_discards_two_cards():
    scenario = build(
        alice={"graveyard": ["Rona, Sheoldred's Faithful"], "hand": ["Island", "Swamp"]}
    )
    hand = list(scenario.player("alice").hand)
    rona = cast_with_permission(scenario, "Rona, Sheoldred's Faithful", Zone.GRAVEYARD, choosing=hand)
    assert on_battlefield(rona)
    assert all(card.zone is Zone.GRAVEYARD for card in hand)


def test_demonic_embrace_pays_three_life_and_discards():
    scenario = build(
        alice={"graveyard": ["Demonic Embrace"], "hand": ["Island"], "battlefield": ["Grizzly Bears"]}
    )
    island = scenario.find("Island", Zone.HAND, "alice")
    cast_with_permission(
        scenario,
        "Demonic Embrace",
        Zone.GRAVEYARD,
        choosing=[island],
        targets=[scenario.creature("Grizzly Bears", "alice")],
    )
    assert scenario.player("alice").life == 17
    assert island.zone is Zone.GRAVEYARD


def test_wickerfolk_pays_two_life_and_sacrifices_a_creature():
    scenario = build(alice={"graveyard": ["Wickerfolk Indomitable"], "battlefield": ["Grizzly Bears"]})
    bears = scenario.creature("Grizzly Bears", "alice")
    folk = cast_with_permission(scenario, "Wickerfolk Indomitable", Zone.GRAVEYARD, choosing=[bears])
    assert on_battlefield(folk)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18


# -- a permanent's permission to cast from the top of the library ------------


def top_board(permanent, library, *, battlefield=(), hand=()):
    return build(
        alice={"battlefield": [permanent, *battlefield], "library": [*library, "Forest", "Forest"], "hand": list(hand)}
    )


def top_refusal(scenario):
    top = scenario.player("alice").library[0]
    return why_cannot_cast_from(top, "alice", Zone.LIBRARY, scenario.game)


def cast_top(scenario, *, targets=None, choosing=None):
    top = scenario.player("alice").library[0]
    casting = scenario.cast(top.name, username="alice", from_zone=Zone.LIBRARY)
    casting.use_keyword(CAST_PERMISSION, choosing=choosing)
    if targets is not None:
        casting.choose_targets(targets)
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    resolve_everything(scenario)
    return top


@pytest.mark.parametrize("permanent", ["Precognition Field", "Melek, Izzet Paragon"])
def test_instant_and_sorcery_spells_are_castable_from_the_top(permanent):
    scenario = top_board(permanent, ["Divination"])
    assert top_refusal(scenario) is None
    assert cast_top(scenario).zone is Zone.GRAVEYARD
    scenario = top_board(permanent, ["Grizzly Bears"])
    assert top_refusal(scenario).startswith("nothing allows alice")


def test_artifact_and_colorless_spells_from_the_top_with_mystic_forge():
    scenario = top_board("Mystic Forge", ["Sol Ring"])
    assert on_battlefield(cast_top(scenario))
    scenario = top_board("Mystic Forge", ["Grizzly Bears"])
    assert top_refusal(scenario) is not None
    # "colorless" is its own atom: an Eldrazi that is not an artifact
    scenario = top_board("Mystic Forge", ["Eternal Scourge"])
    assert top_refusal(scenario) is None


def test_a_subtype_and_noncreature_list_from_the_top_with_madame_web():
    scenario = top_board("Madame Web, Clairvoyant", ["Spider-Man, Web-Slinger"])
    assert top_refusal(scenario) is None
    scenario = top_board("Madame Web, Clairvoyant", ["Divination"])
    assert top_refusal(scenario) is None
    scenario = top_board("Madame Web, Clairvoyant", ["Grizzly Bears"])
    assert top_refusal(scenario) is not None


def test_two_subtypes_from_the_top_with_sigarda():
    for top, readable in (
        ("Serra Angel", True),
        ("Thraben Inspector", True),
        ("Grizzly Bears", False),
    ):
        scenario = top_board("Sigarda, Font of Blessings", [top])
        assert (top_refusal(scenario) is None) is readable, top


def test_the_chosen_creature_type_gates_realmwalker():
    from magic_cards_model.models.card_state import Choice, ChoiceKind

    scenario = top_board("Realmwalker", ["Llanowar Elves"])
    realmwalker = scenario.creature("Realmwalker", "alice")
    assert top_refusal(scenario) is not None  # nothing chosen yet
    realmwalker.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Elf")
    assert top_refusal(scenario) is None
    scenario = top_board("Realmwalker", ["Grizzly Bears"])
    scenario.creature("Realmwalker", "alice").choice = Choice(
        kind=ChoiceKind.CREATURE_TYPE, value="Elf"
    )
    assert top_refusal(scenario) is not None


def test_flash_or_flying_from_the_top_with_errant_and_giada():
    scenario = top_board("Errant and Giada", ["Serra Angel"])
    assert top_refusal(scenario) is None
    scenario = top_board("Errant and Giada", ["Grizzly Bears"])
    assert top_refusal(scenario) is not None
    scenario = top_board("Errant and Giada", ["Lightning Bolt"])
    assert top_refusal(scenario) is not None  # an instant is not a spell with flash


def test_historic_spells_and_lands_from_the_top_with_crystal_skull():
    scenario = top_board("Crystal Skull, Isu Spyglass", ["Sol Ring"])
    assert top_refusal(scenario) is None
    scenario = top_board("Crystal Skull, Isu Spyglass", ["Grizzly Bears"])
    assert top_refusal(scenario) is not None
    scenario = top_board("Crystal Skull, Isu Spyglass", ["Forest"])
    forest = scenario.player("alice").library[0]
    with pytest.raises(ValueError):
        scenario.game.play_land(forest, "alice")


def test_coven_gates_augur_of_autumn_on_different_powers():
    scenario = top_board(
        "Augur of Autumn", ["Hill Giant"], battlefield=["Llanowar Elves", "Grizzly Bears"]
    )
    assert top_refusal(scenario) is not None  # powers 2, 1 and 2: only two different
    scenario = top_board(
        "Augur of Autumn", ["Hill Giant"], battlefield=["Llanowar Elves", "Hill Giant"]
    )
    assert top_refusal(scenario) is None
    assert on_battlefield(cast_top(scenario))


def test_assemble_the_players_is_once_each_turn_and_power_bounded():
    scenario = top_board("Assemble the Players", ["Hill Giant"])
    assert top_refusal(scenario) is not None  # power 3 is over the bound
    scenario = top_board("Assemble the Players", ["Grizzly Bears", "Llanowar Elves"])
    assert on_battlefield(cast_top(scenario))
    assert top_refusal(scenario) is not None  # the one use of this turn is gone


def test_johann_is_once_each_turn_for_an_instant_or_sorcery():
    scenario = top_board("Johann, Apprentice Sorcerer", ["Divination", "Divination"])
    assert top_refusal(scenario) is None
    cast_top(scenario)
    assert top_refusal(scenario) is not None


def test_falco_spara_removes_a_counter_in_addition_to_the_cost():
    scenario = top_board("Falco Spara, Pactweaver", ["Divination"], battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    cast_top(scenario, choosing=[bears])
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_falco_spara_cannot_pay_without_a_counter():
    scenario = top_board("Falco Spara, Pactweaver", ["Divination"])
    scenario.creature("Falco Spara, Pactweaver", "alice").counters.clear()
    with pytest.raises(ValueError):
        cast_top(scenario)


def test_radha_plays_lands_from_the_top_but_casts_nothing():
    scenario = top_board("Radha, Heart of Keld", ["Forest", "Grizzly Bears"])
    forest = scenario.player("alice").library[0]
    scenario.game.play_land(forest, "alice")
    assert forest.zone is Zone.BATTLEFIELD
    assert top_refusal(scenario).startswith("nothing allows alice")


def test_lunar_whale_plays_the_top_card_only_after_it_attacked():
    scenario = top_board("The Lunar Whale", ["Grizzly Bears"])
    assert top_refusal(scenario) is not None
    whale = scenario.creature("The Lunar Whale", "alice")
    from magic_cards_model.models.game.records import TurnHistoryEntry

    scenario.game.turn_history.append(
        TurnHistoryEntry(kind="attacked", player="alice", object_id=whale.id)
    )
    assert top_refusal(scenario) is None


def test_the_reality_chip_needs_to_be_attached():
    scenario = top_board("The Reality Chip", ["Grizzly Bears"], battlefield=["Llanowar Elves"])
    assert top_refusal(scenario) is not None
    chip = scenario.creature("The Reality Chip", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    chip.attach_to(elves)
    assert top_refusal(scenario) is None


def test_case_of_the_locked_hothouse_works_only_when_solved():
    scenario = top_board("Case of the Locked Hothouse", ["Grizzly Bears"])
    assert top_refusal(scenario) is not None
    case = next(c for c in scenario.game.battlefield if c.name == "Case of the Locked Hothouse")
    case.solved = True
    assert top_refusal(scenario) is None
    scenario = top_board("Case of the Locked Hothouse", ["Divination"])
    next(c for c in scenario.game.battlefield if c.name == "Case of the Locked Hothouse").solved = True
    assert top_refusal(scenario) is not None  # a sorcery is neither creature nor enchantment

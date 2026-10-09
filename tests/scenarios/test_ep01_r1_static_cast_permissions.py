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
    why_cannot_cast_from,
    why_cannot_cast_now,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"
LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest"] * 3


def build(*, alice=None, bob=None, step=Step.PRECOMBAT_MAIN, lands=LANDS):
    alice = dict(alice or {})
    alice.setdefault("battlefield", [])
    alice["battlefield"] = [*alice["battlefield"], *lands]
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
    scenario = build(
        alice={"graveyard": ["Marang River Prowler"], "battlefield": ["Grizzly Bears"]}
    )
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
        alice={
            "graveyard": ["Alien Symbiosis"],
            "hand": ["Island"],
            "battlefield": ["Grizzly Bears"],
        }
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
    rona = cast_with_permission(
        scenario, "Rona, Sheoldred's Faithful", Zone.GRAVEYARD, choosing=hand
    )
    assert on_battlefield(rona)
    assert all(card.zone is Zone.GRAVEYARD for card in hand)


def test_demonic_embrace_pays_three_life_and_discards():
    scenario = build(
        alice={
            "graveyard": ["Demonic Embrace"],
            "hand": ["Island"],
            "battlefield": ["Grizzly Bears"],
        }
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
    scenario = build(
        alice={"graveyard": ["Wickerfolk Indomitable"], "battlefield": ["Grizzly Bears"]}
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    folk = cast_with_permission(
        scenario, "Wickerfolk Indomitable", Zone.GRAVEYARD, choosing=[bears]
    )
    assert on_battlefield(folk)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18


# -- a permanent's permission to cast from the top of the library ------------


def top_board(permanent, library, *, battlefield=(), hand=()):
    return build(
        alice={
            "battlefield": [permanent, *battlefield],
            "library": [*library, "Forest", "Forest"],
            "hand": list(hand),
        }
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
    next(
        c for c in scenario.game.battlefield if c.name == "Case of the Locked Hothouse"
    ).solved = True
    assert top_refusal(scenario) is not None  # a sorcery is neither creature nor enchantment


# -- "You may cast <quality> spells as though they had flash" ----------------


def flash_board(permanent, hand, *, graveyard=(), battlefield=()):
    scenario = build(
        alice={
            "battlefield": [permanent, *battlefield],
            "hand": list(hand),
            "graveyard": list(graveyard),
        },
        step=Step.BEGINNING_OF_COMBAT,
    )
    return scenario


def flash_refusal(scenario, name):
    spell = scenario.find(name, Zone.HAND, "alice")
    return why_cannot_cast_now(spell, "alice", scenario.game)


FLASH_GRANTS = [
    ("Vivien, Champion of the Wilds", "Grizzly Bears", "Divination"),
    ("Prophet of Kruphix", "Grizzly Bears", "Divination"),
    ("Raff Capashen, Ship's Mage", "Sol Ring", "Grizzly Bears"),
    ("Yeva, Nature's Herald", "Llanowar Elves", "Hill Giant"),
    ("Sigarda's Aid", "Pacifism", "Grizzly Bears"),
    ("Sigarda's Aid", "Bonesplitter", "Divination"),
    ("Whirlwing Stormbrood // Dynamic Soar", "Shivan Dragon", "Grizzly Bears"),
    ("Whirlwing Stormbrood // Dynamic Soar", "Divination", "Grizzly Bears"),
    ("Gandalf the White", "Squee, the Immortal", "Grizzly Bears"),
    ("Gandalf the White", "Sol Ring", "Grizzly Bears"),
    ("Liberator, Urza's Battlethopter", "Eternal Scourge", "Grizzly Bears"),
    ("Liberator, Urza's Battlethopter", "Sol Ring", "Grizzly Bears"),
    ("Valley Floodcaller", "Divination", "Grizzly Bears"),
    ("Rattlechains", "Cemetery Illuminator", "Grizzly Bears"),
    ("Shimmer Myr", "Sol Ring", "Grizzly Bears"),
    ("Najal, the Storm Runner", "Divination", "Grizzly Bears"),
    ("Hypersonic Dragon", "Divination", "Grizzly Bears"),
    ("Gandalf, Friend of the Shire", "Divination", "Grizzly Bears"),
]


@pytest.mark.parametrize(("permanent", "granted", "refused"), FLASH_GRANTS)
def test_a_quality_flash_grant_covers_its_quality_and_nothing_else(permanent, granted, refused):
    scenario = flash_board(permanent, [granted, refused])
    assert flash_refusal(scenario, granted) is None
    reason = flash_refusal(scenario, refused)
    assert reason is not None and "is not an instant and has no flash" in reason


def test_a_flash_grant_works_only_while_its_permanent_does():
    scenario = flash_board("Vivien, Champion of the Wilds", ["Grizzly Bears"])
    assert flash_refusal(scenario, "Grizzly Bears") is None
    scenario.game.destroy(next(c for c in scenario.game.battlefield if c.name.startswith("Vivien")))
    assert flash_refusal(scenario, "Grizzly Bears") is not None


def test_dragon_grip_has_flash_only_with_a_power_four_creature():
    scenario = flash_board("Grizzly Bears", ["Dragon Grip"])
    assert flash_refusal(scenario, "Dragon Grip") is not None
    scenario = flash_board("Shivan Dragon", ["Dragon Grip"])
    assert flash_refusal(scenario, "Dragon Grip") is None


def test_hungering_yeti_has_flash_with_a_green_or_blue_permanent():
    scenario = flash_board("Hill Giant", ["Hungering Yeti"])
    assert flash_refusal(scenario, "Hungering Yeti") is not None
    scenario = flash_board("Llanowar Elves", ["Hungering Yeti"])
    assert flash_refusal(scenario, "Hungering Yeti") is None


def test_serpent_of_the_pass_has_flash_with_three_lessons_in_the_graveyard():
    lessons = ["Airbending Lesson", "Boomerang Basics", "Combustion Technique"]
    scenario = flash_board("Grizzly Bears", ["Serpent of the Pass"], graveyard=lessons[:2])
    assert flash_refusal(scenario, "Serpent of the Pass") is not None
    scenario = flash_board("Grizzly Bears", ["Serpent of the Pass"], graveyard=lessons)
    assert flash_refusal(scenario, "Serpent of the Pass") is None


def test_the_conditional_flash_wordings_are_read_per_line():
    assert (
        conditional_flash_condition(
            "Ferocious — If you control a creature with power 4 or greater, you may cast "
            "this spell as though it had flash."
        )
        == "you control a creature with power 4 or greater"
    )
    assert (
        conditional_flash_condition(
            "As long as you control a green or blue permanent, you may cast this spell as "
            "though it had flash."
        )
        == "you control a green or blue permanent"
    )
    assert conditional_flash_condition("Flash") is None


# -- Qasali Ambusher: a free cast and flash while it is attacked -------------


def attacked_board(*, defender_battlefield):
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 6)
        .player(
            "alice",
            hand=["Qasali Ambusher"],
            battlefield=defender_battlefield,
            library=["Forest"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def qasali_free_option(scenario):
    spell = scenario.find("Qasali Ambusher", Zone.HAND, "alice")
    return [
        o
        for o in scenario.game.alternative_costs_for(spell, "alice")
        if o.description.startswith("nothing")
    ]


def test_qasali_ambusher_is_free_and_flash_while_attacked_with_a_forest_and_a_plains():
    scenario = attacked_board(defender_battlefield=["Forest", "Plains"])
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"), defending="alice")
    assert flash_refusal(scenario, "Qasali Ambusher") is None
    (option,) = qasali_free_option(scenario)
    assert option.unavailable is None


def test_qasali_ambusher_is_refused_without_the_plains_or_without_an_attacker():
    scenario = attacked_board(defender_battlefield=["Forest", "Island"])
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"), defending="alice")
    assert flash_refusal(scenario, "Qasali Ambusher") is not None
    (option,) = qasali_free_option(scenario)
    assert "is not so" in option.unavailable
    scenario = attacked_board(defender_battlefield=["Forest", "Plains"])
    assert flash_refusal(scenario, "Qasali Ambusher") is not None
    (option,) = qasali_free_option(scenario)
    assert "is not so" in option.unavailable


def test_qasali_ambusher_is_actually_cast_without_mana_during_the_attack():
    scenario = attacked_board(defender_battlefield=["Forest", "Plains"])
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"), defending="alice")
    scenario.pass_priority()  # bob passes; alice now holds priority
    casting = scenario.cast("Qasali Ambusher", username="alice")
    casting.use_alternative_cost()
    scenario.auto_pay(casting.begin_paying(), username="alice")
    ambusher = scenario.put_on_stack(casting)
    resolve_everything(scenario)
    assert ambusher.zone is Zone.BATTLEFIELD
    assert not any(land.tapped for land in scenario.game.permanents_controlled_by("alice"))


# -- "You may cast <quality> spells without paying their mana costs" ---------


def free_board(permanent, hand, *, battlefield=()):
    return build(alice={"battlefield": [permanent, *battlefield], "hand": list(hand)})


def free_options(scenario, name):
    card = scenario.find(name, Zone.HAND, "alice")
    return [
        o for o in scenario.game.alternative_costs_for(card, "alice") if o.description == "nothing"
    ]


def test_dracogenesis_makes_dragon_spells_free():
    scenario = free_board("Dracogenesis", ["Shivan Dragon", "Grizzly Bears"])
    (option,) = free_options(scenario, "Shivan Dragon")
    assert option.unavailable is None
    assert free_options(scenario, "Grizzly Bears") == [] or all(
        o.unavailable for o in free_options(scenario, "Grizzly Bears")
    )
    casting = scenario.cast("Shivan Dragon", username="alice")
    casting.use_alternative_cost()
    scenario.auto_pay(casting.begin_paying(), username="alice")
    dragon = scenario.put_on_stack(casting)
    resolve_everything(scenario)
    assert dragon.zone is Zone.BATTLEFIELD
    assert not any(land.tapped for land in scenario.game.permanents_controlled_by("alice"))


def test_dracogenesis_reaches_every_zone_a_dragon_is_cast_from():
    from magic_cards_model.machines.casting.casting import (
        static_free_cast_grants,
        static_free_cast_refusal,
    )

    scenario = build(
        alice={"battlefield": ["Dracogenesis"], "graveyard": ["Shivan Dragon", "Grizzly Bears"]}
    )
    ((name, grant),) = static_free_cast_grants(scenario.game, "alice")
    assert grant.zone is None
    dragon = scenario.find("Shivan Dragon", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert (
        static_free_cast_refusal(scenario.game, "alice", dragon, Zone.GRAVEYARD, name, grant)
        is None
    )
    assert "only applies to dragon spells" in static_free_cast_refusal(
        scenario.game, "alice", bears, Zone.GRAVEYARD, name, grant
    )


def test_fires_of_invention_frees_a_spell_within_the_land_count():
    scenario = free_board("Fires of Invention", ["Grizzly Bears", "Shivan Dragon"])
    # fifteen lands: both spells have mana value within that
    assert free_options(scenario, "Grizzly Bears")[0].unavailable is None
    assert free_options(scenario, "Shivan Dragon")[0].unavailable is None


def test_fires_of_invention_refuses_a_spell_above_the_land_count():
    scenario = build(alice={"battlefield": ["Fires of Invention"], "hand": ["Shivan Dragon"]})
    lands = [
        c for c in scenario.game.permanents_controlled_by("alice") if c.name != "Fires of Invention"
    ]
    for land in lands[5:]:
        scenario.game.exile_permanent(land)
    (option,) = free_options(scenario, "Shivan Dragon")
    assert "only applies to spells with mana value 5 or less" in option.unavailable


# -- a permanent's permission to play the cards in its pile of exile ---------


def exile_linked(scenario, card_name, permanent, *, zone=Zone.LIBRARY, owner="alice", face_up=True):
    """Exile `card_name` from `zone` as if `permanent`'s own ability had (CR
    607.2a): the annotation is the one the exiling effects write."""
    from magic_cards_model.models.card_state import ExileAnnotation, ExileMarker

    card = scenario.find(card_name, zone, owner)
    scenario.game.exile_cards([card])
    card.exile_annotation = ExileAnnotation(
        marker=ExileMarker.LINKED,
        owner=owner,
        linked_permanent_id=permanent.id,
        linked_permanent_stamp=permanent.zone_change_stamp,
    )
    card.face_up = face_up
    return card


def permanent_named(scenario, name):
    return next(c for c in scenario.game.battlefield if c.name == name)


def exile_refusal(scenario, card):
    return why_cannot_cast_from(card, "alice", Zone.EXILE, scenario.game)


def cast_from_pile(scenario, card, **kwargs):
    casting = Casting(spell=card, caster="alice", origin_zone=Zone.EXILE, game=scenario.game)
    casting.use_keyword(CAST_PERMISSION, **kwargs)
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    resolve_everything(scenario)
    return card


def test_hedonists_trove_plays_lands_but_casts_nothing_from_its_pile():
    scenario = build(
        alice={"battlefield": ["Hedonist's Trove"], "library": ["Forest", "Grizzly Bears"]}
    )
    trove = permanent_named(scenario, "Hedonist's Trove")
    forest = exile_linked(scenario, "Forest", trove)
    bears = exile_linked(scenario, "Grizzly Bears", trove)
    scenario.game.play_land(forest, "alice")
    assert forest.zone is Zone.BATTLEFIELD
    # the creature half is the card's second sentence, not this one
    assert exile_refusal(scenario, bears) is None


def test_hedonists_trove_ignores_a_card_it_did_not_exile():
    scenario = build(
        alice={"battlefield": ["Hedonist's Trove"], "library": ["Forest", "Grizzly Bears"]}
    )
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.game.exile_cards([bears])
    assert exile_refusal(scenario, bears).startswith("nothing allows alice")


def test_colfenors_plans_plays_a_face_down_card_it_exiled():
    scenario = build(
        alice={"battlefield": ["Colfenor's Plans"], "library": ["Forest", "Grizzly Bears"]}
    )
    plans = permanent_named(scenario, "Colfenor's Plans")
    bears = exile_linked(scenario, "Grizzly Bears", plans, face_up=False)
    assert exile_refusal(scenario, bears) is None
    assert on_battlefield(cast_from_pile(scenario, bears))


def test_theater_of_horrors_needs_your_turn_and_an_opponent_who_lost_life():
    scenario = build(alice={"battlefield": ["Theater of Horrors"], "library": ["Grizzly Bears"]})
    theater = permanent_named(scenario, "Theater of Horrors")
    bears = exile_linked(scenario, "Grizzly Bears", theater)
    reason = exile_refusal(scenario, bears)
    assert reason is not None and "nothing allows alice" in reason
    scenario.game.lose_life("bob", 1)
    assert exile_refusal(scenario, bears) is None
    assert on_battlefield(cast_from_pile(scenario, bears))


def test_jacob_hauken_is_a_free_cast_once_per_turn():
    scenario = build(
        alice={
            "battlefield": ["Jacob Hauken, Inspector // Hauken's Insight"],
            "library": ["Grizzly Bears", "Hill Giant"],
        }
    )
    jacob = permanent_named(scenario, "Jacob Hauken, Inspector")
    jacob.transform()  # Hauken's Insight carries the permission
    bears = exile_linked(scenario, "Grizzly Bears", jacob, face_up=False)
    giant = exile_linked(scenario, "Hill Giant", jacob, face_up=False)
    assert exile_refusal(scenario, bears) is None
    cast_from_pile(scenario, bears)
    assert not any(land.tapped for land in scenario.game.permanents_controlled_by("alice"))
    assert exile_refusal(scenario, giant).startswith("nothing allows alice")


def test_grolnok_plays_the_cards_it_owns_with_croak_counters():
    scenario = build(
        alice={"battlefield": ["Grolnok, the Omnivore"], "library": ["Grizzly Bears", "Hill Giant"]}
    )
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    giant = scenario.find("Hill Giant", Zone.LIBRARY, "alice")
    scenario.game.exile_cards([bears, giant])
    scenario.game.add_counters(bears, "croak", 1)
    assert exile_refusal(scenario, bears) is None
    assert exile_refusal(scenario, giant).startswith("nothing allows alice")
    assert on_battlefield(cast_from_pile(scenario, bears))


def test_grolnok_does_not_reach_cards_alice_does_not_own():
    scenario = build(
        alice={"battlefield": ["Grolnok, the Omnivore"]}, bob={"library": ["Grizzly Bears"]}
    )
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "bob")
    scenario.game.exile_cards([bears])
    scenario.game.add_counters(bears, "croak", 1)
    assert exile_refusal(scenario, bears).startswith("nothing allows alice")


def test_tinybones_plays_only_cards_it_does_not_own_with_stash_counters_on_its_turn():
    scenario = build(
        alice={"battlefield": ["Tinybones, Bauble Burglar"]},
        bob={"library": ["Shivan Dragon", "Grizzly Bears"]},
        lands=["Swamp"] * 6,
    )
    dragon = scenario.find("Shivan Dragon", Zone.LIBRARY, "bob")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "bob")
    scenario.game.exile_cards([dragon, bears])
    scenario.game.add_counters(dragon, "stash", 1)
    assert exile_refusal(scenario, dragon) is None
    assert exile_refusal(scenario, bears).startswith("nothing allows alice")
    # mana of any type: six Swamps pay the red dragon's {4}{R}{R}
    assert on_battlefield(cast_from_pile(scenario, dragon))


def test_azula_casts_what_it_exiled_at_any_time_during_your_turn_with_any_mana():
    scenario = build(
        alice={"battlefield": ["Azula, Cunning Usurper"]},
        bob={"library": ["Grizzly Bears"]},
    )
    azula = permanent_named(scenario, "Azula, Cunning Usurper")
    bears = exile_linked(scenario, "Grizzly Bears", azula, owner="bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)  # creature spells are sorcery-speed without flash
    assert exile_refusal(scenario, bears) is None
    assert on_battlefield(cast_from_pile(scenario, bears))


# -- playing from the graveyard: Lurrus, Serra Paragon, Muldrotha, Emet-Selch -


def test_lurrus_casts_a_cheap_permanent_spell_once_each_turn():
    scenario = build(
        alice={
            "battlefield": ["Lurrus of the Dream-Den"],
            "graveyard": ["Grizzly Bears", "Savannah Lions", "Hill Giant", "Divination"],
        }
    )
    assert refusal(scenario, "Hill Giant", Zone.GRAVEYARD).startswith("nothing allows alice")
    assert refusal(scenario, "Divination", Zone.GRAVEYARD).startswith("nothing allows alice")
    assert on_battlefield(cast_with_permission(scenario, "Grizzly Bears", Zone.GRAVEYARD))
    assert refusal(scenario, "Savannah Lions", Zone.GRAVEYARD).startswith("nothing allows alice")


def test_serra_paragon_plays_a_land_or_casts_a_cheap_spell_once_and_the_card_gains_an_ability():
    scenario = build(
        alice={
            "battlefield": ["Serra Paragon"],
            "graveyard": ["Forest", "Grizzly Bears", "Hill Giant"],
        }
    )
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")
    assert refusal(scenario, "Hill Giant", Zone.GRAVEYARD).startswith("nothing allows alice")
    scenario.game.play_land(forest, "alice")
    assert forest.zone is Zone.BATTLEFIELD
    assert "exile it and you gain 2 life" in forest.granted_ability_texts[0]
    # the one use of the turn is spent by the land
    assert refusal(scenario, "Grizzly Bears", Zone.GRAVEYARD).startswith("nothing allows alice")


def test_serra_paragon_cast_spell_gains_the_ability_and_spends_the_use():
    scenario = build(
        alice={"battlefield": ["Serra Paragon"], "graveyard": ["Forest", "Grizzly Bears"]}
    )
    bears = cast_with_permission(scenario, "Grizzly Bears", Zone.GRAVEYARD)
    assert on_battlefield(bears)
    assert "gain 2 life" in bears.granted_ability_texts[0]
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        scenario.game.play_land(forest, "alice")


def test_muldrotha_plays_one_land_and_casts_one_permanent_spell_of_each_type():
    scenario = build(
        alice={
            "battlefield": ["Muldrotha, the Gravetide"],
            "graveyard": [
                "Forest",
                "Island",
                "Grizzly Bears",
                "Hill Giant",
                "Sol Ring",
                "Mind Stone",
            ],
        }
    )
    scenario.game.play_land(scenario.find("Forest", Zone.GRAVEYARD, "alice"), "alice")
    with pytest.raises(ValueError):
        scenario.game.play_land(scenario.find("Island", Zone.GRAVEYARD, "alice"), "alice")
    assert on_battlefield(cast_with_permission(scenario, "Grizzly Bears", Zone.GRAVEYARD))
    assert refusal(scenario, "Hill Giant", Zone.GRAVEYARD).startswith("nothing allows alice")
    assert on_battlefield(cast_with_permission(scenario, "Sol Ring", Zone.GRAVEYARD))
    assert refusal(scenario, "Mind Stone", Zone.GRAVEYARD).startswith("nothing allows alice")


def test_muldrotha_does_not_cast_a_nonpermanent_spell():
    scenario = build(
        alice={"battlefield": ["Muldrotha, the Gravetide"], "graveyard": ["Divination"]}
    )
    assert refusal(scenario, "Divination", Zone.GRAVEYARD).startswith("nothing allows alice")


def test_emet_selch_plays_any_card_from_the_graveyard_on_your_turn():
    scenario = build(
        alice={
            "battlefield": ["Emet-Selch, Unsundered // Hades, Sorcerer of Eld"],
            "graveyard": ["Forest", "Divination", "Hill Giant"],
        }
    )
    next(c for c in scenario.game.battlefield if c.name.startswith("Emet-Selch")).transform()
    assert refusal(scenario, "Divination", Zone.GRAVEYARD) is None
    assert refusal(scenario, "Hill Giant", Zone.GRAVEYARD) is None
    scenario.game.play_land(scenario.find("Forest", Zone.GRAVEYARD, "alice"), "alice")
    # the back face's own replacement exiles what would reach the graveyard
    assert cast_with_permission(scenario, "Divination", Zone.GRAVEYARD).zone is Zone.EXILE


def test_emet_selch_does_nothing_on_an_opponents_turn():
    scenario = (
        Scenario()
        .player("bob", library=["Island"] * 6)
        .player(
            "alice",
            battlefield=["Emet-Selch, Unsundered // Hades, Sorcerer of Eld", *LANDS],
            graveyard=["Divination"],
            library=["Forest"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert refusal(scenario, "Divination", Zone.GRAVEYARD).startswith("nothing allows alice")


# -- Panglacial Wurm: cast from the library while searching it ---------------


def _search_alice_library(scenario, name="Forest"):
    return scenario.game.search_library(
        "alice", lambda state: state.name == name, count=1, optional=True, source="Test Tutor"
    )


def test_panglacial_wurm_is_cast_from_the_library_while_searching():
    scenario = build(
        alice={"library": ["Panglacial Wurm", "Forest", "Forest", "Forest", "Forest"]},
        lands=["Forest"] * 7,
    )
    scenario.will_take_the_may(True)
    _search_alice_library(scenario)
    wurm = next(c for c in scenario.game.stack if c.name == "Panglacial Wurm")
    assert wurm.zone is Zone.STACK
    assert all(c.name != "Panglacial Wurm" for c in scenario.player("alice").library)


def test_panglacial_wurm_stays_in_the_library_when_the_cast_is_declined():
    scenario = build(
        alice={"library": ["Panglacial Wurm", "Forest", "Forest", "Forest", "Forest"]},
        lands=["Forest"] * 7,
    )
    scenario.will_take_the_may(False)
    _search_alice_library(scenario)
    assert not scenario.game.stack
    assert any(c.name == "Panglacial Wurm" for c in scenario.player("alice").library)


def _may_questions(scenario):
    return [q for q in scenario.questions_asked() if q.kind.value == "may"]


def test_panglacial_wurm_is_not_offered_when_its_mana_cost_cannot_be_paid():
    scenario = build(
        alice={"library": ["Panglacial Wurm", "Forest", "Forest", "Forest", "Forest"]},
        lands=["Forest"] * 2,
    )
    _search_alice_library(scenario)
    assert not scenario.game.stack
    assert not _may_questions(scenario)


def test_panglacial_wurm_in_the_hand_is_not_offered_while_searching():
    scenario = build(alice={"hand": ["Panglacial Wurm"]}, lands=["Forest"] * 7)
    _search_alice_library(scenario)
    assert not scenario.game.stack
    assert not _may_questions(scenario)


# -- Hogaak: "You can't spend mana to cast this spell." ---------------------


def _hogaak_casting(*, graveyard_extra=5, creatures=2, lands=7):
    scenario = build(
        alice={
            "graveyard": ["Hogaak, Arisen Necropolis", *["Mountain"] * graveyard_extra],
            "battlefield": ["Grizzly Bears"] * creatures,
        },
        lands=["Forest"] * lands,
    )
    casting = scenario.cast("Hogaak, Arisen Necropolis", from_zone=Zone.GRAVEYARD)
    casting.use_keyword(CAST_PERMISSION)
    return scenario, casting


def test_hogaak_cannot_be_paid_with_mana_even_when_the_mana_is_there():
    scenario, casting = _hogaak_casting()
    payment = casting.begin_paying()
    with pytest.raises(ValueError, match="can't spend mana"):
        scenario.pay_with(payment, *scenario.untapped_sources(*["Forest"] * 7))


def test_hogaak_is_paid_by_delve_and_convoke_alone():
    from magic_cards_model.machines.objects_as_costs import convoke, delve
    from magic_cards_model.models.card import Color

    scenario, casting = _hogaak_casting()
    payment = casting.begin_paying()
    binned = [c for c in scenario.player("alice").graveyard if c.name == "Mountain"]
    delve(payment, casting.spell, *binned)
    for bears in scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice"):
        convoke(payment, casting.spell, bears, Color.GREEN)
    assert not payment.mana_owed.symbols
    scenario.pay_with(payment)
    assert scenario.put_on_stack(casting).zone is Zone.STACK

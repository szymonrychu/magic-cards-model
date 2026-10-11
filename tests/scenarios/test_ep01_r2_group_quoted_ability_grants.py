"""Scenario: a static ability that hands a whole group a quoted ability
(EP-01 round 2, task T5).

"Elves you control have "{T}: Add {B}."" (Tyvar Kell), "Each creature you
control with a counter on it has "{T}: Add {G}."" (Rishkar, Peema Renegade),
"Sliver creatures you control have "..."" (Manaweft / Hollowhead / Tempered
Sliver), "All Sliver creatures have "..."" (Vampiric / Fungus Sliver), "All
artifacts have "..."" (Kataki, War's Wage), "Treasures you control have "..""
(Goldspan Dragon), "Other Caves you control have "..."" (Forgotten Monument),
"Other permanents you control have "..."" (A Realm Reborn), and so on.

The rules:

- CR 113.10a / CR 613.1f - the grant is a layer 6 effect and gives the object
  the ability itself: a mana ability really taps for mana, an activated one
  really activates, a triggered one really triggers.
- CR 611.3a - a static ability's group is not locked in: an object that stops
  matching (loses its counter, stops being an Elf) stops having the ability,
  and one that starts matching gets it.
- CR 604.2 - the ability is only active while its source is on the battlefield.
- CR 113.3d - a static ability creates a continuous effect; "you control"
  limits the group to one player's objects, "All" does not, "Other" leaves the
  source itself out.

A creature outside the group gets nothing (the negative of every family).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario


def chars(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def find_all(scenario: Scenario, name: str, username: str):
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and state.controller == username
    ]


def granted_index(scenario: Scenario, permanent, text: str) -> int:
    assert text in chars(scenario, permanent).abilities, chars(scenario, permanent).abilities
    (index,) = [
        i
        for i, ability in enumerate(scenario.game.activated_abilities(permanent))
        if f"{ability.cost}: {ability.effect}" == text
    ]
    return index


def board(
    alice: list[str],
    bob: list[str] | None = None,
    *,
    step: Step = Step.PRECOMBAT_MAIN,
    **alice_zones,
):
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, **alice_zones)
        .player("bob", battlefield=bob or [])
        .build()
    )
    scenario.start_at(step)
    return scenario


# --------------------------------------------------------------------------
# One table for every card: members get the text, others do not
# --------------------------------------------------------------------------

#: source, text, members (alice), non-members (alice), bob's objects that must
#: get it (empty for "you control" groups), bob's objects that must not.
GROUPS = [
    ("Tyvar Kell", "{T}: Add {B}.", ["Llanowar Elves"], ["Grizzly Bears"], [], ["Llanowar Elves"]),
    (
        "Path of Annihilation",
        "{T}: Add one mana of any color.",
        ["Eldrazi Mimic"],
        ["Grizzly Bears"],
        [],
        ["Eldrazi Mimic"],
    ),
    (
        "Clement, the Worrywort",
        "{T}: Add {G} or {U}. Spend this mana only to cast a creature spell.",
        ["Clement, the Worrywort"],
        ["Grizzly Bears"],
        [],
        [],
    ),
    (
        "Katilda, Dawnhart Prime",
        "{T}: Add one mana of any of this creature's colors.",
        ["Katilda, Dawnhart Prime", "Laboratory Maniac"],
        ["Grizzly Bears"],
        [],
        ["Laboratory Maniac"],
    ),
    (
        "Sachi, Daughter of Seshiro",
        "{T}: Add {G}{G}.",
        ["Sachi, Daughter of Seshiro"],
        ["Grizzly Bears"],
        [],
        [],
    ),
    (
        "Great Divide Guide",
        "{T}: Add one mana of any color.",
        ["Great Divide Guide", "Forest"],
        ["Grizzly Bears"],
        [],
        ["Forest"],
    ),
    (
        "A Realm Reborn",
        "{T}: Add one mana of any color.",
        ["Forest", "Grizzly Bears"],
        [],
        [],
        ["Forest", "Grizzly Bears"],
    ),
    (
        "Forgotten Monument",
        "{T}, Pay 1 life: Add one mana of any color.",
        ["Sunken Citadel"],
        ["Forest", "Forgotten Monument"],
        [],
        ["Sunken Citadel"],
    ),
    (
        "Resplendent Mentor",
        "{T}: You gain 1 life.",
        ["Resplendent Mentor", "Mother of Runes"],
        ["Grizzly Bears"],
        [],
        ["Mother of Runes"],
    ),
    (
        "Manaweft Sliver",
        "{T}: Add one mana of any color.",
        ["Manaweft Sliver", "Scuttling Sliver"],
        ["Grizzly Bears"],
        [],
        ["Scuttling Sliver"],
    ),
    (
        "Hollowhead Sliver",
        "{T}, Discard a card: Draw a card.",
        ["Hollowhead Sliver", "Scuttling Sliver"],
        ["Grizzly Bears"],
        [],
        ["Scuttling Sliver"],
    ),
    (
        "Tempered Sliver",
        "Whenever this creature deals combat damage to a player, put a +1/+1 counter on it.",
        ["Tempered Sliver", "Scuttling Sliver"],
        ["Grizzly Bears"],
        [],
        ["Scuttling Sliver"],
    ),
    (
        "Vampiric Sliver",
        "Whenever a creature dealt damage by this creature this turn dies, "
        "put a +1/+1 counter on this creature.",
        ["Vampiric Sliver", "Scuttling Sliver"],
        ["Grizzly Bears"],
        ["Scuttling Sliver"],
        [],
    ),
    (
        "Fungus Sliver",
        "Whenever this creature is dealt damage, put a +1/+1 counter on it.",
        ["Fungus Sliver", "Scuttling Sliver"],
        ["Grizzly Bears"],
        ["Scuttling Sliver"],
        [],
    ),
    (
        "Kataki, War's Wage",
        "At the beginning of your upkeep, sacrifice this artifact unless you pay {1}.",
        ["Bonesplitter"],
        ["Forest", "Grizzly Bears"],
        ["Bonesplitter"],
        [],
    ),
    (
        "Magus of the Tabernacle",
        "At the beginning of your upkeep, sacrifice this creature unless you pay {1}.",
        ["Grizzly Bears", "Magus of the Tabernacle"],
        ["Forest", "Bonesplitter"],
        ["Grizzly Bears"],
        [],
    ),
    (
        "Proud Wildbonder",
        "You may have this creature assign its combat damage as though it weren't blocked.",
        ["Proud Wildbonder"],
        ["Grizzly Bears"],
        [],
        [],
    ),
    (
        "Cursed Wombat",
        "Whenever one or more +1/+1 counters are put on this permanent, "
        "put an additional +1/+1 counter on it. This ability triggers only once each turn.",
        ["Forest", "Grizzly Bears", "Cursed Wombat"],
        [],
        [],
        ["Forest", "Grizzly Bears"],
    ),
]


@pytest.mark.parametrize(
    ("source", "text", "members", "outsiders", "bobs_members", "bobs_outsiders"),
    GROUPS,
    ids=[row[0] for row in GROUPS],
)
def test_the_group_has_the_quoted_ability_and_nobody_else_does(
    source, text, members, outsiders, bobs_members, bobs_outsiders
):
    alice = [source, *[name for name in [*members, *outsiders] if name != source]]
    bob = [*bobs_members, *[name for name in bobs_outsiders if name not in bobs_members]]
    scenario = board(alice, bob)

    for name in members:
        for permanent in find_all(scenario, name, "alice"):
            if name == "Forgotten Monument":
                continue
            assert text in chars(scenario, permanent).abilities, (name, "should have the ability")
    for name in outsiders:
        for permanent in find_all(scenario, name, "alice"):
            assert text not in chars(scenario, permanent).abilities, (name, "must not")
    for name in bobs_members:
        for permanent in find_all(scenario, name, "bob"):
            assert text in chars(scenario, permanent).abilities, (name, "(bob) should have it")
    for name in bobs_outsiders:
        for permanent in find_all(scenario, name, "bob"):
            assert text not in chars(scenario, permanent).abilities, (name, "(bob) must not")


def test_other_leaves_the_source_itself_out():
    """CR 113.3d + "Other": A Realm Reborn and Forgotten Monument do not grant
    the ability to themselves."""
    scenario = board(["A Realm Reborn", "Forest"])
    realm = find_all(scenario, "A Realm Reborn", "alice")[0]
    assert "{T}: Add one mana of any color." not in chars(scenario, realm).abilities
    monument = board(["Forgotten Monument", "Sunken Citadel"])
    itself = find_all(monument, "Forgotten Monument", "alice")[0]
    assert "{T}, Pay 1 life: Add one mana of any color." not in chars(monument, itself).abilities


def test_the_grant_goes_when_the_source_leaves_the_battlefield():
    scenario = board(["Tyvar Kell", "Llanowar Elves"])
    elves = find_all(scenario, "Llanowar Elves", "alice")[0]
    tyvar = find_all(scenario, "Tyvar Kell", "alice")[0]
    assert "{T}: Add {B}." in chars(scenario, elves).abilities
    scenario.game.put_into_graveyard(tyvar)
    assert "{T}: Add {B}." not in chars(scenario, elves).abilities
    assert "{T}: Add {B}." not in [
        f"{a.cost}: {a.effect}" for a in scenario.game.activated_abilities(elves)
    ], "the stored granted line goes too (CR 604.2)"


# --------------------------------------------------------------------------
# Granted mana abilities really tap for mana
# --------------------------------------------------------------------------


def test_tyvar_kell_elves_tap_for_black():
    scenario = board(["Tyvar Kell", "Llanowar Elves", "Grizzly Bears"], ["Llanowar Elves"])
    elves = find_all(scenario, "Llanowar Elves", "alice")[0]
    index = granted_index(scenario, elves, "{T}: Add {B}.")
    scenario.activate(elves, index=index)
    assert elves.tapped
    assert scenario.player("alice").mana_pool.floating == {Color.BLACK: 1}
    bobs = find_all(scenario, "Llanowar Elves", "bob")[0]
    assert not any(
        f"{a.cost}: {a.effect}" == "{T}: Add {B}." for a in scenario.game.activated_abilities(bobs)
    ), "'you control': the opponent's Elf has no black mana"


def test_joraga_treespeaker_grants_only_at_level_five():
    low = board(["Joraga Treespeaker", "Llanowar Elves"])
    joraga = find_all(low, "Joraga Treespeaker", "alice")[0]
    joraga.add_counters("level", 1)
    elves = find_all(low, "Llanowar Elves", "alice")[0]
    assert "{T}: Add {G}{G}." not in chars(low, elves).abilities

    high = board(["Joraga Treespeaker", "Llanowar Elves"])
    joraga = find_all(high, "Joraga Treespeaker", "alice")[0]
    joraga.add_counters("level", 5)
    elves = find_all(high, "Llanowar Elves", "alice")[0]
    index = granted_index(high, elves, "{T}: Add {G}{G}.")
    high.activate(elves, index=index)
    assert high.player("alice").mana_pool.floating == {Color.GREEN: 2}


@pytest.mark.parametrize(
    ("source", "text", "counter"),
    [
        ("Rishkar, Peema Renegade", "{T}: Add {G}.", "charge"),
        ("Jiang Yanggu, Wildcrafter", "{T}: Add one mana of any color.", "+1/+1"),
    ],
)
def test_a_creature_with_a_counter_has_the_mana_ability_until_the_counter_goes(
    source, text, counter
):
    scenario = board([source, "Grizzly Bears", "Grizzly Bears"])
    bears, elves = find_all(scenario, "Grizzly Bears", "alice")
    assert text not in chars(scenario, bears).abilities, "no counter yet"
    bears.add_counters(counter if source.startswith("Rishkar") else "+1/+1", 1)
    assert text in chars(scenario, bears).abilities
    assert text not in chars(scenario, elves).abilities
    bears.remove_counters(counter if source.startswith("Rishkar") else "+1/+1", 1)
    assert text not in chars(scenario, bears).abilities, "CR 611.3a: not locked in"


def test_jiang_yanggu_wants_a_plus_one_counter_specifically():
    scenario = board(["Jiang Yanggu, Wildcrafter", "Grizzly Bears"])
    bears = find_all(scenario, "Grizzly Bears", "alice")[0]
    bears.add_counters("charge", 1)
    assert "{T}: Add one mana of any color." not in chars(scenario, bears).abilities


def test_night_of_the_sweets_revenge_foods_tap_for_green():
    scenario = board(["Night of the Sweets' Revenge"])
    (food,) = create_predefined_tokens(scenario.game, "Food", "alice")
    index = granted_index(scenario, food, "{T}: Add {G}.")
    scenario.activate(food, index=index)
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}


def test_goldspan_dragon_treasures_make_two_mana_of_one_colour():
    scenario = board(["Goldspan Dragon"])
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", "alice")
    text = "{T}, Sacrifice this artifact: Add two mana of any one color."
    index = granted_index(scenario, treasure, text)
    scenario.activate(treasure, index=index, color=Color.RED)
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 2}
    assert treasure.zone is not Zone.BATTLEFIELD, "sacrificed as part of the cost"


def test_clement_frog_mana_is_restricted_to_creature_spells():
    scenario = board(["Clement, the Worrywort"])
    clement = find_all(scenario, "Clement, the Worrywort", "alice")[0]
    text = "{T}: Add {G} or {U}. Spend this mana only to cast a creature spell."
    index = granted_index(scenario, clement, text)
    scenario.activate(clement, index=index, color=Color.GREEN)
    (restricted,) = scenario.player("alice").mana_pool.restricted
    assert restricted.restriction.understood is True


def test_resplendent_mentor_white_creatures_gain_life():
    scenario = board(["Resplendent Mentor", "Mother of Runes"])
    mother = find_all(scenario, "Mother of Runes", "alice")[0]
    index = granted_index(scenario, mother, "{T}: You gain 1 life.")
    life = scenario.player("alice").life
    scenario.activate(mother, index=index)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == life + 1


def test_hollowhead_sliver_slivers_can_loot_by_discarding():
    scenario = board(["Hollowhead Sliver", "Scuttling Sliver"], hand=["Forest"], library=["Island"])
    sliver = find_all(scenario, "Scuttling Sliver", "alice")[0]
    index = granted_index(scenario, sliver, "{T}, Discard a card: Draw a card.")
    (forest,) = scenario.player("alice").hand
    scenario.activate(sliver, index=index, discarding=[forest])
    scenario.pass_until_resolved()
    assert [card.name for card in scenario.player("alice").hand] == ["Island"]


# --------------------------------------------------------------------------
# Granted triggered abilities really trigger
# --------------------------------------------------------------------------


def test_tempered_sliver_grants_a_counter_on_combat_damage_to_a_player():
    scenario = board(["Tempered Sliver", "Scuttling Sliver"], ["Forest"])
    sliver = find_all(scenario, "Scuttling Sliver", "alice")[0]
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(sliver, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert sliver.counter_count("+1/+1") == 1


def test_tempered_sliver_trigger_is_not_given_to_an_opponents_sliver():
    scenario = board(["Tempered Sliver"], ["Scuttling Sliver"])
    bobs = find_all(scenario, "Scuttling Sliver", "bob")[0]
    assert not any(
        "Whenever this creature deals combat damage" in a for a in chars(scenario, bobs).abilities
    )


def next_upkeep(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # untap
    scenario.advance()  # upkeep


def upkeep_board(alice: list[str], bob: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice, library=["Forest"] * 6)
        .player("bob", battlefield=bob, library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_kataki_makes_every_artifact_cost_upkeep_mana_or_be_sacrificed():
    """ "All artifacts": the opponent's Bonesplitter has the granted trigger on
    *its* controller's upkeep, and declining the {1} sacrifices it."""
    scenario = upkeep_board(["Kataki, War's Wage", "Bonesplitter"], ["Bonesplitter"])
    bobs = find_all(scenario, "Bonesplitter", "bob")[0]
    next_upkeep(scenario)  # bob's upkeep
    assert scenario.stack_names() == ["Bonesplitter's triggered ability"]
    scenario.will_pay_the_mana_cost(False, username="bob")
    scenario.pass_until_resolved()
    assert bobs.zone is Zone.GRAVEYARD, "unpaid: sacrificed"
    assert find_all(scenario, "Bonesplitter", "alice")[0].zone is Zone.BATTLEFIELD


def test_kataki_gives_nothing_to_a_nonartifact():
    scenario = upkeep_board(["Kataki, War's Wage"], ["Grizzly Bears"])
    next_upkeep(scenario)
    assert scenario.stack_names() == []


def test_magus_of_the_tabernacle_sacrifice_unless_pay_resolves():
    scenario = upkeep_board(["Magus of the Tabernacle"], ["Grizzly Bears", "Forest"])
    bears = find_all(scenario, "Grizzly Bears", "bob")[0]
    next_upkeep(scenario)  # bob's upkeep: the Bears have it, the Magus's is alice's
    assert scenario.stack_names() == ["Grizzly Bears's triggered ability"]
    forest = find_all(scenario, "Forest", "bob")[0]
    scenario.will_pay_the_mana_cost(True, username="bob", sources=[forest])
    scenario.pass_until_resolved()
    assert bears.zone is Zone.BATTLEFIELD, "paid {1}: kept"
    assert forest.tapped


def test_cursed_wombat_gives_every_permanent_the_extra_counter_trigger():
    scenario = board(["Cursed Wombat", "Grizzly Bears"])
    bears = find_all(scenario, "Grizzly Bears", "alice")[0]
    bears.add_counters("+1/+1", 1)
    scenario.game.put_triggers_on_stack()
    texts = chars(scenario, bears).abilities
    assert any("put an additional +1/+1 counter" in text for text in texts)

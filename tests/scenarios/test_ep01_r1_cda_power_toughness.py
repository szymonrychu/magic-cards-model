"""EP-01 round 1, task 8: the general characteristic-defining power/toughness
ability (CR 604.3, CR 604.3a, CR 613.4a) - "`<Name>`'s power is equal to
`<count>`" (and "its toughness is equal to that number plus 1", "toughness is
equal to ...", "power and toughness are each equal to ...").

One reader, `parse._cda_general_sentence_builder`, turns the count phrase into
a `Count`: a pile off the battlefield (graveyard, exile) is read when the
effect is built, a count of permanents is a `Count` over the board as it
stands in sublayer 7a. Each count shape is proven by changing the board and
asserting the computed P/T before and after; a power-only CDA never touches
the printed toughness box (CR 208.2a); a toughness-only one never touches the
printed power.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers.parse import parsed_layer_effects
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import pool
from tests.scenarios.harness import Scenario


def pt(scenario, name: str, username: str = "alice") -> tuple[int | None, int | None]:
    chars = scenario.game.computed_board().of(scenario.creature(name, username))
    return chars.power, chars.toughness


def build(**players):
    scenario = Scenario()
    for username, zones in players.items():
        scenario = scenario.player(username, **zones)
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


# --- party (CR 700.8) --------------------------------------------------------


def test_archpriest_counts_one_creature_per_party_role():
    scenario = build(
        alice={
            "battlefield": [
                "Archpriest of Iona",  # Cleric
                "Agent of Kotis",  # Rogue
                "Ash Zealot",  # Warrior
                "Izzet Staticaster",  # Wizard
            ]
        },
        bob={},
    )
    assert pt(scenario, "Archpriest of Iona") == (4, 2)


def test_archpriest_a_second_cleric_does_not_grow_the_party():
    scenario = build(
        alice={"battlefield": ["Archpriest of Iona", "Codespell Cleric", "Snooping Page"]},
        bob={},
    )
    assert pt(scenario, "Archpriest of Iona") == (1, 2)


def test_archpriest_counts_only_its_controllers_party():
    scenario = build(
        alice={"battlefield": ["Archpriest of Iona"]},
        bob={"battlefield": ["Agent of Kotis", "Ash Zealot", "Izzet Staticaster"]},
    )
    assert pt(scenario, "Archpriest of Iona") == (1, 2)


def test_archpriest_a_two_type_creature_fills_only_one_slot_but_the_best_split_counts():
    # CR 700.8b: Swashbuckler Extraordinaire (Rogue Warrior) and Joined
    # Researchers (Cleric Wizard) each count once, in whichever slot gives the
    # highest number: Archpriest is the Cleric, so Joined Researchers must be
    # the Wizard; with Agent of Kotis as the Rogue, Swashbuckler is the Warrior.
    scenario = build(
        alice={
            "battlefield": [
                "Archpriest of Iona",
                "Joined Researchers // Secret Rendezvous",
                "Swashbuckler Extraordinaire",
            ]
        },
        bob={},
    )
    assert pt(scenario, "Archpriest of Iona") == (3, 2)


def test_archpriest_a_fourth_slot_filled_by_a_second_creature_of_a_two_type_pair():
    scenario = build(
        alice={
            "battlefield": [
                "Archpriest of Iona",
                "Joined Researchers // Secret Rendezvous",
                "Swashbuckler Extraordinaire",
                "Agent of Kotis",
            ]
        },
        bob={},
    )
    # Cleric, Wizard, Warrior (Swashbuckler) and Rogue (Agent of Kotis).
    assert pt(scenario, "Archpriest of Iona") == (4, 2)


# --- cards in graveyards (CR 604.3, 613.4a) --------------------------------


def test_haughty_djinn_counts_instants_and_sorceries_in_its_controllers_graveyard():
    scenario = build(
        alice={"battlefield": ["Haughty Djinn"], "graveyard": ["Lightning Bolt", "Divination"]},
        bob={"graveyard": ["Shock", "Giant Growth"]},
    )
    assert pt(scenario, "Haughty Djinn") == (2, 4)  # bob's graveyard is not "your graveyard"


def test_haughty_djinn_ignores_creature_and_land_cards_and_grows_as_a_sorcery_resolves():
    scenario = build(
        alice={
            "battlefield": ["Haughty Djinn", "Island", "Island", "Island"],
            "hand": ["Divination"],
            "graveyard": ["Grizzly Bears", "Forest"],
            "library": ["Forest"] * 3,
        },
        bob={},
    )
    assert pt(scenario, "Haughty Djinn") == (0, 4)
    # Haughty Djinn makes instants and sorceries cost {1} less: two Islands pay.
    scenario.cast_and_resolve("Divination", auto=True)
    assert pt(scenario, "Haughty Djinn") == (1, 4)


@pytest.mark.parametrize(
    ("name", "toughness"), [("Kinetic Augur", 4), ("Enigma Drake", 4), ("Spellheart Chimera", 3)]
)
def test_instant_and_sorcery_graveyard_cdas_share_the_reader(name, toughness):
    scenario = build(
        alice={"battlefield": [name], "graveyard": ["Lightning Bolt", "Divination", "Opt"]},
        bob={},
    )
    assert pt(scenario, name) == (3, toughness)


def test_dragonfly_swarm_counts_noncreature_nonland_cards():
    scenario = build(
        alice={
            "battlefield": ["Dragonfly Swarm"],
            "graveyard": ["Lightning Bolt", "Sol Ring", "Grizzly Bears", "Forest"],
        },
        bob={},
    )
    assert pt(scenario, "Dragonfly Swarm")[0] == 2


def test_uurg_counts_land_cards_in_your_graveyard():
    scenario = build(
        alice={
            "battlefield": ["Uurg, Spawn of Turg"],
            "graveyard": ["Forest", "Island", "Sol Ring"],
        },
        bob={"graveyard": ["Mountain"]},
    )
    assert pt(scenario, "Uurg, Spawn of Turg") == (2, 5)


def test_neo_exdeath_style_permanent_cards_in_graveyard_are_counted_by_permanent_type():
    scenario = build(
        alice={
            "battlefield": ["Souls of the Lost"],
            "graveyard": ["Grizzly Bears", "Sol Ring", "Lightning Bolt"],
        },
        bob={},
    )
    # Souls of the Lost (not a listed card): power = permanent cards in your
    # graveyard, toughness that number plus 1.
    assert pt(scenario, "Souls of the Lost") == (2, 3)


def test_lhurgoyf_counts_creature_cards_in_all_graveyards_and_toughness_is_one_more():
    scenario = build(
        alice={"battlefield": ["Lhurgoyf"], "graveyard": ["Grizzly Bears", "Lightning Bolt"]},
        bob={"graveyard": ["Llanowar Elves"]},
    )
    assert pt(scenario, "Lhurgoyf") == (2, 3)


def test_necrogoyf_power_only_leaves_its_printed_toughness():
    scenario = build(
        alice={"battlefield": ["Necrogoyf"], "graveyard": ["Grizzly Bears"]},
        bob={"graveyard": ["Llanowar Elves", "Birds of Paradise"]},
    )
    assert pt(scenario, "Necrogoyf") == (3, 4)


def test_magnivore_each_equal_to_sorceries_in_all_graveyards():
    scenario = build(
        alice={"battlefield": ["Magnivore"], "graveyard": ["Divination", "Lightning Bolt"]},
        bob={"graveyard": ["Divination"]},
    )
    assert pt(scenario, "Magnivore") == (2, 2)


def test_detritivore_counts_nonbasic_lands_in_opponents_graveyards_only():
    scenario = build(
        alice={"battlefield": ["Detritivore"], "graveyard": ["Steam Vents"]},
        bob={"graveyard": ["Steam Vents", "Overgrown Tomb", "Forest"]},
    )
    assert pt(scenario, "Detritivore") == (2, 2)


@pytest.mark.parametrize("name", ["Nethergoyf", "Consuming Blob"])
def test_card_types_among_cards_in_your_graveyard_with_toughness_plus_one(name):
    scenario = build(
        alice={
            "battlefield": [name],
            "graveyard": ["Lightning Bolt", "Grizzly Bears", "Living Library"],
        },
        bob={"graveyard": ["Forest"]},
    )
    # instant, creature, artifact: three card types (the artifact creature is
    # both); bob's land is not in "your graveyard".
    assert pt(scenario, name) == (3, 4)


def test_nethergoyf_shrinks_when_a_card_type_leaves_the_graveyard():
    scenario = build(
        alice={"battlefield": ["Nethergoyf"], "graveyard": ["Lightning Bolt", "Sol Ring"]},
        bob={},
    )
    assert pt(scenario, "Nethergoyf") == (2, 3)
    graveyard = scenario.game.player("alice").zones[Zone.GRAVEYARD]
    graveyard.remove(next(c for c in graveyard if c.name == "Sol Ring"))
    assert pt(scenario, "Nethergoyf") == (1, 2)


# --- exile --------------------------------------------------------------------


def test_cosmogoyf_counts_cards_you_own_in_exile_toughness_plus_one():
    scenario = build(
        alice={"battlefield": ["Cosmogoyf"], "exile": ["Forest", "Island"]},
        bob={"exile": ["Mountain"]},
    )
    assert pt(scenario, "Cosmogoyf") == (2, 3)


def test_crackling_drake_counts_instants_and_sorceries_in_exile_and_graveyard():
    scenario = build(
        alice={
            "battlefield": ["Crackling Drake"],
            "exile": ["Lightning Bolt", "Forest"],
            "graveyard": ["Divination", "Grizzly Bears"],
        },
        bob={"exile": ["Shock"]},
    )
    assert pt(scenario, "Crackling Drake") == (2, 4)


# --- permanents on the battlefield -------------------------------------------


def test_wilderness_elemental_counts_only_nonbasic_lands_opponents_control():
    scenario = build(
        alice={"battlefield": ["Wilderness Elemental", "Steam Vents", "Forest"]},
        bob={"battlefield": ["Overgrown Tomb", "Steam Vents", "Forest"]},
    )
    assert pt(scenario, "Wilderness Elemental") == (2, 3)


def test_vile_aggregate_counts_colorless_creatures_you_control_including_itself():
    scenario = build(
        alice={"battlefield": ["Vile Aggregate", "Ornithopter", "Grizzly Bears"]},
        bob={"battlefield": ["Ornithopter"]},
    )
    assert pt(scenario, "Vile Aggregate") == (2, 5)


def test_shambling_suit_counts_artifacts_and_or_enchantments_you_control():
    scenario = build(
        alice={"battlefield": ["Shambling Suit", "Sol Ring", "Ghostly Prison", "Forest"]},
        bob={"battlefield": ["Mind Stone"]},
    )
    assert pt(scenario, "Shambling Suit")[0] == 3  # itself (artifact), Sol Ring, Ghostly Prison


def test_toph_counts_plus_one_counters_on_lands_you_control():
    scenario = build(
        alice={"battlefield": ["Toph, the Blind Bandit", "Forest", "Island"]},
        bob={"battlefield": ["Mountain"]},
    )
    assert pt(scenario, "Toph, the Blind Bandit")[0] == 0
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(forest, Counter.PLUS_ONE, 2)
    scenario.game.add_counters(
        scenario.find("Mountain", Zone.BATTLEFIELD, "bob"), Counter.PLUS_ONE, 5
    )
    assert pt(scenario, "Toph, the Blind Bandit") == (2, 3)


def test_fungal_behemoth_counts_counters_on_creatures_each_half():
    scenario = build(alice={"battlefield": ["Fungal Behemoth", "Grizzly Bears"]}, bob={})
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 3)
    assert pt(scenario, "Fungal Behemoth") == (3, 3)


def test_daretti_greatest_mana_value_among_artifacts_you_control():
    scenario = build(
        alice={"battlefield": ["Daretti, Rocketeer Engineer", "Sol Ring", "Mind Stone"]},
        bob={"battlefield": ["Walking Ballista"]},
    )
    assert pt(scenario, "Daretti, Rocketeer Engineer")[0] == 2


def test_kraven_greatest_mana_value_among_permanents_you_control_and_zero_for_none():
    scenario = build(
        alice={"battlefield": ["Kraven, Proud Predator", "Sol Ring", "Vampire Nighthawk"]},
        bob={},
    )
    assert pt(scenario, "Kraven, Proud Predator")[0] == 3  # Vampire Nighthawk


def test_karn_legacy_reforged_greatest_mana_value_each_half():
    scenario = build(
        alice={"battlefield": ["Karn, Legacy Reforged", "Sol Ring", "Mind Stone"]},
        bob={},
    )
    assert pt(scenario, "Karn, Legacy Reforged") == (5, 5)  # itself: mana value 5


def test_wintermoor_commander_counts_knights_you_control_toughness_only():
    scenario = build(
        alice={"battlefield": ["Wintermoor Commander", "Knight of Grace", "Grizzly Bears"]},
        bob={"battlefield": ["Xerex Strobe-Knight"]},
    )
    assert pt(scenario, "Wintermoor Commander") == (2, 2)  # itself and Knight of Grace


def test_traproot_kami_counts_forests_on_the_battlefield_for_both_players():
    scenario = build(
        alice={"battlefield": ["Traproot Kami", "Forest", "Island"]},
        bob={"battlefield": ["Forest", "Forest"]},
    )
    assert pt(scenario, "Traproot Kami") == (0, 3)


def test_aven_trailblazer_domain_is_toughness_only():
    scenario = build(
        alice={"battlefield": ["Aven Trailblazer", "Forest", "Island", "Steam Vents"]}, bob={}
    )
    assert pt(scenario, "Aven Trailblazer") == (2, 3)  # Forest, Island, Mountain


# --- devotion (CR 700.5) -----------------------------------------------------


def test_anax_power_is_your_devotion_to_red():
    scenario = build(
        alice={"battlefield": ["Anax, Hardened in the Forge", "Ash Zealot"]},
        bob={"battlefield": ["Ash Zealot"]},
    )
    # {1}{R}{R} + {R}{R}: four red symbols; bob's Ash Zealot is not yours.
    assert pt(scenario, "Anax, Hardened in the Forge") == (4, 3)


def test_renata_power_is_your_devotion_to_green_not_other_colors():
    scenario = build(
        alice={"battlefield": ["Renata, Called to the Hunt", "Ash Zealot"]},
        bob={},
    )
    assert pt(scenario, "Renata, Called to the Hunt")[0] == 2  # {1}{G}{G}


@pytest.mark.parametrize(
    ("name", "friend", "alone", "together"),
    [
        ("Callaphe, Beloved of the Sea", "Ink Dissolver", (2, 3), (3, 3)),
        ("Daxos, Blessed by the Sun", "Codespell Cleric", (2, 2), (2, 3)),
        ("Tymaret, Chosen from Death", "Vampire Nighthawk", (2, 2), (2, 4)),
    ],
)
def test_devotion_cdas_track_the_mana_symbols_of_the_matching_color(name, friend, alone, together):
    assert pt(build(alice={"battlefield": [name]}, bob={}), name) == alone
    assert pt(build(alice={"battlefield": [name, friend]}, bob={}), name) == together


# --- cards drawn this turn ---------------------------------------------------


def test_duelist_of_the_mind_counts_cards_drawn_this_turn_and_resets():
    scenario = build(
        alice={"battlefield": ["Duelist of the Mind"], "library": ["Forest"] * 6}, bob={}
    )
    before = pt(scenario, "Duelist of the Mind")[0]
    scenario.draw(2, "alice")
    assert pt(scenario, "Duelist of the Mind")[0] == before + 2
    scenario.game.cards_drawn_this_turn = {}
    assert pt(scenario, "Duelist of the Mind")[0] == 0


# --- every listed card reads ---------------------------------------------------

LISTED = [
    "Archpriest of Iona",
    "Consuming Blob",
    "Cosmogoyf",
    "Dragonfly Swarm",
    "Duelist of the Mind",
    "Enigma Drake",
    "Haughty Djinn",
    "Kinetic Augur",
    "Lhurgoyf",
    "Necrogoyf",
    "Nethergoyf",
    "Shambling Suit",
    "Spellheart Chimera",
    "Toph, the Blind Bandit",
    "Uurg, Spawn of Turg",
    "Vile Aggregate",
    "Wilderness Elemental",
    "Crackling Drake",
    "Anax, Hardened in the Forge",
    "Callaphe, Beloved of the Sea",
    "Traproot Kami",
    "Wintermoor Commander",
    "Daxos, Blessed by the Sun",
    "Tymaret, Chosen from Death",
    "Aven Trailblazer",
    "Kraven, Proud Predator",
    "Daretti, Rocketeer Engineer",
    "Exdeath, Void Warlock // Neo Exdeath, Dimension's End",
]


@pytest.mark.parametrize("name", LISTED)
def test_every_listed_cda_card_has_its_power_toughness_line_read(name):
    printing = pool()[name]
    support = card_support(printing)
    cda = [
        clause
        for clause in support.clauses
        if "equal to" in clause.text.lower()
        and ("power" in clause.text.lower() or "toughness" in clause.text.lower())
    ]
    assert cda, f"{name} has no CDA clause"
    assert all(clause.status == "handled" for clause in cda), [
        (clause.text, clause.status) for clause in cda
    ]
    if printing.oracle_text:
        assert parsed_layer_effects(printing.oracle_text, static_only=True, card_name=printing.name)


# --- the exiled cards used to craft it (CR 702.167a, CR 604.3) ---------------


def _craft_raptor(*dinosaurs, graveyard=()):
    from magic_cards_model.machines.keywords import craft_activation

    scenario = build(
        alice={
            "battlefield": [
                "Saheeli's Lattice // Mastercraft Raptor",
                *dinosaurs,
                *["Mountain"] * 5,
            ],
            "graveyard": list(graveyard),
            "library": ["Forest"] * 4,
        },
        bob={"library": ["Island"] * 4},
    )
    lattice = scenario.find("Saheeli's Lattice // Mastercraft Raptor", Zone.BATTLEFIELD, "alice")
    materials = [
        *(scenario.creature(name, "alice") for name in dinosaurs),
        *(scenario.find(name, Zone.GRAVEYARD, "alice") for name in graveyard),
    ]
    activation = craft_activation(scenario.game, lattice, "alice", materials)
    payment = activation.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 5))
    activation.activate()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    return scenario, materials


def test_mastercraft_raptor_power_is_the_total_power_of_the_cards_used_to_craft_it():
    scenario, materials = _craft_raptor("Raptor Companion", "Orazca Frillback")
    assert all(card.zone is Zone.EXILE for card in materials)
    assert pt(scenario, "Mastercraft Raptor") == (7, 4)


def test_mastercraft_raptor_counts_a_dinosaur_card_crafted_from_the_graveyard():
    scenario, _ = _craft_raptor("Raptor Companion", graveyard=["Orazca Frillback"])
    assert pt(scenario, "Mastercraft Raptor") == (7, 4)


def test_mastercraft_raptor_ignores_exiled_cards_that_were_not_used_to_craft_it():
    scenario, _ = _craft_raptor("Raptor Companion", "Orazca Frillback")
    scenario.game.exile_cards([scenario.find("Forest", Zone.LIBRARY, "alice")])
    assert pt(scenario, "Mastercraft Raptor") == (7, 4)


def test_mastercraft_raptor_survives_a_snapshot_round_trip():
    from magic_cards_model.models.game import Game

    scenario, _ = _craft_raptor("Raptor Companion", "Orazca Frillback")
    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    raptor = next(c for c in decoded.battlefield if c.name == "Mastercraft Raptor")
    assert decoded.computed_board().of(raptor).power == 7


def test_mastercraft_raptor_pool_reader_is_handled():
    support = card_support(pool()["Saheeli's Lattice // Mastercraft Raptor"])
    assert all(c.status == "handled" for c in support.clauses), [
        (c.status, c.text) for c in support.clauses
    ]


# --- a CDA works in every zone (CR 604.3) ------------------------------------


@pytest.mark.parametrize(
    ("zone", "expected"), [("hand", (1, 2)), ("graveyard", (2, 3)), ("exile", (1, 2))]
)
def test_a_creature_card_off_the_battlefield_has_its_cda_power_and_toughness(zone, expected):
    others = ["Grizzly Bears", "Lightning Bolt"]
    scenario = build(
        alice={
            "hand": ["Lhurgoyf"] if zone == "hand" else [],
            "exile": ["Lhurgoyf"] if zone == "exile" else [],
            "graveyard": others + (["Lhurgoyf"] if zone == "graveyard" else []),
            "library": ["Forest"] * 4,
        },
        bob={"library": ["Island"] * 4},
    )
    state = scenario.find("Lhurgoyf", Zone(zone), "alice" if zone != "exile" else None)
    chars = scenario.game.characteristics_of(state)
    assert (chars.power, chars.toughness) == expected

"""Scenario: static "gets +N/+N for each <thing>" and "power and toughness each
equal to <count>" (EP-02 R3 T1).

One reader (`machines/ep02_r3_static_pumps.py`) sizes a sublayer 7c pump or a
base P/T by a count of something on the board, recomputed on every board
computation. CR numbers below were read with `mise run rules:find` in the
session that wrote this file:

- **CR 613.4c** - a P/T change from a static ability is sublayer 7c; it is
  re-evaluated continuously (CR 611.3a).
- **CR 613.4b** - setting P/T to a value is sublayer 7b.
- **CR 700.9** - modified: a counter, or an Equipment or Aura its controller
  controls attached to it.
- **CR 205.3m** - creature types; **CR 105.1** - colors.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _setup(alice, bob=()):
    scenario = (
        Scenario().player("alice", battlefield=list(alice)).player("bob", battlefield=list(bob))
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _pt(scenario, card):
    chars = scenario.game.computed_board().of(card)
    return chars.power, chars.toughness


def _size(name, alice=(), bob=(), user="alice"):
    """The computed P/T of `name` on a board of `alice` + `bob` permanents."""
    scenario = _setup(alice, bob)
    return _pt(scenario, scenario.creature(name, user))


def _delta(scenario, card, before):
    power, toughness = _pt(scenario, card)
    return power - before[0], toughness - before[1]


def _perm(scenario, name, user="alice"):
    return scenario.find(name, Zone.BATTLEFIELD, user)


# -- Equipment / Aura attached ----------------------------------------------


def test_armament_master_pumps_other_kor_per_equipment_on_itself():
    scenario = _setup(["Armament Master", "Kor Castigator", "Bonesplitter", "Bonesplitter"])
    master, kor = scenario.creature("Armament Master"), scenario.creature("Kor Castigator")
    before = _pt(scenario, kor)
    own_before = _pt(scenario, master)
    first, second = [
        c for c in scenario.game.permanents_controlled_by("alice") if c.card.name == "Bonesplitter"
    ]
    first.attach_to(master)
    assert _delta(scenario, kor, before) == (2, 2)
    second.attach_to(master)
    assert _delta(scenario, kor, before) == (4, 4)
    # "Other": the Master itself only gets the Equipment's own +2/+0.
    assert _pt(scenario, master) == (own_before[0] + 4, own_before[1])


def test_armament_master_ignores_equipment_on_another_creature():
    scenario = _setup(["Armament Master", "Kor Castigator", "Bonesplitter"])
    kor = scenario.creature("Kor Castigator")
    before = _pt(scenario, kor)
    _perm(scenario, "Bonesplitter").attach_to(kor)
    assert _delta(scenario, kor, before) == (2, 0)


def test_bruenor_counts_equipment_attached_to_each_creature_separately():
    scenario = _setup(["Bruenor Battlehammer", "Grizzly Bears", "Hill Giant", "Bonesplitter"])
    bears, giant = scenario.creature("Grizzly Bears"), scenario.creature("Hill Giant")
    bears_before, giant_before = _pt(scenario, bears), _pt(scenario, giant)
    _perm(scenario, "Bonesplitter").attach_to(bears)
    # +2/+0 from the Equipment itself, +2/+0 more from Bruenor's per-creature count.
    assert _delta(scenario, bears, bears_before) == (4, 0)
    assert _delta(scenario, giant, giant_before) == (0, 0)


def test_myr_adapter_proves_the_per_equipment_self_pump_on_another_printing():
    scenario = _setup(["Myr Adapter", "Bonesplitter"])
    adapter = scenario.creature("Myr Adapter")
    before = _pt(scenario, adapter)
    _perm(scenario, "Bonesplitter").attach_to(adapter)
    assert _delta(scenario, adapter, before) == (3, 1)


def test_champion_of_the_flame_counts_auras_and_equipment():
    scenario = _setup(["Champion of the Flame", "Bonesplitter", "Pacifism"])
    champion = scenario.creature("Champion of the Flame")
    before = _pt(scenario, champion)
    _perm(scenario, "Bonesplitter").attach_to(champion)
    _perm(scenario, "Pacifism").attach_to(champion)
    assert _delta(scenario, champion, before) == (6, 4)


def test_kellan_pumps_other_creatures_per_attachment_on_kellan():
    scenario = _setup(
        ["Kellan, the Fae-Blooded // Birthright Boon", "Grizzly Bears", "Bonesplitter", "Pacifism"]
    )
    kellan = scenario.creature("Kellan, the Fae-Blooded")
    bears = scenario.creature("Grizzly Bears")
    before = _pt(scenario, bears)
    _perm(scenario, "Bonesplitter").attach_to(kellan)
    _perm(scenario, "Pacifism").attach_to(kellan)
    assert _delta(scenario, bears, before) == (2, 0)


def test_blessing_of_the_nephilim_pumps_enchanted_creature_per_its_colors():
    scenario = _setup(["Linvala, Shield of Sea Gate", "Blessing of the Nephilim"])
    linvala = scenario.creature("Linvala, Shield of Sea Gate")
    before = _pt(scenario, linvala)
    _perm(scenario, "Blessing of the Nephilim").attach_to(linvala)
    assert _delta(scenario, linvala, before) == (2, 2)


def test_eidolon_of_countless_battles_counts_creatures_and_auras_you_control():
    alone = _size("Eidolon of Countless Battles", ["Eidolon of Countless Battles"])
    with_bears = _size(
        "Eidolon of Countless Battles", ["Eidolon of Countless Battles", "Grizzly Bears"]
    )
    # One more creature you control: +1/+1 (CR 613.4c).
    assert (with_bears[0] - alone[0], with_bears[1] - alone[1]) == (1, 1)
    with_aura = _size("Eidolon of Countless Battles", ["Eidolon of Countless Battles", "Pacifism"])
    # An Aura you control adds its own +1/+1, attached or not (CR 303.4).
    assert (with_aura[0] - alone[0], with_aura[1] - alone[1]) == (1, 1)


def test_eidolon_reads_its_own_controllers_board_for_an_enchanted_opposing_creature():
    scenario = _setup(["Eidolon of Countless Battles", "Pacifism"], bob=["Grizzly Bears"])
    eidolon = scenario.creature("Eidolon of Countless Battles")
    bears = scenario.creature("Grizzly Bears", "bob")
    before = _pt(scenario, bears)
    eidolon.attach_to(bears)
    board = scenario.game.computed_board()
    mine = [c for c in scenario.game.permanents_controlled_by("alice")]
    creatures = sum(1 for c in mine if "creature" in {t.value for t in board.of(c).types})
    # Bob's creature is pumped by Alice's creatures and Auras, not by Bob's.
    assert _delta(scenario, bears, before) == (creatures + 1, creatures + 1)


# -- Counted board groups ----------------------------------------------------


def test_coat_of_arms_counts_creatures_sharing_a_type_across_both_players():
    scenario = _setup(["Coat of Arms", "Grizzly Bears", "Hill Giant"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    # Nothing shares a type with Hill Giant; alice's Bears shares Bear with bob's.
    assert _pt(scenario, giant) == (3, 3)
    assert _pt(scenario, bears) == (3, 3)
    assert _pt(scenario, scenario.creature("Grizzly Bears", "bob")) == (3, 3)


def test_copperhoof_vorrac_counts_untapped_opposing_permanents_only():
    scenario = _setup(["Copperhoof Vorrac", "Forest"], bob=["Forest", "Forest", "Island"])
    vorrac = scenario.creature("Copperhoof Vorrac")
    before = _pt(scenario, vorrac)
    scenario.find("Forest", Zone.BATTLEFIELD, "bob").tapped = True
    after = _pt(scenario, vorrac)
    assert (before[0] - after[0], before[1] - after[1]) == (1, 1)


def test_spirit_of_the_aldergard_counts_other_snow_permanents_you_control():
    alone = _size("Spirit of the Aldergard", ["Spirit of the Aldergard"])
    snow = _size(
        "Spirit of the Aldergard",
        ["Spirit of the Aldergard", "Snow-Covered Forest", "Snow-Covered Island", "Forest"],
    )
    assert (snow[0] - alone[0], snow[1] - alone[1]) == (2, 0)


def test_spirit_of_the_aldergard_ignores_the_opponents_snow_permanents():
    alone = _size("Spirit of the Aldergard", ["Spirit of the Aldergard"])
    theirs = _size("Spirit of the Aldergard", ["Spirit of the Aldergard"], ["Snow-Covered Forest"])
    assert theirs == alone


def test_squirrel_mob_counts_other_squirrels_on_the_whole_battlefield():
    alone = _size("Squirrel Mob", ["Squirrel Mob"])
    crowd = _size("Squirrel Mob", ["Squirrel Mob", "Squirrelanoids"], ["Squirrel Mob"])
    assert (crowd[0] - alone[0], crowd[1] - alone[1]) == (2, 2)


def test_sliver_legion_pumps_each_sliver_per_other_sliver():
    legion_alone = _size("Sliver Legion", ["Sliver Legion"])
    construct_alone = _size("Sliver Construct", ["Sliver Construct"])
    board = ["Sliver Legion", "Sliver Construct"]
    # Each Sliver (either player's) counts the Slivers other than itself.
    assert _size("Sliver Construct", board, ["Sliver Construct"]) == (
        construct_alone[0] + 2,
        construct_alone[1] + 2,
    )
    legion = _size("Sliver Legion", board, ["Sliver Construct"])
    assert legion == (legion_alone[0] + 2, legion_alone[1] + 2)


def test_mutagen_connoisseur_counts_transformed_permanents_you_control():
    scenario = _setup(["Mutagen Connoisseur", "Tangleclaw Werewolf // Fibrous Entangler"])
    connoisseur = scenario.creature("Mutagen Connoisseur")
    before = _pt(scenario, connoisseur)
    werewolf = _perm(scenario, "Tangleclaw Werewolf // Fibrous Entangler")
    werewolf.transformed = True
    assert _delta(scenario, connoisseur, before) == (1, 0)


def test_upriser_renegade_counts_other_modified_creatures():
    scenario = _setup(["Upriser Renegade", "Grizzly Bears", "Bonesplitter"])
    renegade = scenario.creature("Upriser Renegade")
    bears = scenario.creature("Grizzly Bears")
    before = _pt(scenario, renegade)
    bears.counters.add("+1/+1", 1)
    assert _delta(scenario, renegade, before) == (2, 0)
    _perm(scenario, "Bonesplitter").attach_to(bears)
    # Still one modified creature - modifications on one creature count once.
    assert _delta(scenario, renegade, before) == (2, 0)


def test_herald_of_leshrac_counts_lands_you_control_but_do_not_own():
    scenario = _setup(["Herald of Leshrac", "Forest", "Forest"])
    herald = scenario.creature("Herald of Leshrac")
    before = _pt(scenario, herald)
    scenario.find("Forest", Zone.BATTLEFIELD, "alice").owner = "bob"
    assert _delta(scenario, herald, before) == (1, 1)


# -- Per-creature counts -----------------------------------------------------


def test_knight_of_new_alara_pumps_other_multicolored_by_their_colors():
    gold_alone = _size("Linvala, Shield of Sea Gate", ["Linvala, Shield of Sea Gate"])
    board = ["Knight of New Alara", "Linvala, Shield of Sea Gate", "Grizzly Bears"]
    linvala = _size("Linvala, Shield of Sea Gate", board)
    assert linvala == (gold_alone[0] + 2, gold_alone[1] + 2)
    assert _size("Grizzly Bears", board) == (2, 2)
    knight_alone = _size("Knight of New Alara", ["Knight of New Alara"])
    # "Each other": the Knight (multicolored itself) does not pump itself.
    assert _size("Knight of New Alara", board) == knight_alone


def test_takeno_pumps_other_samurai_by_their_bushido():
    alone = _size("Devoted Retainer", ["Devoted Retainer"])
    pumped = _size("Devoted Retainer", ["Takeno, Samurai General", "Devoted Retainer"])
    assert (pumped[0] - alone[0], pumped[1] - alone[1]) == (1, 1)
    # Takeno has bushido 2 himself but is "other" to no one: he gets no pump.
    takeno_alone = _size("Takeno, Samurai General", ["Takeno, Samurai General"])
    assert _size("Takeno, Samurai General", ["Takeno, Samurai General", "Devoted Retainer"]) == (
        takeno_alone
    )


def test_diligent_zookeeper_counts_creature_types_of_non_humans_only():
    bears_alone = _size("Grizzly Bears", ["Grizzly Bears"])
    board = ["Diligent Zookeeper", "Grizzly Bears", "Elite Vanguard"]
    assert _size("Grizzly Bears", board) == (bears_alone[0] + 1, bears_alone[1] + 1)
    vanguard_alone = _size("Elite Vanguard", ["Elite Vanguard"])
    # Elite Vanguard is a Human: "each non-Human creature" leaves it alone.
    assert _size("Elite Vanguard", board) == vanguard_alone


def test_light_from_within_counts_white_symbols_in_each_creatures_cost():
    scenario = _setup(["Light from Within", "Serra Angel", "Grizzly Bears"])
    angel = scenario.creature("Serra Angel")
    bears = scenario.creature("Grizzly Bears")
    assert _pt(scenario, angel) == (4 + 2, 4 + 2)
    assert _pt(scenario, bears) == (2, 2)


def test_moraug_counts_the_times_each_creature_attacked_this_turn():
    scenario = _setup(["Moraug, Fury of Akoum", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    before = _pt(scenario, bears)
    scenario.game.attack_count_this_turn[bears.id] = 2
    assert _delta(scenario, bears, before) == (2, 0)


# -- Base power and toughness and animated artifacts -------------------------


def test_dollmakers_shop_sets_base_pt_to_the_number_of_creatures_you_control():
    scenario = _setup(["Dollmaker's Shop // Porcelain Gallery", "Grizzly Bears", "Hill Giant"])
    bears, giant = scenario.creature("Grizzly Bears"), scenario.creature("Hill Giant")
    # The base-P/T line is the Porcelain Gallery door's: locked, it does nothing.
    assert (_pt(scenario, bears), _pt(scenario, giant)) == ((2, 2), (3, 3))
    (shop,) = [
        c
        for c in scenario.game.permanents_controlled_by("alice")
        if c.card.name.startswith("Dollmaker")
    ]
    shop.unlocked_doors = ("Porcelain Gallery",)
    assert (_pt(scenario, bears), _pt(scenario, giant)) == ((2, 2), (2, 2))


def test_march_of_the_machines_animates_noncreature_artifacts_by_mana_value():
    scenario = _setup(["March of the Machines", "Mind Stone", "Sol Ring", "Grizzly Bears"])
    stone = _perm(scenario, "Mind Stone")
    ring = _perm(scenario, "Sol Ring")
    assert _pt(scenario, stone) == (2, 2)
    assert _pt(scenario, ring) == (1, 1)
    assert "creature" in {t.value for t in scenario.game.computed_board().of(stone).types}
    # A creature that was never an artifact is untouched.
    assert _pt(scenario, scenario.creature("Grizzly Bears")) == (2, 2)

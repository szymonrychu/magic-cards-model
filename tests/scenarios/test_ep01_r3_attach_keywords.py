"""EP-01 R3 T3: Equipment/Fortification attach keywords and attach triggers.

Read whole with `mise run rules:find` in the session that wrote this file:

- **CR 702.92a** - Living weapon: "When this Equipment enters, create a 0/0
  black Phyrexian Germ creature token, then attach this Equipment to it."
- **CR 702.163a** - For Mirrodin!: "... create a 2/2 red Rebel creature token,
  then attach this Equipment to it."
- **CR 702.182a** - Job select: "... create a 1/1 colorless Hero creature
  token, then attach this Equipment to it."
- **CR 702.67a** - Fortify: "[Cost]: Attach this Fortification to target land
  you control. Activate only as a sorcery."
- **CR 301.6** - a Fortification attaches to a land and to nothing else.
- **CR 701.3a** - attach; **CR 603.6a** - enters-the-battlefield triggers.

Proved on the listed cards and on Batterskull, Barbed Batterfist, Monk's Fist
and Machinist's Arsenal (Modern/Pioneer/Standard printings in no deck list).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.attach_keywords import fortify_activation
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind, Affordability
from magic_cards_model.models.token import TokenState
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario, mana_from


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _lands(spec) -> list[str]:
    return ["Mountain"] * spec if isinstance(spec, int) else list(spec)


def _cast_board(hand: list[str], lands, *, graveyard=(), bob_graveyard=(), battlefield=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            graveyard=list(graveyard),
            battlefield=[*_lands(lands), *battlefield],
        )
        .player("bob", graveyard=list(bob_graveyard))
        .build()
    )


def _cast(scenario, name: str, lands):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(name, *scenario.untapped_sources(*_lands(lands)))
    settle(scenario)
    return scenario.find(name, Zone.BATTLEFIELD, "alice")


def _host(scenario, equipment):
    return scenario.game.find_by_id(equipment.attached_to)


def _pt(scenario, permanent) -> tuple[int, int]:
    chars = scenario.game.characteristics_of(permanent)
    return chars.power, chars.toughness


# -- the three keywords are handled ------------------------------------------


def test_the_attach_keywords_read_handled():
    for name in (
        "Bonehoard",
        "Cranial Ram",
        "Batterskull",
        "Bladehold War-Whip",
        "Barbed Batterfist",
        "Dark Knight's Greatsword",
        "Monk's Fist",
        "Machinist's Arsenal",
    ):
        assert card_support(card(name)).status == "handled", name


# -- Living weapon (CR 702.92a) ----------------------------------------------


def test_living_weapon_makes_a_black_phyrexian_germ_and_attaches_to_it():
    scenario = _cast_board(["Batterskull"], 5)
    skull = _cast(scenario, "Batterskull", 5)
    germ = _host(scenario, skull)

    assert germ.name == "Phyrexian Germ Token"
    assert isinstance(germ, TokenState)
    assert "Phyrexian" in scenario.game.characteristics_of(germ).subtypes
    assert _pt(scenario, germ) == (4, 4)  # 0/0 base, +4/+4 from Batterskull


def test_living_weapon_germ_dies_when_the_equipment_gives_no_toughness():
    # Bonehoard counts creature cards in all graveyards: none, so a 0/0 Germ.
    scenario = _cast_board(["Bonehoard"], 4)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Bonehoard", *scenario.untapped_sources(*["Mountain"] * 4))
    settle(scenario)
    scenario.state_based_actions()
    hoard = scenario.find("Bonehoard", Zone.BATTLEFIELD, "alice")

    assert hoard.attached_to is None  # CR 704.5f: the 0/0 Germ died, CR 704.5n
    assert [s.name for s in scenario.game.permanents_controlled_by("alice")].count(
        "Phyrexian Germ Token"
    ) == 0


def test_living_weapon_triggers_when_put_onto_the_battlefield_without_casting():
    scenario = (
        Scenario()
        .player("alice", hand=["Batterskull"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skull = scenario.put_onto_battlefield("Batterskull", "alice")
    settle(scenario)

    assert _host(scenario, skull).name == "Phyrexian Germ Token"


def test_another_equipment_entering_does_not_make_a_germ():
    scenario = _cast_board(["Cranial Ram"], RAM_LANDS, battlefield=["Batterskull"])
    skull = scenario.find("Batterskull", Zone.BATTLEFIELD, "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ram = _cast_ram(scenario)

    assert skull.attached_to is None  # Batterskull sat there; only the Ram's own trigger fired
    assert _host(scenario, ram).name == "Phyrexian Germ Token"
    germs = [
        s
        for s in scenario.game.permanents_controlled_by("alice")
        if s.name == "Phyrexian Germ Token"
    ]
    assert len(germs) == 1


RAM_LANDS = ["Swamp", "Mountain"]


def _cast_ram(scenario):
    scenario.cast_and_resolve("Cranial Ram", *scenario.untapped_sources(*RAM_LANDS))
    settle(scenario)
    return scenario.find("Cranial Ram", Zone.BATTLEFIELD, "alice")


def test_bonehoard_counts_creature_cards_in_all_graveyards():
    scenario = _cast_board(
        ["Bonehoard"],
        4,
        graveyard=["Grizzly Bears", "Hill Giant", "Mountain"],
        bob_graveyard=["Serra Angel"],
    )
    hoard = _cast(scenario, "Bonehoard", 4)

    assert _pt(scenario, _host(scenario, hoard)) == (
        3,
        3,
    )  # three creature cards, a land is not one


def test_bonehoard_bonus_follows_the_graveyards():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bonehoard"],
            battlefield=["Mountain"] * 4,
            graveyard=["Grizzly Bears", "Hill Giant"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    hoard = _cast(scenario, "Bonehoard", 4)
    germ = _host(scenario, hoard)
    assert _pt(scenario, germ) == (2, 2)

    scenario.game.destroy(scenario.creature("Serra Angel", "bob"))  # into bob's graveyard
    assert _pt(scenario, germ) == (3, 3)


def test_cranial_ram_counts_artifacts_you_control_including_itself():
    scenario = _cast_board(["Cranial Ram"], RAM_LANDS, battlefield=["Bonehoard", "Batterskull"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ram = _cast_ram(scenario)

    # three artifacts: Bonehoard, Batterskull, Cranial Ram -> +3/+1 on a 0/0
    assert _pt(scenario, _host(scenario, ram)) == (3, 1)


# -- For Mirrodin! (CR 702.163a) ---------------------------------------------


def test_for_mirrodin_makes_a_red_rebel_and_attaches_to_it():
    scenario = _cast_board(["Barbed Batterfist"], 2)
    fist = _cast(scenario, "Barbed Batterfist", 2)
    rebel = _host(scenario, fist)

    assert rebel.name == "Rebel Token"
    assert isinstance(rebel, TokenState)
    assert _pt(scenario, rebel) == (3, 1)  # 2/2 base, +1/-1 from the Equipment


def test_bladehold_war_whip_gives_its_rebel_double_strike():
    scenario = _cast_board(["Bladehold War-Whip"], ["Mountain", "Mountain", "Plains"])
    whip = _cast(scenario, "Bladehold War-Whip", ["Mountain", "Mountain", "Plains"])
    rebel = _host(scenario, whip)

    assert rebel.name == "Rebel Token"
    assert _pt(scenario, rebel) == (2, 2)
    assert has_keyword(rebel, Keyword.DOUBLE_STRIKE, scenario.game)


# -- Job select (CR 702.182a) ------------------------------------------------


def test_job_select_makes_a_colorless_hero_and_attaches_to_it():
    scenario = _cast_board(["Monk's Fist"], 2)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Monk's Fist", *scenario.untapped_sources("Mountain", "Mountain"))
    settle(scenario)
    fist = scenario.find("Monk's Fist", Zone.BATTLEFIELD, "alice")
    hero = _host(scenario, fist)

    assert hero.name == "Hero Token"
    assert isinstance(hero, TokenState)
    chars = scenario.game.characteristics_of(hero)
    assert "Monk" in chars.subtypes  # "is a Monk in addition to its other types"
    assert (chars.power, chars.toughness) == (2, 1)  # 1/1 base, +1/+0


def test_dark_knights_greatsword_hero_is_a_knight_with_plus_three_power():
    scenario = _cast_board(["Dark Knight's Greatsword"], ["Swamp", "Mountain", "Mountain"])
    sword = _cast(scenario, "Dark Knight's Greatsword", ["Swamp", "Mountain", "Mountain"])
    hero = _host(scenario, sword)

    chars = scenario.game.characteristics_of(hero)
    assert hero.name == "Hero Token"
    assert "Knight" in chars.subtypes
    assert (chars.power, chars.toughness) == (4, 1)


def test_job_select_on_a_second_printing_scales_with_artifacts():
    scenario = _cast_board(["Machinist's Arsenal"], ["Mountain"] * 4 + ["Plains"])
    arsenal = _cast(scenario, "Machinist's Arsenal", ["Mountain"] * 4 + ["Plains"])

    # +2/+2 for each artifact you control: the Arsenal itself -> a 3/3 Hero
    assert _pt(scenario, _host(scenario, arsenal)) == (3, 3)


# -- "Return this Aura/Equipment to its owner's hand" (CR 701.3, CR 400.7) ---


def _aura_board(aura: str, lands: list[str], victim: str = "Grizzly Bears"):
    scenario = (
        Scenario()
        .player("alice", battlefield=[aura, victim, *lands])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    host = scenario.creature(victim, "alice")
    scenario.find(aura, Zone.BATTLEFIELD, "alice").attach_to(host)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, host


def test_forced_worship_returns_to_hand_and_frees_the_creature():
    scenario, bears = _aura_board("Forced Worship", ["Plains"] * 3)
    aura = scenario.find("Forced Worship", Zone.BATTLEFIELD, "alice")

    scenario.activate(aura, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    scenario.resolve_top()

    assert [c.name for c in scenario.player("alice").hand] == ["Forced Worship"]
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(bears) is True


def test_forced_worship_keeps_the_creature_home_while_attached():
    scenario, bears = _aura_board("Forced Worship", ["Plains"] * 3)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.can_attack(bears) is False


def test_returning_an_aura_does_nothing_if_it_already_left():
    scenario, _bears = _aura_board("Forced Worship", ["Plains"] * 3)
    aura = scenario.find("Forced Worship", Zone.BATTLEFIELD, "alice")
    scenario.activate(aura, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    scenario.game.destroy(aura)  # in response

    scenario.resolve_top()

    assert [
        c.name for c in scenario.player("alice").hand
    ] == []  # stays in the graveyard (CR 400.7)
    assert [c.name for c in scenario.player("alice").graveyard] == ["Forced Worship"]


def test_wingspan_stride_returns_to_hand_proof():
    scenario, _ = _aura_board("Wingspan Stride", ["Island"] * 3)
    aura = scenario.find("Wingspan Stride", Zone.BATTLEFIELD, "alice")
    scenario.activate(aura, *scenario.untapped_sources("Island", "Island", "Island"))
    scenario.resolve_top()

    assert [c.name for c in scenario.player("alice").hand] == ["Wingspan Stride"]


def test_batterskull_bounces_for_three_and_its_germ_dies():
    scenario = _cast_board(["Batterskull"], 8)
    skull = _cast(scenario, "Batterskull", 5)
    germ = _host(scenario, skull)

    scenario.activate(skull, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.resolve_top()
    scenario.state_based_actions()

    assert [c.name for c in scenario.player("alice").hand] == ["Batterskull"]
    assert germ.zone is not Zone.BATTLEFIELD  # a 0/0 once the Equipment is gone


def test_krasis_incubation_returns_as_a_cost_then_counters_the_enchanted_creature():
    scenario, bears = _aura_board("Krasis Incubation", ["Forest", "Island", "Plains"])
    aura = scenario.find("Krasis Incubation", Zone.BATTLEFIELD, "alice")

    scenario.activate(aura, *scenario.untapped_sources("Forest", "Island", "Plains"))
    # the Aura is returned to pay the cost (CR 602.2b): it is already in hand
    assert [c.name for c in scenario.player("alice").hand] == ["Krasis Incubation"]
    scenario.resolve_top()

    assert _pt(scenario, bears) == (4, 4)  # two +1/+1 counters on a 2/2 (CR 113.7a: last known)
    assert scenario.game.characteristics_of(bears).is_creature


def test_krasis_incubation_cannot_be_activated_once_the_aura_is_gone():
    scenario, _bears = _aura_board("Krasis Incubation", ["Forest", "Island", "Plains"])
    aura = scenario.find("Krasis Incubation", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(aura)

    assert scenario.game.activated_abilities(aura) == [] or scenario.why_cannot_activate(aura)


# -- Dark Knight's Greatsword: "Equip—Pay 3 life. Activate only once each turn." ---


def _equip(scenario, sword, target, username="alice"):
    activation = equip_activation(scenario.game, sword, target, username)
    payment = activation.begin_paying()
    payment.pay()
    activation.activate()
    activation.resolve()
    scenario.state_based_actions()
    return activation


def _sword_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Dark Knight's Greatsword", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find("Dark Knight's Greatsword", Zone.BATTLEFIELD, "alice")


def test_greatsword_equip_costs_three_life():
    scenario, sword = _sword_board()
    bears = scenario.creature("Grizzly Bears", "alice")

    _equip(scenario, sword, bears)

    assert scenario.player("alice").life == 17
    assert sword.attached_to == bears.id
    assert _pt(scenario, bears) == (5, 2)


def test_greatsword_equip_can_be_activated_only_once_each_turn():
    scenario, sword = _sword_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    _equip(scenario, sword, bears)

    with pytest.raises(ValueError, match="only once each turn"):
        _equip(scenario, sword, giant)
    assert scenario.player("alice").life == 17  # the second one never cost anything


# -- Fortify (CR 702.67a) -----------------------------------------------------


def _garrison_board(lands: int = 3):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Darksteel Garrison", "Grizzly Bears", *(["Forest"] * lands), "Mountain"],
        )
        .player("bob", battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find("Darksteel Garrison", Zone.BATTLEFIELD, "alice")


def _fortify(scenario, garrison, land, cost_lands: int = 3, username="alice"):
    activation = fortify_activation(scenario.game, garrison, land, username)
    payment = activation.begin_paying()
    for source in scenario.untapped_sources(*(["Forest"] * cost_lands)):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    scenario.state_based_actions()
    return activation


def test_fortify_attaches_the_fortification_to_a_land_you_control():
    scenario, garrison = _garrison_board(4)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    _fortify(scenario, garrison, mountain)

    assert garrison.attached_to == mountain.id


def test_fortified_land_has_indestructible():
    scenario, garrison = _garrison_board(4)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    assert not has_keyword(mountain, "Indestructible", scenario.game)

    _fortify(scenario, garrison, mountain)

    assert has_keyword(mountain, "Indestructible", scenario.game)
    scenario.game.destroy(mountain)
    assert mountain.zone is Zone.BATTLEFIELD


def test_fortify_refuses_a_nonland_target():
    scenario, garrison = _garrison_board()
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="not a land"):
        fortify_activation(scenario.game, garrison, bears, "alice")


def test_fortify_refuses_an_opponents_land():
    scenario, garrison = _garrison_board()
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match="does not control"):
        fortify_activation(scenario.game, garrison, plains, "alice")


def test_fortify_is_a_sorcery_speed_ability():
    scenario, garrison = _garrison_board()
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    activation = fortify_activation(scenario.game, garrison, mountain, "alice")

    assert "sorcery" in (activation.why_not() or "")


def test_fortify_is_offered_as_a_legal_action_with_a_land_slot():
    scenario, garrison = _garrison_board(4)

    rows = [
        a
        for a in legal_actions(scenario.game, "alice")
        if a.kind is ActionKind.ACTIVATE and a.keyword == "Fortify"
    ]

    assert len(rows) == 1
    assert rows[0].card_id == garrison.id
    assert rows[0].rule == "CR 702.67a"
    assert rows[0].affordable is Affordability.YES
    assert rows[0].target_slots


def test_moving_a_fortification_to_another_land_unattaches_it_from_the_first():
    scenario, garrison = _garrison_board(8)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    forest = scenario.untapped_sources("Forest")[-1]
    _fortify(scenario, garrison, mountain)
    assert garrison.attached_to == mountain.id

    _fortify(scenario, garrison, forest, 3)

    assert garrison.attached_to == forest.id
    assert not has_keyword(mountain, "Indestructible", scenario.game)


def test_a_fortification_stays_on_the_battlefield_when_its_land_leaves():
    scenario, garrison = _garrison_board(4)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    _fortify(scenario, garrison, mountain)
    scenario.game.destroy(mountain)
    scenario.state_based_actions()  # indestructible: it stays; take it away by bouncing instead
    scenario.game.return_to_hand(mountain)
    scenario.state_based_actions()

    assert garrison.zone is Zone.BATTLEFIELD  # CR 704.5n: unattached, not put into a graveyard
    assert garrison.attached_to is None


def test_whenever_fortified_land_becomes_tapped_target_creature_gets_a_counter_of_pump():
    scenario, garrison = _garrison_board(4)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _fortify(scenario, garrison, mountain)
    scenario.choose_trigger_targets("Darksteel Garrison", [bears])

    scenario.game.tap_permanent(mountain)
    settle(scenario)

    assert _pt(scenario, bears) == (3, 3)  # +1/+1 until end of turn


def test_an_unfortified_land_tapping_does_not_trigger_the_garrison():
    scenario, garrison = _garrison_board(4)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.tap_permanent(scenario.untapped_sources("Forest")[0])
    settle(scenario)

    assert _pt(scenario, bears) == (2, 2)
    assert garrison.attached_to is None


# -- Attach on enter (CR 701.3a, CR 603.6a) ---------------------------------


def _cutter_board(*, bob_battlefield=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Cori-Steel Cutter"],
            battlefield=["Sigarda's Aid", "Grizzly Bears", "Hill Giant", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )


def _cast_cutter(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Cori-Steel Cutter", *scenario.untapped_sources("Mountain", "Mountain")
    )
    settle(scenario)
    return scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")


def test_sigardas_aid_attaches_an_entering_equipment_to_target_creature():
    scenario = _cutter_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Sigarda's Aid", [bears])
    scenario.will_take_the_may(True, source="Sigarda's Aid")

    cutter = _cast_cutter(scenario)

    assert cutter.attached_to == bears.id
    assert _pt(scenario, bears) == (3, 3)  # +1/+1 from Cori-Steel Cutter


def test_sigardas_aid_may_be_declined():
    scenario = _cutter_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Sigarda's Aid", [bears])
    scenario.will_take_the_may(False, source="Sigarda's Aid")

    cutter = _cast_cutter(scenario)

    assert cutter.attached_to is None


def test_sigardas_aid_refuses_a_creature_you_do_not_control():
    scenario = _cutter_board(bob_battlefield=["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Sigarda's Aid", [angel])


def test_sigardas_aid_ignores_a_noncreature_permanent_entering():
    scenario = (
        Scenario()
        .player("alice", hand=["Mountain"], battlefield=["Sigarda's Aid", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Mountain")

    assert scenario.game.pending_triggers == []


def test_sigardas_aid_does_not_see_an_opponents_equipment():
    scenario = (
        Scenario()
        .player("bob", hand=["Cori-Steel Cutter"], battlefield=["Mountain", "Mountain"])
        .player("alice", battlefield=["Sigarda's Aid", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Cori-Steel Cutter",
        *scenario.untapped_sources("Mountain", "Mountain", username="bob"),
        username="bob",
    )

    assert scenario.game.pending_triggers == []


# -- Prison Term: "you may attach this Aura to that creature" -----------------


def _prison_term_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Prison Term", "Grizzly Bears"])
        .player("bob", hand=["Grizzly Bears"], battlefield=["Hill Giant", "Forest", "Forest"])
        .build()
    )
    term = scenario.find("Prison Term", Zone.BATTLEFIELD, "alice")
    term.attach_to(scenario.creature("Hill Giant", "bob"))
    return scenario, term


def test_prison_term_moves_to_an_opponents_creature_that_enters():
    scenario, term = _prison_term_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Prison Term")
    entered = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    settle(scenario)

    assert term.attached_to == entered.id


def test_prison_term_may_stay_where_it_is():
    scenario, term = _prison_term_board()
    giant = scenario.creature("Hill Giant", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Prison Term")
    scenario.put_onto_battlefield("Grizzly Bears", "bob")
    settle(scenario)

    assert term.attached_to == giant.id


def test_prison_term_ignores_your_own_creature_entering():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Prison Term"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    term = scenario.find("Prison Term", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    term.attach_to(giant)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert scenario.game.pending_triggers == []
    assert term.attached_to == giant.id


# -- Frodo, Determined Hero: "enters or attacks, you may attach target Equipment" --


def _frodo_board(hand=("Frodo, Determined Hero",), equipment=("Cori-Steel Cutter",)):
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[*equipment, "Grizzly Bears", "Plains", "Plains"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )


def _cast_frodo(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Frodo, Determined Hero", *scenario.untapped_sources("Plains", "Plains")
    )
    return scenario.creature("Frodo, Determined Hero", "alice")


def test_frodo_entering_attaches_an_equipment_with_mana_value_two():
    scenario = _frodo_board()
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Frodo, Determined Hero", [cutter])
    scenario.will_take_the_may(True, source="Frodo, Determined Hero")

    frodo = _cast_frodo(scenario)
    settle(scenario)

    assert cutter.attached_to == frodo.id


def test_frodo_cannot_target_an_equipment_with_mana_value_five():
    scenario = _frodo_board(equipment=("Batterskull",))
    skull = scenario.find("Batterskull", Zone.BATTLEFIELD, "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Frodo, Determined Hero", [skull])


def test_frodo_attacking_attaches_an_equipment():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Frodo, Determined Hero", "Cori-Steel Cutter", "Plains"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    frodo = scenario.creature("Frodo, Determined Hero", "alice")
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.choose_trigger_targets("Frodo, Determined Hero", [cutter])
    scenario.will_take_the_may(True, source="Frodo, Determined Hero")

    scenario.attack_with(frodo, defending="bob")
    settle(scenario)

    assert cutter.attached_to == frodo.id


def test_frodo_may_decline_the_attach():
    scenario = _frodo_board()
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Frodo, Determined Hero", [cutter])
    scenario.will_take_the_may(False, source="Frodo, Determined Hero")

    _cast_frodo(scenario)
    settle(scenario)

    assert cutter.attached_to is None


def test_frodo_takes_no_damage_during_your_turn_and_normal_damage_otherwise():
    scenario = _frodo_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    frodo = scenario.put_onto_battlefield("Frodo, Determined Hero", "alice")

    scenario.game.deal_damage(frodo, 5, source=scenario.creature("Hill Giant", "bob"))
    assert frodo.damage == 0  # alice's turn: prevented (CR 615.1)


def test_frodo_takes_damage_normally_on_an_opponents_turn():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Hill Giant"])
        .player("alice", battlefield=["Frodo, Determined Hero"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    frodo = scenario.creature("Frodo, Determined Hero", "alice")

    scenario.game.deal_damage(frodo, 1, source=scenario.creature("Hill Giant", "bob"))

    assert frodo.damage == 1


# -- Kor Outfitter: "attach target Equipment you control to target creature you control" --


def test_kor_outfitter_attaches_a_target_equipment_to_a_target_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kor Outfitter"],
            battlefield=["Cori-Steel Cutter", "Grizzly Bears", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Kor Outfitter", [cutter, bears])
    scenario.will_take_the_may(True, source="Kor Outfitter")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Kor Outfitter", *scenario.untapped_sources("Plains", "Plains"))
    settle(scenario)

    assert cutter.attached_to == bears.id


def test_kor_outfitter_moves_an_equipment_off_its_old_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kor Outfitter"],
            battlefield=["Cori-Steel Cutter", "Grizzly Bears", "Hill Giant", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    cutter.attach_to(giant)
    scenario.choose_trigger_targets("Kor Outfitter", [cutter, bears])
    scenario.will_take_the_may(True, source="Kor Outfitter")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Kor Outfitter", *scenario.untapped_sources("Plains", "Plains"))
    settle(scenario)

    assert cutter.attached_to == bears.id
    assert _pt(scenario, giant) == (3, 3)


# -- "enchanted/fortified <object> becomes tapped" names the attached object only --


def test_lust_for_war_triggers_only_for_the_enchanted_creature():
    scenario, bears = _aura_board("Lust for War", ["Plains"] * 3)
    giant = scenario.creature("Hill Giant", "bob")

    scenario.game.tap_permanent(giant)  # not the enchanted creature
    settle(scenario)
    assert scenario.player("alice").life == 20

    scenario.game.tap_permanent(bears)
    settle(scenario)
    assert scenario.player("alice").life == 17


# -- Counters on the enchanted creature, and Aura bounce on more printings ----


def test_ephara_s_enlightenment_puts_a_counter_on_the_creature_it_enters_on():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ephara's Enlightenment"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Ephara's Enlightenment",
        *scenario.untapped_sources("Plains", "Island", "Island"),
        targets=[bears],
    )
    settle(scenario)

    assert _pt(scenario, bears) == (3, 3)


@pytest.mark.parametrize(
    ("aura", "lands"),
    [
        ("Agoraphobia", ["Island"] * 3),
        ("Conviction", ["Plains"]),
        ("Wingspan Stride", ["Island"] * 3),
    ],
)
def test_an_aura_that_returns_itself_to_hand_does_so_for_its_printed_cost(aura, lands):
    scenario, bears = _aura_board(aura, lands)
    host_before = scenario.find(aura, Zone.BATTLEFIELD, "alice").attached_to
    assert host_before == bears.id

    scenario.activate(
        scenario.find(aura, Zone.BATTLEFIELD, "alice"), *scenario.untapped_sources(*lands)
    )
    scenario.resolve_top()

    assert [c.name for c in scenario.player("alice").hand] == [aura]
    assert bears.zone is Zone.BATTLEFIELD  # CR 303.4: the creature is untouched

"""Scenario: static damage redirection ("All damage that would be dealt to you
is dealt to <this creature | enchanted creature> instead") and the "prevent that
damage. <rider>" form, the rider performed only when damage was actually
prevented (EP-01 round 1, task T5).

CR 614.9: redirection effects replace damage dealt to one object with the same
damage dealt to another; CR 615.5: a prevention effect's additional effect may
refer to the amount prevented and takes place immediately afterward; CR 615.12:
against damage that can't be prevented the prevention still applies but prevents
nothing, so the rider has nothing to refer to; CR 603.12: a reflexive trigger
("When damage is prevented this way, ...") goes on the stack; CR 122.1: counters;
CR 510.2: combat damage is dealt simultaneously.

Every CR number here was looked up with `mise run rules:find`: 614.9, 615.5,
615.12, 603.12, 122.1, 510.2, 120.4b.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(
    alice=(),
    bob=(),
    alice_graveyard=(),
    alice_library=("Plains", "Plains", "Plains", "Plains", "Plains"),
    *,
    alice_hand=(),
    bob_hand=(),
    first="alice",
):
    """`first` is the active player: the first one added takes the first turn."""
    seats = {
        "alice": {
            "library": list(alice_library),
            "graveyard": list(alice_graveyard),
            "hand": list(alice_hand),
            "battlefield": list(alice),
        },
        "bob": {
            "library": ["Mountain", "Mountain", "Mountain"],
            "hand": list(bob_hand),
            "battlefield": list(bob),
        },
    }
    order = ["alice", "bob"] if first == "alice" else ["bob", "alice"]
    scenario = Scenario()
    for name in order:
        scenario.player(name, **seats[name])
    return scenario.build()


def _on(scenario, name, owner="alice"):
    return scenario.find(name, Zone.BATTLEFIELD, owner)


def _hit(scenario, target, amount, source, *, combat=False, unpreventable=False):
    game = scenario.game
    if combat:
        game._dealing_combat_damage = True
    try:
        return game.deal_damage(target, amount, source=source, unpreventable=unpreventable)
    finally:
        game._dealing_combat_damage = False


def _spell(scenario, name, owner, land="Mountain"):
    """A real spell `owner` cast from their hand and left on the stack - a
    damage source that is a spell (CR 112.1)."""
    game = scenario.game
    if scenario.step is Step.UNTAP:
        scenario.start_at(Step.PRECOMBAT_MAIN)
    if game.priority is not None and game.priority.seat != owner:
        game.pass_priority(game.priority.seat)  # CR 117.3d: the next player in turn order
    other = "bob" if owner == "alice" else "alice"
    source = next(
        c for c in game.battlefield if c.name == land and c.controller == owner and not c.tapped
    )
    return scenario.cast_onto_stack(name, source, username=owner, targets=[scenario.player(other)])


def _counters(state, kind="+1/+1"):
    return state.counter_count(kind)


# -- redirection ---------------------------------------------------------------------------------


@pytest.mark.parametrize("holder", ["Empyrial Archangel", "Palisade Giant"])
def test_damage_to_you_is_dealt_to_the_redirecting_creature_instead(holder):
    scenario = _board(alice=[holder], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    redirector = _on(scenario, holder)

    _hit(scenario, scenario.player("alice"), 3, guide)

    assert scenario.player("alice").life == 20
    assert redirector.damage == 3


def test_damage_to_the_opponent_is_not_redirected():
    scenario = _board(alice=["Empyrial Archangel"], bob=["Goblin Guide"])
    _hit(scenario, scenario.player("bob"), 3, _on(scenario, "Empyrial Archangel"))
    assert scenario.player("bob").life == 17
    assert _on(scenario, "Empyrial Archangel").damage == 0


def test_palisade_giant_also_redirects_damage_to_other_permanents_you_control():
    scenario = _board(alice=["Palisade Giant", "Grizzly Bears"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    giant = _on(scenario, "Palisade Giant")
    bears = scenario.creature("Grizzly Bears", "alice")

    _hit(scenario, bears, 2, guide)
    _hit(scenario, scenario.creature("Goblin Guide", "bob"), 1, giant)

    assert bears.damage == 0
    assert giant.damage == 2
    assert scenario.creature("Goblin Guide", "bob").damage == 1  # the opponent's own creature


def test_empyrial_archangel_does_not_redirect_damage_to_your_creatures():
    scenario = _board(alice=["Empyrial Archangel", "Grizzly Bears"], bob=["Goblin Guide"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _hit(scenario, bears, 2, scenario.creature("Goblin Guide", "bob"))
    assert bears.damage == 2


@pytest.mark.parametrize("holder", ["Pariah", "With Great Power . . ."])
def test_an_aura_redirects_damage_to_you_to_the_enchanted_creature(holder):
    scenario = _board(alice=[holder, "Grizzly Bears"], bob=["Goblin Guide"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _on(scenario, holder).attach_to(bears)

    _hit(scenario, scenario.player("alice"), 1, scenario.creature("Goblin Guide", "bob"))

    assert scenario.player("alice").life == 20
    assert bears.damage == 1


def test_pariahs_shield_redirects_to_the_equipped_creature_and_stops_when_unattached():
    scenario = _board(alice=["Pariah's Shield", "Grizzly Bears"], bob=["Goblin Guide"])
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    # Unattached: there is no equipped creature, so the damage is dealt to you.
    _hit(scenario, scenario.player("alice"), 2, guide)
    assert scenario.player("alice").life == 18

    _on(scenario, "Pariah's Shield").attach_to(bears)
    _hit(scenario, scenario.player("alice"), 2, guide)
    assert scenario.player("alice").life == 18
    assert bears.damage == 2


def test_ancient_adamantoise_redirects_damage_to_you_and_your_other_permanents():
    scenario = _board(alice=["Ancient Adamantoise", "Grizzly Bears"], bob=["Goblin Guide"])
    tortoise = _on(scenario, "Ancient Adamantoise")
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")

    _hit(scenario, scenario.player("alice"), 3, guide)
    _hit(scenario, bears, 2, guide)

    assert scenario.player("alice").life == 20
    assert bears.damage == 0
    assert tortoise.damage == 5


def test_weathered_bodyguards_redirect_unblocked_combat_damage_while_untapped():
    scenario = _board(
        alice=["Weathered Bodyguards"], bob=["Goblin Guide", "Grizzly Bears"], first="bob"
    )
    bodyguards = _on(scenario, "Weathered Bodyguards")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "bob"), defending="alice")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 20
    assert bodyguards.damage == 2


def test_weathered_bodyguards_do_nothing_while_tapped():
    scenario = _board(alice=["Weathered Bodyguards"], bob=["Goblin Guide"], first="bob")
    bodyguards = _on(scenario, "Weathered Bodyguards")
    bodyguards.tap()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "bob"), defending="alice")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 18
    assert bodyguards.damage == 0


def test_weathered_bodyguards_leave_noncombat_damage_alone():
    scenario = _board(alice=["Weathered Bodyguards"], bob=["Goblin Guide"])
    _hit(scenario, scenario.player("alice"), 2, scenario.creature("Goblin Guide", "bob"))
    assert scenario.player("alice").life == 18


# -- prevent that damage, put counters -----------------------------------------------------------


def test_anti_venom_prevents_the_damage_and_grows_by_that_many_counters():
    scenario = _board(
        alice=["Anti-Venom, Horrifying Healer", "Grizzly Bears"], bob=["Goblin Guide"]
    )
    venom = _on(scenario, "Anti-Venom, Horrifying Healer")
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, venom, 3, guide) == 0
    assert venom.damage == 0
    assert _counters(venom) == 3
    # Damage to anything else is untouched.
    assert _hit(scenario, scenario.creature("Grizzly Bears", "alice"), 2, guide) == 2
    assert _counters(venom) == 3


def test_anti_venom_gets_no_counters_from_damage_that_cant_be_prevented():
    scenario = _board(alice=["Anti-Venom, Horrifying Healer"], bob=["Goblin Guide"])
    venom = _on(scenario, "Anti-Venom, Horrifying Healer")
    assert (
        _hit(scenario, venom, 3, scenario.creature("Goblin Guide", "bob"), unpreventable=True) == 3
    )
    assert _counters(venom) == 0


def test_phytohydra_turns_damage_into_counters_instead():
    scenario = _board(alice=["Phytohydra"], bob=["Goblin Guide"])
    hydra = _on(scenario, "Phytohydra")
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, hydra, 4, guide) == 0
    assert _counters(hydra) == 4 and hydra.damage == 0
    # A replacement, not a prevention: damage that can't be prevented is replaced all the same.
    assert _hit(scenario, hydra, 2, guide, unpreventable=True) == 0
    assert _counters(hydra) == 6


def test_stormwild_capridor_only_converts_noncombat_damage():
    scenario = _board(alice=["Stormwild Capridor"], bob=["Goblin Guide"])
    capridor = _on(scenario, "Stormwild Capridor")
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, capridor, 2, guide) == 0
    assert _counters(capridor) == 2
    assert _hit(scenario, capridor, 1, guide, combat=True) == 1  # combat damage is dealt
    assert _counters(capridor) == 2


def test_ironscale_hydra_gets_one_counter_per_prevented_combat_damage_event():
    scenario = _board(
        alice=["Ironscale Hydra"], bob=["Goblin Guide", "Mountain"], bob_hand=["Lightning Bolt"]
    )
    hydra = _on(scenario, "Ironscale Hydra")
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, hydra, 4, guide, combat=True) == 0
    assert _counters(hydra) == 1
    assert _hit(scenario, hydra, 4, guide) == 4  # noncombat damage is not covered
    assert _counters(hydra) == 1
    assert (
        _hit(scenario, hydra, 4, _spell(scenario, "Lightning Bolt", "bob"), combat=True) == 4
    )  # not a creature


def test_vigor_protects_other_creatures_you_control_and_grows_them():
    scenario = _board(alice=["Vigor", "Grizzly Bears"], bob=["Goblin Guide", "Grizzly Bears"])
    vigor = _on(scenario, "Vigor")
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, bears, 3, guide) == 0
    assert _counters(bears) == 3
    assert _hit(scenario, vigor, 3, guide) == 3  # "another creature"
    assert _counters(vigor) == 0
    assert _hit(scenario, scenario.creature("Grizzly Bears", "bob"), 3, guide) == 3  # "you control"
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 3  # a creature, not a player


# -- prevent that damage, then lose or remove counters -------------------------------------------


def test_phantom_wurm_removes_a_counter_whenever_damage_is_prevented():
    scenario = _board(alice=["Phantom Wurm"], bob=["Goblin Guide"])
    wurm = _on(scenario, "Phantom Wurm")
    wurm.add_counters("+1/+1", 4)
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, wurm, 6, guide) == 0
    assert _counters(wurm) == 3
    # CR 615.12: additional effects still happen against unpreventable damage.
    assert _hit(scenario, wurm, 6, guide, unpreventable=True) == 6
    assert _counters(wurm) == 2


def test_phyrexian_hydra_gets_a_minus_counter_per_damage_prevented():
    scenario = _board(alice=["Phyrexian Hydra"], bob=["Goblin Guide"])
    hydra = _on(scenario, "Phyrexian Hydra")
    assert _hit(scenario, hydra, 3, scenario.creature("Goblin Guide", "bob")) == 0
    assert _counters(hydra, "-1/-1") == 3 and hydra.damage == 0


@pytest.mark.parametrize(
    ("holder", "start"),
    [("Polukranos, Unchained", 6), ("Ugin's Conjurant", 5), ("Protean Hydra", 5)],
)
def test_remove_that_many_counters_instead_of_taking_the_damage(holder, start):
    scenario = _board(alice=[holder], bob=["Goblin Guide"])
    creature = _on(scenario, holder)
    creature.add_counters("+1/+1", start)
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, creature, 2, guide) == 0
    assert _counters(creature) == start - 2
    assert creature.damage == 0


def test_the_counter_gated_forms_prevent_nothing_without_a_plus_one_counter():
    scenario = _board(alice=["Polukranos, Unchained"], bob=["Goblin Guide"])
    polukranos = _on(scenario, "Polukranos, Unchained")
    assert _counters(polukranos) == 0
    assert _hit(scenario, polukranos, 2, scenario.creature("Goblin Guide", "bob")) == 2


def test_removing_more_counters_than_it_has_removes_what_it_has():
    scenario = _board(alice=["Ugin's Conjurant"], bob=["Goblin Guide"])
    creature = _on(scenario, "Ugin's Conjurant")
    creature.add_counters("+1/+1", 2)
    assert _hit(scenario, creature, 5, scenario.creature("Goblin Guide", "bob")) == 0
    assert _counters(creature) == 0


@pytest.mark.parametrize("holder", ["Undergrowth Champion", "Oathsworn Knight"])
def test_a_single_counter_is_removed_per_prevented_damage_event(holder):
    scenario = _board(alice=[holder], bob=["Goblin Guide"])
    creature = _on(scenario, holder)
    creature.add_counters("+1/+1", 3)
    assert _hit(scenario, creature, 5, scenario.creature("Goblin Guide", "bob")) == 0
    assert _counters(creature) == 2


def test_magma_pummeler_deals_damage_equal_to_the_counters_removed_to_any_target():
    scenario = _board(alice=["Magma Pummeler"], bob=["Goblin Guide"])
    pummeler = _on(scenario, "Magma Pummeler")
    pummeler.add_counters("+1/+1", 4)
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, pummeler, 3, guide) == 0
    assert _counters(pummeler) == 1
    assert len(scenario.pending_triggers) == 1  # CR 603.12: a reflexive trigger, on the stack next

    scenario.choose_trigger_targets("Magma Pummeler", [scenario.player("bob")])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert scenario.player("bob").life == 17  # that much damage: the 3 counters removed
    assert scenario.stack_names() == []


def test_sekki_removes_counters_and_creates_that_many_spirit_tokens():
    scenario = _board(alice=["Sekki, Seasons' Guide"], bob=["Goblin Guide"])
    sekki = _on(scenario, "Sekki, Seasons' Guide")
    sekki.add_counters("+1/+1", 8)

    assert _hit(scenario, sekki, 3, scenario.creature("Goblin Guide", "bob")) == 0

    assert _counters(sekki) == 5
    spirits = [c for c in scenario.game.battlefield if c.name == "Spirit Token"]
    assert len(spirits) == 3


# -- prevent that damage, other riders -----------------------------------------------------------


def test_gloom_surgeon_exiles_that_many_cards_from_the_library_for_combat_damage():
    scenario = _board(alice=["Gloom Surgeon"], bob=["Goblin Guide"])
    surgeon = _on(scenario, "Gloom Surgeon")
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, surgeon, 3, guide, combat=True) == 0
    assert len(scenario.player("alice").library) == 2
    assert len(scenario.game.exile) == 3
    assert _hit(scenario, surgeon, 1, guide) == 1  # noncombat: dealt, nothing exiled
    assert len(scenario.player("alice").library) == 2


def test_swans_of_bryn_argoll_draws_the_sources_controller_that_many_cards():
    scenario = _board(alice=["Swans of Bryn Argoll"], bob=["Goblin Guide"])
    swans = _on(scenario, "Swans of Bryn Argoll")
    assert _hit(scenario, swans, 2, scenario.creature("Goblin Guide", "bob")) == 0
    assert len(scenario.player("bob").library) == 1  # bob drew two
    assert len(scenario.player("alice").library) == 5


def test_nine_lives_prevents_the_damage_and_collects_an_incarnation_counter():
    scenario = _board(alice=["Nine Lives"], bob=["Goblin Guide"])
    lives = _on(scenario, "Nine Lives")
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, scenario.player("alice"), 5, guide) == 0
    assert _hit(scenario, scenario.player("alice"), 2, guide) == 0
    assert _counters(lives, "incarnation") == 2  # one per event, not per damage
    assert scenario.player("alice").life == 20
    assert _hit(scenario, scenario.player("bob"), 2, guide) == 2


def test_hostility_prevents_spell_damage_to_opponents_and_makes_a_token_per_damage():
    scenario = _board(
        alice=["Hostility", "Mountain", "Mountain"], alice_hand=["Lightning Bolt", "Lightning Bolt"]
    )
    bolt = _spell(scenario, "Lightning Bolt", "alice")
    assert _hit(scenario, scenario.player("bob"), 3, bolt) == 0
    elementals = [c for c in scenario.game.battlefield if c.name == "Elemental Shaman Token"]
    assert len(elementals) == 3
    # Damage to its controller, and damage from a creature, is untouched.
    assert (
        _hit(scenario, scenario.player("alice"), 3, _spell(scenario, "Lightning Bolt", "alice"))
        == 3
    )
    assert _hit(scenario, scenario.player("bob"), 3, _on(scenario, "Hostility")) == 3


def test_immortal_coil_exiles_a_card_from_your_graveyard_per_damage_prevented():
    scenario = _board(
        alice=["Immortal Coil"],
        bob=["Goblin Guide"],
        alice_graveyard=["Plains", "Island", "Swamp", "Forest"],
    )
    graveyard = list(scenario.player("alice").graveyard)
    scenario.will_choose_cards(*graveyard[:2])
    assert (
        _hit(scenario, scenario.player("alice"), 2, scenario.creature("Goblin Guide", "bob")) == 0
    )
    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").graveyard) == 2


def test_dralnu_sacrifices_that_many_permanents_instead_of_taking_the_damage():
    scenario = _board(
        alice=["Dralnu, Lich Lord", "Grizzly Bears", "Llanowar Elves"], bob=["Goblin Guide"]
    )
    dralnu = _on(scenario, "Dralnu, Lich Lord")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.will_choose_cards(bears, elves)
    assert _hit(scenario, dralnu, 2, scenario.creature("Goblin Guide", "bob")) == 0
    assert dralnu.damage == 0
    assert bears.zone is Zone.GRAVEYARD and elves.zone is Zone.GRAVEYARD


def test_phyrexian_vindicator_prevents_and_triggers_for_that_much_damage():
    scenario = _board(alice=["Phyrexian Vindicator"], bob=["Goblin Guide"])
    vindicator = _on(scenario, "Phyrexian Vindicator")
    assert _hit(scenario, vindicator, 4, scenario.creature("Goblin Guide", "bob")) == 0
    assert vindicator.damage == 0
    assert len(scenario.pending_triggers) == 1


# -- replaced combat damage to a player (Szadek, Undead Alchemist) -------------------------------


def test_szadek_puts_counters_on_itself_and_mills_the_player_instead_of_damaging():
    scenario = _board(alice=["Szadek, Lord of Secrets"], bob=[])
    szadek = _on(scenario, "Szadek, Lord of Secrets")
    assert _hit(scenario, scenario.player("bob"), 3, szadek, combat=True) == 0
    assert scenario.player("bob").life == 20
    assert _counters(szadek) == 3
    assert len(scenario.player("bob").library) == 0
    assert len(scenario.player("bob").graveyard) == 3
    # Noncombat damage, and damage to a creature, is dealt normally.
    assert _hit(scenario, scenario.player("bob"), 2, szadek) == 2


def test_undead_alchemist_mills_the_player_instead_of_damaging_for_zombies_you_control():
    scenario = _board(alice=["Undead Alchemist", "Putrid Leech"], bob=[])
    bob = scenario.player("bob")
    assert _hit(scenario, bob, 2, scenario.creature("Putrid Leech", "alice"), combat=True) == 0
    assert bob.life == 20
    assert len(bob.graveyard) == 2
    assert _hit(scenario, bob, 2, scenario.creature("Putrid Leech", "alice")) == 2  # noncombat
    assert (
        _hit(
            scenario,
            scenario.player("alice"),
            2,
            scenario.creature("Putrid Leech", "alice"),
            combat=True,
        )
        == 0
    )


# -- damage that can't be prevented --------------------------------------------------------------


@pytest.mark.parametrize("holder", ["Excruciator", "Malignus"])
def test_damage_dealt_by_this_creature_cant_be_prevented(holder):
    scenario = _board(alice=[holder, "Grizzly Bears"], bob=["Solitary Confinement"])
    bob = scenario.player("bob")
    assert _hit(scenario, bob, 3, _on(scenario, holder)) == 3  # Solitary Confinement cannot stop it
    # Any other source's damage is still prevented (CR 615.12 only exempts this creature's).
    assert _hit(scenario, bob, 3, scenario.creature("Grizzly Bears", "alice")) == 0


def test_questing_beast_makes_combat_damage_by_your_creatures_unpreventable():
    scenario = _board(alice=["Questing Beast", "Grizzly Bears"], bob=["Solitary Confinement"])
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _hit(scenario, bob, 2, bears, combat=True) == 2
    assert _hit(scenario, bob, 2, bears) == 0  # noncombat damage is still preventable


# -- exert as it attacks, then prevent combat damage to it (CR 701.43d, CR 508.1g) -----------------


def _attack_with_the_avenger(exert: bool):
    scenario = _board(alice=["Oketra's Avenger"], bob=["Goblin Guide"])
    avenger = _on(scenario, "Oketra's Avenger")
    avenger.summoning_sick = False
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(exert)
    scenario.attack_with(avenger, defending="bob")
    return scenario, avenger, guide


def test_exerting_the_avenger_as_it_attacks_prevents_combat_damage_dealt_to_it():
    scenario, avenger, guide = _attack_with_the_avenger(exert=True)

    assert avenger.exerted
    assert scenario.stack_names() == ["Oketra's Avenger's triggered ability"]  # CR 603.12
    scenario.resolve_top()
    scenario.block(avenger, guide)
    scenario.combat_damage()

    assert avenger.zone is Zone.BATTLEFIELD
    assert avenger.damage == 0  # the Guide's combat damage to it was prevented
    assert guide.zone is Zone.GRAVEYARD or guide.damage == 3  # the Avenger still deals its own


def test_the_avenger_attacking_without_exerting_takes_the_damage():
    scenario, avenger, guide = _attack_with_the_avenger(exert=False)

    assert not avenger.exerted
    assert scenario.stack_names() == []
    scenario.block(avenger, guide)
    scenario.combat_damage()

    assert avenger.damage == 2 or avenger.zone is Zone.GRAVEYARD


def test_the_avengers_prevention_covers_combat_damage_only():
    scenario, avenger, guide = _attack_with_the_avenger(exert=True)
    scenario.resolve_top()

    assert _hit(scenario, avenger, 1, guide) == 1  # noncombat damage is dealt
    assert _hit(scenario, avenger, 5, guide, combat=True) == 0


# -- prevention abilities a static grants (CR 113.10a) --------------------------------------


def test_security_blockade_gives_the_enchanted_land_a_tap_ability_that_prevents_damage_to_you():
    scenario = _board(alice=["Security Blockade", "Forest"], bob=["Goblin Guide"])
    forest = _on(scenario, "Forest")
    _on(scenario, "Security Blockade").attach_to(forest)
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.activate(forest, index=1)
    scenario.resolve_top()

    assert forest.tapped
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 2  # CR 615.7: the next 1 damage
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 3  # the shield is spent

"""EP-02 R3 T4: the graveyard-return and exile-play members of the library
amounts task.

Rules, each read in full with `mise run rules:find` in this session:

- CR 609.4b - "mana of any type can be spent" to cast a spell.
- CR 611.2a - a continuous effect from a resolving spell lasts as stated
  ("until the end of your next turn").
- CR 115.6 - "up to" a number of targets, zero allowed.
- CR 115.3 - the same object cannot be chosen twice for one instance of the
  word "target".
- CR 105.2 - an object is one or more of the five colors, or none.
- CR 400.7 - an object that changes zone is a new object.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import PlayedScenario, Scenario

BLOODSOAKED = "Bloodsoaked Insight // Sanguine Morass"


def _board(
    *,
    hand=(),
    battlefield=(),
    library=("Island",) * 8,
    graveyard=(),
    bob_battlefield=(),
    bob_library=("Island",) * 8,
    bob_graveyard=(),
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(battlefield),
            library=list(library),
            graveyard=list(graveyard),
        )
        .player(
            "bob",
            battlefield=list(bob_battlefield),
            library=list(bob_library),
            graveyard=list(bob_graveyard),
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# --------------------------------------------------------------------------
# Bloodsoaked Insight: "Target opponent exiles the top three cards of their
# library. Until the end of your next turn, you may play those cards. If you
# cast a spell this way, mana of any type can be spent to cast it."
# --------------------------------------------------------------------------


def _insight(bob_library, extra=()):
    scenario = _board(
        hand=[BLOODSOAKED], battlefield=["Swamp"] * 7 + list(extra), bob_library=bob_library
    )
    spell = scenario.cast_and_resolve(
        BLOODSOAKED, *scenario.untapped_sources(*["Swamp"] * 7), targets=["bob"]
    )
    return scenario, spell


LIBRARY = ["Lightning Bolt", "Forest", "Grizzly Bears", "Island", "Island"]


def test_bloodsoaked_insight_exiles_three_from_the_opponent_and_grants_alice_play():
    scenario, _ = _insight(LIBRARY)
    exiled = sorted(state.name for state in scenario.game.exile)
    assert exiled == ["Forest", "Grizzly Bears", "Lightning Bolt"]
    assert len(scenario.player("bob").library) == 2
    for state in scenario.game.exile:
        permission = scenario.game.play_permission_for(state, "alice")
        assert permission is not None
        assert permission.expires_end_of_next_turn is True
        assert permission.any_type_mana is True
        assert scenario.game.play_permission_for(state, "bob") is None


def test_bloodsoaked_insight_exiled_spell_is_cast_with_mana_of_any_type():
    scenario, _ = _insight(LIBRARY, extra=["Plains", "Plains"])
    bears = next(state for state in scenario.game.exile if state.name == "Grizzly Bears")
    casting = scenario.cast("Grizzly Bears", from_zone=Zone.EXILE)
    casting.use_permission()
    paying = casting.begin_paying()
    scenario.pay_with(paying, *scenario.untapped_sources("Plains", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD, "{1}{G} paid with two Plains: any type (CR 609.4b)"


def test_bloodsoaked_insight_exiled_land_is_played():
    scenario, _ = _insight(LIBRARY)
    forest = next(state for state in scenario.game.exile if state.name == "Forest")
    scenario.play_land("Forest", from_zone=Zone.EXILE)
    assert forest.zone is Zone.BATTLEFIELD


def test_bloodsoaked_insight_with_a_short_library_exiles_what_there_is():
    scenario, _ = _insight(["Lightning Bolt", "Forest"])
    assert sorted(state.name for state in scenario.game.exile) == ["Forest", "Lightning Bolt"]


# --------------------------------------------------------------------------
# Orzhov Charm modes 1 and 2; Hubris and Essence Reliquary prove the
# "and all Auras attached to it" return on a second spell and an ability.
# --------------------------------------------------------------------------

ORZHOV = "Orzhov Charm"
RETURN_MODE = "Return target creature you control and all Auras you control attached to it"
DESTROY_MODE = "Destroy target creature and you lose life equal to its toughness"


def _charm(mode, target, *, battlefield=(), bob_battlefield=(), pre=None):
    scenario = _board(
        hand=[ORZHOV],
        battlefield=["Plains", "Swamp", *battlefield],
        bob_battlefield=list(bob_battlefield),
    )
    if pre is not None:
        pre(scenario)
    casting = scenario.cast(ORZHOV, "alice")
    casting.choose_modes([mode])
    casting.choose_targets([target(scenario)])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def _aura(scenario, name, host, owner):
    aura = scenario.find(name, Zone.BATTLEFIELD, owner)
    aura.attach_to(host)
    return aura


def test_orzhov_charm_returns_the_creature_and_the_auras_you_control():
    def pre(scenario):
        scenario.rancor = _aura(scenario, "Rancor", scenario.creature("Grizzly Bears"), "alice")

    scenario = _charm(
        RETURN_MODE,
        lambda s: s.creature("Grizzly Bears"),
        battlefield=["Grizzly Bears", "Rancor"],
        pre=pre,
    )
    assert _names(scenario, Zone.HAND) == ["Grizzly Bears", "Rancor"]
    assert scenario.rancor.zone is Zone.HAND


def test_orzhov_charm_leaves_an_opponents_aura_to_fall_off():
    def pre(scenario):
        scenario.rancor = _aura(scenario, "Rancor", scenario.creature("Grizzly Bears"), "alice")
        scenario.pacifism = _aura(
            scenario, "Pacifism", scenario.creature("Grizzly Bears"), "bob"
        )

    scenario = _charm(
        RETURN_MODE,
        lambda s: s.creature("Grizzly Bears"),
        battlefield=["Grizzly Bears", "Rancor"],
        bob_battlefield=["Pacifism"],
        pre=pre,
    )
    assert scenario.rancor.zone is Zone.HAND
    assert scenario.pacifism.zone is Zone.GRAVEYARD, "CR 704.5m: it was not returned, so it fell off"
    assert _names(scenario, Zone.HAND) == ["Grizzly Bears", "Rancor"]


def test_orzhov_charm_return_mode_with_no_auras_returns_just_the_creature():
    scenario = _charm(RETURN_MODE, lambda s: s.creature("Hill Giant"), battlefield=["Hill Giant"])
    assert _names(scenario, Zone.HAND) == ["Hill Giant"]


def test_orzhov_charm_destroys_and_loses_life_equal_to_toughness():
    scenario = _charm(
        DESTROY_MODE,
        lambda s: s.creature("Hill Giant", "bob"),
        bob_battlefield=["Hill Giant"],
    )
    assert _names(scenario, Zone.GRAVEYARD, "bob") == ["Hill Giant"]
    assert scenario.player("alice").life == 20 - 3
    assert scenario.player("bob").life == 20


def test_orzhov_charm_loses_life_even_when_the_creature_survives():
    scenario = _charm(
        DESTROY_MODE,
        lambda s: s.creature("Darksteel Myr", "bob"),
        bob_battlefield=["Darksteel Myr"],
    )
    assert _battlefield(scenario, "bob") == ["Darksteel Myr"]
    assert scenario.player("alice").life == 20 - 1


def test_hubris_returns_every_aura_attached_whoever_controls_it():
    scenario = _board(
        hand=["Hubris"],
        battlefield=["Island", "Island", "Grizzly Bears", "Rancor"],
        bob_battlefield=["Pacifism"],
    )
    bears = scenario.creature("Grizzly Bears")
    rancor = _aura(scenario, "Rancor", bears, "alice")
    pacifism = _aura(scenario, "Pacifism", bears, "bob")
    scenario.cast_and_resolve(
        "Hubris", *scenario.untapped_sources("Island", "Island"), targets=[bears]
    )
    assert bears.zone is Zone.HAND
    assert rancor.zone is Zone.HAND
    assert pacifism.zone is Zone.HAND, "owner's hand: Pacifism is bob's"
    assert pacifism.owner == "bob"


def test_essence_reliquary_returns_another_permanent_and_your_auras():
    scenario = _board(battlefield=["Essence Reliquary", "Grizzly Bears", "Rancor"])
    bears = scenario.creature("Grizzly Bears")
    rancor = _aura(scenario, "Rancor", bears, "alice")
    reliquary = scenario.find("Essence Reliquary", Zone.BATTLEFIELD, "alice")
    scenario.activate(reliquary, targets=[bears])
    scenario.resolve_top()
    assert bears.zone is Zone.HAND
    assert rancor.zone is Zone.HAND
    assert reliquary.zone is Zone.BATTLEFIELD


def _names(scenario, zone, username="alice"):
    return sorted(state.name for state in getattr(scenario.player(username), zone.value))


def _battlefield(scenario, username):
    return sorted(
        state.name
        for state in scenario.game.permanents_controlled_by(username)
    )


# --------------------------------------------------------------------------
# All Suns' Dawn / Rogues' Gallery: "For each color, return up to one target
# [creature] card of that color from your graveyard to your hand."
# --------------------------------------------------------------------------

ALL_SUNS = "All Suns' Dawn"
GALLERY = "Rogues' Gallery"
COLOURED = ["Goldmeadow Harrier", "Sage of Fables", "Bloodghast", "Ash Zealot", "Grizzly Bears"]


def _per_color(spell, mana, graveyard, chosen):
    scenario = _board(hand=[spell], battlefield=mana, graveyard=graveyard)
    states = [
        next(s for s in scenario.player("alice").graveyard if s.name == name) for name in chosen
    ]
    casting = scenario.cast(spell, "alice")
    casting.choose_targets(states)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*mana))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario, casting


def test_rogues_gallery_returns_one_creature_of_each_color():
    scenario, _ = _per_color(GALLERY, ["Swamp"] * 3, COLOURED, COLOURED)
    assert _names(scenario, Zone.HAND) == sorted(COLOURED)
    assert _names(scenario, Zone.GRAVEYARD) == [GALLERY]


def test_rogues_gallery_may_return_fewer_than_five():
    scenario, _ = _per_color(GALLERY, ["Swamp"] * 3, COLOURED, ["Bloodghast"])
    assert _names(scenario, Zone.HAND) == ["Bloodghast"]
    assert len(scenario.player("alice").graveyard) == 5


def test_rogues_gallery_may_return_nothing():
    scenario, _ = _per_color(GALLERY, ["Swamp"] * 3, COLOURED, [])
    assert _names(scenario, Zone.HAND) == []


def test_rogues_gallery_refuses_two_cards_of_one_color():
    scenario = _board(hand=[GALLERY], battlefield=["Swamp"] * 3, graveyard=[*COLOURED, "Hill Giant"])
    zealot = next(s for s in scenario.player("alice").graveyard if s.name == "Ash Zealot")
    giant = next(s for s in scenario.player("alice").graveyard if s.name == "Hill Giant")
    casting = scenario.cast(GALLERY, "alice")
    with pytest.raises(ValueError):
        casting.choose_targets([zealot, giant])


def test_rogues_gallery_a_multicolored_card_answers_one_color_only():
    scenario = _board(
        hand=[GALLERY], battlefield=["Swamp"] * 3, graveyard=["Kitchen Finks", "Grizzly Bears"]
    )
    finks = next(s for s in scenario.player("alice").graveyard if s.name == "Kitchen Finks")
    bears = next(s for s in scenario.player("alice").graveyard if s.name == "Grizzly Bears")
    casting = scenario.cast(GALLERY, "alice")
    casting.choose_targets([finks, bears])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert _names(scenario, Zone.HAND) == ["Grizzly Bears", "Kitchen Finks"]


def test_rogues_gallery_refuses_a_noncreature_card():
    scenario = _board(hand=[GALLERY], battlefield=["Swamp"] * 3, graveyard=["Lightning Bolt"])
    bolt = next(s for s in scenario.player("alice").graveyard if s.name == "Lightning Bolt")
    casting = scenario.cast(GALLERY, "alice")
    with pytest.raises(ValueError):
        casting.choose_targets([bolt])


def test_all_suns_dawn_returns_any_card_of_each_color_and_exiles_itself():
    graveyard = ["Goldmeadow Harrier", "Sage of Fables", "Dark Ritual", "Lightning Bolt", "Rancor"]
    scenario, _ = _per_color(ALL_SUNS, ["Forest"] * 5, graveyard, graveyard)
    assert _names(scenario, Zone.HAND) == sorted(graveyard)
    assert [state.name for state in scenario.game.exile] == [ALL_SUNS]
    assert _names(scenario, Zone.GRAVEYARD) == []


def test_all_suns_dawn_leaves_other_players_graveyards_alone():
    scenario = _board(
        hand=[ALL_SUNS],
        battlefield=["Forest"] * 5,
        graveyard=["Dark Ritual"],
        bob_graveyard=["Lightning Bolt"],
    )
    bolt = next(s for s in scenario.player("bob").graveyard if s.name == "Lightning Bolt")
    casting = scenario.cast(ALL_SUNS, "alice")
    with pytest.raises(ValueError):
        casting.choose_targets([bolt])


# --------------------------------------------------------------------------
# Thwart the Grave: "Return target creature card and up to one target Cleric,
# Rogue, Warrior, or Wizard creature card from your graveyard to the battlefield."
# --------------------------------------------------------------------------

THWART = "Thwart the Grave"


def _thwart(graveyard, chosen, battlefield=()):
    scenario = _board(
        hand=[THWART], battlefield=["Swamp"] * 6 + list(battlefield), graveyard=graveyard
    )
    states = [
        next(s for s in scenario.player("alice").graveyard if s.name == name) for name in chosen
    ]
    casting = scenario.cast(THWART, "alice")
    casting.choose_targets(states)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Swamp"] * 6))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def test_thwart_the_grave_returns_both_targets_to_the_battlefield():
    scenario = _thwart(["Grizzly Bears", "Ash Zealot"], ["Grizzly Bears", "Ash Zealot"])
    assert {"Ash Zealot", "Grizzly Bears"} <= set(_battlefield(scenario, "alice"))
    assert _names(scenario, Zone.GRAVEYARD) == [THWART]


def test_thwart_the_grave_second_target_is_optional():
    scenario = _thwart(["Grizzly Bears", "Ash Zealot"], ["Grizzly Bears"])
    assert "Grizzly Bears" in _battlefield(scenario, "alice")
    assert _names(scenario, Zone.GRAVEYARD) == ["Ash Zealot", THWART]


def test_thwart_the_grave_second_target_must_be_in_the_party():
    scenario = _board(
        hand=[THWART], battlefield=["Swamp"] * 6, graveyard=["Grizzly Bears", "Goldmeadow Harrier"]
    )
    bears = next(s for s in scenario.player("alice").graveyard if s.name == "Grizzly Bears")
    harrier = next(s for s in scenario.player("alice").graveyard if s.name == "Goldmeadow Harrier")
    casting = scenario.cast(THWART, "alice")
    with pytest.raises(ValueError):
        casting.choose_targets([bears, harrier])


def test_thwart_the_grave_costs_one_less_per_party_member():
    scenario = _board(
        hand=[THWART],
        battlefield=["Swamp"] * 4 + ["Kitsune Bonesetter", "Ash Zealot"],
        graveyard=["Grizzly Bears"],
    )
    casting = scenario.cast(THWART, "alice")
    bears = next(s for s in scenario.player("alice").graveyard if s.name == "Grizzly Bears")
    casting.choose_targets([bears])
    assert str(casting.total_cost.mana) == "{2}{B}{B}"


# --------------------------------------------------------------------------
# Venom, Lethal Protector: "Whenever Venom attacks, you may sacrifice another
# creature. If you do, draw X cards, then you may put a permanent card with
# mana value X or less from your hand onto the battlefield, where X is the
# sacrificed creature's mana value."
# --------------------------------------------------------------------------

EDDIE = "Eddie Brock // Venom, Lethal Protector"


def _venom(*, hand=(), library=("Island",) * 8, battlefield=("Grizzly Bears",)):
    scenario = _board(
        hand=hand, battlefield=[EDDIE, *battlefield], library=library
    )
    scenario.find(EDDIE, Zone.BATTLEFIELD, "alice").transform()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _attack(scenario, *, sacrifice=None, put=None):
    venom = next(s for s in scenario.game.battlefield if s.name == "Venom, Lethal Protector")
    scenario.will_take_the_may(sacrifice is not None, username="alice")
    if sacrifice is not None:
        scenario.will_choose_cards(sacrifice, username="alice")
    if put is not None:
        scenario.will_choose_cards(put, username="alice")
    scenario.attack_with(venom)
    _resolve_all(scenario)


def _hand_card(scenario, name):
    return next(s for s in scenario.player("alice").hand if s.name == name)


def test_venom_sacrifice_draws_x_then_puts_a_card_with_mana_value_x_or_less():
    scenario = _venom(hand=["Hill Giant", "Elite Vanguard", "Lightning Bolt"])
    bears = scenario.creature("Grizzly Bears")
    vanguard = _hand_card(scenario, "Elite Vanguard")
    _attack(scenario, sacrifice=bears, put=vanguard)
    assert bears.zone is Zone.GRAVEYARD
    assert vanguard.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == 2 + 2, "Giant, Bolt, and the two drawn Islands"
    assert _hand_card(scenario, "Hill Giant").zone is Zone.HAND, "mana value 3 exceeds X=2"


def test_venom_does_not_offer_cards_above_x_or_noncards_of_the_wrong_kind():
    scenario = _venom(hand=["Hill Giant", "Lightning Bolt"])
    bears = scenario.creature("Grizzly Bears")
    _attack(scenario, sacrifice=bears)
    offered = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_CARDS and "mana value 2 or less" in q.prompt
    ]
    assert len(offered) == 1
    names = sorted(s.name for s in scenario.all_card_states() if s.id in set(offered[0].cards))
    assert names == ["Island", "Island"], "neither the Giant (3) nor the Bolt (not a permanent)"


def test_venom_may_put_a_card_it_just_drew():
    scenario = _venom(library=["Elite Vanguard", "Island", "Island"])
    bears = scenario.creature("Grizzly Bears")
    vanguard = next(s for s in scenario.player("alice").library if s.name == "Elite Vanguard")
    _attack(scenario, sacrifice=bears, put=vanguard)
    assert vanguard.zone is Zone.BATTLEFIELD


def test_venom_declining_the_sacrifice_draws_nothing():
    scenario = _venom(hand=["Hill Giant"])
    bears = scenario.creature("Grizzly Bears")
    _attack(scenario, sacrifice=None)
    assert bears.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == 1


def test_venom_sacrificing_a_mana_value_zero_creature_draws_none_and_may_put_a_land():
    scenario = _venom(hand=["Forest", "Hill Giant"], battlefield=["Memnite"])
    memnite = scenario.creature("Memnite")
    forest = _hand_card(scenario, "Forest")
    _attack(scenario, sacrifice=memnite, put=forest)
    assert forest.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == 1


# --------------------------------------------------------------------------
# Kaya, Spirits' Justice
# --------------------------------------------------------------------------

KAYA = "Kaya, Spirits' Justice"


def _kaya(*, battlefield=("Grizzly Bears",), graveyard=(), bob_battlefield=(), bob_graveyard=(), library=("Island",) * 8):
    scenario = _board(
        battlefield=[KAYA, *battlefield],
        graveyard=graveyard,
        bob_battlefield=bob_battlefield,
        bob_graveyard=bob_graveyard,
        library=library,
    )
    return scenario, scenario.find(KAYA, Zone.BATTLEFIELD, "alice")


def _token(scenario, name, username="alice"):
    state = scenario.creature(name, username)
    state.token = True
    return state


def test_kaya_plus_two_surveils_then_exiles_a_card_from_a_graveyard():
    scenario, kaya = _kaya(graveyard=["Lightning Bolt"], library=["Island", "Forest", "Swamp"])
    bolt = next(s for s in scenario.player("alice").graveyard if s.name == "Lightning Bolt")
    scenario.will_choose_cards(bolt, username="alice", source=KAYA)
    scenario.activate(kaya, index=0)
    _resolve_all(scenario)
    assert bolt.zone is Zone.EXILE
    surveils = [q for q in scenario.questions_asked() if q.source == KAYA]
    assert surveils, "the surveil looked at the top two cards"


def test_kaya_plus_two_exiles_from_an_opponents_graveyard_too():
    scenario, kaya = _kaya(bob_graveyard=["Hill Giant"])
    giant = next(s for s in scenario.player("bob").graveyard if s.name == "Hill Giant")
    scenario.will_choose_cards(giant, username="alice", source=KAYA)
    scenario.activate(kaya, index=0)
    _resolve_all(scenario)
    assert giant.zone is Zone.EXILE


def test_kaya_minus_two_exiles_my_creature_and_one_creature_of_each_other_player():
    scenario, kaya = _kaya(bob_battlefield=["Hill Giant"])
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.activate(kaya, index=2, targets=[bears, giant])
    _resolve_all(scenario)
    assert bears.zone is Zone.EXILE
    assert giant.zone is Zone.EXILE


def test_kaya_minus_two_may_exile_none_of_the_other_players_creatures():
    scenario, kaya = _kaya(bob_battlefield=["Hill Giant"])
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.activate(kaya, index=2, targets=[bears])
    _resolve_all(scenario)
    assert bears.zone is Zone.EXILE
    assert giant.zone is Zone.BATTLEFIELD


def test_kaya_minus_two_refuses_my_own_creature_as_the_other_players_target():
    scenario, kaya = _kaya(battlefield=["Grizzly Bears", "Memnite"])
    with pytest.raises(ValueError):
        scenario.activate(
            kaya,
            index=2,
            targets=[scenario.creature("Grizzly Bears"), scenario.creature("Memnite")],
        )


def test_kaya_trigger_copies_an_exiled_creature_onto_a_token_with_flying():
    scenario, kaya = _kaya(battlefield=["Serra Angel", "Hill Giant"])
    angel = scenario.creature("Serra Angel")
    token = _token(scenario, "Hill Giant")
    scenario.will_choose_targets(token, username="alice")
    scenario.will_choose_cards(angel, username="alice", source=KAYA)
    scenario.activate(kaya, index=2, targets=[angel])
    _resolve_all(scenario)
    assert angel.zone is Zone.EXILE
    chars = scenario.game.characteristics_of(token)
    assert chars.name == "Serra Angel"
    assert has_keyword(token, "flying", scenario.game)
    assert has_keyword(token, "vigilance", scenario.game)


def test_kaya_trigger_gives_the_token_flying_even_when_the_card_had_none():
    scenario, kaya = _kaya(battlefield=["Grizzly Bears", "Hill Giant"])
    bears = scenario.creature("Grizzly Bears")
    token = _token(scenario, "Hill Giant")
    scenario.will_choose_targets(token, username="alice")
    scenario.will_choose_cards(bears, username="alice", source=KAYA)
    scenario.activate(kaya, index=2, targets=[bears])
    _resolve_all(scenario)
    chars = scenario.game.characteristics_of(token)
    assert chars.name == "Grizzly Bears"
    assert has_keyword(token, "flying", scenario.game), "the stated exception"


def test_kaya_trigger_copy_ends_at_end_of_turn():
    scenario, kaya = _kaya(battlefield=["Grizzly Bears", "Hill Giant"])
    bears = scenario.creature("Grizzly Bears")
    token = _token(scenario, "Hill Giant")
    scenario.will_choose_targets(token, username="alice")
    scenario.will_choose_cards(bears, username="alice", source=KAYA)
    scenario.activate(kaya, index=2, targets=[bears])
    _resolve_all(scenario)
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    assert scenario.game.characteristics_of(token).name == "Hill Giant"


def test_kaya_trigger_may_choose_no_card():
    scenario, kaya = _kaya(battlefield=["Grizzly Bears", "Hill Giant"])
    bears = scenario.creature("Grizzly Bears")
    token = _token(scenario, "Hill Giant")
    scenario.will_choose_targets(token, username="alice")
    scenario.will_choose_cards(username="alice", source=KAYA)
    scenario.activate(kaya, index=2, targets=[bears])
    _resolve_all(scenario)
    assert scenario.game.characteristics_of(token).name == "Hill Giant"


def test_kaya_trigger_fires_for_a_creature_card_exiled_from_my_graveyard():
    scenario, kaya = _kaya(battlefield=["Hill Giant"], graveyard=["Serra Angel"])
    angel = next(s for s in scenario.player("alice").graveyard if s.name == "Serra Angel")
    token = _token(scenario, "Hill Giant")
    scenario.will_choose_cards(angel, username="alice", source=KAYA)
    scenario.will_choose_targets(token, username="alice")
    scenario.will_choose_cards(angel, username="alice", source=KAYA)
    scenario.activate(kaya, index=0)
    _resolve_all(scenario)
    assert angel.zone is Zone.EXILE
    assert scenario.game.characteristics_of(token).name == "Serra Angel"


def test_kaya_trigger_ignores_an_opponents_creature_or_graveyard_card():
    scenario, kaya = _kaya(
        battlefield=["Hill Giant"], bob_battlefield=["Grizzly Bears"], bob_graveyard=["Serra Angel"]
    )
    token = _token(scenario, "Hill Giant")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.exile_cards([bears, *scenario.player("bob").graveyard])
    scenario.game.announce_batched_events()
    scenario.game.put_triggers_on_stack()
    assert not scenario.game.stack
    assert scenario.game.characteristics_of(token).name == "Hill Giant"


def test_kaya_trigger_does_not_fire_for_a_noncreature_card_from_my_graveyard():
    scenario, kaya = _kaya(battlefield=["Hill Giant"], graveyard=["Lightning Bolt"])
    _token(scenario, "Hill Giant")
    scenario.game.exile_cards(list(scenario.player("alice").graveyard))
    scenario.game.announce_batched_events()
    scenario.game.put_triggers_on_stack()
    assert not scenario.game.stack


def test_kaya_trigger_is_one_event_for_creatures_and_cards_exiled_together():
    scenario, kaya = _kaya(battlefield=["Grizzly Bears", "Memnite", "Hill Giant"], graveyard=["Serra Angel"])
    _token(scenario, "Hill Giant")
    batch = [
        scenario.creature("Grizzly Bears"),
        scenario.creature("Memnite"),
        *scenario.player("alice").graveyard,
    ]
    scenario.game.exile_cards(batch)
    scenario.game.announce_batched_events()
    scenario.game.put_triggers_on_stack()
    kaya_abilities = [obj for obj in scenario.game.stack if getattr(obj, "source_name", "") == KAYA]
    assert len(kaya_abilities) == 1
    assert len(kaya_abilities[0].event.batch_ids) == 3


def test_kaya_trigger_a_token_exiled_gives_no_card_to_choose():
    scenario, kaya = _kaya(battlefield=["Hill Giant", "Memnite"])
    token = _token(scenario, "Hill Giant")
    memnite = _token(scenario, "Memnite")
    scenario.will_choose_targets(token, username="alice")
    scenario.activate(kaya, index=2, targets=[memnite])
    _resolve_all(scenario)
    asked = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_CARDS and "from among them" in q.prompt
    ]
    assert asked == []
    assert scenario.game.characteristics_of(token).name == "Hill Giant"

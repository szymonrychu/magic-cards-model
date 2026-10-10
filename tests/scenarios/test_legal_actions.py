"""Enumerating every legal action, and the categories the old probe missed.

`machines/legal_actions.legal_actions` is the second guarantee the library
owes: "decode any game state" is `Game`, this is "enumerate the legal actions
available to each player at that point". Its answers are written into an
append-only log beside every action a seat takes, so what matters here is
threefold - that the list is *exactly* right on a board small enough to write
the whole answer down, that each category the API's own probe never covered
now appears, and that asking the question changes nothing.

Every CR number this file writes is one already cited, and verified, by the
engine code it exercises (`why_cannot_play_land`, `MarkedExile.plot/foretell/
suspend`, `why_cannot_turn_face_up`, `why_cannot_dredge`, `can_attack`/
`can_block`, CR 117.3d/104.3a, CR 118.6/118.6a, CR 113.6j/113.6m, CR 508.1/508.1a,
CR 106.6 - looked up fresh with `mise run rules:find` in the session that
wrote this file, and again in the session that added the second review
pass's regression tests).
"""

import json
from uuid import NAMESPACE_OID, uuid5

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import AlternativeCostSource, PlayAction
from magic_cards_model.machines.cost import ComponentKind, CostComponent
from magic_cards_model.machines.decisions import Decision, DecisionKind, DecisionPending
from magic_cards_model.machines.legal_actions import (
    _candidate_pool_for,
    decision_answers,
    legal_actions,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.action import Action, ActionKind, Affordability
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import TargetRef
from magic_cards_model.support import in_target_formats
from tests.cards import pool
from tests.scenarios.harness import Scenario


def _kinds(actions: list[Action]) -> set[ActionKind]:
    return {action.kind for action in actions}


def _of_kind(actions: list[Action], kind: ActionKind) -> list[Action]:
    return [action for action in actions if action.kind is kind]


# -- the exact answer on a board small enough to write down -----------------


def test_a_known_board_enumerates_exactly_these_actions_and_no_others():
    """Two Mountains on the battlefield, a Bolt and a Mountain in hand: the
    whole answer is six actions, asserted exhaustively rather than "the ones
    somebody remembered to check".

    One `{T}: Add {R}` per Mountain (CR 605.1a), the Bolt for `{R}`
    (CR 601.2), the land drop (CR 305.1), and the two that are always legal
    and that the API's probe never listed - passing priority (CR 117.3d) and
    conceding (CR 104.3a). Not here: a second land drop, an activation on a
    card no one controls, or an action for bob (this asks only for alice).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt", "Mountain"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")

    assert len(actions) == 6, [a.kind for a in actions]
    assert _kinds(actions) == {
        ActionKind.PASS_PRIORITY,
        ActionKind.CONCEDE,
        ActionKind.CAST,
        ActionKind.PLAY_LAND,
        ActionKind.ACTIVATE_MANA,
    }
    (cast,) = _of_kind(actions, ActionKind.CAST)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    assert cast.card_id == bolt.id
    assert cast.mana_cost == "{R}"
    assert cast.affordable is Affordability.YES
    assert cast.rule == "CR 601.2"

    (land,) = _of_kind(actions, ActionKind.PLAY_LAND)
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    assert land.card_id == mountain.id
    assert land.land_face is None

    mana_actions = _of_kind(actions, ActionKind.ACTIVATE_MANA)
    assert len(mana_actions) == 2
    battlefield_mountains = {
        state.id for state in scenario.untapped_sources("Mountain", "Mountain", username="alice")
    }
    assert {action.card_id for action in mana_actions} == battlefield_mountains
    assert all(action.mana_cost is None for action in mana_actions)  # the cost is {T}, not mana
    assert all(action.affordable is Affordability.YES for action in mana_actions)


def test_the_enumeration_is_for_the_asking_player_only():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    alice_actions = legal_actions(scenario.game, "alice")
    bob_bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert bob_bolt.id not in {a.card_id for a in alice_actions}


# -- previously-missed categories, each proven against a real printing ------


def test_land_drop_includes_an_mdfc_land_face():
    """CR 712.12: an MDFC may be played for its land face - Witch Enchanter
    // Witch-Blessed Meadow, already the pool's own MDFC land test card."""
    scenario = Scenario().player("alice", hand=["Witch Enchanter"], library=["Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")
    land_actions = _of_kind(actions, ActionKind.PLAY_LAND)
    faces = {action.land_face for action in land_actions}
    assert "Witch-Blessed Meadow" in faces


def test_turning_a_face_down_permanent_face_up_appears():
    """CR 702.37e, off a permanent cast face down for {3} (CR 702.37a)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Brine Elemental"], battlefield=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Brine Elemental")
    casting.use_keyword("Morph")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * 3))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    actions = legal_actions(scenario.game, "alice")
    turn_up = _of_kind(actions, ActionKind.TURN_FACE_UP)
    assert len(turn_up) == 1
    assert turn_up[0].mana_cost == "{5}{U}{U}"


def test_suspend_foretell_and_plot_each_appear_as_their_own_action():
    suspend_scenario = (
        Scenario().player("alice", hand=["Living End"], battlefield=["Swamp"] * 4).build()
    )
    suspend_scenario.start_at(Step.PRECOMBAT_MAIN)
    suspend_actions = _of_kind(legal_actions(suspend_scenario.game, "alice"), ActionKind.SUSPEND)
    assert len(suspend_actions) == 1
    assert suspend_actions[0].rule == "CR 116.2f"

    foretell_scenario = (
        Scenario().player("alice", hand=["Lupine Harbingers"], battlefield=["Forest"] * 6).build()
    )
    foretell_scenario.start_at(Step.PRECOMBAT_MAIN)
    foretell_actions = _of_kind(legal_actions(foretell_scenario.game, "alice"), ActionKind.FORETELL)
    assert len(foretell_actions) == 1
    assert foretell_actions[0].rule == "CR 116.2h"

    plot_scenario = (
        Scenario()
        .player("alice", hand=["Slickshot Show-Off"], battlefield=["Mountain", "Mountain"])
        .build()
    )
    plot_scenario.start_at(Step.PRECOMBAT_MAIN)
    plot_actions = _of_kind(legal_actions(plot_scenario.game, "alice"), ActionKind.PLOT)
    assert len(plot_actions) == 1
    assert plot_actions[0].rule == "CR 116.2k"


def test_dredge_appears_for_a_graveyard_card():
    """CR 702.52a-b: Dakmor Salvage, dredge 5, with enough library to pay it."""
    scenario = (
        Scenario().player("alice", library=["Mountain"] * 6, graveyard=["Dakmor Salvage"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")
    dredge_actions = _of_kind(actions, ActionKind.DREDGE)
    assert len(dredge_actions) == 1
    assert dredge_actions[0].rule == "CR 702.52a"


def test_mana_ability_including_a_costed_one_appears_standalone():
    """Nurturing Peatland's only mana ability, `{T}, Pay 1 life: Add {B} or
    {G}.`, costs more than a bare `{T}` - `auto_tap` never spends it unasked
    (CR 118.3c), so it has to be its own `ACTIVATE_MANA` action for a seat to
    learn it can pay the life. Its other ability, `{1}, {T}, Sacrifice this
    land: Draw a card.`, is a real, honest demonstration of the same board
    read the other way: with no other mana source at all, that `{1}` cannot
    be auto-tapped from a source `auto_tap` was never allowed to reach for,
    and the engine's own withheld-source refusal says so by name."""
    scenario = Scenario().player("alice", battlefield=["Nurturing Peatland"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")
    mana_actions = _of_kind(actions, ActionKind.ACTIVATE_MANA)
    assert len(mana_actions) == 1
    costed = mana_actions[0]
    assert costed.cost is not None and "life" in costed.cost.lower()
    assert costed.affordable is Affordability.YES

    draw_actions = _of_kind(actions, ActionKind.ACTIVATE)
    assert len(draw_actions) == 1
    assert draw_actions[0].affordable is Affordability.NO
    assert "Nurturing Peatland" in (draw_actions[0].unaffordable_reason or "")


def test_off_battlefield_activation_covers_cycling_channel_and_gargadon():
    """CR 113.6j/113.6m: three different shapes of "functions off the
    battlefield", none of them a battlefield `ACTIVATE`."""
    cycling_scenario = Scenario().player("alice", hand=["Street Wraith"]).build()
    cycling_scenario.start_at(Step.PRECOMBAT_MAIN)
    cycling_actions = _of_kind(
        legal_actions(cycling_scenario.game, "alice"), ActionKind.ACTIVATE_OFF_ZONE
    )
    assert any(action.keyword and "cycling" in action.keyword.lower() for action in cycling_actions)

    # Boseiju, Who Endures's own Channel targets, and with nothing to name it
    # stays UNKNOWN (`test_boseiju_channel_appears_as_unknown_rather_than_vanishing`);
    # with a target it is priced (`test_activation_target_slots.py`). World
    # Breaker's graveyard-functioning ability targets nothing, so it proves
    # this category's ordinary, non-targeted shape here.
    world_breaker_scenario = (
        Scenario().player("alice", graveyard=["World Breaker"], battlefield=["Forest"] * 5).build()
    )
    world_breaker_scenario.start_at(Step.PRECOMBAT_MAIN)
    channel_actions = _of_kind(
        legal_actions(world_breaker_scenario.game, "alice"), ActionKind.ACTIVATE_OFF_ZONE
    )
    assert any(
        action.rule == "CR 113.6m" and action.from_zone is Zone.GRAVEYARD
        for action in channel_actions
    )

    from magic_cards_model.machines.casting import MarkedExile

    gargadon_scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Greater Gargadon"], battlefield=["Mountain", "Grizzly Bears"])
        .build()
    )
    gargadon_scenario.start_at(Step.PRECOMBAT_MAIN)
    gargadon = gargadon_scenario.find("Greater Gargadon", Zone.HAND, "alice")
    marked = MarkedExile.suspend(gargadon_scenario.game, gargadon, "alice")
    payment = marked.begin_paying()
    (mountain,) = gargadon_scenario.untapped_sources("Mountain")
    gargadon_scenario.pay_with(payment, mountain)
    marked.take()

    exile_actions = _of_kind(
        legal_actions(gargadon_scenario.game, "alice"), ActionKind.ACTIVATE_OFF_ZONE
    )
    assert any(action.rule == "CR 702.62b" for action in exile_actions)


def test_declare_attacker_and_blocker_are_per_pair_not_booleans():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    attacker_actions = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.DECLARE_ATTACKER)
    alice_bear = scenario.creature("Grizzly Bears", "alice")
    assert len(attacker_actions) == 1
    assert attacker_actions[0].card_id == alice_bear.id
    assert attacker_actions[0].defender == "bob"
    # bob is not the active player and nothing is attacking yet, so bob has
    # no declare-blocker action right now.
    assert not _of_kind(legal_actions(scenario.game, "bob"), ActionKind.DECLARE_BLOCKER)

    scenario.attack_with(alice_bear, defending="bob")
    scenario.advance("alice")  # into declare blockers

    blocker_actions = _of_kind(legal_actions(scenario.game, "bob"), ActionKind.DECLARE_BLOCKER)
    bob_bear = scenario.creature("Grizzly Bears", "bob")
    assert len(blocker_actions) == 1
    assert blocker_actions[0].card_id == bob_bear.id
    assert blocker_actions[0].attacker_id == alice_bear.id


def test_modal_and_x_actions_carry_a_parameter_space_not_an_enumeration():
    modal_scenario = (
        Scenario().player("alice", hand=["Cryptic Command"], battlefield=["Island"] * 4).build()
    )
    modal_scenario.start_at(Step.PRECOMBAT_MAIN)
    (cast,) = _of_kind(legal_actions(modal_scenario.game, "alice"), ActionKind.CAST)
    assert len(cast.modes) == 4

    x_scenario = (
        Scenario().player("alice", hand=["Green Sun's Zenith"], battlefield=["Forest"] * 4).build()
    )
    x_scenario.start_at(Step.PRECOMBAT_MAIN)
    (x_cast,) = _of_kind(legal_actions(x_scenario.game, "alice"), ActionKind.CAST)
    assert x_cast.x_range is not None
    # CR 107.3a / 107.1b: X=0 is a legal announcement, and {G} is payable.
    assert x_cast.affordable is Affordability.YES


def test_convoke_widens_a_no_into_an_honest_unknown():
    """CR 702.51a: Conclave Tribunal's convoke could pay part of `{3}{W}` by
    tapping Grizzly Bears, but this affordability check does not replicate
    `objects_as_costs.convoke`'s own reduction - `Game.object_cost_offers`
    says the offer exists, so a plain mana-only `NO` (no lands at all) is
    widened to `UNKNOWN` naming convoke, rather than a wrong `NO`."""
    scenario = (
        Scenario()
        .player("alice", hand=["Conclave Tribunal"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (cast,) = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.CAST)
    assert cast.affordable is Affordability.UNKNOWN
    assert "convoke" in (cast.unaffordable_reason or "")


def test_pitched_and_paid_are_two_actions_with_two_costs():
    """Force of Negation for `{1}{U}{U}` and pitched are two `CAST` actions
    with two different costs (CR 118.9a: only one is ever actually paid, but
    both are legal to announce)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob")
        .player("alice", hand=["Force of Negation", "Lightning Bolt"], battlefield=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"  # CR 118.9's own "if it's not your turn"

    casts = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.CAST)
    force = scenario.find("Force of Negation", Zone.HAND, "alice")
    force_casts = [action for action in casts if action.card_id == force.id]
    assert len(force_casts) == 2
    costs = {action.cost for action in force_casts}
    assert "{1}{U}{U}" in costs
    assert any(cost != "{1}{U}{U}" for cost in costs)


# -- regression tests: the review's findings 1, 2, 4, 5, 6, 8 ---------------


def test_cast_and_play_land_appear_under_a_play_permission_from_exile():
    """Findings 1 and 6, both on the same real printing. Wrenn's Resolve
    exiles a Bolt and a Mountain and grants each its own `PlayPermission`
    (CR 601.3) - `_cast_actions` used to build a printed-mana-cost action
    only for `Zone.HAND`, and none of `keyword_cast_options`/`marker_cast_
    options`/`granted_cast_options` ever hold a bare `PlayPermission`, so the
    Bolt got zero `CAST` actions even though `Game.cast` would accept it and
    `why_cannot_cast_from` already said yes; `_land_actions` was hard-gated
    to `Zone.HAND` and only ever called over `me.hand`, so the Mountain got
    zero `PLAY_LAND` actions even though `Game.play_land` already supports
    `PlayAction.PLAY` out of exile."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Wrenn's Resolve"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            library=["Lightning Bolt", "Mountain", "Island"],
        )
        .player("bob", library=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources("Mountain", "Mountain")
    before_exile = {state.id for state in scenario.game.exile}
    scenario.cast_and_resolve("Wrenn's Resolve", *mountains)
    exiled = [state for state in scenario.game.exile if state.id not in before_exile]
    assert sorted(state.name for state in exiled) == ["Lightning Bolt", "Mountain"]
    bolt = next(state for state in exiled if state.name == "Lightning Bolt")
    mountain = next(state for state in exiled if state.name == "Mountain")

    actions = legal_actions(scenario.game, "alice")

    bolt_casts = [a for a in _of_kind(actions, ActionKind.CAST) if a.card_id == bolt.id]
    assert len(bolt_casts) == 1
    assert bolt_casts[0].from_zone is Zone.EXILE
    assert bolt_casts[0].mana_cost == "{R}"

    mountain_plays = [
        a for a in _of_kind(actions, ActionKind.PLAY_LAND) if a.card_id == mountain.id
    ]
    assert len(mountain_plays) == 1
    assert mountain_plays[0].from_zone is Zone.EXILE


def test_a_card_with_no_mana_cost_is_not_affordable():
    """Finding 2: CR 118.6 - a card with no mana symbols at all (Living End,
    Ancestral Vision) has an unpayable cost, and CR 118.6 itself says
    attempting to *pay* one is illegal. Listing the `CAST` action is right
    (CR 118.6's own first sentence); `affordable=YES` from an empty
    `ManaCost` looking like a real `{0}` is wrong - it must be `NO`, carrying
    the same refusal `Game.cast` would raise."""
    for name, battlefield in (("Living End", ["Swamp"] * 4), ("Ancestral Vision", ["Island"] * 4)):
        scenario = Scenario().player("alice", hand=[name], battlefield=battlefield).build()
        scenario.start_at(Step.PRECOMBAT_MAIN)

        (cast,) = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.CAST)
        assert cast.cost is None, name
        assert cast.mana_cost is None, name
        assert cast.affordable is Affordability.NO, name
        assert cast.unaffordable_reason is not None and "CR 118.6" in cast.unaffordable_reason, name


def test_a_land_can_never_be_cast_and_never_gets_a_misleading_refusal():
    """Finding 7: `why_cannot_cast_now`/`why_cannot_cast_from`/`Casting`
    never checked a card had a castable type at all - a land in the active
    player's own main phase with an empty stack satisfied `Game.
    can_cast_sorcery` exactly the way a real spell would, so `Game.cast`
    went on to build a real `Casting` around a Mountain and only refused
    deep inside cost determination, with a CR 118.6 message that implies
    Suspend would let you cast a land - a lie. `legal_actions`'s own
    `_CASTABLE_TYPES` filter (finding 1's own predecessor) already keeps a
    land out of the enumeration; this is the real fix, at the source
    (`casting.py`'s `why_cannot_cast_a_land`, CR 305.1), so every consumer
    of `Game.cast` gets the honest reason and not the enumeration's guard
    alone."""
    scenario = Scenario().player("alice", hand=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.HAND, "alice")

    assert not _of_kind(legal_actions(scenario.game, "alice"), ActionKind.CAST)

    with pytest.raises(ValueError, match="is a land"):
        scenario.game.cast(mountain, "alice")


def test_split_card_and_adventure_each_emit_one_cast_action_per_face():
    """Finding 4: `Wear // Tear` prints one combined `mana_cost`
    (`{1}{R} // {W}`), which `ManaCost.parse` reads as converted mana value
    3 - not what either half alone costs (CR 709.3b). `Brazen Borrower` is
    the Adventure-shaped sibling bug: its own combined cost is
    `{1}{U}{U} // {1}{U}`, and the creature's plain cast and the Adventure
    half are two different `CAST` actions with two different costs, not one
    action with a fabricated combined one."""
    split_scenario = Scenario().player("alice", hand=["Wear // Tear"]).build()
    split_scenario.start_at(Step.PRECOMBAT_MAIN)
    split_casts = _of_kind(legal_actions(split_scenario.game, "alice"), ActionKind.CAST)
    assert len(split_casts) == 2
    by_face = {cast.spell_face: cast for cast in split_casts}
    assert set(by_face) == {"Wear", "Tear"}
    assert by_face["Wear"].mana_cost == "{1}{R}"
    assert by_face["Tear"].mana_cost == "{W}"

    adventure_scenario = Scenario().player("alice", hand=["Brazen Borrower"]).build()
    adventure_scenario.start_at(Step.PRECOMBAT_MAIN)
    adventure_casts = _of_kind(legal_actions(adventure_scenario.game, "alice"), ActionKind.CAST)
    assert len(adventure_casts) == 2
    by_face = {cast.spell_face: cast for cast in adventure_casts}
    assert set(by_face) == {None, "Petty Theft"}
    assert by_face[None].mana_cost == "{1}{U}{U}"
    assert by_face["Petty Theft"].mana_cost == "{1}{U}"


def test_all_untapped_attackers_are_enumerated_not_only_the_first():
    """Finding 5: `_attacker_actions` used to return `[]` outright once
    `game.combat.attacks` held anything - right for a creature already
    attacking, wrong for every other one, since `Game.declare_attacker` is a
    single-attacker entry point and `why_cannot_attack` still answers `None`
    for the rest."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    before = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.DECLARE_ATTACKER)
    assert {a.card_id for a in before} == {first.id, second.id}

    scenario.attack_with(first, defending="bob")

    after = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.DECLARE_ATTACKER)
    assert {a.card_id for a in after} == {second.id}


def test_boseiju_channel_appears_as_unknown_rather_than_vanishing():
    """Finding 8: `off_battlefield_activation` announces and checks targets
    as part of *building* the activation (`TargetingProfile.check`, which
    raises for too few targets before `.why_not()` is ever reached).
    Boseiju, Who Endures's Channel ("destroy target artifact, enchantment,
    or nonbasic land") is exactly this shape, and it is in the pool - an
    earlier pass here claimed no printing was, which was wrong. Swallowing
    the `ValueError` used to make the whole activation disappear from the
    list; it must appear instead, honestly `UNKNOWN`, naming the engine's
    own reason rather than a synthesized one."""
    scenario = Scenario().player("alice", hand=["Boseiju, Who Endures"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boseiju = scenario.find("Boseiju, Who Endures", Zone.HAND, "alice")

    actions = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.ACTIVATE_OFF_ZONE)
    # Channel's own cost, "Discard this card", can't be paid while Boseiju is
    # on the battlefield (there is nothing in hand to discard from the
    # battlefield), which is CR 113.6j's own shape - "a cost that can't be
    # paid while the object is on the battlefield" - not CR 113.6m's
    # (World Breaker's, below): that one is about an *effect* moving the
    # object, not the cost.
    channel = [a for a in actions if a.rule == "CR 113.6j"]
    assert len(channel) == 1
    assert channel[0].card_id == boseiju.id
    assert channel[0].affordable is Affordability.UNKNOWN
    assert channel[0].unaffordable_reason


def test_off_zone_activation_uses_a_restricted_mana_source_with_the_right_spend():
    """Finding 8's second bug: `_off_zone_actions` judged affordability with
    `spend=None`, and `ManaRestriction.allows(None)` fails closed (CR 106.6)
    for any source at all, always - so Sunken Citadel's own "Spend this
    mana only to activate abilities of land sources" mana was silently
    excluded from paying for Indatha Triome's land-sourced Cycling, even
    though CR 602.5 makes activating a cycling ability exactly the kind of
    activation that restriction names. Sunken Citadel alone can never
    produce all of Cycling {3} (its own second ability taps for only 2), so
    a Forest supplies the rest - the combination is only reachable at all
    once the restricted mana is actually considered."""
    from magic_cards_model.models.card_state import Choice, ChoiceKind
    from magic_cards_model.models.mana import Color

    scenario = (
        Scenario()
        .player("alice", hand=["Indatha Triome"], battlefield=["Sunken Citadel", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    citadel = scenario.find("Sunken Citadel", Zone.BATTLEFIELD, "alice")
    citadel.choice = Choice(kind=ChoiceKind.COLOR, value=Color.GREEN.value)

    actions = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.ACTIVATE_OFF_ZONE)
    cycling = [a for a in actions if a.keyword and "cycling" in a.keyword.lower()]
    assert len(cycling) == 1
    assert cycling[0].affordable is Affordability.YES, cycling[0].unaffordable_reason


# -- answering a pending decision --------------------------------------------


def test_pending_declare_attackers_offers_per_pair_actions_plus_declare_nobody():
    """Finding 3: `DECLARE_ATTACKERS`/`DECLARE_BLOCKERS` used to sit in
    `_BOOLEAN_DECISION_KINDS`, so `legal_options` (which has no branch for
    either) fell through to its own `(True, False)` catch-all - two
    `decision_option`s ("true"/"false") nothing downstream accepts - and the
    `pending` short-circuit made the real per-pair `_attacker_actions`
    unreachable for as long as the decision was outstanding. Now it offers
    the same per-pair actions `legal_actions` gives outside a pending
    decision, plus one "declare nobody" answer (CR 508.1's own "if any")."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.decisions.pause_when_unanswered = True
    bears = {state.id for state in scenario.game.permanents_controlled_by("alice")}

    with pytest.raises(DecisionPending) as excinfo:
        scenario.turn_based_actions()

    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.DECLARE_ATTACKERS

    actions = legal_actions(scenario.game, "alice", pending=pending)
    declare = _of_kind(actions, ActionKind.DECLARE_ATTACKER)
    assert {a.card_id for a in declare} == bears

    nobody = [a for a in actions if a.kind is ActionKind.ANSWER_DECISION]
    assert len(nobody) == 1
    assert nobody[0].decision_option == "declare_nobody"
    assert all(a.decision_seq == pending.seq for a in actions)


def test_pending_decision_gives_exactly_its_legal_answers():
    scenario = Scenario().player("alice", battlefield=["Mountain"]).build()
    game = scenario.game
    game.decisions.pause_when_unanswered = True
    decision = Decision(kind=DecisionKind.MAY, player="alice", prompt="do the thing")

    with pytest.raises(DecisionPending) as excinfo:
        game.ask(decision)

    pending = excinfo.value.pending
    actions = legal_actions(game, "alice", pending=pending)
    assert actions
    bare = decision_answers(pending.decision)
    assert actions == [a.model_copy(update={"decision_seq": pending.seq}) for a in bare]
    assert {a.decision_option for a in actions} == {"true", "false"}
    assert all(a.kind is ActionKind.ANSWER_DECISION for a in actions)
    assert all(a.decision_seq == pending.seq for a in actions)

    # Nobody else has anything legal while this is outstanding.
    assert legal_actions(game, "bob", pending=pending) == []


def test_pending_choose_players_offers_the_candidate_players_not_nothing():
    """`decision_answers` had no branch for `CHOOSE_PLAYERS` and the kind was
    not in `_BOOLEAN_DECISION_KINDS` either, so the function fell all the way
    through to its own `return []` - a pending proliferate's own player
    question (CR 701.34a's "any number of ... players") offered no legal
    action at all, hanging the game. Real pause path: `game.ask` itself
    raises `DecisionPending`, exactly as CR 701.34a's `Game.proliferate`
    reaches it - nothing here pre-scripts an answer."""
    scenario = Scenario().player("alice").player("bob").build()
    game = scenario.game
    game.decisions.pause_when_unanswered = True
    decision = Decision(
        kind=DecisionKind.CHOOSE_PLAYERS,
        player="alice",
        prompt="choose any number of players to proliferate",
        players=("alice", "bob"),
        amount=2,
        exact=False,
    )

    with pytest.raises(DecisionPending) as excinfo:
        game.ask(decision)

    pending = excinfo.value.pending
    actions = legal_actions(game, "alice", pending=pending)
    assert actions
    assert all(a.kind is ActionKind.ANSWER_DECISION for a in actions)
    (action,) = actions
    assert set(action.decision_player_candidates) == {"alice", "bob"}
    assert action.x_range == (0, 2)


# -- the two pure Game entry points requirement 4 asks for ------------------


def test_alternative_costs_for_finds_force_of_negations_pitch_without_a_casting():
    """`Game.alternative_costs_for` answers CR 118.9 before any `Casting`
    exists - no card moved to the stack, no rewind needed."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob")
        .player("alice", hand=["Force of Negation"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    force = scenario.find("Force of Negation", Zone.HAND, "alice")
    before = scenario.game.model_dump_json()

    options = scenario.game.alternative_costs_for(force, "alice")

    assert scenario.game.model_dump_json() == before  # asked no Casting into existence
    pitch = [option for option in options if option.available]
    assert pitch, [option.unavailable for option in options]
    assert "blue card" in pitch[0].description.lower()


def test_object_cost_offers_reads_convoke_eligibility():
    scenario = (
        Scenario()
        .player("alice", hand=["Conclave Tribunal"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Conclave Tribunal", Zone.HAND, "alice")
    bear = scenario.creature("Grizzly Bears", "alice")

    offers = scenario.game.object_cost_offers(card, "alice")

    assert "convoke" in offers
    assert bear.id in {candidate.id for candidate in offers["convoke"].candidates}


def test_improvise_widens_a_no_into_an_honest_unknown():
    """CR 702.126a: Kappa Cannoneer's improvise could pay part of `{5}{U}` by
    tapping an untapped artifact, but this affordability check does not
    replicate `objects_as_costs.improvise`'s own reduction - `Game.
    object_cost_offers` says the offer exists, so a plain mana-only `NO` (one
    Island cannot pay `{5}{U}` alone) is widened to `UNKNOWN` naming
    improvise, rather than a wrong `NO`. The same shape as `test_convoke_
    widens_a_no_into_an_honest_unknown` above."""
    scenario = (
        Scenario()
        .player("alice", hand=["Kappa Cannoneer"], battlefield=["Mishra's Bauble", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (cast,) = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.CAST)
    assert cast.affordable is Affordability.UNKNOWN
    assert "improvise" in (cast.unaffordable_reason or "")


def test_object_cost_offers_reads_improvise_eligibility():
    scenario = (
        Scenario()
        .player("alice", hand=["Kappa Cannoneer"], battlefield=["Mishra's Bauble", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Kappa Cannoneer", Zone.HAND, "alice")
    bauble = scenario.creature("Mishra's Bauble", "alice")

    offers = scenario.game.object_cost_offers(card, "alice")

    assert "improvise" in offers
    assert bauble.id in {candidate.id for candidate in offers["improvise"].candidates}


def test_alternative_costs_for_finds_the_permission_and_static_sources_too():
    """Finding 9: `play_permissions_on`'s PERMISSION options (cascade, Ugin's
    exiled cards) and `_static_free_cast_grants`'s STATIC options
    (Omniscience) are both pure over `(game, caster, card)` - an earlier
    pass here wrongly assumed both needed an in-flight `Casting`'s own
    state. Both are ported into `Game.alternative_costs_for` and both must
    actually surface through it."""
    permission_scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Mountain"])
        .player("bob")
        .build()
    )
    permission_scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = permission_scenario.find("Mountain", Zone.EXILE, "alice")
    permission_scenario.game.grant_play_permission(
        mountain, "alice", action=PlayAction.PLAY, pays_mana_cost=False, source_name="test rig"
    )
    permission_options = [
        option
        for option in permission_scenario.game.alternative_costs_for(mountain, "alice")
        if option.source is AlternativeCostSource.PERMISSION
    ]
    assert len(permission_options) == 1
    assert permission_options[0].source_name == "test rig"
    assert permission_options[0].available

    static_scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Omniscience"])
        .player("bob")
        .build()
    )
    static_scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = static_scenario.find("Lightning Bolt", Zone.HAND, "alice")
    static_options = [
        option
        for option in static_scenario.game.alternative_costs_for(bolt, "alice")
        if option.source is AlternativeCostSource.STATIC
    ]
    assert len(static_options) == 1
    assert static_options[0].source_name == "Omniscience"
    assert static_options[0].available


# -- Game.legal_targets ------------------------------------------------------


def test_game_legal_targets_enumerates_every_requirements_candidates():
    """`Game.legal_targets` had zero direct tests before this - it is the
    enumerating cousin of `legal_target`, which only rechecks one target
    already chosen. Lightning Bolt's "any target" requirement's legal
    candidates are every player and every creature/planeswalker/battle on
    the board."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bear = scenario.creature("Grizzly Bears", "bob")

    (candidates,) = scenario.game.legal_targets(bolt, "alice")

    assert scenario.player("alice") in candidates
    assert scenario.player("bob") in candidates
    assert bear in candidates


def test_game_legal_targets_is_empty_for_a_card_with_no_targeting_requirement():
    scenario = Scenario().player("alice", hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear_card = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    assert scenario.game.legal_targets(bear_card, "alice") == ()


def test_game_legal_targets_reads_only_the_chosen_modes_targets():
    """`Game._announcement_profile`'s `modes` branch had zero direct
    coverage - CR 700.2c: an unchosen mode's targets do not apply, so asking
    for Cryptic Command's "Return target permanent to its owner's hand"
    (mode 2) must offer permanents, without pulling in a mode never chosen."""
    scenario = (
        Scenario()
        .player("alice", hand=["Cryptic Command"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cryptic = scenario.find("Cryptic Command", Zone.HAND, "alice")
    bear = scenario.creature("Grizzly Bears", "bob")

    # Cryptic Command's own "Choose two" (CR 700.2a) needs two modes named -
    # mode 4 ("Draw a card") targets nothing, so the one requirement in the
    # result has to be mode 2's.
    (candidates,) = scenario.game.legal_targets(cryptic, "alice", modes=[2, 4])

    assert bear in candidates


def test_game_targetable_objects_spans_every_public_zone_and_the_stack():
    """`Game.targetable_objects` had zero direct tests - engine knowledge
    moved out of the api's own hardcoded walk, so a candidate list built off
    it can never drift from what the api's UI hints already assumed. Every
    player, a battlefield/graveyard/exile card, and a spell on the stack
    should all be present; a hand card should not (CR 400.2's own public
    zones exclude it)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Grizzly Bears"],
            graveyard=["Grizzly Bears"],
            exile=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"
    battlefield_bear = scenario.creature("Grizzly Bears", "alice")
    graveyard_bear = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    exile_bear = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    hand_bear = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    on_stack = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")

    things = scenario.game.targetable_objects()

    assert scenario.player("alice") in things
    assert scenario.player("bob") in things
    assert battlefield_bear in things
    assert graveyard_bear in things
    assert exile_bear in things
    assert on_stack in things
    assert hand_bear not in things


# -- a second exact-set assertion, wider ActionKind coverage -----------------


def test_a_richer_board_enumerates_exactly_these_actions_and_no_others():
    """The first exact-set test above covers 5 of 14 `ActionKind`s and would
    not have caught any of findings 1-6 - this board adds an exile
    permission (finding 1), a split card (finding 4), a dredger, and two
    attackers (finding 5), all during the declare attackers step on purpose:
    every one of the exile-permission cast, the split card's two instant
    halves, and the dredge are legal at any time with priority (CR 117.1a,
    CR 702.52), which is exactly what makes them coexist with a combat
    declaration in one board small enough to write the whole answer down."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Wear // Tear"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Mountain"],
            graveyard=["Dakmor Salvage"],
            library=["Mountain"] * 6,
            exile=["Lightning Bolt"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bolt = scenario.find("Lightning Bolt", Zone.EXILE, "alice")
    scenario.game.grant_play_permission(
        bolt, "alice", action=PlayAction.PLAY, source_name="test rig"
    )

    actions = legal_actions(scenario.game, "alice")

    assert _kinds(actions) == {
        ActionKind.PASS_PRIORITY,
        ActionKind.CONCEDE,
        ActionKind.CAST,
        ActionKind.DREDGE,
        ActionKind.DECLARE_ATTACKER,
        ActionKind.ACTIVATE_MANA,
    }
    assert len(actions) == 9, [a.kind for a in actions]

    casts = _of_kind(actions, ActionKind.CAST)
    assert len(casts) == 3
    assert {a.card_id for a in casts} == {bolt.id, scenario.find("Wear", Zone.HAND, "alice").id}
    bolt_cast = next(a for a in casts if a.card_id == bolt.id)
    assert bolt_cast.from_zone is Zone.EXILE
    assert bolt_cast.mana_cost == "{R}"
    split_casts = [a for a in casts if a.card_id != bolt.id]
    assert {a.spell_face for a in split_casts} == {"Wear", "Tear"}

    assert len(_of_kind(actions, ActionKind.DREDGE)) == 1
    assert len(_of_kind(actions, ActionKind.DECLARE_ATTACKER)) == 2
    assert len(_of_kind(actions, ActionKind.ACTIVATE_MANA)) == 1


# -- no side effects, no leaked identity -------------------------------------


def test_legal_actions_mutates_nothing():
    lands = (
        ["Forest"] * 4
        + ["Mountain"] * 3
        + ["Swamp"] * 3
        + ["Plains"] * 2
        + ["Island"] * 2
        + ["Cavern of Souls", "Snow-Covered Forest", "Temple Garden"]
    )
    battlefield = lands + ["Tarmogoyf", "Llanowar Elves"]
    hand = [
        "Cryptic Command",
        "Force of Negation",
        "Primeval Titan",
        "Wrath of God",
        "Lightning Bolt",
        "Thoughtseize",
    ]
    scenario = (
        Scenario()
        .player("alice", hand=hand, battlefield=battlefield)
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game

    # `Game.computed_board`'s own lazily-populated continuous-effects clock
    # (`continuous_effects.note`) materialises the first time anything reads
    # it - which any ordinary legality check does, not only this one - so
    # warm it up first, the same as a real game session would have done long
    # before its first `legal_actions` call.
    legal_actions(game, "alice")

    before_json = game.model_dump_json()
    before_objects = game.objects_created
    before_pools = dict(game.open_payment_pools)

    actions = legal_actions(game, "alice")

    assert actions
    assert game.model_dump_json() == before_json
    assert game.objects_created == before_objects
    assert game.open_payment_pools == before_pools


def test_action_round_trips_through_json_and_holds_no_nested_card_state():
    scenario = Scenario().player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (cast,) = _of_kind(legal_actions(scenario.game, "alice"), ActionKind.CAST)

    dumped = cast.model_dump_json()
    restored = Action.model_validate_json(dumped)
    assert restored == cast

    # No embedded `CardState` - only ids. A `CardState`'s own dump always
    # carries a nested printed `Card` under a `"card"` key; this has none.
    payload = json.loads(dumped)
    assert "card" not in payload
    assert isinstance(payload["card_id"], str)


# -- review-pass findings: seven defects found against the real card pool ---


def _unbuildable_activation() -> tuple[str, int]:
    """The first (by name) out-of-format permanent in the pool with an
    activated ability whose cost `Game.activation_cost` refuses to build, and
    that ability's index.

    Chosen rather than named: Relic of Progenitus was this test's card until
    its "Exile this artifact" cost became buildable, and every Modern, Pioneer
    and Standard card is owed full support (the owner rule), so an in-format
    card here is only waiting to be fixed. An out-of-format one - Moniker
    Mage's "Say your middle name", a cost no game engine prices - keeps the
    shape without leaning on a legal card's gap."""
    seen: set[str] = set()
    for _, printing in sorted(pool().items()):
        if printing.name in seen:
            continue
        seen.add(printing.name)
        if in_target_formats(printing) or printing.card_faces or printing.is_land:
            continue
        if not {"Artifact", "Creature", "Enchantment"} & set(printing.type_line.split()):
            continue
        if ":" not in (printing.oracle_text or ""):
            continue
        scenario = Scenario().player("alice", battlefield=[printing.name]).player("bob").build()
        permanent = scenario.find(printing.name, Zone.BATTLEFIELD, "alice")
        for index in range(len(scenario.game.activated_abilities(permanent))):
            try:
                scenario.game.activation_cost(permanent, index)
            except ValueError as error:
                if "cannot build a cost for" in str(error):
                    return printing.name, index
    pytest.fail(
        "no out-of-format permanent in the pool has an activation cost the engine cannot "
        "build: add a real printing of one (an Un-card cost like 'Say your middle name') "
        "with scripts/add_card.py"
    )


def test_legal_actions_reports_unbuildable_activation_cost_as_unknown_instead_of_raising():
    """Finding 1 (highest): an activated ability whose cost has a
    `CostKind.OTHER` piece `cost_component_for_phrase` declines to read makes
    `Game.activation_cost` raise `ValueError: cannot build a cost for ...`.
    The loop in `_battlefield_ability_actions` used to reach that unguarded
    call and let the exception escape `legal_actions` entirely - the caller
    got no actions at all, not even `PASS_PRIORITY`/`CONCEDE`. CR 118.6:
    "Attempting to cast a spell or activate an ability that has an unpayable
    cost is a legal action" - the attempt is still legal even though this
    enumeration cannot price it, so it must be reported `Affordability.
    UNKNOWN` with the engine's own reason instead, the same treatment `_off_
    zone_actions` already gives an unbuildable off-battlefield activation."""
    name, index = _unbuildable_activation()
    scenario = Scenario().player("alice", battlefield=[name]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")

    assert any(a.kind is ActionKind.PASS_PRIORITY for a in actions)
    assert any(a.kind is ActionKind.CONCEDE for a in actions)
    (unbuildable,) = [
        a
        for a in actions
        if a.kind in (ActionKind.ACTIVATE, ActionKind.ACTIVATE_MANA) and a.ability_index == index
    ]
    assert unbuildable.affordable is Affordability.UNKNOWN
    assert unbuildable.unaffordable_reason is not None
    assert "cannot build a cost for" in unbuildable.unaffordable_reason


def test_relic_of_progenitus_exile_this_artifact_cost_is_priced():
    """Relic of Progenitus's second ability - `{1}, Exile this artifact:
    Exile all graveyards. Draw a card.` - now builds: "Exile this artifact"
    is a cost this permanent pays by leaving (CR 118.3), so the ability is
    priced by its `{1}` alone - `NO` with nothing to pay it, `YES` with an
    Island - and activating it exiles the Relic as a cost."""
    bare = Scenario().player("alice", battlefield=["Relic of Progenitus"]).player("bob").build()
    bare.start_at(Step.PRECOMBAT_MAIN)
    (unpaid,) = [
        a
        for a in legal_actions(bare.game, "alice")
        if a.kind is ActionKind.ACTIVATE and a.ability_index == 1
    ]
    assert unpaid.affordable is Affordability.NO
    assert "{1}" in (unpaid.unaffordable_reason or "")

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Relic of Progenitus", "Island"],
            graveyard=["Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob", graveyard=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (paid,) = [
        a
        for a in legal_actions(scenario.game, "alice")
        if a.kind is ActionKind.ACTIVATE and a.ability_index == 1
    ]
    assert paid.affordable is Affordability.YES

    relic = scenario.find("Relic of Progenitus", Zone.BATTLEFIELD, "alice")
    scenario.activate(relic, *scenario.untapped_sources("Island"), index=1)
    assert relic.zone is Zone.EXILE, "exiled as the cost, before the ability resolves"
    scenario.resolve_top()

    assert scenario.game.player("alice").graveyard == []
    assert scenario.game.player("bob").graveyard == []
    assert [card.name for card in scenario.game.player("alice").hand] == ["Forest"]


def test_legal_actions_respects_timing_for_a_keyword_cast_option():
    """Finding 2 (first half): the keyword/marker/granted cast-option loop
    only asked `option.why_not`, never `why_cannot_cast_now`/`why_cannot_
    cast_restriction` the way the plain hand branch and `_permission_cast_
    actions` already do. Grief has no flash, so CR 117.1a's sorcery-speed
    rule still gates its Evoke option (an alternative *cost*, not an
    alternative *timing*) exactly as `Game.cast(..., keyword="Evoke")`
    already enforces (`Casting.model_post_init` runs the same two timing
    checks unconditionally). With Grief in bob's hand during *alice's* main
    phase, this used to report `CAST keyword=Evoke affordable=yes`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"])
        .player("bob", hand=["Grief", "Grief"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "alice"

    actions = legal_actions(scenario.game, "bob")

    evokes = [a for a in actions if a.kind is ActionKind.CAST and a.keyword == "Evoke"]
    assert evokes == []


def test_legal_actions_respects_timing_for_a_static_alternative_cost():
    """Finding 2 (second half): the `alternative_costs_for` loop has the
    identical gap - `alternative.available` never asks CR 117.1a either.
    Omniscience's STATIC grant (CR 118.9) still only pays for casting the
    same card, which is still subject to ordinary timing unless the card
    itself is exempt; a vanilla creature with no flash cast under
    Omniscience is not castable on an opponent's turn any more than it would
    be paying its own mana cost."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Mountain"])
        .player("alice", hand=["Grizzly Bears"], battlefield=["Omniscience"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"

    actions = legal_actions(scenario.game, "alice")

    omniscience_casts = [
        a for a in actions if a.kind is ActionKind.CAST and a.alternative_cost == "Omniscience"
    ]
    assert omniscience_casts == []


def test_legal_actions_never_offers_to_cast_a_land_creature():
    """Finding 3: `_CASTABLE_TYPES` gates on `card.card.types` alone, so
    Dryad Arbor - a land *and* a creature (CR 300.2a) - passed the gate and
    got a `CAST` action built for it, with `unaffordable_reason` coming from
    `why_mana_cost_unpayable` ("no mana cost") rather than the real reason
    `Game.cast` refuses with (`why_cannot_cast_a_land`'s "is a land"). CR
    305.1: "the land doesn't go on the stack, it is never a spell" - casting
    it is never a legal action to attempt in the first place, so it must not
    appear as a `CAST` action at all, with any reason."""
    scenario = Scenario().player("alice", hand=["Dryad Arbor"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")

    assert _of_kind(actions, ActionKind.CAST) == []
    assert len(_of_kind(actions, ActionKind.PLAY_LAND)) == 1


def test_legal_actions_reports_color_options_for_a_choice_mana_ability():
    """Finding 4: Steam Vents' `{T}: Add {U} or {R}.` was reported
    `ACTIVATE_MANA affordable=yes` with nothing telling a caller which
    colour to pass - `Action` had no field for it at all, so turning the
    action into `Game.activate_ability(..., color=?)` without already
    knowing the card's text raised `this ability offers [['U'], ['R']]; pass
    the colour chosen`. `Action.color_options` names the choice as plain
    data, and the action, once a colour from it is chosen, is a call
    `activate_ability` actually accepts."""
    scenario = Scenario().player("alice", battlefield=["Steam Vents"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    steam_vents = scenario.find("Steam Vents", Zone.BATTLEFIELD, "alice")

    actions = legal_actions(scenario.game, "alice")
    (mana_action,) = _of_kind(actions, ActionKind.ACTIVATE_MANA)

    assert set(mana_action.color_options) == {Color.BLUE, Color.RED}
    assert mana_action.affordable is Affordability.YES

    result = scenario.game.activate_ability(
        steam_vents, mana_action.ability_index, "alice", color=mana_action.color_options[0]
    )
    assert result is None, "a mana ability resolves immediately (CR 605.3b) - nothing on the stack"
    assert mana_action.color_choice_count == 1, "one colour named, one mana added"


def test_legal_actions_reports_a_color_per_mana_for_a_combination_ability():
    """Interdimensional Web Watch's `{T}: Add two mana in any combination of
    colors.` chooses a colour for *each* of the two mana, and
    `Action.color_options` alone cannot say so: it is one flat pool of the
    five colours, exactly what a dual land's two-colour pool looks like, so a
    caller driving the engine through `legal_actions` had no way to learn it
    may name two and no way to reach `{W}{U}` - only the five monochrome
    pairs a single `color=` produces. `Game.activate_ability` accepted the
    mixture all along; nothing in the enumerated action said it existed.

    `Action.color_choice_count` is the rest of that parameter space, the same
    treatment `modes`/`x_range` get: name this many colours from
    `color_options`, one per mana. It is per-ability and not a constant -
    Shang-Chi, Master of Kung Fu's "two mana of any **one** color" adds the
    same two mana from the same five-colour pool but takes one colour, and a
    Forest's single printed `{G}` takes none.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Interdimensional Web Watch",
                "Shang-Chi, Master of Kung Fu",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watch = scenario.find("Interdimensional Web Watch", Zone.BATTLEFIELD, "alice")
    shang_chi = scenario.find("Shang-Chi, Master of Kung Fu", Zone.BATTLEFIELD, "alice")
    shang_chi.summoning_sick = False
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    actions = legal_actions(scenario.game, "alice")
    by_card = {action.card_id: action for action in _of_kind(actions, ActionKind.ACTIVATE_MANA)}

    watch_action = by_card[watch.id]
    assert watch_action.color_choice_count == 2
    assert len(watch_action.color_options) == 5
    assert by_card[shang_chi.id].color_choice_count == 1
    assert len(by_card[shang_chi.id].color_options) == 5
    assert by_card[forest.id].color_choice_count == 0
    assert by_card[forest.id].color_options == ()

    # The whole point: a caller that knows nothing but this action's own
    # fields reaches a genuine mixture.
    chosen = watch_action.color_options[: watch_action.color_choice_count]
    scenario.game.activate_ability(
        watch, watch_action.ability_index, watch_action.player, color=list(chosen)
    )

    assert scenario.player().mana_pool.floating == {chosen[0]: 1, chosen[1]: 1}
    assert chosen[0] is not chosen[1], "the pair the five monochrome options could not make"


def test_choose_targets_decision_candidates_include_player_targets():
    """Finding 5: `decision_candidates` was built as `tuple(target.card_id
    for target in decision.targets if target.card_id is not None)`, which
    silently discarded every player candidate - CR 115.1: "The targets are
    object(s) and/or player(s)", and a `TargetRef` for a player carries a
    `username` with `card_id=None`. An "any target"/"target player"
    `CHOOSE_TARGETS` question's enumerated answer therefore advertised an
    `x_range` over a pool missing every legal player answer.
    `Action.decision_player_candidates` is the field `decision_candidates`
    (ids only, cards) could never have named a player through."""
    scenario = Scenario().player("alice", battlefield=["Mountain"]).player("bob").build()
    game = scenario.game
    game.decisions.pause_when_unanswered = True
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    decision = Decision(
        kind=DecisionKind.CHOOSE_TARGETS,
        player="alice",
        prompt="choose targets",
        targets=(TargetRef.to_card(mountain.id), TargetRef.to_player("bob")),
        target_maximum=1,
        target_minimum=1,
    )

    with pytest.raises(DecisionPending) as excinfo:
        game.ask(decision)

    pending = excinfo.value.pending
    (answer,) = decision_answers(pending.decision)

    assert answer.decision_candidates == (mountain.id,)
    assert answer.decision_player_candidates == ("bob",)


def test_candidate_pool_for_exile_from_a_shared_zone_reads_the_shared_zone():
    """Finding 6: `_candidate_pool_for`'s `ComponentKind.EXILE` branch read
    `game.player(payer).cards_in(component.zone)` unconditionally - right
    for `Zone.HAND`/`Zone.GRAVEYARD` (real per-player zones, CR 400.1), wrong
    for `Zone.BATTLEFIELD` (CR 400.1: "The other zones are shared by all
    players"), which `exile_cost`'s own `zone` can legitimately be (an
    "exile a permanent" activation cost - latent in today's pool, since
    every printed self-referential exile like Abstergo Entertainment's own
    "Exile Abstergo Entertainment" is filled in before this pool is ever
    consulted, but wrong all the same). Reading a shared zone through
    `Player.cards_in` returned an always-empty pool (wrongly reporting the
    component unpayable) and, because `Player.cards_in` is `zones.setdefault
    (zone, [])`, permanently mutated the player's own `zones` dict as a side
    effect of a read-only lookup."""
    scenario = (
        Scenario().player("alice", battlefield=["Grizzly Bears", "Mountain"]).player("bob").build()
    )
    game = scenario.game
    bears = scenario.creature("Grizzly Bears", "alice")
    before_zone_keys = set(game.player("alice").zones)

    component = CostComponent(
        kind=ComponentKind.EXILE, zone=Zone.BATTLEFIELD, required=1, payer="alice"
    )
    pool = _candidate_pool_for(game, "alice", component)

    assert pool is not None
    assert bears in pool
    assert set(game.player("alice").zones) == before_zone_keys, (
        "a read-only pool lookup must not add zone keys to the player it asked about"
    )


def test_targetable_objects_mutates_nothing():
    """Finding 7: `targetable_objects` called `player.cards_in(Zone.
    BATTLEFIELD)`/`.cards_in(Zone.EXILE)` for every player, and `Player.
    cards_in` is `zones.setdefault(zone, [])` - the battlefield and exile are
    shared zones (CR 400.1), never stored in `Player.zones` at all, so every
    call permanently added two spurious empty keys to every player's own
    serialized `zones`: a documented read-only query mutating the game it
    describes. Snapshotting *before any call at all* - unlike `test_legal_
    actions_mutates_nothing` above, which warms with one `legal_actions`
    call first for `Game.computed_board`'s own separate, legitimate reason -
    is what actually catches this: a warmed snapshot would already carry the
    mutation from the warming call itself, the same masking `test_legal_
    actions_mutates_nothing` could not have caught this defect through."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"], graveyard=["Mountain"], exile=["Forest"])
        .player("bob")
        .build()
    )
    game = scenario.game
    before = game.model_dump_json()

    game.targetable_objects()

    assert game.model_dump_json() == before


# -- what an ACTIVATE_MANA action produces, and what it may be spent on -----


def test_two_mana_abilities_on_one_permanent_are_told_apart_by_what_they_do():
    """Eldrazi Temple prints `{T}: Add {C}.` and `{T}: Add {C}{C}. Spend this
    mana only to cast colorless Eldrazi spells or activate abilities of
    colorless Eldrazi.` - two `ACTIVATE_MANA` actions that were byte-identical
    apart from `ability_index`, so a seat holding the list could not tell
    which one adds the restricted pair.

    `Action.produces`/`restriction`/`restriction_understood` say it in plain
    data: the printed production of each, and CR 106.6's own sentence on the
    one that carries it.
    """
    scenario = Scenario().player("alice", battlefield=["Eldrazi Temple"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")
    mana_actions = sorted(
        _of_kind(actions, ActionKind.ACTIVATE_MANA), key=lambda action: action.ability_index or 0
    )

    assert len(mana_actions) == 2
    plain, restricted = mana_actions
    assert plain.produces == "{C}"
    assert plain.restriction is None
    assert plain.restriction_understood is None
    assert restricted.produces == "{C}{C}"
    assert restricted.restriction == (
        "Spend this mana only to cast colorless Eldrazi spells or activate "
        "abilities of colorless Eldrazi."
    )
    assert restricted.restriction_understood is True
    assert plain.produces != restricted.produces, (
        "two mana abilities on one permanent must differ by what they do"
    )


def test_cavern_of_souls_two_mana_abilities_differ_by_production_and_restriction():
    """Cavern of Souls is the harder case: `{T}: Add {C}.` and `{T}: Add one
    mana of any color. Spend this mana only to cast a creature spell of the
    chosen type, and that spell can't be countered.` - the second ability's
    colours *include* the first's, so `color_options` alone cannot separate
    them. The printed production and CR 106.6's sentence can.
    """
    scenario = Scenario().player("alice", hand=["Cavern of Souls"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Zombie", source="Cavern of Souls")
    scenario.play_land("Cavern of Souls")

    actions = legal_actions(scenario.game, "alice")
    mana_actions = sorted(
        _of_kind(actions, ActionKind.ACTIVATE_MANA), key=lambda action: action.ability_index or 0
    )

    assert len(mana_actions) == 2
    colorless, any_color = mana_actions
    assert colorless.produces == "{C}"
    assert colorless.restriction is None
    assert any_color.produces == "one mana of any color"
    assert any_color.restriction == (
        "Spend this mana only to cast a creature spell of the chosen type, "
        "and that spell can't be countered."
    )
    assert any_color.restriction_understood is True


def test_an_unreadable_spend_restriction_is_reported_as_not_understood():
    """Rosheen Meanderer's `{T}: Add {C}{C}{C}{C}. Spend this mana only on
    costs that contain {X}.` is a CR 106.6 restriction this engine's clause
    grammar cannot read at all - it is neither a "cast [quality] spells" nor
    an "activate abilities of [quality] sources" clause - so `machines/cost.
    spend_restriction` fails it closed: the mana is produced, and pays for
    nothing.

    `restriction_understood=False` is what says that out loud. Without it a
    seat sees four mana it can never spend and no reason why.

    The quoted text is the whole effect rather than the trailing sentence
    alone, because that is precisely what `ManaRestriction.text` carries when
    the sentence could not be located: the tag the produced mana will
    actually wear, and the words a refusal downstream will quote. `Action.
    restriction` reports the mana's own tag verbatim rather than a prettier
    substring the engine does not itself hold.
    """
    scenario = Scenario().player("alice", battlefield=["Rosheen Meanderer"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")
    (mana_action,) = _of_kind(actions, ActionKind.ACTIVATE_MANA)

    assert mana_action.produces == "{C}{C}{C}{C}"
    assert mana_action.restriction == (
        "Add {C}{C}{C}{C}. Spend this mana only on costs that contain {X}."
    )
    assert mana_action.restriction_understood is False


def test_a_mana_ability_with_an_energy_cost_still_describes_what_it_produces():
    """Servant of the Conduit's `{T}, Pay {E}: Add one mana of any color.` once
    had a cost piece `machines/cost.cost_component_for_phrase` declined to read,
    so `_battlefield_ability_actions` reported it through the `Affordability.
    UNKNOWN` fallback. EP-01 round 1 made "Pay {E}" a priced cost, so with no
    energy it is now `Affordability.NO`; the descriptor must ride on either
    construction site, and the three fields come from the same helper.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Servant of the Conduit"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")
    (mana_action,) = _of_kind(actions, ActionKind.ACTIVATE_MANA)

    assert mana_action.affordable is Affordability.NO
    assert mana_action.produces == "one mana of any color"
    assert mana_action.restriction is None
    assert mana_action.restriction_understood is None


def test_an_unpriceable_mana_ability_still_describes_what_it_produces():
    """A mana ability with a cost piece `machines/cost.cost_component_for_phrase`
    declines to read goes through `_battlefield_ability_actions`'s
    `Affordability.UNKNOWN` fallback rather than the priced branch (CR 118.6:
    attempting an unpayable cost is still a legal action). That fallback is
    where a descriptor would silently go missing, so it is asserted here.

    No pool card keeps such a cost for long (Servant of the Conduit's
    "Pay {E}" was read this round), so the card is built, not named:
    Servant of the Conduit reprinted with an unreadable cost sentence
    ("Say your middle name", Moniker Mage's own shape) in place of "Pay {E}".
    `Card.model_copy` leaves the cached pool printing alone; its own `id`
    keeps `parse_abilities`' per-printing cache from answering with the
    original text.
    """
    text = "{T}, Say your middle name: Add one mana of any color."
    reprinted = pool()["Servant of the Conduit"].model_copy(
        update={
            "id": uuid5(NAMESPACE_OID, text),
            "oracle_text": text,
        }
    )
    scenario = (
        Scenario().player("alice", battlefield=["Servant of the Conduit"]).player("bob").build()
    )
    (servant,) = scenario.game.battlefield
    servant.card = reprinted
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")
    (mana_action,) = _of_kind(actions, ActionKind.ACTIVATE_MANA)

    assert mana_action.affordable is Affordability.UNKNOWN
    assert mana_action.produces == "one mana of any color"
    assert mana_action.restriction is None
    assert mana_action.restriction_understood is None


def test_no_action_but_activate_mana_carries_a_production_descriptor():
    """All three fields default to `None`, so a non-mana action carries
    nothing at all - the api's MCP layer strips `None` keys one level deep
    before an agent ever sees the row, which is why these are three flat
    fields rather than one nested submodel whose `None` members would
    survive that strip.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt", "Mountain"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")

    assert _of_kind(actions, ActionKind.ACTIVATE_MANA), "the Mountain's own ability is the control"
    for action in actions:
        if action.kind is ActionKind.ACTIVATE_MANA:
            continue
        assert action.produces is None
        assert action.restriction is None
        assert action.restriction_understood is None

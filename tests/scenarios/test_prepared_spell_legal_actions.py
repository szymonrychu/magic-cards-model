"""`legal_actions`/`Game.legal_targets` report a CR 722.3c prepared exile
copy by its own prepare spell's characteristics, not the whole preparation
card's.

The reported defect: `machines/legal_actions.py`'s CAST row for a prepared
copy read `card.card.mana_cost` - the two-face preparation card's own
top-level field, which is blank for a `Layout.PREPARE` card the same way it
is for a transform or modal DFC (CR 712.8a has no combined cost to fall back
to) - so the row showed the whole card with no face and no mana cost, and
`Game.legal_targets(copy, player)` returned no candidates at all, because
`Game.announcement_profile` only ever read a face when a `spell_face` name
was passed in, which nothing had any reason to do for a copy that is not a
split card or an Adventure. Together the two made every prepared spell that
targets uncastable through `legal_actions`, even though `Casting` itself
already read the right face (`Casting.base_cost`'s own identical
`prepare_spell_face` check) - `game.cast(...)` worked; nothing driving it
off `legal_actions` could ever announce a legal target.

`_base_cost_options` now reads `Card.prepare_spell` first, and `Game.
announcement_profile` reads `state.prepare_spell_face` unconditionally,
mirroring `Casting.base_cost`'s own ordering - both fixed once, not per
card, so every one of the 21 fra prepare cards benefits.

Proven on two of the 21, both with a genuine target: Seed Suture ("Put a
+1/+1 counter on target creature") and Vicious Verse ("Vicious Verse deals 1
damage to target opponent") - a permanent target and a player target, the
two target shapes `TargetRequirement` tells apart.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 722.3c (the exile copy's own characteristics), CR 601.2c
(target announcement).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def _cast_action_for(scenario: Scenario, player: str, card_id) -> object:
    actions = scenario.game.legal_actions(player)
    (action,) = [
        action for action in actions if action.kind is ActionKind.CAST and action.card_id == card_id
    ]
    return action


def test_seed_sutures_legal_action_reports_its_own_cost_and_a_creature_target():
    scenario = (
        Scenario()
        .player("alice", hand=["Blossom-Blessed Angel"], battlefield=["Plains"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.cast_and_resolve(
        "Blossom-Blessed Angel", *scenario.untapped_sources(*(["Plains"] * 4))
    )
    copy = scenario.game.find_by_id(angel.prepared_copy_id)
    assert copy.name == "Seed Suture"

    action = _cast_action_for(scenario, "alice", copy.id)
    assert action.mana_cost == "{G/W}"
    assert len(action.target_slots) == 1

    targets = scenario.game.legal_targets(copy, "alice")
    assert len(targets) == 1
    (candidates,) = targets
    assert angel.id in {candidate.id for candidate in candidates if hasattr(candidate, "id")}

    # End to end: the copy actually casts and resolves against a real target.
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    (payer,) = scenario.untapped_sources("Plains", username="alice")
    casting = scenario.cast("Seed Suture", username="alice", from_zone=Zone.EXILE, targets=[angel])
    payment = casting.begin_paying()
    scenario.pay_with(payment, payer)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert angel.counter_count("+1/+1") == 1


def test_vicious_verses_legal_action_reports_its_own_cost_and_a_player_target():
    scenario = (
        Scenario()
        .player("alice", hand=["Hallway Heckler"], battlefield=["Mountain"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    heckler = scenario.cast_and_resolve(
        "Hallway Heckler", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    copy = scenario.game.find_by_id(heckler.prepared_copy_id)
    assert copy.name == "Vicious Verse"

    action = _cast_action_for(scenario, "alice", copy.id)
    assert action.mana_cost == "{B/R}"
    assert len(action.target_slots) == 1

    targets = scenario.game.legal_targets(copy, "alice")
    assert len(targets) == 1
    (candidates,) = targets
    assert "bob" in {getattr(candidate, "username", candidate) for candidate in candidates}

    bob_life = scenario.player("bob").life
    (payer,) = scenario.untapped_sources("Mountain", username="alice")
    casting = scenario.cast(
        "Vicious Verse", username="alice", from_zone=Zone.EXILE, targets=["bob"]
    )
    payment = casting.begin_paying()
    scenario.pay_with(payment, payer)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.player("bob").life == bob_life - 1

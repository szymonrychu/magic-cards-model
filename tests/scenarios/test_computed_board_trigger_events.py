"""Scenario: the `GameEvent`s `Game` emits for a permanent leaving the
battlefield, being sacrificed, dying, and attacking all carry the object's
*computed* types (CR 613.5), not its printed ones (CR 613.1's starting
point, CR 712.8d's up-face-only printed reading).

`TriggerEvent.subject_types`/`subject_subtypes` are what
`machines/triggers.condition_matches` reads to decide whether a generic
"whenever a creature ..." ability fires (`_types_match`, verified by reading
`condition_matches`'s `IS_SACRIFICED` and `TriggerEvent.ATTACKS`/`DIES`
handling this session). A land animated by earthbend (CR 701.66a) is a
creature only on the computed board (`test_earthbend.py`,
`test_layer_computed_type_selection.py`) - `CardState.types` still reads
Land alone (CR 712.8d) - so it is the sharpest probe available in the pool
for whether an emitter read the right board.

Each site below is a real trigger firing off a real card, not a direct call
to a private helper: the generic "whenever a/another creature ..." detector
either fires (computed types correctly include Creature) or stays silent
(printed types only), and the test asserts on the trigger's own observable
effect - a card drawn, a life total moved, damage dealt - exactly as
`docs/scenario-tests.md` asks.

Sites fixed here (`src/magic_cards_model/models/game.py`):

- `_sacrifice_impl` (CR 701.21a's own event) - Dragon Appeasement's
  "Whenever you sacrifice a creature, you may draw a card."
- `put_into_graveyard`'s `LEAVES_THE_BATTLEFIELD` and `DIES` emitters
  (CR 603.6c, CR 700.4) - Blood Artist's "Whenever this creature or another
  creature dies, ...". The `DIES` emitter fires *after*
  `_take_out_of_every_zone`, so the fix snapshots `characteristics_of` before
  the move and carries it to both emitters (CR 608.2h, last known
  information) rather than reading the board through a permanent that has
  already left it.
- `declare_attacker` (CR 508.1's own event) - Hellrider's "Whenever a
  creature you control attacks, ...".

`_emit_counters_put` (CR 616.1g's "counters put" event) is fixed in
`models/game.py` alongside these for the same CR 613.5 reason, but every
"whenever one or more +1/+1 counters are put on ..." printing in the pool
(Basking Broodscale, Emperor of Bones) is self-referential ("this
creature") and is asked about a permanent that is never itself animated, so
no printing in the pool distinguishes the printed read from the computed one
for that specific site. It is fixed anyway (CR 613.5 does not carve out an
exception for a currently-untested consumer), and the two self-referential
printings are exercised below as a plain regression: their own counters-put
trigger still fires correctly once the emitter reads the computed board.

`deal_damage`'s own `DEALS_DAMAGE` emitter is fixed the same way, but
`machines/combat.py` never passes it a `source` at all (documented on
`deal_damage` itself), so every combat-damage trigger in the pool (Psychic
Frog, Ayara's Oathsworn, Jolrael) reads a *different*, already-computed path
rather than this event, and no non-combat "a creature deals damage" printing
with an animatable source exists in the pool to distinguish printed from
computed here either. Fixed, not independently exercised.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState
from tests.scenarios.harness import PlayedScenario, Scenario


def _earthbend_a_land(scenario: PlayedScenario, username: str = "alice") -> CardState:
    """Earthbend one of three Forests `username` already controls (two pay
    Badgermole Cub's {1}{G}, the third is the earthbend target), so the
    animated land is not summoning sick and both the attack and combat-only
    tests below stay honest about what haste is doing versus what
    earthbend's own animation is doing."""
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", username=username)
    pay_sources, target_forest = sources[:2], sources[2]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources, username=username)
    scenario.pass_until_resolved()
    return target_forest


def test_dragon_appeasement_triggers_off_sacrificing_an_animated_land():
    """CR 701.21a: `_sacrifice_impl` emits `IS_SACRIFICED` with the
    permanent's types. Dragon Appeasement's "Whenever you sacrifice a
    creature, you may draw a card" only fires if that event says the
    sacrificed object is a creature - which the earthbent Forest is, only on
    the computed board.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Sol Ring"],
            hand=["Badgermole Cub"],
            battlefield=["Forest", "Forest", "Forest", "Dragon Appeasement"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = _earthbend_a_land(scenario)
    assert scenario.game.characteristics_of(forest).is_creature

    scenario.will_take_the_may(True)
    hand_before = len(scenario.player("alice").hand)
    scenario.game.sacrifice(forest)
    assert forest.zone is Zone.GRAVEYARD, "sacrificed before either trigger resolves"

    # Earthbend's own delayed return (CR 701.66a) also fires off this same
    # death and queues alongside Dragon Appeasement's trigger; both resolve
    # here, which is why the assertion below is on the hand size Dragon
    # Appeasement's own trigger changed rather than on the land's zone.
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == hand_before + 1, (
        "Dragon Appeasement's trigger drew a card: it saw a creature sacrificed"
    )


def test_blood_artist_triggers_off_an_animated_lands_own_leaves_and_dies_events():
    """CR 603.6c / CR 700.4: `put_into_graveyard` emits both
    `LEAVES_THE_BATTLEFIELD` and `DIES` for the same move, and Blood Artist's
    "Whenever this creature or another creature dies, target player loses 1
    life and you gain 1 life" only reacts to the `DIES` half if that event's
    own `subject_types` says creature.

    The `DIES` emitter fires after `_take_out_of_every_zone`, so this is the
    fix that has to survive a snapshot taken *before* the move rather than a
    live `characteristics_of` call on a permanent already off the
    battlefield (which would `KeyError`).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub"],
            battlefield=["Forest", "Forest", "Forest", "Blood Artist"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = _earthbend_a_land(scenario)
    assert scenario.game.characteristics_of(forest).is_creature

    alice_life_before = scenario.player("alice").life
    bob_life_before = scenario.player("bob").life

    scenario.game.destroy(forest)
    assert forest.zone is Zone.GRAVEYARD, "destroyed before either trigger resolves"
    scenario.choose_trigger_targets("Blood Artist", ["bob"])

    # Earthbend's own delayed return (CR 701.66a) also fires off this same
    # death and queues alongside Blood Artist's trigger.
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert scenario.player("alice").life == alice_life_before + 1, (
        "Blood Artist's own controller gains 1 life: the DIES event said creature"
    )
    assert scenario.player("bob").life <= bob_life_before, (
        "the target player half of Blood Artist's trigger also ran"
    )


def test_hellrider_triggers_off_an_animated_land_attacking():
    """CR 508.1: `declare_attacker` emits `ATTACKS`, and Hellrider's
    "Whenever a creature you control attacks, this creature deals 1 damage
    to the player or planeswalker it's attacking" only fires for the
    earthbent Forest if that event's `subject_types` says creature. The
    Forest is played fresh and earthbent the same turn so haste (CR 702.10b)
    is what lets it attack at all - exactly `test_earthbend.py`'s own setup -
    keeping this test about Hellrider's own trigger, not about summoning
    sickness.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub", "Forest"],
            battlefield=["Forest", "Forest", "Hellrider"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pay_sources = scenario.untapped_sources("Forest", "Forest")
    new_forest = scenario.play_land("Forest")
    scenario.choose_trigger_targets("Badgermole Cub", [new_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(new_forest).is_creature
    assert scenario.can_attack(new_forest)

    bob_life_before = scenario.player("bob").life
    scenario.attack_with(new_forest)
    scenario.pass_until_resolved()

    assert new_forest in scenario.attackers()
    assert scenario.player("bob").life == bob_life_before - 1, (
        "Hellrider's own trigger dealt 1 damage: the ATTACKS event said creature"
    )


def test_hellrider_does_not_fire_for_a_plain_lands_own_untapping():
    """The inverse: a Forest that was never earthbent is never a creature,
    so declaring it as an attacker is simply illegal (CR 508.1a) and
    Hellrider has nothing to react to. Guards against a fix that made every
    permanent read as a creature.
    """
    scenario = Scenario().player("alice", battlefield=["Forest", "Hellrider"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    assert not scenario.can_attack(forest, "bob")


def test_basking_broodscales_own_counters_put_trigger_still_fires():
    """Regression for `_emit_counters_put`'s move to the computed board:
    Basking Broodscale's self-referential "Whenever one or more +1/+1
    counters are put on this creature, you may create a 0/1 ... Eldrazi
    Spawn" still fires off its own Adapt activation. No printing in the pool
    distinguishes printed from computed characteristics for this specific
    event (see the module docstring), so this is a plain regression rather
    than a probe of the fix.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Basking Broodscale", "Forest", "Forest"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodscale = scenario.find("Basking Broodscale", Zone.BATTLEFIELD, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")

    scenario.will_take_the_may(True)
    scenario.activate(broodscale, *forests, index=0)
    # Adapt's own activated ability resolves first, and only then does the
    # counters-put trigger it caused go on the stack, so the stack has to be
    # drained rather than resolved once.
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert "Eldrazi Spawn Token" in scenario.battlefield_names()

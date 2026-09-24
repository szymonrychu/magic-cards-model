"""Hand-reveal and graveyard-return templates from Marvel Super Heroes (task
C02-T7):

- **Night Nurse, Healer of Heroes** - "When Night Nurse enters, choose
  target permanent card in your graveyard that was put there from anywhere
  this turn. Return it to your hand." A new `_parse_choose_target_then_
  return_to_your_hand_pair` reader, the singular twin of the pool's own
  plural "choose target `<n>` .../return those `<n>` to their owners'
  hands" shape - and `_targets_understood`'s own `battlefield_only=False`,
  needed for the first time by a "return" verb naming a graveyard target.
- **Klaw, Sonic Subjugator** - "Sonic Attack — When Klaw enters, target
  player reveals a number of cards from their hand equal to one plus the
  number of creature cards in your graveyard. You choose one of them. That
  player discards that card." A wholly new reader: unlike the pool's
  existing "reveals their hand" shape, this reveals only *some* cards (the
  revealed player's own choice of which), counted by `amount_expression`.
- **Cloak and Dagger, Entwined** - "When Cloak and Dagger enter, choose
  target opponent and up to one target creature they control. They reveal
  their hand. You may exile a nonland card from their hand or the chosen
  creature until Cloak and Dagger leave the battlefield." Two targets, a
  hand reveal, and a genuine choice between two different kinds of object
  (a hand card versus the already-targeted creature) rather than a fresh
  target - `_watch_for_departure_and_return_exiled_card`'s own CR 610.2
  delayed-return machinery, reused.
- **Call Damage Control** - "Choose up to two. Return those cards from
  your graveyard to your hand. - Target artifact card. - ..." A modal
  spell whose shared verb sentence sits *before* the mode list rather than
  being repeated inside each bare "target `<type>` card" bullet;
  `resolve_modal_spell`'s own per-mode fallback (`_parse_mode_with_shared_
  verb_fallback`) substitutes each mode's own phrase for the shared
  sentence's "those cards" pronoun.
- **Grim Reaper, Lethal Legionnaire** - "Whenever Grim Reaper attacks, you
  may pay `{3}{B}`. When you do, return target creature card from your
  graveyard to the battlefield tapped and attacking with a finality
  counter on it." CR 508.4c: with no attacked player/planeswalker named,
  the reanimated creature attacks whoever/whatever Grim Reaper is already
  attacking (`Game.combat.attack_by`, `models.token._put_onto_the_
  battlefield_attacking`).

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 603.6b** - an enters-the-battlefield trigger.
- **CR 601.2c/608.2b** - targets are announced and rechecked.
- **CR 701.20a** - to reveal a card; **CR 701.9a** - to discard a card.
- **CR 400.7** - an object that changes zones becomes a new object, tracked
  by `zone_change_stamp` (Grim Reaper's own reanimated creature, Ares'
  return in the sibling test file).
- **CR 610.2** - an exile effect with a duration; **CR 610.3** - what
  happens to the exiled card when the duration ends.
- **CR 700.2** - modes; **CR 702.42b** - each chosen mode resolves
  independently, in the order printed.
- **CR 122.1h** - a finality counter (CR 700.4's "died" governs what
  happens to a creature with one, not read here).
- **CR 508.4c** - a creature put onto the battlefield attacking with no
  named defender attacks whatever the source of the effect is attacking.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import TargetRef
from tests.scenarios.harness import Scenario

# -- Night Nurse, Healer of Heroes -----------------------------------------


def test_night_nurse_returns_a_card_put_into_the_graveyard_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Night Nurse, Healer of Heroes"],
            battlefield=["Plains", "Plains"],
            graveyard=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bears)
    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Night Nurse, Healer of Heroes", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bears.zone is Zone.HAND


# -- Klaw, Sonic Subjugator -------------------------------------------------


def test_klaw_reveals_cards_and_discards_the_chosen_one():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Klaw, Sonic Subjugator"],
            battlefield=["Swamp", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears", "Craw Wurm"],  # two creature cards: X = 1 + 2 = 3
        )
        .player("bob", hand=["Forest", "Island", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    casting = scenario.cast("Klaw, Sonic Subjugator")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    bob = scenario.player("bob")
    forest = scenario.find("Forest", Zone.HAND, "bob")
    # Bob's whole hand (3 cards) is fewer than X (3), so no reveal-choice
    # decision is asked - every card is revealed and Klaw's own controller
    # chooses among all three.
    scenario.will_choose_cards(forest, source="Klaw, Sonic Subjugator")
    scenario.resolve_top()

    assert forest.zone is Zone.GRAVEYARD
    assert len(bob.hand) == 2


# -- Cloak and Dagger, Entwined ----------------------------------------------


def test_cloak_and_dagger_exiles_a_chosen_hand_card_until_it_leaves():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cloak and Dagger, Entwined"],
            battlefield=["Plains", "Swamp", "Island"],
        )
        .player("bob", hand=["Lightning Bolt", "Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets("bob", bears)
    sources = scenario.untapped_sources("Plains", "Swamp", "Island")
    casting = scenario.cast("Cloak and Dagger, Entwined")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(bolt, source="Cloak and Dagger, Entwined")
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE

    cloak_and_dagger = scenario.creature("Cloak and Dagger, Entwined", "alice")
    scenario.game.put_into_graveyard(cloak_and_dagger)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.HAND


def test_declining_cloak_and_dagger_leaves_everything_in_place():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Cloak and Dagger, Entwined"], battlefield=["Plains", "Swamp", "Island"]
        )
        .player("bob", hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob")
    sources = scenario.untapped_sources("Plains", "Swamp", "Island")
    casting = scenario.cast("Cloak and Dagger, Entwined")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_take_the_may(False)
    scenario.resolve_top()

    assert bolt.zone is Zone.HAND


# -- Call Damage Control -----------------------------------------------------


def test_call_damage_control_returns_two_chosen_card_types_from_the_graveyard():
    """`resolve_modal_spell`'s shared-verb fallback (`_parse_mode_with_shared_
    verb_fallback`) is proven directly here rather than through the ordinary
    `casting.choose_targets(...)` path.

    Genuine cross-file blocker (locked `machines/casting.py`, not touched by
    this task): `Casting._slice_targets_by_mode` builds each chosen mode's own
    `TargetingProfile` from that mode's bare bullet text ("Target creature
    card.", no zone), independently of the shared verb sentence that precedes
    the mode list ("Return those cards from your graveyard to your hand.").
    `targeting.profile_for_text("target creature card")` (no zone) returns
    `understood=False` - confirmed interactively - while the same phrase with
    an explicit zone ("target creature card in your graveyard") and the
    zone-less "target creature" (no "card" noun) both return
    `understood=True`. Because the zone lives only in the shared sentence, no
    fix inside `targeting.py` (owned by this task) can recover it without
    `casting.py` threading that context into the per-mode slice, so
    `casting.choose_targets(...)` leaves `CastRecord.mode_targets` empty for
    every modal spell shaped like this one - not specific to Call Damage
    Control. This test instead drives the announcement up through
    `choose_modes`, then supplies the two mode target slices directly on the
    `CastRecord` (what a fixed `casting.py` would have sliced out on its own),
    and resolves normally - proving the effects.py-side merge/resolve
    machinery this task owns is correct.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Call Damage Control"],
            battlefield=["Forest", "Forest"],
            graveyard=["Grizzly Bears", "Reliquary Tower"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    tower = scenario.find("Reliquary Tower", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest")
    casting = scenario.cast("Call Damage Control")
    casting.choose_modes([2, 4])  # target creature card / target land card
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    spell = scenario.game.stack[-1]
    record = scenario.game.cast_record(spell)
    record.mode_targets = [
        [TargetRef.coerce(bears)],
        [TargetRef.coerce(tower)],
    ]
    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert tower.zone is Zone.HAND


# -- Grim Reaper, Lethal Legionnaire -----------------------------------------


def test_grim_reaper_reanimates_a_creature_tapped_and_attacking_alongside_him():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grim Reaper, Lethal Legionnaire", "Swamp", "Swamp", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    grim_reaper = scenario.creature("Grim Reaper, Lethal Legionnaire", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.attack_with(grim_reaper, defending="bob")
    scenario.will_choose_targets(bears)
    scenario.game.put_triggers_on_stack()
    scenario.will_pay_the_mana_cost(True)
    scenario.resolve_top()  # the "you may pay" trigger: pays, stacks "when you do"
    scenario.resolve_top()  # the reflexive "when you do" ability itself

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.tapped is True
    assert bears.counters.counts.get("finality", 0) == 1
    attack = scenario.game.combat.attack_by(bears.id)
    assert attack is not None
    assert attack.defender.username == "bob"

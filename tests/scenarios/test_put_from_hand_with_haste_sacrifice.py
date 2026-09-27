"""Meek Attack: "{1}{R}: You may put a creature card with total power and
toughness 5 or less from your hand onto the battlefield. That creature
gains haste. At the beginning of the next end step, sacrifice that
creature."

Three CR 608.2c instructions, already generalised by `_parse_put_then_grant_
then_delayed_whole_text` (the "put ... onto the battlefield. That
`<pronoun>` gains `<keyword>`[. |, then ]`<delayed clause>`." family) - the
only gap was the head clause itself, `_PUT_PERMANENT_CARD_FROM_HAND_RE`,
widened here for Meek Attack's own "with total power and toughness N or
less" filter. Two things needed fixing together:

1. **The filter.** No existing reader summed a hand card's power and
   toughness against a fixed ceiling at all.
2. **The bare "and".** "total power and toughness" carries the identical
   bare-"and"-inside-a-fixed-phrase problem `_DOUBLE_TARGET_POWER_AND_
   TOUGHNESS_RE`'s own docstring already documents for "power and
   toughness" generally: `split_effect_clauses` cuts clean through it,
   turning "... with total power and toughness 5 or less ..." into two
   fragments neither of which is readable alone. The fix is the same one
   that shape already uses - reading the whole clause *before* the splitter
   ever sees it, in both `_ability_effect_or_notice` and `_spell_effect_or_
   notice`.

Proof printing: **Through the Breach** (already in the fixture pool,
Modern-legal, not a listed ecl-T8 card, not in any deck list) - the
identical three-instruction template with *no* power/toughness filter at
all (any creature card qualifies) and the delayed clause's *other* printed
word order ("Sacrifice that creature at the beginning of the next end
step." - verb first, Meek Attack's own is timing first) - proving the shared
`_parse_put_then_grant_then_delayed_whole_text` machinery generally, not
just for this one new filter.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 110.2a** - a card put onto the battlefield this way, not cast.
- **CR 608.2c** - the three instructions run in the order printed.
- **CR 400.7** - "that creature" is CR 607.1's anaphora onto the permanent
  the first instruction's own put just created, not a second target.
- **CR 208.1 / CR 613** - a card's power and toughness, printed plus
  counters, off the battlefield (a hand card has no continuous effects to
  compute against).
- **CR 603.7** - the delayed sacrifice, created only for a creature that
  actually entered.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

MEEK_ATTACK = "Meek Attack"
THROUGH_THE_BREACH = "Through the Breach"


def test_both_printings_are_fully_handled():
    for name in (MEEK_ATTACK, THROUGH_THE_BREACH):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        scenario.game.put_triggers_on_stack()
        while scenario.stack_names():
            scenario.pass_until_resolved()
            scenario.game.put_triggers_on_stack()
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def test_meek_attack_puts_a_cheap_creature_gains_haste_and_sacrifices_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[MEEK_ATTACK] + ["Mountain"] * 3,
            # Grizzly Bears is 2/2 (total 4, within "5 or less"); Serra
            # Angel is 4/4 (total 8, over the ceiling).
            hand=["Grizzly Bears", "Serra Angel"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    bears = next(state for state in alice.hand if state.name == "Grizzly Bears")
    angel = next(state for state in alice.hand if state.name == "Serra Angel")
    meek_attack = scenario.find(MEEK_ATTACK, Zone.BATTLEFIELD, "alice")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="alice", source=MEEK_ATTACK)
    scenario.will_choose_cards(bears, username="alice", source=MEEK_ATTACK)
    mana = scenario.untapped_sources("Mountain", "Mountain")
    scenario.activate(meek_attack, *mana, index=0)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.can_attack(bears, defending="bob"), (
        "'gains haste' lets it act the turn it entered"
    )
    assert angel.zone is Zone.HAND, (
        "total power and toughness 8 is over the ceiling - never offered"
    )

    _to_end_step(scenario)

    assert bears.zone is Zone.GRAVEYARD, "sacrificed at the beginning of the next end step"


def test_meek_attack_declining_the_may_puts_nothing_onto_the_battlefield():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[MEEK_ATTACK] + ["Mountain"] * 3,
            hand=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    bears = alice.hand[0]
    meek_attack = scenario.find(MEEK_ATTACK, Zone.BATTLEFIELD, "alice")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source=MEEK_ATTACK)
    mana = scenario.untapped_sources("Mountain", "Mountain")
    scenario.activate(meek_attack, *mana, index=0)
    scenario.resolve_top()

    assert bears.zone is Zone.HAND


# -- proof printing: Through the Breach, no filter, the other word order ----


def test_through_the_breach_puts_any_creature_gains_haste_and_sacrifices_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Through the Breach", "Serra Angel"],
            battlefield=["Mountain"] * 5,
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    angel = next(state for state in alice.hand if state.name == "Serra Angel")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="alice", source=THROUGH_THE_BREACH)
    scenario.will_choose_cards(angel, username="alice", source=THROUGH_THE_BREACH)
    scenario.cast_and_resolve(THROUGH_THE_BREACH, *sources)

    assert angel.zone is Zone.BATTLEFIELD, "no power/toughness ceiling at all"
    assert scenario.can_attack(angel, defending="bob"), (
        "'gains haste' lets it act the turn it entered"
    )

    _to_end_step(scenario)

    assert angel.zone is Zone.GRAVEYARD

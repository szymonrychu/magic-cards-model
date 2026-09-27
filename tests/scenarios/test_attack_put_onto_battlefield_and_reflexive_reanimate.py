"""Two attack triggers this task reuses tmt-T8's put-onto-battlefield-
attacking primitive for, and a CR 603.12 reflexive ability with a chosen
permanent (rather than a self-referential counter) as its optional action.

- **Kinscaer Sentry** - "Whenever this creature attacks, you may put a
  creature card with mana value X or less from your hand onto the
  battlefield tapped and attacking, where X is the number of attacking
  creatures you control." The dynamic-X, mana-value-capped twin of Ilharg,
  the Raze-Boar's own uncapped "you may put a creature card from your hand
  onto the battlefield tapped and attacking." (`_PUT_CREATURE_FROM_HAND_
  ATTACKING_RE`), reusing the identical CR 508.4 placement primitive
  (`models.token._put_onto_the_battlefield_attacking`). X is fixed once, as
  the ability resolves (CR 608.2c) - `count_expression`'s widened `_COUNT_
  YOU_CONTROL_RE` now also reads "attacking" as a status alongside tapped/
  untapped.
- **Meanders Guide** - "Whenever this creature attacks, you may tap another
  untapped Merfolk you control. When you do, return target creature card
  with mana value 3 or less from your graveyard to the battlefield." CR
  603.12's reflexive shape, with a *chosen* permanent as the optional action
  - distinct from `_MAY_TAP_UNTAPPED_IF_YOU_DO_RE`'s existing CR 118.12 "if
  you do" (same-instruction) sibling, which this is never mistaken for
  because the connector word itself differs ("when" vs "if").

CR numbers verified this session with `mise run rules:find`:

- **CR 508.4** - a creature put onto the battlefield attacking: its
  controller chooses which defending player, planeswalker, or battle it
  attacks.
- **CR 603.12** - a reflexive triggered ability, checked immediately after
  being created, based on whether the trigger event occurred during the
  resolution that created it.
- **CR 608.2c** - an instruction's own count is determined as it is
  performed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Kinscaer Sentry -----------------------------------------------------------


def test_kinscaer_sentry_puts_a_creature_with_mana_value_at_most_the_attacker_count():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Llanowar Elves", "Hill Giant"],
            battlefield=["Kinscaer Sentry", "Goldmeadow Dodger"],
        )
        .player("bob")
        .build()
    )
    sentry = scenario.creature("Kinscaer Sentry", "alice")
    dodger = scenario.creature("Goldmeadow Dodger", "alice")
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    # Two attacking creatures -> X = 2. Hill Giant (mana value 3) is over the
    # cap; only Llanowar Elves (mana value 1) is offered.
    scenario.will_take_the_may(True, source="Kinscaer Sentry")
    scenario.will_choose_cards(elves, source="Kinscaer Sentry")
    scenario.attack_with(sentry, dodger)
    scenario.pass_until_resolved()

    assert elves.zone is Zone.BATTLEFIELD
    assert giant.zone is Zone.HAND, "mana value 3 is over the X=2 cap"
    assert elves.tapped, "CR 508.4: put onto the battlefield tapped"
    assert scenario.game.combat.attack_by(elves.id) is not None, "and attacking"


def test_kinscaer_sentry_offers_nothing_when_every_hand_card_is_over_the_cap():
    scenario = (
        Scenario()
        .player("alice", hand=["Hill Giant"], battlefield=["Kinscaer Sentry"])
        .player("bob")
        .build()
    )
    sentry = scenario.creature("Kinscaer Sentry", "alice")
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    # One attacker -> X = 1; Hill Giant costs 3, so nothing is legal to put
    # down and the "you may" is never even offered (no legal action).
    scenario.attack_with(sentry)
    scenario.pass_until_resolved()

    assert giant.zone is Zone.HAND


def test_kinscaer_sentry_declining_leaves_the_hand_untouched():
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Kinscaer Sentry"])
        .player("bob")
        .build()
    )
    sentry = scenario.creature("Kinscaer Sentry", "alice")
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(False, source="Kinscaer Sentry")
    scenario.attack_with(sentry)
    scenario.pass_until_resolved()

    assert elves.zone is Zone.HAND


# -- Meanders Guide --------------------------------------------------------


def test_meanders_guide_taps_a_merfolk_then_reanimates_a_cheap_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Meanders Guide", "Caller of Gales"],
            graveyard=["Llanowar Elves", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    guide = scenario.creature("Meanders Guide", "alice")
    caller = scenario.creature("Caller of Gales", "alice")
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(True, source="Meanders Guide")
    scenario.will_choose_targets(elves)
    scenario.attack_with(guide)
    scenario.pass_until_resolved()  # the attack trigger
    scenario.pass_until_resolved()  # CR 603.12's reflexive "when you do"

    assert caller.tapped, "tapped as the optional action"
    assert elves.zone is Zone.BATTLEFIELD, "mana value 1 - a legal target"
    assert giant.zone is Zone.GRAVEYARD, "mana value 3 - never offered as a target"


def test_meanders_guide_does_not_trigger_with_no_untapped_merfolk_to_tap():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Meanders Guide", "Hill Giant"],
            graveyard=["Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    guide = scenario.creature("Meanders Guide", "alice")
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    # Hill Giant is not a Merfolk, and there is no *other* untapped Merfolk
    # around at all - nothing legal to tap, so the ability does nothing.
    scenario.attack_with(guide)
    scenario.pass_until_resolved()

    assert elves.zone is Zone.GRAVEYARD


def test_meanders_guide_declining_the_tap_never_creates_the_reflexive_trigger():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Meanders Guide", "Caller of Gales"],
            graveyard=["Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    guide = scenario.creature("Meanders Guide", "alice")
    caller = scenario.creature("Caller of Gales", "alice")
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(False, source="Meanders Guide")
    scenario.attack_with(guide)
    scenario.pass_until_resolved()

    assert not caller.tapped
    assert elves.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []

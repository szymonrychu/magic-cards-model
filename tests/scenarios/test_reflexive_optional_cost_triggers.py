"""CR 603.12's reflexive "`<optional action>`. When you do, `<consequence>`."
shape, widened past a plain mana payment or sacrifice to three new actions:

- Hawkeye, Master Marksman's own "Trick Arrows — Whenever Hawkeye becomes
  tapped, you may pay {1} up to three times. When you do, choose up to that
  many —" - a *repeated* optional mana payment feeding CR 603.2c's "that
  many" into a modal pick among the bulleted list beneath it.
- Bullseye, Death Dealer's own "you may sacrifice an artifact or discard a
  nonland card. When you do, Bullseye deals 2 damage to any target." -
  CR 601.2b's own "[cost] or [cost]" choice of resource, applied to an
  optional reflexive action rather than a mandatory printed one.
- Spider-Man, To the Rescue's own "you may tap him. When you do, another
  target nonattacking creature you control gains indestructible until end
  of turn." - CR 701.26a's tap standing in for the action, off a card whose
  own printed ability word ("No One Dies!") carries a punctuation mark this
  task's own `machines/abilities._ABILITY_WORD` fix had to admit before the
  line even read as triggered at all.

Super Speed's own "When this Aura enters, enchanted creature gains first
strike until end of turn." sits alongside them: not CR 603.12's own
optional-action shape, but the same class of gap - an attached-subject
one-shot grant this task's own `_grant_keywords_to`-based reader closes,
proven here rather than split into a sixth file of its own.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 603.12** - the reflexive triggered ability itself.
- **CR 118.12/CR 608.2g** - "you may pay [cost]", mid-resolution.
- **CR 601.2b** - a "[cost] or [cost]" choice of which resource pays it.
- **CR 701.9a/701.9b** - discarding.
- **CR 701.21a** - sacrificing.
- **CR 701.26a** - tapping.
- **CR 509.1a** - blocking is CR 509.1's own step; "nonattacking" is read
  directly off `CombatState.ATTACKING`'s absence, not a blocking-specific
  rule.
- **CR 613.1f** - a one-shot keyword grant, sublayer 6.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

# --------------------------------------------------------------------------
# Hawkeye, Master Marksman
# --------------------------------------------------------------------------


def hawkeye_board(mana: int) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Hawkeye, Master Marksman", "Grizzly Bears", *(["Mountain"] * mana)],
        )
        .player("bob", battlefield=["Elvish Mystic"])
    )


def test_hawkeye_declining_every_payment_chooses_nothing():
    scenario = hawkeye_board(0).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hawkeye = scenario.creature("Hawkeye, Master Marksman", "alice")

    scenario.attack_with(hawkeye, defending="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Hawkeye, Master Marksman's triggered ability"]
    scenario.resolve_top()

    # No mode chosen: nothing changed - Elvish Mystic still blocks fine, the
    # hand is unchanged, and Bullseye's own "any target" would still be 20.
    assert scenario.player("bob").life == 20


def test_hawkeye_paying_twice_lets_you_choose_two_distinct_modes():
    scenario = hawkeye_board(2).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hawkeye = scenario.creature("Hawkeye, Master Marksman", "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")
    bob_life_before = scenario.player("bob").life

    scenario.will_pay_the_mana_cost(True, source="Hawkeye, Master Marksman", times=2)
    scenario.will_pay_the_mana_cost(False, source="Hawkeye, Master Marksman")
    scenario.will_choose_mode(
        "Hawkeye deals 2 damage to target player", source="Hawkeye, Master Marksman"
    )
    scenario.will_choose_mode(
        "Target creature can't block this turn", source="Hawkeye, Master Marksman"
    )
    scenario.will_choose_targets("bob", username="alice", source="Hawkeye, Master Marksman")
    scenario.will_choose_targets(mystic, username="alice", source="Hawkeye, Master Marksman")

    scenario.attack_with(hawkeye, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # Hawkeye's own trigger: pays twice, picks two modes
    scenario.game.put_triggers_on_stack()  # the two reflexive triggers it created
    assert len(scenario.stack_names()) == 2
    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.player("bob").life == bob_life_before - 2


# --------------------------------------------------------------------------
# Bullseye, Death Dealer
# --------------------------------------------------------------------------


def test_bullseye_sacrifices_an_artifact_and_deals_damage():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bullseye, Death Dealer"],
            battlefield=["Swamp", "Swamp", "Mountain", "Ornithopter"],
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")

    scenario.will_take_the_may(True, username="alice", source="Bullseye, Death Dealer")
    scenario.will_choose_targets(mystic, username="alice", source="Bullseye, Death Dealer")
    casting = scenario.cast("Bullseye, Death Dealer")
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Bullseye becomes a permanent
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Bullseye, Death Dealer's triggered ability"]
    scenario.resolve_top()  # sacrifices, then creates the "deals 2 damage" reflexive trigger
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Bullseye, Death Dealer's triggered ability"]
    scenario.resolve_top()

    assert ornithopter.zone is Zone.GRAVEYARD
    assert mystic.zone is Zone.GRAVEYARD  # 1/1, 2 damage


def test_bullseye_discards_a_nonland_card_instead():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bullseye, Death Dealer", "Lightning Bolt"],
            battlefield=["Swamp", "Swamp", "Mountain"],
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")

    scenario.will_take_the_may(True, username="alice", source="Bullseye, Death Dealer")
    scenario.will_choose_targets(mystic, username="alice", source="Bullseye, Death Dealer")
    casting = scenario.cast("Bullseye, Death Dealer")
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # discards, then creates the "deals 2 damage" reflexive trigger
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert mystic.zone is Zone.GRAVEYARD


def test_bullseye_declining_pays_nothing_and_deals_no_damage():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bullseye, Death Dealer"],
            battlefield=["Swamp", "Swamp", "Mountain"],
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "bob")

    scenario.will_take_the_may(False, username="alice", source="Bullseye, Death Dealer")
    casting = scenario.cast("Bullseye, Death Dealer")
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Bullseye becomes a permanent
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Bullseye, Death Dealer's triggered ability"]
    scenario.resolve_top()  # declines the may - no reflexive trigger is created
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert mystic.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Spider-Man, To the Rescue
# --------------------------------------------------------------------------


def test_spider_man_taps_himself_and_grants_indestructible_to_a_nonattacker():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Spider-Man, To the Rescue"],
            battlefield=["Forest", "Forest", "Plains", "Hill Giant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")

    scenario.will_take_the_may(True, username="alice", source="Spider-Man, To the Rescue")
    scenario.will_choose_targets(giant, username="alice", source="Spider-Man, To the Rescue")
    casting = scenario.cast("Spider-Man, To the Rescue")
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Forest", "Forest", "Plains"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Spider-Man becomes a permanent
    spidey = scenario.creature("Spider-Man, To the Rescue", "alice")

    scenario.game.put_triggers_on_stack()  # "No One Dies!" ETB trigger
    scenario.resolve_top()  # taps himself, creates the reflexive trigger
    assert spidey.tapped

    scenario.game.put_triggers_on_stack()  # the reflexive "gains indestructible"
    scenario.resolve_top()

    assert scenario.game.characteristics_of(giant).has_ability("Indestructible")


def test_spider_man_declining_the_tap_never_creates_the_reflexive_trigger():
    """CR 118.12: declining the "may" is legal, and CR 603.12's reflexive
    ability is created "only once the action it reflects has actually
    happened" - nothing to tap, nothing to create."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Spider-Man, To the Rescue"], battlefield=["Forest", "Forest", "Plains"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.will_take_the_may(False, username="alice", source="Spider-Man, To the Rescue")
    casting = scenario.cast("Spider-Man, To the Rescue")
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Forest", "Forest", "Plains"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Spider-Man becomes a permanent
    spidey = scenario.creature("Spider-Man, To the Rescue", "alice")

    scenario.game.put_triggers_on_stack()  # "No One Dies!" ETB trigger
    assert scenario.stack_names() == ["Spider-Man, To the Rescue's triggered ability"]
    scenario.resolve_top()  # declines the may
    assert not spidey.tapped  # declined, so nothing was even tapped

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Super Speed
# --------------------------------------------------------------------------


def test_super_speed_grants_first_strike_when_it_enters():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Super Speed"],
            battlefield=["Mountain", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Super Speed")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Super Speed becomes an enchantment, attaches
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Super Speed's triggered ability"]
    scenario.resolve_top()

    assert scenario.game.characteristics_of(bears).has_ability("First strike")
    assert scenario.game.characteristics_of(bears).has_ability("Haste")  # the static line too

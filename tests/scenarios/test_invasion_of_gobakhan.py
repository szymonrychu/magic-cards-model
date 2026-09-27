"""Invasion of Gobakhan // Lightshield Array.

Verified this session with `mise run rules:find` against the current CR:

- **CR 701.20e** - looking at a card follows the reveal rules, except only
  the specified player sees it.
- **CR 601.3** - "A player can begin to cast a spell only if a rule or
  effect allows that player to cast it" - the permission this ETB grants.
- **CR 108.3** - a card's owner, not its controller, is who this permission
  goes to.
- **CR 118.7** - a cost may be changed by an effect; the {2} increase here
  is `machines.casting.PlayPermission.cost_increase`, scoped to this one
  grant.
- **CR 400.7** - a card that moves zones becomes a new object, which is why
  no turn-bounded duration is needed: leaving exile ends the grant on its
  own.

Front face: "When this Siege enters, look at target opponent's hand. You
may exile a nonland card from it. For as long as that card remains exiled,
its owner may play it. A spell cast this way costs {2} more to cast." Back
face (Lightshield Array): "At the beginning of your end step, put a +1/+1
counter on each creature that attacked this turn." (its "Sacrifice this
enchantment: ..." line was already handled before this session).

Elite Spellbinder (real, Modern/Pioneer-legal) prints the ETB's front-face
template verbatim, proving it generalises beyond this Siege.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

GOBAKHAN = "Invasion of Gobakhan"
SPELLBINDER = "Elite Spellbinder"


def test_etb_exiles_a_nonland_card_and_grants_its_owner_a_play_permission():
    scenario = (
        Scenario()
        .player("alice", hand=[GOBAKHAN], battlefield=["Plains", "Plains"])
        .player("bob", hand=["Lightning Bolt", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Plains", "Plains")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    forest = scenario.find("Forest", Zone.HAND, "bob")

    casting = scenario.cast(GOBAKHAN)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    scenario.put_on_stack(casting)
    scenario.choose_trigger_targets(GOBAKHAN, ["bob"])
    scenario.will_take_the_may(True, username="alice", source=GOBAKHAN)
    scenario.will_choose_cards(bolt, username="alice", source=GOBAKHAN)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.EXILE
    assert forest.zone is Zone.HAND, "a land was never a legal exile candidate"

    permission = next(p for p in scenario.game.play_permissions if p.card_id == bolt.id)
    assert permission.player == "bob", "the exiled card's owner, not alice, may play it"
    assert permission.until_end_of_turn is False, "no turn-bounded duration - CR 400.7 ends it"
    assert str(permission.cost_increase) == "{2}"


def test_bobs_lightning_bolt_really_costs_two_more_for_him_to_cast():
    scenario = (
        Scenario()
        .player("alice", hand=[GOBAKHAN], battlefield=["Plains", "Plains"])
        .player("bob", hand=["Lightning Bolt", "Forest"], battlefield=["Mountain"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Plains", "Plains")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob")

    casting = scenario.cast(GOBAKHAN)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    scenario.put_on_stack(casting)
    scenario.choose_trigger_targets(GOBAKHAN, ["bob"])
    scenario.will_take_the_may(True, username="alice", source=GOBAKHAN)
    scenario.will_choose_cards(bolt, username="alice", source=GOBAKHAN)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bolt.zone is Zone.EXILE

    scenario.pass_priority("alice")  # priority to bob (CR 117.3b, APNAP)

    bob_casting = scenario.cast(
        "Lightning Bolt", username="bob", from_zone=Zone.EXILE, targets=["alice"]
    )
    payment = bob_casting.determine_cost()
    # `total_cost` only folds in `PlayPermission.cost_increase` once
    # `determine_cost` has claimed the permission (`permission_used`).
    assert str(bob_casting.total_cost.mana) == "{2}{R}", (
        "Lightning Bolt's own {R} plus this permission's {2}"
    )
    scenario.pay_with(payment, *mountains)
    scenario.put_on_stack(bob_casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD


def test_no_nonland_card_means_nothing_is_exiled():
    scenario = (
        Scenario()
        .player("alice", hand=[GOBAKHAN], battlefield=["Plains", "Plains"])
        .player("bob", hand=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Plains", "Plains")
    forest = scenario.find("Forest", Zone.HAND, "bob")

    casting = scenario.cast(GOBAKHAN)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    scenario.put_on_stack(casting)
    scenario.choose_trigger_targets(GOBAKHAN, ["bob"])
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert forest.zone is Zone.HAND
    assert scenario.game.play_permissions == []


def test_elite_spellbinder_shares_the_identical_template():
    """Elite Spellbinder's own ETB prints the identical template verbatim -
    the mechanic generalises past this Siege."""
    scenario = (
        Scenario()
        .player("alice", hand=[SPELLBINDER], battlefield=["Plains", "Plains", "Plains"])
        .player("bob", hand=["Lightning Bolt", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Plains", "Plains", "Plains")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    forest = scenario.find("Forest", Zone.HAND, "bob")

    casting = scenario.cast(SPELLBINDER)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    scenario.put_on_stack(casting)
    scenario.choose_trigger_targets(SPELLBINDER, ["bob"])
    scenario.will_take_the_may(True, username="alice", source=SPELLBINDER)
    scenario.will_choose_cards(bolt, username="alice", source=SPELLBINDER)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.EXILE
    assert forest.zone is Zone.HAND
    permission = next(p for p in scenario.game.play_permissions if p.card_id == bolt.id)
    assert permission.player == "bob"
    assert str(permission.cost_increase) == "{2}"


def test_the_cost_increase_permission_survives_a_save_and_load():
    """The recorded "costs {2} more" rides the play permission through a
    dump and decode of the game."""
    from magic_cards_model.models.game import Game

    scenario = (
        Scenario()
        .player("alice", hand=[SPELLBINDER], battlefield=["Plains", "Plains", "Plains"])
        .player("bob", hand=["Lightning Bolt", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Plains", "Plains", "Plains")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    casting = scenario.cast(SPELLBINDER)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    scenario.put_on_stack(casting)
    scenario.choose_trigger_targets(SPELLBINDER, ["bob"])
    scenario.will_take_the_may(True, username="alice", source=SPELLBINDER)
    scenario.will_choose_cards(bolt, username="alice", source=SPELLBINDER)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))

    permission = next(p for p in decoded.play_permissions if p.card_id == bolt.id)
    assert permission.player == "bob"
    assert str(permission.cost_increase) == "{2}"

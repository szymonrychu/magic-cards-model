"""Undying: coming back once, bigger (CR 702.93).

CR 702.93a: "Undying is a triggered ability. "Undying" means "When this
permanent is put into a graveyard from the battlefield, if it had no +1/+1
counters on it, return it to the battlefield under its owner's control with a
+1/+1 counter on it.""

Persist's mirror image (CR 702.79a), built beside it in `machines/keywords.py`:
`_undying_ability` writes the expansion out as a `TriggeredAbility`, and its
intervening "if" (CR 603.4) is asked of the permanent as it last existed -
CR 122.2 has already wiped the counters by the time the trigger is checked,
so `last_known_counters` (CR 603.10a) is what is read. The +1/+1 counter is
given as the permanent enters (CR 122.6), so a creature that comes back is
never on the battlefield without it.

Printings: Young Wolf (undying alone), Strangleroot Geist (haste), Geralf's
Messenger (enters tapped, an ETB), Flayer of the Hatebound (its "enters from
your graveyard" trigger fires for the undying return), and Undying Evil (a
granted "gains undying until end of turn", CR 702.93a functioning the same
way through `machines/layers._GRANTABLE_TRIGGERED_KEYWORDS`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import executes, keyword_triggered_abilities
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(*alice_battlefield: str, hand: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice_battlefield), hand=list(hand))
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _die_and_resolve(scenario, creature) -> None:
    scenario.game.destroy(creature)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_undying_is_a_keyword_the_engine_executes():
    assert executes("Undying")
    (ability,) = [a for a in keyword_triggered_abilities(card("Young Wolf"))]
    assert ability.keyword == "undying"
    assert ability.event is TriggerEvent.DIES
    assert ability.intervening_if == "it had no +1/+1 counters on it"
    assert ability.effect == (
        "return it to the battlefield under its owner's control with a +1/+1 counter on it"
    )


def test_a_creature_that_dies_clean_comes_back_with_a_counter():
    scenario = _board("Young Wolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf")

    scenario.game.destroy(wolf)
    scenario.game.put_triggers_on_stack()
    assert "Young Wolf's triggered ability" in scenario.stack_names()
    scenario.pass_until_resolved()

    assert wolf.zone is Zone.BATTLEFIELD
    assert wolf.counter_count(Counter.PLUS_ONE) == 1
    assert (wolf.power, wolf.toughness) == (2, 2)


def test_the_second_death_does_not_trigger():
    """CR 603.4: the returned creature had a +1/+1 counter as it died."""
    scenario = _board("Young Wolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf")
    _die_and_resolve(scenario, wolf)
    assert wolf.zone is Zone.BATTLEFIELD

    scenario.game.destroy(wolf)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert wolf.zone is Zone.GRAVEYARD


def test_a_counter_from_anywhere_else_also_stops_it():
    """The clause reads +1/+1 counters, whatever put them there."""
    scenario = _board("Young Wolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf")
    scenario.game.add_counters(wolf, Counter.PLUS_ONE, 1)

    scenario.game.destroy(wolf)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert wolf.zone is Zone.GRAVEYARD


def test_minus_one_counters_do_not_stop_it():
    """Only +1/+1 counters count; a -1/-1 counter is persist's question."""
    scenario = _board("Young Wolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf")
    scenario.game.add_counters(wolf, Counter.MINUS_ONE, 1)
    scenario.state_based_actions()  # a 0/0 dies (CR 704.5f)
    assert wolf.zone is Zone.GRAVEYARD

    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert wolf.zone is Zone.BATTLEFIELD
    assert wolf.counter_count(Counter.PLUS_ONE) == 1
    assert wolf.counter_count(Counter.MINUS_ONE) == 0


def test_a_minus_one_counter_annihilates_the_undying_counter_and_it_returns_again():
    """CR 704.5q: the +1/+1 and -1/-1 counters cancel, so the wolf is a 1/1
    with no counters, and the next death triggers undying again."""
    scenario = _board("Young Wolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf")
    _die_and_resolve(scenario, wolf)

    scenario.game.add_counters(wolf, Counter.MINUS_ONE, 1)
    scenario.state_based_actions()
    assert wolf.zone is Zone.BATTLEFIELD
    assert wolf.counter_count(Counter.PLUS_ONE) == 0
    assert wolf.counter_count(Counter.MINUS_ONE) == 0

    _die_and_resolve(scenario, wolf)

    assert wolf.zone is Zone.BATTLEFIELD
    assert wolf.counter_count(Counter.PLUS_ONE) == 1


def test_it_returns_under_its_owners_control():
    """CR 702.93a: "under its owner's control" - a stolen creature goes home."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Mountain", "Mountain", "Mountain"], hand=["Act of Treason"])
        .player("bob", battlefield=["Young Wolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf", "bob")
    scenario.cast_and_resolve("Act of Treason", auto=True, username="alice", targets=[wolf])
    assert wolf.controller == "alice"

    _die_and_resolve(scenario, wolf)

    assert wolf.zone is Zone.BATTLEFIELD
    assert wolf.controller == "bob"
    assert wolf.counter_count(Counter.PLUS_ONE) == 1


def test_a_token_does_not_come_back():
    """CR 111.7: a token that left the battlefield ceases to exist, so the
    trigger finds nothing to return (CR 603.6)."""
    scenario = _board("Young Wolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf")
    wolf.token = True

    _die_and_resolve(scenario, wolf)

    assert wolf not in scenario.game.battlefield


def test_leaving_the_graveyard_first_means_it_does_not_return():
    """CR 603.6: the ability looks for the card only in the graveyard."""
    scenario = _board("Young Wolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf")
    scenario.game.destroy(wolf)
    scenario.game.put_triggers_on_stack()
    scenario.game.exile_permanent(wolf)
    scenario.pass_until_resolved()

    assert wolf.zone is Zone.EXILE


def test_exile_is_not_dying():
    scenario = _board("Young Wolf").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Young Wolf")

    scenario.game.exile_permanent(wolf)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_strangleroot_geist_comes_back_bigger_and_still_hasty():
    scenario = _board("Strangleroot Geist").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    geist = scenario.creature("Strangleroot Geist")
    assert (geist.power, geist.toughness) == (2, 1)

    _die_and_resolve(scenario, geist)

    assert geist.zone is Zone.BATTLEFIELD
    assert (geist.power, geist.toughness) == (3, 2)
    assert scenario.can_attack(geist)


def test_geralfs_messenger_returns_tapped_and_drains_again():
    scenario = _board("Geralf's Messenger").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    messenger = scenario.creature("Geralf's Messenger")
    messenger.tapped = False
    bob = scenario.player("bob")
    life = bob.life

    scenario.game.destroy(messenger)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert messenger.zone is Zone.BATTLEFIELD
    assert messenger.tapped
    assert messenger.counter_count(Counter.PLUS_ONE) == 1
    assert bob.life == life - 2


def test_flayer_returning_by_undying_enters_from_your_graveyard():
    """Flayer of the Hatebound's "Whenever this creature or another creature
    enters from your graveyard" fires for its own undying return - the
    return is a move from the graveyard to the battlefield (CR 603.6a)."""
    scenario = _board("Flayer of the Hatebound").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    flayer = scenario.creature("Flayer of the Hatebound")

    scenario.game.destroy(flayer)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    assert flayer.zone is Zone.BATTLEFIELD
    assert flayer.counter_count(Counter.PLUS_ONE) == 1
    assert (flayer.power, flayer.toughness) == (5, 3)
    (entering,) = scenario.game.stack
    assert entering.source_name == "Flayer of the Hatebound"
    assert entering.ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD
    assert entering.event is not None and entering.event.origin_zone is Zone.GRAVEYARD


def test_flayer_does_not_fire_for_a_creature_cast_from_hand():
    scenario = _board("Flayer of the Hatebound", "Forest", "Forest", hand=("Grizzly Bears",))
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Grizzly Bears", auto=True, username="alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_granted_undying_returns_the_creature():
    """Undying Evil: "Target creature gains undying until end of turn." - a
    granted undying works exactly as a printed one (CR 702.93a)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Swamp"], hand=["Undying Evil"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    scenario.cast_and_resolve("Undying Evil", auto=True, username="alice", targets=[bears])

    _die_and_resolve(scenario, bears)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert (bears.power, bears.toughness) == (3, 3)


def test_granted_undying_ends_with_the_turn_it_was_granted_for():
    """The returned creature is a new object (CR 400.7) without the grant."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Swamp"], hand=["Undying Evil"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    scenario.cast_and_resolve("Undying Evil", auto=True, username="alice", targets=[bears])
    _die_and_resolve(scenario, bears)
    scenario.game.add_counters(bears, Counter.MINUS_ONE, 1)
    scenario.state_based_actions()
    assert bears.counter_count(Counter.PLUS_ONE) == 0

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert bears.zone is Zone.GRAVEYARD

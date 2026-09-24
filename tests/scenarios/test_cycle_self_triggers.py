""" "When you cycle this card, ..." - a triggered ability that fires off the
card's own cycling (CR 702.29c).

CR 702.29c: "Some cards with cycling have abilities that trigger when they're
cycled. "When you cycle this card" means "When you discard this card to pay
an activation cost of a cycling ability." These abilities trigger from
whatever zone the card winds up in after it's cycled."

CR 702.29f: "Typecycling abilities are cycling abilities, and typecycling
costs are cycling costs. Any cards that trigger when a player cycles a card
will trigger when a card is discarded to pay an activation cost of a
typecycling ability."

CR 113.6k: "A trigger condition that can't trigger from the battlefield
functions in all zones it can trigger from." - which is why the trigger is
heard from the graveyard the cycled card lands in, and why an instant or
sorcery that prints one keeps it off its own resolution (CR 113.6: an instant
or sorcery's abilities otherwise function only on the stack).

Before this, `machines/abilities._trigger_event` read no event out of "you
cycle this card" at all, so the ability was dropped (Vizier of Tumbling Sands
scored silent) - and on an instant the trailing paragraph poisoned the
spell's own resolution text (Choking Tethers' "Tap up to four target
creatures." read as nothing).

Vizier of Tumbling Sands is the listed card; Windcaller Aven (a creature
with a differently worded effect) and Choking Tethers (the same trigger on
an instant) are the proof printings, both Modern-legal and in no api deck.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import cycling_activation
from magic_cards_model.models import CardState, Zone
from magic_cards_model.support import classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from

VIZIER = "Vizier of Tumbling Sands"
AVEN = "Windcaller Aven"
TETHERS = "Choking Tethers"


def cycle_onto_stack(scenario, cycled: CardState, *mana: CardState, username: str = "alice"):
    """Activate a cycling ability and leave it (and whatever it set off) on
    the stack - CR 702.29a's ability uses the stack and can be responded to."""
    activation = cycling_activation(scenario.game, cycled, username)
    payment = activation.begin_paying()
    for source in mana:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation


def test_vizier_untaps_its_target_before_the_cycling_draw() -> None:
    """The trigger goes on the stack above the cycling ability (CR 603.3,
    CR 117.3c hands priority straight back), so it resolves first: the
    permanent untaps while the draw is still waiting."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=[VIZIER], library=["Lightning Bolt"], battlefield=["Island", "Island"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()
    vizier = scenario.find(VIZIER, Zone.HAND, "alice")
    scenario.choose_trigger_targets(VIZIER, [bears])

    cycle_onto_stack(scenario, vizier, *scenario.untapped_sources("Island", "Island"))

    assert vizier.zone is Zone.GRAVEYARD
    assert len(scenario.game.stack) == 2
    assert scenario.stack_names()[-1] == f"{VIZIER}'s triggered ability"

    scenario.resolve_top()
    assert not bears.tapped
    assert scenario.find("Lightning Bolt", Zone.LIBRARY, "alice").zone is Zone.LIBRARY

    scenario.resolve_top()
    assert scenario.find("Lightning Bolt", Zone.HAND, "alice").zone is Zone.HAND


def test_vizier_can_untap_its_controllers_own_land() -> None:
    """ "untap target permanent" - any permanent, the cycler's own included:
    the Island just tapped to pay the cycling cost comes back."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=[VIZIER], library=["Lightning Bolt"], battlefield=["Island", "Island"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vizier = scenario.find(VIZIER, Zone.HAND, "alice")
    first, second = scenario.untapped_sources("Island", "Island")
    scenario.choose_trigger_targets(VIZIER, [first])

    cycle_onto_stack(scenario, vizier, first, second)
    assert first.tapped and second.tapped

    scenario.pass_until_resolved()
    assert not first.tapped
    assert second.tapped


def test_discarding_vizier_any_other_way_is_not_cycling_it() -> None:
    """CR 702.29c: only a discard *to pay a cycling cost* is cycling - an
    effect's discard puts it in the graveyard without the trigger."""
    scenario = (
        Scenario().player("alice", hand=[VIZIER], battlefield=["Island"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vizier = scenario.find(VIZIER, Zone.HAND, "alice")

    scenario.game.discard_cards("alice", [vizier])
    scenario.game.put_triggers_on_stack()

    assert vizier.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_cycling_a_different_card_does_not_set_off_vizier() -> None:
    """ "this card" is a self-reference: a Vizier in the graveyard (already
    cycled earlier) or on the battlefield hears only its own cycling."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Censor"],
            graveyard=[VIZIER],
            library=["Lightning Bolt"],
            battlefield=[VIZIER, "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    censor = scenario.find("Censor", Zone.HAND, "alice")

    cycle_onto_stack(scenario, censor, *scenario.untapped_sources("Island"))

    assert len(scenario.game.stack) == 1
    assert f"{VIZIER}'s triggered ability" not in scenario.stack_names()


def test_the_trigger_is_controlled_by_the_player_who_cycled() -> None:
    """Bob cycles his own Vizier on Alice's turn - an instant-speed activation
    (CR 702.29a has no timing restriction) - and the trigger is his."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=[VIZIER], library=["Lightning Bolt"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()
    vizier = scenario.find(VIZIER, Zone.HAND, "bob")
    scenario.choose_trigger_targets(VIZIER, [bears])

    cycle_onto_stack(
        scenario,
        vizier,
        *scenario.untapped_sources("Island", "Island", username="bob"),
        username="bob",
    )

    trigger = scenario.game.stack[-1]
    assert trigger.controller == "bob"
    scenario.resolve_top()
    assert not bears.tapped


def test_windcaller_aven_gives_its_target_flying_when_cycled() -> None:
    """Proof printing: the same "When you cycle this card" condition, a
    different effect - target creature gains flying until end of turn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[AVEN],
            library=["Lightning Bolt"],
            battlefield=["Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    aven = scenario.find(AVEN, Zone.HAND, "alice")
    scenario.choose_trigger_targets(AVEN, [bears])

    cycle_onto_stack(scenario, aven, *scenario.untapped_sources("Island"))
    assert scenario.stack_names()[-1] == f"{AVEN}'s triggered ability"
    scenario.pass_until_resolved()  # the cycle trigger
    scenario.pass_until_resolved()  # the cycling draw beneath it

    assert has_keyword(bears, Keyword.FLYING, scenario.game)
    assert scenario.find("Lightning Bolt", Zone.HAND, "alice").zone is Zone.HAND


def test_choking_tethers_cycle_trigger_taps_a_creature() -> None:
    """Proof printing on an instant: the trigger works from the graveyard
    the cycled instant lands in (CR 702.29c, CR 113.6k)."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=[TETHERS], library=["Lightning Bolt"], battlefield=["Island", "Island"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    tethers = scenario.find(TETHERS, Zone.HAND, "alice")
    scenario.choose_trigger_targets(TETHERS, [bears])
    scenario.will_take_the_may(True, source=TETHERS)

    cycle_onto_stack(scenario, tethers, *scenario.untapped_sources("Island", "Island"))
    assert scenario.stack_names()[-1] == f"{TETHERS}'s triggered ability"
    scenario.pass_until_resolved()

    assert bears.tapped


def test_choking_tethers_cast_as_a_spell_still_taps_up_to_four() -> None:
    """The cycle trigger is not part of the instant's own resolution: cast,
    it taps its targets and nothing else - the trailing "When you cycle"
    paragraph no longer poisons "Tap up to four target creatures."."""
    scenario = (
        Scenario()
        .player("alice", hand=[TETHERS], battlefield=["Island", "Island", "Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    scenario.cast_and_resolve(
        TETHERS,
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
        targets=[bears, wolf],
    )

    assert bears.tapped and wolf.tapped
    assert scenario.find(TETHERS, Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_the_sweep_reads_every_clause_of_the_cycle_trigger_cards() -> None:
    """`support.classify_clauses` measures what the engine runs: the cycle
    trigger is a real clause (not silent) on the creature and on the
    instant, and the instant's own spell text is read without it."""
    for name in (VIZIER, AVEN, TETHERS):
        outcomes = classify_clauses(card(name))
        assert outcomes, name
        assert {outcome.category for outcome in outcomes} == {"handled"}, (name, outcomes)
        assert any(outcome.source.startswith("triggered") for outcome in outcomes), (name, outcomes)

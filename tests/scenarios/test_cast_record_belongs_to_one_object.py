"""A cast record belongs to one object, never to a card id (CR 400.7).

CR 400.7: "An object that moves from one zone to another becomes a new object
with no memory of, or relation to, its previous existence." CR 400.7d is the
one bridge a cast crosses: "An ability of a permanent can reference
information about the spell that became that permanent as it resolved,
including what costs were paid to cast that spell or what mana was spent to
pay those costs." So a permanent spell's `CastRecord` follows it from the
stack onto the battlefield, and nowhere after that.

Battle 8 (B8-02): Subtlety and Wistfulness were evoked, died to their own
evoke sacrifice, and Living End returned them - and CR 702.74a's "if its evoke
cost was paid" read the record of the earlier cast, so both were sacrificed a
second time. The corner cases are every clause that reads a cast record:
evoke (an alternative cost, CR 118.9), kicker (CR 702.33d), mana spent
(CR 601.2h) and X (CR 107.3m's enters-with counters).

Mulldrifter and Mold Shambler are off the deck pool: they prove the fix is
the record's keying, not the evoke clause.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def settle(scenario: Scenario) -> None:
    """Put every waiting trigger on the stack and resolve the lot (CR 603.3)."""
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def spellbombs(scenario: Scenario) -> int:
    return sum(1 for state in scenario.game.battlefield if state.name == "Aether Spellbomb")


def cast_living_end(scenario: Scenario) -> None:
    living_end = scenario.find("Living End", Zone.HAND, "alice")
    scenario.game.put_on_stack(living_end, "alice")
    living_end.targets = []
    settle(scenario)


def test_an_evoked_subtlety_returned_by_living_end_stays_on_the_battlefield():
    """The reported line: the returned Subtlety was never cast (CR 400.7), so
    CR 702.74a's intervening *if* is false and it never triggers (CR 603.4)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Subtlety", "Counterspell", "Living End"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    counterspell = scenario.find("Counterspell", Zone.HAND, "alice")
    casting = scenario.cast("Subtlety")
    casting.use_keyword("Evoke", choosing=[counterspell])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    subtlety = scenario.resolve_top()
    settle(scenario)
    assert subtlety.zone is Zone.GRAVEYARD, "sanity: the evoked Subtlety was sacrificed"

    cast_living_end(scenario)

    assert subtlety.zone is Zone.BATTLEFIELD
    assert scenario.game.cast_record_of(subtlety) is None
    assert not scenario.game.intervening_if_notices


def test_an_evoked_mulldrifter_returned_by_living_end_draws_again_and_stays():
    """Off the deck pool, and a mana evoke cost rather than an exile cost: the
    unconditional enters trigger fires again for the new object, the
    conditional sacrifice does not."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Mulldrifter", "Living End"],
            library=["Island", "Island", "Island", "Island"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Mulldrifter")
    casting.use_keyword("Evoke")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))
    scenario.put_on_stack(casting)
    mulldrifter = scenario.resolve_top()
    settle(scenario)
    assert mulldrifter.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").library) == 2

    cast_living_end(scenario)

    assert mulldrifter.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").library) == 0


def test_a_returned_wistfulness_reads_no_mana_spent_and_no_evoke():
    """CR 601.2h's mana-spent clause is a cast record reader too: the {G}{G}
    trigger exiled one Spellbomb when Wistfulness was evoked, and must not
    exile the second when Living End returns it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Wistfulness", "Living End"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Aether Spellbomb", "Aether Spellbomb"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Wistfulness")
    casting.use_keyword("Evoke")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    wistfulness = scenario.resolve_top()
    settle(scenario)
    assert wistfulness.zone is Zone.GRAVEYARD
    assert spellbombs(scenario) == 1, "sanity: the {G}{G} trigger exiled one"

    cast_living_end(scenario)

    assert wistfulness.zone is Zone.BATTLEFIELD
    assert spellbombs(scenario) == 1


def test_a_kicked_creature_returned_without_being_cast_was_not_kicked():
    """Off the deck pool, and kicker (CR 702.33d) rather than an alternative
    cost: Mold Shambler's "if it was kicked" is true for the cast object and
    false for the one Living End returns."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Mold Shambler", "Living End"],
            battlefield=["Forest"] * 6,
        )
        .player("bob", battlefield=["Aether Spellbomb", "Aether Spellbomb"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Mold Shambler")
    casting.pay_kicker()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Forest"] * 6))
    scenario.put_on_stack(casting)
    bomb = next(state for state in scenario.game.battlefield if state.name == "Aether Spellbomb")
    scenario.choose_trigger_targets("Mold Shambler", [bomb])
    shambler = scenario.resolve_top()
    settle(scenario)
    assert spellbombs(scenario) == 1, "sanity: the kicked cast triggered"
    scenario.game.destroy(shambler)
    assert shambler.zone is Zone.GRAVEYARD

    cast_living_end(scenario)

    assert shambler.zone is Zone.BATTLEFIELD
    assert spellbombs(scenario) == 1


def test_a_returned_x_creature_enters_with_no_counters_from_the_old_cast():
    """CR 107.3m's X is the value announced for the spell that became the
    permanent; a Walking Ballista Living End returns was never cast, so it
    enters with none and dies to CR 704.5f."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Walking Ballista", "Living End"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Walking Ballista")
    payment = casting.determine_cost(x_value=1)
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    ballista = scenario.resolve_top()
    settle(scenario)
    assert ballista.counter_count("+1/+1") == 1
    scenario.game.destroy(ballista)

    cast_living_end(scenario)
    scenario.state_based_actions()

    assert ballista.zone is Zone.GRAVEYARD


def test_a_permanent_spell_still_reads_its_own_cast_after_it_resolves():
    """CR 400.7d, the bridge that stays: the evoked object on the battlefield
    finds the record of the spell it was."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Subtlety", "Counterspell"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    counterspell = scenario.find("Counterspell", Zone.HAND, "alice")
    casting = scenario.cast("Subtlety")
    casting.use_keyword("Evoke", choosing=[counterspell])
    casting.begin_paying().pay()
    spell = scenario.put_on_stack(casting)
    assert scenario.game.cast_record_of(spell).keyword == "Evoke"

    subtlety = scenario.resolve_top()

    assert subtlety.zone is Zone.BATTLEFIELD
    record = scenario.game.cast_record_of(subtlety)
    assert record is not None and record.keyword == "Evoke"

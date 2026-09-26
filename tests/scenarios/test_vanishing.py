"""Vanishing, CR 702.63 (read whole with `mise run rules:find 702.63`, CR
effective 2026-09-25):

    702.63a Vanishing is a keyword that represents three abilities.
    "Vanishing N" means "This permanent enters with N time counters on it,"
    "At the beginning of your upkeep, if this permanent has a time counter on
    it, remove a time counter from it," and "When the last time counter is
    removed from this permanent, sacrifice it."
    702.63b Vanishing without a number means "At the beginning of your
    upkeep, if this permanent has a time counter on it, remove a time counter
    from it" and "When the last time counter is removed from this permanent,
    sacrifice it."
    702.63c If a permanent has multiple instances of vanishing, each works
    separately.

The three abilities live in two places: the entering counters (CR 614.1c,
602.63a's first ability, only for numbered vanishing per 702.63b) are
`machines/replacement._vanishing_entering_counters`; the upkeep tick and the
last-counter sacrifice (`machines/keywords._vanishing_abilities`/
`_vanishing_effect`) are read the same way suspend's identical two-triggered-
abilities shape already is (CR 702.62a), over a battlefield permanent instead
of an exiled card. CR 603.4 is the intervening *if* on the upkeep tick;
CR 122.2 is why a sacrificed permanent's counters have already ceased to exist
by the time anything asks about them afterward, which is what makes CR 603.10a's
look-back (`CardState.last_known_counters`) the only way Deadly Grub's own
"if it had no time counters on it" dies trigger can still answer the question.

Deadly Grub (Vanishing 3, "When this creature dies, if it had no time counters
on it, create a 6/1 green Insect creature token with shroud.") is the reported
card. Aven Riftwatcher (Flying, Vanishing 3, "When this creature enters or
leaves the battlefield, you gain 2 life.") is a second, unrelated printing -
different colour, different body, no death trigger at all - added as a real
Scryfall printing (`scripts/add_card.py`) to prove the keyword is read off
`KeywordAbility.count`, never off Deadly Grub's own name.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import keyword_abilities
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support, ignored_keywords
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

GRUB = "Deadly Grub"
RIFTWATCHER = "Aven Riftwatcher"


def _advance_to_owners_next_upkeep(scenario: PlayedScenario, owner: str) -> None:
    """Walk the real turn machine forward to `owner`'s own next upkeep step -
    CR 702.63a says "at the beginning of *your* upkeep", so this steps clean
    through any other player's turn in between rather than firing on it.
    Whatever is on the stack is resolved on the way (CR 500.2). Untapping is a
    turn-based action (CR 502.1) `manual_turn_based_actions` switched off, so
    the untap step's own untapping is driven by hand, the same way
    `tests/scenarios/test_impending.py`'s own `advance_to` does."""
    for _ in range(80):
        if scenario.stack_names():
            _resolve_everything(scenario)
            continue
        scenario.advance()
        if scenario.step is Step.UNTAP:
            scenario.game.untap_step()
        if scenario.turn.active_player == owner and scenario.step is Step.UPKEEP:
            return
    raise AssertionError(f"never reached {owner}'s upkeep")


def _resolve_everything(scenario: PlayedScenario) -> None:
    """Resolve the whole stack, top down."""
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _board(
    *,
    hand: list[str] | None = None,
    battlefield: list[str] | None = None,
    graveyard: list[str] | None = None,
    opponent_battlefield: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand if hand is not None else [GRUB],
            battlefield=battlefield if battlefield is not None else ["Swamp"] * 3,
            graveyard=graveyard,
            library=["Swamp"] * 20,
        )
        .player(
            "bob",
            battlefield=opponent_battlefield if opponent_battlefield is not None else [],
            library=["Forest"] * 20,
        )
    )


# -- the keyword line itself --------------------------------------------------


def test_deadly_grub_prints_vanishing_3():
    ability = next(a for a in keyword_abilities(card(GRUB)) if a.canonical.lower() == "vanishing")
    assert ability.count == 3


def test_vanishing_is_no_longer_reported_as_an_ignored_keyword():
    """The regression audit's own acceptance test
    (`tests/test_sweep_pool.py::test_the_pool_wide_ignored_keyword_report_
    matches_the_expected_gap_list`) lists Vanishing as unbuilt; this is that
    gap closed, checked directly against `support.ignored_keywords` and
    `support.card_support`'s own per-keyword clause for both the reported
    card and the unrelated second printing."""
    assert "Vanishing" not in ignored_keywords(card(GRUB))
    assert "Vanishing" not in ignored_keywords(card(RIFTWATCHER))
    for name in (GRUB, RIFTWATCHER):
        (clause,) = [c for c in card_support(card(name)).clauses if c.text == "Vanishing"]
        assert clause.status == "handled"


# -- entering with time counters (the first ability, CR 614.1c) --------------


def test_cast_deadly_grub_enters_with_three_time_counters():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    grub = scenario.cast_and_resolve(GRUB, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))

    assert grub.zone is Zone.BATTLEFIELD
    assert grub.counter_count(Counter.TIME) == 3


def test_a_permanent_put_onto_the_battlefield_by_an_effect_also_enters_with_its_time_counters():
    """Flicker of Fate: "Exile target creature or enchantment, then return it
    to the battlefield under its owner's control." The returning object is
    new (CR 400.7) and was never cast - unlike impending's own version of this
    replacement, which only ever applies when its alternative cost was paid,
    CR 702.63a's wording carries no such condition, so the blinked Riftwatcher
    still enters with fresh time counters."""
    scenario = _board(hand=[RIFTWATCHER, "Flicker of Fate"], battlefield=["Plains"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riftwatcher = scenario.cast_and_resolve(
        RIFTWATCHER, *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    _resolve_everything(scenario)  # its own "enters" life gain trigger
    assert riftwatcher.counter_count(Counter.TIME) == 3
    _advance_to_owners_next_upkeep(scenario, "alice")
    _resolve_everything(scenario)
    assert riftwatcher.counter_count(Counter.TIME) == 2
    stamp_before = riftwatcher.zone_change_stamp

    scenario.cast_and_resolve(
        "Flicker of Fate", *scenario.untapped_sources("Plains", "Plains"), targets=[riftwatcher]
    )
    _resolve_everything(scenario)  # the blink's own re-entering life gain trigger

    assert riftwatcher.zone is Zone.BATTLEFIELD
    assert riftwatcher.zone_change_stamp != stamp_before
    assert riftwatcher.counter_count(Counter.TIME) == 3


def test_a_second_printing_reads_its_own_time_counter_count_off_the_keyword():
    """Aven Riftwatcher is Vanishing 3 too, but a different card entirely -
    the proof this reads `KeywordAbility.count`, not Deadly Grub's name."""
    scenario = _board(hand=[RIFTWATCHER], battlefield=["Plains"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    riftwatcher = scenario.cast_and_resolve(
        RIFTWATCHER, *scenario.untapped_sources("Plains", "Plains", "Plains")
    )

    assert riftwatcher.zone is Zone.BATTLEFIELD
    assert riftwatcher.counter_count(Counter.TIME) == 3
    assert has_keyword(riftwatcher, "flying", scenario.game)


# -- the upkeep tick (the second ability, with its intervening *if*) --------


def test_a_time_counter_comes_off_at_its_controllers_upkeep_and_not_the_opponents():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grub = scenario.cast_and_resolve(GRUB, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))

    _advance_to_owners_next_upkeep(scenario, "alice")
    assert any(GRUB in name for name in scenario.stack_names())  # on the stack, CR 603.3
    _resolve_everything(scenario)
    assert grub.counter_count(Counter.TIME) == 2

    _advance_to_owners_next_upkeep(scenario, "bob")
    assert not any(GRUB in name for name in scenario.stack_names())
    assert grub.counter_count(Counter.TIME) == 2


def test_counters_removed_some_other_way_stop_the_upkeep_tick():
    """Vampire Hexmage: "Sacrifice this creature: Remove all counters from
    target permanent." With no time counter left, CR 603.4's intervening *if*
    ("this permanent has a time counter on it") is false the next upkeep, so
    nothing goes on the stack and the permanent is not sacrificed - only
    `machines/keywords._vanishing_effect`'s own removal raises the
    last-counter event, the same scoped shape suspend's identical ability
    already has."""
    scenario = _board(battlefield=["Swamp"] * 3 + ["Vampire Hexmage"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grub = scenario.cast_and_resolve(GRUB, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    hexmage = scenario.creature("Vampire Hexmage")

    scenario.activate(hexmage, sacrificing=[hexmage], targets=[grub])
    _resolve_everything(scenario)
    assert grub.counter_count(Counter.TIME) == 0
    assert grub.zone is Zone.BATTLEFIELD

    _advance_to_owners_next_upkeep(scenario, "alice")
    assert not any(GRUB in name for name in scenario.stack_names())
    assert grub.zone is Zone.BATTLEFIELD


# -- the last-counter sacrifice (the third ability) --------------------------


def test_the_permanent_is_sacrificed_when_its_last_time_counter_is_removed():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grub = scenario.cast_and_resolve(GRUB, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))

    for remaining in (2, 1, 0):
        _advance_to_owners_next_upkeep(scenario, "alice")
        _resolve_everything(scenario)
        if remaining > 0:
            assert grub.counter_count(Counter.TIME) == remaining
            assert grub.zone is Zone.BATTLEFIELD

    assert grub.zone is Zone.GRAVEYARD


def test_deadly_grub_sacrificed_by_vanishing_creates_the_insect_token():
    """ "When this creature dies, if it had no time counters on it, create a
    6/1 green Insect creature token with shroud." CR 122.2/603.10a:
    `CardState.last_known_counters` still reads zero because the sacrifice
    already took the last counter off before the graveyard move."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grub = scenario.cast_and_resolve(GRUB, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))

    for _ in range(3):
        _advance_to_owners_next_upkeep(scenario, "alice")
        _resolve_everything(scenario)

    assert grub.zone is Zone.GRAVEYARD
    insects = [state for state in scenario.game.battlefield if state.token and state.name != GRUB]
    (insect,) = insects
    chars = scenario.game.characteristics_of(insect)
    assert (chars.power, chars.toughness) == (6, 1)
    assert has_keyword(insect, "shroud", scenario.game)


def test_deadly_grub_destroyed_with_time_counters_remaining_creates_nothing():
    """The corner case Deadly Grub's own text calls out by contrast: dying with
    time counters still on it - here, lethal combat damage right after it
    resolves, before any upkeep has ticked - makes no Insect."""
    scenario = _board(
        hand=[GRUB, "Lightning Bolt"], battlefield=["Swamp"] * 3 + ["Mountain"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grub = scenario.cast_and_resolve(GRUB, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    assert grub.counter_count(Counter.TIME) == 3

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[grub]
    )

    assert grub.zone is Zone.GRAVEYARD
    insects = [state for state in scenario.game.battlefield if state.token]
    assert insects == []


# -- Aven Riftwatcher: the enters/leaves life gain fires on both ends --------


def test_aven_riftwatcher_gains_life_entering_and_again_when_vanishing_sacrifices_it():
    """ "When this creature enters or leaves the battlefield, you gain 2
    life." - twice over the permanent's whole life: once as it enters, once
    more as vanishing's own sacrifice sends it to the graveyard."""
    scenario = _board(hand=[RIFTWATCHER], battlefield=["Plains"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    life_before_cast = scenario.player("alice").life

    riftwatcher = scenario.cast_and_resolve(
        RIFTWATCHER, *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    _resolve_everything(scenario)  # its own "enters" trigger, still to resolve
    assert scenario.player("alice").life == life_before_cast + 2

    for _ in range(3):
        _advance_to_owners_next_upkeep(scenario, "alice")
        _resolve_everything(scenario)

    assert riftwatcher.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == life_before_cast + 4

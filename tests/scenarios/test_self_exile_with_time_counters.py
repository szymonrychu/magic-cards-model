"""Scenario: a spell whose last instruction exiles itself with time counters.

"Exile `<this spell's name>` with `<n>` time counters on it." closes the
resolution text of the suspend spells that recur by themselves - Arc Blade
("Arc Blade deals 2 damage to any target. Exile Arc Blade with three time
counters on it. Suspend 3-{2}{R}") and Suspended Sentence ("Destroy target
creature an opponent controls. That player loses 3 life. Exile Suspended
Sentence with three time counters on it. Suspend 3-{1}{B}"). The card leaves
the stack for exile rather than its owner's graveyard, carrying the counters,
and since it has suspend it is then suspended: the keyword's own exile-zone
triggers bring it back on its owner's upkeeps.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 201.5** - text that refers to the object it's on by name means that
  particular object: the spell itself.
- **CR 608.2n** - an instant or sorcery is put into its owner's graveyard as
  the final part of its resolution; the spell's own exile instruction runs
  first, so it is no longer there to be moved.
- **CR 702.62b** - "A card is 'suspended' if it's in the exile zone, has
  suspend, and has a time counter on it."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario

LIBRARY = ["Island"] * 12


def resolve_everything(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def advance_to_upkeep_of(scenario: PlayedScenario, owner: str) -> None:
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == owner):
        resolve_everything(scenario)
        scenario.advance()


def test_arc_blade_deals_its_damage_then_exiles_itself_suspended():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Arc Blade"], battlefield=["Mountain"] * 5, library=LIBRARY)
        .player("bob", library=LIBRARY)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    blade = scenario.cast_and_resolve(
        "Arc Blade", *scenario.untapped_sources(*["Mountain"] * 5), targets=["bob"]
    )

    assert scenario.game.player("bob").life == 18
    assert blade.zone is Zone.EXILE, "CR 608.2n never moves it: it exiled itself first"
    assert blade.counter_count(Counter.TIME) == 3
    assert blade.is_suspended, "CR 702.62b: in exile, has suspend, has a time counter"
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_arc_blade_comes_back_off_its_owners_upkeeps_and_recurs_again():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Arc Blade"], battlefield=["Mountain"] * 5, library=LIBRARY)
        .player("bob", library=LIBRARY)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blade = scenario.cast_and_resolve(
        "Arc Blade", *scenario.untapped_sources(*["Mountain"] * 5), targets=["bob"]
    )

    for remaining in (2, 1):
        advance_to_upkeep_of(scenario, "alice")
        resolve_everything(scenario)
        assert blade.counter_count(Counter.TIME) == remaining

    advance_to_upkeep_of(scenario, "alice")
    resolve_everything(scenario)

    lives = [scenario.game.player(name).life for name in ("alice", "bob")]
    assert sum(lives) == 36, "cast free, it dealt its 2 damage to some target again"
    blade = scenario.find("Arc Blade", Zone.EXILE, "alice")
    assert blade.counter_count(Counter.TIME) == 3, "the free cast exiles itself again"
    assert blade.is_suspended


def test_suspended_sentence_destroys_drains_and_suspends_itself():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Suspended Sentence"], battlefield=["Swamp"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")

    sentence = scenario.cast_and_resolve(
        "Suspended Sentence", *scenario.untapped_sources(*["Swamp"] * 4), targets=[bears]
    )

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.game.player("bob").life == 17, "that player - the creature's controller"
    assert scenario.game.player("alice").life == 20
    assert sentence.zone is Zone.EXILE
    assert sentence.counter_count(Counter.TIME) == 3
    assert sentence.is_suspended
    assert scenario.game.unmodeled_trigger_effect_notices == []
    assert scenario.game.anaphoric_clause_notices == []


def test_a_countered_self_exiling_spell_goes_to_the_graveyard_without_counters():
    """The exile is one of the spell's own instructions (CR 608.2n's
    ordering), so a spell that never resolves never runs it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Arc Blade"], battlefield=["Mountain"] * 5, library=LIBRARY)
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"], library=LIBRARY)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blade = scenario.cast_onto_stack(
        "Arc Blade", *scenario.untapped_sources(*["Mountain"] * 5), targets=["bob"]
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Counterspell", username="bob", auto=True, targets=[blade])

    assert blade.zone is Zone.GRAVEYARD
    assert blade.counter_count(Counter.TIME) == 0
    assert scenario.game.player("bob").life == 20

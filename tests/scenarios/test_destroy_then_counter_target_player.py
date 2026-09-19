""" "Put a +1/+1 counter on each creature target player controls." - a
board-wide counter placement whose group is a *chosen player's* creatures
rather than "you control"/"each creature", printed after a destroy clause
(Twisted Fates) and as a leaves-the-battlefield trigger (Meadowboon).

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 122.1 / 122.5** - a +1/+1 counter, and placing one.
- **CR 603.6a** - a leaves-the-battlefield trigger looks back at the
  permanent as it last existed.
- **CR 400.7** - the two independent instructions of Twisted Fates' own
  text are not anaphorically linked - "each creature target player
  controls" is its own fresh target, not the destroyed permanent's
  controller.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_twisted_fates_destroys_and_counters_a_chosen_players_creatures() -> None:
    """ "Destroy target nonland permanent. Put a +1/+1 counter on each
    creature target player controls." - two independently targeted
    instructions in one card.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Twisted Fates"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    casting = scenario.cast("Twisted Fates")
    casting.choose_targets([bears, "bob"])
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", "Swamp")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert angel.counters["+1/+1"] == 1, "still on the battlefield, bob's own creature"


def test_meadowboon_off_set_counters_a_chosen_players_creatures_on_leaving() -> None:
    """Meadowboon (not in this pool, not the reported card): "When this
    creature leaves the battlefield, put a +1/+1 counter on each creature
    target player controls." - the identical group-selector clause, this
    time as a leaves-the-battlefield trigger rather than beside a destroy.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Meadowboon"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    meadowboon = scenario.creature("Meadowboon", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Meadowboon", ["bob"])

    scenario.game.destroy(meadowboon)
    scenario.game._before_priority()  # CR 603.3: stack the leaves trigger
    scenario.resolve_top()

    assert meadowboon.zone is Zone.GRAVEYARD
    assert bears.counters["+1/+1"] == 1

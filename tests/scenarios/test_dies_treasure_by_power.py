""" "When this creature dies, create a number of `<descriptor>` tokens equal
to its power." (R0a T8), and its live-battlefield "enters or attacks" twin.

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this
file.

- **CR 603.10a** - a dies trigger looks back in time at the object as it last
  existed.
- **CR 111.10a** - Treasure is "an artifact token with '{T}, Sacrifice this
  artifact: Add one mana of any color.'"
- **CR 122.2** - "Once a counter is removed from an object, it ceases to
  exist" - a permanent that leaves the battlefield keeps none of its
  counters.
- **CR 608.2h** - an effect naming a departed object's characteristic uses
  its last known information.

Goldvein Hydra ("Vigilance, trample, haste. This creature enters with X
+1/+1 counters on it. When this creature dies, create a number of tapped
Treasure tokens equal to its power.") is printed 0/0 (CR 208.1): its *entire*
power is +1/+1 counters, which is exactly the case
`machines/triggers.event_subject_power` documents as deliberately excluded
from its own last-known-power read (that function's own "the same last-known
-information convention `intervening_if_holds`'s own 'it had no -1/-1
counters on it' clause reads" note) - a continuous effect's contribution is
all it keeps, because CR 122.2 has already cleared `CardState.counters` by
the time the trigger resolves. `machines/effects._departed_stat_with_
counters` adds the counters back in from `CardState.last_known_counters`
(`Game._note_left_battlefield`'s own pre-clear snapshot), the same source
every other dies-trigger reader in this file uses (`hangarback_dies`'s "counters
if on the battlefield else last_known_counters"). Without it, a Hydra that
died at printed 0 power (no counters ever having been added, live or staged)
would correctly make zero tokens either way, which is why the test setting
counters explicitly is the one that actually proves the fix.

Generality is proven on Threefold Thunderhulk (legal Modern/Pioneer, not in
`code/magic-cards-model-api/decks/*.txt`): "Whenever this creature enters or
attacks, create a number of 1/1 colorless Gnome artifact creature tokens
equal to its power." - a different trigger event (enters/attacks, not dies),
a different token (a 1/1 Gnome, not a Treasure), and the creature is *still
on the battlefield* when the count is read, so "its power" is the live,
layer-computed characteristic (CR 613.5) rather than a last-known one -
proof `_departed_stat_with_counters` only adds the counters snapshot back in
for a subject that has actually left, and never double-counts a live one
whose counters the layer engine already folds into `.power`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

HYDRA = "Goldvein Hydra"
THUNDERHULK = "Threefold Thunderhulk"


def _board(**kwargs) -> Scenario:
    return Scenario().player("alice", **kwargs)


def test_goldvein_hydra_dies_makes_tapped_treasures_equal_to_its_counter_power():
    """The reported gap: the Hydra's whole power is +1/+1 counters (CR
    208.1's printed 0/0), which is cleared (CR 122.2) before the trigger
    resolves - proving the fix needs the counters read back from
    `last_known_counters`, not merely `event_subject_power` alone."""
    scenario = _board(battlefield=[HYDRA]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.find(HYDRA, Zone.BATTLEFIELD, "alice")
    hydra.add_counters(Counter.PLUS_ONE, 4)
    assert hydra.power == 4

    scenario.game.destroy(hydra)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    treasures = [c for c in scenario.game.battlefield if c.name == "Treasure Token"]
    assert len(treasures) == 4
    assert all(t.tapped for t in treasures)
    assert all(scenario.game.controller_of(t).username == "alice" for t in treasures)


def test_goldvein_hydra_dying_at_zero_power_makes_no_treasures():
    """CR 107.1b: a zero count is zero tokens, not an error - the Hydra
    with no counters at all is printed 0/0."""
    scenario = _board(battlefield=[HYDRA]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.find(HYDRA, Zone.BATTLEFIELD, "alice")
    assert hydra.power == 0

    scenario.game.destroy(hydra)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert not [c for c in scenario.game.battlefield if c.name == "Treasure Token"]


def test_threefold_thunderhulk_enters_making_tokens_equal_to_live_power():
    """Proof of generality: a different trigger event (enters), a different
    token, and the creature is still alive when the count is read - the live,
    layer-computed power (CR 613.5), not a last-known one."""
    scenario = _board(hand=[THUNDERHULK]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thunderhulk = scenario.put_onto_battlefield(THUNDERHULK, "alice")
    assert thunderhulk.zone is Zone.BATTLEFIELD
    # `put_onto_battlefield` is a real zone change (CR 400.7), unlike a
    # scenario's staged `battlefield=[...]`, so the printed "This creature
    # enters with three +1/+1 counters on it" static already applied.
    assert thunderhulk.power == 3

    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    gnomes = [c for c in scenario.game.battlefield if "Gnome" in c.name]
    assert len(gnomes) == 3
    assert thunderhulk.zone is Zone.BATTLEFIELD  # never moved: proves it read the live stat


def test_threefold_thunderhulk_attacking_makes_tokens_equal_to_live_power():
    """The same reader off the other half of "enters or attacks" - CR 508.1
    declares it, and the trigger reads the live power at that moment, not
    the printed base."""
    scenario = Scenario().player("alice", battlefield=[THUNDERHULK]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thunderhulk = scenario.find(THUNDERHULK, Zone.BATTLEFIELD, "alice")
    thunderhulk.add_counters(Counter.PLUS_ONE, 5)
    scenario.start_at(Step.BEGINNING_OF_COMBAT)

    scenario.attack_with(thunderhulk)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    gnomes = [c for c in scenario.game.battlefield if "Gnome" in c.name]
    assert len(gnomes) == 5

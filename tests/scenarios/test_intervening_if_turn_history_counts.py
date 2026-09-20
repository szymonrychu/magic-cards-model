"""An intervening *if* clause read as a count comparison or a negated
"didn't" over this turn's own history (CR 603.4, CR 121.2, CR 601.2i).

`intervening_if_holds` read neither shape at all, so both reported triggers
never fired, silently: Lyra, Tolarian Archangel's own "if you've drawn three
or more cards this turn" and Edgar, Moonlit Sovereign's own "if you didn't
cast a spell this turn" both fell through to `_fail_closed` every time,
recording an `InterveningIfNotice` instead of ever creating a token or
placing a counter, even when the stated condition plainly held.

Both are general shapes, not card-specific:

- **A count comparison over `Game.cards_drawn_this_turn`** (CR 121.2's
  individual draws, each incremented once) - the same four comparison
  words (`at least`/`more than`/`fewer than`/`exactly`, and the suffix
  `N or more`/`N or fewer`) `_counter_count_holds`/`_controlled_subtype_
  count_holds` already read for a counter or subtype count, applied here to
  a turn-history count instead. Lake-town Toymaker is the off-set proof:
  real, non-fra, not the reported card, printing a different count (two, not
  three) and a different trigger event (beginning of combat, not each end
  step) on the identical clause shape.
- **The negated "didn't cast a spell this turn"**, read off the identical
  `Game.spells_cast_this_turn` list `_spells_cast_this_turn_holds` already
  reads for the positive "you've cast N or more spells this turn" form.
  Nightpack Ambusher is the off-set proof: real, non-fra, not the reported
  card, a completely different effect (a Wolf token, not a +1/+1 counter) on
  the identical clause.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 603.4 (intervening *if*), CR 121.2 (each card is its own
draw), CR 601.2i (a cast spell is recorded the moment it is put on the
stack).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _advance_to_end_step(scenario: Scenario) -> None:
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()


def test_lyra_creates_a_token_after_drawing_three_cards_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lyra, Tolarian Archangel"],
            library=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.game.draw_cards("alice", 3)
    assert scenario.game.cards_drawn_this_turn.get("alice") == 3

    _advance_to_end_step(scenario)

    angels = [
        state for state in scenario.game.battlefield if state.token and "Angel" in state.subtypes
    ]
    assert len(angels) == 1
    assert angels[0].controller == "alice"


def test_lyra_does_not_create_a_token_with_only_two_cards_drawn():
    """The other side of the same fix: the trigger still checks the count,
    it does not simply fire regardless."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Lyra, Tolarian Archangel"], library=["Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.game.draw_cards("alice", 2)

    _advance_to_end_step(scenario)

    angels = [
        state for state in scenario.game.battlefield if state.token and "Angel" in state.subtypes
    ]
    assert angels == []


def test_lake_town_toymaker_pumps_a_creature_after_drawing_two_cards():
    """Off-set proof: real, non-fra, not the reported card - a different
    count (two), a different trigger event (beginning of combat), a
    different effect (a pump, not a token)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lake-town Toymaker", "Grizzly Bears"],
            library=["Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.game.draw_cards("alice", 2)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Lake-town Toymaker", [bears])

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()  # beginning of combat
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(bears).power == 5
    assert has_keyword(bears, "first strike", scenario.game)


def test_edgar_gets_two_counters_after_not_casting_a_spell_this_turn():
    scenario = (
        Scenario().player("alice", battlefield=["Edgar, Moonlit Sovereign"]).player("bob").build()
    )
    assert scenario.game.spells_cast_this_turn.get("alice", []) == []

    _advance_to_end_step(scenario)

    edgar = scenario.find("Edgar, Moonlit Sovereign", Zone.BATTLEFIELD, "alice")
    assert edgar.counter_count("+1/+1") == 2


def test_edgar_gets_no_counters_after_casting_a_spell_this_turn():
    """The other side of the same fix: casting a spell first turns the
    condition off, exactly as the card's own words say."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Edgar, Moonlit Sovereign", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    scenario.advance()  # combat
    scenario.advance()  # postcombat main
    scenario.advance()  # end step
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    edgar = scenario.find("Edgar, Moonlit Sovereign", Zone.BATTLEFIELD, "alice")
    assert edgar.counter_count("+1/+1") == 0


def test_nightpack_ambusher_creates_a_wolf_after_not_casting_a_spell():
    """Off-set proof: real, non-fra, not the reported card - a Wolf token,
    not a +1/+1 counter, on the identical negated clause."""
    scenario = Scenario().player("alice", battlefield=["Nightpack Ambusher"]).player("bob").build()

    _advance_to_end_step(scenario)

    wolves = [
        state
        for state in scenario.game.battlefield
        if state.token and "Wolf" in state.subtypes and state.name != "Nightpack Ambusher"
    ]
    assert len(wolves) == 1

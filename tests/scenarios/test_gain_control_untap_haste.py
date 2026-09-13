"""Scenario: "Gain control of target creature until end of turn. Untap that
creature. It gains haste until end of turn."

Act of Treason's three sentences are one template printed on dozens of cards
as a spell (Act of Treason, Claim the Firstborn, Hijack's "Untap it."), an
activated ability (Captivating Crew) and a triggered one (Conquering
Manticore). Three instructions:

- a layer 2 control change (CR 613.1b, "Layer 2: Control-changing effects are
  applied"), lasting until the cleanup step ends it (CR 514.2);
- a one-shot untap (CR 701.26b);
- a layer 6 haste grant for the same duration, which is what lets the new
  controller attack with it and pay {T} (CR 702.10b, CR 302.6).

Threaten prints the same effect in a different order ("Untap target creature
and gain control of it until end of turn. That creature gains haste until end
of turn.") and already read whole. This order did not: the layer parser read
the first sentence and silently skipped the other two, so the creature stayed
tapped and without haste, and the ability versions did nothing at all.

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def steal(spell: str, creature: str = "Grizzly Bears", *, automatic: bool = False, lands: int = 3):
    builder = Scenario()
    builder = (
        builder.automatic_turn_based_actions() if automatic else builder.manual_turn_based_actions()
    )
    scenario = (
        builder.player("alice", hand=[spell], library=["Forest"], battlefield=["Mountain"] * lands)
        .player("bob", library=["Forest"], battlefield=[creature])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature(creature, "bob")
    target.tapped = True
    mountains = scenario.untapped_sources(*["Mountain"] * lands, username="alice")
    scenario.cast_and_resolve(spell, *mountains, targets=[target])
    return scenario, target


def assert_stolen_untapped_hasty(scenario, target) -> None:
    board = scenario.game.computed_board()
    assert target.controller == "alice"
    assert board.of(target).controller == "alice"
    assert not target.tapped, "CR 701.26b: untapped"
    assert board.of(target).has_ability("Haste"), "CR 702.10b: haste until end of turn"
    assert scenario.game.why_cannot_attack(target, "bob") is None


def test_act_of_treason_takes_untaps_and_hastes():
    scenario, bears = steal("Act of Treason")
    assert_stolen_untapped_hasty(scenario, bears)


def test_the_stolen_creature_can_pay_its_own_tap_cost():
    """CR 302.6's {T} restriction is lifted by haste (CR 702.10b)."""
    scenario, mother = steal("Act of Treason", "Mother of Runes")
    assert scenario.game.why_cannot_activate(mother, 0) is None


def test_a_narrowed_target_reads_the_same_way():
    """Claim the Firstborn: "target creature with mana value 3 or less"."""
    scenario, bears = steal("Claim the Firstborn", lands=1)
    assert_stolen_untapped_hasty(scenario, bears)


def test_untap_it_is_the_same_instruction():
    """Hijack: "Gain control of target artifact or creature until end of turn.
    Untap it. It gains haste until end of turn." """
    scenario, bears = steal("Hijack")
    assert_stolen_untapped_hasty(scenario, bears)


def test_threaten_still_reads():
    scenario, bears = steal("Threaten")
    assert_stolen_untapped_hasty(scenario, bears)


def test_the_cleanup_step_gives_it_back_without_haste():
    """CR 514.2: "all 'until end of turn' and 'this turn' effects end"."""
    scenario, bears = steal("Act of Treason", automatic=True)
    assert_stolen_untapped_hasty(scenario, bears)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    board = scenario.game.computed_board()
    assert bears.controller == "bob"
    assert not board.of(bears).has_ability("Haste")


def test_an_activated_ability_with_the_same_words():
    """Captivating Crew: "{3}{R}: Gain control of target creature an opponent
    controls until end of turn. Untap that creature. It gains haste until end
    of turn. Activate only as a sorcery." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Captivating Crew", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crew = scenario.creature("Captivating Crew", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.activate(crew, *mountains, username="alice", targets=[bears])
    scenario.resolve_top()

    assert_stolen_untapped_hasty(scenario, bears)


def test_a_triggered_ability_with_the_same_words():
    """Conquering Manticore: "When this creature enters, gain control of target
    creature an opponent controls until end of turn. Untap that creature. It
    gains haste until end of turn." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Conquering Manticore"], library=["Forest"], battlefield=["Mountain"] * 6
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    mountains = scenario.untapped_sources(*["Mountain"] * 6, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.cast_and_resolve("Conquering Manticore", *mountains)
    if scenario.stack_names():
        scenario.resolve_top()

    assert_stolen_untapped_hasty(scenario, bears)

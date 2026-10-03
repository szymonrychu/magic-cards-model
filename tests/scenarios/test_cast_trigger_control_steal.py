"""Scenario: a cast trigger's optional payment consequence is Act of
Treason's own three-instruction control steal - "gain control of target
creature until end of turn, untap that creature, and it gains haste until
end of turn." - printed as one comma-joined sentence rather than three full
stops.

Eldrazi Obligator: "When you cast this spell, you may pay {1}{C}. If you do,
gain control of target creature until end of turn, untap that creature, and
it gains haste until end of turn." (Modern, Pioneer).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 118.12** - "[A player] may [do something]. If [that player] does,
  [effect]": the optional {1}{C} is a cost paid as the trigger resolves, and
  the three-instruction consequence runs only if it was paid.
- **CR 107.4c** - the colorless mana symbol {C} represents a cost that can be
  paid only with one colorless mana; **CR 106.1b** - colorless is one of the
  six types of mana, so a red source (a Mountain) cannot pay it.
- **CR 613.1b** - control-changing effects apply in layer 2.
- **CR 701.26b** - to untap a permanent, rotate it back to the upright
  position.
- **CR 603.3d** - the remainder of putting a triggered ability on the stack
  follows CR 601.2c-d; if a required choice (here, the mandatory "target
  creature") has no legal option, the ability is simply removed from the
  stack rather than going on it with nothing to point at.
- **CR 608.2b** - a target no longer in the zone it was in when targeted is
  illegal, and the rest of a resolving ability's effect still happens.

`_GAIN_CONTROL_THEN_UNTAP_RE` (`machines/effects.py`) already read Act of
Treason's three full-stop-separated sentences; Eldrazi Obligator prints the
identical instructions comma-joined inside the "if you do" consequence of
its own cast trigger, which needed both the regex widened to accept either
punctuation and `pay_consequence_effect` taught to try the control-steal
reader at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(bob_battlefield: list[str], *, wastes: int = 1) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Eldrazi Obligator"],
            battlefield=["Mountain"] * 4 + ["Wastes"] * wastes,
        )
        .player("bob", battlefield=bob_battlefield)
        .build()
    )


def test_paid_gains_control_untaps_and_grants_haste():
    scenario = _board(["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()  # so the untap half of the effect is actually visible
    scenario.choose_trigger_targets("Eldrazi Obligator", [bears])
    scenario.will_pay_the_mana_cost(True)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_onto_stack("Eldrazi Obligator", *sources)
    scenario.pass_until_resolved()  # the cast trigger

    assert bears.controller == "alice"
    assert not bears.tapped
    assert has_keyword(bears, Keyword.HASTE, scenario.game)


def test_declined_leaves_control_and_tapped_state_untouched():
    scenario = _board(["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()
    scenario.choose_trigger_targets("Eldrazi Obligator", [bears])
    scenario.will_pay_the_mana_cost(False)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_onto_stack("Eldrazi Obligator", *sources)
    scenario.pass_until_resolved()

    assert bears.controller == "bob"
    assert bears.tapped
    assert not has_keyword(bears, Keyword.HASTE, scenario.game)


def test_without_a_colorless_source_the_payment_is_never_offered():
    """CR 107.4c/106.1b: four Mountains can pay {2}{R} for the spell itself,
    but none of them can produce the one colorless mana {1}{C} needs, so the
    optional payment is never legal to accept and the default answer - no -
    applies with nothing queued, the same shape
    `test_may_pay_mana_consequences.py::test_skyline_scout_without_the_mana_cannot_pay`
    already proves for the mana-family reader."""
    scenario = _board(["Grizzly Bears"], wastes=0)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Eldrazi Obligator", [bears])
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.cast_onto_stack("Eldrazi Obligator", *sources)
    scenario.pass_until_resolved()

    assert bears.controller == "bob"
    assert not has_keyword(bears, Keyword.HASTE, scenario.game)


def test_no_legal_target_removes_the_trigger_before_it_reaches_the_stack():
    """CR 603.3d: with no creature at all on the battlefield when Eldrazi
    Obligator is cast, the mandatory "target creature" trigger has no legal
    choice and is simply never put on the stack - the spell itself still
    resolves, and the untapped colorless source proves the "may pay" question
    was never even asked."""
    scenario = _board([])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_onto_stack("Eldrazi Obligator", *sources)

    assert scenario.stack_names() == ["Eldrazi Obligator"]
    wastes = scenario.game.permanents_controlled_by("alice")
    assert any(state.name == "Wastes" and state.untapped for state in wastes)

    scenario.pass_until_resolved()
    assert "Eldrazi Obligator" in scenario.battlefield_names()


def test_a_target_removed_in_response_fizzles_the_control_steal():
    """CR 608.2b: the target is legal when chosen, but destroyed in response
    before the trigger resolves - the ability does nothing (no crash, no
    control change), and the spell underneath still resolves normally."""
    scenario = _board(["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Eldrazi Obligator", [bears])
    scenario.will_pay_the_mana_cost(True)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_onto_stack("Eldrazi Obligator", *sources)
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()  # the cast trigger, now targetless

    assert bears.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()  # Eldrazi Obligator itself
    assert "Eldrazi Obligator" in scenario.battlefield_names()

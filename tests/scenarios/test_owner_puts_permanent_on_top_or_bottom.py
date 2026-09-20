""" "The owner of up to one other target nonland permanent puts it on their
choice of the top or bottom of their library." - Plan for All Outcomes'
own enters-the-battlefield trigger.

CR 115.6's own "up to one" (verified this session) already covers a target
that turns out to be legally zero; the new ground here is CR 108.3's
ownership/control split over a *permanent* rather than Subtlety's own
spell-on-the-stack shape (`test_up_to_one_target_spell.py`,
`_parse_choose_up_to_one_target_spell_clauses`) - a single sentence, not a
two-clause merge, since "up to one ... target nonland permanent" and "puts
it on their choice ..." are one CR 608.2c instruction rather than an
antecedent and a separate anaphoric consequence.

`DecisionKind.PUT_ON_TOP_OR_BOTTOM` is asked of the permanent's *owner*, not
of Plan for All Outcomes' own controller - the same split
`test_up_to_one_target_spell.py` already proves for a spell, over a
permanent instead.

Every CR number here was looked up with `mise run rules:find <number>` in
the session that wrote this file: CR 108.3, CR 115.6, CR 401.1.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

PLAN = "Plan for All Outcomes"


def _board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=[PLAN], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_the_owner_not_the_caster_chooses_top_or_bottom_for_an_opponents_permanent():
    """Bob owns Grizzly Bears; alice controls Plan for All Outcomes. The
    choice belongs to bob, scripted to the bottom so a default-matches-top
    coincidence cannot pass this test."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")

    scenario.choose_trigger_targets(PLAN, [bears])
    scenario.will_choose_top(False, username="bob")
    scenario.cast_onto_stack(PLAN, *islands, username="alice")
    scenario.pass_until_resolved()  # Plan for All Outcomes resolves and enters
    scenario.pass_until_resolved()  # its own ETB trigger resolves

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is bears


def test_choosing_no_target_at_all_leaves_the_battlefield_untouched():
    """CR 115.6: "up to one" may legally choose nothing, and CR 608.2d never
    asks an owner a question that never arises."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")

    scenario.choose_trigger_targets(PLAN, [])
    scenario.cast_onto_stack(PLAN, *islands, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.questions_asked() == []

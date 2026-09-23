"""Scenario: Gather Specimens - "If a creature would enter the battlefield
under an opponent's control this turn, it enters under your control
instead." A CR 614.1a replacement effect a resolving spell creates, read by
`machines/replacement.created_replacement_spec` and held on
`Game.created_replacements` (see `test_enter_under_your_control_instead.py`
for its corner cases). `ControlReplacementNotice` stays as the fail-closed
net for a wording of the same shape that reader does not take; Gather
Specimens itself no longer lands in it.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 614.1a** - "Effects that use the word 'instead' are replacement
  effects."
- **CR 616.1b** - a replacement that would modify under whose control an
  object would enter the battlefield is chosen first.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_gather_specimens_is_built_and_records_no_control_replacement_notice():
    scenario = (
        Scenario()
        .player("alice", hand=["Gather Specimens"], battlefield=["Island"] * 6)
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 6)

    scenario.cast_and_resolve("Gather Specimens", *sources)

    assert scenario.game.control_replacement_notices == []
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.put_onto_battlefield("Grizzly Bears", "bob")

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"

"""Frostbite Pyromental's own unconditional end-step self-sacrifice:
"At the beginning of the end step, sacrifice this creature." - widening
`_SACRIFICE_IT_RE` this session to also read "sacrifice this creature",
not only the literal "sacrifice it".

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 701.21a** - to sacrifice a permanent, its controller moves it to
  the graveyard; no target, no "may".
- **CR 500.8** - the end step, where this ability triggers.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_frostbite_pyromental_sacrifices_itself_at_the_end_step() -> None:
    scenario = (
        Scenario().player("alice", battlefield=["Frostbite Pyromental"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    frostbite = scenario.creature("Frostbite Pyromental", "alice")

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.resolve_top()  # the end-step self-sacrifice trigger

    assert frostbite.zone is Zone.GRAVEYARD

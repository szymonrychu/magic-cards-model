"""Scenario: an instant or sorcery whose last sentence is "Exile `<its own
name>`." - `effect_for`'s `_strip_self_exile_sentence`/`_then_exile_self`:
the rest of the text resolves, then the spell exiles itself instead of CR
608.2n putting it into its owner's graveyard.

Eldritch Evolution is the reported card (`test_sacrificed_mana_value_bound.
py`). Flood of Recollection (Modern- and Pioneer-legal, in no
`magic-cards-model-api` deck) is the off-pool proof: a targeted return
rather than a search.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 201.5** - "Text that refers to the object it's on by name means just
  that particular object."
- **CR 608.2n** - "As the final part of an instant or sorcery spell's
  resolution, the spell is put into its owner's graveyard" - which a spell
  that has already exiled itself never reaches.
- **CR 608.2b** - a spell whose every target is illegal does not resolve, so
  none of its instructions - the self-exile included - happen.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

FLOOD = "Flood of Recollection"


def _board() -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[FLOOD],
            battlefield=["Island", "Island"],
            graveyard=["Opt", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_flood_of_recollection_returns_the_card_and_exiles_itself():
    scenario = _board()
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    islands = scenario.untapped_sources("Island", "Island")

    flood = scenario.cast_and_resolve(FLOOD, *islands, targets=[opt])

    assert opt.zone is Zone.HAND
    assert flood.zone is Zone.EXILE
    assert [state.name for state in scenario.player("alice").graveyard] == ["Grizzly Bears"]


def test_flood_of_recollection_with_its_target_gone_goes_to_the_graveyard():
    """CR 608.2b: with its only target gone the spell does not resolve at
    all - no return and no self-exile; it is put into the graveyard."""
    scenario = _board()
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    islands = scenario.untapped_sources("Island", "Island")
    scenario.cast_onto_stack(FLOOD, *islands, targets=[opt])
    scenario.game.exile_cards([opt])

    flood = scenario.resolve_top()

    assert flood.zone is Zone.GRAVEYARD

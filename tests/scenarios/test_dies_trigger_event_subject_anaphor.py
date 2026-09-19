""" "When enchanted creature dies, return that card to the battlefield ...":
"that card" is CR 400.7's anaphor for the *triggering event's own subject* -
the creature the Aura was attached to - not the Aura's own source
(`test_dies_trigger_self_reference.py`'s "it" is that different, self-
referential case, Rancor's own "return it to its owner's hand"). Ferocity of
the Hunt's own body was never read: the trigger fired (`condition_matches`
already recognises "when enchanted creature dies"), but nothing in `machines/
effects.py` knew what "that card" meant, so the dead creature simply stayed
in the graveyard with no notice at all.

`_parse_return_event_subject_to_battlefield_clause` reads
`AbilityOnStack.event.subject_id` - the same field `event_subject_power`
already reads for a dying creature's power - to find the card CR 603.10a's
look-back names, the way `event_subject_power`'s own docstring describes.

Verified this session with `mise run rules:find` (on-disk CR effective
2026-09-25):

- **CR 400.7** - an object that changes zones becomes a new object; "that
  card" is Oracle's own anaphor back to the one the event just happened to.
- **CR 603.10a** - "leaves-the-battlefield abilities" look back in time,
  which is what still lets this trigger find the creature after it has
  already left.
- **CR 704.5m** - an Aura attached to nothing is put into its owner's
  graveyard - the state-based action that also moves the Aura itself the
  instant its enchanted creature dies.
- **CR 108.3** - a card's owner, which "under its owner's control" sends the
  returned creature to - not necessarily the Aura's controller.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ferocity_of_the_hunt_returns_the_dead_creature_tapped_to_its_owner():
    """The reported card: Ferocity of the Hunt enchants an opponent's
    creature, so "its owner's control" (bob) is a real, different answer
    than "your control" (alice, the Aura's own controller) would be."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ferocity of the Hunt"],
            battlefield=["Swamp", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Forest")
    ferocity = scenario.cast_and_resolve("Ferocity of the Hunt", *sources, targets=[bears])
    assert ferocity.attached_to == bears.id

    scenario.game.destroy(bears)
    scenario.state_based_actions()  # CR 704.5m: Ferocity itself falls off too
    assert ferocity.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Ferocity of the Hunt's triggered ability"]
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "bob", "its owner, not the Aura's own controller"
    assert bears.tapped


def test_unhallowed_pact_returns_under_the_auras_own_controller_off_pool():
    """Off-pool generality proof: Unhallowed Pact's real, near-identical
    printing - "under your control" (the Aura's controller), not "under its
    owner's control", and no "tapped" - exercising the other half of
    `_RETURN_EVENT_SUBJECT_TO_BATTLEFIELD_RE`'s alternation and proving the
    parser is not fitted to Ferocity of the Hunt's own exact wording."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Unhallowed Pact"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    pact = scenario.cast_and_resolve("Unhallowed Pact", *sources, targets=[bears])
    assert pact.attached_to == bears.id

    scenario.game.destroy(bears)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice", "the Aura's own controller, per its own wording"
    assert not bears.tapped

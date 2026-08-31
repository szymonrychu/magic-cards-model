"""Scenario: Gather Specimens - "If a creature would enter the battlefield
under an opponent's control this turn, it enters under your control
instead." A CR 614.1a `IF_WOULD_INSTEAD` replacement effect, recognised by
shape (`_CONTROL_REPLACEMENT_RE` in `machines/effects.py`) but not built:
recorded as a `ControlReplacementNotice` rather than silently doing nothing.

Two real primitives are missing, not one:

- `machines/replacement.ReplaceableEvent` has no field a replacement could
  set to redirect an entering permanent's controller -
  `Game.put_onto_battlefield` sets `card_state.controller` *before*
  `apply_replacements` runs and never reconsiders it.
- `machines/replacement.py`'s own `parse_replacement_effects` only ever reads
  a *permanent's own printed* static-ability text; nothing here represents a
  temporary, "this turn"-scoped replacement rule conjured by a resolving
  instant or sorcery and watching every future zone change, the way a
  permanent's own printed replacement effect (Gather Specimens is neither -
  it is the spell itself that would need to install a watcher).

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 614.1a** - "If [event] would [happen], [replacement] instead" - the
  general shape of a replacement effect.
- **CR 110.2a** - "If an effect instructs a player to put an object onto the
  battlefield, that object enters the battlefield under that player's
  control unless the effect states otherwise" - the default this card is
  trying to override and cannot.
- **CR 616.1b** - "If any of the replacement and/or prevention effects would
  modify under whose control an object would enter the battlefield, one of
  them must be chosen" - the choice mechanism this engine has nowhere to
  register Gather Specimens' own effect into.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import ControlReplacementNotice
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_gather_specimens_records_a_control_replacement_notice():
    """The spell resolves - it is a real object that goes on the stack and
    comes off it (CR 608.2n) - but nothing it says actually happens: no
    watcher is installed, so a creature entering under bob's control later
    the same turn still ends up under bob's control, unaffected."""
    scenario = (
        Scenario()
        .player("alice", hand=["Gather Specimens"], battlefield=["Island"] * 6)
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 6)

    scenario.cast_and_resolve("Gather Specimens", *sources)

    notices = scenario.game.control_replacement_notices
    assert len(notices) == 1
    assert isinstance(notices[0], ControlReplacementNotice)
    assert notices[0].source_name == "Gather Specimens"

    # The unbuilt half, made concrete: a creature entering under bob's own
    # control still ends up there, exactly as CR 110.2a's default says,
    # because nothing here is actually watching for it the way the card's
    # text claims - no field on `ReplaceableEvent` for a watcher to have set.
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.put_onto_battlefield("Grizzly Bears", "bob")

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "bob"

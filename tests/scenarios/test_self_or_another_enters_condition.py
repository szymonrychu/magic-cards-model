"""Scenario: "`<self>` or another creature you control enters" (CR 603.6a).

Mabel, Valley Hero: "Whenever Mabel or another creature you control enters,
put a +1/+1 counter on target creature that entered this turn." Before this
fix, `machines/triggers._SELF_OR_OTHER_ENTERS_RE` only ever matched a
condition that began with the literal words "this `<noun>`" (Campsite
Cuisine's "this enchantment or a legendary creature you control enters") -
never the source's own printed name. Mabel's own condition begins "Mabel or
another ...", so the regex never matched at all: `condition_matches` fell
through to its ordinary single-subject reading, under which "another" in the
condition text made the source's own entry fail (`if "another" in lowered
and event.subject_id == source.id: return False`) - Mabel's own entry never
triggered her, and only "another creature you control" ever did.

The fix, `machines/triggers._self_or_other_enters_match`: reads the self half
against `machines/abilities.self_reference_names` (CR 201.5, 201.5c) - the
source's own full name, or any shortened form it prints itself as - not only
CR 700.7's "this `<noun>`".

Ardoz, Cobbler of War - not in this fix's own design pool - proves it
generalises: "Whenever Ardoz or another creature you control enters, that
creature gets +2/+0 until end of turn." reads its own short form before the
comma (CR 201.5c) the identical way Mabel's does.

Every board here uses `put_onto_battlefield` (the Tooth and Nail path, CR
603.6a's event with none of CR 601's casting scaffolding) so the test is
about the condition alone, not sorcery-speed timing or mana.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 603.6a** - "Enters-the-battlefield abilities trigger when a permanent
  enters the battlefield."
- **CR 201.5c** - "Text printed on some cards refers to that card by a
  shortened version of its name. Instances of a card's shortened name used in
  this manner are treated as though they used the card's full name."
"""

from tests.scenarios.harness import Scenario


def test_mabel_triggers_on_her_own_entry():
    """The self half - Mabel's own "Mabel or another ..." condition must
    fire for Mabel herself, not only for a *different* creature entering."""
    scenario = Scenario().player("alice", hand=["Mabel, Valley Hero"]).player("bob").build()

    scenario.put_onto_battlefield("Mabel, Valley Hero")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Mabel, Valley Hero's triggered ability"]


def test_mabel_triggers_on_another_creature_entering():
    """The other half - a *different* creature Alice controls entering."""
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Mabel, Valley Hero"])
        .player("bob")
        .build()
    )

    scenario.put_onto_battlefield("Grizzly Bears")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Mabel, Valley Hero's triggered ability"]


def test_mabel_does_not_trigger_on_an_opponents_creature():
    """ "another creature **you control**" - Bob's own Grizzly Bears entering
    is not Alice's, so Mabel's trigger must not fire for it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mabel, Valley Hero"])
        .player("bob", hand=["Grizzly Bears"])
        .build()
    )

    scenario.put_onto_battlefield("Grizzly Bears", username="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_ardoz_off_set_proof_triggers_on_his_own_entry():
    """The off-set proof: a card outside this fix's own design pool, using
    the identical CR 201.5c comma-short-name shape."""
    scenario = Scenario().player("alice", hand=["Ardoz, Cobbler of War"]).player("bob").build()

    scenario.put_onto_battlefield("Ardoz, Cobbler of War")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Ardoz, Cobbler of War's triggered ability"]

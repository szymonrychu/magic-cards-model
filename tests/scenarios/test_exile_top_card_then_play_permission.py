""" "Exile the top card of your library. You may play that card this turn." -
a mandatory exile (no "you may" on the exile itself) followed by a bounded
CR 601.3 play permission, printed identically on both a triggered ability
and an activated one.

Card text, confirmed with `resolve_cards` in the session that wrote this
file:

Invasion of Kaldheim // Pyre of the World Tree (back face, an Enchantment):
    Whenever you discard a land card, exile the top card of your library.
    You may play that card this turn.

Charforger (Creature, Modern/Pioneer legal):
    Remove three oil counters from this creature: Exile the top card of
    your library. You may play that card this turn.

`test_discard_quality_card_trigger.py` already proves this consequence from
Pyre of the World Tree's own triggered ability (discarding a land). This
file proves the identical `machines/effects._parse_exile_top_card_then_play_
permission_clause` reader a second, structurally different way -
`activated_effect_for` rather than `trigger_effect_for` - on Charforger's
activated ability, whose own cost (removing oil counters, not a target or a
discard) is unrelated to the consequence being proven.

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is" - the exile itself carries no "you may".
- **CR 601.3** - a rule or effect granting permission to play a card lets
  its controller do so under that permission, for as long as it is stated.
- **CR 118.3** - removing counters as a cost is paid by removing exactly
  that many, with no further choice.
"""

from tests.scenarios.harness import Scenario


def test_charforger_exiles_the_top_card_and_grants_a_this_turn_play_permission():
    scenario = (
        Scenario()
        .player("alice", library=["Grizzly Bears", "Forest"], battlefield=["Charforger"])
        .player("bob")
        .build()
    )
    charforger = scenario.creature("Charforger", "alice")
    alice = scenario.player("alice")
    bears = alice.library[0]

    # Staged straight to three oil counters - the cost this ability removes.
    charforger.counters.add("oil", 3)

    scenario.activate(charforger, username="alice")
    scenario.resolve_top()

    assert charforger.counter_count("oil") == 0, "the activation's own cost was paid"
    assert bears.zone.value == "exile", "exiled off the top of the library"
    permission = scenario.game.play_permissions
    assert any(
        granted.card_id == bears.id and granted.action.value == "play" for granted in permission
    ), "granted this-turn play permission"

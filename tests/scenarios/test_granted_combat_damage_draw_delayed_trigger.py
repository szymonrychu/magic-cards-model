"""Lyra, Tolarian Archangel's own "{3}{U}{U}: Until end of turn, whenever
Lyra deals combat damage to a player, draw two cards." - a granted delayed
triggered ability (CR 603.7a) watching the same `TriggerEvent.DEALS_DAMAGE`
an ordinary printed "deals combat damage to a player" trigger already
watches, unchanged by this stream's own recipient-side work on that event.

`DelayedTrigger.matches` had no way to read "combat"/"to a player" off a
string condition the way `machines/triggers.condition_matches` does for a
printed ability - `combat_only`/`to_player_only` are the two new filter
fields this needs, alongside `subject_id` pinning the delayed trigger to
Lyra herself.

No other printed Magic card shares this exact self-referential "granted
delayed trigger off an activated ability, draws cards on combat damage to a
player" shape (Subira, Tulzidi Caravanner's own printing is the closest
real analogue, but it watches "a creature you control", not itself, and
needs an additional power restriction this file's own negative lookahead
deliberately excludes) - so there is no off-pool card to prove generality
against; `_parse_until_end_of_turn_self_combat_damage_draw_clause`'s own
regex is still not hardcoded to "Lyra" (it reads "this creature"/"this
permanent"/any capitalized self-name generically, off whatever `machines.
abilities.self_normalized_effect_text` hands it), which is verified
directly in this file against the normalized text rather than the literal
card name.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import (
    _UNTIL_END_OF_TURN_SELF_COMBAT_DAMAGE_DRAW_RE,
    _parse_until_end_of_turn_self_combat_damage_draw_clause,
)
from tests.scenarios.harness import Scenario


def test_lyra_draws_two_cards_when_she_deals_combat_damage_to_a_player_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lyra, Tolarian Archangel"] + ["Island"] * 5,
            library=["Mountain", "Forest"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lyra = scenario.creature("Lyra, Tolarian Archangel", "alice")

    scenario.activate(lyra, auto=True)  # {3}{U}{U}
    scenario.pass_until_resolved()  # the activated ability itself

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(scenario.player("bob"), 5, source=lyra)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Lyra, Tolarian Archangel's triggered ability"]
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 2


def test_lyra_does_not_fire_for_noncombat_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lyra, Tolarian Archangel"] + ["Island"] * 5,
            library=["Mountain"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lyra = scenario.creature("Lyra, Tolarian Archangel", "alice")

    scenario.activate(lyra, auto=True)
    scenario.pass_until_resolved()

    scenario.game.deal_damage(scenario.player("bob"), 5, source=lyra)  # not marked combat
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_lyra_does_not_fire_for_combat_damage_to_a_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lyra, Tolarian Archangel"] + ["Island"] * 5,
            library=["Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lyra = scenario.creature("Lyra, Tolarian Archangel", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(lyra, auto=True)
    scenario.pass_until_resolved()

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(bears, 5, source=lyra)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_the_clause_parser_reads_the_normalized_self_reference_not_the_literal_name():
    """`_self_normalized_effect_text` turns "Lyra" into "this permanent"
    before this parser ever sees the text (CR 201.5) - proof that the
    parser itself is not keyed to any card name."""
    normalized = (
        "Until end of turn, whenever this permanent deals combat damage to a player, "
        "draw two cards."
    )
    assert _UNTIL_END_OF_TURN_SELF_COMBAT_DAMAGE_DRAW_RE.fullmatch(normalized) is not None
    assert _parse_until_end_of_turn_self_combat_damage_draw_clause(normalized) is not None
    # Subira, Tulzidi Caravanner's own non-self shape must not be swept up.
    non_self = (
        "Until end of turn, whenever a creature you control with power 2 or less "
        "deals combat damage to a player, draw a card."
    )
    assert _parse_until_end_of_turn_self_combat_damage_draw_clause(non_self) is None

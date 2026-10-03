"""Scenario: "Return a `<quality>` card at random from your graveyard to the
battlefield." - a random pick out of a filtered graveyard, CR 608.2c's
resolving ability doing exactly what it is printed to do.

Tomb Tyrant: "{2}{B}, {T}, Sacrifice a creature: Return a Zombie creature
card at random from your graveyard to the battlefield. Activate only during
your turn and only if there are at least three Zombie creature cards in
your graveyard." The cost and the "at least three" activation restriction
are a separate workstream's, and this engine already fails *closed* on that
restriction: it refuses the activation outright (CR 602.5b) rather than
allowing it unchecked, unconditionally, since the restriction's own text is
not read yet - so no board state can activate Tomb Tyrant through the real
game loop until that restriction reader exists. Every test here reaches the
parsed effect directly instead, the same way `test_counters_that_many_
trigger.py` reaches Marauding Mako's own effect when its triggering path
cannot yet be constructed live.

Kheru Lich Lord's own upkeep trigger contains the identical fragment for a
bare "creature" quality ("return a creature card at random from your
graveyard to the battlefield") inside a larger sentence this reader does not
own (the "you may pay" condition ahead of it, the granted keywords and
delayed exile after it) - proving the reader off that real fragment rather
than off Tomb Tyrant's own "Zombie creature" sentence.

"At random" has no single dedicated CR paragraph of its own (see
`machines/effects.py`'s own docstring on `_RETURN_A_CARD_AT_RANDOM_FROM_
GRAVEYARD_RE`); this reuses the reproducible, seeded `Random` every other
"at random" instruction in this engine already reads through
(`Game.shuffle_seed`/`Game.shuffles_performed`).

Every CR number here was looked up with `mise run rules:find <n>` in the
session that wrote this file:

- **CR 608.2c** - the controller of a resolving ability follows its
  instructions in the order written.
- **CR 609.3** - an effect that attempts something impossible does only as
  much as possible (a graveyard with no matching card).
- **CR 602.5b** - an activation whose restriction is not met is illegal.
"""

import re

from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.effects import _parse_return_a_card_at_random_from_graveyard_clause
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_tomb_tyrant_returns_one_of_three_zombies_at_random():
    """Three real Zombie creature cards in the graveyard - the number the
    printed restriction itself asks for, even though this engine cannot
    read that restriction's own text yet - and a non-Zombie stand-in
    (Runeclaw Bear) that must never be picked. Reached through the parsed
    effect directly (see the module docstring); exactly one of the three
    Zombies ends up on the battlefield, the other two and the non-Zombie
    stay in the graveyard."""
    effect = _tomb_tyrants_own_effect()
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tomb Tyrant"],
            graveyard=["Carrion Feeder", "Grave Scrabbler", "Fatestitcher", "Runeclaw Bear"],
        )
        .player("bob")
        .build()
    )
    tyrant = scenario.creature("Tomb Tyrant")
    ability = _tomb_tyrants_ability_on_stack(tyrant)
    zombies = {"Carrion Feeder", "Grave Scrabbler", "Fatestitcher"}

    effect(scenario.game, ability)

    battlefield_names = {state.name for state in scenario.game.battlefield}
    graveyard_names = [state.name for state in scenario.player("alice").cards_in(Zone.GRAVEYARD)]
    returned = zombies & battlefield_names
    assert len(returned) == 1
    assert "Runeclaw Bear" in graveyard_names
    assert len(graveyard_names) == 3


def _tomb_tyrants_own_effect():
    effect = parse_abilities(card("Tomb Tyrant"))[1].effect
    assert (
        effect == "Return a Zombie creature card at random from your graveyard to the battlefield."
    )
    parsed = _parse_return_a_card_at_random_from_graveyard_clause(effect, for_spell=False)
    assert parsed is not None
    return parsed


def _tomb_tyrants_ability_on_stack(source) -> AbilityOnStack:
    return AbilityOnStack(
        kind=AbilityKind.ACTIVATED,
        ability=parse_abilities(card("Tomb Tyrant"))[1],
        source_id=source.id,
        source_name="Tomb Tyrant",
        controller="alice",
        event=None,
    )


def test_the_pick_is_confined_to_the_zombies():
    """Two Zombies and a non-Zombie in the graveyard: whichever the random
    pick lands on, it is one of the two Zombies, never the non-Zombie
    stand-in (Runeclaw Bear), and exactly one card moves."""
    effect = _tomb_tyrants_own_effect()
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tomb Tyrant"],
            graveyard=["Carrion Feeder", "Grave Scrabbler", "Runeclaw Bear"],
        )
        .player("bob")
        .build()
    )
    tyrant = scenario.creature("Tomb Tyrant")
    ability = _tomb_tyrants_ability_on_stack(tyrant)

    effect(scenario.game, ability)

    battlefield_names = {state.name for state in scenario.game.battlefield}
    graveyard_names = [state.name for state in scenario.player("alice").cards_in(Zone.GRAVEYARD)]
    returned = {"Carrion Feeder", "Grave Scrabbler"} & battlefield_names
    assert len(returned) == 1
    assert "Runeclaw Bear" in graveyard_names
    assert len(graveyard_names) == 2


def test_no_matching_card_returns_nothing():
    """CR 609.3: a graveyard with no Zombie creature card at all leaves the
    ability resolving to no effect, not an error - a real situation
    (opponent removes every Zombie from the graveyard in response to the
    activation, before this resolves), not only a synthetic one."""
    effect = _tomb_tyrants_own_effect()
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tomb Tyrant"], graveyard=["Runeclaw Bear"])
        .player("bob")
        .build()
    )
    tyrant = scenario.creature("Tomb Tyrant")
    ability = _tomb_tyrants_ability_on_stack(tyrant)

    effect(scenario.game, ability)

    graveyard_names = [state.name for state in scenario.player("alice").cards_in(Zone.GRAVEYARD)]
    assert graveyard_names == ["Runeclaw Bear"]


def test_the_reader_generalizes_off_kheru_lich_lords_own_fragment():
    """Kheru Lich Lord's real printed text contains the identical fragment
    for a bare "creature" quality, inside a larger sentence this reader does
    not own - proven on the real substring, not a hand-typed stand-in."""
    oracle_text = card("Kheru Lich Lord").oracle_text
    match = re.search(
        r"[Rr]eturn a creature card at random from your graveyard to the battlefield\.",
        oracle_text,
    )
    assert match is not None, "Kheru Lich Lord's own printed text changed"
    fragment = match.group(0)

    effect = _parse_return_a_card_at_random_from_graveyard_clause(fragment, for_spell=False)
    assert effect is not None

    scenario = (
        Scenario()
        .player("alice", battlefield=["Kheru Lich Lord"], graveyard=["Runeclaw Bear"])
        .player("bob")
        .build()
    )
    lich_lord = scenario.creature("Kheru Lich Lord")

    effect(scenario.game, lich_lord)

    bears = scenario.find("Runeclaw Bear", Zone.BATTLEFIELD, "alice")
    assert bears.zone is Zone.BATTLEFIELD

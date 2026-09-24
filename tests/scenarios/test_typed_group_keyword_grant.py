"""Scenario: "`<cost>`: `<types>` you control gain `<keyword>` until end of
turn." - Along the Crooked Way's own "{1}{B}: Goblins and Orcs you control
gain menace until end of turn."

`machines/effects._MASS_SUBTYPE_SUBJECT_RE` used to read only a single bare
CR 205.3m subtype ("Knights you control") - this session widens it to a
joined list of subtypes, membership in any one of them enough, the same
plural-subject reading `machines/layers.py`'s own static anthem subject
(`_SUBTYPE_LIST`) already gives a comma/"and"-joined list of creature types.
`_mass_creature_group_targets`'s own reader for the shape is what
`activated_effect_for`'s text fallback reaches through `parse_mixed_effect`
- no new dispatch path, only a wider subject grammar on the existing one.

CR 611.2c ("the set of objects it affects is determined when that continuous
effect begins") was verified with `mise run rules:find` in the session that
wrote this file - see `machines/effects.py`'s own docstring for the exact
wording it already cites for `_mass_creature_group_targets`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(*extra: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Along the Crooked Way"],
            battlefield=[
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Raging Goblin",
                "Orcish Spy",
                "Grizzly Bears",
                *extra,
            ],
        )
        .player("bob")
    )


def test_goblins_and_orcs_you_control_gain_menace_but_a_plain_bear_does_not():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.cast_and_resolve("Along the Crooked Way", *cast_sources, username="alice")

    crooked_way = scenario.find("Along the Crooked Way", Zone.BATTLEFIELD, "alice")
    goblin = scenario.creature("Raging Goblin")
    orc = scenario.creature("Orcish Spy")
    bears = scenario.creature("Grizzly Bears")

    assert not has_keyword(goblin, Keyword.MENACE, scenario.game)
    assert not has_keyword(orc, Keyword.MENACE, scenario.game)
    assert not has_keyword(bears, Keyword.MENACE, scenario.game)

    activation_sources = scenario.untapped_sources("Swamp", "Swamp")
    scenario.activate(crooked_way, *activation_sources)
    scenario.resolve_top()

    assert has_keyword(goblin, Keyword.MENACE, scenario.game), "a Goblin you control"
    assert has_keyword(orc, Keyword.MENACE, scenario.game), "an Orc you control"
    assert not has_keyword(bears, Keyword.MENACE, scenario.game), "neither a Goblin nor an Orc"


def test_gollum_the_abandoned_shares_the_gate_neither_type():
    """A second creature the grant deliberately does not reach - Gollum the
    Abandoned (Halfling Horror) is neither a Goblin nor an Orc."""
    scenario = board("Gollum the Abandoned").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.cast_and_resolve("Along the Crooked Way", *cast_sources, username="alice")
    crooked_way = scenario.find("Along the Crooked Way", Zone.BATTLEFIELD, "alice")
    gollum = scenario.creature("Gollum the Abandoned")

    activation_sources = scenario.untapped_sources("Swamp", "Swamp")
    scenario.activate(crooked_way, *activation_sources)
    scenario.resolve_top()

    assert not has_keyword(gollum, Keyword.MENACE, scenario.game)

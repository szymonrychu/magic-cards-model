"""Scenario: a second ENTERS_THE_BATTLEFIELD trigger on one source, gated on
a land subtype (CR 205.3i, CR 603.6a).

Koth of the Homestead prints two separate triggered abilities off two
separate lines: "Landfall — Whenever a land you control enters, you gain 1
life." and "Whenever a Plains you control enters, put a +1/+1 counter on
target creature." Both are parsed and both are offered to `condition_matches`
(`machines/triggers.triggered_abilities_of`/`triggered_abilities_on` keep
every printed triggered ability, not just one per event), so the Plains
trigger was never *lost* - it silently never *matched* any real Plains
entering.

The cause is in `machines/triggers._ENTERING_SUBTYPE`: its own optional
trailing `s?` turns a plural subject ("one or more Cats you control enter")
back into the singular subtype name `_subtype_matches` compares against, but
CR 305.5's "Plains" is spelled with a trailing s in *both* its singular and
plural form. Stripping it off a singular "a Plains you control enters" left
the captured subtype "Plain" - a name the game has never printed - so
`_subtype_matches` compared a real Plains's own subtypes against a name it
could never contain, and Koth's second trigger never fired for one.

The fix, `machines/triggers._required_entering_subtype`: only strips the
trailing s when the *whole* captured word (with it) is not itself one of CR
305.6's `BASIC_LAND_TYPES` - "Plains" survives whole; an ordinary pluralized
subtype like "Cats" still gets trimmed to "Cat".

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 305.5** - "The basic land types are Plains, Island, Swamp, Mountain,
  and Forest."
- **CR 603.6a** - enters-the-battlefield abilities trigger when a permanent
  enters the battlefield.
"""

from tests.scenarios.harness import Scenario


def test_a_plains_entering_fires_both_of_koths_triggers():
    """CR 205.3i: a Plains is a land, so it satisfies both the landfall
    condition and the Plains-specific one at once (CR 603.2c: one event, and
    every matching ability of the source's own triggers on it)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Plains"], battlefield=["Koth of the Homestead", "Grizzly Bears"])
        .player("bob")
        .build()
    )

    scenario.put_onto_battlefield("Plains")
    scenario.game.put_triggers_on_stack()

    assert sorted(scenario.stack_names()) == sorted(
        [
            "Koth of the Homestead's triggered ability",
            "Koth of the Homestead's triggered ability",
        ]
    )


def test_a_forest_entering_fires_only_the_landfall_trigger():
    """A Forest is a land but not a Plains - only the generic landfall half
    should match, proving the Plains-specific trigger is genuinely gated on
    the subtype and not merely always firing alongside it."""
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Koth of the Homestead", "Grizzly Bears"])
        .player("bob")
        .build()
    )

    scenario.put_onto_battlefield("Forest")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Koth of the Homestead's triggered ability"]

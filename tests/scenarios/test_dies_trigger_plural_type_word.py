"""A DIES condition naming its type word in the *plural* - "one or more
creatures you control die" - on a noncreature source (CR 700.4, 603.10a).

`_required_types`'s own `\\b{word}\\b` regex refuses to match inside a
plural: "creatures" has no word boundary after "creature" (the 's' is a
word character, not a boundary), so a condition naming a type only in its
plural form read as naming *no* type at all. `_types_match` then answers
"no restriction" for that emptiness, which `condition_matches`'s DIES
branch (this stream's own earlier fix for Gardenize's singular "a creature
you control dies") reads as "the source could have been the subject" -
exactly backwards for Scavenger's Talent, an Enchantment that can never be
the creature its own plural condition asks about.

Found via `scripts/sweep_pool.py`'s full-pool sweep after that earlier fix
landed: Scavenger's Talent kept reporting `unmatchable_condition` for a
different reason than Gardenize's, once Gardenize's own singular form was
already fixed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import _required_types
from tests.scenarios.harness import Scenario


def test_scavengers_talent_charges_a_food_when_a_controlled_creature_dies():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Scavenger's Talent", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Scavenger's Talent's triggered ability"]


def test_scavengers_talent_does_not_fire_for_an_opponents_creature_dying():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Scavenger's Talent"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_required_types_reads_plural_forms_of_more_than_one_type_word():
    """Not hardcoded to "creature[s]" - `sorcery`/`sorceries` exercises the
    irregular `-y` -> `-ies` pluralization the same fix has to get right,
    and `artifact`/`artifacts` the ordinary `+s` case."""
    from magic_cards_model.models.card import Type

    assert _required_types("a creature dies") == ({Type.CREATURE}, set())
    assert _required_types("one or more creatures you control die") == ({Type.CREATURE}, set())
    assert _required_types("an instant or sorcery spell")[0] == {Type.INSTANT, Type.SORCERY}
    assert _required_types("one or more instant or sorcery cards")[0] == {
        Type.INSTANT,
        Type.SORCERY,
    }
    assert _required_types("one or more artifacts you control enter")[0] == {Type.ARTIFACT}
    assert _required_types("a noncreature spell") == (set(), {Type.CREATURE})
    assert _required_types("one or more nonland permanents") == (set(), {Type.LAND})

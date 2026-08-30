"""Scenario: Brotherhood's End - a modal sorcery (CR 700.2).

    Choose one -
    • Brotherhood's End deals 3 damage to each creature and each planeswalker.
    • Destroy all artifacts with mana value 3 or less.

Neither mode is targeted at all, so both are read by `parse_mode_effect`'s
fallback to `parse_mixed_effect_for_spell`'s per-clause dispatcher, with no
`EFFECTS` registry row. The first mode is `_parse_damage_each_group_clause`
(a new mass, non-targeted damage shape this wave added); the second reuses
`_parse_destroy_each_clause` once `_DESTROY_EACH_RE` also reads "destroy
all", not only "destroy each" (Culling Ritual's own wording).

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 700.2** - "A spell or ability is modal if it has two or more options in
  a bulleted list preceded by instructions for a player to choose a number of
  those options."
- **CR 700.2a** - modes are chosen as the spell is put on the stack (CR 601.2b).
- **CR 119.1** - damage dealt to a permanent or player.
- **CR 701.8a** - destroying a permanent.
- **CR 704.5g** - lethal damage is a state-based action.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def test_mode_one_deals_damage_to_every_creature_and_planeswalker():
    """3 damage kills a 2-toughness creature and any planeswalker with 3 or
    fewer loyalty, but does not touch a noncreature, non-planeswalker
    permanent (a land, an artifact).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Brotherhood's End"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Elvish Mystic", "Sol Ring"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "bob")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Brotherhood's End")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert mystic.zone is Zone.GRAVEYARD, "3 damage is lethal to a 1/1"
    assert ring.zone is Zone.BATTLEFIELD, "Sol Ring is neither a creature nor a planeswalker"


def test_mode_one_hits_the_casters_own_creatures_too():
    """A symmetrical sweep - "each creature", not "each creature an opponent
    controls" - alice's own board is not spared.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Brotherhood's End"], battlefield=["Mountain"] * 3 + ["Elvish Mystic"]
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    _to_main(scenario)
    alices_mystic = scenario.creature("Elvish Mystic", "alice")
    bobs_mystic = scenario.creature("Elvish Mystic", "bob")

    casting = scenario.cast("Brotherhood's End")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert alices_mystic.zone is Zone.GRAVEYARD
    assert bobs_mystic.zone is Zone.GRAVEYARD


def test_mode_two_destroys_cheap_artifacts_but_not_expensive_ones():
    """Mode 2's own mana-value ceiling: Sol Ring (mana value 1) dies, a
    higher mana-value artifact does not.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Brotherhood's End"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Sol Ring", "Wurmcoil Engine"])
        .build()
    )
    _to_main(scenario)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    engine = scenario.creature("Wurmcoil Engine", "bob")
    assert engine.card.cmc > 3

    casting = scenario.cast("Brotherhood's End")
    casting.choose_modes([2])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert ring.zone is Zone.GRAVEYARD
    assert engine.zone is Zone.BATTLEFIELD


def test_mode_two_does_not_touch_creatures():
    """Mode 2 is "destroy all artifacts", not creatures - an artifact
    creature would be caught (it is still an artifact), but a plain creature
    is untouched.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Brotherhood's End"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "bob")

    casting = scenario.cast("Brotherhood's End")
    casting.choose_modes([2])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert mystic.zone is Zone.BATTLEFIELD


def test_only_one_mode_may_be_chosen():
    """ "Choose one" (CR 700.2a): exactly one of the two bullets, not both and
    not zero.
    """
    scenario = (
        Scenario().player("alice", hand=["Brotherhood's End"], battlefield=["Mountain"] * 3).build()
    )
    _to_main(scenario)

    casting = scenario.cast("Brotherhood's End")
    with pytest.raises(ValueError):
        casting.choose_modes([1, 2])

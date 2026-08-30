"""Scenario: the four generalised shapes `machines/layers.py`'s
`parsed_layer_effects` reads straight off oracle text (W5).

`test_layer_effects_registry_is_minimal.py` proves the registry does not carry
a hand-written row for any of these any more; `test_static_abilities.py` and
`test_continuous_effects_with_a_duration.py` already exercise most of the
individual cards end to end (Glorious Anthem, Elesh Norn, Giant Growth,
Basking Rootwalla, ...) because those scenarios were written against the cards
by name, not the old per-card functions, and kept passing unchanged once the
rows were deleted. This file covers what is not already proven elsewhere:

- a granted keyword actually changing what combat does, not just what the
  computed board says (CR 510.4's extra combat damage step for double strike);
- the fail-closed notice a card this wave's regex cannot read produces,
  instead of silently doing nothing.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import LayerNotice
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_assault_strobes_granted_double_strike_deals_damage_twice():
    """CR 510.4: "if any attacking or blocking creature has first strike or
    double strike as the combat damage step begins... there are two combat
    damage steps instead of one."

    The double strike is granted in layer 6 by `parsed_layer_effects`'s
    keyword-grant shape, not printed on Grizzly Bears - so an unblocked 2/2
    hitting for 4 rather than 2 is proof the grant reaches combat, not just
    the computed board `test_static_abilities.py` already checks.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Assault Strobe"], battlefield=["Mountain", "Grizzly Bears"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Assault Strobe", mountain, targets=[bears])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    bob = scenario.player("bob")
    life_before = bob.life
    dealt = scenario.combat_damage()

    assert len(dealt) == 2, "one damage event per combat damage step (CR 510.4)"
    assert life_before - bob.life == 4, "a 2-power double striker deals 2 damage twice"


def test_a_ground_creature_with_granted_double_strike_still_gets_blocked():
    """The grant does not make the creature evasive - it is not flying or
    menace (CR 509.1a) - so a single blocker still stops it from reaching the
    player. But the double strike still matters here: the blocker dies to the
    first-strike step alone (CR 510.4) and so never gets to deal its own
    damage back in the regular step, which a plain (non-double-striking)
    Grizzly Bears could not have arranged.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Assault Strobe"], battlefield=["Mountain", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    attacker = scenario.creature("Grizzly Bears", "alice")
    blocker = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Assault Strobe", mountain, targets=[attacker])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.block(attacker, blocker)
    scenario.combat_damage()

    assert blocker.zone.value == "graveyard", "2 damage in the first-strike step is lethal"
    assert attacker.zone.value == "battlefield", (
        "the dead blocker never reaches the regular damage step to hit back"
    )


def test_fiend_artisans_variable_pump_is_not_one_of_the_generalised_shapes():
    """ "This creature gets +1/+1 for each creature card in your graveyard."

    Starts exactly like the pump shape `parsed_layer_effects` reads
    ("this creature gets"), but the amount is not a fixed +N/+N - it counts the
    controller's graveyard, which no shape this wave generalises accounts for.
    Fail-closed: the printed 1/1 is untouched and a `LayerNotice` records that
    the text looked like this wave's territory but could not be read, rather
    than the card silently doing nothing indistinguishable from having no text
    at all.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Forest", "Fiend Artisan"], graveyard=["Grizzly Bears"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    artisan = scenario.creature("Fiend Artisan", "alice")

    board = scenario.game.continuous_effects.board(scenario.game.battlefield)

    assert board.of(artisan).power_toughness == (1, 1), "the count is not read; nothing applied"
    notices = scenario.game.continuous_effects.layer_notices
    assert notices == [
        LayerNotice(
            source_id=artisan.id,
            source_name="Fiend Artisan",
            text=card("Fiend Artisan").oracle_text,
        )
    ]

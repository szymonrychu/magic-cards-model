"""Scenario: "Sacrifice all `<qualifier>` you control." - Emrakul, the World
Anew's own leaves-the-battlefield trigger ("sacrifice all creatures you
control"), and Death Pit Offering's own enters-the-battlefield trigger, the
identical sentence.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 701.21a** - to sacrifice a permanent is to move it, as its controller,
  from the battlefield directly to its owner's graveyard; it isn't targeted,
  and regeneration/other destruction-replacements never touch it.
- **CR 608.2f** - an action on multiple objects is processed simultaneously
  when it can be, which a mass sacrifice with no ordering choice printed
  always can.
- **CR 603.6c / 603.10a** - Emrakul's own trigger is a leaves-the-battlefield
  ability, which looks back at the board as it stood immediately before the
  event for whether it triggers; its *effect* ("sacrifice all creatures you
  control") is read the same way regardless of which trigger condition put it
  on the stack, which is what Death Pit Offering's enters-the-battlefield
  sibling proves.

The effect is `_parse_sacrifice_all_you_control_clause` in `machines/effects.py`,
the same "all `<type qualifier>` you control" grammar `_parse_untap_all_you_
control_clause` already reads for a mass untap.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_death_pit_offering_sacrifices_every_creature_its_controller_controls():
    """The enters-the-battlefield trigger sacrifices alice's own creatures
    only - bob's creature and alice's own land are both untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Death Pit Offering"],
            battlefield=[
                "Grizzly Bears",
                "Watchwolf",
                "Forest",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
        )
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Death Pit Offering", *sources)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Death Pit Offering's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Watchwolf", Zone.GRAVEYARD, "alice") is not None
    bob_bear = scenario.creature("Runeclaw Bear", "bob")
    assert bob_bear.zone is Zone.BATTLEFIELD, "sacrifice all creatures YOU control, not bob's"
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert forest is not None, "a land is not a creature"
    assert "Death Pit Offering" in scenario.battlefield_names()


def test_no_creatures_controlled_does_nothing_and_the_permanent_still_resolves():
    """An empty group is not a fizzle - there was never a target to begin
    with (CR 701.21a's action is unconditional over whatever qualifies)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Death Pit Offering"], battlefield=["Swamp"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Death Pit Offering", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert "Death Pit Offering" in scenario.battlefield_names()


def test_emrakul_leaving_the_battlefield_sacrifices_every_creature_alice_controls():
    """Emrakul, the World Anew's own leaves-the-battlefield trigger (CR
    603.6c/603.10a's look-back): destroying Emrakul itself still fires it -
    Emrakul is already gone from the battlefield by the time the ability
    resolves, so it is never among the candidates itself."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Emrakul, the World Anew", "Grizzly Bears", "Forest"],
        )
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the World Anew", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(emrakul)
    scenario.game.put_triggers_on_stack()
    assert "Emrakul, the World Anew's triggered ability" in scenario.stack_names()
    scenario.pass_until_resolved()

    assert emrakul.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    bob_bear = scenario.creature("Runeclaw Bear", "bob")
    assert bob_bear.zone is Zone.BATTLEFIELD
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert forest is not None


def test_generalises_off_death_pit_offerings_own_shape():
    """A direct-parse proof, the same one `test_cast_trigger_mass_gain_
    control_of_target_player.py`'s Ashiok check makes: the reader is not
    fitted to Emrakul's exact sentence. Death Pit Offering itself already
    exercises this in a full scenario above; this also proves a qualifier
    variant Emrakul's own text does not print."""
    from magic_cards_model.machines.effects import _parse_sacrifice_all_you_control_clause

    assert (
        _parse_sacrifice_all_you_control_clause("Sacrifice all creatures you control.") is not None
    )
    assert (
        _parse_sacrifice_all_you_control_clause("Sacrifice all artifacts you control.") is not None
    )
    assert _parse_sacrifice_all_you_control_clause("Sacrifice a creature you control.") is None

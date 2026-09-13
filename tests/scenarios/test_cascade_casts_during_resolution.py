"""Cascade's hit is cast while the cascade trigger resolves (CR 702.85a, 608.2g).

CR 702.85a: "exile cards from the top of your library until you exile a
nonland card whose mana value is less than this spell's mana value. You may
cast that card without paying its mana cost if the resulting spell's mana
value is less than this spell's mana value. Then put all cards exiled this way
that weren't cast on the bottom of your library in a random order."

CR 608.2g: "If an effect specifically instructs or allows a player to cast a
spell during resolution, they do so by following the steps in rules 601.2a-i,
except no player receives priority after it's cast. That spell becomes the
topmost object on the stack, and the currently resolving spell or ability
continues to resolve".

Battle 8 (B8-01): "yes" granted a permission instead, the opponent got
priority, and Living End - a sorcery - could only be cast after Violent
Outburst had resolved, so the pump applied before the creatures came back.

The corner cases: timing (a sorcery hit with the cascading spell still on the
stack), announcements made mid-resolution (targets, modes, which face of an
adventurer), an illegal cast (no legal target) falling back to the bottom,
declining, and the resulting spell's mana value (an Adventure half costing as
much as the cascading spell is not offered). Bloodbraid Elf, Kolaghan's
Command, Fatal Push and Foulmire Knight are off the deck pool.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

KNIGHT = "Foulmire Knight // Profane Insight"


def spell_on_the_stack(scenario: Scenario, printing: str):
    return next(
        state
        for state in scenario.game.stack
        if getattr(state, "card", None) and state.card.name == printing
    )


def outburst_board(*library: str, graveyard: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Violent Outburst"],
            library=list(library),
            graveyard=list(graveyard),
            battlefield=["Forest", "Mountain", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def cast_outburst(scenario: Scenario):
    return scenario.cast_onto_stack(
        "Violent Outburst", *scenario.untapped_sources("Forest", "Mountain", "Forest")
    )


def elf_board(*library: str, bob_battlefield: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bloodbraid Elf"],
            library=list(library),
            battlefield=["Forest", "Mountain", "Forest", "Mountain"],
        )
        .player("bob", library=["Island"], hand=["Island"], battlefield=list(bob_battlefield))
    )


def cast_elf(scenario: Scenario):
    return scenario.cast_onto_stack(
        "Bloodbraid Elf", *scenario.untapped_sources("Forest", "Mountain", "Forest", "Mountain")
    )


def test_living_end_is_cast_above_violent_outburst_while_the_trigger_resolves():
    """The reported line. After the cascade trigger resolves, Living End is on
    the stack above Violent Outburst: nobody had priority in between, and
    CR 117.1a's sorcery timing did not apply to a cast the resolving ability
    allowed (CR 608.2g)."""
    scenario = outburst_board("Forest", "Living End", graveyard=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Violent Outburst")
    outburst = cast_outburst(scenario)

    scenario.resolve_top()  # the cascade trigger

    living_end = scenario.find("Living End", Zone.STACK)
    assert scenario.stack_names() == ["Violent Outburst", "Living End"]
    assert scenario.game.stack[-1] is living_end
    assert scenario.game.play_permissions == []
    assert scenario.game.exile == []
    assert scenario.player("alice").library[-1].name == "Forest"
    record = scenario.game.cast_record_of(living_end)
    assert record is not None and record.origin_zone is Zone.EXILE
    assert living_end in scenario.game.spells_cast_this_turn["alice"]

    scenario.resolve_top()  # Living End: alice's Bears return, bob's Bears die
    returned = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.resolve_top()  # Violent Outburst: the returned Bears get +1/+0

    assert outburst.zone is Zone.GRAVEYARD
    assert scenario.game.characteristics_of(returned).power == 3


def test_declining_puts_the_hit_and_every_miss_on_the_bottom():
    scenario = outburst_board("Forest", "Living End", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Violent Outburst")
    cast_outburst(scenario)

    scenario.resolve_top()

    library = scenario.player("alice").library
    assert scenario.stack_names() == ["Violent Outburst"]
    assert scenario.game.exile == []
    assert [state.name for state in library[0:1]] == ["Island"]
    assert sorted(state.name for state in library[1:]) == ["Forest", "Living End"]
    assert scenario.game.play_permissions == []


def test_the_hits_targets_are_announced_during_resolution():
    """CR 601.2c inside CR 608.2g: Lightning Bolt's target is chosen while the
    cascade trigger resolves, and the Bolt is cast above Bloodbraid Elf."""
    scenario = elf_board("Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Bloodbraid Elf")
    scenario.will_choose_targets("bob", source="Lightning Bolt")
    cast_elf(scenario)

    scenario.resolve_top()

    assert scenario.stack_names() == ["Bloodbraid Elf", "Lightning Bolt"]
    scenario.resolve_top()
    assert scenario.player("bob").life == 17


def test_a_modal_hits_modes_are_announced_during_resolution():
    """CR 601.2b inside CR 608.2g: Kolaghan's Command's two modes, then each
    mode's target."""
    modes = [mode.text for mode in modal_profile(card("Kolaghan's Command")).modes]
    scenario = elf_board("Kolaghan's Command", bob_battlefield=("Aether Spellbomb",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spellbomb = scenario.find("Aether Spellbomb", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, source="Bloodbraid Elf")
    scenario.will_choose_mode(modes[1], source="Kolaghan's Command")
    scenario.will_choose_mode(modes[2], source="Kolaghan's Command")
    scenario.will_choose_targets("bob", source="Kolaghan's Command")
    scenario.will_choose_targets(spellbomb, source="Kolaghan's Command")
    cast_elf(scenario)

    scenario.resolve_top()

    assert scenario.stack_names() == ["Bloodbraid Elf", "Kolaghan's Command"]
    command = scenario.find("Kolaghan's Command", Zone.STACK)
    assert scenario.game.cast_record_of(command).modes == [2, 3]
    scenario.resolve_top()
    assert scenario.player("bob").hand == []
    assert spellbomb.zone is Zone.GRAVEYARD


def test_a_hit_with_no_legal_target_is_not_cast_and_goes_to_the_bottom():
    """CR 601.2c makes casting Fatal Push with no creature to target illegal,
    so it "weren't cast" and joins the bottom (CR 702.85a)."""
    scenario = elf_board("Fatal Push").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Bloodbraid Elf")
    cast_elf(scenario)

    scenario.resolve_top()

    push = scenario.find("Fatal Push", Zone.LIBRARY, "alice")
    assert scenario.stack_names() == ["Bloodbraid Elf"]
    assert scenario.player("alice").library[-1] is push
    assert scenario.game.exile == []


def test_an_adventure_costing_as_much_as_the_cascading_spell_is_not_offered():
    """CR 702.85a's "if the resulting spell's mana value is less than this
    spell's mana value": Foulmire Knight has mana value 1 in the library, but
    Profane Insight, its Adventure (CR 715.3), has mana value 3 - not less
    than Violent Outburst's 3 - so only the Knight may be cast, and nobody is
    asked which face."""
    scenario = outburst_board("Foulmire Knight").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Violent Outburst")
    cast_outburst(scenario)

    scenario.resolve_top()

    knight = spell_on_the_stack(scenario, KNIGHT)
    assert knight.face_played is None
    assert not any(
        question.kind is DecisionKind.CHOOSE_A_QUALITY for question in scenario.questions_asked()
    )


def test_an_adventure_cheaper_than_the_cascading_spell_may_be_chosen():
    """Under Bloodbraid Elf's mana value 4 both faces qualify, so the caster
    chooses (CR 715.3) and Profane Insight is cast as an Adventure."""
    scenario = elf_board("Foulmire Knight").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Bloodbraid Elf")
    scenario.will_choose("Profane Insight", source="Foulmire Knight")
    cast_elf(scenario)

    scenario.resolve_top()

    knight = spell_on_the_stack(scenario, KNIGHT)
    assert knight.face_played == "Profane Insight"
    asked = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_A_QUALITY]
    assert len(asked) == 1 and set(asked[0].options) == {"Foulmire Knight", "Profane Insight"}
    scenario.resolve_top()
    assert knight.zone is Zone.EXILE
    assert scenario.player("alice").life == 19

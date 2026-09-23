"""CR 716.2a: "When this Class becomes level N" - the trigger on a level bar.

"[Cost]: Level N - [Abilities]" means "[Cost]: This Class's level becomes N.
Activate only if this Class is level N-1 and only as a sorcery" and "As long
as this Class is level N or greater, it has [abilities]." The level becomes N
as the level bar's ability resolves; a triggered ability printed under that
bar is had from then on, and its "becomes level N" event is that change.

Cards:

- **Caretaker's Talent** - "When this Class becomes level 2, create a token
  that's a copy of target token you control."
- **Stormchaser's Talent** - "When this Class becomes level 2, return target
  instant or sorcery card from your graveyard to your hand."
- **Wizard Class** (proof printing, not a listed card, not in any api deck) -
  "When this Class becomes level 2, draw two cards."

Every one fires only on reaching that level: never on entering, never again
on the way to level 3, never for a different Class's level.

CR numbers used, read with `mise run rules:find` in this session: CR 716.2a
(quoted above), CR 603.2c (one event, one trigger).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def level_up(scenario, name: str, *, index: int, lands: int, land: str) -> None:
    """Activate the level bar at `index`, paying with `lands` untapped
    `land`s, and resolve it and everything it triggers."""
    talent = scenario.find(name, Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources(*[land] * lands)
    scenario.activate(talent, *sources, index=index)
    settle(scenario)


# -- Caretaker's Talent: copy target token you control ----------------------


def caretaker_board(*, hand: list[str], battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Caretaker's Talent", *(battlefield or []), *["Plains"] * 12],
            library=["Forest"] * 6,
        )
        .player("bob")
    )


def tokens(scenario) -> list:
    return [state for state in scenario.game.battlefield if state.token]


def test_reaching_level_2_copies_a_token_you_control():
    scenario = caretaker_board(hand=["Spectral Procession"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 6)
    scenario.cast_and_resolve("Spectral Procession", *sources)
    settle(scenario)
    spirit = tokens(scenario)[0]

    talent = scenario.find("Caretaker's Talent", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Caretaker's Talent", [spirit])
    level_up(scenario, "Caretaker's Talent", index=0, lands=1, land="Plains")

    assert talent.class_level == 2
    assert len(tokens(scenario)) == 4
    copy = tokens(scenario)[-1]
    assert copy.name == spirit.name
    assert copy.controller == "alice"


def test_level_2_with_no_token_to_target_does_nothing():
    """A creature that is not a token is not a legal target, so the trigger
    has none and is removed from the stack (CR 603.3d)."""
    scenario = caretaker_board(hand=[], battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = scenario.find("Caretaker's Talent", Zone.BATTLEFIELD, "alice")

    level_up(scenario, "Caretaker's Talent", index=0, lands=1, land="Plains")

    assert talent.class_level == 2
    assert tokens(scenario) == []
    assert [s.name for s in scenario.game.battlefield].count("Grizzly Bears") == 1


def test_reaching_level_3_does_not_copy_a_token_again():
    scenario = caretaker_board(hand=["Spectral Procession"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 6)
    scenario.cast_and_resolve("Spectral Procession", *sources)
    settle(scenario)
    spirit = tokens(scenario)[0]
    scenario.choose_trigger_targets("Caretaker's Talent", [spirit])
    level_up(scenario, "Caretaker's Talent", index=0, lands=1, land="Plains")
    assert len(tokens(scenario)) == 4

    level_up(scenario, "Caretaker's Talent", index=1, lands=4, land="Plains")

    talent = scenario.find("Caretaker's Talent", Zone.BATTLEFIELD, "alice")
    assert talent.class_level == 3
    assert len(tokens(scenario)) == 4


def test_the_trigger_waits_for_the_level_bar_to_resolve():
    """The level becomes 2 as the level ability *resolves* (CR 716.2a), so
    with it still on the stack nothing has triggered."""
    scenario = caretaker_board(hand=["Spectral Procession"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 6)
    scenario.cast_and_resolve("Spectral Procession", *sources)
    settle(scenario)
    talent = scenario.find("Caretaker's Talent", Zone.BATTLEFIELD, "alice")

    (plains,) = scenario.untapped_sources("Plains")
    scenario.activate(talent, plains, index=0)

    assert talent.class_level == 1
    assert scenario.game.pending_triggers == []
    assert len(scenario.game.stack) == 1


# -- Stormchaser's Talent: return target instant or sorcery card -------------


def stormchaser_board(*, graveyard: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Stormchaser's Talent"],
            battlefield=["Island"] * 10,
            graveyard=graveyard,
            library=["Forest"] * 6,
        )
        .player("bob")
    )


def enter_stormchaser(scenario):
    talent = scenario.put_onto_battlefield("Stormchaser's Talent", "alice")
    settle(scenario)  # the level 1 Otter
    return talent


def test_reaching_level_2_returns_an_instant_from_your_graveyard():
    scenario = stormchaser_board(graveyard=["Unsummon", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = enter_stormchaser(scenario)
    unsummon = scenario.find("Unsummon", Zone.GRAVEYARD, "alice")

    scenario.choose_trigger_targets("Stormchaser's Talent", [unsummon])
    level_up(scenario, "Stormchaser's Talent", index=0, lands=4, land="Island")

    assert talent.class_level == 2
    assert unsummon.zone is Zone.HAND


def test_a_creature_card_is_not_an_instant_or_sorcery_card():
    scenario = stormchaser_board(graveyard=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = enter_stormchaser(scenario)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    level_up(scenario, "Stormchaser's Talent", index=0, lands=4, land="Island")

    assert talent.class_level == 2
    assert bears.zone is Zone.GRAVEYARD


def test_entering_the_battlefield_is_not_becoming_level_2():
    scenario = stormchaser_board(graveyard=["Unsummon"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = enter_stormchaser(scenario)
    unsummon = scenario.find("Unsummon", Zone.GRAVEYARD, "alice")

    assert talent.class_level == 1
    assert unsummon.zone is Zone.GRAVEYARD
    assert len(tokens(scenario)) == 1  # only the level 1 Otter


def test_reaching_level_3_does_not_return_a_second_card():
    scenario = stormchaser_board(graveyard=["Unsummon", "Boomerang Basics"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = enter_stormchaser(scenario)
    unsummon = scenario.find("Unsummon", Zone.GRAVEYARD, "alice")
    basics = scenario.find("Boomerang Basics", Zone.GRAVEYARD, "alice")

    scenario.choose_trigger_targets("Stormchaser's Talent", [unsummon])
    level_up(scenario, "Stormchaser's Talent", index=0, lands=4, land="Island")
    assert unsummon.zone is Zone.HAND

    level_up(scenario, "Stormchaser's Talent", index=1, lands=6, land="Island")

    assert talent.class_level == 3
    assert basics.zone is Zone.GRAVEYARD


# -- Wizard Class (proof printing): draw two cards ---------------------------


def wizard_board(*, battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[*(battlefield or ["Wizard Class"]), *["Island"] * 10],
            library=["Forest"] * 8,
        )
        .player("bob")
    )


def test_wizard_class_draws_two_on_reaching_level_2():
    scenario = wizard_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = len(scenario.player("alice").hand)

    level_up(scenario, "Wizard Class", index=0, lands=3, land="Island")

    assert scenario.find("Wizard Class", Zone.BATTLEFIELD, "alice").class_level == 2
    assert len(scenario.player("alice").hand) == before + 2


def test_wizard_class_does_not_draw_again_on_reaching_level_3():
    scenario = wizard_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    level_up(scenario, "Wizard Class", index=0, lands=3, land="Island")
    after_two = len(scenario.player("alice").hand)

    level_up(scenario, "Wizard Class", index=1, lands=5, land="Island")

    assert scenario.find("Wizard Class", Zone.BATTLEFIELD, "alice").class_level == 3
    assert len(scenario.player("alice").hand) == after_two


def test_each_class_tracks_its_own_level():
    """Two Wizard Classes: levelling one does not make the other "become
    level 2" - the event is about the Class whose level changed."""
    scenario = wizard_board(battlefield=["Wizard Class", "Wizard Class"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = [s for s in scenario.game.battlefield if s.name == "Wizard Class"]
    before = len(scenario.player("alice").hand)

    sources = scenario.untapped_sources(*["Island"] * 3)
    scenario.activate(first, *sources, index=0)
    settle(scenario)

    assert first.class_level == 2
    assert second.class_level == 1
    assert len(scenario.player("alice").hand) == before + 2


def test_the_level_2_trigger_is_not_had_below_level_2():
    """Leveling a Class to level 2 is the only way in: the level bar that
    skips straight to 3 is refused (CR 716.2a's "only if this Class is level
    N-1"), and nothing is drawn."""
    scenario = wizard_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wizard = scenario.find("Wizard Class", Zone.BATTLEFIELD, "alice")
    before = len(scenario.player("alice").hand)

    with pytest.raises(ValueError, match="is level 1, not level 2"):
        scenario.activate(wizard, index=1)

    assert wizard.class_level == 1
    assert len(scenario.player("alice").hand) == before

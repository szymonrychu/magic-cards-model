"""A count of the card types among the spells a player has cast this turn.

- **April O'Neil, Hacktivist** - "At the beginning of your end step, draw a
  card for each card type among spells you've cast this turn."
- **Hurkyl, Master Wizard** (second printing - Modern and Pioneer legal, in
  no deck list) - "At the beginning of your end step, if you've cast a
  noncreature spell this turn, reveal the top five cards of your library. For
  each card type among noncreature spells you've cast this turn, you may put
  a card of that type from among the revealed cards into your hand. Put the
  rest on the bottom of your library in a random order." The same count,
  narrowed to noncreature spells, driving a per-type pick instead of a draw.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 205.2a** - the card types: artifact, battle, creature, enchantment,
  instant, kindred, land, planeswalker, sorcery (and the non-traditional
  ones). April's own ruling: supertypes and subtypes are not card types.
- **CR 205.2b** - an artifact creature has both card types, and counts both.
- **CR 601.2i** - a spell is cast once it becomes cast; a land is played,
  never cast (CR 305.9), so it adds nothing.
- **CR 603.4** - Hurkyl's intervening "if" is checked as the ability would
  trigger and again as it resolves.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

LIBRARY = ["Island"] * 12


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _april(hand, *, lands=("Mountain", "Mountain", "Forest", "Island", "Island")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["April O'Neil, Hacktivist", *lands],
            hand=list(hand),
            library=list(LIBRARY),
        )
        .player("bob", battlefield=["Mountain"], hand=["Shock"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _to_end_step(scenario: Scenario) -> None:
    """Advance through the game itself, so "at the beginning of your end
    step" triggers as the step begins (CR 513.1, CR 603.2)."""
    while scenario.step is not Step.END_STEP:
        _resolve_everything(scenario)
        scenario.advance()
    _resolve_everything(scenario)


def _cast(scenario, name, caster="alice", targets=None):
    card = scenario.find(name, Zone.HAND, caster)
    scenario.game.cast(
        card,
        caster,
        targets=targets,
        mana_sources=[
            permanent
            for permanent in scenario.game.permanents_controlled_by(caster)
            if permanent.card.is_land
        ],
    )
    _resolve_everything(scenario)


def _end_step_draws(scenario) -> int:
    before = len(scenario.player("alice").hand)
    _to_end_step(scenario)
    return len(scenario.player("alice").hand) - before


# -- April O'Neil, Hacktivist ------------------------------------------------


def test_no_spells_cast_draws_nothing():
    scenario = _april([])
    assert _end_step_draws(scenario) == 0


def test_one_instant_draws_one():
    scenario = _april(["Shock"])
    _cast(scenario, "Shock", targets=["bob"])
    assert _end_step_draws(scenario) == 1


def test_it_counts_card_types_not_spells():
    """Two instants are one card type."""
    scenario = _april(["Shock", "Lightning Bolt"])
    _cast(scenario, "Shock", targets=["bob"])
    _cast(scenario, "Lightning Bolt", targets=["bob"])
    assert _end_step_draws(scenario) == 1


def test_instant_creature_and_artifact_draw_three():
    scenario = _april(["Shock", "Llanowar Elves", "Mind Stone"])
    _cast(scenario, "Shock", targets=["bob"])
    _cast(scenario, "Llanowar Elves")
    _cast(scenario, "Mind Stone")
    assert _end_step_draws(scenario) == 3


def test_an_artifact_creature_is_two_card_types():
    """CR 205.2b: Ornithopter is an artifact and a creature."""
    scenario = _april(["Ornithopter"])
    _cast(scenario, "Ornithopter")
    assert _end_step_draws(scenario) == 2


def test_a_land_played_is_not_a_spell_cast():
    scenario = _april(["Forest"])
    scenario.game.play_land(scenario.find("Forest", Zone.HAND, "alice"), "alice")
    assert _end_step_draws(scenario) == 0


def test_an_opponents_spell_does_not_count():
    """Bob's Shock, cast on alice's turn, is a spell *he* cast."""
    scenario = _april([])
    shock = scenario.find("Shock", Zone.HAND, "bob")
    scenario.pass_priority("alice")
    scenario.game.cast(
        shock,
        "bob",
        targets=["alice"],
        mana_sources=scenario.game.permanents_controlled_by("bob"),
    )
    _resolve_everything(scenario)
    assert _end_step_draws(scenario) == 0


def test_last_turns_spells_do_not_count():
    scenario = _april(["Shock"])
    _cast(scenario, "Shock", targets=["bob"])
    for player in ("alice", "bob"):
        while scenario.game.turn.active_player == player:
            _resolve_everything(scenario)
            scenario.advance()
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    assert _end_step_draws(scenario) == 0


# -- Hurkyl, Master Wizard: noncreature spells, one pick per type --------------


def _hurkyl(hand, library):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Hurkyl, Master Wizard", "Mountain", "Island", "Island", "Forest"],
            hand=list(hand),
            library=list(library),
        )
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


REVEALED = ["Opt", "Sol Ring", "Grizzly Bears", "Forest", "Giant Growth", "Island", "Island"]


def test_hurkyl_takes_one_card_per_noncreature_type_cast():
    """Shock (instant) and Mind Stone (artifact) cast: one instant and one
    artifact come to hand; the Bears (creature) and Forest (land) do not, and
    Giant Growth - a second instant - goes to the bottom."""
    scenario = _hurkyl(["Shock", "Mind Stone"], REVEALED)
    _cast(scenario, "Shock", targets=["bob"])
    _cast(scenario, "Mind Stone")
    _to_end_step(scenario)
    hand = sorted(state.name for state in scenario.player("alice").hand)
    assert hand in (["Opt", "Sol Ring"], ["Giant Growth", "Sol Ring"])
    library = [state.name for state in scenario.player("alice").library]
    assert library[:2] == ["Island", "Island"], "what was below the top five never moved"
    assert "Grizzly Bears" in library and "Forest" in library


def test_hurkyl_does_not_trigger_without_a_noncreature_spell():
    """CR 603.4: only creature spells cast, so the "if" is false and nothing
    is revealed or taken."""
    scenario = _hurkyl(["Llanowar Elves"], REVEALED)
    _cast(scenario, "Llanowar Elves")
    _to_end_step(scenario)
    assert [state.name for state in scenario.player("alice").hand] == []
    assert [state.name for state in scenario.player("alice").library] == REVEALED


def test_hurkyl_ignores_the_types_of_creature_spells():
    """An artifact creature is not a noncreature spell, so its artifact type
    opens no pick: only Shock's instant does."""
    scenario = _hurkyl(["Shock", "Ornithopter"], REVEALED)
    _cast(scenario, "Shock", targets=["bob"])
    _cast(scenario, "Ornithopter")
    _to_end_step(scenario)
    hand = [state.name for state in scenario.player("alice").hand]
    assert len(hand) == 1 and hand[0] in ("Opt", "Giant Growth")

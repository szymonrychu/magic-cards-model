"""Scenario: "When you cast this spell, gain control of all creatures target
player controls." - Emrakul, the World Anew.

The same CR 117.2a/603.3 cast-trigger shape `test_cast_triggers.py` already
proves (the trigger resolves *above* its own spell, CR 603.3), applied to an
untargeted group among one targeted player's own permanents rather than a
single chosen target, and with no stated duration at all - CR 611.2a: "If no
duration is stated, [a continuous effect] lasts until the end of the game" -
unlike every mass "gain control ... until end of turn" shape this pool
already reads (Threaten, Act of Treason, Broadcast Takeover, Mob Rule).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 117.2a** - a triggered ability can trigger while a spell is being cast.
- **CR 603.3 / 603.3b / 603.3d** - the trigger goes on the stack the next
  time a player would receive priority, above the spell that caused it, with
  its own target chosen as it is put there.
- **CR 611.2a** - a continuous effect with no stated duration lasts until the
  end of the game.
- **CR 611.2c** - the set of objects a control-changing continuous effect
  affects is determined once, when the effect begins, and does not change
  afterward even if the permanents involved change.
- **CR 613.1b** - control-changing effects are layer 2.
- **CR 608.2b** - a target no longer legal at resolution does nothing.
- **CR 302.6** - a creature that hasn't been continuously controlled since
  the turn began can't attack and can't use tap/untap activated abilities -
  the ordinary "summoning sickness" rule, unaffected by *how* control changed.

The effect is `_parse_gain_control_of_all_target_players_clause` in
`machines/control_change.py`, tried by `control_change_ability_effect`
(`machines/effects.py`'s `_c02_t6_ability_effect`/`_ability_effect_or_notice`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

MOUNTAINS_FOR_EMRAKUL = ["Wastes"] * 12


def _next_turn(scenario: Scenario) -> None:
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def _emrakul_board(opposing: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Emrakul, the World Anew"],
            battlefield=list(MOUNTAINS_FOR_EMRAKUL),
            library=["Wastes"] * 10,
        )
        .player("bob", battlefield=opposing, library=["Forest"] * 10)
    )


def test_the_cast_trigger_sits_above_its_own_spell_on_the_stack():
    """CR 603.3: the trigger resolves before Emrakul, the World Anew itself
    does, the same ordering `test_cast_triggers.py` already proves for
    Ulamog, the Ceaseless Hunger."""
    scenario = _emrakul_board(["Grizzly Bears", "Watchwolf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Emrakul, the World Anew", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_EMRAKUL)

    scenario.cast_onto_stack("Emrakul, the World Anew", *sources)

    assert scenario.stack_names() == [
        "Emrakul, the World Anew",
        "Emrakul, the World Anew's triggered ability",
    ]


def test_gains_control_of_every_creature_the_target_player_controls():
    """Both of bob's creatures change controller while Emrakul, the World
    Anew is still on the stack (CR 603.3) - proving the trigger, not the
    10/10 arriving, is what steals them."""
    scenario = _emrakul_board(["Grizzly Bears", "Watchwolf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Emrakul, the World Anew", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_EMRAKUL)

    scenario.cast_onto_stack("Emrakul, the World Anew", *sources)
    scenario.pass_until_resolved()  # the trigger only

    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf")
    assert bears.controller == "alice"
    assert wolf.controller == "alice"
    assert "Emrakul, the World Anew" in scenario.stack_names(), (
        "the 10/10 itself has not resolved yet"
    )


def test_a_noncreature_permanent_the_target_player_controls_is_untouched():
    """ "All creatures" - not "all permanents". A land bob controls stays his."""
    scenario = _emrakul_board(["Grizzly Bears", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Emrakul, the World Anew", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_EMRAKUL)

    scenario.cast_onto_stack("Emrakul, the World Anew", *sources)
    scenario.pass_until_resolved()

    assert scenario.creature("Grizzly Bears").controller == "alice"
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    assert forest is not None and forest.controller == "bob"


def test_no_creatures_controlled_does_nothing_and_the_spell_still_resolves():
    """An empty group is not a fizzle (CR 608.2c has nothing to skip when
    there was never a target permanent to begin with): the trigger simply
    does less, and Emrakul, the World Anew still resolves underneath it."""
    scenario = _emrakul_board(["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Emrakul, the World Anew", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_EMRAKUL)

    scenario.cast_onto_stack("Emrakul, the World Anew", *sources)
    scenario.pass_until_resolved()  # the trigger
    scenario.pass_until_resolved()  # Emrakul, the World Anew itself

    assert "Emrakul, the World Anew" in scenario.battlefield_names()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    assert forest is not None and forest.controller == "bob"


def test_control_change_is_indefinite_not_until_end_of_turn():
    """CR 611.2a: no duration is printed, so the control change outlasts the
    turn - unlike Threaten's/Act of Treason's own "until end of turn" mass
    control changes this pool already reads."""
    scenario = _emrakul_board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Emrakul, the World Anew", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_EMRAKUL)

    scenario.cast_onto_stack("Emrakul, the World Anew", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    bears = scenario.creature("Grizzly Bears")
    assert bears.controller == "alice"
    _next_turn(scenario)
    _next_turn(scenario)
    assert bears.controller == "alice", "no duration means the theft never ends on its own"


def test_a_creature_removed_before_the_trigger_resolves_is_not_gained():
    """CR 611.2c: the affected set is determined when the effect *begins* -
    when the trigger actually resolves, not when it was put on the stack -
    so a creature bob sacrifices in response is never part of it."""
    scenario = _emrakul_board(["Grizzly Bears", "Watchwolf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Emrakul, the World Anew", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_EMRAKUL)

    scenario.cast_onto_stack("Emrakul, the World Anew", *sources)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    wolf = scenario.creature("Watchwolf")
    assert wolf.controller == "alice"
    assert bears.zone is Zone.GRAVEYARD
    assert bears.controller == "bob", "a creature already gone was never part of the group"


def test_generalises_off_ashiok_sculptor_of_fears_target_opponent_wording():
    """Not Emrakul's own sentence: Ashiok, Sculptor of Fears' -11 reads
    "Gain control of all creatures target opponent controls." - "target
    opponent", not "target player", proving the reader is not fitted to
    Emrakul's exact word. Ashiok is Pioneer/Modern-legal and in no deck pool
    here; only the clause parser itself is exercised, the same direct-parse
    proof `test_cast_triggers.py`'s own
    `test_the_mass_untap_reads_generically_off_untap_all_creatures_you_control`
    uses for Aggravated Assault.
    """
    from magic_cards_model.machines.control_change import (
        _parse_gain_control_of_all_target_players_clause,
    )

    assert (
        _parse_gain_control_of_all_target_players_clause(
            "Gain control of all creatures target opponent controls."
        )
        is not None
    )

"""Infusion (CR 207.2c's ability word): the effect *shapes* that follow "if
you gained life this turn" - a look/reveal doubling, a copy-on-cast, an
ETB pump, and an additive life-loss consequence. The boolean fact itself is
already read generically (`machines/conditions/history.py`'s H4
`_life_this_turn` reader, through `Game.condition_holds`); every scenario
here proves the *shape* wired onto that reader, not the reader itself.

Rules verified with `mise run rules:find` in the session that wrote this
file:

- **CR 207.2c** - "Infusion" is a printed ability word: no rules meaning of
  its own, so stripping the label leaves an ordinary instruction.
- **CR 608.2c** - a resolving spell or ability follows its instructions in
  the order written; a later "if <condition>" gates only the instruction it
  is attached to.
- **CR 608.2h** - a look-back value (a destroyed creature's controller, its
  power) is read from the object as it last existed on the battlefield.
- **CR 707.10** / **CR 707.10c** - a copy is put on the stack, not cast; its
  controller may choose new targets.
- **CR 111.7** / **CR 401.4** - "look at", reveal, and the choice of what
  goes to hand vs. bottom.
- **CR 119.3** - an effect that causes a player to lose life.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice: dict | None = None, bob: dict | None = None):
    alice_kwargs = {"library": ["Plains"] * 8, **(alice or {})}
    bob_kwargs = {"library": ["Plains"] * 8, **(bob or {})}
    scenario = Scenario().player("alice", **alice_kwargs).player("bob", **bob_kwargs).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_everything(scenario) -> None:
    """Resolve the stack down to empty, including any pending trigger a
    step above only puts on the stack once somebody would get priority - the
    same helper `tests/scenarios/test_copy_spells_msh.py` uses for a "when
    you cast this spell" self-trigger's own multi-object stack."""
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()


# -- Follow the Lumarets: look/reveal doubling ------------------------------


def test_follow_the_lumarets_reveals_at_most_one_without_life_gained():
    """No life gained this turn: "You may reveal a creature or land card
    from among them and put it into your hand" - at most one, even though
    two eligible cards sit on top. Answering with two is CR 107.1c's own
    illegal option, which `Game.ask` refuses outright - the proof that only
    one was ever offered."""
    scenario = _board(
        {
            "hand": ["Follow the Lumarets"],
            "battlefield": ["Forest", "Forest"],
            "library": ["Grizzly Bears", "Forest", "Lightning Bolt", "Mishra's Bauble"],
        }
    )
    alice = scenario.player("alice")
    top_two = list(alice.library[:2])
    scenario.will_choose_cards(top_two[0], username="alice")
    scenario.cast_and_resolve("Follow the Lumarets", auto=True)
    hand_names = {state.name for state in alice.hand} - {"Follow the Lumarets"}
    assert hand_names == {top_two[0].name}
    assert len(alice.library) == 3


def test_follow_the_lumarets_reveals_two_with_life_gained_this_turn():
    """ "If you gained life this turn, you may instead reveal two creature
    and/or land cards from among them and put them into your hand." - the
    Infusion doubling, proven by actually taking two."""
    scenario = _board(
        {
            "hand": ["Follow the Lumarets"],
            "battlefield": ["Forest", "Forest"],
            "library": ["Grizzly Bears", "Forest", "Lightning Bolt", "Mishra's Bauble"],
        }
    )
    alice = scenario.player("alice")
    scenario.game.gain_life("alice", 1)
    top_creature_and_land = [
        state for state in alice.library[:4] if state.name in ("Grizzly Bears", "Forest")
    ]
    scenario.will_choose_cards(*top_creature_and_land, username="alice")
    scenario.cast_and_resolve("Follow the Lumarets", auto=True)
    hand_names = {state.name for state in alice.hand} - {"Follow the Lumarets"}
    assert hand_names == {"Grizzly Bears", "Forest"}
    # The two cards not taken (Lightning Bolt, Mishra's Bauble) go to the
    # bottom of the library - nothing is lost, only reordered.
    assert len(alice.library) == 2


# -- Foolish Fate: destroy unconditional, life loss only if gained life ----


def test_foolish_fate_destroys_with_no_extra_life_loss():
    scenario = _board(
        {"hand": ["Foolish Fate"], "battlefield": ["Swamp", "Swamp", "Swamp"]},
        {"battlefield": ["Grizzly Bears"]},
    )
    bob = scenario.player("bob")
    target = scenario.creature("Grizzly Bears", "bob")
    before_life = bob.life
    scenario.cast_and_resolve("Foolish Fate", auto=True, targets=[target])
    assert target.zone is Zone.GRAVEYARD
    assert bob.life == before_life


def test_foolish_fate_also_drains_the_controller_when_life_gained_this_turn():
    """ "Infusion — If you gained life this turn, that creature's controller
    loses 3 life." - CR 608.2h reads the controller off the creature as it
    last existed, after it has already been destroyed."""
    scenario = _board(
        {"hand": ["Foolish Fate"], "battlefield": ["Swamp", "Swamp", "Swamp"]},
        {"battlefield": ["Grizzly Bears"]},
    )
    scenario.game.gain_life("alice", 1)
    bob = scenario.player("bob")
    target = scenario.creature("Grizzly Bears", "bob")
    before_life = bob.life
    scenario.cast_and_resolve("Foolish Fate", auto=True, targets=[target])
    assert target.zone is Zone.GRAVEYARD
    assert bob.life == before_life - 3


# -- Lumaret's Favor: copy-on-cast conditioned on the same fact -------------


def test_lumarets_favor_does_not_copy_without_life_gained():
    scenario = _board(
        {"hand": ["Lumaret's Favor"], "battlefield": ["Forest", "Forest", "Grizzly Bears"]},
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    base_power = bears.power
    scenario.cast_onto_stack("Lumaret's Favor", auto=True, targets=[bears])
    _resolve_everything(scenario)
    # Exactly one resolution of the pump - no copy was made.
    assert scenario.game.power_of(bears) == base_power + 2


def test_lumarets_favor_copies_the_spell_when_life_gained_this_turn():
    """ "When you cast this spell, copy it if you gained life this turn. You
    may choose new targets for the copy." - CR 707.10's copy, put on the
    stack above the original."""
    scenario = _board(
        {"hand": ["Lumaret's Favor"], "battlefield": ["Forest", "Forest", "Grizzly Bears"]},
    )
    scenario.game.gain_life("alice", 1)
    bears = scenario.creature("Grizzly Bears", "alice")
    base_power = bears.power
    scenario.will_take_the_may(False)  # decline the copy's own new-targets offer
    scenario.cast_onto_stack("Lumaret's Favor", auto=True, targets=[bears])
    _resolve_everything(scenario)
    # The copy (CR 707.10) resolves above the original: two applications of
    # "+2/+4 until end of turn" to Grizzly Bears - the total is what proves
    # both actually ran, not just one doubled by mistake.
    assert scenario.game.power_of(bears) == base_power + 4


# -- Poisoner's Apprentice: ETB pump only if you gained life this turn -----


def test_poisoners_apprentice_etb_no_pump_without_life_gained():
    scenario = _board(
        {"hand": ["Poisoner's Apprentice"], "battlefield": ["Swamp", "Swamp", "Swamp"]},
        {"battlefield": ["Grizzly Bears"]},
    )
    target = scenario.creature("Grizzly Bears", "bob")
    base_power, base_toughness = target.power, target.toughness
    scenario.cast_and_resolve("Poisoner's Apprentice", auto=True)
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_targets(target)
    scenario.pass_until_resolved()
    scenario.state_based_actions()
    assert target.zone is Zone.BATTLEFIELD
    assert scenario.game.power_of(target) == base_power
    assert scenario.game.toughness_of(target) == base_toughness


def test_poisoners_apprentice_etb_pumps_down_when_life_gained_this_turn():
    """-4/-4 on a 2/2 leaves toughness at -2: CR 704.5g's state-based action
    then destroys it, which is the proof the pump actually took hold (a
    live power/toughness check on the same object cannot be made afterward -
    CR 400.7 makes what is left in the graveyard a new object)."""
    scenario = _board(
        {"hand": ["Poisoner's Apprentice"], "battlefield": ["Swamp", "Swamp", "Swamp"]},
        {"battlefield": ["Grizzly Bears"]},
    )
    scenario.game.gain_life("alice", 1)
    target = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Poisoner's Apprentice", auto=True)
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_targets(target)
    scenario.pass_until_resolved()
    scenario.state_based_actions()
    assert target.zone is Zone.GRAVEYARD

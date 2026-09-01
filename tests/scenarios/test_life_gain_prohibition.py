"""A player who can't gain life: the prohibition, and what it does not stop.

Screaming Nemesis prints the shape this file is about (verified with
`resolve_cards`): "Whenever this creature is dealt damage, it deals that much
damage to any other target. If a player is dealt damage this way, they can't
gain life for the rest of the game." Leyline of Punishment prints the other
shape - "Players can't gain life." - as a static ability.

Both land on the same question: a life gain the rules otherwise direct, that
an effect says can't happen.

- **CR 101.2** - "When a rule or effect allows or directs something to happen,
  and another effect states that it can't happen, the 'can't' effect takes
  precedence." That is why the gain simply does not occur rather than being
  prevented, replaced, or reduced.
- **CR 614.17** - "Some effects state that something can't happen. These
  effects aren't replacement effects, but follow similar rules." CR 614.17c
  adds that such an event "can only be replaced by a self-replacement effect",
  so nothing downstream gets a second say.
- **CR 119.3** - "If an effect causes a player to gain life or lose life, that
  player's life total is adjusted accordingly" - the rule the prohibition
  overrides, and the rule `Player.gain_life`/`Player.lose_life` implement.
- **CR 119.9** - "Some triggered abilities trigger whenever a player gains
  life" - a gain that can't happen is no trigger event either, so a prohibited
  player must not be recorded in `Game.life_gained_this_turn`.
- **CR 702.15b** - lifelink: "Damage dealt by a source with lifelink causes
  that source's controller ... to gain that much life (in addition to any
  other results that damage causes)." The damage is one result and the gain is
  another; only the gain is prohibited.

Two things are modelled, and they are separate. `Player.cannot_gain_life` is
the prohibition as *player state*, which most of this file exercises.
`Game.life_gain_prohibited` is the prohibition as a **board fact**: Leyline of
Punishment's "Players can't gain life." read fresh off the battlefield on
every call, which the last test plays out end to end.

- **CR 119.7** - "If an effect says that a player can't gain life ...", the
  rule that reads either of them back.
- **CR 611.1** - a continuous effect "affects players or the rules of the
  game". The Leyline's sentence changes no characteristic of any object, so
  CR 613's layers have nothing to write and `machines/layers.py` was never the
  right home for it - the reason it went missing for so long.

Screaming Nemesis's trigger still has no entry in `machines/effects.py`, so
the *card* that would set `cannot_gain_life` does not reach it yet.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 101.2, CR 119.3, CR 119.7,
CR 119.9, CR 611.1, CR 614.17, CR 614.17c, CR 702.15b.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def lifelinking_duel() -> Scenario:
    """Wurmcoil Engine (lifelink, deathtouch) on alice's side of an empty board."""
    return Scenario().player("alice", battlefield=["Wurmcoil Engine"]).player("bob")


def test_a_player_who_cannot_gain_life_gains_nothing_from_lifelink():
    """CR 101.2: the lifelink gain is directed, and the "can't" wins.

    Six damage goes through unblocked. CR 702.15b would have alice gain six;
    she can't gain life, so she gains none - and CR 704.5a is nowhere near it,
    because nothing about her life total changed.
    """
    scenario = lifelinking_duel().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.player("alice").cannot_gain_life = True

    wurm = scenario.creature("Wurmcoil Engine")
    scenario.attack_with(wurm)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 20, "CR 101.2: the gain can't happen"
    assert scenario.player("bob").life == 14, "CR 702.15b: the damage still does"


def test_the_prohibition_leaves_no_life_gain_for_CR_119_9_to_trigger_on():
    """A gain that can't happen is not a gain event.

    `Game.life_gained_this_turn` is what CR 119.9's "whenever a player gains
    life" triggers read. Recording a prohibited player there would fire Ocelot
    Pride and friends off a gain that never occurred.
    """
    scenario = lifelinking_duel().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.player("alice").cannot_gain_life = True

    wurm = scenario.creature("Wurmcoil Engine")
    scenario.attack_with(wurm)
    scenario.no_blocks()
    scenario.combat_damage()

    assert "alice" not in scenario.game.life_gained_this_turn


def test_the_same_hit_gains_the_life_when_nothing_prohibits_it():
    """The control: the flag is the only difference between the two."""
    scenario = lifelinking_duel().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Wurmcoil Engine")
    scenario.attack_with(wurm)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 26
    assert "alice" in scenario.game.life_gained_this_turn


def test_the_prohibition_says_nothing_about_losing_life():
    """CR 119.3's other half is untouched: alice can't gain, she can still lose.

    Screaming Nemesis's clause is "they can't gain life", and a player who
    cannot gain life dies to damage exactly as fast as anyone else.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bob.cannot_gain_life = True

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )

    assert bob.life == 17


def test_gain_life_still_reports_the_life_total_it_left_alone():
    """`gain_life` returns the new total (CR 119.3). Refusing must not change
    that contract into `None` or a raise - CR 101.2 makes the instruction do
    nothing, not fail."""
    scenario = lifelinking_duel().build()
    alice = scenario.player("alice")
    alice.cannot_gain_life = True

    assert alice.gain_life(5) == 20
    assert alice.life == 20


def test_a_negative_gain_is_still_refused_as_a_bad_call():
    """The prohibition must not swallow the argument check: `gain_life(-1)` is
    a caller bug either way, and a prohibited player is not a place to hide
    it."""
    scenario = lifelinking_duel().build()
    alice = scenario.player("alice")
    alice.cannot_gain_life = True

    with pytest.raises(ValueError, match="negative"):
        alice.gain_life(-1)


def test_leyline_of_punishment_imposes_the_prohibition_on_both_players():
    """The plan's test-first case, end to end: with the Leyline out, a lifelink
    hit gains nothing.

    Leyline of Punishment (verified with `resolve_cards`): "Players can't gain
    life. Damage can't be prevented." It is a continuous effect from a static
    ability, and it is symmetric - "Players", not "your opponents" - so the
    Leyline's own controller is caught by it too. Here that is bob, whose
    lifelink damage from the Wurm he is being hit by is irrelevant; what
    matters is that alice, attacking with a lifelink creature, gains nothing.

    Read by `Game.life_gain_prohibited`, not by `machines/layers.py`: the
    sentence changes no characteristic, so CR 613's layers have nothing to
    write. CR 611.1 calls it an effect that "affects players or the rules of
    the game", and CR 119.7 is the rule that reads it back.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wurmcoil Engine"])
        .player("bob", battlefield=["Leyline of Punishment"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Wurmcoil Engine")
    scenario.attack_with(wurm)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 14

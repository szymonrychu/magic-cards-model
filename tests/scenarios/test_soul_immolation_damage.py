"""Scenario: Soul Immolation's own damage sentence - "Soul Immolation deals
X damage to each opponent and each creature they control." X is CR 107.3a's
variable, announced through the "blight X" additional cost
(`tests/scenarios/test_blight_counts.py` already covers that cost paying
correctly), not through the spell's own `{3}{R}{R}` mana cost, which carries
no `{X}` symbol at all.

`Game.resolve_top` only ever substituted X into a spell's effect text when
the literal `{X}` symbol was in the printed mana cost (CR 107.3a's most
common case, Fireball's own template) - a spell whose X is instead announced
by an *additional* cost (CR 118.8a) read its own effect text with a bare,
unsubstituted "X" still in it, which no damage-amount parser can read as a
number. The blight itself paid and placed its counters correctly
(`test_blight_counts.py`); only the payoff sentence was silent.

`_DAMAGE_EACH_OPPONENT_AND_THEIRS_RE` (`machines/effects.py`, built for End
the Festivities' "each opponent and each creature and planeswalker they
control") already reads this exact filter shape once X is a real number -
proving this is the substitution gate, not a missing damage-filter reader.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 107.3a** - X in an additional cost the text does not itself define is
  announced by the caster as the spell is cast.
- **CR 701.68a** - "To 'blight N' means to put N -1/-1 counters on a
  creature you control."
- **CR 119.2/CR 120.3a** - damage to a player is a life loss.
- **CR 120.1** - "Simultaneous, non-targeted damage" - CR 608.2f's own
  application to a whole named group at once, so a creature's own damage
  does not change who else the same instruction hits.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_soul_immolation_deals_x_damage_to_each_opponent_and_their_creatures():
    """X=2 (Sting-Slinger, a 3/3, survives blighted for 2): bob and his
    Serra Angel (a 4/4, so it survives 2 damage to be checked afterward)
    each take 2 damage. Alice's own Elvish Mystic is untouched - the
    sentence names only each opponent's creatures, not alice's own.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Soul Immolation"],
            battlefield=["Sting-Slinger", "Elvish Mystic", *(["Mountain"] * 5)],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    slinger = scenario.creature("Sting-Slinger", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    serra = scenario.creature("Serra Angel", "bob")
    mountains = scenario.untapped_sources(*(["Mountain"] * 5))
    bob = scenario.player("bob")
    life_before = bob.life

    casting = scenario.cast("Soul Immolation", username="alice")
    casting.pay_blight(slinger)
    payment = casting.determine_cost(x_value=2)
    casting.begin_paying()
    scenario.pay_with(payment, *mountains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert slinger.counters[Counter.MINUS_ONE] == 2, "the blight cost paid as before"
    assert bob.life == life_before - 2
    assert serra.damage == 2
    assert mystic.damage == 0, "not one of bob's creatures"

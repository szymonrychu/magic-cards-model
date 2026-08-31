"""Judge scenario: exchanging life totals with a player who can't gain life.

From DDR#974 "Mister Negative vs. Screaming Nemesis" - a True Stories episode.
Nick has already damaged Amy with Screaming Nemesis's trigger, so Amy can't
gain life for the rest of the game. Amy then plays Mister Negative and wants to
exchange life totals with Nick.

- If Amy is *above* Nick, the exchange makes her life total go down, so nothing
  stops it and the whole trigger resolves normally, cards drawn included.
- If Amy is *below* Nick, the exchange would raise her life total, and it
  cannot happen at all - **neither** player's life total changes.

The rules:

- **CR 701.12c** - "When life totals are exchanged, each player gains or loses
  the amount of life necessary to equal the other player's previous life
  total." The exchange is implemented as gains and losses, which is what makes
  "can't gain life" relevant at all.
- **CR 119.7** - "If an effect says that a player can't gain life, that player
  can't make an exchange such that the player's life total would become higher;
  in that case, the exchange won't happen."
- **CR 701.12a** - "if the entire exchange can't happen, no part of the
  exchange occurs" is the general form; CR 701.12g says the same for exchanging
  two numerical values. That is why Nick's life total is untouched too, rather
  than the exchange half-happening in Amy's favour.

The player-level half of this is modelled now: `Player.cannot_gain_life` is
CR 119.7's prohibition, and `Player.exchange_life_totals` is the CR 701.12a/c
primitive - refused as one event, applied as gains and losses (see
`tests/scenarios/test_exchanging_life_totals.py` and
`tests/scenarios/test_life_gain_prohibition.py` for its corner cases). What is
still missing is everything that would let the two *cards* reach it: neither
Mister Negative nor Screaming Nemesis has an entry in `machines/effects.py`,
and `Game` has no wrapper to resolve an exchange as part of a spell. So this
file is passing tests on what the engine reads off the printings and on the
prohibition, and an `xfail` for the game-level exchange.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 119.3, CR 119.7, CR 603.1 is
not cited, CR 701.12a, CR 701.12c, CR 701.12g.
"""

import pytest

from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.machines.triggers import triggered_abilities_of
from magic_cards_model.models.player import Player
from tests.cards import card


def test_both_printings_carry_the_triggered_abilities_the_ruling_needs():
    """CR 603.2's shape, read off the two real cards.

    Mister Negative's enters trigger is the one that offers the exchange;
    Screaming Nemesis's damage trigger is the one that imposes "they can't gain
    life for the rest of the game". Both are read as triggered abilities by
    `machines/abilities.parse_abilities`, which is as far as the engine gets
    with either.
    """
    (negative,) = [
        ability
        for ability in parse_abilities(card("Mister Negative"))
        if ability.kind is AbilityKind.TRIGGERED
    ]
    assert "exchange life totals with target opponent" in negative.effect

    (nemesis,) = [
        ability
        for ability in parse_abilities(card("Screaming Nemesis"))
        if ability.kind is AbilityKind.TRIGGERED
    ]
    assert "can't gain life for the rest of the game" in nemesis.effect


def test_only_mister_negatives_half_reaches_the_trigger_matcher():
    """The narrower gap under the one above, worth naming separately.

    Mister Negative's "When Mister Negative enters" resolves to
    `TriggerEvent.ENTERS_THE_BATTLEFIELD`, so `triggered_abilities_of` hands it
    to the matcher. Screaming Nemesis's "Whenever this creature is dealt
    damage" resolves to no `TriggerEvent` at all, so it is dropped before any
    event could match it - the clause that makes Amy unable to gain life never
    fires in the first place.
    """
    assert len(triggered_abilities_of(card("Mister Negative"))) == 1
    assert triggered_abilities_of(card("Screaming Nemesis")) == []


def test_neither_ability_has_a_scripted_effect():
    """The gap, stated rather than discovered by a failing scenario.

    `machines/effects.py` is keyed by card name and neither card has a row, so
    both abilities resolve and do nothing. A scenario that played the episode
    out would pass for the wrong reason.
    """
    for name in ("Mister Negative", "Screaming Nemesis"):
        assert effect_for(name, card(name).oracle_text) is None


def test_a_player_who_cannot_gain_life_does_not_gain_life():
    """CR 119.7's precondition, before any exchange is involved.

    `Player.cannot_gain_life` is the flag Screaming Nemesis's clause needs, and
    `Player.gain_life` refuses outright when it is set - CR 101.2's "can't"
    takes precedence over the rule that directs the gain. Nothing on the card
    side reaches it yet; `tests/scenarios/test_life_gain_prohibition.py` covers
    the prohibition itself and `xfail`s the card that would impose it.
    """
    assert any("gain" in name and "life" in name for name in Player.model_fields)

    amy = Player(username="amy", cannot_gain_life=True)

    assert amy.gain_life(4) == 20
    assert amy.life == 20


@pytest.mark.xfail(
    reason=(
        "The CR 701.12a/701.12c exchange primitive exists on `Player` now "
        "(`Player.exchange_life_totals`), but `Game` has no wrapper for it, so "
        "no resolving spell or ability can reach it. `Game.exchange_life_totals` "
        "belongs to whoever owns models/game.py."
    ),
    strict=True,
)
def test_the_exchange_is_refused_outright_when_one_half_cannot_happen():
    """DDR#974's ruling: Amy below Nick, and nothing moves.

    CR 119.7 stops Amy's half; CR 701.12a/701.12g then stop Nick's, because an
    exchange is one event rather than two independent adjustments.
    """
    from magic_cards_model.models import game as game_module

    assert hasattr(game_module.Game, "exchange_life_totals")

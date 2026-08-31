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

None of this is modelled. `Player` has `gain_life`/`lose_life` and no notion of
being unable to gain life; neither Mister Negative nor Screaming Nemesis has an
entry in `machines/effects.py`; and there is no exchange primitive anywhere. So
this file is one passing test on what the engine *does* read off the printings,
and `xfail`s for the ruling itself.

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


@pytest.mark.xfail(
    reason=(
        "Nothing in the engine can say a player can't gain life: `Player` has "
        "`life`, `gain_life` and `lose_life` and no flag or continuous effect "
        "for CR 119.7's prohibition, so Screaming Nemesis's clause has nowhere "
        "to live."
    ),
    strict=True,
)
def test_a_player_who_cannot_gain_life_does_not_gain_life():
    """CR 119.7's precondition, before any exchange is involved."""
    assert any("gain" in name and "life" in name for name in Player.model_fields)


@pytest.mark.xfail(
    reason=(
        "There is no exchange primitive at all - no CR 701.12a 'if the entire "
        "exchange can't happen, no part of it occurs', and no CR 701.12c "
        "gain/lose implementation - so DDR#974's answer (neither life total "
        "changes) cannot be asserted against the engine."
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

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

Both the player-level and the game-level halves are modelled now:
`Player.cannot_gain_life` is CR 119.7's prohibition,
`Player.exchange_life_totals` is the CR 701.12a/c primitive - refused as one
event, applied as gains and losses - and `Game.exchange_life_totals` is the
wrapper a resolving spell or ability reaches, which also emits the gain and
loss events the primitive does not (see
`tests/scenarios/test_exchanging_life_totals.py` and
`tests/scenarios/test_life_gain_prohibition.py` for the corner cases).

What is still missing is what would let the two *cards* reach it: neither
Mister Negative nor Screaming Nemesis has an entry in `machines/effects.py`,
so both abilities resolve and do nothing. That is asserted rather than
`xfail`ed, below.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 119.3, CR 119.7, CR 603.1 is
not cited, CR 701.12a, CR 701.12c, CR 701.12g.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.machines.delayed import SacrificeSubject
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.machines.triggers import TriggerEvent, triggered_abilities_of
from magic_cards_model.models.game import DelayedTrigger
from magic_cards_model.models.player import Player
from tests.cards import card
from tests.scenarios.harness import Scenario


def _life_watchers(scenario) -> None:
    """Stage a delayed trigger on each of the two life events (CR 603.7).

    No card in the pool prints "whenever a player loses life", so the watchers
    are created through `Game.create_delayed_trigger` the way a resolving spell
    would - what is under test is that the exchange *emits* the events, not
    what anything does about them.
    """
    for event in (TriggerEvent.GAINS_LIFE, TriggerEvent.LOSES_LIFE):
        scenario.game.create_delayed_trigger(
            DelayedTrigger(
                text=f"Whenever a player {event}, note it.",
                effect=SacrificeSubject(),
                event=event,
                controller="amy",
                source_name="a resolving spell",
            )
        )


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


def test_both_halves_now_reach_the_trigger_matcher():
    """Mister Negative's "When Mister Negative enters" resolves to
    `TriggerEvent.ENTERS_THE_BATTLEFIELD`. Screaming Nemesis's "Whenever this
    creature **is dealt** damage" is the passive voice of the identical CR 120
    damage event `TriggerEvent.DEALS_DAMAGE` already names for the active
    "deals damage" phrasing (FRA stream S8's own fix, needed for Hexhaven
    Invigorator's own "Whenever this creature is dealt damage, you may
    search ..." trigger) - `machines/abilities._trigger_event` now reads "is
    dealt"/"are dealt" the same way, so this ability is no longer dropped
    before any event could match it, and `machines/triggers.condition_matches`
    reads the recipient side off `GameEvent.target_id`/`target_controller`/
    `target_types` (a permanent) or `GameEvent.player` (a player) - FRA S5's
    own fields, reconciled onto at the int-engine-dsl merge in place of this
    stream's own narrower, permanent-only `recipient_id`.

    Both reach `triggered_abilities_of`, so the remaining gap that keeps Amy
    able to gain life is entirely the missing effect body
    `test_neither_ability_has_a_scripted_effect` already covers, not the
    condition going unmatched.
    """
    assert len(triggered_abilities_of(card("Mister Negative"))) == 1
    assert len(triggered_abilities_of(card("Screaming Nemesis"))) == 1


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


def test_the_exchange_is_refused_outright_when_one_half_cannot_happen():
    """DDR#974's ruling: Amy below Nick, and nothing moves.

    CR 119.7 stops Amy's half; CR 701.12a then stops Nick's, because an
    exchange is one event rather than two independent adjustments: "if the
    entire exchange can't happen, no part of the exchange occurs."

    Driven through `Game.exchange_life_totals`, the wrapper a resolving spell
    or ability reaches, rather than through the `Player` primitive - the point
    of the case is that the refusal survives the trip through `Game`, and that
    a refused exchange emits no life-gain or life-loss event either.
    """
    scenario = Scenario().player("amy", life=5).player("nick", life=17).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    game.player("amy").cannot_gain_life = True
    _life_watchers(scenario)

    lost = game.exchange_life_totals("amy", "nick")

    assert lost == 0
    assert game.player("amy").life == 5, "CR 119.7 refuses amy's half"
    assert game.player("nick").life == 17, "CR 701.12a refuses nick's with it"
    assert scenario.pending_triggers == [], "nothing moved, so nothing is announced"


def test_an_exchange_that_can_happen_moves_both_totals_and_announces_both():
    """The other side of CR 701.12a, so the refusal above is not vacuous.

    CR 701.12c: "each player gains or loses the amount of life necessary to
    equal the other player's previous life total" - and those really are a
    gain and a loss, so CR 119.9's triggers have events to watch. The return
    value is the life the *first* player lost, which is what Mister Negative's
    "If you lost life this way, draw that many cards" asks for.
    """
    scenario = Scenario().player("amy", life=17).player("nick", life=5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    _life_watchers(scenario)

    lost = game.exchange_life_totals("amy", "nick")

    assert lost == 12, "amy went from 17 to 5"
    assert game.player("amy").life == 5
    assert game.player("nick").life == 17
    assert sorted(item.ability.event for item in scenario.pending_triggers) == sorted(
        [TriggerEvent.GAINS_LIFE, TriggerEvent.LOSES_LIFE]
    ), "one gain and one loss, each announced once (CR 701.12c)"

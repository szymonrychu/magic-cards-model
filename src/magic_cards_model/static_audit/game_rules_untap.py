"""Untap-step, game-rule and deck-construction statics (EP-01 R2, T6).

Each family is credited only when the production reader that performs it
reads the line - never a re-derived regex:

- untap-step statics (CR 502.3, CR 614.10): `machines/untap_statics.py`,
  performed by `Game.untap_step_rule`, `Game._untap_step_impl` and
  `Game._advance_past_checks`; a printed condition must also be one
  `Game.condition_holds` reads, asked on a throwaway real permanent;
- maximum hand size (CR 402.2): `models/player.py`'s readers, performed by
  `Player.cards_over_maximum_hand_size`;
- game-outcome and life statics (CR 104.3, CR 101.2):
  `machines/game_rule_statics.py`, performed by `Game`'s loss/win checks and
  life changes;
- the legend rule exemption (CR 704.5j): `machines/game_rule_statics.py`,
  performed by `Game._legend_rule_losers`;
- uncounterable spells (CR 101.2): `machines/game_rule_statics.py`,
  performed through `casting_restrictions.static_uncounterable_source`;
- deck construction (CR 100.2a, CR 702.139a): `DeckLimits.copies_allowed`
  and `companion.companion_condition_satisfied`, which `Deck.problems`
  enforces before the game.
"""

from magic_cards_model.machines import untap_statics as us
from magic_cards_model.machines.abilities import self_normalized_effect_text


def _condition_of(line: str) -> str | None:
    other = us.other_players_untap_of_line(line)
    if other is not None:
        return other.condition
    skip = us.upkeep_skip_of_line(line)
    if skip is not None:
        return skip.condition
    return us.self_doesnt_untap_condition_of_line(
        line
    ) or us.attached_doesnt_untap_condition_of_line(line)


_READABLE: dict[tuple[str, str], bool] = {}


def _condition_readable(printing, condition: str) -> bool:
    """Whether `Game.condition_holds` reads `condition`, asked on a
    throwaway real permanent of `printing` (memoised per name and text)."""
    from magic_cards_model.static_audit.enters_counters import _stage

    key = (printing.name, condition)
    if key not in _READABLE:
        game, state = _stage(printing, rich=True, record=None)
        _READABLE[key] = game.condition_holds("sweep_you", condition, state) is not None
    return _READABLE[key]


def _reads_untap_line(printing, line: str) -> bool:
    if not us.reads_untap_static_line(line):
        return False
    condition = _condition_of(line)
    return condition is None or _condition_readable(printing, condition)


def _reads_game_rule_line(line: str) -> bool:
    from magic_cards_model.machines import game_rule_statics
    from magic_cards_model.models.deck import reads_deck_limit_line
    from magic_cards_model.models.game import _ZERO_LOYALTY_EXEMPTION_RE

    return (
        game_rule_statics.reads_game_rule_line(line)
        or bool(_ZERO_LOYALTY_EXEMPTION_RE.fullmatch(line.rstrip(".")))
        or reads_deck_limit_line(line)
    )


def reads_game_rules_untap_line(printing, text, *, card_name=None, legendary=False) -> bool:
    name = card_name or printing.name
    line = self_normalized_effect_text(name, text.lstrip("•* ").strip(), legendary=legendary)
    return _reads_untap_line(printing, line) or _reads_game_rule_line(line)

"""EP-01 round 2, task T1: group anthems, group grants and type statics.

Most of this family is read by `machines/layers/group_grants.py` through
`parsed_layer_effects`, which `support._static_ability_category` asks before
any audit module. What lands here is the part another production reader
performs: each predicate stages a throwaway permanent of the printing on a real
`Game` and asks that reader, never a regex of its own (see
`static_audit/__init__.py`).
"""

from magic_cards_model.machines.combat import all_damage_has_wither, may_assign_as_though_unblocked
from magic_cards_model.machines.zone_grants import line_grants_off_zone
from magic_cards_model.models.game import Game
from magic_cards_model.models.player import Player
from magic_cards_model.models.zone import Zone

#: Cheap lowercase gate: every line this module can credit carries one of these.
_GATES = (
    "as though it weren't blocked",
    "had wither",
    "mana as though it were",
    "mana of any type can be spent",
    "can be attached only to",
)


def _staged(printing):
    from magic_cards_model.support import _synthetic_permanent

    game = Game(
        players=[Player(username="sweep_you"), Player(username="sweep_opp")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )
    state = _synthetic_permanent(
        printing, controller="sweep_you", token=False, tapped=False, counter_kind=None
    )
    state.bind_to_game(game)
    state.zone = Zone.BATTLEFIELD
    game.battlefield.append(state)
    return game, state


_UNBLOCKED_CACHE: dict[str, bool] = {}


def _may_assign_as_though_unblocked(printing) -> bool:
    if printing.name not in _UNBLOCKED_CACHE:
        game, state = _staged(printing)
        _UNBLOCKED_CACHE[printing.name] = may_assign_as_though_unblocked(game, state)
    return _UNBLOCKED_CACHE[printing.name]


_WITHER_CACHE: dict[str, bool] = {}


def _all_damage_has_wither(printing) -> bool:
    if printing.name not in _WITHER_CACHE:
        game, _state = _staged(printing)
        _WITHER_CACHE[printing.name] = all_damage_has_wither(game)
    return _WITHER_CACHE[printing.name]


_COLOR_RULE_CACHE: dict[tuple[str, str], bool] = {}


def _reads_mana_colour_rule(printing, lowered: str) -> bool:
    """CR 609.4b: `Game.mana_color_rule` really returns a rule for this card's
    line (and, for Celestial Dawn's second sentence, one that carries it)."""
    key = (printing.name, lowered)
    if key not in _COLOR_RULE_CACHE:
        game, state = _staged(printing)
        rule = game.mana_color_rule("sweep_you", state)
        _COLOR_RULE_CACHE[key] = rule is not None and (
            "other mana" not in lowered or rule.others_colorless
        )
    return _COLOR_RULE_CACHE[key]


def _reads_attach_restriction(printing) -> bool:
    """CR 702.6c: `keywords.attach_restriction_refusal` really refuses a
    creature outside the named quality and allows one inside it."""
    from magic_cards_model.machines.keywords import attach_only_quality
    from magic_cards_model.machines.layers.group_grants import parse_group

    quality = attach_only_quality(printing)
    return quality is not None and parse_group(quality) is not None


def reads_anthems_grants_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    # A static ability granting a keyword (or a type or colour) to cards off the
    # battlefield: `machines/zone_grants.py` reads it, every consumer (unearth,
    # cycling, dredge, ninjutsu, flash, `characteristics_of`) asks that reader.
    if line_grants_off_zone(text):
        return True
    if not any(gate in lowered for gate in _GATES):
        return False
    if "mana as though it were" in lowered or "mana of any type can be spent" in lowered:
        return _reads_mana_colour_rule(printing, lowered)
    if "can be attached only to" in lowered:
        return _reads_attach_restriction(printing)
    if "had wither" in lowered:
        return _all_damage_has_wither(printing)
    return _may_assign_as_though_unblocked(printing)

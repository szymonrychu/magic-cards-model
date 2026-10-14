"""EP-02 R3 T8 part: "deals damage equal to ..." sentences between creatures and players.

- `choose_then_deals_to_group`: "Choose target creature you control. It deals damage equal to
  its power to each other creature." (CR 120.3, CR 608.2c, CR 608.2h: its power is read as
  the spell resolves); a closing sentence ("If this spell was cast from a graveyard, ...")
  runs after, in printed order.
- `may_deal_then_takes_back`: "You may have it deal damage equal to its power to target
  creature. If you do, that creature deals damage equal to its power to this creature."
  (CR 608.2d: the controller chooses; CR 608.2c: the second sentence follows the first).
- `reveal_at_random_then_damage`: "Target creature's controller reveals a card at random from
  their hand. <Spell> deals damage to that creature and that player equal to the revealed
  card's mana value." (CR 701.20a reveal, CR 202.3 mana value, CR 120.3).
"""

import functools
import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from .decisions import source_id_of
from .effects._chains import ABILITY_TEXT, SPELL_TEXT

if TYPE_CHECKING:
    from ..models.game import Game

_STAT_DAMAGE_GROUP_RE = re.compile(
    r"^choose (?P<target>target creature you control)\. it deals damage equal to its "
    r"(?P<stat>power|toughness) to (?P<group>each other creature|each creature)\.(?P<tail> .+)?$",
    re.IGNORECASE,
)
_MAY_DEAL_RE = re.compile(
    r"^you may have (?:it|this creature) deal damage equal to its (?P<stat>power|toughness) to "
    r"(?P<target>target creature(?: defending player controls| an opponent controls| "
    r"you don't control)?)\. if you do, that creature deals damage equal to its "
    r"(?P<back>power|toughness) to (?:this creature|it)\.?$",
    re.IGNORECASE,
)
_EXCESS_REFLEXIVE_RE = re.compile(
    r"^(?P<subject>[^.]+?) deals (?P<n>\d+) damage to (?P<target>target [^.]+?)\.\s*"
    r"when it deals excess damage this way, (?P<consequence>[^.]*?"
    r"mana value less than or equal to that amount of excess damage)\.?$",
    re.IGNORECASE,
)
_REVEAL_DAMAGE_RE = re.compile(
    r"^target creature's controller reveals a card at random from their hand\. "
    r"(?:this spell|[^.]+?) deals damage to that creature and that player equal to the "
    r"revealed card's mana value\.?$",
    re.IGNORECASE,
)


def _stat(game: "Game", creature: CardState, stat: str) -> int:
    value = game.power_of(creature) if stat == "power" else game.toughness_of(creature)
    return max(value or 0, 0)  # CR 120.8: a creature with no positive power deals no damage


@functools.cache
def _choose_then_deals_to_group(text: str, for_spell: bool) -> Any:
    lowered = text.lower()
    if (
        not lowered.startswith("choose target creature")
        or "deals damage equal to its" not in lowered
    ):
        return None
    effect_lines = [line for line in text.split("\n") if not line.lower().startswith("flashback")]
    match = _STAT_DAMAGE_GROUP_RE.fullmatch(" ".join(" ".join(effect_lines).split()))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.dispatch import parse_mixed_effect_for_spell

    if not _targets_understood(match.group("target")):
        return None
    tail = (match.group("tail") or "").strip()
    after = parse_mixed_effect_for_spell(tail) if tail else None
    if tail and after is None:
        return None
    stat, others_only = match.group("stat").lower(), "other" in match.group("group").lower()

    def effect(game: "Game", spell: Any) -> None:
        for source in game.resolve_card_targets(spell):
            if source.zone is not Zone.BATTLEFIELD:
                continue
            amount = _stat(game, source, stat)
            board = game.computed_board()
            victims = [
                p
                for p in list(game.battlefield)
                if board.of(p).is_creature and not (others_only and p.id == source.id)
            ]
            for victim in victims:
                game.deal_damage(victim, amount, source=source)
        if after is not None:
            after(game, spell)

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def choose_then_deals_to_group(effect_text: str) -> Any:
    """`_choose_then_deals_to_group` as a spell's whole text."""
    return _choose_then_deals_to_group(effect_text.strip(), True)


@functools.cache
def _may_deal_then_takes_back(text: str) -> Any:
    if (
        not text.lower().startswith("you may have ")
        or "if you do, that creature deals" not in text.lower()
    ):
        return None
    match = _MAY_DEAL_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match.group("target")):
        return None
    stat, back = match.group("stat").lower(), match.group("back").lower()

    def effect(game: "Game", ability: Any) -> None:
        source = ability.source_or_last_known(game)
        targets = [t for t in game.resolve_card_targets(ability) if t.zone is Zone.BATTLEFIELD]
        if source is None or source.zone is not Zone.BATTLEFIELD or not targets:
            return  # CR 608.2b: no legal target left
        target = targets[0]
        if not game.may(
            ability.controller,
            f"have {source.name} deal damage to {target.name}?",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        game.deal_damage(target, _stat(game, source, stat), source=source)
        # "If you do": it dealt the damage, so the creature hits back (CR 608.2c); a
        # creature already gone is read as it last existed (CR 608.2h).
        game.deal_damage(source, _stat(game, target, back), source=target)

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def may_deal_then_takes_back(text: str) -> Any:
    """`_may_deal_then_takes_back` as an ability's whole text."""
    return _may_deal_then_takes_back(text.strip())


@functools.cache
def _reveal_at_random_then_damage(text: str) -> Any:
    if "reveals a card at random" not in text.lower():
        return None
    match = _REVEAL_DAMAGE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    from .ep02_r2_card_mana_value import _random_pick

    def effect(game: "Game", spell: Any) -> None:
        targets = [t for t in game.resolve_card_targets(spell) if t.zone is Zone.BATTLEFIELD]
        if not targets:
            return
        creature = targets[0]
        owner = game.controller_of(creature)
        hand = list(owner.hand)
        if not hand:
            return  # nothing is revealed, so there is no mana value to deal
        revealed = _random_pick(game, hand, "random reveal")
        game.reveal(revealed, source=spell.name)
        amount = int(revealed.mana_value)  # CR 202.3
        game.deal_damage(creature, amount, source=spell)
        game.deal_damage(owner, amount, source=spell)

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def reveal_at_random_then_damage(effect_text: str) -> Any:
    """`_reveal_at_random_then_damage` as a spell's whole text."""
    return _reveal_at_random_then_damage(effect_text.strip())


@functools.cache
def _damage_then_reflexive_on_excess(text: str) -> Any:
    if "excess damage this way" not in text.lower():
        return None
    from .effects.text import _strip_non_effect_preamble

    match = _EXCESS_REFLEXIVE_RE.fullmatch(" ".join(_strip_non_effect_preamble(text).split()))
    if match is None or re.search(r"\btarget\b", match.group("subject"), re.IGNORECASE):
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match.group("target")):
        return None
    amount = int(match.group("n"))
    consequence = match.group("consequence")

    def effect(game: "Game", spell: Any) -> None:
        from .delayed import ReflexiveConsequence
        from .effects.merges import _excess_threshold

        for target in game.resolve_targets(spell):  # CR 608.2b
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            threshold = _excess_threshold(game, target, spell)
            dealt = game.deal_damage(target, amount, source=spell)
            excess = 0 if threshold is None else dealt - threshold
            if excess <= 0:
                continue
            written = re.sub(
                r"mana value less than or equal to that amount of excess damage",
                f"mana value {excess} or less",
                consequence,
                flags=re.IGNORECASE,
            )
            game.create_reflexive_trigger(
                text=f"{written[:1].upper()}{written[1:]}.",
                controller=game.controller_of(spell).username,
                source_id=spell.id,
                source_name=spell.name,
                callback=ReflexiveConsequence(),
            )

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def damage_then_reflexive_on_excess(effect_text: str) -> Any:
    """`_damage_then_reflexive_on_excess` as a spell's whole text."""
    return _damage_then_reflexive_on_excess(effect_text.strip())


_MAY_PAY_OR_DAMAGE_RE = re.compile(
    r"^each opponent may sacrifice a nonland permanent of their choice or discard a card\.\s*"
    r"then (?:this (?:creature|permanent)|it) deals damage equal to its power to each opponent "
    r"who didn't sacrifice a permanent or discard a card this way\.?$",
    re.IGNORECASE,
)
_SACRIFICE, _DISCARD, _NEITHER = "sacrifice a nonland permanent", "discard a card", "neither"


def _ask_cards(game: "Game", player: Any, prompt: str, source: Any, cards: list[CardState]) -> Any:
    from .decisions import Decision, DecisionKind

    ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=prompt,
            source=source.source_name,
            source_id=source_id_of(source),
            amount=1,
            exact=True,
            cards=tuple(card.id for card in cards),
        )
    )
    return next(card for card in cards if card.id in set(ids))


@functools.cache
def _opponents_may_pay_or_take_damage(text: str) -> Any:
    if "didn't sacrifice a permanent or discard a card" not in text.lower():
        return None
    if _MAY_PAY_OR_DAMAGE_RE.fullmatch(" ".join(text.split())) is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        from .decisions import Decision, DecisionKind
        from .effects._common import _players_in_apnap_order

        controller = game.controller_of(ability).username
        source = ability.source_or_last_known(game)
        for opponent in _players_in_apnap_order(game):
            if opponent.username == controller:
                continue
            nonland = [
                p
                for p in game.permanents_controlled_by(opponent.username)
                if not game.computed_board().of(p).is_land
            ]
            options = [
                *([_SACRIFICE] if nonland else []),
                *([_DISCARD] if opponent.hand else []),
            ]
            paid = False
            if options:
                choice = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_A_QUALITY,
                        player=opponent.username,
                        prompt="sacrifice a nonland permanent or discard a card?",
                        source=ability.source_name,
                        source_id=source_id_of(ability),
                        options=(*options, _NEITHER),
                        quality="cost",
                    )
                )
                if choice == _SACRIFICE:
                    game.sacrifice(
                        _ask_cards(
                            game, opponent, "sacrifice a nonland permanent", ability, nonland
                        )
                    )
                    paid = True
                elif choice == _DISCARD:
                    card = _ask_cards(
                        game, opponent, "discard a card", ability, list(opponent.hand)
                    )
                    game.discard_cards(opponent.username, [card], source=ability.source_name)
                    paid = True
            if not paid and source is not None:
                power = game.power_of(source) if source.zone is Zone.BATTLEFIELD else source.power
                amount = max(int(power or 0), 0)  # CR 120.8
                if amount:
                    game.deal_damage(opponent, amount, source=source)

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def opponents_may_pay_or_take_damage(text: str) -> Any:
    """`_opponents_may_pay_or_take_damage` as an ability's whole text."""
    return _opponents_may_pay_or_take_damage(text.strip())

"""EP-02 R3 T8 part: spells whose second sentence reads the hand of a creature's controller.

- `destroy_then_exile_hand_excess`: "Destroy target creature. If its controller has more than
  four cards in hand, they exile cards from their hand equal to the difference." (CR 701.8a
  destroy, CR 608.2c order, CR 608.2d the player chooses which cards, CR 400.7 the controller
  is the one the creature had when it was destroyed).
- `cast_target_graveyard_card_free`: "You may cast target instant or sorcery card with mana
  value less than or equal to this creature's power from your graveyard without paying its
  mana cost. If that spell would be put into your graveyard, exile it instead." (CR 608.2g,
  CR 614.1a; Dreadhorde Arcanist).
- `cast_up_to_n_free_within_total_mana_value`: "You may cast up to two instant and/or sorcery
  spells with total mana value 6 or less from your graveyard and/or hand without paying their
  mana costs. If those spells would be put into your graveyard, exile them instead." (CR 608.2g,
  CR 202.3; Invoke Calamity). The spell's closing "Exile <this spell>." is the generic
  self-exile sentence `effects.text._strip_self_exile_sentence` removes.
"""

import functools
import re
from typing import TYPE_CHECKING, Any

from ..models.card import Type
from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import parse_count
from .decisions import Decision, DecisionKind, source_id_of
from .effects._chains import ABILITY_TEXT, SPELL_TEXT

if TYPE_CHECKING:
    from ..models.game import Game

_DESTROY_THEN_EXILE_RE = re.compile(
    r"^(?P<destroy>destroy target creature)\. if its controller has more than "
    r"(?P<n>\w+) cards in hand, they exile cards from their hand equal to the difference\.?$",
    re.IGNORECASE,
)


@functools.cache
def _destroy_then_exile_hand_excess(text: str) -> Any:
    if "equal to the difference" not in text.lower():
        return None
    from .effects.text import _strip_non_effect_preamble

    match = _DESTROY_THEN_EXILE_RE.fullmatch(" ".join(_strip_non_effect_preamble(text).split()))
    limit = parse_count(match.group("n")) if match is not None else None
    if match is None or limit is None:
        return None
    from .effects.dispatch import parse_mixed_effect_for_spell

    destroy = parse_mixed_effect_for_spell(match.group("destroy") + ".")
    if destroy is None:
        return None

    def effect(game: "Game", spell: Any) -> None:
        from .decisions import Decision, DecisionKind, source_id_of

        targets = game.resolve_card_targets(spell)
        controllers = [game.controller_of(target) for target in targets]
        destroy(game, spell)
        for player in controllers[:1]:  # CR 608.2b: no legal target, nothing to read
            excess = len(player.hand) - limit
            if excess <= 0:
                continue
            ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"exile {excess} cards from your hand",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=excess,
                    exact=True,
                    cards=tuple(card.id for card in player.hand),
                )
            )
            chosen = [card for card in player.hand if card.id in set(ids)]
            game.exile_cards(chosen)

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def destroy_then_exile_hand_excess(effect_text: str) -> Any:
    """`_destroy_then_exile_hand_excess` as a spell's whole text."""
    return _destroy_then_exile_hand_excess(effect_text.strip())


_CAST_TARGET_FREE_RE = re.compile(
    r"^you may cast (?P<phrase>target (?:instant or sorcery|[a-z]+) card(?: with mana value "
    r"less than or equal to [^.]+?)?) from your graveyard without paying its mana cost\."
    r"(?P<rider> if that spell would be put into your graveyard, exile it instead\.?)?$",
    re.IGNORECASE,
)


@functools.cache
def _cast_target_graveyard_card_free(text: str) -> Any:
    if "from your graveyard without paying its mana cost" not in text.lower():
        return None
    match = _CAST_TARGET_FREE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(
        match.group("phrase") + " from your graveyard", battlefield_only=False
    ):
        return None
    exile_instead = match.group("rider") is not None

    def effect(game: "Game", ability: Any) -> None:
        caster = game.controller_of(ability).username
        for target in game.resolve_targets(ability):  # CR 608.2b: rechecked as it resolves
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                game.may_cast_during_resolution(
                    target,
                    caster,
                    prompt=f"cast {target.name} without paying its mana cost",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    source_name=ability.source_name,
                    rule="CR 608.2g",
                    exile_instead_of_graveyard=exile_instead,
                )

    return effect


@ABILITY_TEXT.rung("s22")
def cast_target_graveyard_card_free(effect_text: str) -> Any:
    """`_cast_target_graveyard_card_free` as an ability's whole text."""
    return _cast_target_graveyard_card_free(effect_text.strip())


_CAST_UP_TO_FREE_RE = re.compile(
    r"^you may cast up to (?P<n>\w+) instant and/or sorcery spells with total mana value "
    r"(?P<total>\d+) or less from your (?P<zones>graveyard and/or hand|hand and/or graveyard) "
    r"without paying their mana costs\."
    r"(?P<rider> if those spells would be put into your graveyard, exile them instead\.?)?$",
    re.IGNORECASE,
)


@functools.cache
def _cast_up_to_n_free_within_total(text: str) -> Any:
    if "with total mana value" not in text.lower():
        return None
    match = _CAST_UP_TO_FREE_RE.fullmatch(" ".join(text.split()))
    limit = parse_count(match.group("n")) if match is not None else None
    if match is None or limit is None:
        return None
    total = int(match.group("total"))
    exile_instead = match.group("rider") is not None

    def effect(game: "Game", spell: Any) -> None:
        player = game.controller_of(spell)
        chosen: list[CardState] = []
        spent = 0
        while len(chosen) < limit:  # CR 608.2d: each pick is made among what is still legal
            candidates = [
                card
                for card in (*player.graveyard, *player.hand)
                if card not in chosen
                and {Type.INSTANT, Type.SORCERY} & set(card.card.types)
                and card.mana_value <= total - spent
                and game.can_cast_during_resolution(card, player.username)
            ]
            if not candidates:
                break
            ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt="choose an instant or sorcery to cast without paying its mana cost",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=1,
                    exact=False,
                    cards=tuple(card.id for card in candidates),
                )
            )
            picked = [card for card in candidates if card.id in set(ids)]
            if not picked:
                break
            chosen.append(picked[0])
            spent += int(picked[0].mana_value)
        for card in chosen:
            game.cast_during_resolution(
                card,
                player.username,
                source_name=spell.name,
                rule="CR 608.2g",
                exile_instead_of_graveyard=exile_instead,
            )

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def cast_up_to_n_free_within_total_mana_value(effect_text: str) -> Any:
    """`_cast_up_to_n_free_within_total` as a spell's whole text."""
    return _cast_up_to_n_free_within_total(effect_text.strip())

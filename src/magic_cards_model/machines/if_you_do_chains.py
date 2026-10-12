"""'You may X. If you do, Y' chains (CR 608.2c, CR 608.2d): the optional
action is taken while the ability resolves, and the consequence runs on the
same ability only if it was.

The action shapes read here, each by its printed template:

- remove a counter from each of N creatures you control;
- choose target <card> in your graveyard, then sacrifice a <quality> to
  return "the chosen card" to the battlefield;
- put a <quality> card from your hand or graveyard onto the battlefield.

`if_you_do_consequence` is the consequence reader every "If you do" chain
shares: the ordinary clause readers first (`pay_consequence_effect`), then
the whole ability dispatcher, so a consequence such as "when you next cast
an instant or sorcery spell this turn, copy it" is read whole.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import parse_count

if TYPE_CHECKING:
    from ..models.game import Game


def if_you_do_consequence(text: str) -> Any:
    """The consequence of an "If you do, <text>" chain, read whole by the
    ability dispatcher, or None (a notice is not a reading)."""
    from .effects.dispatch import _ability_effect_or_notice
    from .effects.tokens import _is_notice_only

    effect = _ability_effect_or_notice(text)
    if effect is None or _is_notice_only(effect):
        return None
    return effect


def _ask_may(
    game: Game, player: str, prompt: str, source: str, source_id: Any, legal: bool
) -> bool:
    from .decisions import Decision, DecisionKind

    return bool(
        game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=player,
                prompt=prompt,
                source=source,
                affirmative_is_legal=legal,
                source_id=source_id,
            )
        )
    )


# --------------------------------------------------------------------------
# "you may remove a <kind> counter from each of <N> creatures you control.
# If you do, <consequence>."
# --------------------------------------------------------------------------

_REMOVE_FROM_EACH_OF_N_RE = re.compile(
    r"^you may remove (?:a|an|one) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counter from each of "
    r"(?P<n>two|three|four|\d+) (?P<group>creatures|permanents|artifacts) you control\.\s*"
    r"if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_remove_counter_from_each_of_n(text: str) -> Any:
    """Dyadrine, Synthesis Amalgam's shape: the action is possible only when
    N different objects of the group each carry such a counter (CR 608.2d);
    the controller picks which N."""
    from .effects.counters import _counter_kind
    from .effects.text import _strip_non_effect_preamble

    match = _REMOVE_FROM_EACH_OF_N_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = parse_count(match["n"])
    if count is None or count < 1:
        return None
    kind = _counter_kind(match["kind"])
    group = match["group"].lower()
    consequence = if_you_do_consequence(match["consequence"].strip() + ".")
    if consequence is None:
        return None

    def effect(game: Game, ability: Any) -> None:
        from ..models.card import Type
        from .decisions import Decision, DecisionKind, source_id_of

        controller = game.controller_of(ability).username
        wanted = {"creatures": Type.CREATURE, "artifacts": Type.ARTIFACT}.get(group)
        candidates = [
            permanent
            for permanent in game.battlefield
            if permanent.controller == controller
            and permanent.counter_count(kind) >= 1
            and (wanted is None or wanted in game.characteristics_of(permanent).types)
        ]
        legal = len(candidates) >= count
        if not _ask_may(
            game,
            controller,
            f"remove a {kind} counter from each of {count} {group} you control",
            ability.source_name,
            source_id_of(ability),
            legal,
        ):
            return
        if not legal:
            return
        chosen = candidates
        if len(candidates) > count:
            ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt=f"choose {count} {group} to remove a {kind} counter from",
                    source=ability.source_name,
                    amount=count,
                    cards=tuple(p.id for p in candidates),
                    source_id=source_id_of(ability),
                )
            )
            by_id = {p.id: p for p in candidates}
            chosen = [by_id[i] for i in ids]
        for permanent in chosen[:count]:
            permanent.remove_counters(kind, 1)
        consequence(game, ability)

    return effect


# --------------------------------------------------------------------------
# "choose target <card> in your graveyard. You may sacrifice <quality>. If
# you do, return the chosen card to the battlefield."
# --------------------------------------------------------------------------

_CHOSEN_TARGET_SACRIFICE_RETURN_RE = re.compile(
    r"^choose target (?P<target>[^.]+?) in your graveyard\.\s*you may sacrifice "
    r"(?P<sacrifice>an? [a-z ]+?)\.\s*if you do, return the chosen card "
    r"(?:from your graveyard )?to the battlefield(?P<yours> under your control)?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_chosen_target_sacrifice_return(text: str) -> Any:
    """Daretti, Rocketeer Engineer's shape: the graveyard card is a target
    announced as the ability goes on the stack (CR 603.3d), "the chosen
    card" names it again; the sacrifice is the optional action."""
    from .effects._common import _quality_matcher
    from .effects.text import _strip_non_effect_preamble

    match = _CHOSEN_TARGET_SACRIFICE_RETURN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    quality = re.sub(r"^an? ", "", match["sacrifice"].strip(), flags=re.IGNORECASE)
    try:
        matches = _quality_matcher(quality)
    except (ValueError, KeyError):
        return None

    def effect(game: Game, ability: Any) -> None:
        from .decisions import source_id_of
        from .effects.modal import _choose_one_card

        controller = game.controller_of(ability).username
        chosen = [
            t
            for t in game.resolve_targets(ability)
            if isinstance(t, CardState) and t.zone is Zone.GRAVEYARD
        ]
        fodder = [
            p
            for p in game.battlefield
            if p.controller == controller and matches(game.characteristics_of(p))
        ]
        if not _ask_may(
            game,
            controller,
            f"sacrifice {match['sacrifice']}",
            ability.source_name,
            source_id_of(ability),
            bool(fodder),
        ):
            return
        if not fodder:
            return
        victim = _choose_one_card(
            game,
            game.player(controller),
            fodder,
            prompt=f"choose {match['sacrifice']} to sacrifice",
            source=ability.source_name,
            source_id=source_id_of(ability),
        )
        game.sacrifice(victim)
        for card_state in chosen:
            if card_state.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(card_state, controller)

    return effect


# --------------------------------------------------------------------------
# "you may put a <quality> card from your hand or graveyard onto the
# battlefield."
# --------------------------------------------------------------------------

_PUT_FROM_HAND_OR_GRAVEYARD_RE = re.compile(
    r"^(?:then )?you may put an? (?P<quality>[a-z ]+?) card from your hand or graveyard onto "
    r"the battlefield\.?$",
    re.IGNORECASE,
)


def parse_put_from_hand_or_graveyard(clause: str) -> Any:
    """Dakkon, Shadow Slayer's −6 and Bonny Pall, Clearcutter's attack
    trigger: one card of the quality, from either zone, chosen while the
    ability resolves (CR 608.2d)."""
    from .effects._common import _quality_matcher

    match = _PUT_FROM_HAND_OR_GRAVEYARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    quality = match["quality"].strip()
    try:
        matches = _quality_matcher(quality)
    except (ValueError, KeyError):
        return None

    def effect(game: Game, ability: Any) -> None:
        from .decisions import source_id_of
        from .effects.modal import _choose_one_card

        controller = game.controller_of(ability).username
        player = game.player(controller)
        candidates = [c for c in [*player.hand, *player.graveyard] if matches(c)]
        if not _ask_may(
            game,
            controller,
            f"put a {quality} card from your hand or graveyard onto the battlefield",
            getattr(ability, "source_name", None) or ability.name,
            source_id_of(ability),
            bool(candidates),
        ):
            return
        if not candidates:
            return
        chosen = _choose_one_card(
            game,
            player,
            candidates,
            prompt=f"choose a {quality} card to put onto the battlefield",
            source=getattr(ability, "source_name", None),
            source_id=source_id_of(ability),
        )
        game.put_onto_battlefield(chosen, controller)

    return effect

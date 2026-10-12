"""Keyword abilities written out as the triggered abilities their rules say.

CR 702.1: a keyword is shorthand for one or more abilities. These are the
combat and death-trigger keywords of the older sets plus a few newer ones:

- afterlife (CR 702.135a): "When this permanent is put into a graveyard from
  the battlefield, create N 1/1 white and black Spirit creature tokens with
  flying."
- graft (CR 702.58a): enters with N +1/+1 counters, and moves one onto each
  creature that enters afterwards.
- backup (CR 702.165a): "When this creature enters, put N +1/+1 counters on
  target creature. If that's another creature, it also gains the non-backup
  abilities of this creature printed below this one until end of turn."
- champion (CR 702.72a): two linked triggers - enters: sacrifice it unless you
  exile another [object] you control; leaves the battlefield: return the
  exiled card to the battlefield under its owner's control.
- mentor (CR 702.134a): "Whenever this creature attacks, put a +1/+1 counter
  on target attacking creature with power less than this creature's power."

It also holds the keyword actions fateseal (CR 701.29a) and clash (CR 701.30)
and the clause readers for the champion and clash instructions.

`machines/keywords._TRIGGER_EXPANSIONS` registers `LEGACY_EXPANSIONS`, so the
trigger matcher and the effect parser see them like any printed trigger.
"""

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING

from ..models.card import Type
from ..models.card_state import CardState
from ..models.zone import Zone
from .abilities import KeywordAbility, TriggeredAbility, TriggerEvent, TriggerWord
from .decisions import CardSplit, Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ..models.game import Game
    from ..models.player import Player
    from .effects import AbilityEffect
    from .triggers import AbilityOnStack

_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def _count(ability: KeywordAbility) -> int:
    return ability.count if ability.count is not None else 1


def _afterlife_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.135a / CR 702.135b (each instance triggers separately)."""
    from .keywords import _expansion

    count = _count(ability)
    noun = "token" if count == 1 else "tokens"
    quantity = _WORDS.get(count, str(count))
    return _expansion(
        ability,
        keyword="afterlife",
        word=TriggerWord.WHEN,
        condition="this permanent is put into a graveyard from the battlefield",
        effect=f"create {quantity} 1/1 white and black Spirit creature {noun} with flying",
        event=TriggerEvent.DIES,
    )


def _mentor_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.134a / CR 702.134b (each instance triggers separately)."""
    from .keywords import _expansion

    return _expansion(
        ability,
        keyword="mentor",
        word=TriggerWord.WHENEVER,
        condition="this creature attacks",
        effect=(
            "put a +1/+1 counter on target attacking creature with power less than "
            "this creature's power"
        ),
        event=TriggerEvent.ATTACKS,
    )


def _graft_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.58a's second half: "Whenever another creature enters, if this
    permanent has a +1/+1 counter on it, you may move a +1/+1 counter from this
    permanent onto that creature." (The static half - enters with N counters -
    is `machines/replacement/enters._modular_entering_counters`.) CR 702.58b:
    each instance works separately."""
    from .keywords import _expansion

    return _expansion(
        ability,
        keyword="graft",
        word=TriggerWord.WHENEVER,
        condition="another creature enters",
        intervening_if="this permanent has a +1/+1 counter on it",
        effect="you may move a +1/+1 counter from this permanent onto that creature",
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


BACKUP_GRANT_CLAUSE = (
    "If that's another creature, it also gains the non-backup abilities of this creature "
    "printed below this one until end of turn"
)


def _backup_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.165a. The abilities it grants are the printed lines below the
    backup line (`backup_granted_lines`), read when the ability resolves."""
    from .keywords import _expansion

    count = _count(ability)
    noun = "counter" if count == 1 else "counters"
    return _expansion(
        ability,
        keyword="backup",
        word=TriggerWord.WHEN,
        condition="this creature enters",
        effect=(
            f"put {_WORDS.get(count, str(count))} +1/+1 {noun} on target creature. "
            f"{BACKUP_GRANT_CLAUSE}"
        ),
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


_REMINDER_RE = re.compile(r"\s*\([^)]*\)")


@cache
def backup_granted_lines(oracle_text: str) -> tuple[str, ...]:
    """The abilities printed below the backup line of `oracle_text` (CR 702.165a),
    one entry per printed line with its reminder text removed. Abilities printed
    above the backup line are never granted (CR 702.165a)."""
    lines = oracle_text.split("\n")
    for index, line in enumerate(lines):
        if line.lower().startswith("backup"):
            below = (_REMINDER_RE.sub("", rest).strip() for rest in lines[index + 1 :])
            return tuple(rest for rest in below if rest)
    return ()


#: What a champion line names: "Champion a Kithkin", "Champion a creature",
#: "Champion a Goblin or Shaman" (CR 702.72a's "[object]").
_CHAMPION_OBJECT_RE = re.compile(r"^an? (?P<object>.+)$", re.IGNORECASE)


def _champion_abilities(ability: KeywordAbility) -> list[TriggeredAbility]:
    """CR 702.72a: "Champion an [object]" means "When this permanent enters,
    sacrifice it unless you exile another [object] you control" and "When this
    permanent leaves the battlefield, return the exiled card to the battlefield
    under its owner's control." CR 702.72b links the two (CR 607)."""
    from .keywords import _expansion

    match = _CHAMPION_OBJECT_RE.match(ability.parameter or "")
    if match is None:
        return []
    return [
        _expansion(
            ability,
            keyword="champion",
            word=TriggerWord.WHEN,
            condition="this permanent enters",
            effect=f"sacrifice it unless you exile another {match.group('object')} you control",
            event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
        ),
        _expansion(
            ability,
            keyword="champion",
            word=TriggerWord.WHEN,
            condition="this permanent leaves the battlefield",
            effect="return the exiled card to the battlefield under its owner's control",
            event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
        ),
    ]


_CHAMPION_ENTERS_RE = re.compile(
    r"^sacrifice it unless you exile another (?P<object>.+?) you control\.?$", re.IGNORECASE
)
_CHAMPION_RETURN_RE = re.compile(
    r"^return the exiled card to the battlefield under its owner's control\.?$", re.IGNORECASE
)


def _is_champion_object(game: "Game", card: CardState, object_text: str) -> bool:
    """Whether `card` is an [object] a champion line names: the word "creature",
    or one or more creature subtypes joined by "or" (CR 205.3m)."""
    characteristics = game.characteristics_of(card)
    wanted = [word.strip().lower() for word in object_text.split(" or ")]
    if wanted == ["creature"]:
        return Type.CREATURE in characteristics.types
    subtypes = {subtype.lower() for subtype in characteristics.subtypes}
    return any(word in subtypes for word in wanted)


def parse_champion_clause(text: str) -> "AbilityEffect | None":
    """Both halves of champion (CR 702.72a), or `None` for other text."""
    flat = " ".join(text.strip().split())
    enters = _CHAMPION_ENTERS_RE.fullmatch(flat)
    if enters is not None:
        object_text = enters.group("object")

        def champion_enters(game: "Game", ability: "AbilityOnStack") -> None:
            from .effects.removal import linked_exile_annotation

            source = ability.source(game)
            if source is None or source.zone is not Zone.BATTLEFIELD:
                return
            controller = game.controller_of(ability).username
            candidates = [
                card
                for card in game.permanents_controlled_by(controller)
                if card.id != source.id and _is_champion_object(game, card, object_text)
            ]
            chosen = None
            if candidates:
                answer = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=controller,
                        prompt=(
                            f"exile another {object_text} you control, or sacrifice {source.name}"
                        ),
                        source=source.name,
                        source_id=source_id_of(ability),
                        amount=1,
                        exact=False,
                        cards=tuple(card.id for card in candidates),
                        default_cards=(candidates[-1].id,),
                    )
                )
                assert isinstance(answer, tuple)
                chosen = next((card for card in candidates if card.id in answer), None)
            if chosen is None:
                game.sacrifice(source)
                return
            game.exile_permanent(chosen)
            if chosen.zone is Zone.EXILE:
                chosen.exile_annotation = linked_exile_annotation(game, ability, chosen)

        return champion_enters
    if _CHAMPION_RETURN_RE.fullmatch(flat) is not None:

        def champion_returns(game: "Game", ability: "AbilityOnStack") -> None:
            if ability.source_id is None:
                return
            for card in game.cards_exiled_with(ability.source_id, ability.source_stamp):
                if card.zone is Zone.EXILE:
                    game.put_onto_battlefield(
                        card, card.owner or game.controller_of(ability).username
                    )

        return champion_returns
    return None


def _fateseal_target(
    game: "Game", chooser: "Player", source: str | None, source_id
) -> "Player | None":
    from .effects.modal import _choose_an_opponent

    return _choose_an_opponent(game, chooser, source or "", source_id)


def fateseal(
    game: "Game",
    player: "Player | str",
    count: int,
    *,
    source: str | None = None,
    source_id: str | None = None,
) -> CardSplit:
    """Fateseal N (CR 701.29a): look at the top N cards of an opponent's library,
    then put any number of them on the bottom of that library in any order and
    the rest on top in any order. Fateseal 0 (CR 701.29 as scry 0, CR 701.22b)
    asks nothing."""
    if isinstance(player, str):
        player = game.player(player)
    if count <= 0:
        return CardSplit()
    opponent = _fateseal_target(game, player, source, source_id)
    if opponent is None:
        return CardSplit()
    looked_at = game._look_at_top(opponent, count)
    pending_looks = game._look_before_choosing(player, looked_at, source)
    answer = game.ask(
        Decision(
            kind=DecisionKind.SCRY,
            player=player.username,
            prompt=f"fateseal {count}",
            source=source,
            source_id=source_id,
            amount=count,
            exact=False,
            cards=tuple(state.id for state in looked_at),
            moved_label="bottom of that library",
            kept_label="top of that library",
        )
    )
    assert isinstance(answer, CardSplit)
    to_bottom, on_top = game._split_top(opponent, looked_at, answer)
    to_bottom = game.ask_library_bottom_order(player, to_bottom, source=source, source_id=source_id)
    game._end_looks(pending_looks)
    library = opponent.library
    for state in looked_at:
        library.remove(state)
    for index, state in enumerate(on_top):
        library.insert(index, state)
    library.extend(to_bottom)
    if on_top or to_bottom:
        opponent.note_library_changed(placed=looked_at)
    for state in (*on_top, *to_bottom):
        game.look(state, player.username, source=source)
    return CardSplit(
        moved=tuple(state.id for state in to_bottom),
        top_order=tuple(state.id for state in on_top),
    )


def clash(
    game: "Game",
    player: "Player | str",
    *,
    source: str | None = None,
    source_id: str | None = None,
) -> bool:
    """Clash with an opponent (CR 701.30b); whether `player` won (CR 701.30d).

    Each clashing player reveals the top card of their library at the same
    time (CR 701.30c), then those players decide in APNAP order whether the
    card goes to the bottom of the library (CR 701.30a), and the cards move at
    the same time. A player wins by revealing a card with a higher mana value
    than every other revealed card; a player with an empty library reveals
    nothing and cannot win."""
    if isinstance(player, str):
        player = game.player(player)
    opponent = _fateseal_target(game, player, source, source_id)
    if opponent is None:
        return False
    clashers = [player, opponent]
    revealed = {}
    for clasher in clashers:
        top = clasher.library[0] if clasher.library else None
        revealed[clasher.username] = top
        if top is not None:
            game.reveal(top, source=source)
    bottomed = []
    for clasher in clashers:
        top = revealed[clasher.username]
        if top is None:
            continue
        if game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=clasher.username,
                prompt=f"put {top.name} on the bottom of your library",
                source=source,
                source_id=source_id,
                default_may=False,
            )
        ):
            bottomed.append((clasher, top))
    for clasher, top in bottomed:
        clasher.library.remove(top)
        clasher.library.append(top)
        clasher.note_library_changed(placed=[top])
    mine = revealed[player.username]
    if mine is None:
        return False
    others = [card for name, card in revealed.items() if name != player.username and card]
    return all(mine.mana_value > other.mana_value for other in others)


_CLASH_RE = re.compile(
    r"^clash with an opponent\."
    r"(?: if you win, (?P<win>.+?))?"
    r"(?:\.? otherwise, (?P<lose>.+?))?\.?$",
    re.IGNORECASE,
)


def parse_clash_clause(text: str) -> "AbilityEffect | None":
    """ "Clash with an opponent. If you win, [effect]." with an optional
    "Otherwise, [effect]." (CR 701.30)."""
    flat = " ".join(text.strip().split())
    match = _CLASH_RE.fullmatch(flat)
    if match is None:
        return None
    from .effects import parse_mixed_effect

    branches = {}
    for name in ("win", "lose"):
        branch_text = match.group(name)
        if branch_text is None:
            continue
        parsed = parse_mixed_effect(branch_text.rstrip(".") + ".")
        if parsed is None:
            return None
        branches[name] = parsed

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        won = clash(
            game,
            game.controller_of(ability),
            source=ability.source_name,
            source_id=source_id_of(ability),
        )
        branch = branches.get("win" if won else "lose")
        if branch is not None:
            branch(game, ability)

    return effect


#: The keyword (Scryfall spelling, lowercase) and the one ability it expands to.
LEGACY_EXPANSIONS: dict[str, Callable[[KeywordAbility], list[TriggeredAbility]]] = {
    "champion": _champion_abilities,
    "afterlife": lambda ability: [_afterlife_ability(ability)],
    "mentor": lambda ability: [_mentor_ability(ability)],
    "graft": lambda ability: [_graft_ability(ability)],
    "backup": lambda ability: [_backup_ability(ability)],
}

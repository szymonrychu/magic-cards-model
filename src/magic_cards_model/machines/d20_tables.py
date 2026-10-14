"""Die-roll results tables (CR 706), read off an ability's own text.

"<instructions>. Roll a dN[ and add|subtract <amount>]. [If the result is N or
less, <effect>.] <low>[-<high>] | <what happens> ..." - Wizard's Spellbook's
`{T}` ability, Chaos Channeler's attack trigger, Swarming Goblins, The Deck of
Many Things. `abilities._merge_roll_table_lines` keeps the rows with the roll
instruction they answer (CR 706.3b: the roll, its modifiers, the instructions
based on its result and the table are one ability).

The rules, each looked up with `mise run rules:find`:

- CR 706.2: the natural result plus the instruction's own modifiers is the
  result of the roll ("Roll a d20 and subtract the number of cards in your
  hand").
- CR 706.3a: each row means "If the result was in this range, [effect]"; a
  result no row names does nothing ("if any") - a modified result can fall
  below the first row.
- CR 207.2d: a flavor word before a row's effect ("Trapped! - You lose 3
  life.") has no rules meaning and is not read.

What a row says is read by the ordinary ability pipeline, after three
rewrites of the row's own anaphora into the words that pipeline reads:

- "that creature"/"that card" after "Choose target <X>, then roll" is the one
  target the instruction chose (CR 115.1), so the row is read with
  "target <X>" in its place - never as the triggering event's subject, which
  is what a bare "that creature" means to the pipeline;
- "Create two of those tokens." is the token an earlier row creates;
- "this card" (a card that is not a permanent, CR 201.5) is the source in
  its graveyard - Loathsome Troll's graveyard-only ability.

Rows no ordinary clause reader covers - copying an exiled card and casting
the copy, a search that puts an artifact onto the battlefield and anything
else into the hand, a creature taken from any graveyard whose death costs
its owner the game - are read here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING, Any

from magic_cards_model.text_norm import collapsed

from ..models.card import Type
from ..models.card_state import CardState
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack

#: The high end of CR 706.3a's single-endpoint "N+" range.
_OPEN_END = 10**6

#: A row effect: `(game, ability, exiled_now)` - `exiled_now` is what the
#: sentences before the roll exiled ("that card" of a copy row).
RowEffect = Callable[["Game", "AbilityOnStack", list[CardState]], None]

ROLL_TABLE_RE = re.compile(
    r"^(?P<pre>.*?)\s*\broll an? d(?P<sides>\d+)"
    r"(?: and (?P<sign>add|subtract) (?P<modifier>[^.]+?))?\.\s*"
    r"(?:if the result is (?P<floor>-?\d+) or less, (?P<floor_effect>[^.]+)\.\s*)?"
    r"(?P<rows>\d+(?:[-–—]\d+|\+)? \| .+)$",
    re.IGNORECASE | re.DOTALL,
)
_ROW_START_RE = re.compile(r"(?:^|(?<=\s))(?P<low>\d+)(?:[-–—](?P<high>\d+)|(?P<plus>\+))? \| ")
#: "Choose target <X>, then" - the instruction only names the target the rows
#: act on (Scion of Stygia, Spiked Pit Trap, Aberrant Mind Sorcerer).
_CHOOSE_TARGET_THEN_RE = re.compile(r"^choose (?P<phrase>target [^,.]+), then$", re.IGNORECASE)
#: CR 207.2d: a capitalised flavor word (or phrase) and an em dash before a
#: row's effect - no sentence punctuation but a closing "!", at most 40 chars.
_FLAVOR_WORD_RE = re.compile(r"^(?P<flavor>[A-Z][^.|—]{0,38}?!?)\s+—\s+(?P<body>.+)$")
_THAT_NOUN_RE = re.compile(
    r"\bthat (?P<noun>creature|card|permanent|artifact|land|planeswalker)\b", re.IGNORECASE
)
_THOSE_TOKENS_RE = re.compile(r"^create (?P<count>\w+) of those tokens\.?$", re.IGNORECASE)
_TOKEN_ROW_RE = re.compile(r"^create an? (?P<what>.+?) token(?P<rest>[^.]*)\.?$", re.IGNORECASE)
_THIS_CARD_RE = re.compile(r"\bthis card\b(?! from)", re.IGNORECASE)
_COPY_CAST_ROW_RE = re.compile(
    r"^copy (?P<what>that card|each card exiled with this \w+)\.\s*"
    r"you may cast (?P<which>the copy|any number of the copies)"
    r"(?: by paying (?P<alt>(?:\{[^}]+\})+) rather than paying its mana cost"
    r"| (?P<free>without paying (?:its|their) mana costs?))?\.?$",
    re.IGNORECASE,
)
#: Treasure Chest's natural 20: "Search your library for a card. If it's an
#: artifact card, you may put it onto the battlefield. Otherwise, put that
#: card into your hand. Then shuffle." (CR 701.23a's search, then a choice of
#: two destinations by the found card's type).
_SEARCH_TYPE_SPLIT_RE = re.compile(
    r"^search your library for a card\.\s*"
    r"if it'?s an? (?P<type>[a-z]+) card, you may put it onto the battlefield\.\s*"
    r"otherwise, put that card into your hand\.\s*then shuffle\.?$",
    re.IGNORECASE,
)
#: The Deck of Many Things' natural 20: "Put a creature card from any
#: graveyard onto the battlefield under your control. When that creature
#: dies, its owner loses the game." - chosen as the row resolves (no target),
#: watched by a delayed trigger (CR 603.7) whose loss is CR 104.3e's.
_ANY_GRAVEYARD_REANIMATE_RE = re.compile(
    r"^put an? (?P<type>[a-z]+) card from any graveyard onto the battlefield under your "
    r"control\.(?:\s*when that (?P=type) dies, (?P<doom>[^.]+)\.?)?$",
    re.IGNORECASE,
)


def split_roll_rows(
    rows: str, sides: int, *, modified: bool = False
) -> list[tuple[int, int, str]] | None:
    """The rows of a results table as `(low, high, body)`, or None.

    An unmodified roll's rows tile 1..`sides` exactly once each - every
    natural result has its row. A modified roll's rows are in order and do not
    overlap, but a result below or above them names no row (CR 706.3a's "if
    any"). "N+" is CR 706.3a's single-endpoint range."""
    starts = list(_ROW_START_RE.finditer(rows))
    if not starts or starts[0].start() != 0:
        return None
    parsed: list[tuple[int, int, str]] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(rows)
        low = int(match.group("low"))
        high = _OPEN_END if match.group("plus") else int(match.group("high") or low)
        parsed.append((low, high, rows[match.end() : end].strip()))
    expected = parsed[0][0] if modified else 1
    for low, high, _ in parsed:
        if low != expected or high < low:
            return None
        expected = high + 1
    if modified:
        return parsed
    return parsed if expected == sides + 1 or parsed[-1][1] == _OPEN_END else None


def _strip_flavor_word(body: str) -> str:
    match = _FLAVOR_WORD_RE.match(body)
    return match.group("body") if match else body


def _target_phrase_for_row(phrase: str) -> str:
    """A "choose target <X>" phrase as a row clause names its object: "in
    your graveyard" becomes the pipeline's "from your graveyard"."""
    return re.sub(r"\bin (your|a|an opponent's) graveyard\b", r"from \1 graveyard", phrase)


def _row_variants(body: str, target_phrase: str | None, earlier: list[str]) -> list[str]:
    """The texts a row is read as, most specific first (see the module docstring)."""
    body = _strip_flavor_word(collapsed(body))
    those = _THOSE_TOKENS_RE.fullmatch(body)
    if those is not None:
        for previous in reversed(earlier):
            token = _TOKEN_ROW_RE.fullmatch(_strip_flavor_word(previous))
            if token is not None:
                body = (
                    f"Create {those.group('count')} {token.group('what')} tokens"
                    f"{token.group('rest')}."
                )
                break
        else:
            return []
    if target_phrase is not None and _THAT_NOUN_RE.search(body):
        # "that creature" is the chosen target, never the event's subject:
        # the raw anaphora is not offered as a fallback.
        return [_THAT_NOUN_RE.sub(target_phrase, body, count=1)]
    if _THIS_CARD_RE.search(body):
        return [_THIS_CARD_RE.sub("this card from your graveyard", body, count=1), body]
    return [body]


def _plain_row(text: str) -> RowEffect | None:
    from .effects.dispatch import _ability_effect_or_notice
    from .effects.tokens import _is_notice_only

    inner = _ability_effect_or_notice(text)
    if inner is None or _is_notice_only(inner):
        return None

    def effect(game: Game, ability: AbilityOnStack, exiled_now: list[CardState]) -> None:
        inner(game, ability)

    return effect


def _copy_cast_row(body: str) -> RowEffect | None:
    """A result row "Copy <that card | each card exiled with this ...>. You may
    cast <the copy | any number of the copies>[ by paying {cost} rather than
    paying its mana cost | without paying its mana cost]." - CR 707.12's copy
    made in exile, cast through `Game.may_cast_during_resolution` (one
    question per copy, CR 707.12a), removed again if it was not cast (CR
    707.10a)."""
    match = _COPY_CAST_ROW_RE.fullmatch(collapsed(body))
    if match is None:
        return None
    from ..models.mana import ManaCost
    from .cost import TotalCost
    from .decisions import source_id_of
    from .effects._common import _permanent_id_and_name

    each_exiled = match.group("what").lower() != "that card"
    free = match.group("free") is not None
    alternative = TotalCost(mana=ManaCost.parse(match.group("alt"))) if match.group("alt") else None

    def effect(game: Game, ability: AbilityOnStack, exiled_now: list[CardState]) -> None:
        controller = game.controller_of(ability).username
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        if each_exiled:
            originals = [
                card
                for card in game.cards_exiled_with(ability.source_id, ability.source_stamp)
                if card.zone is Zone.EXILE
            ]
        else:
            originals = [card for card in exiled_now if card.zone is Zone.EXILE]
        copies = []
        for original in originals:
            copy = CardState(
                card=original.card,
                zone=Zone.EXILE,
                controller=controller,
                owner=controller,  # CR 112.2a
                is_copy=True,
            )
            game.exile.append(copy)
            copies.append(copy)
        for copy in copies:
            game.may_cast_during_resolution(
                copy,
                controller,
                prompt=f"cast the copy of {copy.name}",
                source=source_name,
                source_id=source_id_of(ability),
                source_name=source_name,
                rule="CR 707.12",
                pays_mana_cost=not free and alternative is None,
                alternative_cost=alternative,
            )
        for copy in copies:
            if copy.zone is Zone.EXILE and copy in game.exile:
                game.exile.remove(copy)  # CR 707.10a

    return effect


def _search_type_split_row(body: str) -> RowEffect | None:
    """`_SEARCH_TYPE_SPLIT_RE`: the found card of the named type may go onto
    the battlefield; any other find, or a declined one, goes to the hand."""
    match = _SEARCH_TYPE_SPLIT_RE.fullmatch(collapsed(body.replace("\u2019", "'")))
    if match is None:
        return None
    try:
        card_type = Type(match.group("type").lower())
    except ValueError:
        return None
    from .decisions import Decision, DecisionKind, source_id_of

    def effect(game: Game, ability: AbilityOnStack, exiled_now: list[CardState]) -> None:
        controller = game.controller_of(ability).username
        found = game.search_library(
            controller,
            lambda _card: True,
            count=1,
            optional=True,
            shuffle=False,
            source=ability.source_name,
            source_id=source_id_of(ability),
            caused_by=controller,
        )
        player = game.player(controller)
        for card in found:
            if card_type in card.types and game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=controller,
                    prompt=f"put {card.name} onto the battlefield",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                )
            ):
                game.put_onto_battlefield(card, controller)
            else:
                player.add(card, Zone.HAND)
        game.shuffle_library(player)

    return effect


def _any_graveyard_reanimate_row(body: str) -> RowEffect | None:
    """`_ANY_GRAVEYARD_REANIMATE_RE`: the controller picks a card of the type
    from any graveyard as the row resolves and puts it onto the battlefield
    under their control; "When that creature dies, its owner loses the game"
    is a delayed trigger on that object (CR 603.7, CR 104.3e)."""
    match = _ANY_GRAVEYARD_REANIMATE_RE.fullmatch(collapsed(body))
    if match is None:
        return None
    try:
        card_type = Type(match.group("type").lower())
    except ValueError:
        return None
    doom_text = match.group("doom")
    from .dies_this_turn import dies_consequence_effect

    if doom_text is not None and dies_consequence_effect(doom_text) is None:
        return None
    from .decisions import Decision, DecisionKind, source_id_of
    from .delayed import DelayedTrigger, ThatCreatureDiesConsequence
    from .triggers import TriggerEvent

    def effect(game: Game, ability: AbilityOnStack, exiled_now: list[CardState]) -> None:
        controller = game.controller_of(ability).username
        candidates = [
            card
            for player in game.players_in_game
            for card in player.graveyard
            if card_type in card.types
        ]
        if not candidates:
            return
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=f"choose a {card_type.value.lower()} card from any graveyard",
                source=ability.source_name,
                amount=1,
                cards=tuple(card.id for card in candidates),
                source_id=source_id_of(ability),
            )
        )
        by_id = {card.id: card for card in candidates}
        for card_id in chosen or ():
            card = by_id[card_id]
            permanent = game.put_onto_battlefield(card, controller)
            if doom_text is None or permanent.zone is not Zone.BATTLEFIELD:
                continue
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=doom_text,
                    effect=ThatCreatureDiesConsequence(),
                    event=TriggerEvent.DIES,
                    controller=controller,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    subject_id=permanent.id,
                    remaining=1,
                )
            )

    return effect


def read_row(body: str, target_phrase: str | None, earlier: list[str]) -> RowEffect | None:
    """One results-table row's effect, or None when no reading performs it."""
    for text in _row_variants(body, target_phrase, earlier):
        for reader in (_copy_cast_row, _search_type_split_row, _any_graveyard_reanimate_row):
            row = reader(text)
            if row is not None:
                return row
        row = _plain_row(text)
        if row is not None:
            return row
    return None


def _modifier_reader(phrase: str) -> Callable[[Game, str], int] | None:
    """CR 706.2's printed modifier amount: "the number of cards in your hand"
    or anything `count_expression` reads."""
    lowered = collapsed(phrase.lower())
    if lowered in ("the number of cards in your hand", "the number of cards in their hand"):
        return lambda game, controller: len(game.player(controller).hand)
    if lowered.isdigit():
        value = int(lowered)
        return lambda _game, _controller: value
    from .effects.amounts import count_expression

    return count_expression(phrase)


@cache
def roll_table_effect(text: str) -> Any:
    """The results-table ability `text` prints, or None (also None when any
    sentence before the roll, the modifier, the floor clause or any row is
    one this engine does not perform - no half-run table)."""
    if "roll a" not in text.lower() or " | " not in text:
        return None
    from .effects.text import _strip_non_effect_preamble

    match = ROLL_TABLE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    sides = int(match.group("sides"))
    modifier = None
    if match.group("sign"):
        modifier = _modifier_reader(match.group("modifier"))
        if modifier is None:
            return None
    sign = -1 if (match.group("sign") or "").lower() == "subtract" else 1
    rows = split_roll_rows(match.group("rows"), sides, modified=modifier is not None)
    if rows is None:
        return None
    pre_text = match.group("pre").strip()
    pre = None
    target_phrase = None
    choose = _CHOOSE_TARGET_THEN_RE.fullmatch(pre_text)
    if choose is not None:
        from .targeting import profile_for_text

        profile = profile_for_text(f"{choose.group('phrase')}.")
        if not profile.understood or len(profile.requirements) != 1:
            return None
        target_phrase = _target_phrase_for_row(choose.group("phrase"))
    elif pre_text:
        from .effects.dispatch import _ability_effect_or_notice
        from .effects.tokens import _is_notice_only

        pre = _ability_effect_or_notice(pre_text)
        if pre is None or _is_notice_only(pre):
            return None
    floor = None
    if match.group("floor") is not None:
        floor_row = _plain_row(match.group("floor_effect").strip() + ".")
        if floor_row is None:
            return None
        floor = (int(match.group("floor")), floor_row)
    row_effects: list[tuple[int, int, RowEffect]] = []
    earlier: list[str] = []
    for low, high, body in rows:
        row = read_row(body, target_phrase, earlier)
        if row is None:
            return None
        earlier.append(body)
        row_effects.append((low, high, row))
    links_pile = "exiled with this" in match.group("rows").lower()

    def effect(game: Game, ability: AbilityOnStack) -> None:
        from .effects.removal import linked_exile_annotation

        controller = game.controller_of(ability).username
        before = {card.id for card in game.exile}
        if pre is not None:
            pre(game, ability)
        exiled_now = [card for card in game.exile if card.id not in before]
        if links_pile and ability.source_id is not None:
            for card in exiled_now:
                if card.exile_annotation is None and card.zone is Zone.EXILE:
                    card.exile_annotation = linked_exile_annotation(game, ability, card)
        rolled = game.roll_dice(controller, sides)
        if not rolled:
            return
        result = rolled[0]
        if modifier is not None:
            result += sign * modifier(game, controller)  # CR 706.2
        if floor is not None and result <= floor[0]:
            floor[1](game, ability, exiled_now)
        for low, high, row in row_effects:
            if low <= result <= high:
                row(game, ability, exiled_now)
                return

    return effect

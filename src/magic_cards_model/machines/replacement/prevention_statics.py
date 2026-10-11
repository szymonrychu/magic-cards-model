"""A permanent's static damage prevention and damage replacement, read off its
printed paragraph (CR 615.1, CR 614.1a, CR 616.1, CR 120.4).

`parse.py` reads the narrow shapes ("If a source you control would deal damage
to <recipient>, it deals double ... instead", "Prevent all damage that would be
dealt to this creature", "If damage would be dealt to you, prevent that
damage"). This module reads the rest of the family with one small grammar
instead of one regex per card:

- **Object phrases** (`_phrase_test`): who is dealt damage and who deals it -
  "you", "this creature", "enchanted creature", "creature tokens you control",
  "another red source you control", "a red instant or sorcery spell you
  control", "a Lizard, Mouse, Otter, or Raccoon you control", "creatures with
  first strike", "a source you control with an odd mana value", "creatures
  blocking it", "sources with the chosen name" ... Words are characteristics
  (`models.game._continuous._characteristic_word`), read off the damage
  source as `Game._protection_characteristics` computes them (CR 609.7b: the
  source's properties are checked as the damage would be dealt).
- **Event clauses**: "Prevent all [combat|noncombat] damage that would be
  dealt [to R] [by S]", "... that <S> would deal [to R]", "All damage that
  would be dealt to R is dealt to <T> instead" (CR 614.9), "If <S> would deal
  [non|combat] damage [to R], ..." and "If [non|combat] damage would be dealt
  to R [while it has a +1/+1 counter on it], ...", each optionally under a
  leading "During your turn," or "As long as <condition>,".
- **Outcomes**: "prevent that damage", "prevent N / X / all but N / half that
  damage" (CR 615.10, the part prevented per event), "it deals double / twice
  that much / half, rounded down / that much plus N instead" (CR 701.10g), and
  the actions that follow or replace the damage - counters put on or removed,
  cards milled, exiled, drawn, permanents sacrificed, tokens created, and the
  reflexive "when damage is prevented this way, ... deals that much damage"
  (CR 603.12). "That much" is the amount prevented or replaced (CR 615.5).

A paragraph is read whole or not at all: any sentence this does not read
returns nothing, so the permanent is never half-performed (the fail-closed rule
`parse.py` states). Against damage that can't be prevented (CR 615.12) a
prevention effect prevents nothing, but its additional effects that do not
refer to the amount prevented still take place.

`reads_damage_static_line` is what `static_audit/damage_replacement.py` asks.
The module imports `parse` lazily from its callers' side only: `parse.py`
reaches this module from inside `parsed_card_replacements`, never at import.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from math import ceil
from typing import TYPE_CHECKING, Any

from ...models.card import Card, Supertype
from ...models.card_state import CardState, ChoiceKind, TargetKind
from ...models.game._continuous import _characteristic_word
from ...models.token import create_tokens, is_token
from ...models.zone import Zone
from ..combat import source_had_keyword
from ..decisions import Decision, DecisionKind, source_id_of
from . import parse
from .model import CardReplacement, EventKind, ReplaceableEvent

if TYPE_CHECKING:
    from ...models.game import Game

#: A test on one object relative to the permanent carrying the effect: the
#: object is a `Player` or a `CardState` (a permanent, or a spell on the stack).
_Test = Callable[["Game", CardState, Any], bool]
_Gate = Callable[["Game", CardState], bool]
_Action = Callable[["Game", CardState, ReplaceableEvent, "_Outcome"], None]


@dataclass
class _Outcome:
    """What the effect did to this damage event, for the actions that follow:
    `amount` is the damage prevented or replaced ("that much", CR 615.5)."""

    amount: int = 0
    removed: int = 0


# --------------------------------------------------------------------------
# Text normalisation
# --------------------------------------------------------------------------

_ABILITY_WORD_RE = re.compile(r"^[A-Z][A-Za-z' ]{2,30}? [-—–] (?=\S)")
_SELF_NOUN_RE = re.compile(
    r"\bthis (?:creature|permanent|enchantment|artifact|planeswalker|equipment|aura|vehicle"
    r"|land)\b",
    re.IGNORECASE,
)
_NEXT_SENTENCE = re.compile(r"(?<=\.)\s+(?=[A-Z])")


def _normalise(names: Sequence[str], text: str) -> str:
    """The printed paragraph with the ability word stripped and every way the
    permanent names itself (CR 201.5) replaced by "~"."""
    line = _ABILITY_WORD_RE.sub("", text.strip())
    # `_names_of` can hand back a legendary card's first word with its comma.
    for name in sorted({name.strip(", ") for name in names}, key=len, reverse=True):
        line = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", "~", line, flags=re.IGNORECASE)
    line = _SELF_NOUN_RE.sub("~", line)
    return " ".join(line.split())


# --------------------------------------------------------------------------
# Object phrases
# --------------------------------------------------------------------------


def _is_card(obj: Any) -> bool:
    return isinstance(obj, CardState)


def _controller(game: "Game", holder: CardState) -> str:
    return game.controller_of(holder).username


def _you(game: "Game", holder: CardState, obj: Any) -> bool:
    return not _is_card(obj) and obj.username == _controller(game, holder)


def _an_opponent(game: "Game", holder: CardState, obj: Any) -> bool:
    return not _is_card(obj) and obj.username != _controller(game, holder)


def _itself(game: "Game", holder: CardState, obj: Any) -> bool:
    return _is_card(obj) and obj.id == holder.id


def _attached_to(game: "Game", holder: CardState, obj: Any) -> bool:
    """CR 301.5a / CR 303.4b: the object the Equipment or Aura is attached to."""
    return _is_card(obj) and holder.attached_to is not None and holder.attached_to == obj.id


def _enchanted_player(game: "Game", holder: CardState, obj: Any) -> bool:
    """CR 303.4m: "enchanted player" is whoever the Aura is attached to."""
    attachment = getattr(holder, "attachment", None)
    return (
        not _is_card(obj)
        and attachment is not None
        and attachment.kind is TargetKind.PLAYER
        and attachment.username == obj.username
    )


_SPECIAL_PHRASES: dict[str, _Test] = {
    "you": _you,
    "an opponent": _an_opponent,
    "each opponent": _an_opponent,
    "~": _itself,
    "it": _itself,
    "enchanted creature": _attached_to,
    "equipped creature": _attached_to,
    "enchanted permanent": _attached_to,
    "enchanted player": _enchanted_player,
}

#: Words that open a new object phrase after "and" / "or" / a comma, rather
#: than continuing a list inside one ("a Lizard, Mouse, Otter, or Raccoon").
_PHRASE_OPENER_RE = re.compile(
    r"^(?:an? |another |other |you\b|your |that |enchanted |equipped |~|permanents|creatures)",
    re.IGNORECASE,
)
_LIST_SEPARATOR_RE = re.compile(r"(,?\s+and/or\s+|,\s+or\s+|\s+or\s+|\s+and\s+|,\s+)")
_WORD_SEPARATOR_RE = re.compile(r"(\s*,\s*or\s+|\s*,\s*|\s+or\s+|\s+)")

_KEYWORD_QUALIFIER = r"first strike|double strike|flying|deathtouch|lifelink|trample|haste|menace"
#: Trailing qualifiers peeled off a noun phrase, innermost first.
_QUALIFIERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\s+that entered this turn$"), "entered"),
    (re.compile(r"\s+with an? (odd|even) mana value$"), "parity"),
    (re.compile(r"\s+with the chosen name$"), "chosen_name"),
    (re.compile(rf"\s+with ({_KEYWORD_QUALIFIER})$"), "keyword"),
    (re.compile(r"\s+blocking (?:~|it)$"), "blocking_holder"),
    (re.compile(r"\s+you control$"), "yours"),
    (re.compile(r"\s+(?:an opponent|your opponents) controls?$"), "opponents"),
)


def _atom(word: str) -> _Test | None:
    """One word of a noun phrase as a test on the object, or None when it names
    nothing this reads (the phrase then fails closed)."""
    if word in ("source", "sources"):
        return lambda game, holder, obj: _is_card(obj)
    if word in ("spell", "spells"):
        return lambda game, holder, obj: _is_card(obj) and obj.zone is Zone.STACK
    if word in ("permanent", "permanents"):
        return lambda game, holder, obj: _is_card(obj) and obj.zone is Zone.BATTLEFIELD
    if word in ("player", "players"):
        return lambda game, holder, obj: not _is_card(obj)
    if word in ("opponent", "opponents"):
        return _an_opponent
    if word in ("token", "tokens"):
        return lambda game, holder, obj: _is_card(obj) and is_token(obj)
    if word == "nontoken":
        return lambda game, holder, obj: _is_card(obj) and not is_token(obj)
    if word == "attacking":
        return lambda game, holder, obj: _is_card(obj) and game.is_attacking(obj)
    if word == "blocking":
        return lambda game, holder, obj: _is_card(obj) and game.is_blocking(obj)
    if word == "unblocked":
        return lambda game, holder, obj: (
            _is_card(obj) and game.is_attacking(obj) and not game.is_blocked(obj)
        )
    characteristic = _characteristic_word(word)
    if characteristic is None:
        return None
    return lambda game, holder, obj: (
        _is_card(obj) and characteristic(game._protection_characteristics(obj))
    )


def _qualifier_test(kind: str, arg: str | None) -> _Test:
    if kind == "entered":
        return lambda game, holder, obj: _is_card(obj) and game._entered_this_turn(obj)
    if kind == "parity":
        odd = arg == "odd"
        return lambda game, holder, obj: (
            _is_card(obj)
            and (int(game._protection_characteristics(obj).mana_value) % 2 == 1) == odd
        )
    if kind == "chosen_name":

        def chosen(game: "Game", holder: CardState, obj: Any) -> bool:
            choice = holder.choice
            if choice is None or choice.kind is not ChoiceKind.CARD_NAME or not _is_card(obj):
                return False
            faces = {part.strip().lower() for part in obj.name.split("//")}
            return choice.value.strip().lower() in faces | {obj.name.lower()}

        return chosen
    if kind == "keyword":
        return lambda game, holder, obj: _is_card(obj) and source_had_keyword(obj, arg or "", game)
    if kind == "blocking_holder":

        def blocking_holder(game: "Game", holder: CardState, obj: Any) -> bool:
            attack = game.combat.attack_by(holder.id)
            return _is_card(obj) and attack is not None and obj.id in attack.blockers

        return blocking_holder
    if kind == "yours":
        return lambda game, holder, obj: (
            _is_card(obj) and game.controller_of(obj).username == _controller(game, holder)
        )
    return lambda game, holder, obj: (
        _is_card(obj) and game.controller_of(obj).username != _controller(game, holder)
    )


def _noun_phrase_test(phrase: str) -> _Test | None:
    body = phrase.strip().lower()
    tests: list[_Test] = []
    determiner = re.match(r"^(?:an?|the|another|other) ", body)
    if determiner is not None:
        if determiner.group(0).strip() in ("another", "other"):
            tests.append(lambda game, holder, obj: not _itself(game, holder, obj))
        body = body[determiner.end() :]
    peeling = True
    while peeling:
        peeling = False
        for pattern, kind in _QUALIFIERS:
            found = pattern.search(body)
            if found is not None:
                tests.append(_qualifier_test(kind, found.group(1) if found.groups() else None))
                body = body[: found.start()]
                peeling = True
    if not body:
        return None
    parts = _WORD_SEPARATOR_RE.split(body)
    groups: list[list[_Test]] = []
    for index in range(0, len(parts), 2):
        atom = _atom(parts[index])
        if atom is None:
            return None
        joiner = parts[index - 1] if index else ""
        if index and ("or" in joiner or "," in joiner):
            groups[-1].append(atom)
        else:
            groups.append([atom])
    for group in groups:
        tests.append(
            lambda game, holder, obj, group=tuple(group): any(
                each(game, holder, obj) for each in group
            )
        )

    def matches(game: "Game", holder: CardState, obj: Any) -> bool:
        return all(test(game, holder, obj) for test in tests)

    return matches


def _split_phrases(text: str) -> list[str]:
    parts = _LIST_SEPARATOR_RE.split(text.strip())
    phrases = [parts[0]]
    for separator, piece in zip(parts[1::2], parts[2::2], strict=True):
        if _PHRASE_OPENER_RE.match(piece) or phrases[-1].strip().lower() == "you":
            phrases.append(piece)
        else:
            phrases[-1] += separator + piece
    return phrases


def _phrase_test(phrase: str) -> _Test | None:
    """The test a printed object phrase puts on a damage source or recipient,
    alternatives joined by "and", "or" or "and/or" (any one matches)."""
    lowered = " ".join(phrase.strip().lower().split()).replace("one or more ", "")
    tests: list[_Test] = []
    for part in _split_phrases(lowered):
        test = _SPECIAL_PHRASES.get(part.strip()) or _noun_phrase_test(part)
        if test is None:
            return None
        tests.append(test)
    if len(tests) == 1:
        return tests[0]
    return lambda game, holder, obj: any(test(game, holder, obj) for test in tests)


# --------------------------------------------------------------------------
# Gates ("During your turn,", "As long as <condition>,", "while it has ...")
# --------------------------------------------------------------------------


def _your_turn(game: "Game", holder: CardState) -> bool:
    return game.turn is not None and game.turn.active_player == _controller(game, holder)


def _untapped(game: "Game", holder: CardState) -> bool:
    return not holder.tapped


def _condition_gate(condition: str) -> _Gate | None:
    """CR 604.2: the effect exists only while the condition holds, asked each
    time damage would be dealt (CR 611.3a)."""
    lowered = condition.strip().lower()
    if lowered == "~ is untapped":
        return _untapped
    spelled = condition.replace("~", "this permanent")
    if not parse.condition_claims(spelled):
        return None
    return lambda game, holder: bool(
        game.condition_holds(_controller(game, holder), spelled, holder)
    )


_COUNTER_KIND = r"[+-]\d+/[+-]\d+|[a-z]+"
_WHILE_COUNTER_RE = re.compile(
    rf"^(?:~|it) has an? (?P<kind>{_COUNTER_KIND}) counter on (?:it|~)$", re.IGNORECASE
)


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

_EACH_PREVENTED = r"(?P<each> for each 1 damage (?:prevented|replaced) this way)?"
_SELF_REFERENCE = r"(?:~|it|him|her|them)"
_PUT_COUNTERS_RE = re.compile(
    rf"^put (?P<count>an?|that many|\d+) (?P<kind>{_COUNTER_KIND}) counters? on "
    rf"(?P<on>{_SELF_REFERENCE}|that creature){_EACH_PREVENTED}$",
    re.IGNORECASE,
)
_REMOVE_COUNTERS_RE = re.compile(
    rf"^remove (?P<count>an?|that many) (?P<kind>{_COUNTER_KIND}) counters? from "
    rf"{_SELF_REFERENCE}$",
    re.IGNORECASE,
)
_MILL_RE = re.compile(
    r"^(?P<who>that player|each opponent|you) mills? that many cards$", re.IGNORECASE
)
_SACRIFICE_RE = re.compile(r"^sacrifice that many permanents$", re.IGNORECASE)
_EXILE_TOP_RE = re.compile(r"^exile that many cards from the top of your library$", re.IGNORECASE)
_EXILE_GRAVEYARD_RE = re.compile(
    r"^exile a card from your graveyard for each 1 damage prevented this way$", re.IGNORECASE
)
_DRAW_RE = re.compile(
    r"^(?P<who>the source's controller|you) draws? cards? equal to the damage "
    r"(?:prevented|replaced) this way$",
    re.IGNORECASE,
)
_GAIN_LIFE_RE = re.compile(r"^you gain life equal to the damage prevented this way$", re.IGNORECASE)
_CREATE_TOKENS_RE = re.compile(
    rf"^create (?P<count>an?|that many|\d+) (?P<descriptor>.+?){_EACH_PREVENTED}$",
    re.IGNORECASE,
)
_REFLEXIVE_PREVENTED_RE = re.compile(
    r"^when damage is prevented this way, ~ deals that much damage to any other target$",
    re.IGNORECASE,
)
_REFLEXIVE_REMOVED_RE = re.compile(
    r"^when one or more counters are removed from ~ this way, it deals that much damage "
    r"to any target$",
    re.IGNORECASE,
)


def _times(count: str, each: str | None) -> Callable[[_Outcome], int] | None:
    """How many a "put a / that many / N ... [for each 1 damage prevented]"
    counts: "that many" is the damage prevented (CR 615.5), "a" is one per
    damage prevented under "for each 1 damage prevented this way"."""
    lowered = count.lower()
    if lowered == "that many":
        return None if each else (lambda outcome: outcome.amount)
    base = 1 if lowered in ("a", "an") else parse.parse_count(lowered)
    if base is None:
        return None
    if each:
        return lambda outcome: base * outcome.amount
    return lambda outcome: base


def _counter_target(game: "Game", holder: CardState, event: ReplaceableEvent, on: str) -> Any:
    return event.card if on.lower() == "that creature" else holder


def _action(text: str) -> _Action | None:
    """One instruction that follows or replaces the damage, or None."""
    clause = text.strip().rstrip(".")
    found = _PUT_COUNTERS_RE.fullmatch(clause)
    if found is not None:
        count = _times(found.group("count"), found.group("each"))
        if count is None:
            return None
        kind = found.group("kind").lower()
        on = found.group("on")

        def put_counters(
            game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
        ) -> None:
            target = _counter_target(game, holder, event, on)
            number = count(outcome)
            if target is not None and number > 0:
                game.add_counters(target, kind, number, putter=_controller(game, holder))

        return put_counters
    found = _REMOVE_COUNTERS_RE.fullmatch(clause)
    if found is not None:
        count = _times(found.group("count"), None)
        if count is None:
            return None
        kind = found.group("kind").lower()

        def remove_counters(
            game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
        ) -> None:
            number = min(count(outcome), holder.counter_count(kind))
            if number > 0:
                holder.remove_counters(kind, number)
                outcome.removed += number

        return remove_counters
    found = _MILL_RE.fullmatch(clause)
    if found is not None:
        who = found.group("who").lower()

        def mill(
            game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
        ) -> None:
            if who == "that player":
                players = [] if event.player is None else [event.player]
            elif who == "you":
                players = [game.controller_of(holder)]
            else:
                players = [
                    each
                    for each in game.players_in_game
                    if each.username != _controller(game, holder)
                ]
            for each in players:
                parse._mill(game, each, outcome.amount)

        return mill
    if _SACRIFICE_RE.fullmatch(clause):
        return _sacrifice_that_many
    if _EXILE_TOP_RE.fullmatch(clause):

        def exile_top(
            game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
        ) -> None:
            library = game.controller_of(holder).library
            game.exile_cards(list(library[: outcome.amount]))

        return exile_top
    if _EXILE_GRAVEYARD_RE.fullmatch(clause):
        return _exile_from_graveyard
    found = _DRAW_RE.fullmatch(clause)
    if found is not None:
        sources_controller = found.group("who").lower() != "you"

        def draw(
            game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
        ) -> None:
            if sources_controller:
                if event.source is None:
                    return
                drawer = game.controller_of(event.source)
            else:
                drawer = game.controller_of(holder)
            if outcome.amount > 0:
                game.draw_cards(drawer, outcome.amount)

        return draw
    if _GAIN_LIFE_RE.fullmatch(clause):

        def gain_life(
            game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
        ) -> None:
            if outcome.amount > 0:
                game.gain_life(_controller(game, holder), outcome.amount)

        return gain_life
    found = _CREATE_TOKENS_RE.fullmatch(clause)
    if found is not None:
        count = _times(found.group("count"), found.group("each"))
        definition = parse._read_token_descriptor(found.group("descriptor"))
        if count is None or definition is None:
            return None

        def create(
            game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
        ) -> None:
            number = count(outcome)
            if number > 0:
                create_tokens(game, definition, _controller(game, holder), number)

        return create
    if _REFLEXIVE_PREVENTED_RE.fullmatch(clause):
        return _reflexive_damage("any other target", removed=False)
    if _REFLEXIVE_REMOVED_RE.fullmatch(clause):
        return _reflexive_damage("any target", removed=True)
    return None


def _reflexive_damage(targets: str, *, removed: bool) -> _Action:
    """CR 603.12: "When damage is prevented this way, ... deals that much damage
    to any other target." goes on the stack as a reflexive trigger."""

    def trigger(
        game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
    ) -> None:
        from ..delayed import ReflexiveWhenYouDoConsequence

        amount = outcome.removed if removed else outcome.amount
        if amount <= 0:
            return
        game.create_reflexive_trigger(
            text=f"When you do, this permanent deals {amount} damage to {targets}.",
            controller=_controller(game, holder),
            source_id=holder.id,
            source_name=holder.name,
            callback=ReflexiveWhenYouDoConsequence(),
        )

    return trigger


def _choose_cards(
    game: "Game", holder: CardState, candidates: list[CardState], count: int, prompt: str
) -> list[CardState]:
    """CR 608.2d: the controller chooses `count` of `candidates` (all of them
    when there are no more than that)."""
    if count >= len(candidates):
        return list(candidates)
    answer = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=_controller(game, holder),
            prompt=prompt,
            source=holder.name,
            source_id=source_id_of(holder),
            amount=count,
            cards=tuple(candidate.id for candidate in candidates),
        )
    )
    chosen = tuple(answer) if isinstance(answer, (tuple, list)) else ()
    by_id = {candidate.id: candidate for candidate in candidates}
    return [by_id[card_id] for card_id in chosen if card_id in by_id]


def _sacrifice_that_many(
    game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
) -> None:
    controller = _controller(game, holder)
    candidates = [
        permanent
        for permanent in game.battlefield
        if game.controller_of(permanent).username == controller
    ]
    for permanent in _choose_cards(
        game, holder, candidates, outcome.amount, f"sacrifice {outcome.amount} permanents"
    ):
        game.sacrifice(permanent)


def _exile_from_graveyard(
    game: "Game", holder: CardState, event: ReplaceableEvent, outcome: _Outcome
) -> None:
    graveyard = list(game.controller_of(holder).graveyard)
    chosen = _choose_cards(
        game,
        holder,
        graveyard,
        min(outcome.amount, len(graveyard)),
        f"exile {outcome.amount} cards from your graveyard",
    )
    game.exile_cards(chosen)


# --------------------------------------------------------------------------
# Outcomes: what happens to the damage
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Outcomes:
    """How the damage changes (`prevent` or `scale`) and what else happens."""

    prevention: bool
    #: Of `amount` damage, how much this prevents or the new amount; None leaves it.
    change: Callable[["Game", CardState, int], int]
    may: bool = False
    actions: tuple[_Action, ...] = ()


_PREVENT_N_RE = re.compile(
    r"^prevent (?P<n>\w+) of that damage$|"
    r"^prevent (?P<n2>\w+) damage that (?:source|spell|creature) would deal to that "
    r"(?:permanent or player|player or permanent)$",
    re.IGNORECASE,
)
_PREVENT_X_RE = re.compile(
    r"^(?P<may>you may )?prevent x of that damage, where x is (?P<expr>.+)$", re.IGNORECASE
)
_PREVENT_ALL_BUT_RE = re.compile(r"^prevent all but (?P<n>\w+) of that damage$", re.IGNORECASE)
_PREVENT_HALF_RE = re.compile(
    r"^prevent half that damage, rounded (?P<direction>up|down)$", re.IGNORECASE
)
_SCALE_TARGET = (
    r"(?:,? to (?:that (?:permanent or player|player or permanent|player|permanent)|you|~|"
    r"equipped creature|enchanted creature|enchanted player))?"
)
_SCALE_RE = re.compile(
    rf"^(?:it|that source|~) deals (?P<how>double that damage|twice that much damage|"
    rf"triple that damage|half that damage, rounded (?P<direction>down|up)|"
    rf"that much damage plus (?P<plus>\w+|an amount of damage equal to (?P<expr>.+?)))"
    rf"{_SCALE_TARGET}$",
    re.IGNORECASE,
)
_SPLIT_ACTIONS_RE = re.compile(r",? and |, ")


def _amount_reader(expression: str) -> Callable[["Game", CardState], int] | None:
    from ..effects.amounts import amount_expression

    reader = amount_expression(expression.replace("~", "this permanent"))
    if reader is None:
        return None
    return lambda game, holder: reader(game, _controller(game, holder), holder, 0)


def _read_outcomes(out: str, *, instead: bool) -> _Outcomes | None:
    """The OUT half of "If <event>, <out>": a prevention (with optional
    follow-up actions) or a replacement ("... instead")."""
    out = out.strip().rstrip(".")
    found = _SCALE_RE.fullmatch(out)
    if found is not None and instead:
        how = found.group("how").lower()
        if found.group("plus") is not None:
            if found.group("expr") is not None:
                reader = _amount_reader(found.group("expr"))
                if reader is None:
                    return None
                return _Outcomes(False, lambda game, holder, amount: amount + reader(game, holder))
            plus = parse.parse_count(found.group("plus"))
            if plus is None:
                return None
            return _Outcomes(False, lambda game, holder, amount: amount + plus)
        if how.startswith("half"):
            if found.group("direction").lower() == "down":
                return _Outcomes(False, lambda game, holder, amount: amount // 2)
            return _Outcomes(False, lambda game, holder, amount: ceil(amount / 2))
        factor = 3 if how.startswith("triple") else 2
        return _Outcomes(False, lambda game, holder, amount: amount * factor)
    found = _PREVENT_X_RE.fullmatch(out)
    if found is not None:
        reader = _amount_reader(found.group("expr"))
        if reader is None:
            return None
        return _Outcomes(
            True,
            lambda game, holder, amount: min(reader(game, holder), amount),
            may=found.group("may") is not None,
        )
    found = _PREVENT_N_RE.fullmatch(out)
    if found is not None:
        n = parse.parse_count(found.group("n") or found.group("n2"))
        if n is None:
            return None
        return _Outcomes(True, lambda game, holder, amount: min(n, amount))
    found = _PREVENT_ALL_BUT_RE.fullmatch(out)
    if found is not None:
        n = parse.parse_count(found.group("n"))
        if n is None:
            return None
        return _Outcomes(True, lambda game, holder, amount: max(amount - n, 0))
    found = _PREVENT_HALF_RE.fullmatch(out)
    if found is not None:
        if found.group("direction").lower() == "up":
            return _Outcomes(True, lambda game, holder, amount: ceil(amount / 2))
        return _Outcomes(True, lambda game, holder, amount: amount // 2)
    clauses = [clause for clause in _SPLIT_ACTIONS_RE.split(out) if clause.strip()]
    if not clauses:
        return None
    prevention = clauses[0].strip().lower() == "prevent that damage"
    if not prevention and not instead:
        return None
    actions: list[_Action] = []
    for clause in clauses[1:] if prevention else clauses:
        action = _action(clause)
        if action is None:
            return None
        actions.append(action)
    if prevention:
        return _Outcomes(True, lambda game, holder, amount: amount, actions=tuple(actions))
    return _Outcomes(True, lambda game, holder, amount: amount, actions=tuple(actions))


# --------------------------------------------------------------------------
# The paragraph reader
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Read:
    """A paragraph read whole. `replacement` is None for a "can't be prevented"
    static, which `unpreventable_source` serves instead."""

    replacement: CardReplacement | None = None
    unpreventable_source: _Test | None = None
    unpreventable_combat_only: bool = False


_AS_LONG_AS_RE = re.compile(
    r"^as long as (?P<condition>.+?), (?P<rest>(?:if|all|prevent|combat|damage) .+)$",
    re.IGNORECASE,
)
_DURING_YOUR_TURN_RE = re.compile(r"^during your turn, (?P<rest>.+)$", re.IGNORECASE)
_PREVENT_ALL_RE = re.compile(
    r"^prevent all (?P<kind>combat |noncombat )?damage that (?P<body>.+)$", re.IGNORECASE
)
_REDIRECT_RE = re.compile(
    r"^all (?P<kind>combat |noncombat )?damage that would be dealt to (?P<recipient>.+?)"
    r"(?: by (?P<source>.+?))? is dealt to (?P<to>.+?) instead$",
    re.IGNORECASE,
)
_CANT_BE_PREVENTED_RE = re.compile(
    r"^(?P<kind>combat |noncombat )?damage that would be dealt by (?P<source>.+?) "
    r"can't be prevented$",
    re.IGNORECASE,
)
_IF_RE = re.compile(r"^if (?P<head>.+?\bwould\b[^,]*), (?P<out>.+)$", re.IGNORECASE)
_EVENT_DEAL_RE = re.compile(
    r"^(?P<source>.+?) would deal (?P<kind>combat |noncombat )?damage(?: to (?P<recipient>.+))?$",
    re.IGNORECASE,
)
_EVENT_DEALT_RE = re.compile(
    r"^(?P<kind>combat |noncombat )?damage would be dealt to (?P<recipient>.+?)"
    r"(?: while (?P<while>.+))?$",
    re.IGNORECASE,
)
#: "If this creature would be dealt damage, ..." (Unbreathing Horde): the
#: recipient first, the damage kind after the verb.
_EVENT_RECIPIENT_DEALT_RE = re.compile(
    r"^(?P<recipient>.+?) would be dealt (?P<kind>combat |noncombat )?damage$", re.IGNORECASE
)
_PREVENT_ALL_BODY_RES = (
    re.compile(r"^would be dealt to and dealt by (?P<both>.+)$", re.IGNORECASE),
    re.compile(r"^would be dealt to (?P<recipient>.+?) by (?P<source>.+)$", re.IGNORECASE),
    re.compile(r"^would be dealt to (?P<recipient>.+)$", re.IGNORECASE),
    re.compile(r"^would be dealt by (?P<source>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<source>.+?) would deal(?: to (?P<recipient>.+))?$", re.IGNORECASE),
)
_DURING_YOUR_TURN_SUFFIX_RE = re.compile(r"^(?P<body>.+?) during your turn$", re.IGNORECASE)
_LEVEL_HEADER_RE = re.compile(r"^LEVEL (?P<low>\d+)(?:-(?P<high>\d+)|(?P<plus>\+))$")


def _combat_matches(kind: str | None, event: ReplaceableEvent) -> bool:
    word = (kind or "").strip().lower()
    return not ((word == "combat" and not event.combat) or (word == "noncombat" and event.combat))


def _event_applies(
    *,
    kind: str | None,
    recipient: _Test | None,
    source: _Test | None,
    gates: Sequence[_Gate],
    destination: Callable[["Game", CardState], Any] | None = None,
) -> Callable[["Game", CardState, ReplaceableEvent], bool]:
    def applies(game: "Game", holder: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.DAMAGE or event.amount <= 0:
            return False
        if not _combat_matches(kind, event):
            return False
        if any(not gate(game, holder) for gate in gates):
            return False
        obj = event.player if event.player is not None else event.card
        if recipient is not None and (obj is None or not recipient(game, holder, obj)):
            return False
        if source is not None and (event.source is None or not source(game, holder, event.source)):
            return False
        if destination is not None:
            target = destination(game, holder)
            return target is not None and not (
                event.card is not None and event.card.id == target.id
            )
        return True

    return applies


def _redirect_destination(phrase: str) -> Callable[["Game", CardState], Any] | None:
    lowered = phrase.strip().lower()
    if lowered in ("~", "it"):
        return lambda game, holder: holder
    if lowered in ("enchanted creature", "equipped creature"):

        def attached(game: "Game", holder: CardState) -> CardState | None:
            host = game.find_by_id(holder.attached_to) if holder.attached_to is not None else None
            if isinstance(host, CardState) and host.zone is Zone.BATTLEFIELD:
                return host
            return None

        return attached
    return None


def _prevent_all_effect(
    applies: Callable[["Game", CardState, ReplaceableEvent], bool], actions: Sequence[_Action]
) -> tuple[Callable[..., None], bool]:
    return _prevention_apply(lambda game, holder, amount: amount, False, tuple(actions)), True


def _prevention_apply(
    change: Callable[["Game", CardState, int], int], may: bool, actions: tuple[_Action, ...]
) -> Callable[["Game", CardState | None, ReplaceableEvent], None]:
    def apply(game: "Game", holder: CardState | None, event: ReplaceableEvent) -> None:
        if holder is None:
            return
        if may and not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=_controller(game, holder),
                prompt=f"prevent some of that damage ({holder.name}, CR 615.1)",
                source=holder.name,
                source_id=source_id_of(holder),
            )
        ):
            return
        unpreventable = game.damage_cant_be_prevented(event) is not None
        prevented = 0 if unpreventable else min(change(game, holder, event.amount), event.amount)
        event.amount -= prevented
        outcome = _Outcome(amount=prevented)
        for action in actions:
            action(game, holder, event, outcome)

    return apply


def _replacement_apply(
    outcomes: _Outcomes,
) -> Callable[["Game", CardState | None, ReplaceableEvent], None]:
    def apply(game: "Game", holder: CardState | None, event: ReplaceableEvent) -> None:
        if holder is None:
            return
        amount = event.amount
        if outcomes.actions:
            event.amount = 0
            outcome = _Outcome(amount=amount)
            for action in outcomes.actions:
                action(game, holder, event, outcome)
        else:
            event.amount = max(outcomes.change(game, holder, amount), 0)

    return apply


def _read_if(
    sentence: str, gates: list[_Gate], riders: Sequence[_Action]
) -> tuple[Callable[..., bool], Callable[..., None], bool] | None:
    found = _IF_RE.match(sentence)
    if found is None:
        return None
    head, out = found.group("head"), found.group("out")
    event_found = _EVENT_DEAL_RE.fullmatch(head)
    source_test: _Test | None = None
    recipient_test: _Test | None = None
    kind: str | None
    if event_found is not None:
        kind = event_found.group("kind")
        subject = event_found.group("source").strip()
        if subject.lower() not in ("a source", "any source"):
            source_test = _phrase_test(subject)
            if source_test is None:
                return None
        if event_found.group("recipient"):
            recipient_test = _phrase_test(event_found.group("recipient"))
            if recipient_test is None:
                return None
    else:
        event_found = _EVENT_DEALT_RE.fullmatch(head) or _EVENT_RECIPIENT_DEALT_RE.fullmatch(head)
        if event_found is None:
            return None
        kind = event_found.group("kind")
        recipient_test = _phrase_test(event_found.group("recipient"))
        if recipient_test is None:
            return None
        if "while" in event_found.re.groupindex and event_found.group("while"):
            counter = _WHILE_COUNTER_RE.fullmatch(event_found.group("while").strip())
            if counter is None:
                return None
            counter_kind = counter.group("kind").lower()
            gates = [*gates, lambda game, holder: holder.counter_count(counter_kind) > 0]
    instead = bool(re.search(r"(?:^|\s)instead$", out, re.IGNORECASE)) or out.lower().startswith(
        "instead "
    )
    cleaned = re.sub(r"^instead,?\s+|\s+instead$", "", out.strip().rstrip("."), flags=re.IGNORECASE)
    outcomes = _read_outcomes(cleaned, instead=instead)
    if outcomes is None:
        return None
    applies = _event_applies(kind=kind, recipient=recipient_test, source=source_test, gates=gates)
    if outcomes.prevention and not (instead and outcomes.actions):
        actions = (*outcomes.actions, *riders)
        return applies, _prevention_apply(outcomes.change, outcomes.may, actions), True
    if riders:
        return None  # a replacement's riders have no "prevented this way" to refer to
    return applies, _replacement_apply(outcomes), False


def _read_prevent_all(
    match: re.Match[str], gates: list[_Gate], riders: Sequence[_Action]
) -> tuple[Callable[..., bool], Callable[..., None], bool] | None:
    body = match.group("body").strip()
    suffix = _DURING_YOUR_TURN_SUFFIX_RE.fullmatch(body)
    if suffix is not None:
        gates = [*gates, _your_turn]
        body = suffix.group("body")
    recipient_test: _Test | None = None
    source_test: _Test | None = None
    for pattern in _PREVENT_ALL_BODY_RES:
        found = pattern.fullmatch(body)
        if found is None:
            continue
        groups = found.groupdict()
        if groups.get("both"):
            both = _phrase_test(groups["both"])
            if both is None:
                return None
            recipient_test = source_test = None
            applies_to = both
            kind = match.group("kind")

            def either(
                game: "Game", holder: CardState, event: ReplaceableEvent, both: _Test = both
            ) -> bool:
                obj = event.player if event.player is not None else event.card
                return (obj is not None and both(game, holder, obj)) or (
                    event.source is not None and both(game, holder, event.source)
                )

            def applies(
                game: "Game",
                holder: CardState,
                event: ReplaceableEvent,
                either=either,
                kind=kind,
                gates=tuple(gates),
            ) -> bool:
                return (
                    event.kind is EventKind.DAMAGE
                    and event.amount > 0
                    and _combat_matches(kind, event)
                    and all(gate(game, holder) for gate in gates)
                    and either(game, holder, event)
                )

            del applies_to
            return applies, _prevention_apply(lambda g, h, a: a, False, tuple(riders)), True
        if groups.get("recipient"):
            recipient_test = _phrase_test(groups["recipient"])
            if recipient_test is None:
                return None
        if groups.get("source"):
            source_test = _phrase_test(groups["source"])
            if source_test is None:
                return None
        break
    else:
        return None
    applies = _event_applies(
        kind=match.group("kind"), recipient=recipient_test, source=source_test, gates=gates
    )
    return applies, _prevention_apply(lambda g, h, a: a, False, tuple(riders)), True


def _read_redirect(
    match: re.Match[str], gates: list[_Gate], riders: Sequence[_Action]
) -> tuple[Callable[..., bool], Callable[..., None], bool] | None:
    if riders:
        return None
    recipient = _phrase_test(match.group("recipient"))
    source = _phrase_test(match.group("source")) if match.group("source") else None
    destination = _redirect_destination(match.group("to"))
    if recipient is None or destination is None or (match.group("source") and source is None):
        return None
    applies = _event_applies(
        kind=match.group("kind"),
        recipient=recipient,
        source=source,
        gates=gates,
        destination=destination,
    )

    def apply(game: "Game", holder: CardState | None, event: ReplaceableEvent) -> None:
        """CR 614.9's redirection, as `parse._redirect_damage_to_the_source`
        stands it in: the original event is zeroed (CR 614.6) and the new
        recipient is dealt the damage as its own event, so it stays subject to
        that recipient's own prevention and replacement effects."""
        if holder is None:
            return
        target = destination(game, holder)
        amount = event.amount
        event.amount = 0
        if target is not None and amount > 0:
            game.deal_damage(target, amount, source=event.source)

    return applies, apply, False


def _read_paragraph(names: Sequence[str], text: str) -> _Read | None:
    """One printed paragraph read whole, or None (fail closed)."""
    if "damage" not in text.lower():
        return None
    line = _normalise(names, text)
    gates: list[_Gate] = []
    found = _DURING_YOUR_TURN_RE.match(line)
    if found is not None:
        gates.append(_your_turn)
        line = found.group("rest")
    found = _AS_LONG_AS_RE.match(line)
    if found is not None:
        gate = _condition_gate(found.group("condition"))
        if gate is None:
            return None
        gates.append(gate)
        line = found.group("rest")
    sentences = [sentence.strip().rstrip(".") for sentence in _NEXT_SENTENCE.split(line)]
    main, rider_sentences = sentences[0], sentences[1:]
    riders: list[_Action] = []
    for sentence in rider_sentences:
        action = _action(sentence)
        if action is None:
            return None
        riders.append(action)
    found = _CANT_BE_PREVENTED_RE.fullmatch(main)
    if found is not None and not riders and not gates and found.group("kind") != "noncombat ":
        source = _phrase_test(found.group("source"))
        if source is None:
            return None
        return _Read(
            unpreventable_source=source,
            unpreventable_combat_only=(found.group("kind") or "").strip().lower() == "combat",
        )
    read: tuple[Callable[..., bool], Callable[..., None], bool] | None = None
    found = _PREVENT_ALL_RE.fullmatch(main)
    if found is not None:
        read = _read_prevent_all(found, gates, riders)
    else:
        found = _REDIRECT_RE.fullmatch(main)
        if found is not None:
            read = _read_redirect(found, gates, riders)
        elif main.lower().startswith("if "):
            read = _read_if(main, gates, riders)
    if read is None:
        return None
    applies, apply, prevention = read
    return _Read(
        replacement=CardReplacement(
            label=text.strip(), applies=applies, apply=apply, prevention=prevention
        )
    )


# --------------------------------------------------------------------------
# Public surface
# --------------------------------------------------------------------------

_CACHE: dict[tuple[tuple[str, ...], str], _Read | None] = {}


def _read_cached(card: Card, names: tuple[str, ...], text: str) -> _Read | None:
    key = (names, text)
    if key not in _CACHE:
        _CACHE[key] = _read_paragraph(names, text)
    return _CACHE[key]


def _level_gate(low: int, high: int | None) -> _Gate:
    return lambda game, holder: (
        low <= holder.counter_count("level")
        and (high is None or holder.counter_count("level") <= high)
    )


def _claimed_elsewhere(card: Card, line: str) -> bool:
    """A line `parse` already performs, which must not apply twice."""
    return parse.performs_static_line(card, line)


def damage_static_replacements(card: Card, lines: Sequence[str]) -> list[CardReplacement]:
    """Every damage prevention or replacement paragraph among `lines` that this
    module reads whole (a level-up card's `LEVEL a-b` header gates the lines
    under it, CR 711.2)."""
    names = parse._names_of(card)
    found: list[CardReplacement] = []
    level: tuple[int, int | None] | None = None
    for line in lines:
        header = _LEVEL_HEADER_RE.match(line.strip())
        if header is not None:
            high = header.group("high")
            level = (int(header.group("low")), int(high) if high else None)
            continue
        if "damage" not in line.lower() or "\n" in line:
            continue
        read = _read_cached(card, names, line)
        if read is None or read.replacement is None or _claimed_elsewhere(card, line):
            continue
        replacement = read.replacement
        if level is not None:
            gate = _level_gate(*level)
            inner = replacement.applies
            replacement = CardReplacement(
                label=replacement.label,
                applies=lambda game, holder, event, inner=inner, gate=gate: (
                    gate(game, holder) and inner(game, holder, event)
                ),
                apply=replacement.apply,
                prevention=replacement.prevention,
            )
        found.append(replacement)
    return found


def reads_damage_static_line(card: Card, line: str) -> bool:
    """Whether this module reads the whole paragraph - `static_audit`'s question."""
    if "damage" not in line.lower():
        return False
    read = _read_cached(card, parse._names_of(card), line)
    return read is not None and not _claimed_elsewhere(card, line)


def unpreventable_source(card: Card, line: str) -> tuple[_Test, bool] | None:
    """A "Damage that would be dealt by <S> can't be prevented." static as the
    source test and whether it is limited to combat damage (CR 615.12), or None."""
    if "can't be prevented" not in line.lower():
        return None
    read = _read_cached(card, parse._names_of(card), line)
    if read is None or read.unpreventable_source is None:
        return None
    return read.unpreventable_source, read.unpreventable_combat_only


__all__ = [
    "damage_static_replacements",
    "reads_damage_static_line",
    "unpreventable_source",
]

_ = (Supertype, field)

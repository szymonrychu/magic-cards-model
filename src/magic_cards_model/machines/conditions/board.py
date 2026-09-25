"""Board conditions: what is on the battlefield, who controls it, and how much
of it there is (CR 613.5: every count reads the computed board).

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps. Counts go
through `magic_cards_model.numbers`; qualities through `models/game.py`'s own
`_characteristic_word`, extended here by the object-state words a count of
permanents is printed with.

A reader claims a clause only when every word of its quality is read
(`_ReadableTemplate`): "you control a frobnicated creature" is left unclaimed,
so it fails closed with a notice rather than being answered False.

Rules verified with `mise run rules:find`:

- CR 613.5: "The application of continuous effects as described by the layer
  system is continually and automatically performed by the game."
- CR 111.1: a token is a marker used to represent a permanent that isn't
  represented by a card - "token"/"nontoken" is asked of the object itself,
  not of its characteristics.
- CR 108.3: "The owner of a card in the game is the player who started the
  game with it in their deck"; CR 111.2 makes a token's owner the player
  under whose control it was created - "permanents you don't own".
- CR 700.9: "A permanent is modified if it has one or more counters on it
  (see rule 122), if it is equipped (see rule 301.5), or if it is enchanted
  by an Aura that is controlled by that permanent's controller (see rule
  303.4)."
- CR 700.12: "The term outlaw refers to an object that has the Assassin,
  Mercenary, Pirate, Rogue, and/or Warlock creature types."
- CR 208.4b: base power and toughness are the characteristics "after
  applying any characteristic-defining abilities and abilities that set power
  and/or toughness, ignoring any effects and counters that modify power
  and/or toughness without setting them" (`Game.base_power_toughness_board`).
- CR 105.2c: "A colorless object has no color" - "colors among permanents"
  never counts colorless.
- CR 506.2 / CR 508.5: the defending player is the player attacked, or the
  controller of the planeswalker or battle attacked.
- CR 601.2c / CR 608.2b: whether "that spell could target" an object is
  asked of the spell's own targeting requirement as a target would be
  checked (`Game.legal_target`).
"""

import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, cast

from ...numbers import COUNT, parse_count
from . import ConditionReader

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from ..layers import Characteristics
    from . import ConditionContext

#: One read quality: whether a permanent has it, asked with the context the
#: condition is read in (for "other", "you own", "that spell could target").
ObjectTest = Callable[["ConditionContext", "CardState", "Characteristics"], bool]

#: CR 700.12's batch of creature types.
_OUTLAW_TYPES = frozenset({"assassin", "mercenary", "pirate", "rogue", "warlock"})


@dataclass(frozen=True)
class _ReadableTemplate:
    """A regex that claims a clause only when `readable` accepts its match -
    duck-typed as `re.Pattern` for `ConditionReader.pattern`, whose only use
    is `fullmatch`. What a quality phrase means is not a regular language, so
    the regex claims the clause's shape and `readable` its words."""

    regex: re.Pattern[str]
    readable: Callable[[re.Match[str]], bool]

    def fullmatch(self, text: str) -> re.Match[str] | None:
        match = self.regex.fullmatch(text)
        if match is None or not self.readable(match):
            return None
        return match


def _template(pattern: str, readable: Callable[[re.Match[str]], bool]) -> re.Pattern[str]:
    return cast("re.Pattern[str]", _ReadableTemplate(re.compile(pattern), readable))


# -- qualities ------------------------------------------------------------------


def _attached(context: "ConditionContext", state: "CardState", subtype: str) -> list["CardState"]:
    """The permanents of `subtype` (Aura, Equipment) attached to `state`, read
    off the computed board (CR 613.5)."""
    game = context.game
    board = game.computed_board()
    return [
        other
        for other in game.battlefield
        if other.attached_to == state.id and subtype in board.of(other).subtypes
    ]


def _is_modified(context: "ConditionContext", state: "CardState", chars: "Characteristics") -> bool:
    """CR 700.9's three ways, the Aura's controller compared to the
    permanent's."""
    if any(amount > 0 for amount in chars.counters.values()):
        return True
    if _attached(context, state, "Equipment"):
        return True
    controller = chars.controller
    board = context.game.computed_board()
    return any(
        board.of(aura).controller == controller for aura in _attached(context, state, "Aura")
    )


def _colors(chars: "Characteristics") -> set:
    from ...models.card import Color

    return {color for color in chars.colors if color is not Color.COLORLESS}


def _other(ctx: "ConditionContext", state: "CardState", chars: "Characteristics") -> bool:
    """ "other"/"another": not the object the condition is printed on."""
    return ctx.source is None or state.id != ctx.source.id


def _state_word(word: str) -> ObjectTest | None:
    """A word about the object rather than its characteristics - its status
    (CR 110.5), whether it is a token (CR 111.1), in combat, modified or
    attached to - or CR 700.12's "outlaw"."""
    if word in ("other", "another"):
        return _other
    if word in ("permanent", "permanents"):
        return lambda ctx, state, chars: True
    if word in ("token", "tokens"):
        return lambda ctx, state, chars: bool(state.token)
    if word == "nontoken":
        return lambda ctx, state, chars: not state.token
    if word in ("tapped", "untapped"):
        wanted = word == "tapped"
        return lambda ctx, state, chars: bool(state.tapped) == wanted
    if word in ("attacking", "nonattacking"):
        wanted = word == "attacking"
        return lambda ctx, state, chars: (state.id in ctx.game.combat.attacker_ids) == wanted
    if word in ("blocking", "nonblocking"):
        wanted = word == "blocking"
        return lambda ctx, state, chars: (state.id in ctx.game.combat.blocker_ids) == wanted
    if word == "modified":
        return _is_modified
    if word in ("enchanted", "equipped"):
        subtype = "Aura" if word == "enchanted" else "Equipment"
        return lambda ctx, state, chars: bool(_attached(ctx, state, subtype))
    if word in ("outlaw", "outlaws"):
        return lambda ctx, state, chars: any(
            each.lower() in _OUTLAW_TYPES for each in chars.subtypes
        )
    if word == "multicolored":
        return lambda ctx, state, chars: len(_colors(chars)) >= 2
    if word == "monocolored":
        return lambda ctx, state, chars: len(_colors(chars)) == 1
    return None


def _words(phrase: str) -> ObjectTest | None:
    """Every word of a quality's noun phrase, each read as a state word or a
    characteristic word (`_characteristic_word`); None when any is not."""
    from ...models.game import _characteristic_word

    tests: list[ObjectTest] = []
    for word in (each for each in re.split(r"[,\s]+", phrase.strip()) if each):
        state_test = _state_word(word)
        if state_test is not None:
            tests.append(state_test)
            continue
        characteristic = _characteristic_word(word)
        if characteristic is None:
            return None
        tests.append(lambda ctx, state, chars, test=characteristic: test(chars))
    if not tests:
        return None
    return lambda ctx, state, chars: all(test(ctx, state, chars) for test in tests)


def _both(first: ObjectTest, second: ObjectTest) -> ObjectTest:
    return lambda ctx, state, chars: first(ctx, state, chars) and second(ctx, state, chars)


_STAT = r"power|toughness|mana value"


def _stat(chars: "Characteristics", stat: str) -> float:
    if stat == "power":
        return chars.numeric_power
    if stat == "toughness":
        return chars.numeric_toughness
    return chars.mana_value


def _greatest(among: ObjectTest, stat: str) -> ObjectTest:
    """ "with the greatest <stat> among <quality> on the battlefield" - a tie
    for the greatest has the greatest too (Padeem prints "or tied for" out)."""

    def test(ctx: "ConditionContext", state: "CardState", chars: "Characteristics") -> bool:
        board = ctx.game.computed_board()
        values = [
            _stat(board.of(other), stat)
            for other in ctx.game.battlefield
            if among(ctx, other, board.of(other))
        ]
        return bool(values) and _stat(chars, stat) == max(values)

    return test


def _base_power_below(
    ctx: "ConditionContext", state: "CardState", chars: "Characteristics"
) -> bool:
    """CR 208.4b: power greater than base power."""
    base = ctx.game.base_power_toughness_board()
    try:
        return chars.numeric_power > base.of(state).numeric_power
    except KeyError:
        return False


def _could_be_targeted_by_the_event_spell(
    ctx: "ConditionContext", state: "CardState", chars: "Characteristics"
) -> bool:
    """ "that spell could target" (Beamsplitter Mage): the trigger event's
    spell, asked whether `state` would be a legal target for it now."""
    from ...models.card_state import TargetRef

    event = ctx.event
    if event is None or event.subject_id is None:
        return False
    spell = ctx.game.find_by_id(event.subject_id)
    if spell is None:
        return False
    return ctx.game.legal_target(spell, TargetRef.to_card(state)) is not None


def _counter_kind(word: str) -> str:
    return word.strip().lower()


#: Each suffix a quality phrase may end with, read off the end one at a time.
_SUFFIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?P<rest>.+?) named (?P<name>.+)"), "named"),
    (
        re.compile(
            r"(?P<rest>.+?),? (?:that (?:each )?(?:has|have)|with) toughness greater than "
            r"(?:its|their) power"
        ),
        "toughness_over_power",
    ),
    (re.compile(r"(?P<rest>.+?) with power greater than (?:its|their) base power"), "base"),
    (
        re.compile(
            rf"(?P<rest>.+?) with the greatest (?P<stat>{_STAT})"
            r"(?: among (?P<among>.+?)(?: on the battlefield)?)?"
            rf"(?: or tied for the greatest (?:{_STAT}))?"
        ),
        "greatest",
    ),
    (
        re.compile(r"(?P<rest>.+?) with (?:a|an|one or more) counters? on (?:it|them)"),
        "any_counter",
    ),
    (
        re.compile(
            rf"(?P<rest>.+?) with (?:(?P<count>{COUNT}|one or more)(?: or more)? )?"
            r"(?P<kind>[a-z0-9+/-]+) counters? on (?:it|them)"
        ),
        "counter",
    ),
    (
        re.compile(rf"(?P<rest>.+?) with (?P<stat>{_STAT}) (?P<n>\d+) or (?P<dir>greater|less)"),
        "stat",
    ),
    (re.compile(r"(?P<rest>.+?) that spell could target"), "could_target"),
    (re.compile(r"(?P<rest>.+?) (?:that )?you (?P<neg>don't |do not )?own"), "owned"),
    (re.compile(r"(?P<rest>.+?) (?:that )?you (?P<neg>don't |do not )?control"), "controlled"),
    (re.compile(r"(?P<rest>.+?) your opponents control"), "opponents"),
    (re.compile(r"(?P<rest>.+?) with (?P<keyword>[a-z][a-z -]*)"), "keyword"),
)


def _suffixed(phrase: str) -> ObjectTest | None:
    for pattern, kind in _SUFFIXES:
        match = pattern.fullmatch(phrase)
        if match is None:
            continue
        rest = quality(match.group("rest"))
        if rest is None:
            continue
        extra = _suffix_test(kind, match)
        if extra is None:
            continue
        return _both(rest, extra)
    return None


def _suffix_test(kind: str, match: re.Match[str]) -> ObjectTest | None:
    if kind == "named":
        name = match.group("name").strip().lower()
        return lambda ctx, state, chars: chars.name.lower() == name
    if kind == "toughness_over_power":
        return lambda ctx, state, chars: chars.numeric_toughness > chars.numeric_power
    if kind == "base":
        return _base_power_below
    if kind == "greatest":
        among = (
            quality(match.group("among")) if match.group("among") else quality(match.group("rest"))
        )
        if among is None:
            return None
        return _greatest(among, match.group("stat"))
    if kind == "any_counter":
        return lambda ctx, state, chars: any(amount > 0 for amount in chars.counters.values())
    if kind == "counter":
        printed = match.group("count")
        needed = 1 if printed in (None, "one or more") else parse_count(printed)
        if needed is None:
            return None
        counter = _counter_kind(match.group("kind"))
        return lambda ctx, state, chars: state.counter_count(counter) >= needed
    if kind == "stat":
        threshold = int(match.group("n"))
        stat = match.group("stat")
        if match.group("dir") == "greater":
            return lambda ctx, state, chars: _stat(chars, stat) >= threshold
        return lambda ctx, state, chars: _stat(chars, stat) <= threshold
    if kind == "could_target":
        return _could_be_targeted_by_the_event_spell
    if kind == "owned":
        negated = bool(match.group("neg"))
        return lambda ctx, state, chars: (state.owner == ctx.controller) != negated
    if kind == "controlled":
        negated = bool(match.group("neg"))
        return lambda ctx, state, chars: (chars.controller == ctx.controller) != negated
    if kind == "opponents":
        return lambda ctx, state, chars: chars.controller not in (None, ctx.controller)
    if kind == "keyword":
        from ..abilities import KEYWORD_ABILITY_NAMES
        from ..combat import has_keyword

        keyword = match.group("keyword").strip()
        if keyword not in KEYWORD_ABILITY_NAMES:
            return None
        return lambda ctx, state, chars: has_keyword(state, keyword, ctx.game)
    return None


_ARTICLE = re.compile(r"^(?:a|an|the) ")


@cache
def quality(phrase: str) -> ObjectTest | None:
    """A quality phrase - "creature with flying", "tapped creatures", "other
    colorless creatures", "Plains or a Swamp", "Wolves and/or Werewolves",
    "creature with the greatest power among creatures on the battlefield" -
    as a test on one permanent, or None when any word of it is not read.

    Tried in order: the phrase as plain words; with its trailing suffix read
    off (`_SUFFIXES`); and last as two qualities either of which will do
    ("or", "and/or" - CR 205.2a's "artifact or enchantment" style)."""
    text = _ARTICLE.sub("", phrase.strip().lower(), count=1)
    if not text:
        return None
    plain = _words(text)
    if plain is not None:
        return plain
    suffixed = _suffixed(text)
    if suffixed is not None:
        return suffixed
    for joiner in (" and/or ", " or "):
        start = 0
        while (index := text.find(joiner, start)) != -1:
            left, right = quality(text[:index]), quality(text[index + len(joiner) :])
            if left is not None and right is not None:
                first, second = left, right
                return lambda ctx, state, chars: (
                    first(ctx, state, chars) or second(ctx, state, chars)
                )
            start = index + 1
    return None


def _matching(
    context: "ConditionContext", test: ObjectTest, permanents: Iterable["CardState"]
) -> list["CardState"]:
    board = context.game.computed_board()
    return [state for state in permanents if test(context, state, board.of(state))]


# -- grouping: "with different powers", "that share a creature type" -----------

_GROUPING = re.compile(
    rf"(?P<quality>.+?) (?:with different (?P<distinct>powers|names|{_STAT}s)"
    r"|that share a (?P<shared>creature|card) type)"
)


def _grouped_measure(
    context: "ConditionContext", states: list["CardState"], match: re.Match[str] | None
) -> int:
    """How many of `states` the clause counts: all of them, or the size of the
    largest group of distinct values or of a shared type."""
    if match is None:
        return len(states)
    board = context.game.computed_board()
    if match.group("distinct"):
        attribute = match.group("distinct").removesuffix("s")
        if attribute == "name":
            return len({board.of(state).name for state in states})
        return len({_stat(board.of(state), attribute) for state in states})
    shared: Counter[str] = Counter()
    for state in states:
        chars = board.of(state)
        words = (
            {str(each).lower() for each in chars.types}
            if match.group("shared") == "card"
            else {each.lower() for each in chars.subtypes}
        )
        shared.update(words)
    return max(shared.values(), default=0)


def _split_quality(text: str) -> tuple[str, re.Match[str] | None]:
    grouping = _GROUPING.fullmatch(text)
    return (grouping.group("quality"), grouping) if grouping else (text, None)


def _quality_readable(text: str) -> bool:
    core, _grouping = _split_quality(text)
    return quality(core) is not None


# -- amounts ----------------------------------------------------------------------

_AMOUNT = (
    rf"(?P<amount>no|another|an?|the|one or more|exactly {COUNT}|at least {COUNT}"
    rf"|{COUNT} or more|{COUNT} or fewer|fewer than {COUNT})"
)


def _amount_test(amount: str) -> Callable[[int], bool] | None:
    """The count a printed amount asks for, via `magic_cards_model.numbers`."""
    if amount == "no":
        return lambda count: count == 0
    if amount in ("a", "an", "the", "another", "one or more"):
        return lambda count: count >= 1
    for prefix, compare in (
        ("exactly ", lambda count, n: count == n),
        ("at least ", lambda count, n: count >= n),
        ("fewer than ", lambda count, n: count < n),
    ):
        if amount.startswith(prefix):
            needed = parse_count(amount.removeprefix(prefix))
            if needed is None:
                return None
            return lambda count, needed=needed, compare=compare: compare(count, needed)
    for suffix, compare in (
        (" or more", lambda count, n: count >= n),
        (" or fewer", lambda count, n: count <= n),
    ):
        if amount.endswith(suffix):
            needed = parse_count(amount.removesuffix(suffix))
            if needed is None:
                return None
            return lambda count, needed=needed, compare=compare: compare(count, needed)
    return None


def _defending_players(context: "ConditionContext") -> list[str]:
    """CR 506.2 / 508.5: the defending player the trigger event names, else
    the one the source is attacking, else every one in this combat."""
    from ..combat import defending_player

    game = context.game
    event = context.event
    if event is not None and getattr(event, "defender_controller", None) is not None:
        return [event.defender_controller]
    if event is not None and getattr(event, "defender", None) is not None:
        found = defending_player(game, event.defender)
        return [found] if found is not None else []
    attacks = game.combat.attacks
    if context.source is not None:
        own = [attack for attack in attacks if attack.attacker_id == context.source.id]
        if own:
            attacks = own
    return sorted(
        {
            player
            for attack in attacks
            if (player := defending_player(game, attack.defender)) is not None
        }
    )


def _players(context: "ConditionContext", who: str) -> tuple[list[str], bool]:
    """The players a clause is about, and whether every one of them must
    satisfy it (True) or any one will do (False)."""
    everyone = [player.username for player in context.game.players_in_game]
    opponents = [player for player in everyone if player != context.controller]
    if who == "you":
        return [context.controller], True
    if who == "an opponent":
        return opponents, False
    if who == "a player":
        return everyone, False
    if who in ("each player",):
        return everyone, True
    if who in ("each opponent", "your opponents"):
        return opponents, True
    if who == "defending player":
        return _defending_players(context), True
    if who == "that player":
        event = context.event
        player = getattr(event, "player", None) if event is not None else None
        return ([player] if player else []), True
    return [], True


_WHO = (
    r"(?P<who>you|an opponent|a player|each player|each opponent|your opponents"
    r"|defending player|that player)"
)
_CONTROLS = r"(?:(?P<dont>don't|doesn't|do not|does not) control|controls?)"


def _controls(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<who> [don't] control(s) <amount> <quality>" - a count of the
    permanents each named player controls (CR 613.5), compared with the
    amount, the "don't" negating the whole."""
    amount = _amount_test(match.group("amount"))
    core, grouping = _split_quality(match.group("quality"))
    test = quality(core)
    if amount is None or test is None:
        return False
    if match.group("amount") == "another":
        test = _both(test, _other)
    players, every = _players(context, match.group("who"))
    if not players:
        return False
    game = context.game

    def holds(player: str) -> bool:
        matching = _matching(context, test, game.permanents_controlled_by(player))
        return amount(_grouped_measure(context, matching, grouping))

    answers = [holds(player) for player in players]
    held = all(answers) if every else any(answers)
    return held != bool(match.group("dont"))


def _controls_readable(match: re.Match[str]) -> bool:
    return _amount_test(match.group("amount")) is not None and _quality_readable(
        match.group("quality")
    )


# -- the whole battlefield ------------------------------------------------------


def _on_the_battlefield(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "no creatures are on the battlefield", "there are N or more <quality>
    on the battlefield"."""
    amount = _amount_test(match.group("amount") or "no")
    test = quality(match.group("quality"))
    if amount is None or test is None:
        return False
    return amount(len(_matching(context, test, context.game.battlefield)))


def _all_are(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "all lands on the battlefield are Islands" - every permanent with the
    first quality has the second (vacuously true when there are none)."""
    subject = quality(match.group("quality"))
    predicate = quality(match.group("target"))
    if subject is None or predicate is None:
        return False
    board = context.game.computed_board()
    return all(
        predicate(context, state, board.of(state))
        for state in _matching(context, subject, context.game.battlefield)
    )


def _have_counters(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "two or more permanents you don't control have an aim counter on them"
    - the counter read as one more suffix of the quality."""
    amount = _amount_test(match.group("amount"))
    test = quality(f"{match.group('quality')} with {match.group('counter')}")
    if amount is None or test is None:
        return False
    return amount(len(_matching(context, test, context.game.battlefield)))


# -- aggregates -----------------------------------------------------------------


def _total(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "creatures you control have total power 8 or greater" - the sum of the
    stat across the permanents, each read off the computed board."""
    needed = parse_count(match.group("count"))
    test = quality(match.group("quality"))
    if needed is None or test is None:
        return False
    board = context.game.computed_board()
    stat = match.group("stat")
    total = sum(
        _stat(board.of(state), stat)
        for state in _matching(
            context, test, context.game.permanents_controlled_by(context.controller)
        )
    )
    return total >= needed


def _colors_among(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "there are five colors among permanents you control" (CR 105.2c:
    colorless is no color). A bare count is exactly that many."""
    amount = _amount_test(_count_bare(match.group("amount")))
    test = quality(match.group("quality"))
    if amount is None or test is None:
        return False
    board = context.game.computed_board()
    colors: set = set()
    for state in _matching(
        context, test, context.game.permanents_controlled_by(context.controller)
    ):
        colors |= _colors(board.of(state))
    return amount(len(colors))


def _attached_object_is(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "enchanted permanent is a creature with the greatest power among
    creatures on the battlefield" - the object the source Aura or Equipment
    is attached to (CR 303.4, CR 301.5) has the quality."""
    source = context.source
    test = quality(f"{match.group('noun')} {match.group('quality')}".strip())
    if source is None or source.attached_to is None or test is None:
        return False
    attached = context.game.find_by_id(source.attached_to)
    if attached is None:
        return False
    try:
        chars = context.game.computed_board().of(attached)
    except KeyError:
        return False
    return test(context, attached, chars)


def _count_bare(amount: str) -> str:
    """A bare count ("five") read as exactly that many."""
    return amount if " " in amount or amount == "no" else f"exactly {amount}"


def _colors_readable(match: re.Match[str]) -> bool:
    return _amount_test(_count_bare(match.group("amount"))) is not None and (
        quality(match.group("quality")) is not None
    )


def _same_name_as_one_another(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you control N or more <quality> with the same name as one another"
    (Chrome Replicator's "two or more nonland, nontoken permanents",
    Mechanized Production's "eight or more artifacts"): some one name is
    shared by at least N of the permanents you control that have the quality.
    A quality word the characteristic reader cannot read makes the whole
    clause false rather than guessed."""
    from ...models.game import _characteristic_word

    needed = parse_count(match.group("count"))
    if needed is None:
        return False
    words = [word for word in re.split(r"[,\s]+", match.group("quality")) if word]
    if not words:
        return False
    *qualifiers, noun = words
    object_tests: list = []
    characteristic_tests: list = []
    for word in qualifiers + ([] if noun in ("permanent", "permanents") else [noun]):
        if word in ("token", "tokens", "nontoken"):
            wanted = word != "nontoken"
            object_tests.append(lambda state, wanted=wanted: bool(state.token) == wanted)
            continue
        test = _characteristic_word(word)
        if test is None:
            return False
        characteristic_tests.append(test)
    game = context.game
    board = game.computed_board()

    def has_quality(state: "CardState") -> bool:
        chars = board.of(state)
        return all(test(state) for test in object_tests) and all(
            test(chars) for test in characteristic_tests
        )

    names = Counter(
        board.of(state).name
        for state in game.permanents_controlled_by(context.controller)
        if has_quality(state)
    )
    return any(count >= needed for count in names.values())


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(
            rf"you control (?P<count>{COUNT}) or more (?P<quality>[a-z, -]+?) "
            r"with the same name as one another"
        ),
        _same_name_as_one_another,
    ),
    ConditionReader(
        _template(rf"{_WHO} {_CONTROLS} {_AMOUNT} (?P<quality>.+)", _controls_readable),
        _controls,
    ),
    ConditionReader(
        _template(
            rf"(?:there (?:are|is) )?(?P<amount>no|{COUNT} or more|{COUNT} or fewer) "
            r"(?P<quality>.+?) (?:(?:are|is) )?on the battlefield",
            lambda match: (
                _amount_test(match.group("amount")) is not None
                and quality(match.group("quality")) is not None
            ),
        ),
        _on_the_battlefield,
    ),
    ConditionReader(
        _template(
            r"all (?P<quality>.+?) on the battlefield are (?P<target>.+)",
            lambda match: (
                quality(match.group("quality")) is not None
                and quality(match.group("target")) is not None
            ),
        ),
        _all_are,
    ),
    ConditionReader(
        _template(
            rf"(?P<amount>{COUNT} or more|no) (?P<quality>.+?) (?:have|has) "
            r"(?P<counter>an? [a-z0-9+/-]+ counters? on (?:it|them))",
            lambda match: (
                _amount_test(match.group("amount")) is not None
                and quality(f"{match.group('quality')} with {match.group('counter')}") is not None
            ),
        ),
        _have_counters,
    ),
    ConditionReader(
        _template(
            rf"(?P<quality>.+?) you control have total (?P<stat>{_STAT}) "
            rf"(?P<count>{COUNT}) or (?:greater|more)",
            lambda match: (
                quality(match.group("quality")) is not None
                and parse_count(match.group("count")) is not None
            ),
        ),
        _total,
    ),
    ConditionReader(
        _template(
            rf"there (?:are|is) (?P<amount>{COUNT} or more|{COUNT} or fewer|{COUNT}) colors? "
            r"among (?P<quality>.+?) you control",
            _colors_readable,
        ),
        _colors_among,
    ),
    ConditionReader(
        _template(
            r"(?:enchanted|equipped) (?P<noun>permanent|creature|artifact|land) is an? "
            r"(?P<quality>.+)",
            lambda match: quality(f"{match.group('noun')} {match.group('quality')}") is not None,
        ),
        _attached_object_is,
    ),
)

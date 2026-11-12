"""Source damage to a target and to a group defined off that target.

"`<src>` deals N damage to target creature and each other creature
`<that shares a color with it | with the same name as that creature>`."
(Wojek Embermage, Izzet Staticaster.) One target (CR 115.1); the rest of the
group is not targeted but read off it by CR 400.7 back-reference as the
ability resolves - a shared color (CR 105.2c: a colorless object has no
color, so it shares none) or a shared name. CR 608.2b: with the one target
illegal the ability doesn't resolve, so the group is not damaged either.

The other back-reference shapes this module once read have one reader each
in `machines/effects.py`: "and M damage to that creature's controller"
(`_DAMAGE_TARGET_ALSO_DAMAGES_CONTROLLER_RE`), "That creature deals damage
equal to its power to this creature" (`_RIDER_DEALS_DAMAGE_EQUAL_TO_ITS_
POWER_RE`), and an elided or back-referring "... instead" alternative
(`_parse_condition_instead_clause_for_ability`).

Rules looked up with `mise run rules:find` in the session that wrote this:
CR 105.2c, CR 608.2b.
"""

import re
from typing import TYPE_CHECKING, Any

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack

_DAMAGE_TARGET_AND_EACH_OTHER_RE = re.compile(
    rf"^(?P<subject>[^.]+?) deals (?P<n>{COUNT}) damage to target creature and each other "
    r"creature (?:(?P<color>that shares a colou?r with it)"
    r"|(?P<name>with the same name as that creature))\.?$",
    re.IGNORECASE,
)


def _parse_damage_target_and_each_other(text: str) -> Any:
    if " and each other creature " not in text:
        return None
    match = _DAMAGE_TARGET_AND_EACH_OTHER_RE.fullmatch(text)
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    by_color = match.group("color") is not None

    def effect(game: "Game", stack_object: "AbilityOnStack | CardState") -> None:
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)
        )
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        board = game.computed_board()
        wanted = board.of(target)
        group = [target]
        for other in game.battlefield:
            if other is target:
                continue
            chars = board.of(other)
            if not chars.is_creature:
                continue
            if by_color:
                shares = bool(set(chars.colors) & set(wanted.colors))  # CR 105.2c
            else:
                shares = bool(wanted.name) and chars.name == wanted.name
            if shares:
                group.append(other)
        for creature in group:
            game.deal_damage(creature, amount, source=source)

    return effect


def damage_backref_spell_effect(effect_text: str) -> Any:
    """`damage_backref_ability_effect`'s shape on a resolving spell (Homing
    Lightning's "deals 4 damage to target creature and each other creature with
    the same name as that creature"), or None."""
    return damage_backref_ability_effect(effect_text)


def damage_backref_ability_effect(effect_text: str) -> Any:
    """The shape above, if `effect_text` reads as it, or None."""
    from .effects import _strip_non_effect_preamble

    text = collapsed(_strip_non_effect_preamble(effect_text))
    return _parse_damage_target_and_each_other(text)


# ---------------------------------------------------------------------------
# A damage SPELL whose later clause refers back to what the first one did
# ---------------------------------------------------------------------------
#
# "`<src>` deals N damage to target creature. If that creature has a +1/+1
# counter on it, `<src>` deals 5 damage to it instead." / "... You gain life
# equal to the damage dealt this way." / "... That player discards two
# cards." / "`<src>` deals 3 damage to that creature's controller."
#
# CR 608.2c: the spell's text is followed in order and later text may modify
# the meaning of earlier text; the referent of "that creature"/"that player"
# is the one target announced under CR 115.1. One reader owns the whole
# sequence rather than one `_merge_*` pair per card, because every pair needs
# the same three things carried between its clauses: the target as it was
# *before* the first clause ran (its quality, its controller by last known
# information, CR 608.2h), the amount the first clause actually dealt (CR
# 120.3, after prevention), and the radiance group when the first clause
# names one. `merges._parse_damage_then_followup_spell` registers it.
#
# Rules looked up with `mise run rules:find` in the session that wrote this:
# CR 105.2c, 115.1, 120.1, 120.3, 207.2c, 608.2b, 608.2c, 608.2d, 608.2h,
# 614.1a, 701.9a.


class _Run:
    """What one resolution of the sequence knows: the head's target as it was
    before the head ran, the controller's name by last known information, and
    the damage dealt so far."""

    def __init__(self, game: "Game", spell: CardState, target: Any) -> None:
        self.game = game
        self.spell = spell
        self.target = target
        self.caster = game.controller_of(spell).username
        # CR 608.2h: read before the head changes anything - a creature the
        # head kills still has the controller it had.
        self.target_controller: str | None = None
        self.target_player: str | None = None
        if isinstance(target, CardState):
            self.target_controller = game.controller_of(target).username
            self.target_player = self.target_controller
        elif target is not None:
            self.target_player = target.username
        self.dealt = 0
        self.facts: dict[int, bool] = {}


#: A sentence after the head: it can decide the head's amount before the head
#: runs (`instead`), run once the head is done (`after`), or both.
class _Followup:
    def __init__(
        self,
        *,
        referent_predicate: Any = None,
        instead_amount: int | None = None,
        after: Any = None,
        needs_player: bool = False,
        needs_permanent: bool = False,
        kind: str = "other",
    ) -> None:
        self.kind = kind
        self.referent_predicate = referent_predicate
        self.instead_amount = instead_amount
        self.after = after
        self.needs_player = needs_player
        self.needs_permanent = needs_permanent


_REFERENT = r"(?:that (?:creature|permanent|planeswalker|artifact|enchantment|land|target)|it)"

_HAS_COUNTER_RE = re.compile(
    rf"^{_REFERENT} has (?:a|an|one or more) (?P<kind>[^ ]+) counters? on it$", re.IGNORECASE
)
_HAS_KEYWORD_RE = re.compile(rf"^{_REFERENT} has (?P<keyword>[a-z]+)$", re.IGNORECASE)
_IS_QUALITY_RE = re.compile(rf"^{_REFERENT} (?:is|'s) (?:an? )?(?P<quality>[a-z/ ]+)$", re.I)
_ITS_QUALITY_RE = re.compile(r"^it's (?:an? )?(?P<quality>[a-z/ ]+)$", re.IGNORECASE)


def _quality_word_test(word: str) -> Any:
    """`(characteristics) -> bool` for one adjective or noun of a printed
    quality - a color (CR 105.2c: colorless has none), a card type, a
    supertype or a subtype - or None when it is none of those."""
    from ..data.subtypes import subtype_vocabulary
    from ..models.card import Supertype, Type
    from .effects import _HAND_EXILE_COLOR_WORDS

    lowered = word.lower()
    if lowered in _HAND_EXILE_COLOR_WORDS:
        color = _HAND_EXILE_COLOR_WORDS[lowered]
        if color is None:
            return lambda chars: not chars.colors
        return lambda chars: color in chars.colors
    try:
        card_type = Type(lowered)
    except ValueError:
        card_type = None
    if card_type is not None:
        return lambda chars: card_type in chars.types
    try:
        supertype = Supertype(lowered)
    except ValueError:
        supertype = None
    if supertype is not None:
        return lambda chars: supertype in chars.supertypes
    if lowered in subtype_vocabulary():
        return lambda chars: any(sub.lower() == lowered for sub in chars.subtypes)
    return None


def _quality_test(quality: str) -> Any:
    """ "green", "an artifact creature", "white and/or blue", "a Chandra
    planeswalker": every word of one alternative must hold, any alternative
    suffices ("and/or" and "or" both read as the inclusive or)."""
    alternatives = re.split(r"\s+and/or\s+|\s+or\s+", quality.strip().lower())
    tests = []
    for alternative in alternatives:
        words = [word for word in alternative.split() if word]
        word_tests = [_quality_word_test(word) for word in words]
        if not words or any(test is None for test in word_tests):
            return None
        tests.append(word_tests)
    return lambda chars: any(all(test(chars) for test in word_tests) for word_tests in tests)


def referent_condition(text: str) -> Any:
    """`(game, permanent) -> bool` for the condition "if `<that creature>`
    `<has a +1/+1 counter on it | has infect | is green | is a Spirit>`", read
    off the permanent as it is on the computed board (CR 613.5) - or None when
    `text` is not one of those shapes, so a condition this does not read
    leaves the whole spell unread (CR 608.2c) rather than assumed false."""
    from .combat import has_keyword
    from .effects.counters import _counter_kind

    stripped = text.strip().rstrip(".").strip()
    if match := _HAS_COUNTER_RE.fullmatch(stripped):
        kind = _counter_kind(match.group("kind"))
        return lambda game, permanent: permanent.counter_count(kind) > 0
    if match := _HAS_KEYWORD_RE.fullmatch(stripped):
        from .combat import Keyword

        keyword = match.group("keyword").lower()
        if keyword not in {member.value.lower() for member in Keyword}:
            return None
        return lambda game, permanent: has_keyword(permanent, keyword, game)
    match = _IS_QUALITY_RE.fullmatch(stripped) or _ITS_QUALITY_RE.fullmatch(stripped)
    if match is None:
        return None
    test = _quality_test(match.group("quality"))
    if test is None:
        return None
    return lambda game, permanent: test(game.computed_board().of(permanent))


_HEAD_TAIL_LIFE = " and you gain life equal to the damage dealt this way"
_HEAD_TAIL_CONTROLLER_RE = re.compile(
    rf" and (?P<m>{COUNT}) damage to that (?P<noun>[a-z]+)'s controller$", re.IGNORECASE
)
_HEAD_TAIL_RADIANCE = " and each other creature that shares a color with it"

_HEAD_FIXED_RE = re.compile(
    rf"^(?P<src>[^.]+?) deals (?P<n>{COUNT}|[xX]) damage to (?P<phrase>.+)$", re.IGNORECASE
)
_HEAD_EQUAL_AFTER_RE = re.compile(
    r"^(?P<src>[^.]+?) deals damage to (?P<phrase>.+?) equal to (?P<expr>.+)$", re.IGNORECASE
)
_HEAD_EQUAL_BEFORE_RE = re.compile(
    r"^(?P<src>[^.]+?) deals damage equal to (?P<expr>.+?) to "
    r"(?P<phrase>any target|target .+)$",
    re.IGNORECASE,
)
_PUMP_HEAD_RE = re.compile(
    r"^(?P<phrase>target (?:creature|permanent|artifact|land|enchantment|planeswalker)) ",
    re.IGNORECASE,
)
_SACRIFICED_POWER_RE = re.compile(r"^the sacrificed creature'?s power$", re.IGNORECASE)

_FOLLOW_INSTEAD_LEADING_RE = re.compile(
    rf"^if (?P<cond>.+?), (?P<src>[^,]+?) deals (?P<m>{COUNT}) damage"
    r"(?: to (?:it|that (?:creature|permanent|planeswalker)))? instead$",
    re.IGNORECASE,
)
_FOLLOW_INSTEAD_TRAILING_RE = re.compile(
    rf"^(?:it|(?P<src>[^,]+?)) deals (?P<m>{COUNT}) damage instead if (?P<cond>.+)$",
    re.IGNORECASE,
)
_FOLLOW_CONTROLLER_RE = re.compile(
    rf"^(?:if (?P<cond>.+?), )?(?P<src>[^,]+?) (?:also )?deals (?P<m>{COUNT}) damage to "
    r"that (?P<noun>[a-z]+)'s controller$",
    re.IGNORECASE,
)
_FOLLOW_DISCARD_RE = re.compile(
    rf"^that player(?: or that planeswalker's controller)? discards "
    rf"(?P<n>{COUNT}|[xX]) cards?$",
    re.IGNORECASE,
)
_PLAYER_DEALT_DAMAGE_THIS_WAY_RE = re.compile(
    r"^if a player is dealt damage this way, (?P<rider>.+)$", re.IGNORECASE
)
_THEY_DISCARD_RE = re.compile(
    rf"^(?:they|that player) discards? (?P<n>{COUNT}) cards?$", re.IGNORECASE
)
_FOLLOW_MAY_DISCARD_RE = re.compile(
    r"^if (?P<cond>.+?), (?P<rest>you may discard .+)$", re.IGNORECASE
)
_FOLLOW_IF_YOU_DO_RE = re.compile(r"^if you do, .+$", re.IGNORECASE)
_PRONOUN_SOURCES = ("it", "this spell")


def _is_the_spell_itself(source: str, head_source: str) -> bool:
    lowered = source.strip().lower()
    if lowered in _PRONOUN_SOURCES or lowered == head_source.strip().lower():
        return True
    # A head that names no source of its own (the pump Fodder Launch opens with)
    # leaves the rider's subject to be any object but a referent or a group.
    return not head_source and not lowered.startswith(("that ", "target ", "each ", "another "))


def _followup_controller(match: "re.Match[str]", head_source: str) -> _Followup | None:
    if not _is_the_spell_itself(match.group("src"), head_source):
        return None
    amount = parse_count(match.group("m"))
    if amount is None:
        return None
    condition = match.group("cond")
    predicate = None
    if condition is not None:
        predicate = referent_condition(condition)
        if predicate is None:
            return None

    def after(run: _Run) -> None:
        if run.target_controller is None:
            return
        if predicate is not None and not run.facts.get(id(after), False):
            return
        run.game.deal_damage(run.game.player(run.target_controller), amount, source=run.spell)

    return _Followup(
        referent_predicate=(after, predicate),
        after=after,
        needs_permanent=True,
        kind="controller",
    )


def damaged_player_rider(rider: str) -> Any:
    """`(game, player, source name, source id) -> None` for the rider of "If a
    player is dealt damage this way, `<rider>`" - Sonic Shrieker's "they
    discard a card" - run on the player the damage actually reached (CR 120.3a,
    CR 615.6: prevented damage is not dealt), or None when the rider is not a
    shape read here."""
    text = rider.strip().rstrip(".").strip()
    if match := _THEY_DISCARD_RE.fullmatch(text):
        count = parse_count(match.group("n"))
        if count is None:
            return None

        def discard(game: "Game", player: Any, source_name: str, source_id: Any) -> None:
            from .effects import _discard_cards

            _discard_cards(game, player, count, source_name, source_id=source_id)

        return discard
    return None


def _followup_for(sentence: str, head_source: str) -> _Followup | None:
    """The `_Followup` one sentence after the head reads as, or None."""
    text = sentence.strip().rstrip(".").strip()
    from .effects.life import gain_life_equal_to_damage_dealt

    if (gain_for := gain_life_equal_to_damage_dealt(text)) is not None:
        return _Followup(after=lambda run: gain_for(run.game, run.caster, run.dealt))
    match = _FOLLOW_INSTEAD_LEADING_RE.fullmatch(text) or _FOLLOW_INSTEAD_TRAILING_RE.fullmatch(
        text
    )
    if match is not None:
        source = match.group("src")
        if source is not None and not _is_the_spell_itself(source, head_source):
            return None
        amount = parse_count(match.group("m"))
        predicate = referent_condition(match.group("cond"))
        if amount is None or predicate is None:
            return None
        return _Followup(
            referent_predicate=(None, predicate), instead_amount=amount, needs_permanent=True
        )
    if match := _FOLLOW_CONTROLLER_RE.fullmatch(text):
        return _followup_controller(match, head_source)
    if match := _FOLLOW_DISCARD_RE.fullmatch(text):
        raw = match.group("n")
        count = None if raw.lower() == "x" else parse_count(raw)
        if count is None and raw.lower() != "x":
            return None

        def discard(run: _Run) -> None:
            from .decisions import source_id_of
            from .effects import _discard_cards

            if run.target_player is None:
                return
            player = run.game.player(run.target_player)
            amount = count if count is not None else run.game.cast_record(run.spell).x_value
            _discard_cards(
                run.game,
                player,
                amount,
                run.spell.name,
                source_id=source_id_of(run.spell),
            )

        return _Followup(after=discard, needs_player=True)
    if (dealt := _PLAYER_DEALT_DAMAGE_THIS_WAY_RE.fullmatch(text)) is not None:
        rider = damaged_player_rider(dealt.group("rider"))
        if rider is None:
            return None

        def after_player_dealt_damage(run: _Run) -> None:
            from .decisions import source_id_of

            if run.dealt > 0 and not isinstance(run.target, CardState) and run.target is not None:
                rider(run.game, run.target, run.spell.name, source_id_of(run.spell))

        return _Followup(after=after_player_dealt_damage, needs_player=True)
    return None


def _split_head_tails(sentence: str) -> tuple[str, bool, "re.Match[str] | None", bool]:
    """`sentence` minus the three tails a head can carry - "and you gain life
    equal to the damage dealt this way", "and M damage to that permanent's
    controller", "and each other creature that shares a color with it" - and
    which of them it had."""
    body = sentence.strip().rstrip(".").strip()
    gains_life = False
    if body.lower().endswith(_HEAD_TAIL_LIFE):
        body = body[: -len(_HEAD_TAIL_LIFE)]
        gains_life = True
    controller_tail = _HEAD_TAIL_CONTROLLER_RE.search(body)
    if controller_tail is not None:
        body = body[: controller_tail.start()]
    radiance = body.lower().endswith(_HEAD_TAIL_RADIANCE)
    if radiance:
        body = body[: -len(_HEAD_TAIL_RADIANCE)]
    return body, gains_life, controller_tail, radiance


def _head_amount(body: str) -> tuple[str, str, Any] | None:
    """(source, target phrase, `(game, spell) -> int`) for a head sentence
    whose tails are already cut, or None."""
    from .effects import amount_expression

    if match := _HEAD_FIXED_RE.fullmatch(body):
        raw = match.group("n")
        if raw.lower() == "x":
            return (
                match.group("src"),
                match.group("phrase"),
                lambda game, spell: game.cast_record(spell).x_value,
            )
        fixed = parse_count(raw)
        if fixed is None:
            return None
        return match.group("src"), match.group("phrase"), lambda game, spell: fixed
    equal = _HEAD_EQUAL_AFTER_RE.fullmatch(body) or _HEAD_EQUAL_BEFORE_RE.fullmatch(body)
    if equal is None:
        return None
    expression = equal.group("expr")
    if _SACRIFICED_POWER_RE.fullmatch(expression.strip()):

        def sacrificed_power(game: "Game", spell: CardState) -> int:
            record = game.cast_record(spell)
            if not record.additional_cost_cards:
                return 0
            sacrificed = game.find_by_id(record.additional_cost_cards[0])
            if sacrificed is None or sacrificed.power is None:
                return 0
            return max(sacrificed.power, 0)

        return equal.group("src"), equal.group("phrase"), sacrificed_power
    reader = amount_expression(expression)
    if reader is None:
        return None

    def read(game: "Game", spell: CardState) -> int:
        controller = game.controller_of(spell).username
        return max(reader(game, controller, spell, game.cast_record(spell).x_value), 0)

    return equal.group("src"), equal.group("phrase"), read


def _head_targets(game: "Game", spell: CardState, phrase: str) -> list[Any]:
    """The first resolved target of `spell` the head's phrase can mean - a
    spell with a second target of another kind (Enter the God-Eternals' "Target
    player mills four cards") leaves that one to its own clause."""
    lowered = phrase.lower()
    wants_players = "player" in lowered or "opponent" in lowered or lowered == "any target"
    wants_permanents = lowered == "any target" or bool(
        re.search(r"creature|planeswalker|permanent|artifact|enchantment|land", lowered)
    )
    kept = []
    for target in game.resolve_targets(spell):
        if isinstance(target, CardState):
            if wants_permanents and target.zone is Zone.BATTLEFIELD:
                kept.append(target)
        elif wants_players:
            kept.append(target)
    return kept[:1]


def _radiance_group(game: "Game", target: CardState) -> list[CardState]:
    """The target and each other creature sharing a color with it, as the spell
    resolves (CR 105.2c: a colorless object shares none)."""
    board = game.computed_board()
    wanted = set(board.of(target).colors)
    group = [target]
    for other in game.battlefield:
        if other is target:
            continue
        chars = board.of(other)
        if chars.is_creature and set(chars.colors) & wanted:
            group.append(other)
    return group


def damage_then_followup_spell_effect(effect_text: str) -> Any:
    """The whole sequence on a spell - a damage head and the clauses that
    refer back to it - or None when `effect_text` is not that.

    Needs at least one follow-up (or a tail) so a plain "deals N damage" spell
    stays with its own reader. A sentence after the head this does not read is
    handed to the ordinary clause pipeline whole; if that cannot read it
    either, the whole spell is left unread (CR 608.2c) instead of running half.
    """
    if "damage" not in effect_text.lower():  # the head or its controller rider deals it
        return None

    from .effects import (
        _merge_may_discard_if_you_do_clauses,
        _parse_mixed_clauses,
        _parse_targeted_clause,
        _plain_resolution_sentences,
        _strip_non_effect_preamble,
        _targets_understood,
    )

    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(effect_text))
    if len(sentences) < 1:
        return None
    body, gains_life, controller_tail, radiance = _split_head_tails(sentences[0])
    head = _head_amount(body)
    head_clause: Any = None
    if head is None:
        # Fodder Launch: "Target creature gets -5/-5 until end of turn. `<src>`
        # deals 5 damage to that creature's controller." - the first clause is
        # any single-target instruction the ordinary pipeline reads, and only
        # the controller rider refers back to it.
        pump = _PUMP_HEAD_RE.match(sentences[0].strip())
        if pump is None or len(sentences) < 2:
            return None
        head_clause = _parse_targeted_clause(sentences[0], for_spell=True)
        if head_clause is None:
            return None
        head_source, phrase, amount_of = "", pump.group("phrase"), None
    else:
        head_source, phrase, amount_of = head
    if not _targets_understood(phrase, allow_player_targets=True, battlefield_only=False):
        return None
    if radiance and phrase.lower() != "target creature":
        return None

    followups: list[_Followup] = []
    if gains_life:
        life = _followup_for("you gain life equal to the damage dealt this way", "")
        assert life is not None
        followups.append(life)
    if controller_tail is not None:
        noun_match = _FOLLOW_CONTROLLER_RE.fullmatch(
            f"{head_source} deals {controller_tail.group('m')} damage to that "
            f"{controller_tail.group('noun')}'s controller"
        )
        assert noun_match is not None
        tail_followup = _followup_controller(noun_match, head_source)
        if tail_followup is None:
            return None
        followups.append(tail_followup)

    index = 1
    leftover: list[str] = []
    while index < len(sentences):
        sentence = sentences[index]
        may_discard = _FOLLOW_MAY_DISCARD_RE.fullmatch(sentence.strip().rstrip("."))
        if may_discard is not None and index + 1 < len(sentences):
            predicate = referent_condition(may_discard.group("cond"))
            pair = _merge_may_discard_if_you_do_clauses(
                [may_discard.group("rest"), sentences[index + 1].strip().rstrip(".")],
                0,
                for_spell=True,
            )
            if predicate is not None and pair is not None:
                followups.append(_conditional_pair_followup(predicate, pair[1]))
                index += 2
                continue
        followup = _followup_for(sentence, head_source)
        if followup is None:
            leftover = sentences[index:]
            break
        followups.append(followup)
        index += 1

    if not followups and not radiance:
        return None
    if head_clause is not None and not all(f.kind == "controller" for f in followups):
        return None
    rest = None
    if leftover:
        rest = _parse_mixed_clauses(" ".join(leftover), for_spell=True)
        if rest is None:
            return None
    if any(f.needs_player for f in followups) and not re.search(
        r"player|opponent", phrase, re.IGNORECASE
    ):
        return None
    if any(f.needs_permanent for f in followups) and not re.search(
        r"creature|planeswalker|permanent|artifact|enchantment|land|any target",
        phrase,
        re.IGNORECASE,
    ):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        targets = _head_targets(game, spell, phrase)
        if not targets:
            return  # CR 608.2b: the one target is illegal; nothing happens.
        run = _Run(game, spell, targets[0])
        amount = amount_of(game, spell) if amount_of is not None else 0
        for followup in followups:
            if followup.referent_predicate is None or not isinstance(run.target, CardState):
                continue
            key, predicate = followup.referent_predicate
            holds = predicate is None or predicate(game, run.target)
            if followup.instead_amount is not None:
                if holds:
                    amount = followup.instead_amount
            elif key is not None:
                run.facts[id(key)] = holds
        if head_clause is not None:
            head_clause(game, spell)
        else:
            if radiance and isinstance(run.target, CardState):
                recipients: list[Any] = _radiance_group(game, run.target)
            else:
                recipients = [run.target]
            for recipient in recipients:
                run.dealt += game.deal_damage(recipient, amount, source=spell)
        for followup in followups:
            if followup.after is not None:
                followup.after(run)
        if rest is not None:
            for clause in rest:
                clause(game, spell)

    return effect


def _conditional_pair_followup(predicate: Any, pair_effect: Any) -> _Followup:
    """ "If `<that permanent is a Chandra planeswalker>`, you may discard a
    card. If you do, draw a card." - the whole pair gated on the target's
    quality as it was before the head ran (CR 608.2h)."""

    def after(run: _Run) -> None:
        if run.facts.get(id(after), False):
            pair_effect(run.game, run.spell)

    return _Followup(referent_predicate=(after, predicate), after=after, needs_permanent=True)


# ---------------------------------------------------------------------------
# The same sequence on a triggered or activated ability
# ---------------------------------------------------------------------------
#
# "When this creature enters, it deals 2 damage to any target and you gain 2
# life. If a player is dealt damage this way, they discard a card." (Sonic
# Shrieker). The head and the optional "and you gain N life" tail are one
# instruction (CR 608.2c); the rider asks what the head actually did to its
# target (CR 120.3a, CR 615.6), so a creature or planeswalker target, a
# prevented hit and an empty hand all end the sequence there.

_ABILITY_HEAD_RE = re.compile(
    rf"^(?P<src>[^.]+?) deals (?P<n>{COUNT}) damage to "
    rf"(?P<phrase>any target|target [^.]+?)(?: and you gain (?P<gain>{COUNT}) life)?$",
    re.IGNORECASE,
)


def damage_then_player_rider_ability_effect(effect_text: str) -> Any:
    """`_ABILITY_HEAD_RE`'s sentence plus "If a player is dealt damage this
    way, `<rider>`" as one ability effect, or None."""
    if "dealt damage this way" not in effect_text.lower():
        return None

    from .effects import (
        _plain_resolution_sentences,
        _strip_non_effect_preamble,
        _targets_understood,
    )

    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(effect_text))
    if len(sentences) != 2:
        return None
    head = _ABILITY_HEAD_RE.fullmatch(sentences[0].strip().rstrip("."))
    follow = _PLAYER_DEALT_DAMAGE_THIS_WAY_RE.fullmatch(sentences[1].strip().rstrip("."))
    if head is None or follow is None:
        return None
    amount = parse_count(head.group("n"))
    gain = parse_count(head.group("gain")) if head.group("gain") is not None else 0
    rider = damaged_player_rider(follow.group("rider"))
    if amount is None or gain is None or rider is None:
        return None
    if not _targets_understood(head.group("phrase"), allow_player_targets=True):
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        from ..models.player import Player

        source = ability.source_or_last_known(game)
        dealt_to: list[Player] = []
        for target in game.resolve_targets(ability):
            if game.deal_damage(target, amount, source=source) > 0 and isinstance(target, Player):
                dealt_to.append(target)
        if gain:
            game.gain_life(ability.controller, gain)
        from .decisions import source_id_of

        for player in dealt_to:
            rider(game, player, ability.source_name, source_id_of(ability))

    return effect


def public_card_ids(game: "Game") -> set[Any]:
    """Every card id now in a graveyard or in exile - taken just before an
    instruction that discards, so `newly_discarded` can tell what it moved."""
    return {card.id for player in game.players for card in player.graveyard} | {
        card.id for card in game.exile
    }


def newly_discarded(game: "Game", before: set[Any], username: str | None = None) -> list[CardState]:
    """The cards `username` (anyone, when `None`) discarded since `before` was
    taken, as their owner's cards: CR 701.9a's
    discard puts them in their owner's graveyard (or exile, for madness, CR
    702.35a), marked `discarded_by`. "That card" in the next sentence is this
    card (CR 608.2c), and its mana value is read off the card where it now is
    (CR 202.3; a land has no mana cost, so 0 - CR 202.3a)."""
    moved = [card for player in game.players for card in player.graveyard] + list(game.exile)
    return [
        card
        for card in moved
        if card.id not in before
        and card.discarded_by is not None
        and (username is None or card.owner == username)
    ]

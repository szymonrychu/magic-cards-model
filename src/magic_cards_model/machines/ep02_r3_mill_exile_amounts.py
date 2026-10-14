"""EP-02 R3 T3: mill / exile-the-top-X amounts and the referenced-stat
amounts that feed them.

    Target player mills cards equal to your life total.
    Up to one target player mills cards equal to this creature's power.
    Any number of target players each mill two cards.
    Any number of target players each mill cards equal to the number of cards
    in their graveyard.
    Destroy all creatures, then any number of target players each mill half
    their library, rounded down.

CR 701.17a: to mill a number of cards, a player puts that many cards from the
top of their library into their graveyard; with fewer cards in the library they
mill as many as possible. CR 107.1c: "any number of" targets is nought upwards
(the targeting reader already honours it). CR 107.1a: a "half" prints which
way it rounds. CR 608.2h: an amount is taken once, as the instruction is
applied, before any card moves.

The wording is `amount_sentences.parse_mill_clause`'s; this module adds the
subjects that sentence leaves open ("up to one target player", "any number of
target players each") and the "half their library" amount, and hooks them in as
one clause rung. The amount is read for each recipient through
`amount_sentences.recipient_amount`, so "their graveyard" is the recipient's own
and "your life total" the controller's.

Registered behind a cheap lowercase gate with memoised parsers, to stay inside
the classify budget.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..models.card import Color
from ..models.card_state import CardState
from ..models.mana import ManaCost, SymbolKind
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import COUNT, halve, parse_count
from .amount_sentences import (
    Amount,
    apply_mill,
    clean,
    controller_of,
    mill_players,
    parse_mill_clause,
    recipient_amount,
)
from .decisions import Decision, DecisionKind, source_id_of
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT
from .ep02_r1_referenced_stat import default_referent, parse_stat_phrase, stat_value
from .layers import (
    ContinuousEffect,
    Duration,
    Layer,
    Sublayer,
    grant_ability,
    only_this_incarnation,
)
from .layers.model import SetPower

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects._common import AbilityEffect, TargetedClause

# --------------------------------------------------------------------------
# "<who> mills <amount>": the subject and the amount
# --------------------------------------------------------------------------

_SUBJECT_RE = re.compile(
    r"^(?:(?P<quantity>up to one|any number of) )?(?P<who>target (?:player|opponent)s?)"
    r"(?: each)?$"
    r"|^(?P<plain>you|each player|each opponent|that player|they|enchanted player)(?: each)?$",
    re.IGNORECASE,
)
_HALF_LIBRARY_RE = re.compile(
    r"^(?P<subject>.+?) mills? half (?:their|your) library, rounded (?P<way>up|down)$",
    re.IGNORECASE,
)
_PLAYER_PLURAL_RE = re.compile(r"\bplayers\b|\bopponents\b", re.IGNORECASE)


def _recipients_word(subject: str) -> tuple[str, bool] | None:
    """The `amount_sentences.resolve_recipients` word `subject` names, and
    whether it targets: "up to one target player" and "any number of target
    players each" both read as "target player" (the targeting reader keeps the
    count, CR 107.1c)."""
    match = _SUBJECT_RE.fullmatch(clean(subject))
    if match is None:
        return None
    if match.group("plain") is not None:
        return match.group("plain").lower(), False
    word = _PLAYER_PLURAL_RE.sub(lambda m: m.group(0)[:-1], match.group("who").lower())
    return word, True


@functools.cache
def parse_mill_amount(text: str) -> tuple[str, Amount, bool] | None:
    """`(recipients word, amount, targets)` for a mill sentence whose subject
    is one of `_SUBJECT_RE`'s and whose amount is a fixed number, "cards equal
    to <expr>" or "half their library, rounded up|down", else `None`."""
    sentence = clean(text)
    lowered = sentence.lower()
    if "mill" not in lowered:
        return None
    if (half := _HALF_LIBRARY_RE.fullmatch(sentence)) is not None:
        named = _recipients_word(half.group("subject"))
        if named is None:
            return None
        round_up = half.group("way").lower() == "up"

        def half_library(_game: "Game", _obj: Any, who: Any) -> int:
            return halve(len(who.library), round_up=round_up)

        return named[0], half_library, named[1]
    clause = parse_mill_clause(sentence)
    if clause is None or clause.subject is None:
        return None
    named = _recipients_word(clause.subject)
    if named is None:
        return None
    if clause.kind == "x" and clause.expr is None:
        return None  # an announced X is the spell's own, read by the plain mill reader
    if clause.kind == "fixed":
        fixed = clause.n

        def fixed_amount(_game: "Game", _obj: Any, _who: Any) -> int:
            return fixed

        return named[0], fixed_amount, named[1]
    amount = recipient_amount(clause.expr or "")
    return None if amount is None else (named[0], amount, named[1])


@MIXED_CLAUSE.rung("s36", for_spell=FORWARD)
def _parse_mill_amount_clause(clause: str, *, for_spell: bool) -> "TargetedClause | None":
    """`parse_mill_amount`'s sentence as one clause, spell or ability."""
    if "mill" not in clause.lower():
        return None
    parsed = parse_mill_amount(clause)
    if parsed is None:
        return None
    who, amount, targets = parsed
    if targets:
        from .effects._common import _targets_understood

        subject = clean(clause).split(" mill", 1)[0]
        subject = re.sub(r" each$", "", subject, flags=re.IGNORECASE)
        if not _targets_understood(subject, count_agnostic=True, allow_player_targets=True):
            return None

    def effect(game: "Game", stack_object: Any) -> None:
        apply_mill(game, stack_object, who, amount)

    return effect


# --------------------------------------------------------------------------
# "Destroy target <permanent> if its mana value is equal to the amount of
# unspent mana you have"
# --------------------------------------------------------------------------

_DESTROY_IF_MV_EQUALS_UNSPENT_RE = re.compile(
    r"^destroy (?P<phrase>target .+?) if its mana value is equal to the amount of "
    r"unspent mana you have$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s36", for_spell=FORWARD)
def _parse_destroy_if_mana_value_equals_unspent_mana(
    clause: str, *, for_spell: bool
) -> "TargetedClause | None":
    """Destroy each legal target whose mana value (CR 202.3) equals the mana in
    the controller's pool (CR 106.4) as the instruction applies (CR 608.2c).
    The pool is counted once, before anything is destroyed (CR 608.2h)."""
    match = _DESTROY_IF_MV_EQUALS_UNSPENT_RE.fullmatch(clean(clause))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        unspent = game.player(controller_of(game, stack_object)).mana_pool.total
        for target in game.resolve_targets(stack_object):
            if (
                isinstance(target, CardState)
                and target.zone is Zone.BATTLEFIELD
                and game.characteristics_of(target).mana_value == unspent
            ):
                game.destroy(target)

    return effect


# --------------------------------------------------------------------------
# "you may have this creature's base power become <amount> until end of turn"
# --------------------------------------------------------------------------

_BASE_POWER_BECOME_RE = re.compile(
    r"^(?P<may>you may have )?(?P<subject>this creature|this permanent)['\u2019]s base power "
    r"become (?:equal to )?(?P<amount>.+?) until end of turn$",
    re.IGNORECASE,
)
_THAT_CREATURES_POWER_RE = re.compile(r"^that creature['\u2019]s power$", re.IGNORECASE)


@ABILITY_TEXT.rung("s8")
def _parse_base_power_become_clause(effect_text: str) -> "AbilityEffect | None":
    """CR 613.4b: a layer 7b set of the source's base power (toughness left
    alone) to "that creature's power" - the trigger's own event subject, read
    once as the ability resolves (CR 608.2h) - or to an amount expression such
    as "1 plus the greatest power among other creatures you control"."""
    match = _BASE_POWER_BECOME_RE.fullmatch(clean(effect_text))
    if match is None:
        return None
    amount_text = match.group("amount")
    optional = match.group("may") is not None
    from .effects.amounts import amount_expression
    from .effects.continuous import _base_pt_become_object, continuous_effects

    if _THAT_CREATURES_POWER_RE.fullmatch(amount_text):
        reader = None
    else:
        reader = amount_expression(amount_text)
        if reader is None:
            return None

    def effect(game: "Game", ability: Any) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if reader is None:
            referent = _base_pt_become_object(game, ability, "that creature")
            if referent is None:
                return
            if referent.zone is Zone.BATTLEFIELD:
                power = game.characteristics_of(referent).numeric_power
            else:
                power = referent.power or 0  # CR 608.2h: last known information
        else:
            power = reader(game, controller_of(game, ability), source, 0)
        if optional and not game.may(
            controller_of(game, ability),
            f"have {source.name}'s base power become {power} until end of turn",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        effects = continuous_effects(game)
        effects.add(
            ContinuousEffect(
                description=f"{ability.source_name}: {source.name} has base power {power}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.SET,
                timestamp=effects.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(source, source.zone_change_stamp),
                modification=SetPower(power=power),
            ),
            game,
        )

    return effect


# --------------------------------------------------------------------------
# "return to your hand the <quality> card in your graveyard with the greatest
# power. If two or more cards are tied for greatest power, you choose one."
# --------------------------------------------------------------------------

_RETURN_EXTREMUM_RE = re.compile(
    r"^return (?:to your hand )?(?:the )?(?P<quality>[a-z ]+?) card in your graveyard "
    r"with the (?P<extremum>greatest|least) (?P<stat>power|toughness|mana value)"
    r"(?: to your hand)?"
    r"(?:\. if two or more cards are tied for (?:greatest|least) (?:power|toughness|mana value), "
    r"you choose one of them)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s8")
def _parse_return_extremum_card_clause(effect_text: str) -> "AbilityEffect | None":
    """The card in the controller's graveyard with the greatest (or least)
    power, toughness or mana value, returned to hand; a tie is the
    controller's choice (CR 608.2d), and a single candidate is no choice at
    all. CR 208.5: a creature card whose power cannot be determined has power
    0; CR 202.3 mana value."""
    match = _RETURN_EXTREMUM_RE.fullmatch(clean(effect_text))
    if match is None:
        return None
    from .effects._common import _card_description_is_readable, _quality_matcher

    quality = match.group("quality").lower()
    if not _card_description_is_readable(quality):
        return None
    wanted = _quality_matcher(quality)
    greatest = match.group("extremum").lower() == "greatest"
    stat = match.group("stat").lower()

    def value_of(card: CardState) -> int:
        if stat == "mana value":
            return int(card.mana_value)
        raw = card.power if stat == "power" else card.toughness
        return int(raw) if isinstance(raw, int) else 0

    def effect(game: "Game", ability: Any) -> None:
        from .decisions import Decision, DecisionKind

        player = game.player(controller_of(game, ability))
        pool = [card for card in player.graveyard if wanted(card)]
        if not pool:
            return
        best = max(map(value_of, pool)) if greatest else min(map(value_of, pool))
        tied = [card for card in pool if value_of(card) == best]
        chosen = tied[0]
        if len(tied) > 1:
            picked = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"choose one of the {quality} cards tied for the "
                    f"{match.group('extremum').lower()} {stat}",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    exact=True,
                    cards=tuple(card.id for card in tied),
                )
            )
            by_id = {card.id: card for card in tied}
            chosen = next((by_id[i] for i in picked if i in by_id), tied[0])
        game.return_to_hand(chosen)

    return effect


# --------------------------------------------------------------------------
# "add mana equal to enchanted permanent's mana cost"
# --------------------------------------------------------------------------

_ADD_MANA_EQUAL_TO_COST_RE = re.compile(
    r"^add mana equal to (?P<host>enchanted (?:permanent|creature|land|artifact)|"
    r"equipped creature)['\u2019]s mana cost$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s8")
def _parse_add_mana_equal_to_attached_cost_clause(effect_text: str) -> "AbilityEffect | None":
    """The mana in the attached permanent's mana cost, symbol by symbol (CR 202.1):
    generic as colorless (CR 107.4b), a coloured symbol as that colour, a
    hybrid or Phyrexian symbol as one colour of the controller's choice
    (CR 608.2d), {X} as 0 (CR 202.3e) and an absent cost as nothing."""
    if _ADD_MANA_EQUAL_TO_COST_RE.fullmatch(clean(effect_text)) is None:
        return None
    from .effects.modal import _choose_mana_color

    def effect(game: "Game", ability: Any) -> None:
        source = ability.source(game)
        host = None if source is None else game.find_by_id(source.attached_to)
        if host is None or host.zone is not Zone.BATTLEFIELD or not host.mana_cost:
            return
        controller = game.player(controller_of(game, ability))
        for symbol in ManaCost.parse(host.mana_cost).symbols:
            if symbol.kind is SymbolKind.GENERIC:
                controller.mana_pool.add(Color.COLORLESS, symbol.amount)
            elif symbol.kind in (SymbolKind.COLORED, SymbolKind.MONOCOLORED_HYBRID):
                controller.mana_pool.add(symbol.colors[0])
            elif symbol.kind in (SymbolKind.HYBRID, SymbolKind.PHYREXIAN):
                color = _choose_mana_color(
                    game,
                    controller.username,
                    ability,
                    symbol.colors,
                    f"choose the colour of mana for {{{'/'.join(c.value for c in symbol.colors)}}}",
                )
                controller.mana_pool.add(color)
            elif symbol.kind is SymbolKind.SNOW:
                controller.mana_pool.add(Color.COLORLESS, 1, snow=True)

    return effect


# --------------------------------------------------------------------------
# An amount that reads the resolving object: "one plus the mana value of the
# sacrificed artifact", "its power", "that card's mana value", or any game
# amount `amount_expression` reads (CR 608.2h: taken once, as it resolves)
# --------------------------------------------------------------------------

_COUNT_PLUS_RE = re.compile(r"^(?P<n>\w+) plus (?P<rest>.+)$", re.IGNORECASE)


@functools.cache
def stack_amount(expression: str) -> "Callable[[Game, Any], int] | None":
    """`expression` as a reader of `(game, stack_object)`, or `None`.

    A referenced object's characteristic (`ep02_r1_referenced_stat`'s sacrificed
    / died / anaphoric referents, as they last existed) comes first; anything
    else is `amount_expression`'s, read for the resolving object's controller
    against its source."""
    text = clean(expression)
    if (plus := _COUNT_PLUS_RE.fullmatch(text)) is not None:
        count = parse_count(plus.group("n"))
        inner = stack_amount(plus.group("rest")) if count is not None else None
        if count is not None and inner is not None:
            return lambda game, obj: count + inner(game, obj)
    if (stat := parse_stat_phrase(text)) is not None:
        return lambda game, obj: stat_value(default_referent(game, obj, stat.anchor), stat.stat)
    from .effects.amounts import amount_expression

    reader = amount_expression(text)
    if reader is None:
        return None

    def read(game: "Game", obj: Any) -> int:
        source = obj if isinstance(obj, CardState) else obj.source(game)
        return reader(game, controller_of(game, obj), source, 0)

    return read


# --------------------------------------------------------------------------
# "exile the top X cards of <whose> library, where X is <amount>" and
# "exile cards equal to <amount> from the top of <whose> library"
# --------------------------------------------------------------------------

_EXILE_TOP_AMOUNT_RE = re.compile(
    r"^exile (?:the top x cards of (?P<whose_x>your|target opponent's|target player's) library, "
    r"where x is (?P<where_x>.+)"
    r"|cards equal to (?P<equal>.+?) from the top of (?P<whose_eq>your|target opponent's|"
    r"target player's|its owner's) library)$",
    re.IGNORECASE,
)


def parse_exile_top_amount_antecedent(
    clause: str,
) -> "tuple[Callable[..., list[CardState]], bool] | None":
    """The exile half of an exile-then-play instruction whose count is an
    amount reading the resolving object (see `stack_amount`). The cards stay
    owned by their library's owner (CR 108.3); a library shorter than the
    count gives what it has (CR 406.2 exiles what is there). "Its owner's" is
    the owner of the trigger's event subject, as it last existed (CR 603.10a)."""
    match = _EXILE_TOP_AMOUNT_RE.fullmatch(clean(clause))
    if match is None:
        return None
    whose = (match.group("whose_x") or match.group("whose_eq")).lower()
    reader = stack_amount(match.group("where_x") or match.group("equal"))
    if reader is None:
        return None

    def exile_top(game: "Game", stack_object: Any) -> list[CardState]:
        if whose == "your":
            players = [game.player(controller_of(game, stack_object))]
        elif whose == "its owner's":
            event = getattr(stack_object, "event", None)
            subject = None if event is None else game.find_by_id(event.subject_id)
            players = [] if subject is None else [game.player(subject.owner)]
        else:
            players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        count = reader(game, stack_object)
        exiled: list[CardState] = []
        for player in players:
            for _ in range(count):
                if not player.library:
                    break
                exiled.append(game.exile_permanent(player.library[0]))
        return exiled

    return exile_top, True


# --------------------------------------------------------------------------
# Amounts read off the cards a mill just moved
# --------------------------------------------------------------------------

_MILLED_AGGREGATE = (
    r"(?:the (?P<agg>greatest) mana value among the milled cards"
    r"|the (?P<tot>total) mana value of (?:those|the milled) cards)"
)


def _milled_mana_value(text: str) -> "Callable[[list[CardState]], int] | None":
    match = re.fullmatch(_MILLED_AGGREGATE, text, re.IGNORECASE)
    if match is None:
        return None
    if match.group("agg"):
        return lambda cards: max((int(card.mana_value) for card in cards), default=0)
    return lambda cards: sum(int(card.mana_value) for card in cards)


_CHOOSE_ANY_TARGET_MILL_DAMAGE_RE = re.compile(
    r"^choose any target, then mill (?P<n>\w+) cards\. this \w+ deals damage to that "
    r"(?:permanent or player|creature or player|target) equal to (?P<amount>.+)$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s8")
def _parse_mill_then_damage_by_milled_clause(effect_text: str) -> "AbilityEffect | None":
    """CR 701.17a mill, then CR 120.3 damage equal to an aggregate of the
    cards just milled (CR 608.2c), dealt by the source (CR 120.7) to the
    target chosen on activation. Heretic's Punishment: "greatest mana value
    among the milled cards"."""
    match = _CHOOSE_ANY_TARGET_MILL_DAMAGE_RE.fullmatch(clean(effect_text))
    count = None if match is None else parse_count(match.group("n"))
    aggregate = None if match is None else _milled_mana_value(match.group("amount"))
    if match is None or count is None or aggregate is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        from .effects.library import _mill

        milled = _mill(game, game.player(controller_of(game, ability)), count)
        source = ability.source_or_last_known(game)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, aggregate(milled), source=source)

    return effect


_MAY_HAVE_YOU_DRAW_OR_MILL_RE = re.compile(
    r"^target opponent may have you draw (?P<d>\w+) cards\. if the player doesn'?t, you mill "
    r"(?P<m>\w+) cards, then this \w+ deals damage to that player equal to (?P<amount>.+)$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s8")
def _parse_opponent_may_have_you_draw_else_mill_damage(effect_text: str) -> "AbilityEffect | None":
    """Combustible Gearhulk: the target opponent chooses (CR 608.2d) whether
    the controller draws; if not, the controller mills and the source deals
    damage to that opponent equal to the milled cards' total mana value."""
    match = _MAY_HAVE_YOU_DRAW_OR_MILL_RE.fullmatch(clean(effect_text))
    if match is None:
        return None
    draw_count, mill_count = parse_count(match.group("d")), parse_count(match.group("m"))
    aggregate = _milled_mana_value(match.group("amount"))
    if draw_count is None or mill_count is None or aggregate is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        from .effects.library import _mill

        controller = game.player(controller_of(game, ability))
        for opponent in [t for t in game.resolve_targets(ability) if isinstance(t, Player)]:
            if game.may(
                opponent,
                f"have {controller.username} draw {draw_count} cards",
                source=ability.source_name,
                source_id=source_id_of(ability),
            ):
                game.draw_cards(controller, draw_count)
                continue
            milled = _mill(game, controller, mill_count)
            game.deal_damage(opponent, aggregate(milled), source=ability.source_or_last_known(game))

    return effect


# --------------------------------------------------------------------------
# "Target player mills X cards. If this spell was cast from a graveyard, that
# player mills twice that many cards instead."
# --------------------------------------------------------------------------

_MILL_X_DOUBLED_FROM_GRAVEYARD_RE = re.compile(
    r"^target player mills x cards\. if this spell was cast from a graveyard, that player "
    r"mills (?P<times>twice|three times) that many cards instead$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_mill_x_doubled_from_graveyard(
    spell_text: str,
) -> "Callable[[Game, CardState], None] | None":
    """CR 107.3a X milled (CR 701.17a); the cast record's origin zone
    (CR 601.2a) says whether it was cast from a graveyard (flashback,
    CR 702.34a), in which case the multiple replaces the plain amount."""
    match = _MILL_X_DOUBLED_FROM_GRAVEYARD_RE.fullmatch(clean(spell_text))
    if match is None:
        return None
    multiple = 2 if match.group("times").lower() == "twice" else 3

    def effect(game: "Game", spell: CardState) -> None:
        record = game.cast_record_of(spell)
        x_value = 0 if record is None else record.x_value
        from_graveyard = record is not None and record.origin_zone is Zone.GRAVEYARD
        amount = x_value * multiple if from_graveyard else x_value
        for target in game.resolve_targets(spell):
            if isinstance(target, Player):
                mill_players(game, [target], [amount])

    return effect


# --------------------------------------------------------------------------
# Discover with a follow-up amount, and the exile-the-top loops
# --------------------------------------------------------------------------

_DISCOVER_THEN_TOKENS_RE = re.compile(
    r"^discover (?P<n>\d+)\. if the discovered card'?s mana value is less than (?P=n), "
    r"create a number of tapped (?P<token>[a-z]+) tokens equal to the difference$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_discover_then_tokens_for_the_difference(
    spell_text: str,
) -> "Callable[[Game, CardState], None] | None":
    """CR 701.57a discover N, then CR 701.57c's "discovered card" (the final
    card exiled, only when its mana value is N or less) sets the CR 608.2h
    amount: N minus its mana value, as tapped predefined tokens (CR 111.10).
    With no discovered card there is no difference, so no tokens."""
    match = _DISCOVER_THEN_TOKENS_RE.fullmatch(clean(spell_text))
    if match is None:
        return None
    n = int(match.group("n"))
    token = match.group("token").capitalize()

    def effect(game: "Game", spell: CardState) -> None:
        from ..models.token import PREDEFINED, create_predefined_tokens
        from .keywords import discover

        if token not in PREDEFINED:
            return
        controller = controller_of(game, spell)
        result = discover(
            game, controller, n, source_name=spell.name, source_id=source_id_of(spell)
        )
        if result.hit is not None and result.hit.mana_value < n:
            create_predefined_tokens(
                game, token, controller, n - int(result.hit.mana_value), tapped=True
            )

    return effect


_OWNER_SHUFFLES_THEN_DISCOVERS_RE = re.compile(
    r"^the owner of (?P<phrase>target .+?) shuffles it into their library\. "
    r"then that player discovers x, where x is its mana value$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_owner_shuffles_target_then_discovers_its_mana_value(
    spell_text: str,
) -> "Callable[[Game, CardState], None] | None":
    """The owner of the target permanent shuffles it into their library
    (CR 701.24a), then discovers X (CR 701.57a) for X its mana value as it
    last existed on the battlefield (CR 608.2h: taken before it moves)."""
    from .effects._common import _targets_understood

    match = _OWNER_SHUFFLES_THEN_DISCOVERS_RE.fullmatch(clean(spell_text))
    if match is None or not _targets_understood(
        match.group("phrase"), count_agnostic=True, battlefield_only=True
    ):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        from .keywords import discover

        for target in game.resolve_targets(spell):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            owner = target.owner
            x_value = int(target.mana_value)
            game.put_cards_into_library([target])
            game.shuffle_library(owner)
            discover(game, owner, x_value, source_name=spell.name, source_id=source_id_of(spell))

    return effect


_EXILE_TOP_LOOP_RE = re.compile(
    r"^(?P<exiles>(?:exile the top card of your library\. ?){2,})"
    r"if the last card exiled isn'?t a land card, repeat this process\. "
    r"create an? (?P<desc>.+?) tokens? for each nonland card exiled this way$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_exile_top_loop_then_tokens_per_nonland(
    spell_text: str,
) -> "Callable[[Game, CardState], None] | None":
    """Exile the top card N times, repeat the whole process while the last
    card exiled is not a land (CR 406.2 exile, CR 701.20a face up), then a
    token per nonland card exiled this way (CR 111.2). A library that runs
    out ends the process."""
    from .effects.tokens import _parse_generic_token_descriptor

    match = _EXILE_TOP_LOOP_RE.fullmatch(clean(spell_text))
    if match is None:
        return None
    batch_size = match.group("exiles").lower().count("exile the top card")
    definition = _parse_generic_token_descriptor(match.group("desc").split(), None)
    if definition is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        from ..models.token import create_tokens
        from .keywords import exile_until

        controller = controller_of(game, spell)
        library_owner = game.player(controller)
        nonland = 0
        while True:
            batch = exile_until(
                game,
                library_owner,
                lambda _state, exiled: len(exiled) >= batch_size,
                source_name=spell.name,
            )
            nonland += sum(1 for state in batch if not state.card.is_land)
            if not batch or batch[-1].card.is_land:
                break
        if nonland:
            create_tokens(game, definition, controller, nonland)

    return effect


_EXILE_UNTIL_NONLAND_TO_HAND_RE = re.compile(
    r"^exile cards from the top of your library until you exile a nonland card, then put "
    r"that card into your hand\. if the card'?s mana value is (?P<n>\d+) or greater, repeat "
    r"this process\. (?:this \w+|[^.]+?) deals (?P<d>\d+) damage to you for each card put "
    r"into your hand this way$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s8")
def _parse_exile_until_nonland_to_hand_repeat_damage(effect_text: str) -> "AbilityEffect | None":
    """Exile until a nonland card (CR 406.2), put it into hand, repeat while
    its mana value is at least N, then damage to the controller per card put
    into hand (CR 120.3). The exiled lands stay in exile."""
    match = _EXILE_UNTIL_NONLAND_TO_HAND_RE.fullmatch(clean(effect_text))
    if match is None:
        return None
    threshold, per_card = int(match.group("n")), int(match.group("d"))

    def effect(game: "Game", ability: Any) -> None:
        from .keywords import exile_until

        player = game.player(controller_of(game, ability))
        taken = 0
        while True:
            exiled = exile_until(
                game,
                player,
                lambda state, _: not state.card.is_land,
                source_name=ability.source_name,
            )
            if not exiled or exiled[-1].card.is_land:
                break
            hit = exiled[-1]
            game.exile.remove(hit)
            player.add(hit, Zone.HAND)
            taken += 1
            if hit.mana_value < threshold:
                break
        if taken:
            game.deal_damage(player, taken * per_card, source=ability.source_or_last_known(game))

    return effect


# --------------------------------------------------------------------------
# Anzrag's Rampage
# --------------------------------------------------------------------------


def choose_one_card_optionally(
    game: "Game", player: Player, candidates: list[CardState], what: str, obj: Any
) -> CardState | None:
    """CR 608.2d: "you may <do something with> a <card> exiled this way" - a
    yes/no first (declined, or with nothing to pick, is no card), then which
    card. Shared by every reader here that offers one card out of a pile."""
    if not candidates:
        return None
    source = getattr(obj, "source_name", None) or obj.name
    if not game.may(player, what, source=source, source_id=source_id_of(obj)):
        return None
    chosen = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=f"choose a card to {what}",
            source=source,
            source_id=source_id_of(obj),
            amount=1,
            cards=tuple(state.id for state in candidates),
            card_labels=tuple(state.name for state in candidates),
        )
    )
    by_id = {state.id: state for state in candidates}
    return by_id[chosen[0]] if chosen else None


_DESTROY_ALL_NOT_YOURS_THEN_EXILE_RE = re.compile(
    r"^destroy all (?P<group>[a-z]+) you don'?t control, then exile the top x cards of your "
    r"library, where x is the number of (?P=group) that were put into graveyards from the "
    r"battlefield this turn\. you may put an? (?P<kind>[a-z]+) card exiled this way onto the "
    r"battlefield\. it gains (?P<keyword>[a-z]+)\. return it to your hand at the beginning of "
    r"the next end step$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_destroy_all_then_exile_top_x_put_one_onto_battlefield(
    spell_text: str,
) -> "Callable[[Game, CardState], None] | None":
    """Destroy every permanent of a type the controller does not control
    (CR 701.8a), exile the top X cards where X counts the permanents of that
    type put into graveyards from the battlefield this turn (CR 400.6 -
    `Game.graveyard_arrivals_this_turn`), optionally put one exiled card of a
    type onto the battlefield with a keyword, and return it to hand at the
    beginning of the next end step (CR 603.7a, CR 603.7c: only if it is still
    the same object)."""
    from ..models.card import Type
    from .abilities import TriggerEvent
    from .delayed import DelayedTrigger, return_subject_to_hand
    from .effects.continuous import continuous_effects
    from .layers.group_grants import parse_group
    from .turn import Step

    match = _DESTROY_ALL_NOT_YOURS_THEN_EXILE_RE.fullmatch(clean(spell_text))
    if match is None:
        return None
    spec = parse_group(match.group("group"))
    kind = parse_group(match.group("kind") + "s")
    if (
        spec is None
        or kind is None
        or len(spec["all_types"]) != 1
        or len(kind["all_types"]) != 1
        or any(spec[k] for k in ("any_types", "not_types", "any_subtypes", "any_colors"))
    ):
        return None
    group_type: Type = spec["all_types"][0]
    card_type: Type = kind["all_types"][0]
    keyword = match.group("keyword")

    def effect(game: "Game", spell: CardState) -> None:
        from .keywords import exile_until

        controller = controller_of(game, spell)
        for permanent in list(game.battlefield):
            if (
                permanent.controller != controller
                and group_type in game.characteristics_of(permanent).types
                and permanent.zone is Zone.BATTLEFIELD
            ):
                game.destroy(permanent)
        amount = sum(
            1
            for arrival in game.graveyard_arrivals_this_turn
            if arrival.origin_zone is Zone.BATTLEFIELD
            and arrival.permanent_types is not None
            and group_type in arrival.permanent_types
        )
        player = game.player(controller)
        exiled = (
            exile_until(
                game, player, lambda _state, taken: len(taken) >= amount, source_name=spell.name
            )
            if amount > 0
            else []
        )
        candidates = [state for state in exiled if card_type in state.types]
        chosen = choose_one_card_optionally(
            game,
            player,
            candidates,
            f"put a {card_type.value} card exiled this way onto the battlefield",
            spell,
        )
        if chosen is None:
            return
        put = game.put_onto_battlefield(chosen, controller)
        if put.zone is not Zone.BATTLEFIELD:
            return
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{spell.name}: {put.name} gains {keyword}",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.INDEFINITE,
                selector=only_this_incarnation(put, put.zone_change_stamp),
                modification=grant_ability(keyword.title()),
            )
        )
        game.create_delayed_trigger(
            DelayedTrigger(
                text="Return it to your hand at the beginning of the next end step.",
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.END_STEP,
                controller=controller,
                source_id=spell.id,
                source_name=spell.name,
                subject_id=put.id,
                expected_zone=Zone.BATTLEFIELD,
                expected_stamp=put.zone_change_stamp,
                effect=return_subject_to_hand,
            )
        )

    return effect


# --------------------------------------------------------------------------
# "Return [up to] N <quality> cards from your graveyard to your hand"
# --------------------------------------------------------------------------

_RETURN_CARDS_FROM_GRAVEYARD_TO_HAND_RE = re.compile(
    rf"^return (?P<upto>up to )?(?P<n>{COUNT}) (?P<quality>[a-z ,/-]+?) cards? "
    r"from your graveyard to your hand$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_return_cards_from_your_graveyard_to_hand_clause(
    clause: str, *, for_spell: bool
) -> "TargetedClause | None":
    """A choice made as the clause resolves (CR 608.2d), not a target: the
    controller picks N (at most N after "up to", CR 107.1c) matching cards in
    their own graveyard, as it is when the clause applies - so cards a
    preceding clause just milled are eligible (CR 608.2c)."""
    from .effects._common import _quality_matcher

    match = _RETURN_CARDS_FROM_GRAVEYARD_TO_HAND_RE.fullmatch(clause.strip().rstrip("."))
    count = None if match is None else parse_count(match.group("n"))
    if match is None or not count:
        return None
    matches = _quality_matcher(match.group("quality").replace("and/or", "or"))
    exact = match.group("upto") is None

    def effect(game: "Game", stack_object: Any) -> None:
        player = game.player(controller_of(game, stack_object))
        candidates = [state for state in player.cards_in(Zone.GRAVEYARD) if matches(state)]
        wanted = min(count, len(candidates))
        if wanted <= 0:
            return
        source = getattr(stack_object, "source_name", None) or stack_object.name
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose {'' if exact else 'up to '}{wanted} card(s) to return to your hand",
                source=source,
                source_id=source_id_of(stack_object),
                amount=wanted,
                exact=exact,
                cards=tuple(state.id for state in candidates),
                card_labels=tuple(state.name for state in candidates),
            )
        )
        by_id = {state.id: state for state in candidates}
        for card_id in chosen:
            game.return_to_hand(by_id[card_id])

    return effect

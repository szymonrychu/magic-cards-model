"""EP-02 R3 T2: counter amounts and the keywords that put counters on a creature.

Fabricate (CR 702.123a): "When this permanent enters, you may put N +1/+1
counters on it. If you don't, create N 1/1 colorless Servo artifact creature
tokens." Each instance triggers separately (CR 702.123b).
"""

import re
from typing import TYPE_CHECKING

from ..models.card import Type
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .abilities import KeywordAbility, TriggeredAbility, TriggerEvent, TriggerWord
from .amount_sentences import parse_put_counters
from .decisions import Decision, DecisionKind, source_id_of
from .layers import is_genuine_resolution_layer_sentence
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES
from .effects._common import AbilityEffect, TargetedClause, _targets_understood
from .effects.amounts import _for_each_multiplier
from .effects.counters import _counter_kind
from .effects.tokens import _parse_token_clause

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack, StackObject

_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def fabricate_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.123a, written out as the triggered ability it stands for."""
    from .keywords import _expansion

    count = ability.count if ability.count is not None else 1
    quantity = _WORDS.get(count, str(count))
    counters = "counter" if count == 1 else "counters"
    servos = "Servo artifact creature token" if count == 1 else "Servo artifact creature tokens"
    return _expansion(
        ability,
        keyword="fabricate",
        word=TriggerWord.WHEN,
        condition="this permanent enters",
        effect=(
            f"you may put {quantity} +1/+1 {counters} on it. "
            f"If you don't, create {quantity} 1/1 colorless {servos}"
        ),
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


# -- "Exile a creature with the greatest power among creatures target opponent controls."

_GROUP_EXTREMUM_REMOVAL_RE = re.compile(
    r"^(?P<verb>exile|destroy) an? creature with the (?P<dir>greatest|least) "
    r"(?P<stat>power|toughness) among creatures "
    r"(?P<who>target opponent|target player) controls\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_remove_extremum_creature_of_target_player(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Exile a creature with the greatest power among creatures target
    opponent controls." (Fall of the Impostor III): the player is the target
    (CR 115.1), the creature is not (CR 115.10a), so hexproof on it stops
    nothing. The extremum is taken as the effect resolves (CR 608.2h); a tie
    for it is the ability controller's choice, since "a creature" is theirs to
    pick (CR 608.2d)."""
    if " among creatures " not in clause:
        return None
    match = _GROUP_EXTREMUM_REMOVAL_RE.fullmatch(clause.strip())
    if match is None or not _targets_understood(f"{match.group('who')}", allow_player_targets=True):
        return None
    greatest = match.group("dir").lower() == "greatest"
    stat = match.group("stat").lower()
    exiling = match.group("verb").lower() == "exile"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        pool = [
            permanent
            for player in players
            for permanent in game.permanents_controlled_by(player.username)
            if game.characteristics_of(permanent).is_creature
        ]
        if not pool:
            return

        def value(permanent) -> int:
            number = game.power_of(permanent) if stat == "power" else game.toughness_of(permanent)
            return number if number is not None else 0

        bound = (max if greatest else min)(value(permanent) for permanent in pool)
        tied = [permanent for permanent in pool if value(permanent) == bound]
        pick = tied[0]
        if len(tied) > 1:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt=f"choose a creature with the {match.group('dir').lower()} {stat}",
                    source=getattr(stack_object, "source_name", None) or stack_object.name,
                    amount=1,
                    exact=True,
                    cards=tuple(permanent.id for permanent in tied),
                    source_id=source_id_of(stack_object),
                )
            )
            by_id = {permanent.id: permanent for permanent in tied}
            pick = by_id.get(chosen_ids[0]) if chosen_ids else tied[0]
        if pick.zone is Zone.BATTLEFIELD:
            if exiling:
                game.exile_permanent(pick)
            else:
                game.destroy(pick)

    return effect


# -- "Create a <token>, then put N <kind> counters on it for each <thing>."

_THEN_PUT_RE = re.compile(
    r"^(?P<create>create .+?)(?:,|\.)\s+(?:and )?then put (?P<put>.+)$", re.IGNORECASE
)
_THAT_TOKEN_RE = re.compile(r"^(?:that token|it|each of them)$", re.IGNORECASE)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_create_then_put_counters_for_each(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """ "Create a 2/2 ... token, then put two +1/+1 counters on that token for
    each spell you've cast this turn other than the first." (Outlaw Stitcher):
    the counters go on the token(s) the first instruction just made (CR 608.2c,
    instructions in order), `N` of them per counted thing, the count taken once
    as the instruction applies (CR 608.2h). Without a "for each" it is the
    plain "put N counters on it" riding on the new token."""
    if " then put " not in text.lower() or " token" not in text.lower():
        return None
    split = _THEN_PUT_RE.fullmatch(" ".join(text.strip().split()))
    if split is None:
        return None
    put = parse_put_counters(f"put {split.group('put').rstrip('.')}")
    if put is None or put.x or _THAT_TOKEN_RE.fullmatch(put.on) is None:
        return None
    if put.each is not None and "this way" in put.each.lower():
        return None  # the this-way ledger's count (ep02_r1_this_way_counts) is not a for-each
    reader = _for_each_multiplier(put.each) if put.each is not None else None
    if put.each is not None and reader is None:
        return None
    create = _parse_token_clause(split.group("create").rstrip(".").strip(), for_spell=for_spell)
    if create is None:
        return None
    kind = _counter_kind(put.kind)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        before = {existing.id for existing in game.battlefield}
        create(game, stack_object)
        created = [state for state in game.battlefield if state.id not in before]
        amount = put.n
        if reader is not None:
            controller = game.controller_of(stack_object).username
            amount *= reader(game, controller, source_id_of(stack_object))
        if amount <= 0:
            return
        for token in created:
            game.add_counters(token, kind, amount)

    return [effect]


# -- "Put a +1/+1 counter on it for each other Zombie that entered the
# battlefield under your control this turn."

_TYPE_WORDS = frozenset(kind.value.lower() for kind in Type)
_ENTERED_THIS_TURN_COUNTERS_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on it for each other "
    r"(?P<what>[a-z]+) that entered the battlefield under your control this turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_counters_on_entering_object_for_each_other_entered(
    effect_text: str,
) -> AbilityEffect | None:
    """Geralf, the Fleshwright: "Whenever a Zombie you control enters, put a
    +1/+1 counter on it for each other Zombie that entered the battlefield
    under your control this turn." "It" is the entering object (the trigger
    event's subject); the count is `Game.turn_count`'s ledger of what entered
    for its controller this turn (still true of ones that have since left,
    CR 603.6a), less the subject itself, taken as the ability resolves
    (CR 608.2h)."""
    if "that entered the battlefield under your control this turn" not in effect_text.lower():
        return None
    match = _ENTERED_THIS_TURN_COUNTERS_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None:
        return None
    unit = parse_count(match.group("n"))
    if unit is None:
        return None
    kind = _counter_kind(match.group("kind"))
    what = match.group("what").lower()
    fact = f"entered_type:{what}" if what in _TYPE_WORDS else f"entered_subtype:{what}"

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        event = ability.event
        subject = game.find_by_id(event.subject_id) if event and event.subject_id else None
        if subject is None or subject.zone is not Zone.BATTLEFIELD:
            return
        others = game.turn_count(fact, ability.controller) - 1
        if others > 0:
            game.add_counters(subject, kind, unit * others)

    return effect


# -- "Search your library for a basic land card, put it onto the battlefield
# tapped, then shuffle. That land becomes a 0/0 green and blue Fractal creature
# that's still a land. Put a +1/+1 counter on it for each land you had enter
# the battlefield under your control this turn."

_SEARCH_ANIMATE_COUNT_RE = re.compile(
    r"^search your library for an? (?P<quality>[a-z ]+?) card, put it onto the battlefield "
    r"tapped, then shuffle\.\s+that land becomes (?P<becomes>an? .+? creature) that's still "
    r"an? (?P<still>[a-z]+)\.\s+put (?P<n>{count}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"it for each land you had enter the battlefield under your control this turn\.?$".replace(
        "{count}", COUNT
    ),
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_search_animate_then_count_counters(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """Emergent Sequence: the found land (CR 701.23a, "that land" is the card
    the search put onto the battlefield, CR 400.7) becomes the stated creature
    for good (CR 611.2a: no duration, CR 205.1b: "still a land"), and gets a
    counter per land that entered under its controller's control this turn
    (CR 608.2c, in order; `Game.lands_entered_this_turn` counts the found land
    itself, which entered as the first instruction ran)."""
    if "that land becomes" not in text.lower():
        return None
    match = _SEARCH_ANIMATE_COUNT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    unit = parse_count(match.group("n"))
    quality = _quality_matcher_for(match.group("quality"))
    if unit is None or quality is None:
        return None
    animation = f"It becomes {match.group('becomes')}. It's still a {match.group('still')}."
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .effects import continuous_effects, layer_context_for

        controller = game.controller_of(stack_object)
        found = game.search_library(
            controller,
            quality,
            count=1,
            optional=False,
            shuffle=True,
            source=stack_object.name,
            source_id=source_id_of(stack_object),
        )
        if not found:
            return
        land = found[0]
        game.put_onto_battlefield(land, controller.username, tapped=True)
        if land.zone is not Zone.BATTLEFIELD:
            return
        continuous_effects(game).create(
            stack_object,
            targets=[land],
            context=layer_context_for(game, controller),
            ability_text=animation,
            game=game,
        )
        entered = game.lands_entered_this_turn.get(controller.username, 0)
        if entered > 0:
            game.add_counters(land, kind, unit * entered)

    return [effect]


def _quality_matcher_for(quality: str):
    from .effects import _quality_matcher, _search_quality_is_readable

    if not _search_quality_is_readable(quality):
        return None
    return _quality_matcher(quality)


# -- "for each creature you control with power greater than that creature's base
# power, put a number of +1/+1 counters on that creature equal to the difference."

_POWER_OVER_BASE_RE = re.compile(
    r"^for each creature you control with power greater than that creature's base power, "
    r"put a number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters on that creature equal to "
    r"the difference\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_counters_equal_to_power_over_base(effect_text: str) -> AbilityEffect | None:
    """Sovereign Okinec Ahau. CR 208.4b: a creature's base power is its power
    before counters and +X/+Y effects (sublayers 7c and 7d); the difference
    between its power now and that is read once for each creature as the
    ability resolves (CR 608.2h), all of them before any counter lands, so
    one creature's new counters never feed another's difference."""
    if "greater than that creature's base power" not in effect_text.lower():
        return None
    match = _POWER_OVER_BASE_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        base = game.base_power_toughness_board()
        board = game.computed_board()
        gains = []
        for permanent in game.permanents_controlled_by(ability.controller):
            chars = board.of(permanent)
            if not chars.is_creature:
                continue
            difference = chars.numeric_power - base.of(permanent).numeric_power
            if difference > 0:
                gains.append((permanent, difference))
        for permanent, difference in gains:
            game.add_counters(permanent, kind, difference)

    return effect


# -- "Put a +1/+1 counter on each other creature you control. You gain 1 life for
# each of those creatures."

_COUNTER_EACH_OTHER_GAIN_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each other creature you "
    rf"control\.\s+you gain (?P<life>{COUNT}) life for each of those creatures\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_counter_on_each_other_creature_then_gain_per_creature(
    effect_text: str,
) -> AbilityEffect | None:
    """Bounding Felidar. "Those creatures" are the ones the first instruction
    put counters on (CR 608.2c, in order), so the life gained is `N` per
    creature that was in that group as it resolved (CR 608.2h)."""
    if " for each of those creatures" not in effect_text.lower():
        return None
    match = _COUNTER_EACH_OTHER_GAIN_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None:
        return None
    unit = parse_count(match.group("n"))
    life = parse_count(match.group("life"))
    if unit is None or life is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        source = ability.source(game)
        board = game.computed_board()
        group = [
            permanent
            for permanent in game.permanents_controlled_by(ability.controller)
            if permanent is not source and board.of(permanent).is_creature
        ]
        for permanent in group:
            game.add_counters(permanent, kind, unit)
        if group:
            game.gain_life(game.player(ability.controller), life * len(group))

    return effect


# -- "create half X Food tokens, rounded up."

_HALF_TOKENS_RE = re.compile(
    r"^create half (?P<amount>X|\d+) (?P<token>.+?) tokens?, rounded (?P<direction>up|down)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_create_half_x_tokens(effect_text: str) -> AbilityEffect | None:
    """The Goose Mother: CR 107.1a, a half that is not a whole number is
    rounded as the card says ("rounded up"); X is the value an enters trigger
    takes from the spell that became it (CR 107.3m), already written into the
    text as the ability resolves. The token itself is read by the token
    clause reader, once per unit."""
    if " rounded " not in effect_text.lower() or "create half " not in effect_text.lower():
        return None
    match = _HALF_TOKENS_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None or match.group("amount").upper() == "X":
        return None if match is None else _unresolved_x_effect
    template = _parse_token_clause(f"create a {match.group('token')} token", for_spell=False)
    if template is None:
        return None
    whole = int(match.group("amount"))
    times = (whole + 1) // 2 if match.group("direction").lower() == "up" else whole // 2

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        for _ in range(times):
            template(game, ability)

    return effect


def _unresolved_x_effect(game: "Game", ability: "AbilityOnStack") -> None:
    """X with no value written in (CR 107.3b: it is 0), so half of it makes
    nothing."""


# -- "This Vehicle becomes an artifact creature. Put a +1/+1 counter on it for each
# Mount and/or Vehicle you control other than this Vehicle."

_BECOMES_THEN_COUNTERS_RE = re.compile(
    r"^(?P<becomes>this [a-z]+ becomes an? [a-z ]+? creature)\.\s+"
    rf"(?P<put>put (?:{COUNT}) (?:\+1/\+1|-1/-1|[a-z]+) counters? on it for each .+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_becomes_creature_then_counters_for_each(effect_text: str) -> AbilityEffect | None:
    """Spire Mechcycle's exhaust ability. The source becomes the creature for
    good (CR 611.2a, no duration), then "it" is that same permanent (CR 608.2c,
    in order) and gets `N` counters per counted thing, the count taken once as
    the instruction applies (CR 608.2h)."""
    if " becomes " not in effect_text.lower() or " counter" not in effect_text.lower():
        return None
    match = _BECOMES_THEN_COUNTERS_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None:
        return None
    animation = f"{match.group('becomes')}."
    put = parse_put_counters(match.group("put"))
    if put is None or put.x or put.on.lower() != "it" or put.each is None:
        return None
    reader = _for_each_multiplier(put.each)
    if reader is None or not is_genuine_resolution_layer_sentence(animation):
        return None
    kind = _counter_kind(put.kind)

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        from .effects import continuous_effects, layer_context_for

        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        continuous_effects(game).create(
            source,
            targets=[source],
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=animation,
            game=game,
        )
        amount = put.n * reader(game, ability.controller, source_id_of(ability))
        if amount > 0:
            game.add_counters(source, kind, amount)

    return effect


# -- "Look at the top six cards of your library. Put up to two land cards from among
# them onto the battlefield tapped and the rest on the bottom of your library in a
# random order. If you put fewer than two lands onto the battlefield this way,
# proliferate a number of times equal to the difference."

_LOOK_PUT_PROLIFERATE_RE = re.compile(
    rf"^look at the top (?P<n>{COUNT}) cards of your library\.\s+put up to (?P<k>{COUNT}) "
    r"(?P<kind>[a-z]+) cards from among them onto the battlefield tapped and the rest on the "
    r"bottom of your library in a random order\.\s+if you put fewer than (?P=k) (?P=kind)s onto "
    r"the battlefield this way, proliferate a number of times equal to the difference\.?"
    r"(?:\s*\([^)]*\))?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_look_put_lands_then_proliferate_for_shortfall(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """Expand the Sphere. CR 608.2d: the controller picks "up to" two of the
    land cards (zero is legal); CR 608.2c: the rest go to the bottom first-
    named instruction by first, then the shortfall is counted from what
    actually reached the battlefield "this way" (a land a replacement kept
    off it does not count), and CR 701.34a proliferate runs that many times
    (`counters.proliferate_times`)."""
    if "proliferate a number of times equal to the difference" not in text.lower():
        return None
    match = _LOOK_PUT_PROLIFERATE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    top = parse_count(match.group("n"))
    limit = parse_count(match.group("k"))
    kind = match.group("kind").lower()
    if top is None or limit is None or kind not in _TYPE_WORDS:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .effects.counters import proliferate_times
        from .effects.library import _shuffle_remainder_to_bottom

        controller = game.controller_of(stack_object)
        looked = list(controller.library[:top])
        wanted = [
            state for state in looked if kind in {t.value.lower() for t in state.card.types}
        ]
        taken: list = []
        if wanted:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"put up to {limit} {kind} cards onto the battlefield tapped",
                    source=stack_object.name,
                    source_id=source_id_of(stack_object),
                    amount=min(limit, len(wanted)),
                    exact=False,
                    cards=tuple(state.id for state in wanted),
                )
            )
            by_id = {state.id: state for state in wanted}
            taken = [by_id[card_id] for card_id in chosen_ids if card_id in by_id][:limit]
        arrived = 0
        for state in taken:
            game.put_onto_battlefield(state, controller.username, tapped=True)
            if state.zone is Zone.BATTLEFIELD:
                arrived += 1
        _shuffle_remainder_to_bottom(game, controller, [s for s in looked if s not in taken])
        proliferate_times(game, stack_object, max(limit - arrived, 0))

    return [effect]


# -- "Target creature gets -2/-2 until end of turn. It gets an additional -1/-1
# until end of turn for each modified creature you controlled as you cast this
# spell."

_ADDITIONAL_PER_AS_CAST_RE = re.compile(
    rf"^target (?P<what>creature) gets (?P<sign>[+-])(?P<a>\d+)/(?P=sign)(?P=a) until end of turn\."
    rf"\s+it gets an additional (?P<sign2>[+-])(?P<b>\d+)/(?P=sign2)(?P=b) until end of turn "
    r"for each modified creature you controlled as you cast this spell\.?"
    r"(?:\s*\([^)]*\))?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_pump_plus_additional_per_modified_as_cast(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """Lethal Exploit. The count is what the cast fixed (CR 601.2i; modified
    is CR 700.9) - `amounts.locked_amount_as_cast` stored it as the spell's
    cast X - and the two sentences are one pump of the single target for the
    summed amount (CR 611.2a, CR 608.2c), registered for what is still a legal
    target as the spell resolves (CR 608.2b). A copy was never cast
    (CR 707.10), so it counts none."""
    if "as you cast this spell" not in text.lower() or "an additional" not in text.lower():
        return None
    match = _ADDITIONAL_PER_AS_CAST_RE.fullmatch(" ".join(text.strip().split()))
    if match is None or match.group("sign") != match.group("sign2"):
        return None
    base, extra, sign = int(match.group("a")), int(match.group("b")), match.group("sign")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .effects import continuous_effects, layer_context_for

        record = game.cast_record_of(stack_object)
        counted = 0 if record is None else record.x_value
        total = base + extra * counted
        continuous_effects(game).create(
            stack_object,
            targets=game.resolve_card_targets(stack_object),
            context=layer_context_for(game, game.controller_of(stack_object)),
            ability_text=f"Target creature gets {sign}{total}/{sign}{total} until end of turn.",
            game=game,
        )

    return [effect]

"""EP-02 R3 T5: life-total amounts - amounts read off the players and the board that a
life change, a token count, a pump or a draw spends.

One mechanic: a variable amount whose source is a player-level number.

- `for_each_count` reads the "for each <count>" tails `amount_sentences.parse_life_clause`
  hands over that no earlier reader knew: "player" (CR 102.1), "creature attacking
  you" (CR 506.2, 508.1k), "<quality> that player controls" (the trigger event's
  player), "<creature> that died this turn" (CR 700.4) and "time it was kicked"
  (CR 702.33d).
- `amount_term` reads the "equal to <expr>" terms: "your speed" (CR 702.179f),
  "the number of opponents you have" (CR 102.2), "the greatest power|toughness|mana
  value among other <things> you control" (CR 107.2) and "the total power|toughness
  of <things> you control".

Both are pure readers: no persisted field. `amounts.py` calls them as its last rung, so a
sentence `amount_sentences` already reads picks the new terms up without a second parser.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from ..models.zone import Zone
from ..numbers import COUNT, parse_count, parse_multiplier
from .amount_sentences import apply_life, life_clause_amount, parse_life_clause
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game, StackObject
    from .triggers.events import AbilityOnStack

#: `(game, controller, source_id) -> int`, the `_for_each_multiplier` reader shape.
ForEachReader = Callable[["Game", str, "str | None"], int]
#: `(game, controller, source, x) -> int`, the `_amount_term` reader shape.
TermReader = Callable[["Game", str, "CardState | None", int], int]

_EACH_PLAYER_RE = re.compile(r"^players?$", re.IGNORECASE)
_ATTACKING_YOU_RE = re.compile(r"^creatures? attacking you$", re.IGNORECASE)
_THAT_PLAYER_CONTROLS_RE = re.compile(r"^(?P<what>.+?) that player controls$", re.IGNORECASE)
_DIED_RE = re.compile(r"^(?P<what>[A-Za-z-]+) that died this turn$", re.IGNORECASE)
_TIMES_KICKED_RE = re.compile(
    r"^times? (?:it|this (?:spell|creature|permanent|enchantment|artifact)) was kicked$",
    re.IGNORECASE,
)


def _source_of(game: "Game", source_id: "str | None") -> "CardState | None":
    return None if source_id is None else game.find_by_id(UUID(source_id))


def _event_player(game: "Game") -> str | None:
    """The player the resolving trigger's event concerns (CR 603.2's "that player")."""
    event = getattr(game.resolving, "event", None)
    return None if event is None else event.player


@functools.cache
def for_each_count(phrase: str) -> ForEachReader | None:
    """The count of a "for each <phrase>" tail described in the module docstring."""
    text = " ".join(phrase.split()).rstrip(".")
    lowered = text.lower()
    if _EACH_PLAYER_RE.fullmatch(text):
        # CR 102.1: every person still in the game.
        return lambda game, _controller, _source: len(game.players_in_game)
    if "attacking you" in lowered and _ATTACKING_YOU_RE.fullmatch(text):
        # CR 506.2: the attacks whose defender is the controller themselves (a planeswalker
        # or battle they control is not "you").
        def attacking_you(game: "Game", controller: str, _source: "str | None") -> int:
            return sum(
                1
                for attack in game.combat.attacks
                if attack.defender.username == controller and attack.defender.card_id is None
            )

        return attacking_you
    if "that player controls" in lowered and (match := _THAT_PLAYER_CONTROLS_RE.fullmatch(text)):
        from .effects.amounts import _for_each_multiplier

        counted = _for_each_multiplier(f"{match.group('what')} you control")
        if counted is None:
            return None

        def controlled_by_that_player(game: "Game", controller: str, source: "str | None") -> int:
            player = _event_player(game)
            return 0 if player is None else counted(game, player, source)

        return controlled_by_that_player
    if "died this turn" in lowered and _DIED_RE.fullmatch(text):
        from .effects.amounts import count_expression

        counted_deaths = count_expression(f"the number of {text}")
        if counted_deaths is None:
            return None
        return lambda game, controller, _source: counted_deaths(game, controller)
    if "kicked" in lowered and _TIMES_KICKED_RE.fullmatch(text):

        def times_kicked(game: "Game", _controller: str, source_id: "str | None") -> int:
            source = _source_of(game, source_id)
            record = None if source is None else game.cast_record_of(source)
            return 0 if record is None else record.kicked

        return times_kicked
    return None


#: `(game, controller) -> int`, the `count_expression` reader shape.
CountReader = Callable[["Game", str], int]


@functools.cache
def count_term(text: str) -> CountReader | None:
    """The player-level terms - "your life total" (CR 119.1), "your speed" (CR 702.179f),
    "the number of opponents you have" / "the number of players" (CR 102.1, 102.2) - as a
    `count_expression` reader, so a sentence that reads its X through `count_expression`
    (a "create X tokens, where X is ..." or a layer pump "gets +X/+X, where X is ...")
    reads them too."""
    lowered = " ".join(text.lower().split())
    if lowered == "your life total":
        return lambda game, controller: game.player(controller).life
    if lowered == "your speed":
        # CR 702.179f: a player with no speed has speed 0 for an effect that refers to it.
        return lambda game, controller: game.player(controller).speed or 0
    if _OPPONENTS_RE.fullmatch(lowered):
        everyone = lowered.endswith("players")
        return lambda game, controller: sum(
            1 for player in game.players_in_game if everyone or player.username != controller
        )
    return None


_OPPONENTS_RE = re.compile(r"^the number of (?:opponents(?: you have)?|players)$", re.IGNORECASE)
_GREATEST_OTHER_RE = re.compile(
    r"^(?:the )?(?P<which>greatest|total) (?P<stat>power|toughness|mana value) (?:among|of) "
    r"(?P<other>other )?(?P<what>[A-Za-z]+) you control$",
    re.IGNORECASE,
)


@functools.cache
def amount_term(text: str) -> TermReader | None:
    """The "equal to <expr>" terms described in the module docstring, or `None`."""
    if (player_level := count_term(text)) is not None:
        return lambda game, controller, _source, _x: player_level(game, controller)
    lowered = text.lower()
    if "among" in lowered or " of " in lowered:
        return _characteristic_extremum(" ".join(text.split()))
    return None


def _characteristic_extremum(text: str) -> TermReader | None:
    match = _GREATEST_OTHER_RE.fullmatch(text)
    if match is None:
        return None
    from .effects.text import _singular_card_type, _singular_subtype_for_count_expression

    what = match.group("what")
    card_type = _singular_card_type(what)
    subtype = None if card_type is not None else _singular_subtype_for_count_expression(what)
    if card_type is None and subtype is None:
        return None
    stat = match.group("stat").lower()
    greatest = match.group("which").lower() == "greatest"
    excludes_source = match.group("other") is not None

    def read(game: "Game", controller: str, source: "CardState | None", _x: int) -> int:
        board = game.computed_board()
        values: list[int] = []
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller != controller:
                continue
            if excludes_source and source is not None and permanent.id == source.id:
                continue
            if card_type is not None and card_type not in chars.types:
                continue
            if subtype is not None and not any(w.lower() == subtype for w in chars.subtypes):
                continue
            if stat == "mana value":
                values.append(int(permanent.mana_value))  # CR 202.3
            elif stat == "power":
                values.append(chars.numeric_power)  # CR 208.5
            else:
                values.append(chars.numeric_toughness)
        if not values:
            return 0  # CR 107.2: a number that can't be determined is 0
        return max(values) if greatest else sum(values)

    return read


# --------------------------------------------------------------------------
# Clauses
# --------------------------------------------------------------------------

#: Who a life clause may name: the controller, the opponent groups, everyone, or a
#: declared player target (CR 102.2, 102.3, 115.1).
_LIFE_WHO = frozenset(
    {
        "you",
        "each opponent",
        "each other player",
        "each player",
        "target opponent",
        "target player",
    }
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_life_amount_clause(clause: str, *, for_spell: bool) -> "Callable[..., None] | None":
    """ "<who> gains/loses twice X life | life equal to <expr> | N life for each <count> |
    X life, where X is <expr>" - the one life-sentence reader (`amount_sentences`) run as a
    clause, so every amount a sibling reader knows is usable in a sequence of sentences
    (CR 608.2c). X is the announced X of the spell or ability (CR 107.3a)."""
    lowered = clause.lower()
    if " life" not in lowered or not ("gain" in lowered or "lose" in lowered):
        return None
    life = parse_life_clause(clause)
    if life is None or life.who not in _LIFE_WHO:
        return None
    if life.who.startswith("target"):
        from .effects import _targets_understood

        if not _targets_understood(life.who, allow_player_targets=True):
            return None
    amount = life_clause_amount(life, spell_x=for_spell)
    if amount is None:
        return None
    who, gains = life.who, life.gains

    def effect(game: "Game", stack_object: "StackObject") -> None:
        apply_life(game, stack_object, who, gains, amount)

    return effect


_REVEAL_HAND_CLAUSE_RE = re.compile(
    r"^(?P<who>target player|target opponent|each opponent|each player) reveals their hand$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_reveal_hand_clause(clause: str, *, for_spell: bool) -> "Callable[..., None] | None":
    """ "Target player reveals their hand." on its own: every card in it is shown to all
    players and none moves (CR 701.20a, CR 701.20b); a later sentence reads it
    ("the number of cards in that player's hand")."""
    match = _REVEAL_HAND_CLAUSE_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    who = match.group("who").lower()
    if who.startswith("target"):
        from .effects import _targets_understood

        if not _targets_understood(who, allow_player_targets=True):
            return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .amount_sentences import controller_of, resolve_recipients, source_card

        source = source_card(game, stack_object)
        for player in resolve_recipients(
            game, stack_object, who, controller_of(game, stack_object)
        ):
            for card in list(player.hand):
                game.reveal(card, source=None if source is None else source.name)

    return effect


# --------------------------------------------------------------------------
# Exchanging a life total with a creature's power or toughness (CR 701.12g)
# --------------------------------------------------------------------------

_EXCHANGE_LIFE_RE = re.compile(
    r"^exchange (?P<who>your|target opponent's|target player's) life total with "
    r"(?P<owner>this creature|this permanent|[A-Za-z][\w ,'-]*?)'s (?P<stat>power|toughness)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_exchange_life_total_clause(
    clause: str, *, for_spell: bool
) -> "Callable[..., None] | None":
    """ "Exchange your | target opponent's life total with <this creature>'s power |
    toughness" (Evra, Tree of Redemption, Tree of Perdition). CR 701.12g: each value becomes
    the other's previous value - the player gains or loses the necessary life, and a
    continuous effect sets the power or toughness (CR 613.4b). If the whole exchange can't
    be completed - the creature has left, or the player can't gain (CR 119.7) or can't lose
    (CR 119.8) the life the exchange needs - no part of it occurs (CR 701.12a)."""
    if "exchange" not in clause.lower():
        return None
    match = _EXCHANGE_LIFE_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    who = "you" if match.group("who").lower() == "your" else match.group("who").lower()[:-2]
    if who.startswith("target"):
        from .effects import _targets_understood

        if not _targets_understood(who, allow_player_targets=True):
            return None
    wants_power = match.group("stat").lower() == "power"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .amount_sentences import controller_of, resolve_recipients, source_card
        from .layers.model import (
            ContinuousEffect,
            Layer,
            SetPower,
            SetToughness,
            Sublayer,
            only_this_incarnation,
        )

        creature = source_card(game, stack_object)
        if creature is None or creature.zone is not Zone.BATTLEFIELD:
            return
        players = resolve_recipients(game, stack_object, who, controller_of(game, stack_object))
        if not players:
            return
        player = players[0]
        stat = game.power_of(creature) if wants_power else game.toughness_of(creature)
        if stat is None:
            return
        life = player.life
        if (stat > life and player.cannot_gain_life) or (stat < life and player.cannot_lose_life):
            return
        game.set_life_total(player, stat)
        store = game.continuous_effects
        store.add(
            ContinuousEffect(
                description=(
                    f"{creature.name}: its {'power' if wants_power else 'toughness'} "
                    f"becomes {life} (exchanged with {player.username}'s life total)"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.SET,
                timestamp=store.tick(),
                selector=only_this_incarnation(creature, creature.zone_change_stamp),
                modification=SetPower(power=life) if wants_power else SetToughness(toughness=life),
            ),
            game,
        )

    return effect


# --------------------------------------------------------------------------
# "Then if <condition>, <instruction>" - a conditional step in a sequence (Betor)
# --------------------------------------------------------------------------

_THEN_IF_RE = re.compile(r"^then if (?P<condition>.+?), (?P<tail>.+)$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_then_if_clause(clause: str, *, for_spell: bool) -> "Callable[..., None] | None":
    """ "Then if <condition>, <instruction>" as one step of a sequence (CR 608.2c): the
    condition is read against the game as that step is reached - after the earlier steps have
    done what they did (CR 608.2c, "in the order written") - and the instruction is whatever
    the ordinary clause reader makes of the tail, so the mechanic is the conditional step,
    not the card. Betor, Kin to All chains three of them on total toughness (CR 208.1)."""
    match = _THEN_IF_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    from ..models.game._conditions import condition_is_readable
    from .effects import parse_mixed_effect, parse_mixed_effect_for_spell

    condition = match.group("condition").strip()
    if not condition_is_readable(condition):
        return None
    tail_text = match.group("tail").strip()
    reader = parse_mixed_effect_for_spell if for_spell else parse_mixed_effect
    tail = reader(tail_text[:1].upper() + tail_text[1:] + ".")
    if tail is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .amount_sentences import controller_of, source_card

        controller = controller_of(game, stack_object).username
        if game.condition_holds(controller, condition, source_card(game, stack_object)):
            tail(game, stack_object)

    return effect


# --------------------------------------------------------------------------
# A bite that "deals twice that much damage instead" under a condition (Chocobo Kick)
# --------------------------------------------------------------------------

_BITE_SCALED_RE = re.compile(
    r"^(?P<bite>target (?:creature|planeswalker) you control deals damage equal to its "
    r"(?:power|loyalty) to [^.]+?)\.\s*if (?P<condition>[^,]+), the (?:creature|planeswalker) "
    r"you control deals (?P<factor>twice|three times) that much damage instead\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s18")
def _parse_scaled_bite_spell(effect_text: str) -> "Callable[..., None] | None":
    """ "<Bite>. If <condition>, the creature you control deals twice that much damage
    instead." The bite is the ordinary one (CR 701.14 is not invoked: the creature deals the
    damage); the condition (here CR 702.33d's "this spell was kicked") is read as the spell
    resolves and scales the amount fixed in that one damage event (CR 120.3, CR 608.2h)."""
    if " that much damage instead" not in effect_text.lower():
        return None
    from ..models.game._conditions import condition_is_readable
    from .effects import _strip_non_effect_preamble
    from .effects.damage import _parse_bite_damage_clause

    match = _BITE_SCALED_RE.fullmatch(" ".join(_strip_non_effect_preamble(effect_text).split()))
    if match is None:
        return None

    condition = match.group("condition").strip()
    factor = parse_multiplier(match.group("factor"))
    if factor is None or not condition_is_readable(condition):
        return None

    def scale(game: "Game", spell: "StackObject") -> int:
        from .amount_sentences import controller_of, source_card

        controller = controller_of(game, spell)
        holds = game.condition_holds(controller, condition, source_card(game, spell))
        return factor if holds else 1

    return _parse_bite_damage_clause(match.group("bite"), for_spell=True, scale=scale)


# --------------------------------------------------------------------------
# "add twice that much {G}" - mana for the quantity the trigger event establishes (Fangorn)
# --------------------------------------------------------------------------

_ADD_THAT_MUCH_MANA_RE = re.compile(
    r"^add (?P<factor>twice |three times )?that much (?P<symbols>(?:\{[wubrgc]\})+)$",
    re.IGNORECASE,
)


def triggering_quantity(game: "Game", ability: "AbilityOnStack") -> int:
    """The "that much" a trigger's condition establishes (CR 603.2c, CR 607.1): for "one or
    more <creatures> attack" the number of those creatures that were declared as attackers
    (the batch the condition counts); otherwise the event's own amount."""
    from .triggers.collect import batched_attackers

    event = ability.event
    if event is None:
        return 0
    batch = batched_attackers(game, ability.ability.condition, ability.controller)
    if batch is not None:
        return len(batch)
    return event.amount or 0


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_add_that_much_mana_clause(
    clause: str, *, for_spell: bool
) -> "Callable[..., None] | None":
    """ "Add [twice] that much {G}." (CR 106.4): mana of the stated colour equal to the
    quantity the triggering event established, times the factor. Ability-only: a spell has no
    event for "that much" to point back at (CR 608.2c)."""
    if for_spell or "that much" not in clause.lower():
        return None
    match = _ADD_THAT_MUCH_MANA_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    factor = parse_multiplier((match.group("factor") or "").strip()) or 1
    symbols = match.group("symbols")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .amount_sentences import add_mana_times, controller_of

        add_mana_times(
            game,
            controller_of(game, stack_object),
            symbols,
            factor * triggering_quantity(game, stack_object),  # type: ignore[arg-type]
            stack_object=stack_object,
        )

    return effect


# --------------------------------------------------------------------------
# "Until end of turn, you may ... play cards from the top of your library" (Gwenom)
# --------------------------------------------------------------------------

_UNTIL_EOT_TOP_OF_LIBRARY_RE = re.compile(
    r"^until end of turn, you may look at the top card of your library any time and you may "
    r"(?P<act>play cards|play lands and cast spells|cast spells) from the top of your library\.?"
    r"(?P<rider> if you cast a spell this way, pay life equal to its mana value rather than pay "
    r"its mana cost\.?)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_until_end_of_turn_top_of_library_permission(
    effect_text: str,
) -> "Callable[..., None] | None":
    """ "Until end of turn, you may look at the top card of your library any time and you may
    play cards from the top of your library. If you cast a spell this way, pay life equal to
    its mana value rather than pay its mana cost." - the same permission a static ability
    prints (`casting.static_zone_cast_permission`, CR 601.3, CR 118.9, CR 611.3d), granted for
    the turn as a layer 6 ability of the source (CR 611.2a, CR 514.2), so every casting,
    payment and land-play check reads the one reader."""
    if "top card of your library any time" not in effect_text.lower():
        return None
    match = _UNTIL_EOT_TOP_OF_LIBRARY_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    from .casting.permissions import static_zone_cast_permission

    line = (
        "You may look at the top card of your library any time, and you may "
        f"{match.group('act')} from the top of your library."
    )
    if match.group("rider"):
        line += " If you cast a spell this way, pay life equal to its mana value rather than pay"
        line += " its mana cost."
    if static_zone_cast_permission(line) is None:
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        from .layers.model import (
            ContinuousEffect,
            Duration,
            Layer,
            grant_ability,
            only_this_incarnation,
        )

        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        store = game.continuous_effects
        store.add(
            ContinuousEffect(
                description=f"{source.name}: may play cards from the top of its library",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(source, source.zone_change_stamp),
                modification=grant_ability(line),
            ),
            game,
        )

    return effect


# --------------------------------------------------------------------------
# Two players reveal and lose life by each other's card (Parker Luck)
# --------------------------------------------------------------------------

_REVEAL_AND_CROSS_LOSE_RE = re.compile(
    r"^(?P<who>two target players) each reveal the top card of their library\. "
    r"they each lose life equal to the mana value of the card revealed by the other player\. "
    r"then they each put the card they revealed into their hand\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_two_players_reveal_and_cross_lose_life(
    effect_text: str,
) -> "Callable[..., None] | None":
    """ "Two target players each reveal the top card of their library. They each lose life
    equal to the mana value of the card revealed by the other player. Then they each put the
    card they revealed into their hand." Each reveal is public (CR 701.20a); each loss is read
    off the other player's revealed card once, before any life moves (CR 608.2h), in the
    order written (CR 608.2c). A target that became illegal reveals nothing (CR 608.2b), so
    the other player loses nothing for it."""
    if "revealed by the other player" not in effect_text.lower():
        return None
    match = _REVEAL_AND_CROSS_LOSE_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    from .effects import _targets_understood

    # Exactly two players: the reveal and loss are written for the pair, so the count is
    # fixed by the text and the reader itself works out what is left if a target is gone.
    if not _targets_understood(
        match.group("who").lower(), allow_player_targets=True, count_agnostic=True
    ):
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        players = [t for t in game.resolve_targets(ability) if hasattr(t, "library")][:2]
        revealed = {}
        for player in players:
            if player.library:
                top = player.library[0]
                game.reveal(top, source=ability.source_name)
                revealed[player.username] = top
        losses = [
            (player, int(revealed[other.username].card.cmc))
            for player in players
            for other in players
            if other is not player and other.username in revealed
        ]
        for player, amount in losses:
            if amount > 0:
                game.lose_life(player, amount)
        for player in players:
            card = revealed.get(player.username)
            if card is not None and card.zone is Zone.LIBRARY:
                player.move(card, Zone.HAND)

    return effect


# --------------------------------------------------------------------------
# An edict whose failures are punished: "Each opponent sacrifices a creature or Vehicle of their
# choice. Each opponent who can't discards a card." (Momentum Breaker)
# --------------------------------------------------------------------------

_EDICT_RE = re.compile(
    r"^(?P<who>each opponent|each player) sacrifices (?:a|an|one) (?P<description>.+?) "
    r"of their choice$",
    re.IGNORECASE,
)
_WHO_CANT_DISCARD_RE = re.compile(
    rf"^(?P<who>each opponent|each player) who can'?t discards? (?P<n>{COUNT}) cards?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_edict_then_who_cant_discards(
    text: str, *, for_spell: bool
) -> "list[Callable[..., None]] | None":
    """The edict (CR 701.21a: each player of the group chooses among the permanents they
    control, CR 101.4 in APNAP order, CR 608.2d; a player with none sacrifices nothing) and
    the sentence after it, which reads who sacrificed: "Each opponent who can't discards a
    card" is every member who had nothing to sacrifice (CR 608.2c, in order)."""
    if "who can't" not in text.lower() and "who can’t" not in text.lower():
        return None
    from .effects import _strip_non_effect_preamble
    from .effects.text import _plain_resolution_sentences

    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    if len(sentences) != 2:
        return None
    edict = _EDICT_RE.fullmatch(sentences[0].strip().rstrip("."))
    punishment = _WHO_CANT_DISCARD_RE.fullmatch(sentences[1].strip().rstrip(".").replace("’", "'"))
    if (
        edict is None
        or punishment is None
        or edict.group("who").lower() != (punishment.group("who").lower())
    ):
        return None
    from .targeting import permanent_description

    requirement = permanent_description(edict.group("description").strip())
    discards = parse_count(punishment.group("n"))
    if requirement is None or discards is None:
        return None
    opponents_only = edict.group("who").lower() == "each opponent"
    description = edict.group("description").strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .decisions import Decision, DecisionKind, source_id_of
        from .effects._common import _players_in_apnap_order
        from .effects.draw_discard import _discard_cards

        controller = game.controller_of(stack_object).username
        source_name = getattr(stack_object, "source_name", None) or stack_object.name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        chosen: list[CardState] = []
        failed = []
        for player in _players_in_apnap_order(game):
            if opponents_only and player.username == controller:
                continue
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if requirement.rejects(permanent, player.username, game) is None
            ]
            if not candidates:
                failed.append(player)
            elif len(candidates) == 1:
                chosen.extend(candidates)
            else:
                picked = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=f"sacrifice a {description}",
                        source=source_name,
                        amount=1,
                        cards=tuple(permanent.id for permanent in candidates),
                        source_id=source_id,
                    )
                )
                by_id = {permanent.id: permanent for permanent in candidates}
                chosen.extend(by_id[card_id] for card_id in picked if card_id in by_id)
        for permanent in chosen:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)
        for player in failed:
            _discard_cards(game, player, discards, source_name, source_id=source_id)

    return [effect]


# --------------------------------------------------------------------------
# "you may return one of them to its owner's hand. If you do, you may activate loyalty abilities
# of <this> twice this turn rather than only once" (Kaito, Dancing Shadow)
# --------------------------------------------------------------------------

_RETURN_ONE_THEN_LOYALTY_TWICE_RE = re.compile(
    r"^you may return one of them to its owner's hand\. if you do, you may activate loyalty "
    r"abilities of (?P<who>this permanent|[\w ,'-]+?) twice this turn rather than only once\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_return_one_of_them_then_loyalty_twice(
    effect_text: str,
) -> "Callable[..., None] | None":
    """After a batched "one or more creatures you control deal combat damage to a player"
    trigger (CR 603.2c): the controller may return one of the creatures that dealt it to its
    owner's hand (CR 701.19a); if they do, the source planeswalker's loyalty abilities may be
    activated twice this turn (CR 606.3 raised for the turn, `Game.loyalty_activation_allowance`).
    "Them" is the batch the trigger counted (`batched_combat_damage_sources`)."""
    if "loyalty abilities of" not in effect_text.lower():
        return None
    match = _RETURN_ONE_THEN_LOYALTY_TWICE_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        from ..models.card_state import CardState
        from .decisions import Decision, DecisionKind, source_id_of
        from .triggers.collect import batched_combat_damage_sources

        source = ability.source(game)
        event = ability.event
        if source is None or event is None:
            return
        controller = game.controller_of(ability).username
        ids = batched_combat_damage_sources(game, ability.ability.condition, controller, event)
        candidates = [
            state
            for state in (game.find_by_id(card_id) for card_id in ids or ())
            if isinstance(state, CardState) and state.zone is Zone.BATTLEFIELD
        ]
        if not candidates:
            return
        source_id = source_id_of(ability)
        if not game.may(
            controller,
            "return one of the creatures that dealt combat damage to its owner's hand",
            source=ability.source_name,
            source_id=source_id,
        ):
            return
        chosen = candidates[0]
        if len(candidates) > 1:
            picked = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt="return one of them to its owner's hand",
                    source=ability.source_name,
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                    source_id=source_id,
                )
            )
            by_id = {state.id: state for state in candidates}
            chosen = next((by_id[card_id] for card_id in picked if card_id in by_id), chosen)
        game.return_to_hand(chosen)
        if chosen.zone is Zone.HAND and source.zone is Zone.BATTLEFIELD:
            key = str(source.id)
            game.loyalty_activation_allowance[key] = max(
                2, game.loyalty_activation_allowance.get(key, 1)
            )

    return effect


# --------------------------------------------------------------------------
# "Draw a card, then exile a card from your hand. If cards with five or more different mana
# values are exiled with <this>, you gain 5 life, untap <this>, and transform it." (Azor's Gateway)
# --------------------------------------------------------------------------

_DRAW_EXILE_FROM_HAND_TRANSFORM_RE = re.compile(
    rf"^draw a card, then exile a card from your hand\. if cards with (?P<n>{COUNT}) or more "
    r"different mana values are exiled with (?P<name>[^,]+), you gain (?P<life>"
    rf"{COUNT}) life, untap (?P<untap>[^,]+), and transform it\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_draw_exile_from_hand_then_transform_on_different_values(
    effect_text: str,
) -> "Callable[..., None] | None":
    """The draw, then a card of the controller's choice from their hand exiled *with* this
    permanent (CR 607.2a: `ExileMarker.LINKED`, the object and its incarnation recorded); then,
    if the cards exiled with it have N or more different mana values (CR 202.3), the controller
    gains the life, the permanent untaps and transforms (CR 701.27a). The count is read after the
    new card is linked, since the instruction is followed in order (CR 608.2c)."""
    if "different mana values" not in effect_text.lower():
        return None
    match = _DRAW_EXILE_FROM_HAND_TRANSFORM_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    needed = parse_count(match.group("n"))
    life = parse_count(match.group("life"))
    if needed is None or life is None:
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        from ..models.card_state import ExileAnnotation, ExileMarker
        from .decisions import Decision, DecisionKind, source_id_of

        controller = game.player(game.controller_of(ability).username)
        source = ability.source(game)
        game.draw_cards(controller.username, 1)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        hand = list(controller.hand)
        if hand:
            chosen = hand[0]
            if len(hand) > 1:
                picked = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=controller.username,
                        prompt="exile a card from your hand",
                        source=ability.source_name,
                        amount=1,
                        exact=True,
                        cards=tuple(card.id for card in hand),
                        source_id=source_id_of(ability),
                    )
                )
                by_id = {card.id: card for card in hand}
                chosen = next((by_id[card_id] for card_id in picked if card_id in by_id), chosen)
            game.exile_permanent(chosen)
            if chosen.zone is Zone.EXILE:
                chosen.exile_annotation = ExileAnnotation(
                    marker=ExileMarker.LINKED,
                    owner=chosen.owner,
                    turn_exiled=game.turn.turns_taken if game.turn is not None else None,
                    linked_permanent_id=source.id,
                    linked_permanent_stamp=source.zone_change_stamp,
                )
        exiled = game.cards_exiled_with(source.id, source.zone_change_stamp)
        if len({int(card.card.cmc) for card in exiled}) < needed:
            return
        game.gain_life(controller, life)
        source.untap()
        source.transform()

    return effect


# --------------------------------------------------------------------------
# What a revealed card is worth: "you draw cards equal to its power and you gain life equal to
# its toughness" (Nissa's Revelation)
# --------------------------------------------------------------------------

_REVEALED_CARD_PART_RE = re.compile(
    r"^you (?P<verb>draw cards|gain life|lose life) equal to its "
    r"(?P<stat>power|toughness|mana value)$",
    re.IGNORECASE,
)


@functools.cache
def revealed_card_consequence(
    text: str,
) -> "Callable[[Game, StackObject, CardState], None] | None":
    """ "you draw cards | gain life | lose life equal to its power | toughness | mana value",
    chained with "and": the instruction a reveal-and-check reader (`library`'s "reveal the top
    card ... If it's a <quality> card, ...") follows for the card it revealed. Every value is
    read off that card once, as the instruction begins (CR 608.2h), before any part is
    followed (CR 608.2c, in order)."""
    parts = []
    for piece in re.split(r" and (?=you )", " ".join(text.split()).rstrip(".")):
        match = _REVEALED_CARD_PART_RE.fullmatch(piece.strip())
        if match is None:
            return None
        parts.append((match.group("verb").lower(), match.group("stat").lower()))
    if not parts:
        return None

    def stat_of(card: "CardState", stat: str) -> int:
        if stat == "mana value":
            return int(card.card.cmc)
        printed = card.card.power if stat == "power" else card.card.toughness
        return int(printed) if printed is not None and printed.lstrip("-").isdigit() else 0

    def follow(game: "Game", stack_object: "StackObject", revealed: "CardState") -> None:
        from .amount_sentences import controller_of

        controller = game.player(controller_of(game, stack_object))
        amounts = [(verb, stat_of(revealed, stat)) for verb, stat in parts]
        for verb, amount in amounts:
            if amount <= 0:
                continue
            if verb == "draw cards":
                game.draw_cards(controller.username, amount)
            elif verb == "gain life":
                game.gain_life(controller, amount)
            else:
                game.lose_life(controller, amount)

    return follow


__all__ = ["amount_term", "count_term", "for_each_count", "revealed_card_consequence"]

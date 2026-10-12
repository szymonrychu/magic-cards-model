"""'`<instruction naming target creature>`. When that creature dies this
turn, `<consequence>`.' (ECL).

End-Blaze Epiphany: "End-Blaze Epiphany deals X damage to target creature.
When that creature dies this turn, exile a number of cards from the top of
your library equal to its power, then choose a card exiled this way. Until
the end of your next turn, you may play that card." and Burn Away: "Burn Away
deals 6 damage to target creature. When that creature dies this turn, exile
its controller's graveyard."

The second sentence creates a CR 603.7 delayed triggered ability as the
first resolves, watching the creature the first one targeted (CR 603.7c:
that object), for the rest of the turn (CR 603.7b's stated duration). It
triggers on that creature's death (CR 700.4), and - a leaves-the-battlefield
ability looking back in time (CR 603.10a) - "its power" and "its controller"
are the creature as it last existed on the battlefield (CR 608.2h).
"""

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ..models.game import Game

_THEN_WHEN_THAT_CREATURE_DIES_RE = re.compile(
    r"^(?P<first>[^.]*\btarget creature\b[^.]*\.)\s*when "
    r"(?:that creature|(?P<dealt>a creature dealt damage this way)"
    r"|the (?:permanent|creature|planeswalker) (?P<other>you don['’]t control)) dies this turn, "
    r"(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)
#: "`<source>` deals N damage to the creature's controller" - Searing Blood's
#: consequence. The player is the dead creature's controller as it last
#: existed (CR 603.10a, CR 608.2h), carried on the DIES event.
_DEALS_DAMAGE_TO_ITS_CONTROLLER_RE = re.compile(
    rf"^[^.,]+? deals (?P<n>{COUNT}) damage to "
    r"(?:its controller|(?:the|that) creature'?s controller)\.?$",
    re.IGNORECASE,
)
_EXILE_TOP_THEN_CHOOSE_ONE_TO_PLAY_RE = re.compile(
    r"^exile (?:a number of cards from the top of your library equal to (?P<its_power>its power)"
    r"|the top (?P<n>\w+) cards of your library), then choose a card exiled this way\.\s*"
    r"until the end of your next turn, you may play that card\.?$",
    re.IGNORECASE,
)
_EXILE_ITS_CONTROLLERS_GRAVEYARD_RE = re.compile(
    r"^exile its controller'?s graveyard\.?$", re.IGNORECASE
)
#: The Deck of Many Things' "When that creature dies, its owner loses the
#: game." - CR 104.3e's loss, for the dead card's owner (CR 108.3), who may
#: not be the player who controlled it.
_ITS_OWNER_LOSES_THE_GAME_RE = re.compile(r"^its owner loses the game\.?$", re.IGNORECASE)
#: Initiate of Blood's "flip this creature" (CR 710): the source that created
#: the delayed trigger, not the creature that died.
_FLIP_THIS_RE = re.compile(r"^flip this (?:creature|permanent)\.?$", re.IGNORECASE)


def _dead_creature(game: "Game", ability: Any) -> CardState | None:
    event = getattr(ability, "event", None)
    if event is None or event.subject_id is None:
        return None
    found = game.find_by_id(event.subject_id)
    return found if isinstance(found, CardState) else None


def _last_known_power(card: CardState) -> int:
    """CR 603.10a / CR 608.2h: the power it had as it left the battlefield -
    the shared `conditions.objects._last_known_power_toughness` read (a
    continuous effect's snapshot, or the printing plus the counters it left
    with, CR 122.1a)."""
    from .conditions.objects import _last_known_power_toughness

    power, _toughness = _last_known_power_toughness(card)
    return max(power or 0, 0)


def dies_consequence_effect(text: str, *, source_stamp: UUID | None = None) -> Any:
    """The consequence as an ability effect, or None.

    `source_stamp` is the creating ability's source as it was then
    (`CardState.zone_change_stamp`): "this creature" is that object, and one
    that has left the battlefield since is a new object (CR 400.7, CR 603.7c)
    the consequence no longer reaches."""
    from .casting import PlayAction

    cleaned = " ".join(text.split())
    if _FLIP_THIS_RE.fullmatch(cleaned):

        def flip_source(game: "Game", ability: Any) -> None:
            source_id = getattr(ability, "source_id", None)
            source = game.find_by_id(source_id) if source_id is not None else None
            if not isinstance(source, CardState) or source.zone is not Zone.BATTLEFIELD:
                return
            if source_stamp is not None and source.zone_change_stamp != source_stamp:
                return
            source.flip()

        return flip_source
    if match := _EXILE_TOP_THEN_CHOOSE_ONE_TO_PLAY_RE.fullmatch(cleaned):
        fixed = None if match.group("its_power") else parse_count(match.group("n") or "")
        if fixed is None and not match.group("its_power"):
            return None

        def exile_and_play(game: "Game", ability: Any) -> None:
            controller = game.controller_of(ability)
            if fixed is None:
                dead = _dead_creature(game, ability)
                count = 0 if dead is None else _last_known_power(dead)
            else:
                count = fixed
            exiled = [
                game.exile_permanent(card) for card in list(controller.library[: max(count, 0)])
            ]
            if not exiled:
                return
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="choose a card exiled this way to play until the end of your next turn",
                    source=ability.source_name,
                    amount=1,
                    exact=True,
                    cards=tuple(card.id for card in exiled),
                    source_id=source_id_of(ability),
                )
            )
            chosen = next(card for card in exiled if card.id == chosen_ids[0])
            game.grant_play_permission(
                chosen,
                controller.username,
                action=PlayAction.PLAY,
                source_name=ability.source_name,
                rule="CR 601.3, CR 611.2a",
                until_end_of_turn=False,
                expires_end_of_next_turn=True,
            )

        return exile_and_play
    if match := _DEALS_DAMAGE_TO_ITS_CONTROLLER_RE.fullmatch(cleaned):
        damage = parse_count(match.group("n"))
        if damage is None:
            return None

        def damage_its_controller(game: "Game", ability: Any) -> None:
            event = getattr(ability, "event", None)
            username = getattr(event, "subject_controller", None)
            if username is None or not game.is_in_game(username):
                return
            game.deal_damage(
                game.player(username), damage, source=ability.source_or_last_known(game)
            )

        return damage_its_controller
    if _EXILE_ITS_CONTROLLERS_GRAVEYARD_RE.fullmatch(cleaned):

        def exile_graveyard(game: "Game", ability: Any) -> None:
            event = getattr(ability, "event", None)
            username = getattr(event, "subject_controller", None)
            if username is None:
                return
            for card in list(game.player(username).graveyard):
                game.exile_permanent(card)

        return exile_graveyard
    if _ITS_OWNER_LOSES_THE_GAME_RE.fullmatch(cleaned):

        def owner_loses(game: "Game", ability: Any) -> None:
            dead = _dead_creature(game, ability)
            owner = None if dead is None else dead.owner
            if owner is not None and game.is_in_game(owner):
                game.player_loses_the_game(owner)

        return owner_loses
    from .effects import parse_mixed_effect

    return parse_mixed_effect(cleaned)


def parse_then_when_that_creature_dies_this_turn(text: str, *, for_spell: bool) -> Any:
    """The whole two-sentence chain, or None."""
    match = _THEN_WHEN_THAT_CREATURE_DIES_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from ..machines.abilities import TriggerEvent
    from .delayed import DelayedTrigger, ThatCreatureDiesConsequence
    from .effects import _parse_mixed_clauses

    if re.search(r"\bX\b", match.group("first")):
        # CR 107.3a: an X the caster announced is read by `effects.effect_for`
        # substituting it into the text first - declining here is what lets
        # that second, substituted reading happen.
        return None
    consequence = match.group("consequence").strip()
    if dies_consequence_effect(consequence) is None:
        return None
    first = _parse_mixed_clauses(match.group("first"), for_spell=for_spell)
    if first is None:
        return None

    # "the permanent you don't control" (Devouring Tendrils' bite): the one
    # target the first sentence names that the spell's controller does not
    # control - never the biter they do.
    the_other = match.group("other") is not None
    if the_other and "you don't control" not in match.group("first").lower().replace("’", "'"):
        return None
    dealt_this_way = match.group("dealt") is not None
    if dealt_this_way and " damage " not in match.group("first").lower():
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if the_other:
            targets = [
                target
                for target in targets
                if game.controller_of(target).username != game.controller_of(stack_object).username
            ]
        marked_before = {target.id: target.damage for target in targets}
        for clause in first:
            clause(game, stack_object)
        if dealt_this_way:
            # CR 615.6: prevented damage was never dealt, so a creature whose
            # damage was all prevented was not "dealt damage this way".
            targets = [
                target
                for target in targets
                if target.zone is Zone.BATTLEFIELD and target.damage > marked_before[target.id]
            ]
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        for creature in targets:
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=consequence,
                    event=TriggerEvent.DIES,
                    controller=controller,
                    source_id=source_id_of_object(stack_object),
                    source_name=source_name,
                    subject_id=creature.id,
                    remaining=1,
                    expires_end_of_turn=True,
                    effect=ThatCreatureDiesConsequence(
                        source_stamp=getattr(stack_object, "source_stamp", None)
                    ),
                )
            )

    return effect


def source_id_of_object(stack_object: Any) -> Any:
    """The creating object's id (CR 603.7d/e): the spell itself, or the
    ability's source."""
    if isinstance(stack_object, CardState):
        return stack_object.id
    return getattr(stack_object, "source_id", None)

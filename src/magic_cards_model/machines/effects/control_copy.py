import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from ...models.card import Type
from ...models.card_state import (
    CardState,
)
from ...models.player import Player
from ...models.token import (
    token_copy_of,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    parse_count,
)
from ..abilities import (
    TriggerEvent,
    parse_granted_ability_lines,
)
from ..combat import Keyword
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    CopyNextSpellYouCast,
    CreateTokenCopyOfControlledToken,
    DelayedTrigger,
    SpellEntersWithAdditionalCounter,
    anaphoric_delayed_trigger,
)
from ..layers import (
    ContinuousEffect,
    Layer,
    grant_ability,
    only_this_incarnation,
    split_and_validate_keywords,
)
from ..targeting import (
    RetargetScope,
    profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT
from ._common import _SPELL_QUALIFIER, AbilityEffect, Effect, TargetedClause, _CopyExceptionList

#: A power qualifier trailing the group - Mob Rule's "creatures with power 4
#: or greater" / "creatures with power 3 or less" (CR 208.1's power, read off
#: the computed board, CR 613.5).
_MASS_GROUP_POWER_RE = re.compile(
    r"^(?P<base>.+?) with power (?P<n>\d+) or (?P<cmp>greater|less)$", re.IGNORECASE
)


def _mass_control_group(group: str) -> "GroupPredicate | None":
    """`_MASS_GAIN_CONTROL_UNTAP_RE`'s group as a predicate - the
    `_parse_damage_group_phrase` grammar (controller and type qualifiers),
    plus a trailing power comparison. `None` for anything else."""
    power = _MASS_GROUP_POWER_RE.fullmatch(group.strip())
    base = _parse_damage_group_phrase(power.group("base") if power else group)
    if base is None:
        return None
    if power is None:
        return base
    bound = int(power.group("n"))
    at_least = power.group("cmp").lower() == "greater"

    def predicate(game: "Game", permanent: CardState, controller: str) -> bool:
        if not base(game, permanent, controller):
            return False
        value = game.characteristics_of(permanent).numeric_power
        return value >= bound if at_least else value <= bound

    return predicate


#: "Whenever you cast a [restriction] spell, copy it. You may choose new
#: targets for the copy." - Codie, Ravenous Codex's own "cast a prepared
#: spell" trigger (`machines/triggers.py`'s `CAST_SPELL` condition reads the
#: restriction itself; this only ever reads the *effect* half, so it is
#: general across any card printing the identical CAST_SPELL-copy template,
#: prepared spells included but not assumed). CR 603.10's "it" is the spell
#: whose cast just triggered this ability - `Game._resolve_top` pops the
#: ability off `self.stack` before calling its effect (CR 608.2n), and
#: `Game.put_triggers_on_stack` put this ability directly above the spell
#: that caused it (CR 603.3) with nothing yet given a chance to resolve in
#: between, so the new top of the stack at that moment is that same spell.
_COPY_CAST_SPELL_RE = re.compile(
    r"^copy it\.(?P<retarget>\s*you may choose new targets for the copy\.)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_copy_cast_spell_clause(text: str) -> AbilityEffect | None:
    """`_COPY_CAST_SPELL_RE`'s shape - see its own docstring."""
    match = _COPY_CAST_SPELL_RE.fullmatch(text.strip())
    if match is None:
        return None
    # CR 707.10: a copy keeps the original's targets; only an effect that
    # says so lets its controller choose new ones (CR 707.10c).
    may_retarget = match.group("retarget") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if not game.stack:
            return
        spell = game.stack[-1]
        if not isinstance(spell, CardState):
            return
        copy = game.copy_spell(spell, ability.controller)
        if not may_retarget:
            return
        game.offer_new_targets_for_copy(
            copy,
            ability.controller,
            source_name=ability.source_name,
            source_id=str(ability.source_id) if ability.source_id is not None else None,
        )

    return effect


#: "you may copy it. If you do, you may choose new targets for the copy. If
#: the copy is a permanent spell, it gains haste." (Spider-Verse, its "Do this
#: only once each turn." already stripped into `TriggeredAbility.
#: once_per_turn`) - `_COPY_CAST_SPELL_RE`'s optional sibling. "it" is the
#: spell whose cast triggered the ability (CR 603.10, `ability.event`). A copy
#: of a permanent spell becomes a token as it resolves (CR 707.10f) and keeps
#: the keyword granted to it on the stack (CR 400.7b). Declining the "may"
#: hands CR 603.2h's once-each-turn budget back: it is spent by the action.
_MAY_COPY_CAST_SPELL_RE = re.compile(
    r"^you may copy it\."
    r"(?P<retarget>\s*if you do, you may choose new targets for the copy\.)?"
    r"(?:\s*if the copy is a permanent spell, it gains (?P<keyword>[a-z]+(?: [a-z]+)?)\.)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_may_copy_cast_spell_clause(text: str) -> AbilityEffect | None:
    """`_MAY_COPY_CAST_SPELL_RE`'s shape - see its own docstring."""
    match = _MAY_COPY_CAST_SPELL_RE.fullmatch(text.strip())
    if match is None:
        return None
    may_retarget = match.group("retarget") is not None
    keyword = match.group("keyword")
    if keyword is not None:
        keyword = keyword.strip().title()
        if keyword.lower() not in {k.value.lower() for k in Keyword}:
            return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ..connive import _release_once_per_turn

        spell: CardState | None = None
        event = ability.event
        if event is not None and event.subject_id is not None:
            found = game.find_by_id(event.subject_id)
            if isinstance(found, CardState) and found.zone is Zone.STACK:
                spell = found
        if spell is None:
            return
        taken = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=ability.controller,
                prompt=f"copy {spell.name}",
                source=ability.source_name,
                source_id=source_id_of(ability),
            )
        )
        if not taken:
            _release_once_per_turn(game, ability)
            return
        copy = game.copy_spell(spell, ability.controller)
        if copy is None:
            return
        if may_retarget:
            game.offer_new_targets_for_copy(
                copy,
                ability.controller,
                source_name=ability.source_name,
                source_id=str(ability.source_id) if ability.source_id is not None else None,
            )
        if keyword is not None and copy.is_permanent:
            copy.granted_ability_texts = (*copy.granted_ability_texts, keyword)

    return effect


#: "Exchange control of two target creatures." (Switcheroo), "... two target
#: nonland permanents that share a card type." (Burglar's Plot), "... two
#: target permanents that share a card type." (Shifting Loyalties) - CR
#: 701.12's exchange, performed by `machines/control.exchange_control`. The
#: two targets are one "target" instance (CR 601.2c), announced together;
#: "that share a card type" is enforced on the announcement by
#: `TargetRequirement.share_a_card_type` and rechecked as it resolves.
#:
#: Widened (271-tmt) to Kitsune, Dragon's Daughter's "you may exchange control
#: of two other target creatures controlled by different players." and The
#: Trickster-God's Heist's "You may exchange control of two target nonbasic,
#: noncreature permanents that share a card type." - an optional exchange
#: (CR 608.2d, `_optional_targeted_clause`), "other" (the source excluded)
#: and a comma inside the target description; `machines/targeting.py` reads
#: the restrictions themselves.
_EXCHANGE_CONTROL_RE = re.compile(
    r"^(?P<may>you may )?exchange control of (?P<phrase>two (?:other )?target [a-z ,]+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s8")
@SPELL_TEXT.rung("s8")
def _parse_exchange_control_clause(text: str) -> TargetedClause | None:
    """`_EXCHANGE_CONTROL_RE`'s shape, on a spell or an ability."""
    from ..control import exchange_control

    match = _EXCHANGE_CONTROL_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    if match.group("may") is not None:
        inner = _parse_exchange_control_clause(text.strip()[len(match.group("may")) :])
        if inner is None:
            return None
        prompt = text.strip()[len(match.group("may")) :]

        def optional(game: "Game", stack_object: "StackObject") -> None:
            source = (
                stack_object.name
                if isinstance(stack_object, CardState)
                else str(getattr(stack_object, "source_name", ""))
            )
            player = game.controller_of(stack_object)
            if game.may(player, prompt, source=source, source_id=source_id_of(stack_object)):
                inner(game, stack_object)

        return optional
    profile = profile_for_text(match.group("phrase"))
    if (
        not profile.understood
        or len(profile.requirements) != 1
        or profile.requirements[0].count != 2
        or profile.requirements[0].zones != frozenset({Zone.BATTLEFIELD})
        or profile.requirements[0].allows_players
    ):
        return None
    share = profile.requirements[0].share_a_card_type

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = game.resolve_card_targets(stack_object)
        if len(targets) != 2:
            # CR 608.2b left one of the pair illegal: CR 701.12a, no part of
            # the exchange occurs.
            return
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name  # type: ignore[union-attr]
        )
        exchange_control(
            game, targets[0], targets[1], source_name=source_name, share_a_card_type=share
        )

    return effect


def _controlled_by_whose(
    permanent: CardState, whose: str, controller: str, opponent_names: set[str]
) -> bool:
    """Whether `permanent` is in a damage filter's controller group, relative
    to the effect's controller - its CR 109.5 "you". "They control" and "your
    opponents control" are the opponents' permanents, "you control" the
    controller's own, and "you don't control" everyone's but the
    controller's."""
    if whose == "you control":
        return permanent.controller == controller
    if whose.startswith("you don"):
        return permanent.controller != controller
    return permanent.controller in opponent_names


#: "if you control a[n] `<color>` permanent other than `<name>`, [he|she|it|
#: they] deals damage equal to `<expr>` to any target." - the intervening
#: *if* (CR 603.4) nested inside Ajani, Nacatl Avenger's own reflexive
#: clause. `<name>` is read and thrown away: "other than Ajani" is CR 400.7's
#: self-reference (this permanent is the only "Ajani" the sentence could
#: mean), the same idiom `machines/triggers.py`'s own `_self_referential`
#: reads for an ordinary trigger's condition, so the exclusion is applied by
#: id (the ability's own source) rather than by matching the captured name.
_IF_CONTROL_COLORED_PERMANENT_DEALS_DAMAGE_RE = re.compile(
    r"^if you control an? (?P<color>white|blue|black|red|green) permanent other than "
    r"[a-z' ]+?,\s*(?:he|she|they|it) deals damage equal to (?P<expr>.+?) to any target\.?$",
    re.IGNORECASE,
)


def _parse_if_control_colored_permanent_damage_clause(
    text: str,
) -> tuple[Callable[["Game", str, UUID | None], bool], AbilityEffect] | None:
    """The condition-and-damage pair `_IF_CONTROL_COLORED_PERMANENT_DEALS_
    DAMAGE_RE` reads, split apart so a caller can check CR 603.4's condition
    once - at whatever moment it decides is "checked immediately" (CR 603.12)
    - rather than re-deriving it from the consequence text a second time.
    """
    match = _IF_CONTROL_COLORED_PERMANENT_DEALS_DAMAGE_RE.fullmatch(text.strip())
    if match is None:
        return None
    color = _TOKEN_COLOR_WORDS.get(match.group("color").lower())
    if color is None:
        return None
    count_fn = count_expression(match.group("expr"))
    if count_fn is None:
        return None

    def condition_holds(game: "Game", controller: str, excluded_id: UUID | None) -> bool:
        board = game.computed_board()
        return any(
            permanent.id != excluded_id
            and board.of(permanent).controller == controller
            and color in board.of(permanent).colors
            for permanent in game.battlefield
        )

    def deal_the_damage(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        amount = count_fn(game, controller.username)
        if amount <= 0:
            return
        source = ability.source_or_last_known(game)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return condition_holds, deal_the_damage


#: "Whenever you cast a noncreature spell this turn, create a token that's a
#: copy of a non-`<Subtype>` token you control." - Summon: Good King Mog
#: XII's own Saga chapters II and III. CR 603.7a's own delayed trigger for
#: the rest of the turn - the same shape Dalkovan Encampment's "whenever you
#: attack this turn" builds above, just watching `CAST_SPELL` instead of
#: `ATTACKS` and filtered by CR 205.2a's own type negation
#: (`DelayedTrigger.forbidden_types`) rather than firing unconditionally.
#: `excluded` is optional so a bare "a token you control" (no printing in
#: the pool needs it yet) still reads.
_CAST_NONCREATURE_SPELL_THIS_TURN_COPY_TOKEN_RE = re.compile(
    r"^whenever you cast a noncreature spell this turn,\s*"
    r"create a tokens? that'?s a copy of a "
    r"(?:non-(?P<excluded>[A-Za-z]+) )?tokens? you control\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_cast_noncreature_spell_this_turn_copy_token_clause(
    text: str,
) -> AbilityEffect | None:
    """`_CAST_NONCREATURE_SPELL_THIS_TURN_COPY_TOKEN_RE`'s shape, or `None`.

    The chosen token to copy is read by `CreateTokenCopyOfControlledToken`
    itself at resolution, not here - CR 608.2c fixes *what* to copy only
    when the delayed trigger actually fires, which may be any later moment
    this turn, never at the point this ability is created.
    """
    match = _CAST_NONCREATURE_SPELL_THIS_TURN_COPY_TOKEN_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    excluded = match.group("excluded")
    excluded_subtypes = (excluded,) if excluded else ()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=match.group(0),
                event=TriggerEvent.CAST_SPELL,
                controller=controller.username,
                source_id=source_id,
                source_name=source_name,
                # See `_parse_attack_this_turn_create_tapped_attacking_tokens`
                # above for why `only_when_active` is the right field for
                # "the event's own player must be this one" even off the
                # controller's own turn (flash) - `CAST_SPELL` is never
                # subjectless, so `subjectless_only` is left at its default.
                only_when_active=controller.username,
                forbidden_types=(Type.CREATURE,),
                remaining=None,
                expires_end_of_turn=True,
                effect=CreateTokenCopyOfControlledToken(excluded_subtypes=excluded_subtypes),
            )
        )

    return effect


#: Isochron Scepter's `{2}, {T}` ability, read whole: "You may copy the exiled
#: card. If you do, you may cast the copy without paying its mana cost."
#:
#: Whole rather than per-clause because the second sentence's "the copy" is the
#: object the first sentence made: split apart, it names nothing, and CR 608.2c
#: has no notion of running half an instruction.
#:
#: CR 707.12 is the whole point of the shape: "an effect that instructs a
#: player to cast a copy of an object (and not just copy a spell) follows the
#: rules for casting spells, except that the copy is created in the same zone
#: the object is in and then cast while another spell or ability is resolving."
#: The imprinted card is in exile, so the copy is created in exile and cast
#: from there - which is why `Game.copy_spell` (CR 707.10's put-a-copy-on-the-
#: stack) is the wrong door and the copy is built here instead. CR 112.1b:
#: "some effects allow a player to cast a copy of a card; if the player does,
#: that copy is a spell as well", and CR 112.2a gives the copy's owner: "the
#: owner of that copy is the player who is instructed to create it and given
#: permission to cast it."
_COPY_EXILED_CARD_AND_CAST_RE = re.compile(
    r"^you may copy the exiled card\.?\s*"
    r"if you do, you may cast the copy without paying its mana cost\.?$",
    re.IGNORECASE,
)


#: God-Eternal Kefnet's trigger effect: "copy that card and you may cast the
#: copy. That copy costs {2} less to cast." - the card is the one the linked
#: reveal named (`ExtraTriggerEvent.REVEALED_FIRST_DRAW`).
_COPY_REVEALED_CARD_CAST_LESS_RE = re.compile(
    r"^copy that card and you may cast the copy\.\s*"
    r"that copy costs \{(?P<less>\d+)\} less to cast\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_copy_revealed_card_and_cast_for_less(text: str) -> AbilityEffect | None:
    """`_COPY_REVEALED_CARD_CAST_LESS_RE`'s shape.

    CR 707.12: the copy is created in the zone the revealed card is in - the
    hand - and cast following CR 601.2a-i with its mana cost owed less the
    stated generic reduction (CR 601.2f, CR 118.7); "may" is one CR 608.2d
    question inside `Game.may_cast_during_resolution`. A revealed card that
    has left the hand since is a new object (CR 400.7), so nothing is copied.
    CR 707.10a: a copy that is not cast ceases to exist.
    """
    match = _COPY_REVEALED_CARD_CAST_LESS_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    less = int(match.group("less"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        revealed = ability.event
        original = next(
            (c for c in controller.hand if revealed is not None and c.id == revealed.subject_id),
            None,
        )
        if original is None:
            return
        copy = CardState(
            card=original.card,
            zone=Zone.HAND,
            controller=controller.username,
            owner=controller.username,  # CR 112.2a
            is_copy=True,
        )
        controller.hand.append(copy)
        game.may_cast_during_resolution(
            copy,
            controller.username,
            prompt=f"cast the copy of {copy.name} (it costs {{{less}}} less)",
            source=source_name,
            source_id=source_id_of(ability),
            source_name=source_name,
            rule="CR 707.12",
            pays_mana_cost=True,
            cost_reduction=less,
        )
        if copy in controller.hand:
            controller.hand.remove(copy)  # CR 707.10a

    return effect


@ABILITY_TEXT.rung("s22")
def _parse_copy_exiled_card_and_cast(text: str) -> AbilityEffect | None:
    """`_COPY_EXILED_CARD_AND_CAST_RE`'s shape - Isochron Scepter's activated
    ability.

    "The exiled card" is the definite reference the Imprint clause left
    behind, found the same way `_parse_return_imprinted_clause` finds it:
    `Game.card_imprinted_on`, by the source permanent's own id, rather than a
    pointer stored anywhere. Nothing imprinted means nothing to copy, and the
    ability then does nothing (CR 101.3).

    Two CR 608.2d questions in printed order, the second being CR 118.12's
    "if you do" - so declining the first is never asked the second. A copy
    that is made and not cast does not linger: CR 707.10a is a state-based
    action, "if a copy of a card is in any zone other than the stack or the
    battlefield, it ceases to exist", and it is performed here rather than
    left for a check that does not know about this copy.

    The cast itself is `Game.may_cast_during_resolution` - CR 707.12's cast
    of a copy, CR 118.9's "without paying its mana cost", with the copy's own
    new targets chosen at CR 601.2c and its kicker offered (CR 601.2b), which
    is what makes the imprinted Orim's Chant point at a fresh player every
    activation.
    """
    if (
        _COPY_EXILED_CARD_AND_CAST_RE.fullmatch(" ".join(_strip_non_effect_preamble(text).split()))
        is None
    ):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        exiled = game.card_imprinted_on(source_id)
        if exiled is None:
            return
        controller = game.controller_of(ability)
        if not game.may(
            controller, "copy the exiled card", source=source_name, source_id=source_id_of(ability)
        ):
            return
        # CR 707.12: created in the same zone the object is in - exile.
        # CR 707.2: the copy acquires the original's copiable values, which is
        # what sharing the immutable `Card` printing amounts to here.
        copy = CardState(
            card=exiled.card,
            zone=Zone.EXILE,
            controller=controller.username,
            owner=controller.username,  # CR 112.2a
            is_copy=True,
        )
        game.exile.append(copy)
        if (
            game.may_cast_during_resolution(
                copy,
                controller.username,
                prompt="cast the copy without paying its mana cost",
                source=source_name,
                source_id=source_id_of(ability),
                source_name=source_name,
                rule="CR 707.12",
            )
            is not None
        ):
            return
        if copy in game.exile:
            game.exile.remove(copy)  # CR 707.10a

    return effect


#: "Copy those exiled cards. You may cast up to `<N>` of the copies without
#: paying their mana costs." - Baron Helmut Zemo's boast. "Those exiled
#: cards" are the ones this ability's own cost exiled (CR 602.2b's paid cost,
#: `AbilityOnStack.cost_exiled_card_ids`); "up to N" and "any number" are
#: both read, as is a plain "you may cast" that pays the copies' costs.
#:
#: CR 707.12: each copy is created in the zone its card is in - exile - and
#: cast from there while this ability resolves; CR 707.12a lets the player
#: choose "individually, for each of those objects, whether or not to cast
#: it"; CR 707.10a: a copy left in exile ceases to exist; CR 112.2a: the
#: player told to create and cast it owns it.
_COPY_COST_EXILED_CARDS_AND_CAST_RE = re.compile(
    r"^copy (?:those|the) exiled cards\.\s*"
    r"you may cast (?:up to (?P<count>\w+)|any number) of the copies"
    r"(?P<free> without paying their mana costs)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_copy_cost_exiled_cards_and_cast(text: str) -> AbilityEffect | None:
    """`_COPY_COST_EXILED_CARDS_AND_CAST_RE`'s shape; see the banner above."""
    match = _COPY_COST_EXILED_CARDS_AND_CAST_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    limit = parse_count(match.group("count")) if match.group("count") else None
    if match.group("count") and limit is None:
        return None
    free = match.group("free") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        originals = [
            card
            for card_id in ability.cost_exiled_card_ids
            if (card := game.find_by_id(card_id)) is not None and card.zone is Zone.EXILE
        ]
        copies: list[CardState] = []
        for original in originals:
            copy = CardState(
                card=original.card,
                zone=Zone.EXILE,
                controller=controller.username,
                owner=controller.username,  # CR 112.2a
                is_copy=True,
            )
            game.exile.append(copy)
            copies.append(copy)
        cast = 0
        for copy in copies:
            if limit is not None and cast >= limit:
                break
            spell = game.may_cast_during_resolution(
                copy,
                controller.username,
                prompt=(
                    f"cast the copy of {copy.name}"
                    + (" without paying its mana cost" if free else "")
                ),
                source=ability.source_name,
                source_id=source_id_of(ability),
                source_name=ability.source_name,
                rule="CR 707.12",
                pays_mana_cost=not free,
            )
            if spell is not None:
                cast += 1
        for copy in copies:
            if copy in game.exile:
                game.exile.remove(copy)  # CR 707.10a

    return effect


#: Mister Negative's Darkforce Inversion trigger, read whole: "you may exchange
#: life totals with target opponent. If you lost life this way, draw that many
#: cards."
#:
#: Whole rather than per-clause because the second sentence is *about* the
#: first: "that many" is the amount the exchange moved, which only the first
#: sentence's own return value knows. Split apart, the second clause names a
#: number nothing can supply, and CR 608.2c has no notion of running half an
#: instruction - so they are matched together or not at all.
#:
#: CR 701.12a is the exchange itself: "if the entire exchange can't happen, no
#: part of the exchange occurs", which `Player.exchange_life_totals` decides
#: before anything moves; CR 119.7 and CR 119.8 are the two prohibitions that
#: can refuse it (a player who can't gain life can't be raised by an exchange,
#: and the mirror for losing). CR 701.12c is why the movement is gains and
#: losses rather than an assignment: "each player gains or loses the amount of
#: life necessary to equal the other player's previous life total". The wrapper
#: reached is `Game.exchange_life_totals`, not the `Player` primitive under it:
#: the wrapper is what emits CR 701.12c's gain and loss events, which CR 119.9's
#: "whenever a player gains life" triggers watch.
_EXCHANGE_LIFE_TOTALS_THEN_DRAW_RE = re.compile(
    r"^(?P<may>you may )?exchange life totals with target opponent\.?"
    r"(?:\s*if you lost life this way, (?P<draw>draw that many cards)\.?)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_exchange_life_totals_then_draw(text: str) -> AbilityEffect | None:
    """`_EXCHANGE_LIFE_TOTALS_THEN_DRAW_RE`'s shape - Mister Negative's own
    enters trigger.

    The opponent is a real CR 115.1 target, chosen when the ability went on
    the stack, so it is read back through `Game.resolve_targets` - CR 608.2b's
    legality check included: an opponent who has left the game since is no
    longer a legal target and the ability then has nothing to exchange with.

    "You may" is CR 608.2d's plain optional question, asked before anything
    moves. Declining, or a CR 701.12a refusal, both leave the amount at 0, and
    a draw of "that many" is then a draw of none - CR 121.2's "if a player is
    instructed to draw multiple cards, that player performs that many
    individual card draws", of which zero is a legal count.

    The draw is guarded on having *lost* life, as printed: the exchange is
    signed from this player's side, so a controller who gained draws nothing.
    """
    match = _EXCHANGE_LIFE_TOTALS_THEN_DRAW_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    optional = match.group("may") is not None
    draws = match.group("draw") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        opponent = next(
            (thing for thing in game.resolve_targets(ability) if isinstance(thing, Player)),
            None,
        )
        if opponent is None:
            return
        source_name = ability.source_name
        if optional and not game.may(
            controller,
            "exchange life totals with target opponent",
            source=source_name,
            source_id=source_id_of(ability),
        ):
            return
        lost = game.exchange_life_totals(controller, opponent)
        if draws and lost > 0:
            game.draw_cards(controller, lost)

    return effect


def _armies_controlled_by(game: "Game", controller: str) -> list[CardState]:
    """Every Army **creature** `controller` controls (CR 701.47a), read off
    the computed board rather than the printing: an Army is often a token
    whose subtypes came from a `TokenDefinition`, and a permanent can have
    become one through layer 4 (this function's own last step does exactly
    that), neither of which is on `Card`.
    """
    armies: list[CardState] = []
    for permanent in game.battlefield:
        if game.controller_of(permanent).username != controller:
            continue
        characteristics = game.characteristics_of(permanent)
        if not characteristics.is_creature:
            continue
        if any(subtype.lower() == "army" for subtype in characteristics.subtypes):
            armies.append(permanent)
    return armies


#: "Copy that spell[. You may choose new targets for the copy.]" - Jin-
#: Gitaxias, Progress Tyrant's own "Whenever you cast an artifact, instant,
#: or sorcery spell" trigger, the bare form of the same CR 607.1 "that
#: spell" anaphora `_parse_counter_that_spell_clause` reads, plus CR 707.10's
#: copy (`Game.copy_spell`) and CR 707.10c's own retargeting offer (`Game.
#: offer_new_targets_for_copy`) - the same two primitives `_parse_target_
#: opponent_draw_then_copy_that_spell_clause` already uses for Alania,
#: Divergent Storm's richer two-clause chain, here with nothing in front of
#: the copy at all. Mica, Reader of Ruins joins the two with "and" instead of
#: a period ("copy that spell and you may choose new targets for the copy") -
#: the same permission (CR 707.10c).
_COPY_THAT_SPELL_RE = re.compile(
    r"^copy that spell(?:\.|,)?"
    r"(?P<new_targets>\s*(?:and )?you may choose new targets for the copy\.?)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s27", for_spell=False)
@MIXED_CLAUSE.rung("s28", for_spell=FORWARD)
def _parse_copy_that_spell_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """Ability-only (`for_spell=False`), the same restriction `_parse_
    counter_that_spell_clause` holds itself to: "that spell" only resolves
    against `ability.event`, which a spell being cast does not have.
    """
    if for_spell:
        return None
    match = _COPY_THAT_SPELL_RE.fullmatch(clause.strip())
    if match is None:
        return None
    offer_new_targets = match.group("new_targets") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None:
            return
        # CR 608.2h: "that spell" is not a target, so one countered in
        # response is still copied, as it last existed on the stack.
        copy = game.copy_spell_as_last_known(spell, controller=ability.controller)
        if offer_new_targets:
            game.offer_new_targets_for_copy(
                copy,
                ability.controller,
                source_name=ability.source_name,
                source_id=source_id_of(ability),
            )

    return effect


#: "Copy target <qualifier> spell[ you control]." - Reverberate's own bare
#: shape, plus Increasing Vengeance's own "If this spell was cast from a
#: graveyard, copy that spell twice instead." rider and either card's
#: optional "You may choose new targets for the copy/copies." permission.
#: Unlike `_COPY_THAT_SPELL_RE` above, the copied object is the stack
#: object's own announced target (CR 601.2c for a spell, CR 115.1c/602.2b
#: for an activated ability - `targets` either way, the `_COUNTER_TARGET_
#: SPELL_RE` "counter target spell" precedent), not CR 607.1's "that spell"
#: anaphora back to a triggering `CAST_SPELL` event. So it reads the same
#: printed on a spell (Reverberate, Increasing Vengeance) and on an
#: activated ability (Mirrorpool, Nivix Guildmage: "instant or sorcery
#: spell you control"; Drafna, Founder of Lat-Nam: "artifact spell you
#: control. (The copy becomes a token.)" - the reminder is stripped by
#: `_strip_non_effect_preamble`, and CR 707.10f's token is `Game.
#: resolve_top`'s own resolution of a copied permanent spell).
#: `_SPELL_QUALIFIER` already reads every type word the printings use, and
#: the type and "you control" restrictions are enforced at announcement by
#: `machines/targeting.py`, not here.
_COPY_TARGET_SPELL_RE = re.compile(
    rf"^copy target(?: {_SPELL_QUALIFIER})? spell(?: you control)?\.?"
    r"(?P<doubles>\s*if this spell was cast from a graveyard,\s*"
    r"copy that spell twice instead\.)?"
    r"(?P<new_targets>\s*you may choose new targets for the cop(?:y|ies)\.?)?"
    r"(?P<gains>\s*the copy gains (?P<keywords>[a-z ,]+?)"
    r"(?:,? and \"(?P<quoted>[^\"]+)\")?\.?)?\s*$",
    re.IGNORECASE,
)

#: "The copy gains `<keywords>`[ and "`<ability>`"]." (Choreographed Sparks'
#: second mode) - what the copy of a spell gains as it is put onto the stack,
#: carried onto the token it becomes (CR 707.10f, CR 400.7b's permanent-spell
#: exception, `CardState.move_to`). Each keyword has to be one combat reads
#: (`machines/combat.Keyword`), or the rider is not read at all.
_COPY_GAINS_KEYWORD_SPLIT_RE = re.compile(r"\s*(?:,\s*and|,|\band)\s*", re.IGNORECASE)


def _parse_copy_target_spell_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_COPY_TARGET_SPELL_RE`'s shape, tried against the whole unsplit text
    (see the call site in `_parse_mixed_clauses`) for the same reason
    `_parse_copy_that_spell_clause` is: a bare period joins its sentences,
    which `_prepare_effect_clauses` would otherwise cut apart before any
    per-clause dispatch ever saw them together.

    `text` is stripped through `_strip_non_effect_preamble` first, the same
    call `_prepare_effect_clauses` itself makes - Increasing Vengeance's own
    printed text carries a trailing "Flashback {cost} (reminder text)." line
    (CR 702.32a's own keyword-ability line, not part of this spell's CR
    608.2c resolution at all), which `_strip_keyword_ability_lines` (the last
    step of `_strip_non_effect_preamble`) is what removes; left in, it would
    trail after `_COPY_TARGET_SPELL_RE`'s own `$` anchor and the whole clause
    would silently fail to match instead of being read.

    CR 707.10: each spell the caster actually targeted, still on the stack
    (CR 608.2b - an illegal or already-resolved/countered target is simply
    skipped, `counter_targets`'s own precedent), is put through `Game.
    copy_spell` once, or twice when the graveyard rider applies. That rider
    reads *this spell's own* `CastRecord` (`game.cast_record(spell)`), never
    the copied target's: CR 707.10 is explicit that a copy "isn't cast" at
    all, so a copy of Increasing Vengeance itself (built by some further
    copy effect, the way Doublecast or Reverberate would build one) was
    never "cast from a graveyard" regardless of where the original it copies
    came from - `CastRecord.is_copy` is what settles that read, not leaning
    on `origin_zone is not Zone.GRAVEYARD` alone (a copy's `origin_zone` is
    unconditionally forced to `Zone.STACK` by `Game.copy_spell`, which
    already answers "not from a graveyard" on its own, but `is_copy` is the
    field written for exactly this kind of negation-shaped read).
    """
    stripped = " ".join(_strip_non_effect_preamble(text).strip().split())
    match = _COPY_TARGET_SPELL_RE.fullmatch(stripped)
    if match is None:
        return None
    doubles_from_graveyard = match.group("doubles") is not None
    if doubles_from_graveyard and not for_spell:
        # "If this spell was cast ..." only means anything on a spell.
        return None
    offer_new_targets = match.group("new_targets") is not None
    gained = _copy_gains_lines(match.group("keywords"), match.group("quoted"))
    if match.group("gains") is not None and gained is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        copies = 1
        if doubles_from_graveyard and isinstance(stack_object, CardState):
            record = game.cast_record(stack_object)
            if not record.is_copy and record.origin_zone is Zone.GRAVEYARD:
                copies = 2
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        for reference in stack_object.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            for _ in range(copies):
                copy = game.copy_spell(target, controller=controller)
                if copy is not None and gained:
                    copy.granted_ability_texts = (
                        *copy.granted_ability_texts,
                        *(line for line in gained if line not in copy.granted_ability_texts),
                    )
                if offer_new_targets:
                    game.offer_new_targets_for_copy(
                        copy,
                        controller,
                        source_name=source_name,
                        source_id=source_id_of(stack_object),
                    )

    return effect


def _copy_gains_lines(keywords: str | None, quoted: str | None) -> tuple[str, ...] | None:
    """`_COPY_TARGET_SPELL_RE`'s "The copy gains ..." rider as the ability
    lines the copy is granted, `()` when there is no rider, or None when a
    keyword is not one combat executes or the quoted ability does not parse
    - an unread rider fails the whole clause closed."""
    if keywords is None:
        return ()
    lines: list[str] = []
    for word in _COPY_GAINS_KEYWORD_SPLIT_RE.split(keywords.strip()):
        if not word:
            continue
        try:
            Keyword(word.lower())
        except ValueError:
            return None
        lines.append(word.capitalize())
    if quoted is not None:
        if not parse_granted_ability_lines([quoted]):
            return None
        lines.append(quoted)
    return tuple(lines)


#: "Create `<n>` token(s) that('s a copy|are copies) of it." - Gruff Triplets'
#: ETB ("if it isn't a token, create two tokens that are copies of it") and
#: Sphinx of False Conclusions' dies trigger ("if it isn't a token, create a
#: token that's a copy of it"). "It" is the ability's own source (CR 109.2,
#: `intervening_if_holds`'s "it isn't a token" clause above already checked
#: the same referent) - not a target, so no `_targets_understood` gate is
#: needed the way `_parse_create_token_copy_of_target_clause` below needs one.
#: CR 700.7's "this `<something>`" names the same source - Phoenix Fleet
#: Airship's "create a token that's a copy of this Vehicle", Scute Swarm's
#: "... a copy of this creature instead".
#:
#: The Notary Hobbits widen it twice: a plural self-reference ("copies of
#: them", the card's own name being plural) and CR 707.9b's "except the
#: tokens aren't legendary" / "except it isn't legendary" (Impostor Syndrome,
#: where "it" is the creature that dealt the damage - the trigger's own event
#: subject, see `_self_copy_token_object`).
_SELF_COPY_TOKEN_RE = re.compile(
    rf"^create (?P<n>{COUNT}) "
    r"(?:tokens that are copies|token that(?:'s| is) a copy) of (?P<of>it|them|this [a-z]+)"
    r"(?P<nonlegendary>,? except (?:the tokens aren['’]t|they aren['’]t|it isn['’]t|"
    r"the token isn['’]t) legendary)?\.?$",
    re.IGNORECASE,
)


def _self_copy_token_object(game: "Game", ability: AbilityOnStack, word: str) -> CardState | None:
    """What `_SELF_COPY_TOKEN_RE`'s "it"/"them" names: the trigger's own event
    subject when it has one (CR 603.2 - Impostor Syndrome's "a nontoken
    creature you control deals combat damage", Sphinx of False Conclusions'
    own death, Gruff Triplets' own entry), else the ability's own source;
    "this `<something>`" is always the source (CR 700.7). CR 113.7a/608.2h:
    an object that has left its zone is read by its last known information."""
    event = ability.event
    if word.lower() in ("it", "them") and event is not None and event.subject_id is not None:
        subject = game.find_by_id(event.subject_id)
        if subject is not None:
            return subject
    return ability.source_or_last_known(game)


@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_self_copy_token_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SELF_COPY_TOKEN_RE`'s shape, or `None` if this is not it.

    Ability-only: both pool cards printing this shape are permanents'
    triggered abilities copying themselves, and `source_or_last_known` is
    what makes a *dies* trigger's own "it" answerable at all (CR 113.7a,
    CR 608.2h) once the source has already left the battlefield - a spell has
    no comparable look-back object to fall back to.
    """
    if for_spell:
        return None
    match = _SELF_COPY_TOKEN_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    count = parse_count(match.group("n"))
    not_legendary = match.group("nonlegendary") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        controller = game.controller_of(stack_object).username
        original = _self_copy_token_object(game, stack_object, match.group("of"))
        if original is None:
            return
        token_copy_of(game, original, controller, count=count, not_legendary=not_legendary)

    return effect  # type: ignore[return-value]


#: "For each creature target player controls, create a token that's a copy of
#: that creature[, except it has `<keyword>`[ and "`<ability>`"]]." - Clone
#: Legion (no "except" tail) and Face Yourself's own "except it has haste and
#: '...'" - a mixed keyword-then-quoted-ability tail neither
#: `_parse_token_tail` (a single quoted string *or* bare keywords, never
#: both) nor `_CREATE_TOKEN_COPIES_EXCEPT_RE`'s own tail (quoted only) reads,
#: so `_parse_copy_added_ability_lines` below reads it directly.
_FOR_EACH_CREATURE_TARGET_PLAYER_COPY_RE = re.compile(
    r"^for each creature target player controls,\s*"
    r"create a token that'?s a copy of that creature"
    r"(?:,\s*except (?:it has|they have)\s+(?P<except_tail>.+?))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_copy_added_ability_lines(tail: str) -> tuple[str, ...] | None:
    """ "`<keyword>`[, `<keyword>`][ and] ["`<ability>`"]" - CR 707.9a's added
    abilities, as lines ready for `copiable_card_with_added_abilities`: a bare
    keyword from `_TOKEN_KEYWORDS` is title-cased the way a real printing
    lists one, and a trailing quoted sentence is copied through exactly as
    printed. Any other part - a shape this wave does not read - fails the
    whole tail rather than dropping it silently.

    The quoted sentence is peeled off *first*, by its own closing quote mark
    at the end of the whole tail, rather than folded into the same comma/
    "and" split the bare keywords go through - Face Yourself's own quoted
    ability ("if you don't control a planeswalker, **sacrifice this
    creature**") has a comma of its own inside the quotes, which a naive
    split would cut the sentence in half at.
    """
    tail = tail.strip()
    quoted_text: str | None = None
    if quote := re.search(r"""["“'‘](?P<text>.+)["”'’]\s*$""", tail, re.DOTALL):
        quoted_text = quote.group("text")
        tail = re.sub(r"\s+and\s*$", "", tail[: quote.start()]).strip()
    added: list[str] = []
    if tail:
        parts = [part.strip() for part in re.split(r",\s*|\s+and\s+", tail) if part.strip()]
        for part in parts:
            if part.lower() not in _TOKEN_KEYWORDS:
                return None
            added.append(part.title())
    if quoted_text is not None:
        added.append(quoted_text)
    if not added:
        return None
    return tuple(added)


@ABILITY_TEXT.rung("s15", for_spell=False)
@SPELL_TEXT.rung("s13", for_spell=True)
def _parse_for_each_creature_target_player_copy_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_FOR_EACH_CREATURE_TARGET_PLAYER_COPY_RE`'s shape, or `None`.

    The creatures target player controls are read once, off the computed
    board (CR 613.5), at the moment this instruction resolves (CR 611.2c) -
    the same fixed-set-now convention `_mass_creature_group_targets` already
    uses for an untargeted "creatures you control", applied here to a
    targeted player's own instead.
    """
    match = _FOR_EACH_CREATURE_TARGET_PLAYER_COPY_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    added: tuple[str, ...] = ()
    except_tail = match.group("except_tail")
    if except_tail is not None:
        read = _parse_copy_added_ability_lines(except_tail)
        if read is None:
            return None
        added = read

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, Player):
                continue
            board = game.computed_board()
            creatures = [
                permanent
                for permanent in game.battlefield
                if board.of(permanent).controller == target.username
                and Type.CREATURE in board.of(permanent).types
            ]
            for creature in creatures:
                token_copy_of(game, creature, controller, added_abilities=added)

    return effect


#: "For each nontoken creature you control, create a token that's a copy of
#: that creature, except it isn't legendary." (Multiversal Incursion) - the
#: you-control twin of `_FOR_EACH_CREATURE_TARGET_PLAYER_COPY_RE`, with CR
#: 707.9b's nonlegendary exception. The creatures are read once, off the
#: computed board, as the instruction resolves (CR 611.2c's fixed-set-now
#: convention), so the new tokens are not copied in turn.
_FOR_EACH_CREATURE_YOU_CONTROL_COPY_RE = re.compile(
    r"^for each (?P<nontoken>nontoken )?creature you control,\s*"
    r"create a token that['’]?s a copy of that creature"
    r"(?P<nonlegendary>,\s*except it isn['’]t legendary)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s15", for_spell=False)
@SPELL_TEXT.rung("s13", for_spell=True)
def _parse_for_each_creature_you_control_copy_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_FOR_EACH_CREATURE_YOU_CONTROL_COPY_RE`'s shape, or `None`."""
    match = _FOR_EACH_CREATURE_YOU_CONTROL_COPY_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    nontoken = match.group("nontoken") is not None
    not_legendary = match.group("nonlegendary") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        board = game.computed_board()
        creatures = [
            permanent
            for permanent in game.battlefield
            if board.of(permanent).controller == controller
            and Type.CREATURE in board.of(permanent).types
            and not (nontoken and permanent.token)
        ]
        for creature in creatures:
            token_copy_of(game, creature, controller, not_legendary=not_legendary)

    return effect


#: One part of CR 707.9b's exception *list*: "it isn't legendary" / "it's not
#: legendary", "[it's|is] a[n] [N/N ]`<Subtype>` in addition to its other
#: types", "[it ]has `<keywords>`" (The Cloning of Shredder's "except it isn't
#: legendary and is a Mutant in addition to its other types", Ember Island
#: Production's "except it's not legendary and it's a 4/4 Hero in addition
#: to its other types"). Mirror Room's "except it's a Reflection in addition
#: to its other creature types" is the same CR 205.1b exception worded for the
#: one kind of subtype it adds.
_EXCEPT_NOT_LEGENDARY_PART_RE = re.compile(
    r"^(?:it |they )?(?:isn['’]t|is not|aren['’]t|are not|['’]s not|['’]re not|it['’]s not|"
    r"they['’]re not) legendary$",
    re.IGNORECASE,
)
_EXCEPT_SUBTYPE_PART_RE = re.compile(
    r"^(?:it['’]?s|is|it is) an? (?:(?P<power>\d+)/(?P<toughness>\d+) )?"
    r"(?P<subtype>[A-Z][a-z]+) in addition to its other (?:creature )?types$"
)
_EXCEPT_HAS_PART_RE = re.compile(r"^(?:it )?has (?P<keywords>[a-z][a-z ]*)$", re.IGNORECASE)
#: CR 707.9a's quoted form, stashed out of the list before it is split on
#: commas (Delina: `it has "At end of combat, exile this token."`).
_EXCEPT_QUOTE_RE = re.compile(r'["\u201c](?P<ability>[^"\u201d]+)["\u201d]')
_EXCEPT_HAS_QUOTE_PART_RE = re.compile(r"^(?:it )?has \x00(?P<index>\d+)\x00$", re.IGNORECASE)


def _read_copy_exception_list(except_text: str | None) -> _CopyExceptionList | None:
    """A token copy's ", except `<list>`" when it is a *list* naming "isn't
    legendary" or a subtype "in addition to its other types" (CR 707.9b: each
    modified value "becomes part of the copiable values of the copy"), parts
    joined by commas and/or "and". `None` for a tail with any other part, or
    with neither of those two parts - the single-exception shapes
    `_read_token_copy_except` already reads keep their own reader."""
    if except_text is None:
        return None
    quoted: list[str] = []

    def stash(match: re.Match[str]) -> str:
        quoted.append(match.group("ability").strip())
        return f"\x00{len(quoted) - 1}\x00"

    stripped = _EXCEPT_QUOTE_RE.sub(stash, " ".join(except_text.strip().split()))
    stripped = stripped.rstrip(".")
    parts = [part.strip() for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", stripped) if part]
    not_legendary = False
    subtype: str | None = None
    power: int | None = None
    toughness: int | None = None
    abilities: list[str] = []
    for part in parts:
        if _EXCEPT_NOT_LEGENDARY_PART_RE.fullmatch(part):
            not_legendary = True
        elif (typed := _EXCEPT_SUBTYPE_PART_RE.fullmatch(part)) is not None and subtype is None:
            subtype = typed.group("subtype")
            if typed.group("power") is not None:
                power, toughness = int(typed.group("power")), int(typed.group("toughness"))
        elif (granted := _EXCEPT_HAS_QUOTE_PART_RE.fullmatch(part)) is not None:
            abilities.append(quoted[int(granted.group("index"))])
        elif (has := _EXCEPT_HAS_PART_RE.fullmatch(part)) is not None:
            keywords = split_and_validate_keywords(has.group("keywords"))
            if keywords is None:
                return None
            abilities.append(", ".join(keywords))
        else:
            return None
    if not not_legendary and subtype is None:
        return None
    return _CopyExceptionList(not_legendary, subtype, power, toughness, tuple(abilities))


#: "[You may] copy that spell. The copy targets `<self-reference>`." - Ivy,
#: Gleeful Spellthief's own cast trigger effect, once its own "a player casts
#: a spell that targets only a single creature other than Ivy" condition has
#: been split off (`machines/triggers._targets_only_single_creature_other_
#: than_re` reads *that* half - CR 601.2c's target-count restriction). This
#: is the bare retarget, with no token-creation clause in front of it the way
#: Frontline Heroism's own "create a ... token, then copy that spell. The
#: copy targets that token." pairs one, so `_parse_create_token_then_copy_
#: spell_retargeted_clause` above stays the reader for that shape and is
#: never tried against this one - its own `token_clause` group has nothing
#: to match on a bare "copy that spell.".
#:
#: `<self-reference>` only ever reaches this reader normalized: the literal
#: printed name ("The copy targets Ivy.") is what `trigger_effect_for`'s
#: first, unnormalized pass tries, and only the second,
#: `machines/abilities.self_normalized_effect_text` pass turns it into "this
#: permanent" before any clause parser sees it - the same two-pass precedent
#: `trigger_effect_for`'s own docstring already documents for Ruby, Daring
#: Tracker's own printed-name pump.
_COPY_THAT_SPELL_RETARGETED_RE = re.compile(
    r"^(?P<may>you may )?copy that spell\.\s*the copy targets "
    r"(?:this permanent|this creature)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_copy_that_spell_retargeted_clause(text: str) -> AbilityEffect | None:
    """`_COPY_THAT_SPELL_RETARGETED_RE`'s shape - Ivy, Gleeful Spellthief.

    CR 707.10e: "the copy targets `<X>`" specifies the copy's own new target
    rather than offering CR 707.10c's optional "you may choose new targets"
    permission, so this reaches `Game.copy_spell_targeting` (not `Game.
    offer_new_targets_for_copy`) exactly the way `_parse_create_token_then_
    copy_spell_retargeted_clause` above does for Frontline Heroism - it
    builds the copy only if the trigger's own source is a legal target for
    every instance of "target" on the spell, and creates nothing at all
    otherwise; nothing here ever overwrites `copy.targets` directly. Ivy's
    own "you may" is CR 608.2d's ordinary optional permission, asked before
    the attempt - answering no is always legal and simply means no copy is
    made, the same as an illegal specified target does.
    """
    match = _COPY_THAT_SPELL_RETARGETED_RE.fullmatch(text.strip())
    if match is None:
        return None
    optional = match.group("may") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None or spell not in game.stack:
            return
        source = ability.source(game)
        if source is None:
            return
        if optional and not game.may(
            game.player(ability.controller),
            "copy that spell",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        game.copy_spell_targeting(spell, ability.controller, source)

    return effect


#: "Change the target to enchanted creature if able." (Captured by the
#: Consulate's cast trigger, once its "if it has a single target" has been
#: split off) - CR 115.7a: the trigger's event is the cast of the spell whose
#: target changes, the new target is the permanent the Aura is attached to
#: (CR 303.4b), and "if able" is CR 115.7a's own rule: a target that can't
#: be changed to another legal target stays as it was.
_CHANGE_TARGET_TO_RE = re.compile(
    r"^change the target to (?P<new>enchanted (?:creature|permanent|land)|"
    r"this (?:creature|permanent))(?P<able> if able)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_change_the_target_to_clause(text: str) -> AbilityEffect | None:
    """`_CHANGE_TARGET_TO_RE`'s shape - see its docstring. Goes through
    `Game.change_targets`, the one CR 115.7 retargeting path, so the new
    target is checked exactly like an announced one (protection, hexproof,
    the requirement the old target filled)."""
    match = _CHANGE_TARGET_TO_RE.fullmatch(text.strip())
    if match is None:
        return None
    attached = match.group("new").lower().startswith("enchanted")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None or spell not in game.stack:
            return
        source = ability.source(game)
        if source is None:
            return
        destination = (
            game.find_by_id(source.attached_to)
            if attached and source.attached_to is not None
            else None
            if attached
            else source
        )
        if not isinstance(destination, CardState) or destination.zone is not Zone.BATTLEFIELD:
            return
        game.change_targets(
            spell,
            ability.controller,
            scope=RetargetScope.ALL,
            to=destination,
            source_name=ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


#: Flamehold Grappler's whole enters trigger, once its condition has been split
#: off: "copy the next spell you cast this turn when you cast it. You may choose
#: new targets for the copy."
#:
#: Read whole rather than per clause: the second sentence's "the copy" is the
#: object the first sentence's own delayed ability will make, so split apart it
#: names nothing (CR 608.2c has no notion of running half an instruction) - the
#: same treatment `_CREATE_TOKEN_THEN_COPY_SPELL_RETARGETED_RE` above already
#: gets for Frontline Heroism's two-sentence pair.
#:
#: "When you cast it" is what makes this a delayed triggered ability rather than
#: something this resolution does now. CR 603.7a: "Delayed triggered abilities
#: are created during the resolution of spells or abilities ... A delayed
#: triggered ability won't trigger until it has actually been created, even if
#: its trigger event occurred just beforehand" - so the spell that put the
#: Grappler itself on the stack is never the one copied, however recently it was
#: cast.
_COPY_NEXT_SPELL_YOU_CAST_RE = re.compile(
    r"^copy the next spell you cast this turn when you cast it\."
    r"(?P<new_targets>\s*you may choose new targets for the copy\.?)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_copy_next_spell_you_cast_clause(text: str) -> AbilityEffect | None:
    """`_COPY_NEXT_SPELL_YOU_CAST_RE`'s shape - Flamehold Grappler.

    Creates one `DelayedTrigger` watching `TriggerEvent.CAST_SPELL`, which
    `Game.put_on_stack` already emits for every spell cast (CR 707.10 is
    explicit that a *copy* is not cast, so a copy this ability makes can never
    feed it a second time).

    - `remaining=1` is CR 603.7b's default and is exactly "the **next** spell".
    - `expires_end_of_turn=True` is CR 603.7b's "unless it has a stated
      duration, such as 'this turn'" - printed here as "this turn", so a
      Grappler whose controller casts nothing else this turn does not carry the
      permission into the next one.
    - `only_when_active` scopes the event to one player. It is named for the
      active player because that is what its first user needed, but every
      reader of it compares `GameEvent.player` and nothing else (see
      `DelayedTrigger.matches`), and `Game.put_on_stack` sets that field to the
      caster - so this is CR 109.5's "you" ("copy the next spell **you** cast"),
      read exactly, not an approximation.
    - CR 603.7d/e put the source and the controller on the ability that created
      this one, which is the Grappler's own enters trigger.

    **The spell is resolved from last known information.** DDR#977's whole
    point is that the copy still happens when the original was countered in
    response: the delayed ability goes on the stack above the spell it is
    copying, an opponent may then put a counterspell above *that*, and by the
    time this callback runs the original may be in a graveyard. So the object
    is fetched by `Game.find_by_id` - which searches every zone - rather than
    off `Game.stack`. CR 608.2b's on-resolution target check is what would
    normally punish a vanished object, and it does not apply here: it only
    refuses an object that "specifies targets", and this ability specifies
    none.

    CR 707.10c is the second sentence: "Some effects copy a spell or ability
    and state that its controller may choose new targets for the copy." It is
    only offered when the card actually prints it, so the group is optional
    here rather than assumed.

    CR 707.10f finishes the job with no help from this clause: "Some effects
    copy a permanent spell. As that copy resolves, it ceases being a copy of a
    spell and becomes a token permanent" - `Game.resolve_top` already does that.
    """
    match = _COPY_NEXT_SPELL_YOU_CAST_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    may_retarget = match.group("new_targets") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        game.create_delayed_trigger(
            DelayedTrigger(
                text="Copy the next spell you cast this turn when you cast it.",
                event=TriggerEvent.CAST_SPELL,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                only_when_active=ability.controller,
                remaining=1,
                expires_end_of_turn=True,
                effect=CopyNextSpellYouCast(may_retarget=may_retarget),
            )
        )

    return effect


#: "When you next cast an instant or sorcery spell this turn, copy that
#: spell. You may choose new targets for the copy." - Doublecast, off-set,
#: and Way of the Cryomancer's own granted `[-3]`, Chandra, the Firebrand's
#: `-2`, Ral, Storm Conduit's `-2` among many others. `_COPY_NEXT_SPELL_YOU_
#: CAST_RE`'s own sibling shape: the same CR 603.7a delayed trigger and the
#: same `CopyNextSpellYouCast` effect, restricted to CR 300.1's instant and
#: sorcery card types (`DelayedTrigger.required_any_types`) rather than
#: "the next spell" unrestricted, and phrased as "when you next cast ...,
#: copy that spell" instead of "copy the next spell ... when you cast it" -
#: a different sentence for the identical CR 603.7 mechanism, not a
#: different one.
#: Widened (ecl T7) to "copy it" - Rimefire Torque's and Najal, the Storm
#: Runner's own wording of the identical instruction.
_COPY_NEXT_INSTANT_OR_SORCERY_YOU_CAST_RE = re.compile(
    r"^when you next cast an instant or sorcery spell this turn, copy (?:that spell|it)\."
    r"(?P<new_targets>\s*you may choose new targets for the copy\.?)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_copy_next_instant_or_sorcery_you_cast_clause(text: str) -> AbilityEffect | None:
    """`_COPY_NEXT_INSTANT_OR_SORCERY_YOU_CAST_RE`'s shape."""
    match = _COPY_NEXT_INSTANT_OR_SORCERY_YOU_CAST_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    may_retarget = match.group("new_targets") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        game.create_delayed_trigger(
            DelayedTrigger(
                text=("When you next cast an instant or sorcery spell this turn, copy that spell."),
                event=TriggerEvent.CAST_SPELL,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                only_when_active=ability.controller,
                remaining=1,
                expires_end_of_turn=True,
                required_any_types=(Type.INSTANT, Type.SORCERY),
                effect=CopyNextSpellYouCast(may_retarget=may_retarget),
            )
        )

    return effect


#: "When you next cast a creature spell this turn, that creature enters with
#: an additional +1/+1 counter on it." (Kumano Faces Kakkazan's chapter II) -
#: the same CR 603.7a delayed cast trigger as the copy shapes above, with the
#: counter riding the cast spell's record (`SpellEntersWithAdditionalCounter`).
_NEXT_SPELL_ENTERS_WITH_ADDITIONAL_COUNTER_RE = re.compile(
    r"^when you next cast an? (?P<type>creature|artifact|enchantment|planeswalker) spell "
    r"this turn, that (?:creature|permanent) enters with an additional "
    r"(?P<kind>\+1/\+1|[a-z]+) counter on it\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_next_spell_enters_with_additional_counter_clause(text: str) -> AbilityEffect | None:
    """`_NEXT_SPELL_ENTERS_WITH_ADDITIONAL_COUNTER_RE`'s shape."""
    match = _NEXT_SPELL_ENTERS_WITH_ADDITIONAL_COUNTER_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    card_type = Type(match.group("type").lower())
    counter_kind = match.group("kind").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        game.create_delayed_trigger(
            DelayedTrigger(
                text=(
                    f"When you next cast a {card_type.value} spell this turn, that "
                    f"{card_type.value} enters with an additional {counter_kind} counter on it."
                ),
                event=TriggerEvent.CAST_SPELL,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                only_when_active=ability.controller,
                remaining=1,
                expires_end_of_turn=True,
                required_any_types=(card_type,),
                effect=SpellEntersWithAdditionalCounter(counter_kind=counter_kind),
            )
        )

    return effect


@SPELL_TEXT.rung("s10")
def _parse_copy_next_instant_or_sorcery_you_cast_spell_clause(text: str) -> Effect | None:
    """`_COPY_NEXT_INSTANT_OR_SORCERY_YOU_CAST_RE`'s shape, for a resolving
    *spell* rather than an ability - Doublecast, Galvanic Iteration, Howl of
    the Horde (all off-set) print this exact sentence as their whole card.
    `_parse_copy_next_instant_or_sorcery_you_cast_clause`'s own ability
    callback reads `ability.controller`/`source_id`/`source_name` off an
    `AbilityOnStack`; a spell's own resolving callback gets a bare
    `CardState` instead, so this is that same match and delayed-trigger
    construction with the other of the two callback shapes `effect_for`
    and `_ability_effect_or_notice` each expect.
    """
    match = _COPY_NEXT_INSTANT_OR_SORCERY_YOU_CAST_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    may_retarget = match.group("new_targets") is not None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=("When you next cast an instant or sorcery spell this turn, copy that spell."),
                event=TriggerEvent.CAST_SPELL,
                controller=controller.username,
                source_id=spell.id,
                source_name=spell.name,
                only_when_active=controller.username,
                remaining=1,
                expires_end_of_turn=True,
                required_any_types=(Type.INSTANT, Type.SORCERY),
                effect=CopyNextSpellYouCast(may_retarget=may_retarget),
            )
        )

    return effect


# --------------------------------------------------------------------------
# "Copy this spell." (CR 707.10)
# --------------------------------------------------------------------------
#
# Sage of the Skies' own cast trigger: "When you cast this spell, if you've
# cast another spell this turn, copy this spell." CR 707.10 is what a copy of
# a spell on the stack is, CR 707.10f and CR 608.3f are what happens to a copy
# of a *permanent* spell when it resolves ("it ceases being a copy of a spell
# and becomes a token permanent"), and CR 111.13 says the same from the token
# side: "A copy of a permanent spell becomes a token as it resolves." That is
# exactly the parenthesis Sage of the Skies prints.
#
# `Game.copy_spell` already does all of that. "This spell" is the spell that
# was cast, which for a cast trigger is the object
# the trigger's event names, not the ability's source permanent (the source is
# the same card, but it is on the *stack*, and `AbilityOnStack.source(game)`
# finding it there by id is precisely what makes this readable).

_COPY_THIS_SPELL_RE = re.compile(r"^copy this spell\.?$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_copy_this_spell_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_COPY_THIS_SPELL_RE`'s shape - Sage of the Skies' cast trigger.

    Only ever an ability's shape: a spell that said this about itself would
    be copying the object that is resolving, which CR 608.2n has already
    finished with. The copy is put on the stack by `Game.copy_spell` above
    the ability that made it (CR 707.10: to copy a spell "means to put a copy of it onto the
    stack"), so it resolves before anything under it.

    Silently does nothing when the spell is no longer on the stack - it was
    countered, or it already resolved - which leaves nothing to copy rather
    than being an error.
    """
    if for_spell:
        return None
    if _COPY_THIS_SPELL_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.STACK:
            return
        game.copy_spell(source, game.controller_of(stack_object).username)

    return effect


#: CR 115.7a/115.7b/115.7c: "[You may] change the target of target <noun>
#: [with a single target] [to this creature]." - Bolt Bend, Redirect
#: Lightning and Ricochet Trap ("the target", CR 115.7a), Hydroelectric
#: Specimen ("you may ... to this creature"), Spellskite ("a target ... to
#: this creature", CR 115.7b). The noun and its "with a single target"
#: restriction (CR 115.9a) are the targeting requirement
#: `machines/targeting.py` reads; this reads only the change itself.
_CHANGE_TARGET_RE = re.compile(
    r"^(?P<may>you may )?change (?P<scope>the|a|any) targets?(?:\(s\))? of target [^.]+?"
    r"(?: to (?P<to>this (?:creature|permanent|artifact|enchantment|land)))?\.?$",
    re.IGNORECASE,
)

_RETARGET_SCOPES = {"the": RetargetScope.ALL, "a": RetargetScope.ONE, "any": RetargetScope.ANY}


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_change_target_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_CHANGE_TARGET_RE`'s shape: change the target(s) of this object's own
    single target, a spell or ability on the stack, through
    `Game.change_targets`.

    The object changed is taken through `Game.resolve_targets`, so one that has
    already left the stack (CR 608.2b) is simply not there to change. "to this
    creature" names the resolving ability's own source, and only while it is
    still on the battlefield - gone, it is no longer "this creature" to move a
    target onto, and CR 115.7a leaves the original target unchanged.
    """
    match = _CHANGE_TARGET_RE.fullmatch(clause.strip())
    if match is None:
        return None
    scope = _RETARGET_SCOPES[match.group("scope").lower()]
    optional = match.group("may") is not None
    to_self = match.group("to") is not None
    if to_self and for_spell:
        # "this creature" on a spell names nothing on the battlefield.
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targeted = game.resolve_targets(stack_object)
        if not targeted:
            return
        subject = targeted[0]
        if not isinstance(subject, (CardState, AbilityOnStack)):
            return
        destination: CardState | None = None
        if to_self:
            destination = stack_object.source(game)  # type: ignore[union-attr]
            if destination is None or destination.zone is not Zone.BATTLEFIELD:
                return
        game.change_targets(
            subject,
            game.controller_of(stack_object).username,
            scope=scope,
            to=destination,
            optional=optional,
            source_name=stack_object.name if for_spell else stack_object.source_name,  # type: ignore[union-attr]
            source_id=source_id_of(stack_object),
        )

    return effect


#: "Create a token that's a copy of a card exiled with this Saga, except it
#: isn't legendary and is a Mutant in addition to its other types." (The
#: Cloning of Shredder's chapters II and III); "Create a token that's a copy
#: of a card exiled with this artifact. It gains haste. Exile it at the
#: beginning of the next end step." (Mimic Vat). CR 607.2a: "a card exiled
#: with this `<object>`" is the pile this object's own linked exiling ability
#: made (`Game.cards_exiled_with`, this incarnation only - CR 400.7). The
#: optional trailing sentences are about the token just made (CR 608.2c).
_COPY_OF_CARD_EXILED_WITH_SELF_RE = re.compile(
    r"^create a token that['’]?s a copy of a card exiled with (?:this [a-z]+|it)"
    r"(?:, except (?P<except>[^.]+?))?\.?"
    r"(?P<haste>\s*it gains haste\.)?"
    r"(?P<end_step>\s*(?:exile|sacrifice) it at the beginning of the next end step\.)?\s*$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s14")
def _parse_copy_of_card_exiled_with_self_clause(text: str) -> AbilityEffect | None:
    """`_COPY_OF_CARD_EXILED_WITH_SELF_RE`'s shape, or `None`.

    With more than one card in the pile the controller chooses which one
    (CR 608.2d); with none, nothing happens. The copy's exceptions are
    CR 707.9b's (`_read_copy_exception_list`, then `_read_token_copy_except`).
    "It gains haste." has no duration (CR 611.2a) and is a layer 6 grant on
    the token (CR 613.1f); the end-step exile is CR 603.7's delayed trigger
    (`anaphoric_delayed_trigger`)."""
    match = _COPY_OF_CARD_EXILED_WITH_SELF_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    not_legendary = False
    listed = _read_copy_exception_list(match.group("except"))
    if listed is not None:
        added, power, toughness, added_type = (
            listed.added_abilities,
            listed.power,
            listed.toughness,
            listed.added_creature_type,
        )
        not_legendary = listed.not_legendary
    else:
        exception = _read_token_copy_except(match.group("except"))
        if exception is None:
            return None
        added, power, toughness, added_type = exception
    end_step = match.group("end_step")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if ability.source_id is None:
            return
        pile = [
            card
            for card in game.cards_exiled_with(ability.source_id, ability.source_stamp)
            if card.zone is Zone.EXILE
        ]
        if not pile:
            return
        controller = game.controller_of(ability)
        chosen = pile[0]
        if len(pile) > 1:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="choose a card exiled with it to copy",
                    source=ability.source_name,
                    cards=tuple(card.id for card in pile),
                    count=1,
                    source_id=source_id_of(ability),
                )
            )
            assert isinstance(answer, tuple)
            chosen = next(card for card in pile if card.id == answer[0])
        created = token_copy_of(
            game,
            chosen,
            controller.username,
            added_abilities=added,
            power=power,
            toughness=toughness,
            added_creature_type=added_type,
            not_legendary=not_legendary,
        )
        store = continuous_effects(game)
        for token in created:
            if token.zone is not Zone.BATTLEFIELD:
                continue
            if match.group("haste"):
                store.add(
                    ContinuousEffect(
                        description=f"{ability.source_name}: {token.name} gains haste",
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        selector=only_this_incarnation(token, token.zone_change_stamp),
                        modification=grant_ability("Haste"),
                    ),
                    game,
                )
            if end_step:
                trigger = anaphoric_delayed_trigger(
                    end_step.strip(),
                    subject=token,
                    controller=controller.username,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    game=game,
                )
                if trigger is not None:
                    game.create_delayed_trigger(trigger)

    return effect


from ._common import (  # noqa: E402
    _TOKEN_COLOR_WORDS,
    _TOKEN_KEYWORDS,
    GroupPredicate,
    _permanent_id_and_name,
    _targets_understood,
)
from .amounts import count_expression  # noqa: E402
from .continuous import continuous_effects  # noqa: E402
from .damage import _parse_damage_group_phrase  # noqa: E402
from .text import _strip_non_effect_preamble  # noqa: E402
from .tokens import _read_token_copy_except  # noqa: E402

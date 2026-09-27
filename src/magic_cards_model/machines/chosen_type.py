"""CR 205.3m creature types chosen at runtime, and the consumers that read
the choice back - not CR 614.12a's storage itself (`CardState.choice`,
`ChoiceKind.CREATURE_TYPE`, `machines/replacement.py`'s "as [this] enters,
choose a creature type") or the fixed-subject anthem over it
(`machines/layers.py`'s `_chosen_type_anthem_builder`), both of which already
existed before this module and are only imported here, never duplicated.

What is new:

- **The restricted enumerated choice.** "As this artifact/land enters,
  choose Elemental, Elf, Faerie, Giant, Goblin, Kithkin, Merfolk, or
  Treefolk." (Dawn-Blessed Pennant, Eclipsed Realms) is still CR 614.12a's
  ordinary "choose a creature type" - CR 601.2b/614.12a draw no distinction
  between a choice offered openly and one offered from a printed list - but
  the eight names are the *only* legal answers this printed sentence allows,
  narrower than CR 205.3m's full list `machines/replacement.py`'s own bare
  "choose a creature type" already offers. `RESTRICTED_TRIBAL_TYPES` and
  `matches_restricted_creature_type_choice` are what `machines/replacement.py`
  reads to narrow the offered `Decision.options` and refuse an answer outside
  the printed eight.
- **CR 702.73a's shared-type comparison.** `shares_creature_type` - Winnowing's
  own "don't share a creature type with the chosen creature" - reading a
  changeling (CR 702.73a: "This object is every creature type") as sharing
  every type any other creature has, the same way any other creature-type
  check in this engine already must.
- **Three consumers of an already-recorded chosen type** that needed their own
  reader because none of `machines/layers.py`'s, `machines/cost.py`'s, or
  `machines/effects.py`'s existing dispatch tables had a matching shape yet:
  Oko, Lorwyn Liege's own fresh-choice emblem (`parse_choose_creature_type_
  then_emblem_clause`), Selfless Safewright's temporary other-permanents grant
  (`parse_choose_type_hexproof_indestructible_clause`), and Gathering Stone's
  combined enters-and-upkeep look-reveal-or-graveyard trigger
  (`parse_gathering_stone_look_clause`).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..data.creature_types import creature_types
from ..models.card import Type
from ..models.card_state import CardState, Choice, ChoiceKind
from ..models.zone import Zone
from ..phrases import with_indefinite_article
from .decisions import Decision, DecisionKind, source_id_of
from .layers import (
    ContinuousEffect,
    Duration,
    Layer,
    chosen_creature_type_of,
    grant_ability,
    permanents_controlled_by_with_subtype,
)

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect
    from .triggers import AbilityOnStack

#: CR 205.3m creature types, exactly as Dawn-Blessed Pennant and Eclipsed
#: Realms print the printed list - the Lorwyn tribal cycle's own eight, in
#: their printed order. A card-specific restriction, not a rules-defined
#: subset: CR 205.3m lists hundreds of creature types, and nothing about the
#: rule itself narrows to these eight - the printed sentence does that, the
#: same way any other "choose [enumerated list]" would.
RESTRICTED_TRIBAL_TYPES: tuple[str, ...] = (
    "Elemental",
    "Elf",
    "Faerie",
    "Giant",
    "Goblin",
    "Kithkin",
    "Merfolk",
    "Treefolk",
)

#: "choose Elemental, Elf, Faerie, Giant, Goblin, Kithkin, Merfolk, or
#: Treefolk" - the enumerated form of CR 614.12a's "choose a creature type",
#: matched on the literal list rather than a generic "choose one of ..."
#: reader so a differently ordered or worded enumeration (none printed yet)
#: is left unread rather than silently accepted as this one.
_CHOOSE_ENUMERATED_TRIBAL_TYPES_RE = re.compile(
    r"^choose elemental, elf, faerie, giant, goblin, kithkin, merfolk, or treefolk\.?$",
    re.IGNORECASE,
)


def matches_restricted_creature_type_choice(replacement_text: str) -> bool:
    """Whether `replacement_text` is `_CHOOSE_ENUMERATED_TRIBAL_TYPES_RE`'s
    shape - `machines/replacement.py`'s `_classify_choice` reads this
    alongside its own bare "choose a creature type" to decide `ChoiceKind.
    CREATURE_TYPE`, and `_choose_a_quality` reads it again to narrow the
    `Decision.options` it offers to `RESTRICTED_TRIBAL_TYPES` instead of
    every CR 205.3m type."""
    return bool(_CHOOSE_ENUMERATED_TRIBAL_TYPES_RE.match(replacement_text.strip()))


def shares_creature_type(game: Game, first: CardState, second: CardState) -> bool:
    """CR 702.73a: "'Changeling' means 'This object is every creature
    type.'" - so two creatures "share a creature type" (Winnowing) whenever
    their subtype sets intersect, treating either side's changeling as
    matching anything the other side has.

    Read off `game.characteristics_of` when the object is on the battlefield
    (CR 613.5's computed board - a creature that gained changeling, or a
    subtype, from a continuous effect still shares it), off `CardState.
    subtypes` otherwise (its own printed/copied subtypes, changeling's own
    CR 604.3 characteristic-defining reading already included there off the
    battlefield too).
    """

    def subtypes_of(card: CardState) -> set[str]:
        if card.zone is Zone.BATTLEFIELD:
            try:
                return {subtype.lower() for subtype in game.characteristics_of(card).subtypes}
            except (AttributeError, KeyError):
                pass
        return {subtype.lower() for subtype in card.subtypes}

    return bool(subtypes_of(first) & subtypes_of(second))


def ask_creature_type(
    game: Game, controller_username: str, source_name: str, source_id: str | None
) -> str:
    """CR 614.12a's own open "choose a creature type" question, asked fresh
    at an ability's resolution rather than as this object enters - Oko's
    "-6: Choose a creature type. ..." and Selfless Safewright's "When this
    creature enters, choose a creature type. ..." both choose *anew* each
    time the ability resolves, never reusing whatever `CardState.choice`
    (if anything) a CR 614.12a replacement effect might separately hold."""
    value = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_A_QUALITY,
            player=controller_username,
            prompt=f"choose {with_indefinite_article('creature type')}",
            source=source_name,
            source_id=source_id,
            options=creature_types(),
            quality=ChoiceKind.CREATURE_TYPE.value,
        )
    )
    assert isinstance(value, str)
    return value


#: Oko, Lorwyn Liege's own "-6: Choose a creature type. You get an emblem
#: with '...'." - CR 607.2d's "choose a [value]" ability linked (in the same
#: paragraph, CR 607.1c) to the emblem's own text that reads "the chosen
#: type" (`_CHOSEN_TYPE_ANTHEM_RE`, `machines/layers.py`). The loyalty cost
#: itself ("-6:") is already stripped by `machines/abilities.py` before this
#: text is ever seen, the same way every other activated-ability reader in
#: this pool receives its text.
_CHOOSE_TYPE_THEN_EMBLEM_RE = re.compile(
    r'^choose a creature type\.\s*(?:you|they) gets? an emblem with ["“](?P<text>[^"”]+)["”]\.?$',
    re.IGNORECASE | re.DOTALL,
)


def parse_choose_creature_type_then_emblem_clause(text: str) -> AbilityEffect | None:
    """`_CHOOSE_TYPE_THEN_EMBLEM_RE`'s shape, or `None`.

    The emblem (CR 114.2, `Game.create_emblem`) is a fresh command-zone
    object with no `CardState.choice` of its own until this sets one - the
    same `ChoiceKind.CREATURE_TYPE` a permanent's own CR 614.12a entry choice
    would carry, read back by the identical `chosen_creature_type_of`/
    `_chosen_type_anthem_builder` (`machines/layers.py`) that already serves
    Chronicle of Victory's static, since CR 114.4 makes an emblem's own
    abilities function in the command zone exactly like a permanent's
    function on the battlefield."""
    match = _CHOOSE_TYPE_THEN_EMBLEM_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    quoted = match.group("text")

    def effect(game: Game, ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        chosen = ask_creature_type(
            game, controller.username, ability.source_name, source_id_of(ability)
        )
        emblem = game.create_emblem(controller.username, quoted, ability.source_name)
        emblem.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value=chosen)

    return effect


#: Selfless Safewright's own ETB: "choose a creature type. Other permanents
#: you control of that type gain hexproof and indestructible until end of
#: turn." The trigger condition itself ("When this creature enters, ") is
#: already stripped before this text is seen, the same convention every
#: other triggered-ability reader in this pool relies on.
_CHOOSE_TYPE_HEXPROOF_INDESTRUCTIBLE_RE = re.compile(
    r"^choose a creature type\. other permanents you control of that type "
    r"gain hexproof and indestructible until end of turn\.?$",
    re.IGNORECASE,
)


def parse_choose_type_hexproof_indestructible_clause(text: str) -> AbilityEffect | None:
    """`_CHOOSE_TYPE_HEXPROOF_INDESTRUCTIBLE_RE`'s shape, or `None`.

    A fresh choice at resolution (CR 608.2b), not CR 614.12a's "as [this]
    enters" - the source is already on the battlefield by the time this
    triggered ability resolves, so nothing here touches `CardState.choice`
    at all; the grant is a plain layer 6 (CR 613.1f) continuous effect over
    `permanents_controlled_by_with_subtype`'s live selector (CR 613.5),
    excluding the source itself ("**other** permanents") and lasting until
    the coming cleanup step (CR 514.2)."""
    match = _CHOOSE_TYPE_HEXPROOF_INDESTRUCTIBLE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source = ability.source(game)
        chosen = ask_creature_type(
            game, controller.username, ability.source_name, source_id_of(ability)
        )
        selector = permanents_controlled_by_with_subtype(
            controller.username, [chosen], other_than=source.id if source is not None else None
        )
        store = game.continuous_effects
        timestamp = store.tick()
        for keyword in ("hexproof", "indestructible"):
            store.add(
                ContinuousEffect(
                    description=(
                        f"{ability.source_name}: other permanents you control of the chosen "
                        f"type ({chosen}) gain {keyword}"
                    ),
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    source_id=source.id if source is not None else None,
                    selector=selector,
                    modification=grant_ability(keyword),
                )
            )

    return effect


#: Gathering Stone's own combined trigger: "When this artifact enters and at
#: the beginning of your upkeep, look at the top card of your library. If
#: it's a card of the chosen type, you may reveal it and put it into your
#: hand. If you don't put the card into your hand, you may put it into your
#: graveyard." `machines/triggers._expand_enters_and_upkeep` has already
#: split the *condition* into two triggered abilities (CR 603.1b); both
#: share this one effect text, read once here.
_LOOK_REVEAL_HAND_OR_GRAVEYARD_RE = re.compile(
    r"^look at the top card of your library\. if it'?s a card of the chosen type, "
    r"you may reveal it and put it into your hand\. if you don'?t put (?:the|that) card "
    r"into your hand, you may put it into your graveyard\.?$",
    re.IGNORECASE,
)


def parse_gathering_stone_look_clause(text: str) -> AbilityEffect | None:
    """`_LOOK_REVEAL_HAND_OR_GRAVEYARD_RE`'s shape, or `None`.

    CR 701.5a/701.5c's "look" is private - nothing is revealed by looking
    alone, so an empty library or a non-matching top card ends the ability
    having shown nothing to anyone. The second "you may" (CR 608.2d) is
    offered whenever the card was **not** put into the hand, whether that is
    because it did not match `chosen_creature_type_of` at all or because the
    controller declined the first "you may" - the printed condition
    ("if you don't put the card into your hand") is the same either way, so
    this reads it as one flag rather than re-deriving why."""
    match = _LOOK_REVEAL_HAND_OR_GRAVEYARD_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        if not controller.library:
            return
        top = controller.library[0]
        source = ability.source(game)
        source_id = source_id_of(ability)
        chosen = chosen_creature_type_of(source) if source is not None else None
        matches = (
            chosen is not None
            and Type.CREATURE in top.types
            and chosen in (subtype.lower() for subtype in top.subtypes)
        )
        put_into_hand = False
        if matches and game.may(
            controller,
            f"reveal {top.name} and put it into your hand",
            source=ability.source_name,
            source_id=source_id,
            cards=(top,),
        ):
            game.reveal(top, source=ability.source_name)
            controller.add(top, Zone.HAND)
            put_into_hand = True
        if (
            not put_into_hand
            and top.zone is Zone.LIBRARY
            and game.may(
                controller,
                f"put {top.name} into your graveyard",
                source=ability.source_name,
                source_id=source_id,
                cards=(top,),
            )
        ):
            game.put_into_graveyard(top)

    return effect

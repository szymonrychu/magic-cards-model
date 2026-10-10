import re
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from ...ids import new_id
from ...models.card import Card, Layout, Supertype
from ...models.card_state import CardState
from ...models.zone import Zone
from ...numbers import COUNT, parse_count
from ...snapshot import scan_pin
from ..abilities import (
    Ability,
    AbilityKind,
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    intrinsic_land_ability,
    leveler_lines,
    parse_abilities,
    parse_granted_ability_lines,
    self_reference_names,
    self_reference_pattern,
)
from ..designations import designation_holds, split_as_long_as

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ...models.game import Game

    # `.cost` imports names from this module and `.keywords` imports
    # `AbilityOnStack` itself, so neither can be imported for real up here -
    # `keyword_activation`/`unless_payment` below carry these as string
    # annotations, and `keywords.py`'s own `model_rebuild()` call, run once
    # both classes exist, is what resolves them for real.
from .events import AbilityOnStack, ExtraTriggerEvent, GameEvent


def _unread_trigger_events(condition: str) -> frozenset[TriggerEvent | ExtraTriggerEvent]:
    """The events a condition `machines/abilities._trigger_event` left unread
    watches, or an empty set when this module cannot read it either.

    CR 603.1b: "A triggered ability may have more than one trigger condition" -
    Ketramose, the New Dawn's single printed condition names two origins for
    the same exile and so watches two events, which is why this returns a set
    rather than one event.
    """
    lowered = condition.lower().strip()
    if _COUNTERS_PUT_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    if _LOYALTY_COUNTERS_PUT_ON_PLANESWALKER_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    if _COUNTERS_PUT_ON_DESCRIPTION_CONDITION.match(condition.strip()):
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    if _YOU_PUT_A_COUNTER_ON_QUALITY_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    if _OPPONENTS_ARE_ATTACKED_CONDITION.match(lowered):
        return frozenset({TriggerEvent.ATTACKS})
    if _PLAYER_COUNTERS_PUT_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.PLAYER_COUNTERS_PUT})
    if _LEAVES_GRAVEYARD_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.LEAVES_GRAVEYARD})
    if _PUT_INTO_LIBRARY_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.PUT_INTO_LIBRARY})
    if _EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION.match(lowered):
        return frozenset(
            {
                ExtraTriggerEvent.EXILED_FROM_GRAVEYARD,
                TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
            }
        )
    if _NTH_DRAW_CONDITION.match(lowered):
        return frozenset({TriggerEvent.DRAWS_A_CARD})
    if _NTH_COUNTER_PUT_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    if _ONE_OR_MORE_BECOME_TAPPED_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.PERMANENTS_TAPPED})
    if _ONE_OR_MORE_CARDS_INTO_YOUR_GRAVEYARD_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.PUT_INTO_GRAVEYARD})
    if _LAND_ADDED_CHOSEN_MANA_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.MANA_ADDED})
    if _LAST_TIME_COUNTER_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED})
    if _LAST_COUNTER_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.LAST_COUNTER_REMOVED})
    if _REVEALED_THIS_WAY_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.REVEALED_FOR_MIRACLE})
    if _REVEALED_FIRST_DRAW_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.REVEALED_FIRST_DRAW})
    if _UNTAPPED_DURING_UNTAP_STEP_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.UNTAPPED_DURING_UNTAP_STEP})
    if _ONE_OR_MORE_DEAL_COMBAT_DAMAGE_RE.fullmatch(lowered):
        return frozenset({ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS})
    if _PLAY_A_CARD_EXILED_WITH_CONDITION.match(lowered):
        return frozenset({TriggerEvent.CAST_SPELL, ExtraTriggerEvent.PLAYS_LAND})
    if _PLAY_A_LAND_OR_CAST_CONDITION.match(lowered):
        return frozenset({TriggerEvent.CAST_SPELL, ExtraTriggerEvent.PLAYS_LAND})
    if _LOSES_LIFE_CONDITION.match(lowered):
        return frozenset({TriggerEvent.LOSES_LIFE})
    if _returned_subject(lowered) is not None:
        return frozenset({TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND})
    if _CLASS_BECOMES_LEVEL_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.CLASS_BECOMES_LEVEL})
    if _CYCLE_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.CYCLED})
    if _ABILITY_ACTIVATED_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.ABILITY_ACTIVATED})
    if _RING_TEMPTS_YOU_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.RING_TEMPTS_YOU})
    if _CRIME_COMMITTED_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.CRIME_COMMITTED})
    if _SEARCHES_LIBRARY_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.SEARCHES_LIBRARY})
    if _ROLLS_DICE_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.ROLLS_DICE})
    if _DOOR_UNLOCKED_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.DOOR_UNLOCKED})
    if _SOLVE_A_CASE_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.CASE_SOLVED})
    if _SELF_PUT_INTO_GRAVEYARD_FROM_ANYWHERE_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.PUT_INTO_GRAVEYARD})
    if _ENLISTS_A_CREATURE_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.ENLISTS})
    bending = _bending_events_named(lowered)
    if bending:
        return bending
    day_night = _day_night_events_named(lowered)
    if day_night:
        return day_night
    from ..counter_effects import counter_trigger_events

    return counter_trigger_events(condition)


def triggers_only_off_the_stack(ability: TriggeredAbility) -> bool:
    """Whether this triggered ability's own condition can only occur while
    its card is in a hand on its way somewhere else - "When you discard this
    card" (CR 701.9a) or "When you cycle this card" (CR 702.29c).

    CR 113.6k: "A trigger condition that can't trigger from the battlefield
    functions in all zones it can trigger from." Neither can occur while the
    card is a spell on the stack either, so on an instant or sorcery such a
    paragraph is a separate ability printed on the card, never part of the
    spell's own resolution (CR 113.6: an instant's or sorcery's abilities
    usually function only on the stack - this is one of the exceptions).
    """
    condition = ability.condition.lower().strip()
    if ability.event is TriggerEvent.DISCARDS_A_CARD and condition.endswith("this card"):
        return True
    cycled = _CYCLE_CONDITION.match(condition)
    return cycled is not None and cycled.group("what") == "this card"


#: CR 603.10a's look-back events: the source is deliberately still asked for
#: these even though it has already left the battlefield by the time the event
#: is worked out - `Game.emit` widens `sources` for exactly this reason.
#:
#: `LEAVES_THE_BATTLEFIELD` belongs here on CR 603.10a's own say-so - "Some
#: zone-change triggers look back in time. These are leaves-the-battlefield
#: abilities, abilities that trigger when a player sacrifices a permanent,
#: abilities that trigger when a card leaves a graveyard, and abilities that
#: trigger when an object that all players can see is put into a hand or
#: library" - not merely by analogy with `DIES`. Its absence was a real
#: defect: `Game.put_into_graveyard` happens to emit `LEAVES_THE_BATTLEFIELD`
#: *before* moving the card, so `source.zone` still read BATTLEFIELD when
#: this was checked and the plain-battlefield default below passed by
#: accident. `Game.exile_permanent`, `Game.return_to_hand`, `Game.
#: put_cards_into_library`, and `Game.ante` all emit it *after* the move, so
#: `source.zone` already read EXILE/HAND/LIBRARY/ANTE and the same default
#: refused every one of them - a leaves-the-battlefield ability fired for a
#: destroyed or sacrificed permanent and silently not for one exiled,
#: bounced, tucked, or anted. Adding it here fixes every route at once,
#: regardless of which side of its own move each one happens to emit on.
_LOOK_BACK_EVENTS = (
    TriggerEvent.DIES,
    TriggerEvent.IS_SACRIFICED,
    TriggerEvent.SPELL_IS_COUNTERED,
    TriggerEvent.LEAVES_THE_BATTLEFIELD,
    TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
)


def zones_ability_functions_in(
    ability: TriggeredAbility, source: CardState, game: "Game | None" = None
) -> frozenset[Zone]:
    """Which zone(s) this printed ability functions from (CR 113.6).

    CR 113.6: "Abilities of an instant or sorcery spell usually function only
    while that object is on the stack. Abilities of all other objects usually
    function only while that object is on the battlefield. The exce[ptions are
    listed below]" - the tail truncated for this session's `knowledge_search`
    too, so the exceptions list itself was never read directly; only the
    individually-served subrules below were. The conservative default kept
    here is the rule's own opening sentence: a permanent's ability functions
    on the battlefield unless one of the confirmed exceptions applies.

    Deliberately does **not** consult `_self_referential`/`mine` - CR 113.6k is
    a narrower question ("can this specific trigger condition occur anywhere
    other than the battlefield") than self-reference is ("does the condition
    name this object"). Ugin, Eye of the Storms prints two self-referential
    ("mine") cast triggers - "When you cast this spell" and "Whenever you cast
    a colorless spell" - and only the first can happen while Ugin is a spell
    rather than a permanent; the second names no spell in particular and keeps
    functioning from the battlefield. Gating on `mine` would have granted the
    second one stack rights it does not have.
    """
    lowered = ability.condition.lower()

    if source.card.layout is Layout.EMBLEM:
        # CR 114.4: "Abilities of emblems function in the command zone."
        return frozenset({Zone.COMMAND})

    # CR 113.6b: "An ability that states which zones it functions in functions
    # only from those zones." An intervening if (CR 603.4) that says where its
    # own source is - "if this card is in your graveyard", "if Firemane Angel
    # is in your graveyard or on the battlefield" - is that statement.
    if ability.intervening_if is not None:
        from ..conditions.player import zones_the_source_names

        named = zones_the_source_names(ability.intervening_if, source)
        if named is not None:
            return named
    # The same statement made by a "This ability triggers only if <source> is
    # on the battlefield or if <source> is in your graveyard and ..." restriction
    # (Quakebringer): every zone its alternatives name for the source.
    if ability.triggers_only_if is not None:
        from ..conditions.player import zones_the_source_names_any

        named = zones_the_source_names_any(ability.triggers_only_if, source)
        if named is not None:
            return named

    # CR 113.6b again, off the trigger condition. A cast trigger's "from your graveyard" is not
    # that: "Whenever you cast a Dragon creature spell from your graveyard"
    # (Rivaz of the Claw, Secrets of the Dead) says where the *spell* came
    # from - `_origin_zone_matches` reads it off the cast - and names no zone
    # for its own source, which works from the battlefield like any other.
    cast_origin = (
        ability.event is TriggerEvent.CAST_SPELL
        and _required_cast_origin_zone(lowered) is Zone.GRAVEYARD
    )
    # Likewise "When this creature enters from your graveyard" (Phyrexian
    # Dragon Engine) says where the *entering permanent* came from; an enters
    # ability triggers from the battlefield (CR 603.6a).
    enters_origin = (
        ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD
        and entering_origin_zone(lowered) is not None
    )
    if "in your graveyard" in lowered or (
        "from your graveyard" in lowered and not cast_origin and not enters_origin
    ):
        return frozenset({Zone.GRAVEYARD})
    if "opening hand" in lowered:
        return frozenset({Zone.HAND})

    # CR 113.6k: "A trigger condition that can't trigger from the battlefield
    # functions in all zones it can trigger from." A cast-trigger that names
    # "this spell" can only occur while the object is a spell on the stack -
    # once it resolves and becomes a permanent it is never "cast" again - so it
    # functions there instead of the battlefield default. Gated on the parsed
    # event as well as the phrase: a CR 603.1b compound such as Cityscape
    # Leveler's "When you cast this spell and whenever this creature attacks"
    # is one `TriggeredAbility` per condition (`machines/abilities.
    # _split_compound_condition`), and CR 113.6k's own "Other trigger
    # conditions of the same triggered ability may function in different
    # zones" keeps the attack half on the battlefield.
    if ability.event is TriggerEvent.CAST_SPELL and "this spell" in lowered:
        return frozenset({Zone.STACK})

    # CR 113.6k again, the discard twin of the cast-trigger branch just
    # above: "discard this card" (CR 701.9a) can never occur on the
    # battlefield either - a permanent is never discarded, only a card in a
    # hand is - so Titanbones, Towering Heart's own "When you discard this
    # card, ..." functions wherever the discard actually lands it.
    # `Game.discard_cards` moves the card before it ever calls `Game.emit`,
    # so by the time this is asked the card already sits in the graveyard
    # (CR 701.9a's ordinary destination) or, for a madness-replaced discard,
    # exile (CR 702.35a) - both are offered rather than guessing which.
    if ability.event is TriggerEvent.DISCARDS_A_CARD and "this card" in lowered:
        return frozenset({Zone.GRAVEYARD, Zone.EXILE})

    # CR 702.29c, the cycling twin of the discard branch just above: "These
    # abilities trigger from whatever zone the card winds up in after it's
    # cycled" - never the hand it was cycled from, never the battlefield.
    cycled = _CYCLE_CONDITION.match(lowered.strip())
    if cycled is not None and cycled.group("what") == "this card":
        return frozenset({Zone.GRAVEYARD, Zone.EXILE})

    # CR 702.35a: madness watches its own exile, which can only be observed
    # while the card is, in fact, being exiled that way.
    if ability.event is TriggerEvent.EXILED:
        return frozenset({Zone.EXILE})

    # CR 702.62a says it in as many words: "Suspend is a keyword that
    # represents three abilities. The first is a static ability that functions
    # while the card with suspend is in a player's hand. The second and third
    # are triggered abilities that function in the exile zone." Read off
    # `TriggeredAbility.keyword` rather than off the condition text, because
    # neither of the two is printed as a line at all - `machines/keywords.
    # _suspend_abilities` writes both out from the rule, and the keyword is
    # what says which rule they came from. Both are covered by the one branch:
    # CR 702.62a scopes the sentence to the pair, not to either one.
    if ability.keyword is not None and ability.keyword.lower() == "suspend":
        return frozenset({Zone.EXILE})

    # CR 702.94a: miracle's static ability reveals the card "from your hand
    # as you draw it", and its linked trigger is about that card in that
    # hand - the only zone the reveal can happen in.
    if ability.keyword is not None and ability.keyword.lower() == "miracle":
        return frozenset({Zone.HAND})

    # CR 603.10a: dies, is-sacrificed, countered, and leaves-the-battlefield
    # triggers look back at the object as it existed immediately beforehand,
    # so they function from the battlefield the source just left as well as
    # wherever it ended up - `source.zone` already reflects the post-event
    # location for a route that emits after the move, and still reads
    # BATTLEFIELD for one that emits before it (`Game.put_into_graveyard`);
    # either way the object just left is exactly what `Game.emit` widens
    # `sources` for.
    if ability.event in _LOOK_BACK_EVENTS:
        # CR 603.10a looks back at the event the source was part of - it and
        # whatever left in the same batch (its own example: a "whenever a
        # creature dies" artifact destroyed together with two creatures
        # triggers twice). A source that left in an earlier batch, or was
        # never on the battlefield, is only a card in that zone and hears
        # nothing (CR 113.6). A countered spell never left the battlefield.
        if (
            game is None
            or source.zone is Zone.BATTLEFIELD
            or ability.event is TriggerEvent.SPELL_IS_COUNTERED
            or source.left_battlefield_in(game._departure_epoch)
        ):
            return frozenset({Zone.BATTLEFIELD, source.zone})
        return frozenset({Zone.BATTLEFIELD})
    if ability.event is None and _returned_subject(lowered) is not None:
        # CR 603.10a's look-back for a returned-to-hand condition the parser
        # left unread: the source returned by the same event is in a hand
        # already. `_returned_to_hand_matches` hears it only then.
        return frozenset({Zone.BATTLEFIELD, Zone.HAND})

    if (
        ability.event is None
        and _SELF_PUT_INTO_GRAVEYARD_FROM_ANYWHERE_CONDITION.match(lowered) is not None
    ):
        # CR 113.6k: "A trigger condition that can't trigger from the
        # battlefield functions in all zones it can trigger from" - "is put
        # into a graveyard from anywhere" (Emrakul, the Aeons Torn; Purity)
        # can occur from whichever zone the source was in before the move -
        # the battlefield (a death), the library (milled), the hand
        # (discarded), exile - and is asked again from the graveyard it
        # just arrived in either way, the identical widening `_LOOK_BACK_
        # EVENTS` gives every other zone-change look-back, generalised over
        # every origin the way "anywhere" prints.
        return frozenset(
            {Zone.BATTLEFIELD, Zone.GRAVEYARD, Zone.LIBRARY, Zone.HAND, Zone.EXILE, Zone.STACK}
        )

    # CR 113.6m: "An ability whose cost or effect specifies that it moves the
    # object it's on out of a particular zone functions only in that zone,
    # unless its trigger condition or a previous part of its cost or effect
    # specifies that it moves the object it's on into that zone."
    #
    # Arclight Phoenix's "At the beginning of combat on your turn, if you've
    # cast three or more instant and sorcery spells this turn, return this
    # card from your graveyard to the battlefield" is exactly that: the
    # *effect*, not the condition, names the zone. Checked after the branches
    # above so the rule's own "unless" is honoured - a dies trigger whose
    # effect returns the card from the graveyard puts it *into* that zone as
    # its own trigger condition, and `_LOOK_BACK_EVENTS` has already answered
    # for those. `machines/abilities._activated_ability_zone` applies the
    # identical rule to an activated ability's effect text, which is why
    # Cauldron Familiar's `Sacrifice a Food:` ability already worked from a
    # graveyard and this triggered one did not.
    effect = (ability.effect or "").lower()
    if "from your graveyard" in effect and "this card" in effect:
        return frozenset({Zone.GRAVEYARD})

    return frozenset({Zone.BATTLEFIELD})


# --------------------------------------------------------------------------
# Turning an event into abilities waiting to go on the stack
# --------------------------------------------------------------------------


def triggered_abilities_of(card: Card) -> list[TriggeredAbility]:
    """Every triggered ability a card has (CR 113.3c), printed or abbreviated.

    Two sources, and the second is why ward and prowess fire in a real game
    rather than only when a scenario drives them:

    - the lines that begin When, Whenever or At, read by
      `machines/abilities.parse_abilities`;
    - the CR 702 keywords that *are* triggered abilities without being printed
      as one - ward (CR 702.21a), prowess (CR 702.108a), cascade (CR 702.85a),
      persist (CR 702.79a) and mobilize (CR 702.181a). CR 702.1 calls a keyword
      "shorthand for one or more abilities", and
      `machines/keywords.keyword_triggered_abilities` writes each rule's own
      expansion out.

    Once they are in this list there is nothing further to special-case:
    `triggers_for`, `Game.emit` and CR 603.3's stack ordering treat an
    abbreviated trigger exactly like a spelled-out one.
    """
    # Imported here rather than at the top because `machines/keywords.py`
    # imports this module for `AbilityOnStack`; the cycle is real and only
    # resolvable at call time.
    from ..keywords import keyword_triggered_abilities
    from ..sieges import siege_triggered_abilities

    printed = [
        ability
        for ability in parse_abilities(card)
        if isinstance(ability, TriggeredAbility)
        # CR 721.2a: a station striation's trigger is granted by the symbol's
        # static ability (`layers._station_symbol_effects`) and is found
        # through `added_ability_lines` while the counters reach N - never as
        # a printed ability the permanent always has. CR 711.2a/b's level
        # striation the same way (`layers._level_symbol_effects`).
        and ability.station_threshold is None
        and ability.level_band is None
        # An ability the parser could not file under a `TriggerEvent` is kept
        # when this module can read its condition anyway (`_unread_trigger_
        # events`) - it is matched from the printed condition rather than from
        # `event`, which stays None. Everything else the parser left unread is
        # dropped exactly as before: an ability nothing can match would only
        # ever sit here waiting to fire on the wrong event.
        and (ability.event is not None or _unread_trigger_events(ability.condition))
    ]
    expanded: list[TriggeredAbility] = []
    for ability in printed:
        for split in _expand_attacks_or_blocks(
            ability, card.name, legendary=Supertype.LEGENDARY in card.supertypes
        ):
            for enters_split in _expand_enters_or_attacks(
                split, card.name, legendary=Supertype.LEGENDARY in card.supertypes
            ):
                for leaves_split in _expand_enters_or_leaves(enters_split):
                    for dies_split in _expand_enters_or_dies(
                        leaves_split,
                        card.name,
                        legendary=Supertype.LEGENDARY in card.supertypes,
                    ):
                        for damage_split in _expand_enters_or_deals_combat_damage(
                            dies_split,
                            card.name,
                            legendary=Supertype.LEGENDARY in card.supertypes,
                        ):
                            for upkeep_split in _expand_enters_and_upkeep(
                                damage_split,
                                card.name,
                                legendary=Supertype.LEGENDARY in card.supertypes,
                            ):
                                for tapped_split in _expand_enters_or_becomes_tapped(
                                    upkeep_split,
                                    card.name,
                                    legendary=Supertype.LEGENDARY in card.supertypes,
                                ):
                                    for transforms_split in _expand_enters_or_transforms_into(
                                        tapped_split
                                    ):
                                        expanded.extend(
                                            _expand_transforms_and_first_main(transforms_split)
                                        )
    return expanded + keyword_triggered_abilities(card) + siege_triggered_abilities(card)


#: "Whenever this creature attacks or blocks, ..." - Elder Gargaroth's own
#: condition, and the shape CR 508.1/509.1 have no single `TriggerEvent` for:
#: `_trigger_event` (`machines/abilities.py`) reads the first event word it
#: recognises in the condition and stops there, so a compound "attacks or
#: blocks" condition is read as `TriggerEvent.ATTACKS` alone and the "or
#: blocks" half is silently dropped - a real game where Elder Gargaroth
#: blocks and never attacks would never see its own trigger. "this
#: `<kind>`" is read the same open way `_ENTERS_OR_LEAVES_RE` already reads
#: it, not pinned to "creature" - Smuggler's Copter's and Getaway Car's own
#: "this Vehicle attacks or blocks" is the identical compound shape on a
#: different self-reference noun (CR 700.7).
_ATTACKS_OR_BLOCKS_RE = re.compile(r"^this (?P<kind>[a-z]+) attacks or blocks$", re.IGNORECASE)

#: Bebop & Rocksteady: "Whenever Bebop & Rocksteady attack or block, ..." -
#: `_ATTACKS_OR_BLOCKS_RE`'s identical compound condition, but self-referenced
#: by a comma-joined legendary's own printed name (CR 201.5c) rather than
#: "this creature", and with the *plural* verb form ("attack or block", no
#: trailing "s") WotC's own templating gives an "&"-joined name (Raph & Leo,
#: Sibling Rivals' own "Raph & Leo attack" is the identical singular-event
#: precedent, already read by `_trigger_event`'s bare `\battacks?\b`). Tried
#: only when `_ATTACKS_OR_BLOCKS_RE` itself declines, so a genuine "this
#: creature attacks or blocks" is never re-read through the self-reference
#: path by mistake.
_SELF_ATTACKS_OR_BLOCKS_RE = re.compile(r"^attack(?:s)? or block(?:s)?$", re.IGNORECASE)

#: Doran, Besieged by Time: "Whenever a creature you control attacks or
#: blocks, ..." - `_ATTACKS_OR_BLOCKS_RE`'s identical compound-event gap
#: (`_trigger_event` stops at the first event word it recognises), but on
#: CR 508.1/509.1's *group* form rather than a self-reference: "a"/"another"
#: `<quality>` (a card type, "creature", or left bare) "you control" attacks
#: or blocks, not only the source itself. `condition_matches`'s own BLOCKS
#: branch already reads a non-self "`<quality>` you control blocks" the
#: identical way Tetsuko Umezawa, Pursuer's own "a creature an opponent
#: controls ... blocks" is read - this only has to stop `_trigger_event` from
#: ever seeing the compound and silently keeping "attacks" alone.
_GROUP_ATTACKS_OR_BLOCKS_RE = re.compile(
    r"^(?P<subject>a|another) (?P<quality>[a-z]+) you control attacks or blocks$",
    re.IGNORECASE,
)


def _expand_attacks_or_blocks(
    ability: TriggeredAbility, card_name: str | None = None, *, legendary: bool = True
) -> list[TriggeredAbility]:
    """One ability whose condition is `_ATTACKS_OR_BLOCKS_RE`'s shape becomes
    two: the same printed effect, once watching CR 508.1's attack and once
    watching CR 509.1's block, each a `TriggeredAbility` in its own right so
    `triggers_for`/`condition_matches` need no special case for a compound
    condition - this is the only place that reads "attacks or blocks" as two
    separate self-referential conditions rather than as raw text.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    condition = ability.condition.strip()
    match = _ATTACKS_OR_BLOCKS_RE.match(condition)
    kind = match.group("kind").lower() if match is not None else "creature"
    if match is None and card_name is not None:
        # CR 201.5c: "Bebop & Rocksteady attack or block" names itself - strip
        # the self-reference the same way `_expand_enters_or_attacks` already
        # does for "Eluge enters or attacks", then read what is left as the
        # plural-verb compound `_ATTACKS_OR_BLOCKS_RE` itself never matches.
        for name in self_reference_names(card_name, legendary=legendary):
            pattern = self_reference_pattern(name)
            stripped = re.sub(pattern, "", condition, count=1).strip()
            if stripped != condition and _SELF_ATTACKS_OR_BLOCKS_RE.fullmatch(stripped):
                match = True  # sentinel: matched via self-reference, not `_ATTACKS_OR_BLOCKS_RE`
                break
    if match is not None:
        return [
            ability.model_copy(
                update={"condition": f"this {kind} attacks", "event": TriggerEvent.ATTACKS}
            ),
            ability.model_copy(
                update={"condition": f"this {kind} blocks", "event": TriggerEvent.BLOCKS}
            ),
        ]
    group_match = _GROUP_ATTACKS_OR_BLOCKS_RE.fullmatch(condition)
    if group_match is not None:
        subject = group_match.group("subject")
        quality = group_match.group("quality")
        return [
            ability.model_copy(
                update={
                    "condition": f"{subject} {quality} you control attacks",
                    "event": TriggerEvent.ATTACKS,
                }
            ),
            ability.model_copy(
                update={
                    "condition": f"{subject} {quality} you control blocks",
                    "event": TriggerEvent.BLOCKS,
                }
            ),
        ]
    return [ability]


#: "Whenever this creature enters or attacks, ..." - Primeval Titan's own
#: condition, the same compound shape `_ATTACKS_OR_BLOCKS_RE` reads for
#: "attacks or blocks": `_trigger_event` (`machines/abilities.py`) reads
#: "enters?" ahead of "attacks?" in its own precedence order, so a compound
#: "enters or attacks" condition is read as `TriggerEvent.ENTERS_THE_
#: BATTLEFIELD` alone and the "or attacks" half is silently dropped - a real
#: Primeval Titan that attacks without ever having triggered on entry (cast
#: with haste, or already on the battlefield when this engine first sees it)
#: would never see its own attack trigger. "this `<kind>`", the identical
#: open read `_ATTACKS_OR_BLOCKS_RE` takes just above.
#: A pair printed as one card says it in the plural - "Whenever Krang &
#: Shredder enter or attack" - and the events are the same two.
_ENTERS_OR_ATTACKS_RE = re.compile(r"^this (?P<kind>[a-z]+) enters? or attacks?$", re.IGNORECASE)

#: "Whenever this creature enters or transforms into `<face>`, ..." - Brutal
#: Cathar's and Huntmaster of the Fells' own condition. CR 603.1b: "A
#: triggered ability may have more than one trigger condition";
#: `_trigger_event` (`machines/abilities.py`) reads "enters" first and
#: stops, so the CR 701.27e transform half was silently dropped.
_ENTERS_OR_TRANSFORMS_INTO_RE = re.compile(
    r"^this (?P<kind>[a-z]+) enters or (?P<transforms>transforms into .+)$", re.IGNORECASE
)


def _expand_enters_or_transforms_into(ability: TriggeredAbility) -> list[TriggeredAbility]:
    """One "enters or transforms into `<face>`" ability becomes two: the
    entering half (CR 603.6a) and the "transforms into" half (CR 701.27e),
    each matched by its own existing `TriggerEvent` reader. Anything else
    passes through unchanged, singleton-wrapped."""
    match = _ENTERS_OR_TRANSFORMS_INTO_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    kind = match.group("kind").lower()
    return [
        ability.model_copy(
            update={
                "condition": f"this {kind} enters",
                "event": TriggerEvent.ENTERS_THE_BATTLEFIELD,
            }
        ),
        ability.model_copy(
            update={
                "condition": f"this {kind} {match.group('transforms')}",
                "event": TriggerEvent.TRANSFORMS,
            }
        ),
    ]


#: "Whenever this creature transforms into `<face>` and at the beginning of
#: your first main phase, ..." - Ashling, Rimebound's own condition
#: (`machines/abilities._transforms_into_face_and_first_main_boundary`
#: already keeps this whole compound condition intact against the face's own
#: internal comma). CR 603.1b: one triggered ability, two trigger
#: conditions - CR 701.27e's transform and CR 505.1a's precombat main phase -
#: each its own `TriggerEvent` `_trigger_event` cannot read as a pair, since
#: it reads only the first event word and stops.
_TRANSFORMS_AND_FIRST_MAIN_RE = re.compile(
    r"^(?P<transform>this [a-z]+ transforms into .+?) and at "
    r"(?P<first_main>the beginning of your first main phase)$",
    re.IGNORECASE,
)


def _expand_transforms_and_first_main(ability: TriggeredAbility) -> list[TriggeredAbility]:
    """One "transforms into `<face>` and at the beginning of your first main
    phase" ability becomes two: CR 701.27e's transform half and CR 505.1a's
    precombat-main-phase half, each a `TriggeredAbility` in its own right -
    the same split every other `_expand_*` function in this module already
    performs for its own compound condition.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    match = _TRANSFORMS_AND_FIRST_MAIN_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    return [
        ability.model_copy(
            update={"condition": match.group("transform"), "event": TriggerEvent.TRANSFORMS}
        ),
        ability.model_copy(
            update={
                "condition": match.group("first_main"),
                "event": TriggerEvent.BEGINNING_OF_STEP,
            }
        ),
    ]


def _expand_enters_or_attacks(
    ability: TriggeredAbility, card_name: str | None = None, *, legendary: bool = True
) -> list[TriggeredAbility]:
    """One ability whose condition is `_ENTERS_OR_ATTACKS_RE`'s shape becomes
    two: the same printed effect, once watching CR 603.6a's entering event and
    once watching CR 508.3c's attack, each a `TriggeredAbility` in its own
    right - the same split `_expand_attacks_or_blocks` already performs for
    its own compound condition, reused here for a second one rather than
    writing a second splitter.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    condition = ability.condition.strip()
    match = _ENTERS_OR_ATTACKS_RE.match(condition)
    if match is None and card_name is not None:
        # CR 201.5: "Whenever Eluge enters or attacks" names itself - read as
        # CR 700.7's "this permanent", the same rewrite
        # `abilities.self_normalized_effect_text` gives an effect.
        for name in self_reference_names(card_name, legendary=legendary):
            condition = re.sub(self_reference_pattern(name), "this permanent", condition)
        match = _ENTERS_OR_ATTACKS_RE.match(condition)
    if match is None:
        return [ability]
    kind = match.group("kind").lower()
    return [
        ability.model_copy(
            update={
                "condition": f"this {kind} enters",
                "event": TriggerEvent.ENTERS_THE_BATTLEFIELD,
            }
        ),
        ability.model_copy(
            update={"condition": f"this {kind} attacks", "event": TriggerEvent.ATTACKS}
        ),
    ]


#: "When this artifact enters or leaves the battlefield, ..." -
#: Sewer-veillance Cam's own condition, the third compound shape of the same
#: family as `_ATTACKS_OR_BLOCKS_RE` and `_ENTERS_OR_ATTACKS_RE`. CR 603.1b: "A
#: triggered ability may have more than one trigger condition"; `_trigger_
#: event` (`machines/abilities.py`) reads "enters" first and stops, so the
#: departure half - CR 603.6c's leaves-the-battlefield ability, which is the
#: half a deck actually uses when the Cam is sacrificed to its own draw
#: ability - was silently dropped.
_ENTERS_OR_LEAVES_RE = re.compile(
    r"^this (?P<kind>[a-z]+) enters or leaves the battlefield$", re.IGNORECASE
)


def _expand_enters_or_leaves(ability: TriggeredAbility) -> list[TriggeredAbility]:
    """One ability whose condition is `_ENTERS_OR_LEAVES_RE`'s shape becomes
    two: CR 603.6a's enters-the-battlefield ability and CR 603.6c's
    leaves-the-battlefield one, each self-referential and each a
    `TriggeredAbility` in its own right - the same split
    `_expand_attacks_or_blocks` and `_expand_enters_or_attacks` already
    perform for their own compound conditions.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    match = _ENTERS_OR_LEAVES_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    kind = match.group("kind").lower()
    return [
        ability.model_copy(
            update={
                "condition": f"this {kind} enters",
                "event": TriggerEvent.ENTERS_THE_BATTLEFIELD,
            }
        ),
        ability.model_copy(
            update={
                "condition": f"this {kind} leaves the battlefield",
                "event": TriggerEvent.LEAVES_THE_BATTLEFIELD,
            }
        ),
    ]


#: "When `<self>` enters or dies, ..." - Apex Witchstalker's own "When this
#: creature enters or dies, you gain 2 life." (CR 700.7) and Aerid
#: Konstrari's identically-shaped "When Aerid Konstrari enters or dies,
#: create a Heartwood token." (CR 201.5c's own short/full-name self-
#: reference, same as `_expand_enters_or_leaves` already reads for "this
#: `<kind>`"). `_trigger_event` (`machines/abilities.py`) reads "enters"
#: first and stops, so this compound condition parsed as
#: `TriggerEvent.ENTERS_THE_BATTLEFIELD` alone and the "or dies" half - CR
#: 603.10a's death trigger, which is the half that matters whenever either
#: card actually dies rather than merely entering - was silently dropped.
_ENTERS_OR_DIES_RE = re.compile(r"^(?P<subject>.+?) enters or dies$", re.IGNORECASE)


def _expand_enters_or_dies(
    ability: TriggeredAbility, card_name: str, *, legendary: bool = True
) -> list[TriggeredAbility]:
    """One ability whose condition is `_ENTERS_OR_DIES_RE`'s shape becomes
    two: CR 603.6a's enters-the-battlefield ability and CR 700.4/603.10a's
    dies one, each self-referential and each a `TriggeredAbility` in its own
    right - the same split `_expand_attacks_or_blocks`, `_expand_enters_or_
    attacks` and `_expand_enters_or_leaves` already perform for their own
    compound conditions.

    The subject has to be a genuine self-reference - CR 700.7's "this
    `<noun>`" or one of `card_name`'s own CR 201.5/201.5c short forms
    (`self_reference_names`) - not just any condition that happens to end in
    "enters or dies"; nothing in this pool prints the compound any other
    way, and requiring it keeps this from ever misreading two unrelated
    clauses that merely share those two words.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    match = _ENTERS_OR_DIES_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    subject = match.group("subject")
    if not re.fullmatch(r"this [a-z]+", subject, re.IGNORECASE) and subject not in (
        self_reference_names(card_name, legendary=legendary)
    ):
        return [ability]
    return [
        ability.model_copy(
            update={"condition": f"{subject} enters", "event": TriggerEvent.ENTERS_THE_BATTLEFIELD}
        ),
        ability.model_copy(update={"condition": f"{subject} dies", "event": TriggerEvent.DIES}),
    ]


#: "Whenever `<self>` enters or deals combat damage to a player, ..." -
#: Kitsune, Dragon's Daughter's own condition, and Tomebound Lich's "this
#: creature" form. CR 603.1b: "A triggered ability may have more than one
#: trigger condition"; `_trigger_event` (`machines/abilities.py`) reads
#: "enters" first and stops, so the combat-damage half was silently dropped.
_ENTERS_OR_DEALS_COMBAT_DAMAGE_RE = re.compile(
    r"^(?P<subject>.+?) enters or deals combat damage to a player$", re.IGNORECASE
)


def _expand_enters_or_deals_combat_damage(
    ability: TriggeredAbility, card_name: str, *, legendary: bool = True
) -> list[TriggeredAbility]:
    """One ability whose condition is `_ENTERS_OR_DEALS_COMBAT_DAMAGE_RE`'s
    shape becomes two: CR 603.6a's enters-the-battlefield ability and the
    "deals combat damage to a player" one (`TriggerEvent.DEALS_DAMAGE`,
    whose own condition reader already tells combat damage to a player from
    any other damage) - the split `_expand_enters_or_dies` performs, with
    the same genuine-self-reference requirement on the subject.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    match = _ENTERS_OR_DEALS_COMBAT_DAMAGE_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    subject = match.group("subject")
    if not re.fullmatch(r"this [a-z]+", subject, re.IGNORECASE) and subject not in (
        self_reference_names(card_name, legendary=legendary)
    ):
        return [ability]
    return [
        ability.model_copy(
            update={"condition": f"{subject} enters", "event": TriggerEvent.ENTERS_THE_BATTLEFIELD}
        ),
        ability.model_copy(
            update={
                "condition": f"{subject} deals combat damage to a player",
                "event": TriggerEvent.DEALS_DAMAGE,
            }
        ),
    ]


#: "Whenever `<self>` enters or becomes tapped, ..." - Champions of the
#: Shoal's own condition (CR 603.1b, the same "more than one trigger
#: condition" shape `_expand_enters_or_dies` already splits). `_trigger_
#: event` (`machines/abilities.py`) reads "enters" first and stops, so the
#: "becomes tapped" half - which is the half that matters on every turn
#: after this permanent's own entrance - was silently dropped exactly the
#: way `_expand_enters_or_dies`'s own docstring describes for "enters or
#: dies".
_ENTERS_OR_BECOMES_TAPPED_RE = re.compile(
    r"^(?P<subject>.+?) enters or becomes tapped$", re.IGNORECASE
)


def _expand_enters_or_becomes_tapped(
    ability: TriggeredAbility, card_name: str, *, legendary: bool = True
) -> list[TriggeredAbility]:
    """One ability whose condition is `_ENTERS_OR_BECOMES_TAPPED_RE`'s shape
    becomes two: CR 603.6a's enters-the-battlefield ability and CR 701.26a's
    own `TriggerEvent.BECOMES_TAPPED` one, each self-referential and each a
    `TriggeredAbility` in its own right - the same split `_expand_enters_or_
    dies`/`_expand_enters_or_deals_combat_damage` already perform for their
    own compound conditions, with the same genuine-self-reference
    requirement on the subject.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    match = _ENTERS_OR_BECOMES_TAPPED_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    subject = match.group("subject")
    if not re.fullmatch(r"this [a-z]+", subject, re.IGNORECASE) and subject not in (
        self_reference_names(card_name, legendary=legendary)
    ):
        return [ability]
    return [
        ability.model_copy(
            update={"condition": f"{subject} enters", "event": TriggerEvent.ENTERS_THE_BATTLEFIELD}
        ),
        ability.model_copy(
            update={"condition": f"{subject} becomes tapped", "event": TriggerEvent.BECOMES_TAPPED}
        ),
    ]


#: "When `<self>` enters and at the beginning of your upkeep, ..." -
#: Gathering Stone's own condition (CR 603.1b: "A triggered ability may have
#: more than one trigger condition, in which case it triggers when any of
#: the events occurs"). `_trigger_event` (`machines/abilities.py`) reads
#: "enters" first and stops, so the upkeep half - which is the one that
#: matters on every turn after the permanent's own entrance - was silently
#: dropped, the identical gap `_expand_enters_or_dies` already closes for
#: "enters or dies".
_ENTERS_AND_UPKEEP_RE = re.compile(
    r"^(?P<subject>.+?) enters and at the beginning of your upkeep$", re.IGNORECASE
)


def _expand_enters_and_upkeep(
    ability: TriggeredAbility, card_name: str, *, legendary: bool = True
) -> list[TriggeredAbility]:
    """One ability whose condition is `_ENTERS_AND_UPKEEP_RE`'s shape becomes
    two: CR 603.6a's enters-the-battlefield ability and an ordinary "at the
    beginning of your upkeep" one (`TriggerEvent.BEGINNING_OF_STEP`, whose
    own `_step_matches` reads that printed condition text directly - no
    further field needs setting) - the same split `_expand_enters_or_dies`
    and `_expand_enters_or_deals_combat_damage` already perform for their
    own compound conditions, with the same genuine-self-reference
    requirement on the subject.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    match = _ENTERS_AND_UPKEEP_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    subject = match.group("subject")
    if not re.fullmatch(r"this [a-z]+", subject, re.IGNORECASE) and subject not in (
        self_reference_names(card_name, legendary=legendary)
    ):
        return [ability]
    return [
        ability.model_copy(
            update={"condition": f"{subject} enters", "event": TriggerEvent.ENTERS_THE_BATTLEFIELD}
        ),
        ability.model_copy(
            update={
                "condition": "at the beginning of your upkeep",
                "event": TriggerEvent.BEGINNING_OF_STEP,
            }
        ),
    ]


#: `activated_abilities_of`'s memo, keyed on `(Card.id, face)` so two
#: different printings - and the same printing asked about two different
#: faces - can never collide. Sound for the same reason `_ability_cache` in
#: `machines/abilities.py` is: `Card` is immutable (`frozen=True`), verified by
#: `tests/test_card.py::test_card_is_immutable`.
_activated_abilities_cache: dict[tuple[UUID, str | None], list[ActivatedAbility]] = {}


def activated_abilities_of(card: Card, face: str | None = None) -> list[ActivatedAbility]:
    """Every activated ability printed on a card (CR 113.3b, 602.1).

    A basic land prints none of its own - its mana ability is reminder text,
    which `parse_abilities` correctly does not treat as rules text - so a card
    with the basic supertype and no printed activated ability falls back to
    `intrinsic_land_ability` (CR 305.6). That is what lets `Game.activate_ability`
    tap a Forest at all, not only pay a mana cost with it through the
    `tap_for_mana` shortcut.

    `face` narrows the list to the abilities printed on one face, and is how a
    double-faced permanent's abilities follow the face that is up: CR 109.3
    counts abilities among an object's characteristics and CR 712.8d/712.8e/
    712.8f give such a permanent only the characteristics of the face that's
    up, so a transformed Ajani, Nacatl Pariah has Ajani, Nacatl Avenger's three
    loyalty abilities and none of his front face's, and an untransformed one has
    neither. `CardState.up_face_name` is what callers pass; `None` - every
    single-faced card - filters nothing.

    Memoised on `(card.id, face)` - see `_activated_abilities_cache`.
    """
    key = (card.id, face)
    cached = _activated_abilities_cache.get(key)
    if cached is not None:
        return cached
    printed = [
        ability
        for ability in parse_abilities(card)
        if isinstance(ability, ActivatedAbility)
        and (face is None or ability.face == face)
        # CR 721.2a: granted by the station symbol's static ability at N
        # charge counters, and found then through `added_ability_lines`; a
        # CR 711.2a/b level striation's at its level counters.
        and ability.station_threshold is None
        and ability.level_band is None
    ]
    result = printed or ([intrinsic] if (intrinsic := intrinsic_land_ability(card, face)) else [])
    _activated_abilities_cache[key] = result
    return result


def granted_activated_abilities_of(texts: Sequence[str]) -> list[ActivatedAbility]:
    """`CardState.granted_ability_texts`'s own activated lines, read the same
    way `activated_abilities_of` reads a card's printed ones.

    Urza's Saga's chapter II - "This Saga gains '{2}, {T}: Create a 0/0
    colorless Construct artifact creature token ...'" - is the reason this
    exists: without it, a granted activated ability would sit on `CardState.
    granted_ability_texts` fully parsed and completely unreachable, since
    `Game.activate_ability` only ever indexes `activated_abilities_of`'s own
    printed-card list. Callers append this to that list (never replace it),
    the same "additional to what is printed" convention `granted_mana_
    abilities` documents for the mana half.
    """
    return [
        ability
        for ability in parse_granted_ability_lines(texts)
        if isinstance(ability, ActivatedAbility)
    ]


def rewritten_ability_lines(game: "Game", permanent: CardState) -> tuple[str, ...] | None:
    """This permanent's *computed* ability text when a continuous effect has
    rewritten it away from the printed card, else None.

    CR 613.5: "The application of continuous effects as described by the layer
    system is continually and automatically performed by the game. All resulting
    changes to an object's characteristics are instantaneous." CR 109.3 counts
    abilities among an object's characteristics, so a permanent whose layer 1
    (CR 613.2c, 707.2: "the copy acquires the copiable values of the original
    object's characteristics") copy effect replaced its rules text has the
    *copied* object's abilities and none of its own - a land that has become a
    copy of Sol Ring can be tapped for `{C}{C}` and cannot be tapped for green.

    Only a rewrite is reported, never a plain grant: if every printed line
    survives into `Characteristics.abilities`, the callers' printed-plus-granted
    list is already right and keeping it keeps every ability *index* stable.
    Nothing is reported for a permanent the layer engine has not computed, or
    for one that lost all its ability text - CR 613.1f removal is already
    policed by `Game._still_has_ability`.
    """
    if permanent.zone is not Zone.BATTLEFIELD:
        return None
    try:
        computed = game.characteristics_of(permanent)
    except KeyError:
        return None
    lines = tuple(computed.abilities)
    if not lines:
        return None
    # CR 711.2: a leveler's striated lines are granted by its level symbols,
    # not printed abilities it always has (`leveler_lines`).
    printed = leveler_lines(permanent.oracle_text, None)
    if all(line in lines for line in printed):
        return None
    return lines


def added_ability_lines(game: "Game", permanent: CardState) -> tuple[str, ...]:
    """The ability lines a continuous effect *added* to this permanent on top of
    everything it prints, in computed order.

    The additive twin of `rewritten_ability_lines`, which reports only the case
    where a printed line was taken *away*. A layer 4 effect that grants a basic
    land type grants the intrinsic "{T}: Add [mana symbol]" that comes with it
    (CR 305.6, CR 613.1d) - Urborg, Tomb of Yawgmoth's Swamp, Yavimaya, Cradle
    of Growth's Forest, Dryad of the Ilysian Grove's all five - and every
    printed line survives, so `rewritten_ability_lines` correctly answers None
    and the caller keeps its printed list. That left the added mana ability
    visible on the computed board (CR 613.5) and unusable: the Forest under an
    Urborg could not actually be tapped for {B}.

    Reported separately, rather than by widening `rewritten_ability_lines`, so
    a caller can **append** these and keep every printed ability's index where
    it was - the stability `Game.activated_abilities` depends on.

    A line the permanent already carries in `granted_ability_texts` is left out,
    since those are folded in by the callers themselves and would otherwise be
    counted twice.

    CR 603.10a: off the battlefield, this reads `CardState.abilities_as_it_
    left` instead of the (now unrelated) live computed board - the identical
    look-back snapshot `_had_as_it_left` already filters a *printed*
    leaves-the-battlefield trigger against. Without this, a keyword a static
    ability *grants* to another permanent (Isilu, Carrier of Twilight's own
    "has persist") could never produce a leaves-the-battlefield trigger at
    all: `triggered_abilities_on` builds its own candidate list from this
    function's return, and CR 400.7 has already made the departing object a
    new one with an empty `computed_characteristics` (`None`) by the time
    that candidate list is asked for - not just an object CR 603.4 has to
    look back from, but one this function used to see as having gained
    nothing, ever.
    """
    if permanent.zone is not Zone.BATTLEFIELD:
        lines = permanent.abilities_as_it_left
        if lines is None:
            return ()
        printed = set(leveler_lines(permanent.oracle_text, None))
        granted = set(permanent.granted_ability_texts)
        # A grant `machines/layers._sync_stored_grant_ability_texts` had
        # already reconciled onto `granted_ability_texts` before this
        # permanent left - Rhys, the Evermore's own stored, one-shot "gains
        # persist until end of turn" - is `triggered_abilities_on`'s own
        # `source.granted_as_it_left` already, read at its own call site
        # just above this one; counted here too it would double the
        # ability the permanent's dies trigger produces.
        already_covered = granted | set(permanent.granted_as_it_left)
        return tuple(line for line in lines if line not in printed and line not in already_covered)
    try:
        computed = game.characteristics_of(permanent)
    except KeyError:
        return ()
    printed = set(leveler_lines(permanent.oracle_text, None))
    granted = set(permanent.granted_ability_texts)
    return tuple(line for line in computed.abilities if line not in printed and line not in granted)


def activated_abilities_from_lines(
    lines: Sequence[str], card: Card, face: str | None = None
) -> list[ActivatedAbility]:
    """`rewritten_ability_lines`' output read as activated abilities (CR 602.1).

    The same fallback `activated_abilities_of` applies: a basic land prints no
    activated ability of its own (its mana ability is reminder text), so a
    computed line list that parses to nothing falls back to
    `intrinsic_land_ability` (CR 305.6).
    """
    abilities = [
        ability
        for ability in parse_granted_ability_lines(lines)
        if isinstance(ability, ActivatedAbility)
    ]
    if abilities:
        return abilities
    intrinsic = intrinsic_land_ability(card, face)
    return [intrinsic] if intrinsic is not None else []


def granted_triggered_abilities_of(texts: Sequence[str]) -> list[TriggeredAbility]:
    """`CardState.granted_ability_texts`' own triggered abilities, read the same
    way `triggered_abilities_of` reads a card's printed ones.

    Two sources, mirroring that function exactly:

    - the granted lines that begin When, Whenever or At, expanded through the
      same compound-condition splitters a printed line goes through;
    - the granted lines that are a bare CR 702 keyword, written out by
      `machines/keywords.granted_keyword_triggered_abilities`.

    The second is what makes a *granted* evoke behave like a printed one.
    CR 702.74a: "Evoke represents two abilities: a static ability that
    functions in any zone from which the card with evoke can be cast and a
    triggered ability that functions on the battlefield." `machines/casting.py`
    executes the first when the keyword is announced; this is where the second
    comes from once the permanent is on the battlefield, and CR 400.7b -
    "effects from static abilities that grant an ability to a permanent spell
    that functions on the battlefield continue to apply to the permanent that
    spell becomes" - is why it is read off the object rather than off whatever
    granted it, which may well be dead by then.
    """
    # Imported here rather than at the top for the same cycle
    # `triggered_abilities_of` documents: `machines/keywords.py` imports this
    # module for `AbilityOnStack`.
    from ..keywords import granted_keyword_triggered_abilities

    granted = [
        ability
        for ability in parse_granted_ability_lines(texts)
        if isinstance(ability, TriggeredAbility)
        and (ability.event is not None or _unread_trigger_events(ability.condition))
    ]
    expanded: list[TriggeredAbility] = []
    for ability in granted:
        for split in _expand_attacks_or_blocks(ability):
            for enters_split in _expand_enters_or_attacks(split):
                for leaves_split in _expand_enters_or_leaves(enters_split):
                    for transforms_split in _expand_enters_or_transforms_into(leaves_split):
                        expanded.extend(_expand_transforms_and_first_main(transforms_split))
    return expanded + granted_keyword_triggered_abilities(texts)


def spell_grant_triggered_abilities(game: "Game", source: CardState) -> list[TriggeredAbility]:
    """The triggered abilities another permanent's static grant gives a spell
    on the stack or a card in hand (`machines/spell_grants.py`), and a cast
    spell's own casualty triggers (CR 702.153a) - nothing for an object in
    any other zone, which is every object most events ask about."""
    if source.zone not in (Zone.STACK, Zone.HAND):
        return []
    # Imported here for the same cycle `granted_triggered_abilities_of`
    # documents: `machines/keywords.py` imports this module.
    from ..spell_grants import granted_triggered_abilities_for

    return granted_triggered_abilities_for(game, source)


def triggered_abilities_on(game: "Game", source: CardState) -> list[TriggeredAbility]:
    """Every triggered ability `source` has right now, printed and granted,
    before any condition is read - the abilities `triggers_for` asks."""
    # CR 400.7b / CR 611.3d: an ability granted to this object is had by
    # this object, so it is asked here alongside the card's own printed
    # ones. Never *instead* of them - a grant adds.
    # CR 603.10a: a source that has just left the battlefield looks back at
    # what it was granted as it left - `CardState.move_to` has emptied the
    # live tuple (CR 400.7).
    granted = granted_triggered_abilities_of(
        (*source.granted_ability_texts, *source.granted_as_it_left)
    )
    # CR 613.5 / CR 707.2: a permanent whose computed ability text has been
    # rewritten by a layer 1 copy effect has the *copied* object's triggers
    # and not its own, so the printed card is the wrong thing to read.
    # `rewritten_ability_lines` answers None whenever nothing was taken
    # away, which is every ordinary permanent.
    rewritten = rewritten_ability_lines(game, source)
    if rewritten is not None:
        from ..sieges import copied_siege_triggered_abilities

        # CR 310.12b: a Siege's defeat trigger is intrinsic, not printed text,
        # so it never appears among the copied lines.
        granted = granted_triggered_abilities_of(rewritten) + copied_siege_triggered_abilities(
            game, source
        )
    else:
        # CR 613.1f / CR 613.5: a layer 6 grant ("Other creatures you
        # control are ... and have '...'") can add a triggered ability
        # this object neither prints nor carries in
        # `granted_ability_texts` - `layers.quoted_ability_grants` writes
        # it onto the computed board only. `added_ability_lines` is the
        # reader `Game.activated_abilities` already uses for the
        # identical gap on the activated-ability side (the intrinsic mana
        # ability a granted basic land type brings with it); mirrored
        # here so a granted "Whenever ..." is actually found rather than
        # granted invisibly.
        granted = granted + granted_triggered_abilities_of(added_ability_lines(game, source))
    # CR 604.2 / CR 611.3a: a permanent's "spells you cast have storm" or
    # "cards in your hand have miracle" grant, read now off the board -
    # `machines/spell_grants.py` - plus CR 702.153a's casualty trigger, one
    # per casualty cost paid (CR 702.153b).
    granted = granted + spell_grant_triggered_abilities(game, source)
    granted_ids = {id(ability) for ability in granted}
    printed_abilities = [] if rewritten is not None else triggered_abilities_of(source.card)
    had: list[TriggeredAbility] = []
    for ability in printed_abilities + granted:
        up_face_name = source.up_face_name
        if (
            up_face_name is not None
            # A granted line was never printed on any face (its `face` is
            # the empty string), so the double-faced filter below is not
            # a question that can be asked of it - CR 712.8d is about
            # which of the *card's* two printed sides is up, and a grant
            # is on neither.
            and id(ability) not in granted_ids
            and ability.face != up_face_name
        ):
            # CR 712.8d/712.8e/712.8f: a double-faced permanent has only
            # the characteristics of the face that's up, and CR 109.3
            # counts abilities among them. Witch-Blessed Meadow, played as
            # a land (CR 712.12), has no "when this creature enters"
            # trigger, because that line was printed on Witch Enchanter's
            # face; a transformed Duskwatch Recruiter has Krallenhorde
            # Howler's upkeep trigger and not its own (CR 701.27g), and an
            # untransformed one has the mirror.
            continue
        if ability.class_level is not None and source.class_level < ability.class_level:
            # CR 716.2a: "As long as this Class is level N or greater, it
            # has [Abilities]" - a level-gated trigger printed under a
            # bar the Class has not reached yet is not "in effect", the
            # same way `CardState.class_ability_text` already keeps a
            # static ability quiet until then.
            continue
        if id(ability) not in granted_ids and not _had_as_it_left(source, ability):
            continue
        had.append(ability)
    return had


def _had_as_it_left(source: CardState, ability: TriggeredAbility) -> bool:
    """CR 603.10a: a leaves-the-battlefield ability looks back at the object
    as it existed immediately before the event - so a printed one it had
    lost by then (layer 6, CR 613.1f: Hellcat, Undying Vigilante returned
    with no abilities) does not trigger. True for any object not just off
    the battlefield, or with no look-back snapshot."""
    if source.zone is Zone.BATTLEFIELD or ability.event not in _LOOK_BACK_EVENTS:
        return True
    lines = source.abilities_as_it_left
    if lines is None:
        return True
    text = ability.raw or ability.text
    return any(text in line or line in text for line in lines)


def abilities_triggered_by(
    game: "Game", event: GameEvent, sources: list[CardState]
) -> list[tuple[CardState, TriggeredAbility, str]]:
    """`(source, ability, controller)` for every ability of `sources` this
    event would trigger (CR 603.2, CR 603.4), without triggering anything.

    Changes nothing and mints nothing, so the payment search can ask what a
    tap would set off (`machines/cost.triggered_mana_bonus`) as often as it
    likes; `triggers_for` is this plus the once-per-turn bookkeeping and the
    stack objects.

    Every source is asked on one layered board (`snapshot.scan_pin`):
    nothing moves while they are, and a mutating command that raises the event
    would otherwise recompute the board once per source.
    """
    found: list[tuple[CardState, TriggeredAbility, str]] = []
    with scan_pin(game):
        for source in sources:
            controller = controller_of_source(game, source)
            for ability in triggered_abilities_on(game, source):
                if not condition_matches(game, ability, source, controller, event):
                    continue
                if source.zone not in zones_ability_functions_in(ability, source, game):
                    continue  # CR 113.6: doesn't function from the zone it's in.
                if not event_qualifier_holds(game, ability, source, controller, event):
                    continue  # CR 603.2: the event did not happen that way.
                if not intervening_if_holds(game, ability, source, event):
                    continue  # CR 603.4: it does not trigger at all.
                found.append((source, ability, controller))
    return found


#: "one or more `<description>` attack[ `<defender>`]" - The Earth King's
#: "one or more creatures you control with power 4 or greater attack" (no
#: defender named) and Frenzied Gorespawn's/Garruk, Curse Breaker's own
#: "one or more creatures attack one of your opponents" (CR 508.3a: "attacks
#: [a player, planeswalker, or battle]" - the defender is part of the same
#: printed condition, not a separate clause). CR 603.2c: "An ability triggers
#: only once each time its trigger event occurs. However, it can trigger
#: repeatedly if one event contains multiple occurrences" - the plural "one
#: or more" is one trigger for the declaration, and how many of the
#: attackers fit the description is the event's count, which a later "that
#: many" reads (`machines/effects.that_many`).
#: Flummoxed Cyclops' "two or more creatures your opponents control attack"
#: is the same batched declaration with a minimum count: the trigger event
#: still occurs once (CR 603.2c), and only when at least that many of the
#: declared attackers fit the description.
_ONE_OR_MORE_ATTACK_RE = re.compile(
    r"^(?P<minimum>one|two|three|four|five) or more (?P<description>.+?) "
    r"attack(?:\s+(?P<defender>.+))?$",
    re.IGNORECASE,
)


#: "creatures your opponents control" (Flummoxed Cyclops): attackers under
#: the control of anyone but the ability's own controller.
_ONE_OR_MORE_ATTACK_THEIRS = re.compile(
    r"\s*\b(?:your opponents control|an opponent controls)\b", re.IGNORECASE
)

#: "one of your opponents[ or a planeswalker they control]" - Frenzied
#: Gorespawn's own defender phrase and Frontier Warmonger's widened compound
#: form (CR 508.3a's "a player, planeswalker, or battle", restricted to an
#: opponent of the ability's controller). Both reduce to the identical
#: runtime question - is the attack's defender controlled by anyone but this
#: ability's own controller - since `GameEvent.defender_controller`/
#: `_defender_controller_of` already resolve a planeswalker's defender down
#: to its controller before either reader ever sees it.
_DEFENDER_OPPONENT_RE = re.compile(
    r"^one of your opponents(?:\s+or\s+a\s+planeswalker\s+they\s+control)?\.?$", re.IGNORECASE
)


#: Screaming Swarm's "you attack with one or more creatures" - the same
#: batched declaration as "one or more creatures you control attack", said
#: from the attacking player's side (CR 508.3d). Path of Mettle's "you
#: attack with at least two creatures that have ..." is the same declaration
#: with a minimum.
_YOU_ATTACK_WITH_ONE_OR_MORE_RE = re.compile(
    r"^you attack with (?:one or more|at least (?P<least>two|three|four|five)) "
    r"(?P<description>.+?)$",
    re.IGNORECASE,
)

#: A CR 702 keyword list: "first strike, double strike, vigilance, and/or
#: haste" / "flying or reach" - the keywords `machines/combat.Keyword` names.
_KEYWORD_LIST_SEPARATOR_RE = re.compile(r"\s*,\s*(?:and/or\s+|or\s+|and\s+)?|\s+(?:and/or|or)\s+")


def parse_keyword_list(text: str) -> tuple[str, ...] | None:
    """The keywords of a printed "A, B, C, and/or D" list, lowercased, or
    None when any item is not a keyword `machines/combat.Keyword` names."""
    from ..combat import Keyword

    known = {member.value.lower() for member in Keyword}
    items = [item.strip().lower() for item in _KEYWORD_LIST_SEPARATOR_RE.split(text.strip())]
    items = [item for item in items if item]
    if not items or any(item not in known for item in items):
        return None
    return tuple(items)


#: "creatures that have `<keyword list>`" / "creatures with `<keyword list>`"
#: - an attacker qualifies with any one of them.
_CREATURES_WITH_KEYWORD_LIST_RE = re.compile(
    r"^creatures (?:that have|with) (?P<list>.+)$", re.IGNORECASE
)


def _batched_attack_match(condition: str) -> "re.Match[str] | None":
    """`_ONE_OR_MORE_ATTACK_RE` over `condition`, with "you attack with one
    or more X" (or "at least N X") read as its equivalent "one (N) or more X
    you control attack"."""
    text = condition.strip()
    you_attack = _YOU_ATTACK_WITH_ONE_OR_MORE_RE.fullmatch(text)
    if you_attack is not None:
        minimum = (you_attack.group("least") or "one").lower()
        text = f"{minimum} or more {you_attack.group('description')} you control attack"
    return _ONE_OR_MORE_ATTACK_RE.fullmatch(text)


def batched_attack_minimum(condition: str) -> int:
    """How many fitting attackers a batched attack condition needs: the
    "`<N>` or more" count (`_ONE_OR_MORE_ATTACK_RE`), 1 for anything else."""
    match = _batched_attack_match(condition)
    if match is None:
        return 1
    return parse_count(match.group("minimum")) or 1


#: "a player attacks with five or more creatures" (Aurelia, the Law Above):
#: the attacking player's declared count, read once per declaration (CR 508.3d).
PLAYER_ATTACKS_WITH_N_OR_MORE_RE = re.compile(
    rf"^(?P<who>a player|you|an opponent) attacks? with (?P<n>{COUNT}) or more creatures$"
)


def is_batched_attack_condition(condition: str) -> bool:
    """Whether `condition` is "one or more `<description>` attack[
    `<defender>`]" (or "you attack with one or more `<description>`", or "a
    player attacks with `<N>` or more creatures") - one trigger for a whole
    declaration (`batched_attackers`)."""
    return (
        _batched_attack_match(condition) is not None
        or PLAYER_ATTACKS_WITH_N_OR_MORE_RE.fullmatch(condition.strip().lower()) is not None
    )


def _defender_controller_of(game: "Game", attacker: CardState) -> str | None:
    """The defending player for `attacker` (CR 508.5) - a player directly, a
    planeswalker's controller, or a battle's protector - the same resolution
    `Game._emit_attack_event` already does for `GameEvent.defender_
    controller`, read here off `Game.combat` directly since a delayed or
    printed group condition is checked before any one attacker's own event
    exists yet."""
    from ..combat import defending_player

    attack = game.combat.attack_by(attacker.id)
    if attack is None:
        return None
    return defending_player(game, attack.defender)


def batched_attackers(game: "Game", condition: str, controller: str) -> list[CardState] | None:
    """The attacking creatures a "one or more `<description>` attack[
    `<defender>`]" condition counts, or `None` when `condition` is not that
    shape, its description does not read (`machines/targeting.
    permanent_description`, the grammar a "target" phrase uses, with "you
    control" read here as the attackers' own controller), or it names a
    defender phrase this reader does not recognise (`_DEFENDER_OPPONENT_RE`)
    - fail closed rather than ignore an unread qualifier."""
    match = _batched_attack_match(condition)
    if match is None:
        return None
    from ..combat import has_keyword
    from ..targeting import permanent_description

    description = match.group("description")
    yours = _ONE_OR_MORE_ATTACK_YOURS.search(description) is not None
    theirs = _ONE_OR_MORE_ATTACK_THEIRS.search(description) is not None
    description = _ONE_OR_MORE_ATTACK_THEIRS.sub("", description)
    bare = _ONE_OR_MORE_ATTACK_YOURS.sub("", description).strip()
    keyword_list = _CREATURES_WITH_KEYWORD_LIST_RE.fullmatch(bare)
    keywords = parse_keyword_list(keyword_list.group("list")) if keyword_list else None
    requirement = None if keywords is not None else permanent_description(bare)
    if requirement is None and keywords is None:
        return None
    defender = match.group("defender")
    opponent_only = False
    if defender is not None:
        if _DEFENDER_OPPONENT_RE.fullmatch(defender.strip()) is None:
            return None
        opponent_only = True
    return [
        attacker
        for attacker in game.attacking_creatures()
        if (not yours or game.controller_of(attacker).username == controller)
        and (not theirs or game.controller_of(attacker).username != controller)
        and (
            requirement.rejects(attacker, controller, game) is None
            if requirement is not None
            else any(has_keyword(attacker, keyword, game) for keyword in keywords or ())
        )
        and (
            not opponent_only
            or (
                (defender_controller := _defender_controller_of(game, attacker)) is not None
                and defender_controller != controller
            )
        )
    ]


def batched_combat_damage_sources(
    game: "Game", condition: str, controller: str, event: GameEvent
) -> list[UUID] | None:
    """The sources a "one or more `<description>` deal combat damage to
    `<recipient>`" condition counts in `event`'s combat damage step, or
    `None` when `condition` is not that shape or its description does not
    read (fail closed).

    The step's records are the last `event.amount` entries of `Game.
    combat_damage_to_players_this_turn` - the event is matched as it is
    emitted, right after that step's damage was dealt (CR 510.2), so nothing
    has been appended since. Each record holds the source's controller and
    creature types *when it dealt the damage*; a bare subtype list
    ("Assassins") is read off those, and any other description ("creatures
    with flying", "non-Human creatures") through `machines/targeting.
    permanent_description` against the source as it is now - still on the
    battlefield, since state-based actions have not run yet (CR 510.2 is
    followed by CR 704.3's check only once the step's triggers are
    collected).
    """
    match = _ONE_OR_MORE_DEAL_COMBAT_DAMAGE_RE.fullmatch(condition.strip())
    if match is None:
        return None
    if event.event is not ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS or event.player is None:
        return []
    if match.group("recipient").lower() != "a player" and event.player == controller:
        return []
    description = match.group("description")
    yours = _ONE_OR_MORE_ATTACK_YOURS.search(description) is not None
    remainder = " ".join(_ONE_OR_MORE_ATTACK_YOURS.sub("", description).split())
    if not yours and re.search(r"\bcontrols?\b", remainder, re.IGNORECASE):
        return None
    subtypes = _bare_subtype_list(remainder)
    requirement = None
    if subtypes is None:
        from ..targeting import permanent_description

        requirement = permanent_description(remainder)
        if requirement is None:
            return None
    records = game.combat_damage_to_players_this_turn
    step_records = records[len(records) - (event.amount or 0) :] if event.amount else []
    found: list[UUID] = []
    for record in step_records:
        if record.player != event.player or (yours and record.controller != controller):
            continue
        if subtypes is not None:
            if not subtypes & {kind.lower() for kind in record.creature_types}:
                continue
        else:
            source = game.find_by_id(record.source_id)
            if not isinstance(source, CardState) or requirement is None:
                continue
            if requirement.rejects(source, controller, game) is not None:
                continue
        if record.source_id not in found:
            found.append(record.source_id)
    return found


#: CR 603.2c's "one event contains multiple occurrences" for a discard: "you
#: discard a card" (and CR 702.29d's "cycle or discard [another] card") is
#: about each card, so one instruction discarding two cards is two
#: occurrences. "one or more cards" is the batch itself and stays one.
#: "discard a `<quality>` card" (Wharf Infiltrator's "a creature card",
#: Invasion of Kaldheim's "a land card") narrows which discarded cards count
#: at all - `quality` is one bare type/subtype word, read the identical way
#: a search's own stated quality is (`machines.effects._quality_matcher`,
#: imported locally below to avoid this module's own import cycle with
#: `machines/effects.py`).
_PER_CARD_DISCARD_CONDITION = re.compile(
    r"\bdiscards? (?P<which>a card|another card|an? (?P<quality>[a-z]+) card)\b"
)


def discard_occurrences(
    game: "Game", ability: TriggeredAbility, source: CardState, event: GameEvent
) -> int:
    """How many times a `DISCARDS_A_CARD` trigger fires off `event` (CR
    603.2c): once per discarded card matching the condition's own quality
    (if it has one) for a per-card condition - never counting the source
    itself for "another card" (Curator of Mysteries, Archfiend of Ifnir) -
    and once for anything else. A cycled card is one discard, so CR 702.29d's
    "cycles or discards" counts it once.

    A quality's card is looked up by id (`Game.find_by_id`) rather than read
    off the event itself: `Game.discard_cards` moves each card to the
    graveyard *before* emitting `DISCARDS_A_CARD` (CR 701.9a), so it is
    already sitting there, with its own printed type line, by the time this
    ever runs.
    """
    if ability.event is not TriggerEvent.DISCARDS_A_CARD:
        return 1
    match = _PER_CARD_DISCARD_CONDITION.search(ability.condition.lower())
    if match is None or not event.discarded_ids:
        return 1
    ids = event.discarded_ids
    if match.group("which") == "another card":
        ids = tuple(card_id for card_id in ids if card_id != source.id)
    quality = match.group("quality")
    if quality is not None:
        from ..effects import _quality_matcher  # avoids effects<->triggers import cycle

        matches = _quality_matcher(quality)
        ids = tuple(
            card_id
            for card_id in ids
            if (found := game.find_by_id(card_id)) is not None and matches(found)
        )
    return len(ids)


def _event_for(
    game: "Game", ability: TriggeredAbility, controller: str, event: GameEvent, source: CardState
) -> GameEvent:
    """The event this ability carries onto the stack: `event` itself, or -
    for a batched "one or more `<description>` attack" trigger - a copy
    whose `amount` is how many attackers fit the description, the count
    this ability's own "that many" reads (CR 603.2c); or, for a
    self-referential "`<name>` is put into a graveyard from anywhere"
    (Emrakul, the Aeons Torn; Purity), a copy stamped with `source`'s own
    identity and current `zone_change_stamp` - `PUT_INTO_GRAVEYARD`'s shared
    batch event otherwise carries neither, which is fine for a batched "one
    or more ... cards" condition (read straight off `Game.graveyard_batch`)
    but leaves a consequence that finds the object by its event
    (`machines/effects._dead_self_found`, CR 400.7e/608.2h) with nothing to
    find: `source` here is already that object's current (graveyard)
    incarnation, found the same way `Game.emit` widened its own `sources`
    to offer every graveyard card in the first place."""
    if event.event is ExtraTriggerEvent.PUT_INTO_GRAVEYARD and event.subject_id is None:
        arrival = next((a for a in game.graveyard_batch if a.card_id == source.id), None)
        if arrival is not None:
            return event.model_copy(
                update={
                    "subject_id": source.id,
                    "zone_change_stamp": source.zone_change_stamp,
                    "player": arrival.player,
                }
            )
    if ability.event is not TriggerEvent.ATTACKS or event.subject_id is not None:
        return event
    batch = batched_attackers(game, ability.condition, controller)
    if batch is None:
        return event
    return event.model_copy(update={"amount": len(batch)})


def triggers_for(game: "Game", event: GameEvent, sources: list[CardState]) -> list[AbilityOnStack]:
    """Every ability `sources` have that this event triggers (CR 603.2).

    The intervening *if* of CR 603.4 is checked here: an ability whose clause is
    false does not trigger at all, which is a different thing from triggering and
    then doing nothing.
    """
    triggered: list[AbilityOnStack] = []
    for source, ability, controller in abilities_triggered_by(game, event, sources):
        if ability.triggers_only_if is not None and not game.condition_holds(
            controller, ability.triggers_only_if, source
        ):
            # "This ability triggers only if ..." - asked as the event occurs
            # (as CR 603.2h's and CR 702.169c's restrictions are), never on
            # resolution; an unread clause (None) fails closed and does not
            # trigger.
            continue
        if ability.once_per_turn:
            # CR 603.2h: "the ability triggers only if its source's
            # controller has not yet taken the indicated action that
            # turn" - Caretaker's Talent's own "This ability triggers
            # only once each turn." `key` pairs the source with the
            # ability's printed text, so a permanent with more than one
            # once-per-turn trigger is tracked separately for each, while
            # the conditions of one CR 603.1b compound (MACH-1's "When
            # MACH-1 enters and whenever you gain life") - split into one
            # `TriggeredAbility` each, all sharing that text - share one
            # budget, because the restriction is on the ability.
            key = f"{source.id}:{ability.text}"
            fired = game.once_per_turn_triggers.get(key, 0)
            if fired > 0:
                continue
            game.once_per_turn_triggers[key] = fired + 1
        on_stack = AbilityOnStack(
            kind=AbilityKind.TRIGGERED,
            ability=ability,
            source_id=source.id,
            source_name=source.name,
            controller=controller,
            source_stamp=source.zone_change_stamp,
            source_times_transformed=source.times_transformed,
            event=_event_for(game, ability, controller, event, source),
        )
        triggered.append(on_stack)
        # CR 603.2c: one discard instruction of several cards is several
        # occurrences of a per-card "discard a card" condition.
        for _ in range(discard_occurrences(game, ability, source, event) - 1):
            triggered.append(on_stack.model_copy(update={"id": new_id()}, deep=True))
        # CR 603.2d: "determine how many times it should trigger, then
        # trigger it that many times" - Panharmonicon. Each extra time is a
        # separate ability on the stack in its own right, with its own id.
        for _ in range(additional_trigger_times(game, on_stack, source, event)):
            triggered.append(on_stack.model_copy(update={"id": new_id()}, deep=True))
    return triggered


#: CR 603.2d's own shape, as Panharmonicon prints it: "If an artifact or
#: creature entering causes a triggered ability of a permanent you control to
#: trigger, that ability triggers an additional time."
_ADDITIONAL_TRIGGER_RE = re.compile(
    r"^if (?P<cause>.+?) causes a triggered ability of a permanent you control "
    r"to trigger, that ability triggers an additional time\.?$",
    re.IGNORECASE,
)


#: CR 603.2d's other shape, keyed by *whose* ability it is rather than by
#: what caused it: "If a triggered ability of a Dwarf you control triggers,
#: that ability triggers an additional time." (Bifur, Melodic Rider, behind
#: its enduring-story gate), "... of a Shaman or another Wizard you control
#: ..." (Harmonic Prodigy), "... of a legendary creature you control ..."
#: (Annie Joins Up), "... of another Elemental you control triggers, it
#: triggers ..." (Twinflame Travelers), "... of a permanent you control ..."
#: (Fractured Realm - "permanent" is a word every permanent has), and "... of
#: equipped creature ..." (Wizard's Staff, CR 301.5a's "equipped creature").
_TYPED_ADDITIONAL_TRIGGER_RE = re.compile(
    r"^if a triggered ability of (?P<whose>.+?) triggers, "
    r"(?:that ability|it) triggers an additional time\.?$",
    re.IGNORECASE,
)


def _multiplier_line(line: str) -> tuple[str, str | None]:
    """A static line with its designation gate split off, and the gate."""
    gated = split_as_long_as(line.strip())
    if gated is None:
        return line.strip(), None
    condition, rest = gated
    return rest, condition


def is_additional_trigger_line(text: str) -> bool:
    """Whether a static line is CR 603.2d's multiplier - an entering cause
    `_entering_cause_matches` can read, or a source `_typed_whose` can - gated
    on a designation or not: what `support.py` counts handled."""
    line, _condition = _multiplier_line(text)
    match = _ADDITIONAL_TRIGGER_RE.match(line)
    if match is not None:
        cause = _ENTERING_CAUSE_RE.match(match["cause"].strip())
        return cause is not None and _cause_words(cause["types"]) is not None
    typed = _TYPED_ADDITIONAL_TRIGGER_RE.match(line)
    return typed is not None and _typed_whose(typed["whose"]) is not None


def _computed_ability_lines(game: "Game", permanent: CardState) -> tuple[str, ...]:
    """This permanent's ability text as the layer system computes it (CR 613.5),
    falling back to the printed lines for a permanent the engine has not
    computed."""
    try:
        return tuple(game.characteristics_of(permanent).abilities)
    except KeyError:
        return tuple(
            line.strip() for line in (permanent.oracle_text or "").splitlines() if line.strip()
        )


def additional_trigger_times(
    game: "Game", ability: AbilityOnStack, source: CardState, event: GameEvent
) -> int:
    """How many *extra* times this ability triggers, by CR 603.2d.

    CR 603.2d: "An ability may state that a triggered ability triggers
    additional times. In this case, rather than simply determining that such an
    ability has triggered, determine how many times it should trigger, then
    trigger it that many times."

    Two shapes are read: the entering cause below, and `_TYPED_ADDITIONAL_
    TRIGGER_RE`'s "if a triggered ability of `<whose>` triggers" - Bifur,
    Melodic Rider's Dwarfs, Harmonic Prodigy's Shamans and other Wizards,
    Wizard's Staff's equipped creature - either behind a designation gate
    ("As long as you have an enduring story, ...", `machines/designations.
    py`) checked against the multiplier's controller.

    Every permanent on the battlefield is asked whether one of its own static
    ability lines is a multiplier of this shape, read off the *computed* text
    (CR 613.5) - Panharmonicon, Elesh Norn, Mother of Machines, Starfield
    Vocalist, Ancient Greenwarden, Naban, Dean of Iteration. Each one's own gate
    is checked here rather than assumed: the ability's source has to be a
    permanent the multiplier's controller controls, and the event has to be the
    entrance its cause names (`_entering_cause_matches`).

    Only what `triggers_for` builds from a *printed* ability is multiplied. A
    delayed triggered ability (CR 603.7a) is created during the resolution of
    the ability it belongs to and fired by `DelayedTriggers`, never by this
    function - so doubling the ability that creates a delayed trigger does not
    double the delayed trigger, which is DDR#981's whole point.
    """
    if source.zone is not Zone.BATTLEFIELD:
        return 0
    extra = 0
    for permanent in list(game.battlefield):
        controller = permanent.controller
        if controller is None:
            continue
        # "a triggered ability of a permanent / a Dwarf **you** control" -
        # every shape but "equipped creature", which names its object outright.
        yours = controller == ability.controller
        for printed in _computed_ability_lines(game, permanent):
            line, condition = _multiplier_line(printed)
            if condition is not None and not designation_holds(condition, game.player(controller)):
                continue
            if match := _ADDITIONAL_TRIGGER_RE.match(line):
                if yours and _entering_cause_matches(game, match["cause"], event, controller):
                    extra += 1
                continue
            typed = _TYPED_ADDITIONAL_TRIGGER_RE.match(line)
            if typed is None:
                continue
            whose = _typed_whose(typed["whose"])
            if (
                whose is not None
                and (whose.equipped or (yours and source.controller == controller))
                and _typed_source_matches(game, whose, permanent, source)
            ):
                extra += 1
    return extra


def _state_trigger_abilities(game: "Game", source: CardState) -> list[TriggeredAbility]:
    """The CR 603.8 abilities this permanent has right now.

    Read off the *computed* ability text (CR 613.5, CR 109.3: abilities are
    characteristics) rather than the printed card, so a permanent that has lost
    all abilities in layer 6 (CR 613.1f) has no state trigger left - which is
    DDR#961's Tishana's Tidebinder exactly. A permanent the layer engine has
    not computed falls back to its printed text.
    """
    try:
        lines: Sequence[str] = tuple(game.characteristics_of(source).abilities)
        parsed: list[Ability] = parse_granted_ability_lines(lines)
    except KeyError:
        parsed = parse_abilities(source.card)
    return [
        ability
        for ability in parsed
        if isinstance(ability, TriggeredAbility)
        and ability.event is None
        and _STATE_COUNTER_TRIGGER_RE.match(ability.condition.strip())
    ]


def state_triggers_for(game: "Game") -> list[AbilityOnStack]:
    """Every CR 603.8 state trigger that has just become true.

    CR 603.8: "Some triggered abilities trigger when a game state ... is true,
    rather than triggering when an event occurs." CR 704.1a confirms these are
    triggered abilities and not state-based actions, so what comes back here is
    an ordinary `AbilityOnStack` that CR 603.3 puts on the stack the next time a
    player would receive priority.

    The rest of CR 603.8 is the latch: such an ability "doesn't trigger again
    until it has left the stack". `Game.state_trigger_latches` holds, per source
    and condition, the id of the ability that is currently holding it shut, and
    the latch opens the moment that object is neither on the stack nor waiting
    in `pending_triggers` - which is true whether it left by resolving or by
    being countered (CR 701.6a: countering "means to cancel it, removing it from
    the stack"). Countering therefore frees the trigger to fire again at once,
    which is DDR#961's whole ruling.

    Nothing is appended to `pending_triggers` here; the caller does that, the
    same way `Game.emit` owns that step for event triggers.
    """
    live = {item.id for item in game.stack if isinstance(item, AbilityOnStack)}
    live |= {item.id for item in game.pending_triggers}
    for key, ability_id in list(game.state_trigger_latches.items()):
        if ability_id not in live:
            del game.state_trigger_latches[key]

    # Read first, on one layered board (`snapshot.scan_pin`), and act
    # after: the sweep asks every permanent while nothing moves, and the
    # latch bookkeeping below is kept out of the read.
    with scan_pin(game):
        holding = [
            (source, source.controller or game.active_player.username, ability)
            for source in list(game.battlefield)
            for ability in _state_trigger_abilities(game, source)
            if _state_condition_holds(game, ability, source)
        ]

    triggered: list[AbilityOnStack] = []
    for source, controller, ability in holding:
        key = f"{source.id}:{ability.condition}"
        if key in game.state_trigger_latches:
            continue
        on_stack = AbilityOnStack(
            kind=AbilityKind.TRIGGERED,
            ability=ability,
            source_id=source.id,
            source_name=source.name,
            controller=controller,
            source_stamp=source.zone_change_stamp,
            source_times_transformed=source.times_transformed,
        )
        game.state_trigger_latches[key] = on_stack.id
        triggered.append(on_stack)
    return triggered


def apnap_order(triggered: list[AbilityOnStack], turn_order: list[str]) -> list[AbilityOnStack]:
    """Sort triggers into the order they are put on the stack (CR 603.3b).

    "First, each player, in APNAP order, puts each triggered ability they
    control on the stack in any order they choose." The active player goes
    first, so the active player's trigger ends up at the *bottom* of the pile
    and resolves last. This settles only which *player's* block goes on first -
    CR 405.3's direction too, for objects an effect puts on the stack at once.
    Within one player's set the order they triggered in is kept here, and
    `Game._order_triggers_by_controller` is what then puts CR 603.3b's "in any
    order they choose" to that player.

    A stable sort, deliberately: one controller's abilities stay contiguous, so
    the caller can walk the result and hand each run to its own controller.
    """
    rank = {username: index for index, username in enumerate(turn_order)}
    return sorted(triggered, key=lambda item: rank.get(item.controller, len(rank)))


from ._common import (  # noqa: E402
    _ABILITY_ACTIVATED_CONDITION,
    _CLASS_BECOMES_LEVEL_CONDITION,
    _COUNTERS_PUT_CONDITION,
    _COUNTERS_PUT_ON_DESCRIPTION_CONDITION,
    _CRIME_COMMITTED_CONDITION,
    _CYCLE_CONDITION,
    _DOOR_UNLOCKED_CONDITION,
    _ENLISTS_A_CREATURE_CONDITION,
    _ENTERING_CAUSE_RE,
    _EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION,
    _LAND_ADDED_CHOSEN_MANA_CONDITION,
    _LAST_COUNTER_CONDITION,
    _LAST_TIME_COUNTER_CONDITION,
    _LEAVES_GRAVEYARD_CONDITION,
    _LOSES_LIFE_CONDITION,
    _LOYALTY_COUNTERS_PUT_ON_PLANESWALKER_CONDITION,
    _NTH_COUNTER_PUT_CONDITION,
    _NTH_DRAW_CONDITION,
    _ONE_OR_MORE_ATTACK_YOURS,
    _ONE_OR_MORE_BECOME_TAPPED_CONDITION,
    _ONE_OR_MORE_CARDS_INTO_YOUR_GRAVEYARD_CONDITION,
    _ONE_OR_MORE_DEAL_COMBAT_DAMAGE_RE,
    _OPPONENTS_ARE_ATTACKED_CONDITION,
    _PLAY_A_CARD_EXILED_WITH_CONDITION,
    _PLAY_A_LAND_OR_CAST_CONDITION,
    _PLAYER_COUNTERS_PUT_CONDITION,
    _PUT_INTO_LIBRARY_CONDITION,
    _REVEALED_FIRST_DRAW_CONDITION,
    _REVEALED_THIS_WAY_CONDITION,
    _RING_TEMPTS_YOU_CONDITION,
    _ROLLS_DICE_CONDITION,
    _SEARCHES_LIBRARY_CONDITION,
    _SELF_PUT_INTO_GRAVEYARD_FROM_ANYWHERE_CONDITION,
    _SOLVE_A_CASE_CONDITION,
    _STATE_COUNTER_TRIGGER_RE,
    _UNTAPPED_DURING_UNTAP_STEP_CONDITION,
    _YOU_PUT_A_COUNTER_ON_QUALITY_CONDITION,
)
from .conditions import (  # noqa: E402
    _bare_subtype_list,
    _bending_events_named,
    _cause_words,
    _day_night_events_named,
    _entering_cause_matches,
    _required_cast_origin_zone,
    _returned_subject,
    _state_condition_holds,
    _typed_source_matches,
    _typed_whose,
    condition_matches,
    controller_of_source,
    entering_origin_zone,
    event_qualifier_holds,
    intervening_if_holds,
)

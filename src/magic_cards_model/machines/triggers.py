"""Abilities on the stack, and what makes a triggered ability trigger.

`machines/abilities.py` reads an ability off printed text and stops. This is the
half that makes one happen: it turns a game event into triggered abilities, and
it holds the object an ability becomes once it is on the stack.

Every rule number below was looked up in this session against the Comprehensive
Rules. The load-bearing ones:

- **CR 603.2** - "Whenever a game event or game state matches a triggered
  ability's trigger event, that ability automatically triggers. The ability
  doesn't do anything at this point."
- **CR 603.3** - "Once an ability has triggered, its controller puts it on the
  stack as an object that's not a card the next time a player would receive
  priority."
- **CR 603.3b** - several abilities that triggered since the last time a player
  received priority go on the stack in APNAP order: the active player puts
  theirs on first, so theirs end up *lowest* and resolve *last*.
- **CR 603.4** - the intervening *if*: the condition is checked when the trigger
  event occurs, and the ability triggers only if it is true. **CR 608.2a** then
  checks it again on resolution; if it is false the ability is removed from the
  stack and does nothing.
- **CR 405.1** - "When a spell is cast, the physical card is put on the stack.
  When an ability is activated or triggers, it goes on top of the stack without
  any card associated with it." **CR 113.1c** makes that ability an object.
- **CR 113.7 / 113.7a** - the source of an ability is the object that generated
  it, and "once activated or triggered, an ability exists on the stack
  independently of its source. Destruction or removal of the source after that
  time won't affect the ability."
- **CR 608.2n** - "As the final part of an ability's resolution, the ability is
  removed from the stack and ceases to exist." An ability never goes to a
  graveyard, because it is not a card.
- **CR 603.10a** - some zone-change triggers look back in time; a dies-trigger
  is one, so the permanent that just left the battlefield is still asked whether
  it triggered.
- **CR 500.6** - abilities that trigger "at the beginning of" a step trigger when
  that step begins and go on the stack the next time a player would receive
  priority.
- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield".

## What this reads, and what it refuses to read

Trigger conditions are matched by a small set of shapes rather than by a general
parser. `condition_matches` returns False for anything it cannot read, which
means a card whose trigger is not one of these shapes simply never fires - it is
never *wrongly* fired. The shapes understood are listed on `condition_matches`.
"""

import contextlib
import operator
import re
from collections.abc import Sequence
from enum import StrEnum
from functools import cache
from typing import TYPE_CHECKING, Annotated, Any, Literal, NamedTuple
from uuid import UUID

from pydantic import ConfigDict, Field

from ..data.subtypes import subtype_vocabulary
from ..ids import new_id
from ..models.card import Card, Color, Layout, Supertype, Type
from ..models.card_state import CardState, ChoiceKind, Counter, ExileAnnotation, TargetRef
from ..models.token import TokenState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count, parse_ordinal
from ..snapshot import EngineModel, scan_pin
from .abilities import (
    Ability,
    AbilityKind,
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    intrinsic_land_ability,
    parse_abilities,
    parse_granted_ability_lines,
    parse_mana_count,
    self_counter_mana_count,
    self_reference_names,
    self_reference_pattern,
)
from .turn import Step

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import CastRecord, Game

    # `.cost` imports names from this module and `.keywords` imports
    # `AbilityOnStack` itself, so neither can be imported for real up here -
    # `keyword_activation`/`unless_payment` below carry these as string
    # annotations, and `keywords.py`'s own `model_rebuild()` call, run once
    # both classes exist, is what resolves them for real.
    from .cost import CostPayment
    from .keywords import KeywordActivation


class ExtraTriggerEvent(StrEnum):
    """Trigger events with no `machines/abilities.TriggerEvent` member.

    `_trigger_event` (`machines/abilities.py`) reads a printed condition into a
    `TriggerEvent` or leaves `event` unset; a condition it cannot read parses
    with `event=None` and, until now, was dropped by `triggered_abilities_of`
    and could never fire. These are the events those dropped conditions watch,
    named here rather than there because this module owns the matching half.
    `condition_matches` reads them off the printed condition itself (see
    `_unread_trigger_events`), so a `TriggeredAbility` still carries
    `event=None` and nothing about the parser's own output changes.

    **Not all of these are emitted yet.** Each member below says either where
    it is raised from or which emit is still missing; a member with no emitter
    has a complete matcher here watching an event nothing raises.
    """

    #: CR 122.6: "Some spells and abilities refer to counters being put on an
    #: object. This refers to putting counters on that object while it's on the
    #: battlefield and also to an object that's given counters as it enters the
    #: battlefield." Basking Broodscale's and Emperor of Bones' "Whenever one
    #: or more +1/+1 counters are put on this creature". `GameEvent.
    #: counter_kind` is which kind, `GameEvent.amount` how many - CR 603.2c's
    #: "one event contains multiple occurrences" is *not* what a "one or more
    #: counters" condition asks for: that is one event with a count, so it
    #: fires once however many counters arrived at the same time.
    #: **Missing emit:** `Game.add_counters` (`models/game.py`), which today
    #: emits only for lore counters (CR 107.15a).
    COUNTERS_PUT = "counters_put"
    #: CR 122.6's same "counters being put on ... an object that's given
    #: counters" sentence, from a player's side rather than a permanent's -
    #: CR 122.1's "some kinds of counters are normally placed on players
    #: rather than on objects" (energy chief among them). Fabrication
    #: Module's "Whenever you get one or more {E} (energy counters), ..." and
    #: Territorial Gorger's identical condition with a different effect.
    #: `GameEvent.counter_kind` is which kind, `GameEvent.amount` how many,
    #: `GameEvent.player` who got them - CR 603.2c's "one event, multiple
    #: occurrences" reading is the same one `COUNTERS_PUT` documents above.
    #: **Emitted by:** `Game.add_player_counters` (`models/game.py`), through
    #: `Game._emit_player_counters_put`.
    PLAYER_COUNTERS_PUT = "player_counters_put"
    #: CR 603.10a names "abilities that trigger when a card leaves a graveyard"
    #: among the zone-change triggers that look back in time. Murktide Regent's
    #: "Whenever an instant or sorcery card leaves your graveyard" and Hardened
    #: Academic's "Whenever one or more cards leave your graveyard".
    #: **Missing emit:** every graveyard departure in `models/game.py` - the
    #: card exiled to pay delve, the card returned to hand, the card put onto
    #: the battlefield from a graveyard.
    LEAVES_GRAVEYARD = "leaves_graveyard"
    #: CR 401.1's library, as a destination: Wan Shi Tong, All-Knowing's
    #: "Whenever one or more cards are put into a library from anywhere". One
    #: event per instruction that moves cards there, with `GameEvent.amount`
    #: cards, since CR 603.2c makes several cards moved by one instruction one
    #: occurrence rather than several.
    #: **Missing emit:** the library moves in `models/game.py`/`machines/
    #: effects.py` (Brainstorm's own put-back among them).
    PUT_INTO_LIBRARY = "put_into_library"
    #: CR 406.2: "To exile an object is to put it into the exile zone from
    #: whatever zone it's currently in." Scoped to a *graveyard* as the origin,
    #: which is the half of Ketramose, the New Dawn's condition that
    #: `TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE` does not already cover.
    #: **Missing emit:** the graveyard-to-exile moves in `models/game.py`
    #: (delve, Rest in Peace's replacement, a graveyard-hate effect).
    EXILED_FROM_GRAVEYARD = "exiled_from_graveyard"
    #: "An ability caused a player to add mana", which is not the same event as
    #: CR 106.12's "tapped for mana": Caged Sun's "Whenever a land's ability
    #: causes you to add one or more mana of the chosen color" is about the
    #: *adding*, so a mana ability that costs no `{T}` matches it and so does
    #: another triggered mana ability's own addition - which is the whole of
    #: DDR#990's loop. `GameEvent.mana_added` carries which mana, and
    #: `GameEvent.subject_types` the type line of the object whose ability
    #: added it. Emitted by `Game.activate_ability`'s CR 605.3b fast path and
    #: by `Game.resolve_triggered_mana_abilities`.
    MANA_ADDED = "mana_added"
    #: CR 702.62a's third ability: "When the last time counter is removed from
    #: this card, if it's exiled, you may play it without paying its mana cost
    #: if able." The *last* one specifically - a suspended card going from one
    #: time counter to none - which is why this is its own event rather than a
    #: generic counters-removed one: the count reaching zero is the whole
    #: trigger condition. Emitted by `machines/casting.remove_suspend_time_
    #: counter`, the one place in the engine that takes a time counter off a
    #: suspended card, so both routes into it - suspend's own upkeep trigger
    #: and Greater Gargadon's printed "Sacrifice an artifact, creature, or
    #: land: Remove a time counter from this card" - raise it alike.
    LAST_TIME_COUNTER_REMOVED = "last_time_counter_removed"
    #: CR 502.3: "the active player determines which permanents they control
    #: will untap. Then they untap them all simultaneously." The Millennium
    #: Calendar's "Whenever you untap one or more permanents during your untap
    #: step" watches that one simultaneous untap, not each permanent's own
    #: `TriggerEvent.BECOMES_UNTAPPED`. `GameEvent.player` is the active
    #: player and `GameEvent.amount` how many permanents actually untapped.
    #: Emitted by `Game.untap_step`, and only when that number is not zero
    #: (CR 603.2g: "An ability triggers only if its trigger event actually
    #: occurs").
    UNTAPPED_DURING_UNTAP_STEP = "untapped_during_untap_step"
    #: CR 701.67c: "An ability that triggers whenever a player waterbends
    #: triggers whenever that player pays a waterbend cost, regardless of
    #: how they paid that cost." One event per waterbend cost actually paid
    #: (mana, taps, or a mix), not one per tap - `machines/objects_as_costs.
    #: waterbend`'s own per-symbol substitutions are how the cost is paid,
    #: not events of their own. Emitted by `Game.activate_ability` once the
    #: payment it opened through `begin_activating` is confirmed `PAID` and
    #: that `TotalCost` carried a waterbend cost (`CostPayment.
    #: waterbend_generic is not None`). `GameEvent.player` is the payer.
    WATERBENDS = "waterbends"
    #: The three sibling bending verbs Avatar Aang's own "Whenever you
    #: waterbend, earthbend, firebend, or airbend, draw a card" condition
    #: names alongside waterbend (CR 701.67c's own rule number covers only
    #: waterbend; the other three bending keywords are not built by this
    #: module - see `docs/engine-coverage.md`). Named here, with no emitter,
    #: purely so the condition parser can read the whole printed OR-list
    #: without misreading the words it does not yet have an event for as
    #: unparseable; `_unread_condition_matches` never returns True for one
    #: of these because nothing raises them.
    EARTHBENDS = "earthbends"
    FIREBENDS = "firebends"
    AIRBENDS = "airbends"
    #: CR 702.94a's linked trigger: "When you reveal this card this way, you
    #: may cast it by paying [cost] rather than its mana cost." CR 607.2h
    #: links it to miracle's static ability, so only a reveal *that ability*
    #: made is this event - never a reveal some other effect asked for.
    #: `GameEvent.subject_id` is the revealed card, `GameEvent.player` the
    #: player who drew and revealed it. **Emitted by:** `Game.draw_cards`,
    #: through `Game._offer_miracle_reveal`, and nowhere else.
    REVEALED_FOR_MIRACLE = "revealed_for_miracle"
    #: CR 510.2: "all combat damage that's been assigned is dealt
    #: simultaneously" - one combat damage step's damage to one player, as a
    #: single event, which is what a batched "Whenever one or more
    #: `<description>` you control deal combat damage to a player" condition
    #: watches (CR 603.2c: "An ability triggers only once each time its
    #: trigger event occurs"). Jacob Frye's "one or more Assassins", Invasion
    #: Tactics' "one or more Allies". `GameEvent.player` is the player dealt
    #: the damage; `GameEvent.amount` is how many `Game.combat_damage_to_
    #: players_this_turn` records that step appended - the tail
    #: `batched_combat_damage_sources` reads, each record carrying what its
    #: source was at the time it dealt the damage. **Emitted by:**
    #: `machines/combat.combat_damage_step`, once per player dealt combat
    #: damage in the step, and only when some was actually dealt (CR 603.2g).
    COMBAT_DAMAGE_TO_PLAYERS = "combat_damage_to_players"
    #: CR 305.1 / CR 305.2a: a player played a land - the special action from
    #: a hand, or a land played from another zone under a permission, or one
    #: played during a resolution. `GameEvent.player` is who played it and
    #: `GameEvent.origin_exile_annotation` the exile pile it was played out
    #: of, if any. CR 601.1a makes "playing a card" either this or a cast
    #: (`TriggerEvent.CAST_SPELL`), which is how Voltaic Visionary's "When
    #: you play a card exiled with this creature" watches both.
    #: **Emitted by:** `Game.play_land`, `Game._play_land_during_resolution`.
    PLAYS_LAND = "plays_land"
    #: CR 716.2a: a class level bar's ability, resolving, makes "This Class's
    #: level become N" - the event a "When this Class becomes level N"
    #: trigger printed under that bar watches. `GameEvent.subject_id` is the
    #: Class, `GameEvent.amount` the level it became. **Emitted by:** the
    #: level bar's resolution in `Game._effect_of`, and only when the
    #: level actually changed.
    CLASS_BECOMES_LEVEL = "class_becomes_level"


class GameEvent(EngineModel):
    """One thing that happened, in the shape a trigger condition is matched against.

    CR 603.2 asks whether "a game event or game state matches a triggered
    ability's trigger event". This is that game event, reduced to the handful of
    facts the conditions in `condition_matches` actually ask about.
    """

    event: TriggerEvent | ExtraTriggerEvent
    """Which event this is. `ExtraTriggerEvent` widens the field rather than
    replacing it: the parser's own `TriggerEvent` stays the vocabulary every
    existing emitter speaks, and the members this module had to name for
    itself sit alongside them. The two enums' values are disjoint, so a
    serialised event still round-trips to exactly the member it was."""

    subject_id: UUID | None = None
    """The object the event happened to: the permanent that entered, died,
    attacked, blocked or was sacrificed, the card that was drawn, the spell
    that was cast or countered, or the source that dealt damage."""

    subject_name: str | None = None
    subject_controller: str | None = None
    subject_card: Card | None = None
    """The printing of the subject, kept so a cast trigger can ask what kind of
    spell it was after the card has moved on."""

    subject_types: tuple[Type, ...] | None = None
    """The subject's card types *as they actually are* right now (CR 712.8f,
    712.8a, 712.12), not the raw printing's front-face-only types.

    `subject_card.types` reads `Card.front_type_line`, which is structurally
    the front face - correct outside the battlefield and stack (CR 712.8a) but
    wrong for a modal double-faced permanent played for its back face: "While a
    modal double-faced ... permanent is on the battlefield, it has only the
    characteristics of the face that's up" (CR 712.8f), and CR 603.10 checks a
    trigger condition against the object "as it exists" (an enters-the-
    battlefield trigger is not one of the look-back exceptions, so this is the
    permanent as it exists on the battlefield now). `CardState.types` already
    reads the up face - the land face when `land_face_played` names one,
    otherwise the front face - so this is that value, captured at the moment
    the event is built rather than recomputed from a bare `Card` later.
    `None` for an event with no `CardState` subject to ask (a countered spell
    once removed from the stack, a leaves-battlefield-to-exile event no
    condition reads by type) - callers that use this fall back to "matches
    nothing named" the same way `subject_card=None` already did."""

    subject_subtypes: tuple[str, ...] | None = None
    """The subject's subtypes, read the same up-face-aware way as
    `subject_types` (CR 205.3a, 712.8f) - "whenever another Merfolk enters"
    needs the face that's actually up, not `Card.subtypes`'s front-face-only
    read."""

    subject_colors: tuple[Color, ...] | None = None
    """The subject's colors (CR 105.2), read the same up-face-aware way as
    `subject_types` - `CardState.colors` rather than `Card.colors`, which is
    front-face-only. A cast event populates this with the spell's colors as it
    sits on the stack, which is what "Whenever you cast a colorless spell ..."
    (Sanctum of Ugin, Ugin, Eye of the Storms) reads; `None` for an event with
    no `CardState` subject to ask, the same fallback `subject_types` already
    uses."""

    mana_added: tuple[Color, ...] = ()
    """The mana this event put into a player's pool, one entry per mana.

    CR 106.12a's "tapped for mana" event carried no colours at all, so a
    condition that asks *which* mana was added - Caged Sun's "Whenever a land's
    ability causes you to add one or more mana of the chosen color" - had
    nothing to read. Colourless is `Color.COLORLESS`, so `{C}{C}` is two
    entries, matching how `ManaAbility.produces` already reports a production.
    Empty for every event that is not about mana."""

    related_id: UUID | None = None
    """The other creature in a blocking pair (CR 509.1a)."""

    targeted_by: UUID | None = None
    """The spell or ability that targeted the subject (CR 702.21a).

    Ward's condition is "becomes the target of a spell or ability an opponent
    controls" and its effect is "counter *that* spell or ability", so the event
    has to carry which one it was. Held as an id, because CR 113.1c makes an
    ability on the stack an object with an id of its own and either kind can be
    the answer."""

    defender: TargetRef | None = None
    """What an attacking creature is attacking (CR 508.1a)."""

    defender_controller: str | None = None
    """Who `defender` belongs to right now - the defending player themselves
    when `defender` is a player, or that permanent's own controller when it
    is a planeswalker or battle - resolved once, at emission, and carried on
    the event rather than re-derived later. `DelayedTrigger.matches` (see
    `machines/delayed.py`) has no `Game` to ask "who controls this id" of; a
    delayed trigger watching "whenever a creature attacks you or a
    planeswalker you control" (Jace, Reality Sculptor's own `-3`) needs this
    answered as the attack is declared, not at match time."""

    player: str | None = None
    """The player the event is "yours" for: who cast the spell, whose step
    began, who drew the card, gained or lost the life, or took the damage."""

    combat: bool = False
    """For a damage event, whether it was dealt as a result of combat
    (CR 120.2a). "Deals combat damage" conditions refuse a noncombat event and
    the other way round, which is what separates Ragavan's trigger from the
    same creature taking a Lightning Bolt."""

    step: Step | None = None

    counter_kind: str | None = None
    """Which kind of counter was put on the subject, for an
    `ExtraTriggerEvent.COUNTERS_PUT` event (CR 122.1: "any name at all is a
    legal counter kind", which is why this is a plain string and not the
    `Counter` enum). `GameEvent.amount` is how many. `None` for every other
    event, and for a counters event whose emitter did not say - which a
    condition naming a kind ("one or more **+1/+1** counters") refuses, since
    a counter of unknown kind is not known to be the kind it asks for."""

    amount: int | None = None
    """How much, for an event a later clause refers back to by number rather
    than by object - "that much damage" (Questing Beast), "that many cards"
    (Nashi, Searcher in the Dark) - which is CR 607.1's linked-ability shape
    read within one ability rather than across two: the condition clause
    establishes the quantity and the effect clause points back at it. A
    damage event populates this with the amount CR 615.1's prevention and
    CR 608.2b's legality checks already settled on (`Game.deal_damage`'s own
    `event.amount` after replacement, not the raw amount requested).

    A cast event populates it too, with the spell's mana value **as it is on
    the stack** (CR 202.3e: "X is treated as ... the number chosen for it
    while the object is on the stack"), which `Game.put_on_stack` works out
    from `Card.cmc` (CR 107.3g's own X-is-0 reading of the printed cost) plus
    whatever `Game.cast_record` says X was paid as. This is *not* the same
    number as `subject_card.cmc` on this same event, which is always the
    static printed value - Chalice of the Void's "mana value equal to the
    number of charge counters" is exactly the condition that needs the real,
    on-stack number, not the printed one, or a Chalice on 3 would never catch
    a Fireball cast for X=3."""

    origin_zone: Zone | None = None
    """For a `TriggerEvent.ENTERS_THE_BATTLEFIELD` event, the zone the
    permanent entered from (`Game.enter_the_battlefield`; `Zone.STACK` for a
    resolving spell) - read by CR 603.4's "if it entered from your
    graveyard". For a `TriggerEvent.CAST_SPELL` event, the zone the card was in
    immediately before CR 601.2a moved it to the stack (CR 400.7: it is a new
    object on the stack, so this has to be captured before the move, not
    re-derived from the object afterwards). `Game.put_on_stack` is the only
    place a `CAST_SPELL` event is built, and it reads `card_state.zone` before
    calling `_take_out_of_every_zone`/`move_to`.

    Knowledge Pool's "Whenever a player casts a spell **from their hand**" and
    Appa, Steadfast Guardian's "Whenever you cast a spell **from exile**" both
    restrict this event to a specific origin - CR 603.2's "matches a triggered
    ability's trigger event" is not satisfied by a cast from anywhere else,
    which is exactly what `condition_matches`'s `CAST_SPELL` branch reads this
    for. Without it, a flashback cast from the graveyard matched "from their
    hand" the same as a cast from hand, and a card whose own free cast comes
    from exile (Knowledge Pool's second ability) would re-trigger itself
    forever. `None` for an event this field was never populated for."""

    origin_exile_annotation: ExileAnnotation | None = None
    """For a `TriggerEvent.CAST_SPELL` or `ExtraTriggerEvent.PLAYS_LAND`
    event of a card played out of exile, the pile it was in - captured before
    CR 400.7's move to the stack or the battlefield cleared it (`CastRecord.
    exile_annotation` for a cast). Voltaic Visionary's "When you play a card
    exiled with this creature" reads CR 607.2a's link off it. `None` for a
    card played from anywhere else."""

    target_id: UUID | None = None
    """For a `TriggerEvent.DEALS_DAMAGE` event whose target is a permanent
    (CR 120.3e), that permanent's id - the *recipient*, as opposed to
    `subject_id`'s source/dealer. Hexhaven Invigorator's own "Whenever this
    creature is dealt damage" is the only shape in the pool that asks about
    the receiving end rather than the dealing one, which is why this is its
    own field instead of overloading `subject_id`: a self-damaging source
    ("this creature deals damage to itself") needs both ends distinguishable
    at once. `None` for damage aimed at a player (that player is
    `GameEvent.player` already) and for every non-damage event."""

    target_controller: str | None = None
    """The controller of `target_id`, read the same way `subject_controller`
    is - `None` whenever `target_id` is."""

    target_types: tuple[Type, ...] | None = None
    """`target_id`'s computed card types (CR 613.5) at the moment of the
    event, the recipient-side twin of `subject_types`. `None` whenever
    `target_id` is."""

    discarded_ids: tuple[UUID, ...] = ()
    """Which cards `TriggerEvent.DISCARDS_A_CARD` actually moved, for Titanbones,
    Towering Heart's own self-referential "When you discard this card, ...".
    `Game.discard_cards` batches every card of one discard instruction into a
    single event (`GameEvent.amount` is the count, CR 603.2c's "one event,
    multiple occurrences"), so a self-reference has to be checked against the
    whole batch rather than a single `subject_id` - this is that batch, in
    the order `discard_cards` moved them. Empty for every other event."""

    attacking_alone: bool = False
    """Whether the whole attacking party this combat was this one creature
    (CR 506.5) - settled only once every attacker in the declaration is
    known, so `Game.declare_attackers` computes it after registering every
    attack in the batch and before emitting any of their `ATTACKS` events,
    never mid-loop. `False` for every event that is not `TriggerEvent.
    ATTACKS`, and for an `ATTACKS` event with no attacker of its own (the
    once-per-declaration "you attack" event `GameEvent.subject_id is None`
    already carries)."""

    attacking_player_alone: bool = False
    """CR 506.6's narrower cousin of `attacking_alone`: whether this
    attacker is the only creature attacking the *same defending player* it
    is attacking (irrelevant, and left `False`, for an attack on a
    planeswalker or a battle - CR 506.6 names a player specifically). Jiang
    Yanggu, Alone and Yuriko, Blade of the Mighty both print "attacks a
    player alone" rather than the bare CR 506.5 form, and the two conditions
    disagree the moment a second creature attacks a *different* player in
    the same combat: that declaration is not `attacking_alone`, but each
    attacker is still `attacking_player_alone`."""

    zone_change_stamp: UUID | None = None
    """For a `TriggerEvent.DIES` event, `subject_id`'s own `CardState.
    zone_change_stamp` as it was the instant CR 700.4's move landed it in
    the graveyard - `Game.put_into_graveyard` reads it off the object right
    after `Player.add` (`CardState.move_to`) mints it, before anything else
    can move the card again.

    CR 400.7e: a look-back ability "can find the new object that it became
    in the zone it moved to when the ability triggered, if that zone is a
    public zone" - a narrower promise than "wherever it is now". A dies
    trigger's own "exile it" (Ancient Adamantoise), "return it to its
    owner's hand" (Rancor) and "put it on the bottom of its owner's
    library" (Murderous Rider) all read this stamp against the live
    object's *current* `zone_change_stamp` before touching it: matching
    means the graveyard object the trigger is holding is still the exact
    incarnation CR 700.4 created, and a mismatch (moved again since,
    including back into the same graveyard as a fresh CR 400.7 object) means
    it cannot be found any more, so the clause does nothing - CR 608.2c
    never runs half an instruction, so the notice-free "nothing" is CR
    400.7's own answer, not a gap. `None` for every event this field was
    never populated for, and for a `DIES` event built before this field
    existed (an older decoded game), which is read the same "nothing found"
    way rather than crashing."""


class TargetingNoticeKind(StrEnum):
    """Why a triggered ability went on the stack with no targets chosen."""

    UNPARSED = "unparsed_targets"
    """`machines/targeting.py` could not read the restriction at all
    (`TargetingProfile.understood` is False). An engine gap, not a legal game
    state - the next unparsed shape must be audible, not silently dropped."""

    NO_LEGAL_TARGET = "no_legal_targets"
    """The restriction was read fine, but nothing satisfies it right now. A
    legitimate game state (CR 608.2d's own "nobody says otherwise" default),
    not a bug - and not the same thing as CR 608.2b's target-becomes-illegal
    fizzle, which only ever applies to a target that *was* chosen."""


class TargetingNotice(EngineModel):
    """One triggered ability whose targets could not be asked for as normal.

    `Game._ask_trigger_targets` used to `return []` silently whenever a
    restriction was unreadable, which is how White Orchid Phantom's "destroy up
    to one target nonbasic land" went on the stack, resolved, and did nothing -
    no decision offered, no record left anywhere. This is that record: appended
    to `Game.targeting_notices` so a player, a test, or a log consumer can see
    the difference between "the parser has a gap" and "there is genuinely
    nothing to target" instead of both looking like an ability that did
    nothing.
    """

    model_config = ConfigDict(frozen=True)

    kind: TargetingNoticeKind
    source_id: UUID | None
    source_name: str
    text: str
    """The ability's own rules text, read for its restriction."""


class InterveningIfNotice(EngineModel):
    """One triggered ability whose intervening *if* clause (CR 603.4) could not
    be evaluated, and so was made to fail closed rather than fire on a
    condition nobody actually checked.

    The old default in `intervening_if_holds` was the opposite: any clause it
    could not read was treated as true, which is how an unkicked Sowing
    Mycospawn exiled a land - "if it was kicked" was never checked, only ever
    assumed. Fail-open is worse than not implemented, so the new default is
    the reverse: a clause this module cannot read is treated as false, and
    that refusal is recorded here - the same "the engine could not read this"
    pattern `TargetingNotice` already established for target restrictions -
    so a gap in `intervening_if_holds` is visible instead of indistinguishable
    from an ability that legitimately never triggers.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    clause: str
    """The intervening *if* clause itself, as printed (without the leading
    "if")."""


class CastConditionNotice(EngineModel):
    """One "Whenever you cast a [restriction] spell" condition (CR 601.2,
    603.2) whose restriction this module recognised as a mana-value
    comparison but could not parse into a number and a direction, and so was
    made to fail closed rather than fire on a spell nobody actually checked.

    Sanctum of Ugin's "mana value 7 or greater" and its siblings ("... or
    less", "greater than ...", "less than ...", a bare "mana value N") are
    read by `condition_matches`; a mana-value clause shaped some other way is
    not known to be true, so the ability does not trigger, and that refusal is
    recorded here - the same "the engine could not read this" pattern
    `InterveningIfNotice` and `TargetingNotice` already established, so a gap
    stays visible instead of looking like a spell that legitimately did not
    match."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    condition: str
    """The trigger condition itself, as printed (without the leading "when",
    "whenever", or "at")."""


class AbilityOnStack(EngineModel):
    """An activated or triggered ability as an object on the stack (CR 113.1c).

    This is deliberately *not* a `CardState`. CR 405.1: an ability "goes on top
    of the stack without any card associated with it", so it has no zone to
    return to and never reaches a graveyard - CR 608.2n removes it from the
    stack and it ceases to exist.

    It keeps its source's id *and* its source's name, because CR 113.7a lets the
    source be destroyed while the ability is still waiting to resolve; the name
    is what is left to describe the ability once the object is gone.
    """

    id: UUID = Field(default_factory=new_id)
    kind: AbilityKind
    ability: TriggeredAbility | ActivatedAbility
    source_id: UUID | None = None
    source_name: str
    controller: str
    source_stamp: UUID | None = None
    """The source's `CardState.zone_change_stamp` when the ability triggered,
    or - for an activated ability - as its activation began, before a cost
    could move the source (`Game.begin_activating`), so a recheck on
    resolution reads the object it came from (CR 113.7a: "if the source is
    no longer in the zone it's expected to be in at that time,
    its last known information is used"; CR 608.2h) rather than whatever new
    object the card has since become (CR 400.7). `None` for an ability that
    records no source object."""
    state_class: Literal["AbilityOnStack"] = "AbilityOnStack"
    """Which concrete Python class built this object - decode-time identity
    for `models.game.StackObject`'s discriminated union, the exact
    counterpart of `CardState.state_class` (see that field's own docstring).

    `StackObject` is `CardState | TokenState | AbilityOnStack`, tagged on
    this field via `Field(discriminator="state_class")`
    (`models/game.py:StackObject`) - not a rules concept, just the label
    pydantic reads to pick the right arm of the union without guessing from
    shape. An `AbilityOnStack` never changes Python class the way a token
    does, so unlike `CardState.state_class` this one has nothing else to key
    off and is always this one literal value.
    """
    source_last_known: (
        Annotated[CardState | TokenState, Field(discriminator="state_class")] | None
    ) = Field(default=None, repr=False)
    """The source as it last existed, kept once it has ceased to exist while
    this ability waits (a token, CR 704.5d). CR 113.7a: the ability "exists on
    the stack independently of its source", and CR 608.2h has an effect that
    needs the source use "the object's last known information" once it is no
    longer in its zone - nothing is left to find by `source_id`. None while the
    source can still be found. `source_or_last_known` reads it."""
    targets: list[TargetRef] = Field(default_factory=list)
    event: GameEvent | None = None
    """The event that triggered it, for an effect that needs to know which
    creature attacked or what blocked what. None for an activated ability."""

    modes: list[int] = Field(default_factory=list)
    """A modal triggered ability's chosen modes, as their 1-based printed
    positions in the order chosen (CR 700.2). CR 603.3c: "its controller
    announces the mode choice when putting the ability on the stack", so
    `Game.put_triggers_on_stack` fills this before any target is chosen, and
    the resolving effect reads it rather than asking again. Empty for a
    non-modal ability."""

    mode_targets: list[list[TargetRef]] = Field(default_factory=list)
    """Each chosen mode's own targets (CR 700.2c, CR 700.2f), aligned by
    position with `modes`; `targets` is their concatenation."""

    x_value: int = 0
    """CR 107.3a's X, as announced when this ability was activated (CR 602.2b
    - "the remainder of the process for activating an ability is identical to
    the process for casting a spell", which includes announcing X). Zero for
    an ability whose cost carries no `{X}` at all - Fiend Artisan's
    "{X}{B/G}, {T}, Sacrifice another creature: Search your library for a
    creature card with mana value X or less ..." is the only ability in the
    pool that reads this; `machines/effects.py`'s `activated_effect_for` is
    what turns it back into the literal word "X" in the ability's own text."""

    keyword_activation: "KeywordActivation | None" = Field(default=None, repr=False)
    """The `machines/keywords.KeywordActivation` this ability came from, if any.

    `machines/effects.py` keys an ability's effect by the name of the card it is
    printed on. A CR 702 keyword's ability is printed on no card in particular -
    cycling (CR 702.29a) and equip (CR 702.6a) are the same ability wherever
    they appear - so there is no name to key it under and the effect lives with
    the keyword instead.

    This is the link back. `machines/keywords.keyword_effect_for` reads it, and
    it is the one thing a resolver needs to run a keyword's effect through the
    ordinary CR 608.2 path rather than by hand.

    Round-trips as real data now, not dropped: a dumped-and-decoded ability
    used to lose this entirely (`exclude=True`), so `keyword_effect_for` fell
    through past a keyword's own effect to the ordinary card-name lookup and a
    decoded cycling or equip activation resolved as nothing. `KeywordActivation`
    itself needed three fixes before it could carry across a round trip -
    see its own docstring and `model_post_init` below:

    - `KeywordActivation.game` (a live `Game`) is still `exclude=True` and
      reset to `None` on decode; nothing this module's `run_effect` reaches
      needs it to have survived by the time an ability is resolved through
      `keyword_effect_for` after a round trip, because `Game.model_post_init`
      relinks it from the outside, the same way it already relinks
      `Player.game`.
    - `KeywordActivation.payment` is a `CostPayment`, which is already plain
      data once its own `.game` is excluded (see `unless_payment` below for
      why that is safe) - but a *paused* payment (still `PENDING`, mid crew or
      equip) does need `.game` back to resume: `Game.model_post_init` relinks
      `keyword_activation.payment.game` the same pass it relinks `keyword_
      activation.game` itself, not "no change needed" as this once claimed.
    - `KeywordActivation.on_stack` points back at this very `AbilityOnStack`,
      which would make a dump cycle forever if both sides kept the edge.
      `KeywordActivation.on_stack` is `exclude=True` for exactly that reason,
      and `model_post_init` below re-wires it from this side after a decode,
      the one direction that does not close a loop.
    - `KeywordActivation.result` (`Any`) stays `exclude=True`. The reason is
      not that a caller promises never to dump a `Game` mid-resolution -
      nothing in this model enforces a caller's contract, and `machines/
      decisions.py`'s pause-and-replay design is exactly that, a convention
      the caller follows, not something this class can rely on. What actually
      rules a mid-flight `result` out is `Game.resolve_top`/`_resolve_top`
      (`models/game.py`): the ability is popped off `self.stack` (CR 608.2n)
      before its effect ever runs, and on an exception `_resolve_ability`'s
      `except Exception` branch discards it and calls `_before_priority()`
      without ever pushing it back onto the stack. A mid-flight ability -
      resolving cleanly or blown up partway through - therefore sits in no
      serialized field at all: not `self.stack`, not `self.pending_triggers`,
      and not `Game.resolving` either, which is itself `exclude=True` and is
      reset to `None` in `resolve_top`'s own `finally` before control ever
      returns to a caller that might dump the game. There is no path back into
      a serialized `Game` for a `KeywordActivation` that is not pre-resolution
      - not a promise, a structural fact about where the reference lives.

      One field on this class *is* serialized in an intermediate-looking
      shape, though: `applied` is a plain `bool`, not excluded, and `run_
      effect` (`machines/keywords.py`) sets it `True` *before* calling the
      keyword's effect function. A dump taken from inside that call - a
      re-entrant `game.ask`, say - would decode to an activation reading
      `applied=True` with `result` still `None`, and `run_effect`'s own early
      return (`if self.applied: return self.result`) would then treat it as
      already run and silently do nothing. Unreachable today only because of
      the same pop: nothing dumps a `Game` from inside a running effect call,
      since the ability that effect belongs to has already left every
      serialized field by the time the call starts.
    """

    division: list[int] | None = None
    """CR 601.2d's announced division, `Casting.division`'s own field mirrored
    here so `machines/effects._deal_divided_damage_shares` reads the same
    attribute off either kind of stack object - CR 602.2b: "the remainder of
    the process for activating an ability is identical to the process for
    casting a spell", which is what makes an ability's own "deals N damage
    divided as you choose among one or two targets" (Ral, Monsoon Mage's −2)
    the same CR 601.2d announcement a spell's identical wording already gets.
    `None` here (no caller announces one yet for an ability) falls through to
    `_divided_damage_shares`'s own even-split fallback, exactly as an
    un-announced spell already does."""
    target_amounts: list[int] | None = None
    """One entry per resolved target of `targets`, in the same order, for a
    "`<source>` deals `<n>` damage to `<phrase1>` and `<m>` damage to
    `<phrase2>`" instruction whose two halves name *different* amounts
    (`machines/effects._merge_split_damage_clauses`) - `CardState.target_
    amounts`'s own twin mirrored here for the identical CR 602.2b reason
    `division` already is. Unlike `division`, nothing here is a player
    announcement: the amounts are fixed by the printed card text, so this is
    computed and stamped on as resolution begins rather than carried from
    CR 601.2c/d announcement. `None` when the resolving instruction never
    named more than one amount (the ordinary single-amount case, and the
    equal-amount case, which never needed a per-target answer to begin
    with)."""
    cost_exiled_card_id: UUID | None = None
    """The id of the card exiled to pay this ability's own cost, when the
    ability's *effect* refers back to it anaphorically - Back from the
    Brink's "Exile a creature card from your graveyard and pay its mana
    cost: Create a token that's a copy of **that card**." The choice is made
    while the cost is paid (CR 601.2b/602.2b), before this object even
    exists, so there is nowhere else on the ability itself to carry it -
    unlike a target, which `machines/targeting.py` already tracks through
    `targets`, this was never a target at all (CR 115.1 - Back from the
    Brink's own sentence never says "target")."""

    cost_exiled_card_ids: tuple[UUID, ...] = ()
    """Every card exiled to pay this ability's own cost - Corpseweft's
    "Exile one or more creature cards from your graveyard", whose effect
    counts them: "where X is twice the number of cards exiled this way". The
    plural twin of `cost_exiled_card_id` (which names the one card an
    effect acts on), filled by `Game.activate_ability` from the paid
    payment (CR 602.2b)."""

    cost_sacrificed_card_ids: tuple[UUID, ...] = ()
    """The ids of the permanents sacrificed to pay this ability's own cost,
    when the ability's *effect* asks a question about them - Witch's Oven's
    "Create a Food token. If **the sacrificed creature's** toughness was 4 or
    greater, create two Food tokens instead."

    The sacrifice twin of `cost_exiled_card_id`, and there for the identical
    reason: CR 602.2b pays an activated ability's costs as it is activated,
    so by the time this object exists the permanent is already in a graveyard
    (CR 701.21a) and there is nothing on the battlefield to look at. It was
    never a target either - CR 115.10a: "Just because an object or player is
    being affected by a spell or ability doesn't make that object or player a
    target of that spell or ability", and Witch's Oven's sentence never says
    "target" - so `targets` is not where it can live.

    A tuple rather than a single id because a printed cost may sacrifice more
    than one permanent; every printing in the pool sacrifices exactly one."""

    cost_sacrificed_mana_values: tuple[float, ...] = ()
    """`cost_sacrificed_card_ids`' mana values, aligned by position and taken
    by `Game.activate_ability` as this object is created - CR 608.2h's last
    known information for Prime Speaker Vannifar's "the sacrificed
    creature's mana value". The id alone cannot answer it once a sacrificed
    token has ceased to exist (CR 704.5d), which happens before this ability
    resolves; see `CastRecord.additional_cost_mana_values`, its spell twin."""

    unless_payment: "CostPayment | None" = Field(default=None, repr=False)
    """The `machines/cost.CostPayment` made for an "unless that player pays" clause.

    CR 702.21a's ward is the one ability of this shape the engine produces:
    "counter that spell or ability unless that player pays [cost]". The cost is
    paid *as the ability resolves*, so the payment has to live on the ability
    that is on the stack - **the object that is paid must be the object that
    resolves**. `machines/keywords.WardTrigger` is the view that opens it and
    `machines/keywords._ward_effect` is what reads it back.

    Option (a) of the two the serialization task offered - reduced to data,
    not refused. `_ward_effect` (`machines/keywords.py`) only ever reads
    `ward_was_paid`, which is `payment.step is CostStep.PAID` - never
    `payment.game` - so *counters or lets through* needs nothing more than
    what was serialized here.

    Resuming a *paused* payment is a different question, though, and an
    earlier version of this note answered it wrong by not asking it at all: it
    said every other field on `CostPayment` - "`cost`, `components`, `pool`,
    `step`, `tapped_for_mana`, and the rest" - was "already plain pydantic
    data with no callable or live object among them", and that a persisted
    `unless_payment` is always terminal (`None`, `PENDING` with nothing tapped
    yet, or settled `PAID`) so none of that mattered anyway. Both halves were
    wrong. `tapped_for_mana` held live `CardState`s by reference until it was
    reduced to `list[UUID]` (`machines/cost.py`) - a full duplicate permanent
    on every dump, and untapping those decoded copies on `rewind` silently
    left the real battlefield sources tapped forever. And a `CostStep.PENDING`
    payment mid-tapping - the exact shape ward is opened in, one priority pass
    before anyone decides whether to pay - round-trips identically to a
    finished one, so "always terminal" was never true either; resuming it
    needs `game` back to find its own tapped sources, seed its payer's pool,
    and keep tapping, which is why `Game.model_post_init` now relinks `.game`
    on both `keyword_activation.payment` and this field. `CostComponent.cards`
    still holds `CardState`s by reference too (ward itself never uses one, but
    `unless_payment`'s type does not rule one out for some future non-mana
    ward cost) - safe because the one place that both mutates through a
    captured reference and can run after a decode, `CostComponent.unpay`,
    re-resolves each one through `game.find_by_id` first. And two more pieces
    of this class's state genuinely do not survive a round trip at all:
    `CostComponent._undo` and `CostPayment._preexisting`
    are `PrivateAttr`s, so a decoded payment's `rewind`/`unpay` now refuse
    loudly rather than silently restoring nothing when that state is gone -
    see both methods' own docstrings.
    """

    def model_post_init(self, _context: object) -> None:
        """Re-close the `KeywordActivation.on_stack` loop `exclude=True` opened.

        `keyword_activation.on_stack` is excluded from serialisation so a dump
        does not chase `self -> keyword_activation -> on_stack -> self`
        forever; this is the one direction that puts the edge back without
        recreating that cycle, run after both live construction (`_activate_
        impl` already assigns `self.on_stack = AbilityOnStack(...,
        keyword_activation=self)`, so this only repeats what it just did) and
        `model_validate` decoding a dump (where nothing else would ever set it
        again). `KeywordActivation.game` is not relinked here - only `Game`
        itself has the reference to relink it with, so `Game.model_post_init`
        does that half, the same way it already relinks `Player.game`.
        """
        if self.keyword_activation is not None:
            self.keyword_activation.on_stack = self

    @property
    def name(self) -> str:
        """A readable name, so a stack listing reads the same for both kinds."""
        return f"{self.source_name}'s {self.kind.value} ability"

    @property
    def is_ability(self) -> bool:
        return True

    @property
    def is_permanent(self) -> bool:
        """An ability never becomes a permanent, whatever its source was."""
        return False

    @property
    def zone(self) -> Zone:
        return Zone.STACK

    def source(self, game: "Game") -> CardState | None:
        """The object that generated this ability, if it is still findable (CR 113.7)."""
        if self.source_id is None:
            return None
        return game.find_by_id(self.source_id)

    def source_or_last_known(self, game: "Game") -> CardState | None:
        """The source if it can still be found, otherwise its last known
        information (CR 113.7a, CR 608.2h), or None when there is neither."""
        return self.source(game) or self.source_last_known


def tapped_for_mana_event(
    source: CardState,
    game: "Game | None" = None,
    mana_added: "Sequence[Color] | None" = None,
) -> GameEvent:
    """CR 106.12a: this permanent's mana ability just resolved and produced mana.

    Built once and reused by every place the engine taps something for mana -
    `machines/cost.CostPayment.tap_for_mana` (tapping a land to pay a total
    cost) and `Game.activate_ability`'s mana-ability fast path (CR 605.3b: the
    ability itself never reaches the stack, but the event still happens) -
    so the two call sites cannot drift apart on what the event looks like.

    `game`, when given and `source` is still on the battlefield, reads
    `subject_types`/`subject_subtypes` off `Game.characteristics_of`
    (CR 613.5) rather than `CardState.types` - a land a continuous effect has
    turned into a creature (Badgermole Cub's own earthbend, Karn's animation)
    is only a Creature on the *computed* board; `CardState.types` is up-face
    aware (CR 712.8f) but knows nothing about layers, and reading it here
    would leave "whenever you tap a creature for mana" blind to exactly the
    land its own controller just animated. Falling back to
    `source.types`/`.subtypes` without a `game`, or once `source` has left the
    battlefield, keeps every existing caller working: Tinder Farm's own
    "{T}, Sacrifice this land: Add {R}{W}" pays its sacrifice before this event
    is emitted (CR 601.2h/602.2's cost is paid in full before the ability
    resolves and produces this event), so the computed board built from the
    *current* battlefield never has it to ask - `computed_board()` only knows
    about permanents still there (CR 613.5's "objects" are the ones on it).
    """
    on_battlefield = game is not None and source.zone is Zone.BATTLEFIELD
    if on_battlefield:
        characteristics = game.characteristics_of(source)
        types = characteristics.types
        subtypes = characteristics.subtypes
    else:
        types = source.types
        subtypes = source.subtypes
    return GameEvent(
        event=TriggerEvent.TAPPED_FOR_MANA,
        subject_id=source.id,
        subject_name=source.name,
        subject_controller=source.controller,
        subject_card=source.card,
        subject_types=types,
        subject_subtypes=subtypes,
        mana_added=tuple(mana_added or ()),
    )


def triggered_mana_count(
    game: "Game", phrase: str, controller: str, source: "CardState | None" = None
) -> int:
    """How many times a triggered mana ability's "for each <phrase>" adds its
    mana, counted now (CR 608.2h: "the answer is determined only once, when
    the effect is applied"), off the computed board (CR 613.5). An unread
    phrase counts 0, adding nothing.

    `source` is the ability's own permanent (CR 113.7a: found by id,
    whatever zone it is in now) - Gardenize's own "charge counter on this
    enchantment" (CR 122.1) counts nothing on the board at all, only what is
    already on that one object, so it is checked first and short-circuits
    the board scan entirely when it matches. `None` for a caller with no
    source to hand (there is none in the pool that both needs one and is
    reached without a live `AbilityOnStack`/`CardState` in scope), which
    reads as 0 rather than guessing.
    """
    self_counter_kind = self_counter_mana_count(phrase)
    if self_counter_kind is not None:
        return max(source.counter_count(self_counter_kind), 0) if source is not None else 0
    parsed = parse_mana_count(phrase)
    if parsed is None:
        return 0
    scope, card_type, subtype = parsed
    board = game.computed_board()
    total = 0
    for permanent in game.battlefield:
        characteristics = board.of(permanent)
        if scope == "you_control" and characteristics.controller != controller:
            continue
        if (
            card_type is not None
            and card_type in characteristics.types
            or subtype
            and any(word.lower() == subtype.lower() for word in characteristics.subtypes)
        ):
            total += 1
    return total


def triggered_mana_recipient(
    recipient: str, controller: str, event: "GameEvent | None"
) -> str | None:
    """Whose pool a triggered mana ability's mana goes to (CR 605.1b).

    "add" is the ability's own controller; "its controller" is the controller
    of the permanent the event is about - the land that was tapped, which for
    an Aura's "enchanted land" is the enchanted one; "that player" is the
    player the condition named, falling back to that same permanent's
    controller.
    """
    if recipient == "controller":
        return controller
    if event is not None:
        if recipient == "that_player" and event.player is not None:
            return event.player
        if event.subject_controller is not None:
            return event.subject_controller
    return None


def mana_added_event(
    source: CardState, game: "Game | None" = None, mana_added: "Sequence[Color] | None" = None
) -> GameEvent:
    """An ability of `source` just caused its controller to add mana.

    Distinct from `tapped_for_mana_event`: CR 106.12 defines "tap for mana" as
    activating a mana ability "that includes the {T} symbol in its activation
    cost", so a condition about *tapping* (Leyline of Abundance's "Whenever you
    tap a creature for mana") is not the same question as one about *adding*
    (Caged Sun's "Whenever a land's ability causes you to add one or more mana
    of the chosen color"). Only the second is matched against this event, which
    is why a triggered mana ability's own addition re-raises this one and never
    the tap.

    Types are read off `Game.characteristics_of` (CR 613.5) while the source is
    still on the battlefield, exactly as `tapped_for_mana_event` does and for
    the same reason: "a **land's** ability" is a question about the computed
    type line, which is how Toph, the First Metalbender's static ability can
    make Caged Sun's own trigger answer it.
    """
    on_battlefield = game is not None and source.zone is Zone.BATTLEFIELD
    if on_battlefield:
        characteristics = game.characteristics_of(source)
        types = characteristics.types
        subtypes = characteristics.subtypes
    else:
        types = source.types
        subtypes = source.subtypes
    return GameEvent(
        event=ExtraTriggerEvent.MANA_ADDED,
        subject_id=source.id,
        subject_name=source.name,
        subject_controller=source.controller,
        subject_card=source.card,
        subject_types=types,
        subject_subtypes=subtypes,
        mana_added=tuple(mana_added or ()),
    )


def is_ability(item: Any) -> bool:
    """True for a stack object that is an ability rather than a spell."""
    return isinstance(item, AbilityOnStack)


# --------------------------------------------------------------------------
# Matching an event against printed trigger conditions
# --------------------------------------------------------------------------

#: The non-type words modern templating also uses to mean "this object
#: itself" - CR 608.2b's own "spell" for an object on the stack, CR 110.1's
#: "permanent", and "card"/"token", none of which is one of CR 205.2a's card
#: types (`Type`) or a printed subtype (`subtype_vocabulary`) but every one
#: of which still names the source and nothing else.
_SELF_REFERENCE_EXTRA_WORDS = frozenset({"permanent", "spell", "card", "token"})


@cache
def _self_reference_type_words() -> frozenset[str]:
    """Every word "this " can be followed by and still mean *itself*
    (CR 700.7, CR 201.5c) - not a fixed list of examples the way
    `_SELF_PHRASES` used to be, which had no entry for Smuggler's Copter's
    own "this Vehicle" (CR 205.3g) until this file was told to add one card
    at a time. Built instead from the same data every other subtype reader
    in this codebase already shares: CR 205.2a's card types (`Type`) and
    every printed CR 205.3 subtype (`subtype_vocabulary`, the flat artifact/
    battle/creature/enchantment/land/planeswalker/spell-type set `layers.py`
    and `replacement.py` already read off `data/subtypes.json`), plus the
    handful of non-type self-reference words `_SELF_REFERENCE_EXTRA_WORDS`
    names. A card's own subtype line is never consulted here - the point of
    reading "this Vehicle" as self-referential is that it is CR 700.7's
    templating convention for *any* Vehicle naming itself, not a fact about
    one particular printing.
    """
    return (
        frozenset(member.value for member in Type)
        | subtype_vocabulary()
        | _SELF_REFERENCE_EXTRA_WORDS
    )


#: "this " followed by the word(s) that say what it is - one word ("this
#: artifact") or CR 205.3m's own two-word creature type ("this Time Lord").
#: Matched here and checked against `_self_reference_type_words` rather than
#: matched by a fixed alternation, so a *new* subtype needs no edit to this
#: file, and "this way"/"this turn"/"this ability" - none of them a type or
#: subtype word - are never mistaken for a self-reference the way a bare
#: "this " substring test would read them.
_SELF_REFERENCE_WORD_RE = re.compile(r"\bthis ([a-z]+(?: [a-z]+)?)\b")


def _has_self_reference_type_word(condition: str) -> bool:
    """Whether `condition` (already lowercased by the caller) names its own
    source through "this `<type or subtype word>`" (CR 700.7).

    `_SELF_REFERENCE_WORD_RE` greedily grabs up to two words after "this ",
    to catch a two-word subtype ("this Time Lord") - so a condition whose
    "this `<word>`" is immediately followed by another word of its own
    ("this Vehicle attacks") is checked both as that two-word span and, when
    the span itself names nothing, as its first word alone; either reading
    naming a type or subtype word is enough.
    """
    words = _self_reference_type_words()
    for match in _SELF_REFERENCE_WORD_RE.finditer(condition):
        phrase = match.group(1)
        if phrase in words:
            return True
        first_word = phrase.split(" ", 1)[0]
        if first_word in words:
            return True
    return False


_TYPE_WORDS: dict[str, Type] = {
    "artifact": Type.ARTIFACT,
    "creature": Type.CREATURE,
    "enchantment": Type.ENCHANTMENT,
    "instant": Type.INSTANT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "sorcery": Type.SORCERY,
    "battle": Type.BATTLE,
}

#: "At the beginning of [your] upkeep" and friends, mapped onto the turn machine.
#: Ordered longest-phrase-first so "end step" is not mistaken for "step".
_STEP_PHRASES: tuple[tuple[str, Step], ...] = (
    ("end step", Step.END_STEP),
    ("upkeep", Step.UPKEEP),
    ("draw step", Step.DRAW),
    ("untap step", Step.UNTAP),
    ("precombat main phase", Step.PRECOMBAT_MAIN),
    # CR 505.1: "the first main phase (also known as the precombat main
    # phase)" - Static Prison's own "the beginning of your first main phase"
    # is this same phase under its other name, not a step this table was
    # missing a mapping for.
    ("first main phase", Step.PRECOMBAT_MAIN),
    ("postcombat main phase", Step.POSTCOMBAT_MAIN),
    # CR 505.1: "the first main phase (also known as the precombat main
    # phase) and the second main phase (also known as the postcombat main
    # phase)" - Kona, Rescue Beastie's own *survival* trigger says "your
    # second main phase", which is the same phase under its other name.
    # CR 505.1a's corner ("All other main phases are postcombat main phases.
    # This includes the second main phase of a turn in which the combat phase
    # has been skipped") does not arise here: this engine's turn machine has
    # exactly the two main phases CR 500.1 lists.
    ("second main phase", Step.POSTCOMBAT_MAIN),
    ("combat", Step.BEGINNING_OF_COMBAT),
)


class TriggerReadability(StrEnum):
    """Whether a printed condition is one of the shapes this module can read."""

    READ = "read"
    UNREAD = "unread"


#: Chalice of the Void's shape: "a player casts a spell with mana value equal
#: to the number of charge counters on this artifact". Read here rather than
#: left to `_types_match`'s "no type word means anything matches" default,
#: which would otherwise make Chalice counter every spell cast regardless of
#: mana value - the counter-count comparison is the entire point of the card.
_MANA_VALUE_EQUALS_COUNTERS = re.compile(
    r"with mana value equal to the number of (?P<kind>[a-z]+) counters on "
)


def _is_legendary_source(source: CardState) -> bool:
    """Whether `source`'s own printed card carries CR 205.4a's Legendary
    supertype - the printed fact `self_reference_names`' epithet and
    bare-two-word shortenings are gated on, not the computed board (CR
    613.5): Oracle's own shortened-self-reference convention is a property
    of how a card is *templated*, fixed at print time, not something a
    continuous effect making a permanent legendary this turn should turn on
    for it.
    """
    card = getattr(source, "card", None)
    return card is not None and Supertype.LEGENDARY in card.supertypes


def _self_referential(condition: str, source_name: str, *, legendary: bool = True) -> bool:
    """Whether `condition` refers to its own source (CR 700.7, 201.5, 201.5c) -
    "this creature"/"this permanent" and friends, or the source's own name in
    any of the shortened forms `machines/abilities.self_reference_names`
    reads: the short form before a comma ("Whenever Ragavan deals..."), and -
    only for a legendary source (`legendary`, default `True` for a caller
    with no supertype to check) - a no-comma legend's own epithet short form
    (Kiora of Fire and Ashes' own "When Kiora enters" - CR 201.5's short name
    of a no-comma "of" legend, not read as self before this) and a bare
    two-word name's own short form (Ajani Resolute's own "Ajani") - see
    `self_reference_names`'s own docstring for why those two shapes are a
    legendary-only convention.

    Reads through `self_reference_pattern`'s shared, word-bounded,
    longer-name-guarded regex rather than a plain substring test, so a
    shortened candidate that happens to be the start of a *different*,
    longer capitalized name mentioned in the same condition is never
    mistaken for this source naming itself.
    """
    lowered = condition.lower()
    if _has_self_reference_type_word(lowered):
        return True
    # Case-sensitive, like `self_normalized_effect_text`'s own substitution:
    # Oracle templating always spells a card's own name (and its shortened
    # forms) with the same capitalization it prints on the card, which is
    # also what `_LONGER_NAME_CONTINUATION_LOOKAHEAD`'s capital-letter check
    # needs to tell a genuine continuation apart from an ordinary lowercase
    # word - folding the whole search case-insensitive would blind that
    # lookahead to the difference.
    return any(
        re.search(self_reference_pattern(name), condition) is not None
        for name in self_reference_names(source_name, legendary=legendary)
    )


def _plural_type_word_pattern(word: str) -> str:
    """`word`'s own singular-or-plural regex fragment (CR 205.2a's card
    types, pluralized the ordinary English way Scryfall's own oracle text
    already uses: "creature" -> "creatures", "sorcery" -> "sorceries").

    Gardenize's and Scavenger's Talent's own "Whenever a/one or more
    creature**s** you control di**e**" both name the type in the plural -
    `\bcreature\b`'s trailing word boundary refuses to match inside
    "creatures" at all (the 's' is a word character, not a boundary), so a
    condition naming a type only in its plural form was read as naming no
    type, which `_types_match` then reads as "no restriction" rather than
    "the source doesn't have to be a creature to match" - the wrong kind of
    permissive for a noncreature source to widen past CR 603.10a's
    "another"/"other" requirement on. `-y` words (only "sorcery" in this
    pool's `_TYPE_WORDS`) pluralize by swapping the 'y' for '-ies', same as
    English; everything else just takes a trailing 's'.
    """
    if word.endswith("y"):
        return f"{word[:-1]}(?:y|ies)"
    return f"{word}s?"


def _required_types(condition: str) -> tuple[set[Type], set[Type]]:
    """The types a condition asks the subject to have, and the ones it forbids.

    `"an instant or sorcery spell"` requires one of instant or sorcery;
    `"a noncreature spell"` forbids creature. A condition naming no type at all
    requires nothing, which is what "whenever you cast a spell" means. Reads
    either the singular or the plural form of each type word (`_plural_type_
    word_pattern`) - "one or more creatures die" is exactly as much a
    creature-type restriction as "a creature dies" is.
    """
    lowered = condition.lower()
    forbidden = {
        card_type
        for word, card_type in _TYPE_WORDS.items()
        if re.search(rf"\bnon-?{_plural_type_word_pattern(word)}\b", lowered)
    }
    required = {
        card_type
        for word, card_type in _TYPE_WORDS.items()
        if card_type not in forbidden
        and re.search(rf"\b{_plural_type_word_pattern(word)}\b", lowered)
    }
    return required, forbidden


def _types_match(types: tuple[Type, ...] | None, condition: str) -> bool:
    """Whether `types` satisfies a condition's type words (CR 712.8f).

    Takes the subject's *actual* types - `GameEvent.subject_types`, up-face
    aware - rather than a raw `Card`, whose `.types` reads the front face only
    (CR 712.8a) and is wrong for an MDFC on the battlefield for its back face.
    """
    required, forbidden = _required_types(condition)
    if types is None:
        return not required and not forbidden
    type_set = set(types)
    if forbidden & type_set:
        return False
    return not required or bool(required & type_set)


#: "one or more other Cats you control die" names a creature *subtype*
#: (CR 205.3m), not one of `_TYPE_WORDS`'s card types. Captured non-greedily
#: so "Cats" yields "Cat" rather than swallowing the trailing "s".
_OTHER_SUBTYPE = re.compile(r"\bother ([A-Za-z]+?)s?\s+you control\b", re.IGNORECASE)

#: "that targets only a single creature [you control | other than
#: `<self-reference>`]" - Frontline Heroism's own "you control" and Ivy,
#: Gleeful Spellthief's own "other than Ivy" are the identical CR 601.2c
#: target-count restriction (CR 115.3's exactly-one) with two different
#: qualifiers on *which* single creature counts, read by one template rather
#: than a card-specific reader for each - see `condition_matches`'s
#: `CAST_SPELL` branch for why either has to be stripped before `_types_match`
#: sees it. The "you control" half needs no card name and stays a fixed
#: module-level pattern; the "other than" half is built per-source
#: (`_targets_only_single_creature_other_than_re`), the same reason
#: `_self_referential` cannot be a fixed pattern either - it has to recognise
#: *this* card's own self-reference forms (`self_reference_names`), never a
#: hardcoded name.
_TARGETS_ONLY_SINGLE_CREATURE_CLAUSE = re.compile(
    r"that targets only a single creature you control", re.IGNORECASE
)


def _targets_only_single_creature_other_than_re(
    source_name: str, *, legendary: bool = True
) -> re.Pattern[str]:
    """ "that targets only a single creature other than `<self-reference>`" -
    Ivy, Gleeful Spellthief's own shape, built for `source_name`'s own
    self-reference forms rather than a literal name: the mechanic is "other
    than itself", never "other than Ivy" as a hardcoded string, so a
    differently-named card printing the identical template is read the same
    way.
    """
    alternatives = "|".join(
        self_reference_pattern(name)
        for name in self_reference_names(source_name, legendary=legendary)
    )
    return re.compile(
        rf"that targets only a single creature other than\s+(?:{alternatives})",
        re.IGNORECASE,
    )


#: Danitha, Spear of Agony's own "a spell that targets an opponent or a
#: creature an opponent controls" and Danitha, Sword of Hope's own "a spell
#: that targets a creature you control" (CR 601.2c) - a general "that
#: targets `<restriction>`" tail on a CAST_SPELL condition, read *after*
#: `_TARGETS_ONLY_SINGLE_CREATURE_CLAUSE` has already taken Frontline
#: Heroism's own narrower "that targets only a single creature you control"
#: out of the text, so the two clauses can never both match the same
#: condition - Frontline Heroism's own count-and-controller reading of its
#: target (CR 115.3) stays exactly as it was; this is the general shape for
#: every other restriction a "spell that targets ..." condition can name.
_SPELL_THAT_TARGETS_RE = re.compile(r"\bthat targets (?P<target>.+)$", re.IGNORECASE)

#: Where a CAST_SPELL condition names more than one kind of qualifying spell
#: (Danitha, Sword of Hope's own "an Equipment spell or a spell that targets
#: a creature you control") splits: an " or " immediately followed by
#: another complete "[a/an] ... spell" or "a spell that targets ..." clause,
#: never an " or " sitting *inside* one description's own noun list (a
#: colour list, a target restriction's own "an opponent or a creature an
#: opponent controls") - the lookahead only fires when a fresh clause
#: actually starts at that exact position, which a bare colour or noun
#: alternative never does.
_CAST_CLAUSE_BOUNDARY = re.compile(r"\s+or\s+(?=an?\s+.*?\bspell\b)", re.IGNORECASE)

#: The shared lead-in every CAST_SPELL condition in this pool begins with
#: (CR 601.2) - `_cast_spell_alternatives` re-prefixes it onto every
#: alternative clause it splits off, so `_controller_clause_holds` still
#: sees who has to have done the casting in each one.
_CAST_LEAD = re.compile(r"^(?P<lead>(?:you|an opponent) casts?)\s+", re.IGNORECASE)


def _cast_spell_alternatives(condition: str) -> list[str]:
    """`condition` split into its alternative spell-description clauses when
    it names more than one kind of qualifying spell, each carrying its own
    copy of the shared "you cast"/"an opponent casts" lead-in - or `[condition]`
    unchanged, its own one and only alternative, when there is no such split
    (every CAST_SPELL condition in the pool but Danitha, Sword of Hope's)."""
    lead_match = _CAST_LEAD.match(condition)
    if lead_match is None:
        return [condition]
    lead, body = lead_match.group("lead"), condition[lead_match.end() :]
    parts = [part.strip() for part in _CAST_CLAUSE_BOUNDARY.split(body) if part.strip()]
    if len(parts) < 2:
        return [condition]
    return [f"{lead} {part}" for part in parts]


#: A leading "a"/"an" - at the very start of the restriction, or right after
#: an "or" that opens a fresh item of a noun list (Danitha, Spear of Agony's
#: own "an opponent or **a** creature an opponent controls") - is stripped
#: everywhere it introduces a noun, not only the first: `machines/targeting.
#: _read_phrase`'s own grammar reads a "target ..." phrase, or one item of
#: its own noun list, with no article at all (CR 601.2c's own templating
#: never prints one), and a lone leading strip used to leave the *second*
#: item's own article behind, which that grammar could not read either.
_LEADING_ARTICLE = re.compile(r"(^|\bor\s+)(?:a|an)\s+", re.IGNORECASE)


def _strip_leading_article(text: str) -> str:
    """`text` with every list-item-introducing "a"/"an" removed - see
    `_LEADING_ARTICLE`."""
    return _LEADING_ARTICLE.sub(r"\1", text.strip())


def _cast_spell_targets_condition_holds(
    game: "Game", target_text: str, controller: str, event: GameEvent
) -> bool | None:
    """Whether a CAST_SPELL condition's own "... that targets
    `<restriction>`" clause (CR 601.2c) is satisfied by the spell `event`
    names - true when at least one of the spell's own announced targets fits
    the restriction. `None` when the restriction cannot be read at all, so
    the caller can record a `CastConditionNotice` the same way an unreadable
    mana-value comparison already does, rather than silently treat an
    unreadable restriction as satisfied.

    Reuses `machines/targeting._read_phrase` - the identical grammar a
    "target `<description>`" phrase on the spell itself is read with - so a
    restriction here and an ordinary targeting requirement can never disagree
    about what "a creature you control" means. Imported at call time: `.
    targeting` imports `.combat`, which imports this module for `GameEvent`,
    so the two cannot import each other at module scope.
    """
    from .targeting import _read_phrase

    requirement = _read_phrase("", _strip_leading_article(target_text), strict=True)
    if requirement is None:
        return None
    if event.subject_id is None:
        return False
    spell = game.find_by_id(event.subject_id)
    if spell is None:
        return False
    for target_ref in spell.targets:
        candidate: Any
        if target_ref.is_player:
            candidate = target_ref.username
        else:
            found = game.find_by_id(target_ref.card_id)
            if found is None:
                continue
            candidate = found
        if requirement.rejects(candidate, controller, game, source_id=spell.id) is None:
            return True
    return False


def _required_subtype(condition: str) -> str | None:
    match = _OTHER_SUBTYPE.search(condition)
    if match is not None:
        return match.group(1)
    return _required_dying_subtype(condition)


#: A subtype named as a DIES condition's own plain subject (CR 205.3m,
#: CR 712.8f), outside the "other `<X>`s you control" shape `_OTHER_SUBTYPE`
#: already reads - Ygra, Eater of All's own "a Food is put into a graveyard
#: from the battlefield" (CR 700.4's own wording for "dies"). The same
#: capitalization discriminator `_ENTERING_SUBTYPE` already relies on: Oracle
#: templating capitalizes a subtype and never a card-type word, so "a
#: creature dies" (no subtype at all) and "a nontoken creature you control
#: dies" (Lightning Coils - "nontoken" is lowercase and "creature" is a card
#: type, not a subtype) never match this.
_DYING_SUBTYPE = re.compile(
    r"^(?:an?|another|one or more) (?:nontoken )?(?P<subtype>[A-Z][A-Za-z]*?)(?P<plural_s>s?)"
    r"(?: you control| an opponent controls)?"
    r" (?:dies\b|die\b|is put into a graveyard from the battlefield\b|"
    r"are put into a graveyard from the battlefield\b)"
)


def _required_dying_subtype(condition: str) -> str | None:
    """The subtype `_DYING_SUBTYPE` names, or `None` - `_required_entering_
    subtype`'s own reading, mirrored for a DIES condition's subject rather
    than an ENTERS_THE_BATTLEFIELD one."""
    match = _DYING_SUBTYPE.match(condition.strip())
    if match is None:
        return None
    subtype, plural_s = match.group("subtype"), match.group("plural_s")
    whole = subtype + plural_s
    from .layers import BASIC_LAND_TYPES

    return whole if whole in BASIC_LAND_TYPES else subtype


#: "a Mountain you control enters" (Valakut, the Molten Pinnacle) - a *subtype*
#: named on an entry condition (CR 205.3i's land types here, but the shape is
#: subtype-generic). Capitalization is the discriminator, the same one
#: `_CAST_SUBTYPE`'s own comment relies on: Oracle templating always
#: capitalizes a subtype, and never capitalizes the card-type and colour words
#: `_types_match`/`_color_matches` already read, so "a creature you control
#: enters" and "a nonland permanent enters" cannot match this. Anchored at the
#: start so it reads the condition's *subject*, not a qualifier buried later
#: in the sentence.
#:
#: `another` sits alongside `a`/`an`/`one or more` - Miirym, Sentinel Wyrm's
#: own "another nontoken Dragon you control enters" (CR 205.3a's subtype) -
#: rather than in a second regex, because it is still the condition's subject,
#: read the identical way; self-exclusion for "another" is a separate general
#: rule `condition_matches` already applies to every ENTERS_THE_BATTLEFIELD
#: condition, not something this regex has to encode. An optional "nontoken"
#: (lowercase, so it can never itself be mistaken for the capitalized
#: subtype word right after it - Miirym's own reason to exist) sits between
#: the lead-in and the subtype for the identical reason: Miirym's subject is
#: not "a Dragon" but "another **nontoken** Dragon", and without skipping it
#: the capture would land on "nontoken" itself and fail the `[A-Z]` class.
_ENTERING_SUBTYPE = re.compile(
    r"^(?:an?|one or more|another) (?:nontoken )?(?P<subtype>[A-Z][A-Za-z]*?)(?P<plural_s>s?) "
    r"(?:you control |an opponent controls )?enters?\b"
)


#: "you tap a Swamp for mana" (Nirkana Revenant), "a Forest is tapped for mana"
#: (Vernal Bloom) - a subtype named as the tapped permanent (CR 205.3i's land
#: types). Capitalization tells it from the lowercase card-type words
#: `_types_match` reads ("a creature", "a land"), as `_ENTERING_SUBTYPE` does.
_TAPPED_SUBTYPE = re.compile(
    r"(?:\btaps? an? |^an? )(?P<subtype>[A-Z][A-Za-z]*) (?:for mana|is tapped for mana)"
)


def _required_tapped_subtype(condition: str) -> str | None:
    """The subtype a tapped-for-mana condition names, or `None`."""
    match = _TAPPED_SUBTYPE.search(condition)
    return match.group("subtype") if match else None


def _required_entering_subtype(condition: str) -> str | None:
    """The subtype an ENTERS_THE_BATTLEFIELD condition demands, or `None`.

    Split from `_required_subtype` because that one reads only the "other ...
    you control" shape CR 603.10a's death triggers print, which never matches
    an entry condition's plain "a Mountain you control enters".

    `_ENTERING_SUBTYPE`'s own optional trailing `s?` is there to turn a
    plural subject - "one or more Cats you control enter" - back into the
    singular subtype name `_subtype_matches` compares against. CR 305.5's
    "Plains" is the one basic land type this stripping corrupts: it is
    spelled with a trailing s in both its singular and plural form, so
    Koth of the Homestead's own singular "a Plains you control enters"
    used to have its captured subtype trimmed to "Plain" - a name the game
    has never printed - and its own trigger could never match a real Plains
    entering. `BASIC_LAND_TYPES` (CR 305.6) is what tells "Plains" apart
    from an ordinary pluralizable subtype rather than a hardcoded name.
    """
    match = _ENTERING_SUBTYPE.match(condition.strip())
    if match is None:
        return None
    subtype, plural_s = match.group("subtype"), match.group("plural_s")
    whole = subtype + plural_s
    # Imported here, not at module scope: `machines/combat.py` imports this
    # module for `GameEvent`, and `machines/layers.py` (where
    # `BASIC_LAND_TYPES` lives) imports `machines/combat.py` in turn - the
    # same real, call-time-only cycle `triggered_abilities_of` already routes
    # its own `from .keywords import keyword_triggered_abilities` around.
    from .layers import BASIC_LAND_TYPES

    return whole if whole in BASIC_LAND_TYPES else subtype


#: "a non-Angel creature you control dies" (Archangel Avacyn) - CR 205.3's
#: subtype, negated by a hyphenated "non-" (the capital is Oracle's own
#: subtype capitalisation, so "nontoken"/"noncreature" never match).
_NON_SUBTYPE_WORD = re.compile(r"\bnon-(?P<subtype>[A-Z][A-Za-z]*)\b")


def _excluded_subtype_absent(subtypes: tuple[str, ...] | None, condition: str) -> bool:
    """Whether the subject lacks every subtype a "non-`<Subtype>`" word in
    `condition` excludes (CR 205.3), read off the event's up-face-aware
    `subject_subtypes` the way `_subtype_matches` reads the required one."""
    excluded = {match.group("subtype").lower() for match in _NON_SUBTYPE_WORD.finditer(condition)}
    if not excluded:
        return True
    return not any(word.lower() in excluded for word in subtypes or ())


def _subtype_matches(subtypes: tuple[str, ...] | None, subtype: str | None) -> bool:
    """Whether `subtypes` names `subtype` (CR 712.8f). See `_types_match`'s
    docstring for why this reads `GameEvent.subject_subtypes`, not a raw
    `Card`."""
    if subtype is None:
        return True
    if subtypes is None:
        return False
    return any(word.lower() == subtype.lower() for word in subtypes)


#: Tetsuko Umezawa, Pursuer's own "with power or toughness 1 or less" -
#: which characteristic is not fixed to the pool's one printing (a
#: differently worded card could as easily say "power 4 or greater" or
#: "toughness 3 or less").
_POWER_OR_TOUGHNESS_QUALIFIER = re.compile(
    rf"\bwith (?P<stat>power|toughness|power or toughness) "
    rf"(?P<count>{COUNT}) or (?P<direction>less|greater|more)\b"
)


def _power_or_toughness_qualifier_holds(
    game: "Game", condition: str, subject_id: "UUID | None"
) -> bool | None:
    """Whether a trigger condition's "with power [or toughness] N or
    less/greater" qualifier (CR 208.1) is true of `subject_id` right now, or
    `None` when the condition carries no such qualifier at all - which
    `condition_matches`'s BLOCKS branch reads as "nothing to check", not as a
    refusal.

    Read off the live, computed board (CR 613.5) rather than anything the
    event snapshot carries: power and toughness are exactly the
    characteristics a static ability can still be changing the moment this
    is asked, and `GameEvent` was never meant to snapshot every one of a
    permanent's numbers."""
    match = _POWER_OR_TOUGHNESS_QUALIFIER.search(condition.lower())
    if match is None:
        return None
    if subject_id is None:
        return False
    subject = game.find_by_id(subject_id)
    if subject is None:
        return False
    threshold = parse_count(match.group("count"), article=False)
    if threshold is None:
        return None
    chars = game.characteristics_of(subject) if subject.zone is Zone.BATTLEFIELD else None
    power = chars.power if chars is not None else subject.power
    toughness = chars.toughness if chars is not None else subject.toughness
    values = [value for value in (power, toughness) if value is not None]
    if match.group("stat") == "power":
        values = [power] if power is not None else []
    elif match.group("stat") == "toughness":
        values = [toughness] if toughness is not None else []
    if not values:
        return False
    compare = operator.le if match.group("direction") == "less" else operator.ge
    return any(compare(value, threshold) for value in values)


#: "a Dragon spell", "the first Otter spell" - a subtype named on a "cast a
#: ... spell" condition (CR 205.3a). Templating always capitalizes a subtype
#: the way Scryfall's Oracle text does, which is what tells this apart from
#: the lowercase color and card-type words `_color_condition`/`_types_match`
#: already read - "a colorless spell" and "a noncreature spell" never match
#: here because "colorless" and "noncreature" are not capitalized.
_CAST_SUBTYPE_WORD = re.compile(r"\b(?:a|an)\s+([A-Z][a-z]+)\s+spell\b")


def _required_cast_subtype(condition: str) -> str | None:
    match = _CAST_SUBTYPE_WORD.search(condition)
    return match.group(1) if match else None


#: Cori-Steel Cutter's own *Flurry* shape: "you cast your second spell each
#: turn" (the ability word itself, CR 207.2c, carries no rules meaning and is
#: stripped before this text is ever seen). Unlike Alania, Divergent Storm's
#: "it's the first ... spell ... you've cast this turn" - an intervening *if*
#: read by `_first_spell_this_turn_holds`, rechecked at resolution (CR 603.4,
#: 608.2a) - this ordinal sits in the trigger condition itself (CR 603.2): the
#: ability triggers (or doesn't) once, at the moment of casting, and is never
#: revisited.
_ORDINAL_SPELL_EACH_TURN = re.compile(r"your (?P<ordinal>[a-z]+) spells? each turn")


def _ordinal_spell_this_turn_matches(
    game: "Game", condition: str, controller: str, event: GameEvent
) -> bool | None:
    """Whether `event`'s spell is exactly the controller's Nth spell cast this
    turn (CR 603.2), for "you cast your [ordinal] spell each turn". `None`,
    not False, when `condition` isn't this shape at all, so the caller can
    tell "read and false" from "not this pattern" the same way
    `_first_spell_this_turn_holds` already does for its own clause.

    `game.spells_cast_this_turn` (`Game.put_on_stack`) already holds this very
    spell by the time the CAST_SPELL event reaches here - CR 601.2a's casting
    event has already happened - so its 1-indexed position in that per-turn,
    per-controller list *is* the ordinal this clause asks about, with no
    separate counter to maintain.
    """
    match = _ORDINAL_SPELL_EACH_TURN.search(condition.lower())
    if match is None:
        return None
    ordinal = parse_ordinal(match.group("ordinal"))
    if ordinal is None:
        return False
    cast_this_turn = game.spells_cast_this_turn.get(controller, [])
    position = next(
        (
            index
            for index, state in enumerate(cast_this_turn, start=1)
            if state.id == event.subject_id
        ),
        None,
    )
    return position == ordinal


#: CR 105.2's five colors, as the adjective a "cast a ... spell" condition
#: names them with.
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def _color_condition(condition: str) -> tuple[str, frozenset[Color]] | None:
    """The color restriction a "cast a ... spell" condition names, or `None`
    when it names none at all - which is what a plain "whenever you cast a
    spell" means.

    Reads CR 105.2's whole vocabulary for an object's color: "colorless"
    (CR 105.2c, 202.2b - no colored mana symbols), "monocolored" (CR 105.2a -
    exactly one color), "multicolored" (CR 105.2b - two or more), and one or
    more of the five color adjectives named outright (Frontline Heroism's
    "red" is not this shape - it colors a token the effect creates, not the
    spell the condition restricts, so this is only ever consulted for the
    condition clause itself, never the effect that follows it).
    """
    lowered = condition.lower()
    if re.search(r"\bcolorless\b", lowered):
        return "colorless", frozenset()
    if re.search(r"\bmonocolored\b", lowered):
        return "monocolored", frozenset()
    if re.search(r"\bmulticolored\b", lowered):
        return "multicolored", frozenset()
    named = frozenset(
        color for word, color in _COLOR_WORDS.items() if re.search(rf"\b{word}\b", lowered)
    )
    if named:
        return "named", named
    return None


def _color_matches(colors: tuple[Color, ...] | None, condition: str) -> bool:
    """Whether `colors` satisfies a "cast a ... spell" condition's color
    restriction, if it has one (CR 105.2). No restriction named matches
    anything, the same "nothing required" default `_types_match` uses.
    """
    requirement = _color_condition(condition)
    if requirement is None:
        return True
    kind, named = requirement
    color_set = set(colors or ())
    if kind == "colorless":
        return not color_set
    if kind == "monocolored":
        return len(color_set) == 1
    if kind == "multicolored":
        return len(color_set) >= 2
    return bool(color_set & named)


#: The zone words a "cast a ... spell **from** [zone]" clause names -
#: Knowledge Pool's and Possibility Storm's "from their hand" (also "from
#: your hand", the singular-controller phrasing prowess-style keyword
#: expansions would use if one ever named a zone) and Appa, Steadfast
#: Guardian's "from exile" are the two shapes actually printed in the pool
#: (grepped across `tests/fixtures/cards/*.json` rather than guessed), but
#: the word list is zone-generic so a future graveyard- or library-scoped
#: cast trigger reads correctly with no further parser work. "Exile" takes no
#: possessive ("from exile", never "from your exile" - exile is a shared
#: zone, CR 400.1: "Each player has their own library, hand, and graveyard.
#: The other zones are shared by all players."), so it is matched on its own
#: rather than through the
#: `their|your|his or her` possessive `_CAST_ORIGIN_ZONE_RE` group the other
#: four zones share.
_CAST_ORIGIN_ZONE_WORDS: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "battlefield": Zone.BATTLEFIELD,
    "exile": Zone.EXILE,
}

_CAST_ORIGIN_ZONE_RE = re.compile(
    r"\bfrom (?:(?:their|your|his or her) (?P<possessive>hand|graveyard|library|battlefield)"
    r"|(?P<bare>exile))\b",
    re.IGNORECASE,
)


def _required_cast_origin_zone(condition: str) -> Zone | None:
    """The zone a "cast a ... spell from [zone]" condition restricts the cast
    to, or `None` when the condition names no origin at all - which is what a
    plain "whenever you cast a spell" means (CR 603.2: no restriction is no
    restriction).
    """
    match = _CAST_ORIGIN_ZONE_RE.search(condition)
    if match is None:
        return None
    word = (match.group("possessive") or match.group("bare") or "").lower()
    return _CAST_ORIGIN_ZONE_WORDS.get(word)


def _origin_zone_matches(origin_zone: Zone | None, condition: str) -> bool:
    """Whether a `CAST_SPELL` event's `GameEvent.origin_zone` satisfies a
    condition's "from [zone]" restriction, if it has one.

    `origin_zone is None` matches anything: every real `CAST_SPELL` event
    populates it (`Game.put_on_stack` is the only emitter), so `None` here
    means the condition asked about something this engine doesn't track
    rather than a cast this engine knows happened from nowhere - the same
    "nothing required" default `_types_match` and `_color_matches` already
    fall back to, kept on the permissive side rather than refusing a
    legitimate trigger over missing data.
    """
    required = _required_cast_origin_zone(condition)
    if required is None:
        return True
    if origin_zone is None:
        return True
    return origin_zone is required


#: CR 202.3's ordinary mana-value comparisons, as a "cast a ... spell"
#: condition phrases them. Order matters: the "or greater"/"or less"/
#: "greater than"/"less than" forms are tried before the bare-number
#: equality form, since a bare `\d+` would otherwise match the leading digit
#: of "7 or greater" and read it as equality.
_MANA_VALUE_OR_GREATER = re.compile(r"mana value (?:of )?(\d+) or greater")
_MANA_VALUE_OR_LESS = re.compile(r"mana value (?:of )?(\d+) or less")
_MANA_VALUE_GREATER_THAN = re.compile(r"mana value (?:of )?greater than (\d+)")
_MANA_VALUE_LESS_THAN = re.compile(r"mana value (?:of )?less than (\d+)")
_MANA_VALUE_EQUALS = re.compile(r"mana value (?:of )?(\d+)\b")


def _mana_value_comparison(condition: str) -> tuple[int, str] | None:
    """The `(threshold, comparator)` a "with mana value ..." clause names, or
    `None` when the condition names no mana-value restriction at all.

    `comparator` is one of `">="`, `"<="`, `">"`, `"<"`, `"=="`. Chalice of the
    Void's "equal to the number of ... counters" shape is read earlier, by
    `_MANA_VALUE_EQUALS_COUNTERS`, before this is ever reached - its threshold
    is not a literal number in the condition text, so it cannot be one of
    these five.
    """
    lowered = condition.lower()
    or_greater = _MANA_VALUE_OR_GREATER.search(lowered)
    if or_greater is not None:
        return int(or_greater.group(1)), ">="
    or_less = _MANA_VALUE_OR_LESS.search(lowered)
    if or_less is not None:
        return int(or_less.group(1)), "<="
    greater_than = _MANA_VALUE_GREATER_THAN.search(lowered)
    if greater_than is not None:
        return int(greater_than.group(1)), ">"
    less_than = _MANA_VALUE_LESS_THAN.search(lowered)
    if less_than is not None:
        return int(less_than.group(1)), "<"
    equals = _MANA_VALUE_EQUALS.search(lowered)
    if equals is not None:
        return int(equals.group(1)), "=="
    return None


#: CR 506.2/508.1b: an attack on the ability's controller, or on a
#: planeswalker they control - "Whenever a creature attacks you or a
#: planeswalker you control" (Slumbering Dragon, Isperia, Circle of Flame).
#: The "you control" here is the planeswalker's, never the attacker's.
_ATTACKS_YOU_RE = re.compile(r"\battacks you(?P<planeswalker> or a planeswalker you control)?$")


def _attacks_you_holds(
    game: "Game",
    attacker_text: str,
    defended: "re.Match[str]",
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether `event`'s attack is on `controller` (or, when the condition
    says so, a planeswalker `controller` controls) by an attacker matching
    the condition's own description ("a creature without flying")."""
    defender = event.defender
    if defender is None:
        return False
    if defender.username is not None:
        attacked_you = defender.username == controller
    else:
        attacked = game.find_by_id(defender.card_id) if defender.card_id is not None else None
        attacked_you = (
            defended.group("planeswalker") is not None
            and isinstance(attacked, CardState)
            and attacked.controller == controller
            and Type.PLANESWALKER in attacked.types
        )
    if not attacked_you:
        return False
    from .targeting import permanent_description

    description = re.sub(r"^(?:a|an)\s+", "", attacker_text.strip())
    requirement = permanent_description(description)
    attacker = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    if requirement is None or not isinstance(attacker, CardState):
        return False
    return requirement.rejects(attacker, controller, game, None) is None


def _controller_clause_holds(
    condition: str, controller: str, subject_controller: str | None
) -> bool:
    """Honour "you control" / "an opponent controls" in a trigger condition.

    A condition that names neither is true for anybody, which is what
    "whenever a creature dies" means.
    """
    lowered = condition.lower()
    if "you control" in lowered or lowered.startswith("you "):
        return subject_controller == controller
    if "an opponent controls" in lowered or "your opponents control" in lowered:
        return subject_controller is not None and subject_controller != controller
    return True


#: CR 603.6d: "Some permanents have text that reads '[This permanent] enters
#: with . . . ,' 'As [this permanent] enters . . . ,' '[This permanent]
#: enters as . . . ,' or '[This permanent] enters tapped.'" - the shapes that
#: qualify *how* a permanent enters, on top of CR 603.6a's bare "enters"/
#: "enters the battlefield". When a trigger condition is itself written with
#: one of these qualifiers - Amulet of Vigor's own "Whenever a permanent you
#: control enters tapped" - the qualifier narrows the CR 603.2 event match
#: itself, checked once when the event occurs; it is not an intervening "if"
#: (CR 603.4, 608.2a) rechecked at resolution, since the condition text never
#: spells "if" for this. `Game.put_onto_battlefield` (`models/game.py`) sets
#: `card_state.tapped` and applies any entering counters *before* emitting
#: `TriggerEvent.ENTERS_THE_BATTLEFIELD` (`Game._enters_event`), so the
#: subject looked up here already carries its real entering state.
_ENTERS_TAPPED_RE = re.compile(r"\benters?\b(?:[^.]*\bthe battlefield\b)?[^.]*?\btapped\b")
_ENTERS_UNTAPPED_RE = re.compile(r"\benters?\b(?:[^.]*\bthe battlefield\b)?[^.]*?\buntapped\b")
_ENTERS_WITH_COUNTER_RE = re.compile(
    r"\benters?\b[^.]*?\bwith\s+(?:a|an|one or more|\d+)\s+"
    r"(?P<kind>[+/\-\w]+(?:[ \-][+/\-\w]+)*?)\s+counters?\s+on\s+(?:it|them)\b"
)


def _entry_qualifier_matches(game: "Game", condition: str, event: "GameEvent") -> bool:
    """Whether an "enters tapped"/"enters untapped"/"enters with a ... counter
    on it" qualifier (CR 603.6d) on an ENTERS_THE_BATTLEFIELD condition holds
    for `event`.

    A condition naming none of these qualifiers imposes none, which is what a
    bare "enters"/"enters the battlefield" already means - this returns True
    for those unconditionally, the same "nothing named, nothing required"
    default `_controller_clause_holds` and `_types_match` already use.
    """
    lowered = condition.lower()
    subject: CardState | None = None
    if event.subject_id is not None:
        subject = game.find_by_id(event.subject_id)

    if _ENTERS_TAPPED_RE.search(lowered) is not None and (subject is None or not subject.tapped):
        return False
    if _ENTERS_UNTAPPED_RE.search(lowered) is not None and (subject is None or subject.tapped):
        return False

    counter_match = _ENTERS_WITH_COUNTER_RE.search(lowered)
    if counter_match is not None:
        if subject is None:
            return False
        kind = counter_match.group("kind").strip()
        if kind not in subject.counters:
            return False

    return True


#: CR 111.1's token, read off a condition's own printed word rather than
#: assumed from a card-name table. `\b` word boundaries so `_TOKEN_WORD`
#: cannot match the "token" inside "nontoken" (a substring, not a word) - see
#: `condition_matches`'s ENTERS_THE_BATTLEFIELD and IS_SACRIFICED branches for
#: why both directions are checked, not just the false-positive one a
#: word-boundary test alone would stop.
_NONTOKEN_WORD = re.compile(r"\bnontoken\b")
_TOKEN_WORD = re.compile(r"\btokens?\b")


#: "this `<noun>` or `<other subject>` enters" - a self-or-other entry
#: condition; `other` is read like any other "`<subject>` enters" condition.
#: The self half is either CR 700.7's "this `<noun>`" or the source's own
#: name in any shortened form `self_reference_names` reads (Mabel, Valley
#: Hero's own "Whenever Mabel or another creature you control enters" -
#: CR 201.5c's short name before the comma, not "this planeswalker").
_SELF_OR_OTHER_ENTERS_TAIL = r" or (?P<other>(?:an?|another) .+ enters?)$"


def _self_or_other_enters_match(
    condition: str, source_name: str, *, legendary: bool = True
) -> re.Match[str] | None:
    generic = re.match(rf"^this [a-z]+{_SELF_OR_OTHER_ENTERS_TAIL}", condition, re.IGNORECASE)
    if generic is not None:
        return generic
    for name in self_reference_names(source_name, legendary=legendary):
        named = re.match(rf"^{self_reference_pattern(name)}{_SELF_OR_OTHER_ENTERS_TAIL}", condition)
        if named is not None:
            return named
    return None


_LEGENDARY_WORD = re.compile(r"\blegendary\b")


#: Orcish Bowmasters' "whenever an opponent draws a card except the first one
#: they draw in each of their draw steps" - CR 504.1's turn-based draw (or
#: whichever card is first drawn in that step, if that one was replaced away,
#: CR 603.2g) does not count.
_EXCEPT_FIRST_DRAW_STEP_DRAW = re.compile(
    r"\bexcept the first one (?:they|you) draws? in each of (?:their|your) draw steps\b"
)


def _is_first_own_draw_step_draw(game: "Game", player: str | None) -> bool:
    """Whether the draw being dispatched is the first card `player` has drawn
    in their own draw step this turn (`Game.cards_drawn_in_own_draw_step`,
    counted before the draw event is emitted)."""
    turn = getattr(game, "turn", None)
    if player is None or turn is None:
        return False
    if turn.step is not Step.DRAW or turn.active_player != player:
        return False
    return game.cards_drawn_in_own_draw_step.get(player, 0) == 1


def condition_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether this printed condition is matched by this event (CR 603.2).

    The shapes read, one per `TriggerEvent`:

    - **enters** (CR 603.6a) - "When this creature enters" fires for the source
      itself; "Whenever [another] [type] you control enters" fires for another
      permanent of that type. A condition additionally qualified "... enters
      tapped"/"... enters untapped"/"... enters with a[n] [kind] counter on
      it" (CR 603.6d) only matches an event whose subject actually entered
      that way - see `_entry_qualifier_matches`.
    - **dies** (CR 700.4, 603.10a) - "When this creature dies" for the source
      itself, and "Whenever another creature you control dies" / "... one or
      more other Cats you control die" for anything else that dies, optionally
      narrowed by type or subtype. The plural "die" and the spelled-out CR
      700.4 form ("is put into a graveyard from the battlefield", Flagstones
      of Trokair) are both read as this event by `_trigger_event`. Simultaneous
      deaths are not deduplicated: the engine emits one DIES event per
      permanent that dies rather than batching a single state-based-action
      sweep, so a plural "one or more ... die" condition fires once per death
      that matches rather than once per sweep the way CR 603.2c's "one event,
      multiple occurrences" reading of the printed plural would - untested
      beyond one creature dying at a time, which is what the pool exercises.
    - **leaves the battlefield** (CR 603.6c) - "When this creature leaves the
      battlefield" (Thought-Knot Seer), self-referential only in this pool:
      the generic departure, distinct from `DIES`'s graveyard-specific one,
      emitted by all three of `Game.put_into_graveyard`, `Game.exile_
      permanent`, and `Game.return_to_hand` whenever the move actually
      started on the battlefield, regardless of which of those three it
      became.
    - **attacks** (CR 508.1, 508.3d) - "Whenever this creature attacks" for the
      source, "Whenever a creature you control attacks" for any attacker under
      the same control, and "Whenever you attack" for the controller once per
      combat regardless of how many creatures were declared - the last of
      those reads a second, playerwide event `Game.declare_attackers` emits
      once per attacking player after every per-creature attack event, and
      only that shape of condition is matched against it.
    - **blocks** (CR 509.1) - only the self-referential forms, "Whenever this
      creature blocks" and "... or becomes blocked".
    - **beginning of a step** (CR 500.6) - "At the beginning of your upkeep",
      "... of each upkeep", end step, draw step, untap step, the two main
      phases, and "combat on your turn".
    - **cast** (CR 601.2) - "When you cast this spell" for the spell itself, and
      "Whenever you cast a[n] [restriction] spell" for anything that player
      casts, where the restriction can name a card type/non-type
      (`_types_match`), a subtype (`_required_cast_subtype`,
      `_subtype_matches`), a color/colorless/monocolored/multicolored
      restriction (CR 105.2, `_color_matches`), or a mana-value comparison
      (CR 202.3, `_mana_value_comparison`) - Sanctum of Ugin's "a colorless
      spell with mana value 7 or greater" is all three of the last kinds at
      once. Chalice of the Void's "mana value equal to the number of ...
      counters" is its own shape, read first and separately, since its
      threshold is not a literal number in the condition text. A mana-value
      clause that names one but whose comparison shape none of the five
      regexes read fails closed and is recorded on
      `game.cast_condition_notices` (`CastConditionNotice`) - a restriction
      genuinely present but unrecognised must never be treated as satisfied,
      the same reasoning `intervening_if_holds` already applies to an
      unreadable intervening *if*.
    - **draws a card** (CR 121.2) - "Whenever you draw a card" for the
      controller's own draws and "Whenever an opponent draws a card" for the
      others. The subject is the card drawn; the player is the one who drew it.
    - **gains life** (CR 119.9) - "Whenever you gain life" for the
      controller's own gains, "Whenever an opponent gains life" against the
      others. The player is the one who gained it.
    - **deals damage** (CR 120.1, 120.2a) - "Whenever [this] deals combat
      damage to a player" and the same "to an opponent": combat damage only,
      aimed at a player, and an opponent is one who is not the source's
      controller. Damage to a creature carries no player, so neither clause
      matches; damage with no known source matches nothing self-referential.
    - **is sacrificed** (CR 701.21a, 603.10a) - "Whenever you sacrifice a
      [type]" for what the controller sacrifices, and the self-referential
      "when this [type] is sacrificed". The subject is the permanent that went.
    - **becomes tapped / untapped** (CR 701.26a/b) - only the self-referential
      forms, "Whenever [this] becomes tapped" and "Whenever this creature
      becomes untapped".
    - **is tapped for mana** (CR 106.12, 106.12a) - "Whenever you tap a
      creature for mana" for the controller's own taps, and "Whenever
      enchanted [land] is tapped for mana" for the permanent an Aura source is
      attached to. Emitted by `machines/cost.CostPayment.tap_for_mana`, the
      only place the engine taps a permanent for mana.

    - **becomes the target** (CR 115.1, 601.2c, 602.2b) - ward's and
      Bonecrusher Giant's self-referential forms, and Loki, God of Mischief's
      general "a player or permanent becomes the target of an ability you
      control", which asks nothing about *what* was targeted and everything
      about who controls the targeting object and whether it was a spell or an
      ability (`_targeting_object_matches`).

    An ability the parser left with `event=None` is matched from its printed
    condition instead, by `_unread_condition_matches` - the counters-put,
    leaves-a-graveyard, put-into-a-library, exiled-from-a-graveyard and
    Nth-draw shapes.

    Anything else returns False. A condition this module cannot read never fires
    a trigger, which is the safe direction to be wrong in.
    """
    condition = ability.condition

    if ability.event is TriggerEvent.CAST_SPELL:
        # Danitha, Sword of Hope's own "you cast an Equipment spell or a
        # spell that targets a creature you control" (CR 601.2, two
        # independent descriptions of the cast spell joined by an ordinary
        # English "or", not a single description's own internal
        # disjunction the way "a red or green creature spell"'s colour list
        # is). `_cast_spell_alternatives` finds the boundary only where the
        # text after "or" itself starts a new "[a/an] ... spell"/"a spell
        # that targets ..." clause, so an ordinary condition with no such
        # boundary returns unchanged and falls straight through to the
        # single-clause reading below - every other CAST_SPELL card in the
        # pool is unaffected.
        alternatives = _cast_spell_alternatives(condition)
        if len(alternatives) > 1:
            return any(
                condition_matches(
                    game,
                    ability.model_copy(update={"condition": clause}),
                    source,
                    controller,
                    event,
                )
                for clause in alternatives
            )

    lowered = condition.lower()
    mine = _self_referential(condition, source.name, legendary=_is_legendary_source(source))

    if ability.event is None:
        # A condition `machines/abilities._trigger_event` could not read at
        # all. It still names a real trigger event (CR 603.1's "[trigger
        # condition or event]"), and `_unread_condition_matches` reads the
        # handful of those shapes this module knows - see
        # `_unread_trigger_events`.
        return _unread_condition_matches(game, ability, source, controller, event)

    if event.event is not ability.event:
        return False

    if ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD:
        if not _entry_qualifier_matches(game, condition, event):
            return False
        either = _self_or_other_enters_match(
            condition, source.name, legendary=_is_legendary_source(source)
        )
        if mine and either is None:
            return event.subject_id == source.id
        if either is not None:
            # "this enchantment or a legendary creature you control enters"
            # (Campsite Cuisine): the source itself, or anything that fits
            # the other half, read as its own condition below.
            if event.subject_id == source.id:
                return True
            condition = either.group("other")
            lowered = condition.lower()
        if "another" in lowered and event.subject_id == source.id:
            return False
        if _LEGENDARY_WORD.search(lowered):
            # CR 205.4a: "legendary" is a supertype, read off the computed
            # object (CR 613.5) - not a card type `_types_match` knows.
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if (
                subject is None
                or Supertype.LEGENDARY not in game.characteristics_of(subject).supertypes
            ):
                return False
        if not _controller_clause_holds(
            condition, controller, event.subject_controller
        ) or not _types_match(event.subject_types, condition):
            return False
        # A subtype named as the entry condition's subject (CR 205.3i,
        # CR 712.8f) - Valakut, the Molten Pinnacle's "Whenever a Mountain you
        # control enters". `_types_match` reads *card* types only and so
        # answers True for any permanent at all here, which let a plain Forest
        # entering fire a Mountain trigger. `GameEvent.subject_subtypes` is the
        # computed, layer-aware read (CR 613.5), so a land that is a Mountain
        # only because of Blood Moon or Dryad of the Ilysian Grove counts, and
        # one that is not does not.
        if not _subtype_matches(event.subject_subtypes, _required_entering_subtype(condition)):
            return False
        # "Whenever one or more tokens you control enter" (Caretaker's
        # Talent) - CR 111.1's token, not a card type `_types_match` already
        # reads, so it is checked separately: whatever just entered must be
        # a token, not merely a permanent of some named type.
        #
        # "nontoken" contains "token" as a substring, so a plain `"token" in
        # lowered` test used to match Weapons Manufacturing's "a nontoken
        # artifact you control enters" and Miirym's "another nontoken Dragon
        # you control enters" too - and, since the guard demanded the
        # entering permanent *be* a token, it fired those two conditions on
        # exactly the class of permanent their own text excludes. `nontoken`
        # is checked first and enforces the opposite requirement; only when
        # it is absent does a bare `\btoken\b` (word-boundary, so "nontoken"
        # itself cannot match it) ask for the Caretaker's Talent/Belladonna
        # Took shape.
        if _NONTOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or getattr(subject, "token", False):
                return False
        elif _TOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if not (subject is not None and getattr(subject, "token", False)):
                return False
        # "a creature you control with power 4 or greater enters" (Garruk,
        # Curse Breaker, CR 208.1) - the same "with power [or toughness] N
        # or less/greater" qualifier `BLOCKS` already reads for Tetsuko
        # Umezawa, Pursuer's non-self form, wired in here too rather than
        # kept BLOCKS-only: nothing about the qualifier's own grammar is
        # specific to blocking, and leaving it unread here silently dropped
        # Garruk's own filter, firing his draw on any creature at all.
        power_or_toughness = _power_or_toughness_qualifier_holds(game, condition, event.subject_id)
        return power_or_toughness is None or power_or_toughness

    if ability.event is TriggerEvent.DIES:
        if "enchanted" in lowered:
            # Ferocity of the Hunt's own "When enchanted creature dies, ..."
            # (CR 303.4b/303.4m's "enchanted [object]"), the DIES twin of
            # `TAPPED_FOR_MANA`'s own "enchanted [land]" read above -
            # `source.attached_to` is CR 603.10a's look-back: the Aura's own
            # SBA-triggered fall (CR 303.4c, CR 704.5m) has not run the
            # sweep yet at the moment this event fires, so it still names
            # the creature that just died rather than nothing.
            return event.subject_id is not None and event.subject_id == source.attached_to
        if event.subject_id == source.id:
            # Covers "When this creature dies" and the self half of
            # "Whenever this creature or another creature dies" (Blood
            # Artist) - either way the source's own death matches only if
            # the condition names itself at all.
            return mine
        # Not the source's own death: only a condition that also names
        # something else - "another"/"other" - can still match (CR 700.4,
        # 603.10a). A pure "When this creature dies" does not; a condition
        # naming no object of its own at all ("Whenever a creature dies",
        # an emblem's, Gardenize's own "Whenever a creature you control
        # dies" on an Enchantment) is about any creature, since it never
        # named itself as the one being asked about in the first place -
        # `mine` is false the moment the condition names no self-phrase and
        # no self-name (`_self_referential`), and only a condition that
        # *does* self-reference needs "another"/"other" to say "besides me
        # too" rather than "instead of me" (CR 603.10a).
        if mine and "another" not in lowered and "other" not in lowered:
            return False
        subtype = _required_subtype(condition)
        if not (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, subtype)
            and _excluded_subtype_absent(event.subject_subtypes, condition)
        ):
            return False
        # CR 111.1's token, read the identical way `ENTERS_THE_BATTLEFIELD`
        # already reads it above (Weapons Manufacturing's own "nontoken", and
        # the plain Caretaker's Talent/Belladonna Took "token" without it) -
        # this branch used to skip both, so Lightning Coils' own "a nontoken
        # creature you control dies" charged its counter off a token
        # creature's death too, exactly what "nontoken" is printed to
        # exclude.
        if _NONTOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or getattr(subject, "token", False):
                return False
        elif _TOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if not (subject is not None and getattr(subject, "token", False)):
                return False
        power_or_toughness = _power_or_toughness_qualifier_holds(game, condition, event.subject_id)
        return power_or_toughness is None or power_or_toughness

    if ability.event is TriggerEvent.TRANSFORMS:
        # CR 701.27e: "this creature transforms into `<face>`" - this object
        # turned over, and the face now up is the one named.
        named = lowered.split("transforms into", 1)[1].strip()
        return (
            mine
            and event.subject_id == source.id
            and (source.up_face_name or source.name or "").lower() == named
        )

    if ability.event is TriggerEvent.LEAVES_THE_BATTLEFIELD:
        # CR 603.6c: "When this creature leaves the battlefield" (Thought-
        # Knot Seer) is the source's own departure. "When another creature
        # you control leaves the battlefield" (Aang, at the Crossroads) is
        # anyone else's, read the way `DIES` reads its own "another"/"other"
        # widening (CR 603.10a: a leaves-the-battlefield ability looks back
        # at the object as it last existed, which the event carries).
        if event.subject_id == source.id:
            return mine
        if mine and "another" not in lowered and "other" not in lowered:
            return False
        return (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_subtype(condition))
            and _excluded_subtype_absent(event.subject_subtypes, condition)
        )

    if ability.event is TriggerEvent.ATTACKS:
        batch = batched_attackers(game, condition, controller)
        if batch is not None:
            # CR 603.2c: "one or more <description> attack" is one trigger
            # event for the whole declaration, read off `Game.declare_
            # attackers`' own subject-less event, not once per attacker.
            return (
                event.subject_id is None
                and bool(batch)
                and (event.player == controller or not _ONE_OR_MORE_ATTACK_YOURS.search(condition))
            )
        # CR 508.3d: "Whenever [a player] attacks, ..." triggers once when one
        # or more creatures that player controls are declared as attackers -
        # not once per attacker. `Game.declare_attackers` emits that as its
        # own event, with no subject, once per attacking player.
        if lowered.strip() == "you attack":
            return event.subject_id is None and event.player == controller
        if event.subject_id is None:
            return False
        # CR 506.6: Jiang Yanggu, Alone's and Yuriko, Blade of the Mighty's
        # own "attacks a player alone" - checked first since the phrase
        # contains "alone" too and would otherwise also satisfy the plainer
        # CR 506.5 branch below.
        if "a player alone" in lowered and not event.attacking_player_alone:
            return False
        # CR 506.5, Exalted's own defining shape (Agents of S.H.I.E.L.D.'s
        # "a creature you control attacks alone").
        if "a player alone" not in lowered and "alone" in lowered and not event.attacking_alone:
            return False
        defended = _ATTACKS_YOU_RE.search(lowered)
        if defended is not None:
            return _attacks_you_holds(
                game, lowered[: defended.start()], defended, controller, event
            )
        if mine:
            return event.subject_id == source.id
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

    if ability.event is TriggerEvent.BLOCKS:
        if mine:
            blocks = "blocks" in lowered and event.subject_id == source.id
            blocked = "becomes blocked" in lowered and event.related_id == source.id
            return blocks or blocked
        # Tetsuko Umezawa, Pursuer's own non-self-referential form: "a
        # creature an opponent controls with power or toughness 1 or less
        # blocks" (CR 509.1a) - the subject is the blocker, not the source,
        # so the controller/type/subtype clause is read the same general
        # way `ATTACKS`'s own non-self branch reads an attacker.
        if "blocks" not in lowered:
            return False
        if not (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_subtype(condition))
        ):
            return False
        power_or_toughness = _power_or_toughness_qualifier_holds(game, condition, event.subject_id)
        return power_or_toughness is None or power_or_toughness

    if ability.event is TriggerEvent.BEGINNING_OF_STEP:
        return _step_matches(condition, controller, event)

    if ability.event is TriggerEvent.LOYALTY_ABILITY_ACTIVATED:
        # CR 606.3. "you activate ..." (Ajani Unrelenting) - the ability's
        # own controller; "an opponent activates ..." (Gideon the Oathless)
        # - anyone but them, the same bare-"an opponent" reading `DRAWS_A_
        # CARD`/`GAINS_LIFE` already use rather than `_controller_clause_
        # holds`'s own "an opponent controls" phrasing, which this condition
        # never prints. `event.player` is whoever actually activated it
        # (`Game.activate_ability`'s own emit).
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.CAST_SPELL:
        mv_match = _MANA_VALUE_EQUALS_COUNTERS.search(lowered)
        if mv_match is not None:
            if event.subject_card is None:
                return False
            threshold = source.counters[mv_match.group("kind")]
            # CR 202.3e: on the stack, an {X} spell's mana value is the value
            # chosen for X, not the printed cost's X-as-0 reading -
            # `event.amount` is `Game.put_on_stack`'s own computation of that
            # real number (see `GameEvent.amount`'s docstring); a spell with
            # no {X} at all has `event.amount` equal to `subject_card.cmc`
            # anyway, so this is not a narrower read for the ordinary case.
            mana_value = event.amount if event.amount is not None else event.subject_card.cmc
            return mana_value == threshold
        if mine and "this spell" in lowered:
            return event.subject_id == source.id
        # Frontline Heroism's own "that targets only a single creature you
        # control" clause is stripped first (CR 115.3/109.4's own vocabulary,
        # read directly by the dedicated block near the end of this branch,
        # which still asks the *original*, unstripped `lowered` whether it is
        # present at all), so Danitha, Spear of Agony's/Danitha, Sword of
        # Hope's own general "that targets `<restriction>`" reader just below
        # never mistakes Frontline's narrower clause for a *different*
        # restriction it would have to fail closed on trying to read.
        targets_only_single_creature_you_control_match = (
            _TARGETS_ONLY_SINGLE_CREATURE_CLAUSE.search(condition)
        )
        targets_only_single_creature_other_than_pattern = (
            _targets_only_single_creature_other_than_re(
                source.name, legendary=_is_legendary_source(source)
            )
        )
        targets_only_single_creature_other_than_match = (
            targets_only_single_creature_other_than_pattern.search(condition)
        )
        without_frontline_clause = _TARGETS_ONLY_SINGLE_CREATURE_CLAUSE.sub("", condition)
        without_frontline_clause = targets_only_single_creature_other_than_pattern.sub(
            "", without_frontline_clause
        )
        target_match = _SPELL_THAT_TARGETS_RE.search(without_frontline_clause)
        target_clause = target_match.group("target").strip() if target_match is not None else None
        # `caster_condition` also serves as the type/colour/subtype checks'
        # own `type_condition` below - both need the identical text with
        # Frontline's clause and this restriction's own tail gone, so one
        # strip does for both rather than two copies of the same substitution.
        caster_condition = (
            without_frontline_clause
            if target_clause is None
            else _SPELL_THAT_TARGETS_RE.sub("", without_frontline_clause)
        )
        if "an opponent" in caster_condition.lower():
            # Jin-Gitaxias, Progress Tyrant's own "Whenever an opponent
            # casts ..." - `_controller_clause_holds` only ever recognises
            # "an opponent **controls**"/"your opponents **control**"
            # (CR 613.5's board-control question), never "casts", so a
            # condition worded this way fell through its default "nothing
            # named, nothing required" branch and matched *any* caster,
            # controller included - the same "an opponent" fallback
            # `TriggerEvent.DRAWS_A_CARD`/`GAINS_LIFE` already use just below.
            # Read off `caster_condition`, not `lowered`: Danitha, Spear of
            # Agony's own "an opponent" names her *target*, not who cast the
            # spell, and the raw text used to collide with this check the
            # identical way Frontline Heroism's own "creature" once collided
            # with the type-word scan below - refusing the caster's own cast
            # outright for a restriction that was never about the caster.
            if event.player is None or event.player == controller:
                return False
        elif not _controller_clause_holds(condition, controller, event.player):
            return False
        if not _origin_zone_matches(event.origin_zone, condition):
            return False
        if "prepared spell" in lowered:
            # CR 722.3c/722.3d, Codie, Ravenous Codex's own "Whenever you
            # cast a prepared spell, ...": a spell cast as a prepare spell -
            # the CR 722.3c exile copy itself, or (722.3d) any further copy
            # of one - is `CardState.prepare_spell_face`, the same flag its
            # own characteristics are read off.
            spell = game.find_by_id(event.subject_id) if event.subject_id is not None else None
            if spell is None or not spell.prepare_spell_face:
                return False
        if "during your turn" in lowered or "during their turn" in lowered:
            # Ral, Monsoon Mage's own condition: the cast has to have
            # happened during *this ability's controller's* own turn, not
            # merely by that controller - CR 500.1's turn structure is what
            # "your turn" points at, read off the live `TurnMachine` rather
            # than any snapshot, since the trigger is checked as the cast
            # event fires, before anything else has moved the turn along.
            turn = getattr(game, "turn", None)
            if turn is None or turn.active_player != controller:
                return False
        ordinal_match = _ordinal_spell_this_turn_matches(game, condition, controller, event)
        if ordinal_match is not None:
            return ordinal_match
        # Frontline Heroism's own clause names a type word ("creature") that
        # describes the *target*, not the cast spell itself - `_required_
        # types`/`_types_match` cannot tell the two apart on sight (it just
        # scans the whole condition for a known type word) and used to
        # misread the clause as "cast a creature spell", which Lightning
        # Bolt aimed at your own creature is not, wrongly refusing to fire
        # at all. Danitha's own "that targets ..." tail has the identical
        # problem with "opponent"/"creature you control" - both are already
        # gone from `caster_condition`, computed above.
        type_condition = caster_condition
        if not _types_match(event.subject_types, type_condition):
            return False
        if not _color_matches(event.subject_colors, type_condition):
            return False
        subtype = _required_cast_subtype(type_condition)
        if not _subtype_matches(event.subject_subtypes, subtype):
            return False
        if target_clause is not None:
            holds = _cast_spell_targets_condition_holds(game, target_clause, controller, event)
            if holds is None:
                game.cast_condition_notices.append(
                    CastConditionNotice(
                        source_id=source.id, source_name=source.name, condition=condition
                    )
                )
                return False
            if not holds:
                return False
        if (
            targets_only_single_creature_you_control_match is not None
            or targets_only_single_creature_other_than_match is not None
        ):
            # Frontline Heroism's own "you control" and Ivy, Gleeful
            # Spellthief's own "other than Ivy" - not a fact about the cast
            # spell's own printed characteristics at all (CR 105, CR 202.3),
            # but about *what it targets* (CR 601.2c), read off the spell's
            # own `CardState.targets` now that it sits on the stack. "only a
            # single" is CR 115.3's exactly-one; "creature you control" is
            # CR 109.4/608.2b's ordinary target-legality vocabulary and
            # "other than `<self-reference>`" is CR 201.5/115.5's own
            # exclusion of the source itself - both read directly here
            # rather than through `machines/targeting.py`, since this is a
            # *condition on an already-legal announcement*, not a targeting
            # requirement of the trigger source's own.
            if event.subject_id is None:
                return False
            spell = game.find_by_id(event.subject_id)
            if spell is None or len(spell.targets) != 1:
                return False
            (only_target,) = spell.targets
            if only_target.is_player:
                return False
            target = game.find_by_id(only_target.card_id)
            if target is None or target.zone is not Zone.BATTLEFIELD:
                return False
            # CR 613.5: the target's computed types, not the printed line -
            # an earthbent land (CR 701.66a) is a creature only there.
            if not game.characteristics_of(target).is_creature:
                return False
            if targets_only_single_creature_you_control_match is not None:
                if game.controller_of(target).username != controller:
                    return False
            elif target.id == source.id:
                return False
        if "mana value" in lowered:
            comparison = _mana_value_comparison(condition)
            if comparison is None:
                game.cast_condition_notices.append(
                    CastConditionNotice(
                        source_id=source.id,
                        source_name=source.name,
                        condition=condition,
                    )
                )
                return False
            threshold, comparator = comparison
            if event.amount is None:
                return False
            ops = {
                ">=": operator.ge,
                "<=": operator.le,
                ">": operator.gt,
                "<": operator.lt,
                "==": operator.eq,
            }
            if not ops[comparator](event.amount, threshold):
                return False
        return True

    if ability.event is TriggerEvent.EXILED:
        # CR 702.35a: "When this card is exiled this way". Only the
        # self-referential form is read, which is the only form madness prints;
        # the "this way" is enforced by the emitter, which raises the event only
        # for the exile the madness replacement performed.
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.BECOMES_TARGET:
        # CR 115.1: "Some spells and abilities require their controller to
        # choose one or more targets for them ... These targets are declared as
        # part of the process of putting the spell or ability on the stack"
        # (CR 601.2c for a spell, imported wholesale for an ability by
        # CR 602.2b). Two shapes are read:
        #
        # - the self-referential one, which is what ward prints (CR 702.21a,
        #   "Whenever this permanent becomes the target of a spell or ability
        #   an opponent controls") and what Bonecrusher Giant prints
        #   ("Whenever this creature becomes the target of a spell");
        # - the general one, which names no particular object: Loki, God of
        #   Mischief's "Whenever a player or permanent becomes the target of
        #   an ability you control". Nothing about *what* was targeted is
        #   asked there - "a player or permanent" is every legal target of an
        #   ability - so the whole question is who controls the targeting
        #   object and whether it is a spell or an ability.
        #
        # - the object-subject one, which names *what* was targeted by type
        #   and controller: Venerated Rotpriest's "Whenever a creature you
        #   control becomes the target of a spell". Its "you control" is the
        #   targeted object's, so only the part after "the target of" is left
        #   for the targeting object's own controller check below.
        if mine:
            if event.subject_id != source.id:
                return False
        elif (object_subject := _OBJECT_TARGET_SUBJECT.match(lowered.strip())) is not None:
            if not _targeted_object_matches(
                game, object_subject.group("subject"), event, source, controller
            ):
                return False
            lowered = object_subject.group("by")
            condition = lowered
        elif not _target_subject_matches(condition):
            return False
        if not _targeting_object_matches(game, condition, event):
            return False
        if "an opponent controls" in lowered:
            return event.player is not None and event.player != controller
        if "you control" in lowered:
            # `GameEvent.player` on a becomes-target event is the controller
            # of the spell or ability that did the targeting (that is what
            # `machines/casting.Casting` puts there), which is exactly whose
            # "you control" this asks about.
            return event.player == controller
        return True

    if ability.event is TriggerEvent.DRAWS_A_CARD:
        if _EXCEPT_FIRST_DRAW_STEP_DRAW.search(lowered) and _is_first_own_draw_step_draw(
            game, event.player
        ):
            return False
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.GAINS_LIFE:
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.DEALS_DAMAGE:
        if re.search(r"\b(?:is|are) dealt\b", lowered):
            # Passive voice reads the *recipient*, not the dealer - Hexhaven
            # Invigorator's self-referential "this creature is dealt damage"
            # and Master of Barbs'/Massacre Girl, Most Wanted's/Fblthp,
            # Impossibly Lost's "an opponent is/one or more opponents are
            # dealt [non]combat damage[, during your turn]" none of them say
            # anything about who *dealt* it, so the dealer-oriented checks
            # below (which read `subject_id`/`subject_controller`, the
            # dealer) do not apply at all; `target_id`/`player` (the
            # recipient) are read instead.
            if mine:
                if event.target_id != source.id:
                    return False
            elif "opponent" in lowered:
                if event.player is None or event.player == controller:
                    return False
            else:
                return False
            if "noncombat damage" in lowered:
                if event.combat:
                    return False
            elif "combat damage" in lowered and not event.combat:
                return False
            if "during your turn" in lowered or "during their turn" in lowered:
                turn = getattr(game, "turn", None)
                if turn is None or turn.active_player != controller:
                    return False
            return True
        # CR 120.1: "An object that deals damage is the source of that
        # damage" - the subject is the source, so the self-referential
        # form ("this creature deals damage") checks the source and the
        # general form checks the controller clause and types of whatever
        # dealt it. Damage with no known source carries neither an id nor a
        # controller and matches nothing here. The passive form ("this
        # creature is dealt damage") is caught above, before this point is
        # ever reached, through `target_id`/`player` instead.
        if mine:
            if event.subject_id != source.id:
                return False
        elif not (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
        ):
            return False
        if "combat damage" in lowered and not event.combat:
            return False
        if "to an opponent" in lowered:
            return event.player is not None and event.player != controller
        if "to a player" in lowered:
            return event.player is not None
        return True

    if ability.event is TriggerEvent.IS_SACRIFICED:
        if mine:
            return event.subject_id == source.id
        # Ashling, the Limitless: "Whenever you sacrifice a nontoken
        # Elemental, ...". "Elemental" is CR 205.3a's creature subtype, not
        # one of `_TYPE_WORDS`'s card types, so `_types_match` cannot see
        # "nontoken" at all - it has to be read the same way
        # ENTERS_THE_BATTLEFIELD's own guard reads it, off the event's actual
        # subject rather than a type word.
        if _NONTOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or getattr(subject, "token", False):
                return False
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

    if ability.event in (TriggerEvent.BECOMES_TAPPED, TriggerEvent.BECOMES_UNTAPPED):
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.BECOMES_MONSTROUS:
        # CR 701.37a. Every printing in the pool - Polukranos, World Eater;
        # Arbor Colossus - prints only the self-referential "When [this
        # creature] becomes monstrous, ...", so only that form is read, the
        # same narrowing `BECOMES_TAPPED`/`BECOMES_UNTAPPED` apply above.
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.TAPPED_FOR_MANA:
        # CR 106.12a. "Whenever enchanted Forest is tapped for mana" (Utopia
        # Sprawl) asks about the land the Aura is attached to, not the Aura
        # itself - `source.attached_to` is that land's id (CR 303.4).
        if "enchanted" in lowered:
            return event.subject_id is not None and event.subject_id == source.attached_to
        # "Whenever you tap a creature for mana" (Badgermole Cub, Leyline of
        # Abundance) - the controller's own tap, of a permanent of the named
        # type - and "you tap a Swamp for mana" (Nirkana Revenant), "a Forest is
        # tapped for mana" (Vernal Bloom), naming a land subtype instead.
        # Nothing in the pool prints the self-referential form.
        if "an opponent" in lowered:
            # Vorinclex, Voice of Hunger's own "Whenever an opponent taps a
            # land for mana, ..." - `_controller_clause_holds` only ever
            # recognises "an opponent **controls**"/"your opponents
            # **control**" (CR 613.5's board-control question), never
            # "taps", so this fell through its default "nothing named,
            # nothing required" branch and matched *any* tap, controller
            # included - the same "an opponent" fallback `TriggerEvent.
            # CAST_SPELL`/`DRAWS_A_CARD`/`GAINS_LIFE` already use for their
            # own branches.
            controller_ok = event.subject_controller is not None and (
                event.subject_controller != controller
            )
        else:
            controller_ok = _controller_clause_holds(
                condition, controller, event.subject_controller
            )
        return (
            controller_ok
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_tapped_subtype(condition))
        )

    if ability.event is TriggerEvent.TURNED_FACE_UP:
        # CR 702.37e/708.8. Brine Elemental's own "When this creature is
        # turned face up, ..." is self-referential (`mine`); Mastery of the
        # Unseen's "Whenever a permanent you control is turned face up, ..."
        # is not - it watches every permanent its controller turns face up,
        # not only itself, the same self-vs-general split every other event
        # branch in this function reads off `mine` rather than hardcoding.
        if mine:
            return event.subject_id == source.id
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

    if ability.event is TriggerEvent.DISCARDS_A_CARD:
        # Titanbones, Towering Heart's own "When you discard this card, ..."
        # - self-referential (CR 603.10a's look-back shape: the card is
        # already gone from the hand by the time this is checked), matched
        # against the whole batch a single discard instruction moved
        # (`GameEvent.discarded_ids`), since a discard fires once per
        # instruction rather than once per card. Checked ahead of the plain
        # controller-clause read below, which would otherwise treat "you
        # discard this card" as nothing narrower than "you discard".
        if mine:
            return source.id in event.discarded_ids
        # CR 701.9a. "Whenever you discard one or more cards" (Captain
        # Howler, Sea Scourge) asks about the controller's own discards -
        # `event.player` is who did the discarding, `_controller_clause_
        # holds`'s "you " prefix already reads "you discard" the same way
        # every other "you [verb]" condition does.
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.LORE_COUNTERS_ADDED:
        # CR 107.15a: always self-referential (a chapter symbol is never
        # printed any other way) and always about the Saga's own threshold,
        # not the event's raw amount - `ability.chapter` is `N`, `source.
        # lore_counters` is the total *after* `event.amount` were just put
        # on, and CR 107.15a's own "was less than N and became at least N"
        # is exactly the range `event.amount` spans.
        if event.subject_id != source.id or ability.chapter is None:
            return False
        added = event.amount or 0
        new_total = source.lore_counters
        old_total = new_total - added
        return old_total < ability.chapter <= new_total

    if ability.event is TriggerEvent.SCRY_OR_SURVEIL:
        # CR 701.22a/701.25a. "Whenever you scry or surveil" (Denzilore
        # Fatehold, Matoya, Archon Elder) is the only shape this pool prints.
        # "an opponent [verb]" is read directly - the same way `DRAWS_A_CARD`/
        # `GAINS_LIFE` read it - rather than through `_controller_clause_
        # holds`, which only recognises the "controls" phrasing ("an
        # opponent controls"), not an action verb like "scries"/"surveils".
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.LOYALTY_ABILITY_ACTIVATED:
        # CR 606.2/602.2. Ajani Unrelenting's "Whenever you activate a
        # loyalty ability" and Gideon the Oathless's "Whenever an opponent
        # activates a loyalty ability" - the subject is the permanent whose
        # ability was activated. "an opponent activates" is read the same
        # direct way `SCRY_OR_SURVEIL` just did, for the same reason: CR
        # 602.2's "activates" is not `_controller_clause_holds`'s "controls".
        if mine:
            return event.subject_id == source.id
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    return False


#: Loki, God of Mischief's own subject: "a **player or permanent** becomes the
#: target of an ability you control". The only non-self-referential
#: becomes-target subject read at all - anything else (a condition naming a
#: type, a controller, or a subtype for the *target*) is left unread, because
#: "you control" in such a condition can attach either to the target or to the
#: targeting object and reading it wrong fires a trigger that should not fire.
_ANY_TARGET_SUBJECT = re.compile(r"^(?:a player or permanent|a permanent or player)\b")


#: A becomes-target condition whose subject is an object described by type
#: and controller (CR 115.1's "object(s) ... the spell or ability will
#: affect"): "a creature you control", "another permanent an opponent
#: controls". `by` is the rest - "a spell", "a spell or ability an opponent
#: controls" - which is about the targeting object, not the targeted one.
_OBJECT_TARGET_SUBJECT = re.compile(
    r"^(?P<subject>(?:a|an|another) (?:[a-z]+ )*?"
    r"(?:creature|permanent|artifact|enchantment|land|planeswalker)"
    r"(?: you control| an opponent controls)?) becomes the target of (?P<by>.+)$"
)


def _targeted_object_matches(
    game: "Game", subject: str, event: GameEvent, source: CardState, controller: str
) -> bool:
    """Whether the object a becomes-target event names fits `subject`'s type
    and controller words, read off the computed board (CR 613.5) - the
    targeted object is a permanent, so an animated land is a creature there
    and nowhere else."""
    if event.subject_id is None:
        return False
    if subject.startswith("another ") and event.subject_id == source.id:
        return False
    targeted = game.find_by_id(event.subject_id)
    if targeted is None:
        return False
    types = (
        game.characteristics_of(targeted).types
        if targeted.zone is Zone.BATTLEFIELD
        else targeted.types
    )
    return _types_match(tuple(types), subject) and _controller_clause_holds(
        subject, controller, event.subject_controller
    )


def _target_subject_matches(condition: str) -> bool:
    """Whether a non-self-referential becomes-target condition's *subject* is
    one this module reads (CR 115.1's "object(s) and/or player(s) the spell or
    ability will affect")."""
    return _ANY_TARGET_SUBJECT.match(condition.lower().strip()) is not None


def _targeting_object_matches(game: "Game", condition: str, event: GameEvent) -> bool:
    """Whether the spell or ability that did the targeting is the kind this
    condition names.

    CR 115.1 lets either kind target, and the printed conditions distinguish
    them: ward says "a spell or ability" (CR 702.21a), Bonecrusher Giant says
    "a spell", Loki, God of Mischief says "an ability". `GameEvent.targeted_by`
    is the id of whichever it was, and CR 113.1c makes an ability on the stack
    an object with an id of its own, so the two are told apart by looking for
    that id among the abilities on the stack.

    An event with no `targeted_by` at all answers only a condition that names
    neither kind, since an unknown kind is not known to be the named one.
    """
    lowered = condition.lower()
    names_spell = "spell" in lowered
    names_ability = "ability" in lowered
    if not names_spell and not names_ability:
        return True
    if event.targeted_by is None:
        return False
    is_ability_object = any(item.id == event.targeted_by for item in game.abilities_on_stack)
    if names_spell and names_ability:
        return True
    return is_ability_object if names_ability else not is_ability_object


#: Basking Broodscale's and Emperor of Bones' condition: "one or more +1/+1
#: counters are put on this creature" (CR 122.6). The kind is captured so a
#: condition naming +1/+1 is not fired by a charge counter.
_COUNTERS_PUT_CONDITION = re.compile(
    r"^one or more (?P<kind>\S+) counters are put on (?P<subject>.+)$"
)

#: Fabrication Module's and Territorial Gorger's condition: "you get one or
#: more {E} (energy counters), ..." (CR 122.6, CR 107.14) - `machines/
#: abilities.parse_abilities` strips the parenthetical reminder before either
#: module ever sees the text, so the literal string is "you get one or more
#: {e}" with no trailing "counters" word for the mana-symbol case; a
#: spelled-out kind ("you get one or more poison counters") has no reminder to
#: strip and keeps it, which is the second branch below. `_player_counter_
#: kind` reads whichever branch matched into the plain kind string `GameEvent.
#: counter_kind` carries (CR 107.14: "the energy symbol is {E}" - the only
#: mana-symbol counter kind CR 122.1 currently names, so `{e}` is the only
#: symbol read).
_PLAYER_COUNTERS_PUT_CONDITION = re.compile(
    r"^you get one or more (?:(?P<symbol>\{e\})|(?P<kind>[a-z]+) counters?)$"
)


def _player_counter_kind(match: re.Match[str]) -> str:
    """The counter kind `_PLAYER_COUNTERS_PUT_CONDITION` matched, as the plain
    string `GameEvent.counter_kind`/`models.card_state.Counter.ENERGY` use."""
    return "energy" if match.group("symbol") is not None else match.group("kind")


#: Inspired Tethermage's "Whenever you put one or more loyalty counters on a
#: planeswalker, ..." (CR 122.6, CR 606.4) - a different shape from
#: `_COUNTERS_PUT_CONDITION` above in every way that matters: active voice
#: ("you put", not "are put"), a controller clause instead of a bare kind,
#: and "a planeswalker" - any one, not only the ability's own source - as the
#: subject rather than "this creature". CR 606.4's own "to activate a loyalty
#: ability of a permanent is to put on or remove ... loyalty counters" is
#: what makes activating a `[+N]` ability the ordinary way this fires,
#: alongside any effect that puts loyalty counters on directly.
_LOYALTY_COUNTERS_PUT_ON_PLANESWALKER_CONDITION = re.compile(
    r"^(?P<who>you put|an opponent puts) one or more loyalty counters on a planeswalker$"
)

#: Hardened Academic's "one or more cards leave your graveyard" and Murktide
#: Regent's "an instant or sorcery card leaves your graveyard" - one shape with
#: an optional type restriction (CR 603.10a's own "abilities that trigger when
#: a card leaves a graveyard").
_LEAVES_GRAVEYARD_CONDITION = re.compile(
    r"^(?:one or more cards leave|(?:an?|one) (?P<types>[a-z ]+?) card leaves) your graveyard$"
)

#: Wan Shi Tong, All-Knowing's "one or more cards are put into a library from
#: anywhere" (CR 401.1's library as a destination). "From anywhere" is every
#: other zone, so no origin is checked - and nothing that was already in the
#: library was *put into* one, which is why a scry never matches (the event is
#: simply never raised for a reorder).
_PUT_INTO_LIBRARY_CONDITION = re.compile(
    r"^one or more cards are put into a library from anywhere$"
)

#: Ketramose, the New Dawn's "one or more cards are put into exile from
#: graveyards and/or the battlefield during your turn" - one condition naming
#: two origins (CR 406.2's exile from "whatever zone it's currently in"),
#: matched against either of the two events that carry them.
_EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION = re.compile(
    r"^one or more cards are put into exile from graveyards and/or the battlefield"
    r" during your turn$"
)

#: Caged Sun's "a land's ability causes you to add one or more mana of the
#: chosen color" - CR 605.1b's triggered mana ability, watching CR 106.12a's
#: own event for the mana it now carries (`GameEvent.mana_added`). "The chosen
#: color" is CR 614.12a's as-enters choice, recorded on `CardState.choice`.
_LAND_ADDED_CHOSEN_MANA_CONDITION = re.compile(
    r"^a land's ability causes you to add one or more mana of the chosen color$"
)

#: Tamiyo, Inquisitive Student's "you draw your third card in a turn" and
#: Faerie Vandal's "you draw your second card each turn" - an ordinal over
#: CR 121.2's individual card draws, which are one event each. Both suffixes
#: mean the same turn-scoped count; "each turn" is how most printings say it.
_NTH_DRAW_CONDITION = re.compile(r"^you draw your (?P<ordinal>[a-z]+) card (?:in a|each) turn$")

#: CR 702.62a's third ability, as `machines/keywords._suspend_abilities`
#: writes it out: "the last time counter is removed from this card". Never
#: printed as a line of condition text on any card - suspend prints it as one
#: word, and the only text on Lotus Bloom that resembles it is reminder text.
_LAST_TIME_COUNTER_CONDITION = re.compile(r"^the last time counter is removed from this card$")

#: CR 702.94a's second ability, as `machines/keywords._miracle_ability` writes
#: it out: "you reveal this card this way". Miracle prints it as one word, so
#: this condition only ever arrives from that expansion.
_REVEALED_THIS_WAY_CONDITION = re.compile(r"^you reveal this card this way$")

#: Voltaic Visionary's "When you play a card exiled with this creature" - CR
#: 601.1a's "play" (a land played or a spell cast) of a card out of this
#: object's own CR 607.2a pile.
_PLAY_A_CARD_EXILED_WITH_CONDITION = re.compile(r"^you play a card exiled with this \w+$")

#: The Millennium Calendar's "you untap one or more permanents during your
#: untap step" - `ExtraTriggerEvent.UNTAPPED_DURING_UNTAP_STEP`.
_UNTAPPED_DURING_UNTAP_STEP_CONDITION = re.compile(
    r"^you untap one or more permanents during your untap step$"
)

#: A permanent returned from the battlefield to a hand - `TriggerEvent.
#: LEAVES_BATTLEFIELD_TO_HAND`, a leaves-the-battlefield event (CR 603.6c).
#: Azorius Aethermage's "a permanent is returned to your hand", Tameshi,
#: Reality Architect's "one or more noncreature permanents are returned to
#: hand", Justice, Vance Astrovik's "another nonland permanent you control is
#: returned to its owner's hand": a subject (read by `_returned_subject`),
#: whose hand, and an optional "from the battlefield" that only says out loud
#: what "permanent" already means.
_RETURNED_TO_HAND_CONDITION = re.compile(
    r"^(?P<subject>.+?) (?:is|are) returned to "
    r"(?P<hand>your hand|hand|its owner's hand|their owner's hand|their owners' hands)"
    r"(?: from the battlefield)?$"
)

#: The subject of `_RETURNED_TO_HAND_CONDITION`, split into its quantifier
#: and its description.
_RETURNED_SUBJECT = re.compile(
    r"^(?:(?P<plural>one or more)|(?P<another>another)|an?)"
    r" (?P<description>.+)$"
)
_RETURNED_CONTROLLER = re.compile(r"^(?P<types>.+?)(?: (?P<controller>you control))?$")
#: The words a returned-subject description may be built from - a card type
#: or its negation (CR 205.2a), and "permanent". Anything else (a subtype, a
#: colour, "token") is not read, so the whole condition stays unread rather
#: than matching more than it says.
_RETURNED_DESCRIPTION_WORD = re.compile(
    r"^(?:non-?)?(?:"
    + "|".join(_plural_type_word_pattern(word) for word in _TYPE_WORDS)
    + r"|permanents?)$"
)


class _ReturnedSubject(NamedTuple):
    """What `_RETURNED_SUBJECT` read: whether the condition is the plural
    "one or more" (CR 603.2c: one trigger per event), whether it excludes its
    own source ("another"), the type words, the controller clause, and whose
    hand."""

    plural: bool
    another: bool
    types: str
    controller: str | None
    hand: str


def _returned_subject(condition: str) -> _ReturnedSubject | None:
    """`condition` read as a returned-to-hand condition, or None."""
    match = _RETURNED_TO_HAND_CONDITION.match(condition)
    if match is None:
        return None
    subject = _RETURNED_SUBJECT.match(match.group("subject"))
    if subject is None:
        return None
    description = _RETURNED_CONTROLLER.match(subject.group("description"))
    if description is None:
        return None
    words = description.group("types").replace(",", " ").split()
    if not words or any(
        _RETURNED_DESCRIPTION_WORD.match(word) is None for word in words if word != "or"
    ):
        return None
    return _ReturnedSubject(
        plural=subject.group("plural") is not None,
        another=subject.group("another") is not None,
        types=" ".join(words),
        controller=description.group("controller"),
        hand=match.group("hand"),
    )


def _returned_event_described(
    read: _ReturnedSubject,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether one returned-to-hand `event` is what `read` describes, for an
    ability of `source` controlled by `controller`."""
    if event.event is not TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND:
        return False
    if read.another and event.subject_id == source.id:
        return False
    if not _types_match(event.subject_types, read.types):
        return False
    # "your hand": the hand is its owner's (CR 108.3), which the event carries
    # as `player`; "its owner's hand" and bare "hand" are anybody's.
    if read.hand == "your hand" and event.player != controller:
        return False
    # "you control": control as it last existed on the battlefield (CR
    # 603.10a's look-back), captured before the move.
    return read.controller != "you control" or event.subject_controller == controller


def _returned_to_hand_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
    read: _ReturnedSubject,
) -> bool:
    """`_RETURNED_TO_HAND_CONDITION` against one returned permanent's event.

    CR 603.10a: a leaves-the-battlefield ability looks back in time, so every
    permanent returned by the same event is asked, the source included even
    though it is already in a hand (Azorius Aethermage's ruling: it triggers
    for its own return) - `Game.returned_to_hand_batch` is that event, and a
    source off the battlefield is heard only if it is one of them.

    CR 603.2c: the singular "a permanent is returned" triggers once per
    permanent the event moved; the plural "one or more ... are returned"
    triggers once for the whole event, so only the first described permanent
    in the batch answers for it.
    """
    batch = game.returned_to_hand_batch or (event,)
    if source.zone is not Zone.BATTLEFIELD and source.id not in {
        returned.subject_id for returned in batch
    }:
        return False
    if not _returned_event_described(read, source, controller, event):
        return False
    if not read.plural:
        return True
    first = next(
        returned
        for returned in (*batch, event)
        if _returned_event_described(read, source, controller, returned)
    )
    return first.subject_id == event.subject_id


#: CR 716.2a: "[Cost]: Level N - [Abilities]" means "[Cost]: This Class's
#: level becomes N ..." - Caretaker's Talent's, Stormchaser's Talent's and
#: Wizard Class's "When this Class becomes level 2". Self-referential: the
#: level is the Class's own (CR 716.2b).
_CLASS_BECOMES_LEVEL_CONDITION = re.compile(r"^(?P<subject>.+?) becomes level (?P<level>\d+)$")

#: CR 701.67c's own words, "whenever a player waterbends", read off however
#: the condition actually names the bending verbs - a bare "you waterbend"
#: (nothing printed prints this alone yet, but CR 701.67c's rule is written
#: as though something might) or Avatar Aang's own four-way "you waterbend,
#: earthbend, firebend, or airbend" list, in any order and with any subset
#: of the four bending verbs (CR 207.2's own listing-order convention is not
#: pinned to). Every named word maps onto its own `ExtraTriggerEvent`
#: member; only `WATERBENDS` is ever actually raised (see that member's own
#: docstring), so a condition naming only the other three never fires -
#: correctly, since nothing bends that way yet.
_BENDING_WORD = r"(?:waterbend|earthbend|firebend|airbend)"
_BENDING_CONDITION = re.compile(
    rf"^you {_BENDING_WORD}(?:,\s*{_BENDING_WORD})*(?:,)?\s*(?:or\s+{_BENDING_WORD})?$",
    re.IGNORECASE,
)
_BENDING_EVENTS: dict[str, ExtraTriggerEvent] = {
    "waterbend": ExtraTriggerEvent.WATERBENDS,
    "earthbend": ExtraTriggerEvent.EARTHBENDS,
    "firebend": ExtraTriggerEvent.FIREBENDS,
    "airbend": ExtraTriggerEvent.AIRBENDS,
}


def _bending_events_named(condition: str) -> frozenset[ExtraTriggerEvent]:
    """Every bending event `_BENDING_CONDITION` names in `condition`, or an
    empty set if the condition is not that shape at all."""
    if _BENDING_CONDITION.match(condition) is None:
        return frozenset()
    words = re.findall(_BENDING_WORD, condition, re.IGNORECASE)
    return frozenset(_BENDING_EVENTS[word.lower()] for word in words)


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
    if _LAND_ADDED_CHOSEN_MANA_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.MANA_ADDED})
    if _LAST_TIME_COUNTER_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED})
    if _REVEALED_THIS_WAY_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.REVEALED_FOR_MIRACLE})
    if _UNTAPPED_DURING_UNTAP_STEP_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.UNTAPPED_DURING_UNTAP_STEP})
    if _ONE_OR_MORE_DEAL_COMBAT_DAMAGE_RE.fullmatch(lowered):
        return frozenset({ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS})
    if _PLAY_A_CARD_EXILED_WITH_CONDITION.match(lowered):
        return frozenset({TriggerEvent.CAST_SPELL, ExtraTriggerEvent.PLAYS_LAND})
    if _returned_subject(lowered) is not None:
        return frozenset({TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND})
    if _CLASS_BECOMES_LEVEL_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.CLASS_BECOMES_LEVEL})
    bending = _bending_events_named(lowered)
    if bending:
        return bending
    return frozenset()


def _unread_condition_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """`condition_matches` for an ability the parser left with `event=None`.

    The shapes read, and what each asks beyond the event itself:

    - **counters put on this permanent** (CR 122.6) - self-referential only,
      which is the only form printed in this pool, and the counter kind has to
      be the kind named.
    - **you get one or more [kind] counters** (CR 122.6, CR 109.5) -
      Fabrication Module's and Territorial Gorger's own "whenever you get one
      or more {E}": "you" is the ability's controller at the moment it
      triggered, and the counter kind has to be the kind named (CR 107.14
      normalises `{e}` to `"energy"`, the same string `Game.
      add_player_counters` stamps the event with for an ordinary `Counter.
      ENERGY` call).
    - **cards leave your graveyard** (CR 603.10a) - "your" is the ability's
      controller, and an optional type restriction ("an instant or sorcery
      card") is checked against what left.
    - **cards put into a library** (CR 401.1) - "from anywhere", by anyone,
      into any library: nothing further is asked.
    - **cards put into exile from graveyards and/or the battlefield during
      your turn** (CR 406.2) - either origin, and only while the ability's
      controller is the active player.
    - **you draw your Nth card in a turn** (CR 121.2) - the controller's own
      draws, counted over the turn.

    Anything else is False, the same safe direction `condition_matches` fails
    in for a condition it cannot read.
    """
    condition = ability.condition.lower().strip()
    mine = _self_referential(ability.condition, source.name, legendary=_is_legendary_source(source))

    match = _COUNTERS_PUT_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        if event.counter_kind != match.group("kind"):
            return False
        # CR 122.6 is about counters put on *an object*, and every printing in
        # the pool names itself as that object ("on this creature"). A
        # condition naming something else is not read at all.
        return mine and event.subject_id == source.id

    match = _LOYALTY_COUNTERS_PUT_ON_PLANESWALKER_CONDITION.match(condition)
    if match is not None:
        # CR 122.6/606.4: any planeswalker, not only the source - the
        # subject here is whichever permanent the loyalty counters actually
        # landed on, read straight off the event the same way the
        # self-referential branch above reads it, minus the self-reference.
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        if event.counter_kind != "loyalty":
            return False
        if Type.PLANESWALKER not in (event.subject_types or ()):
            return False
        if match.group("who") == "you put":
            return event.subject_controller == controller
        return event.subject_controller is not None and event.subject_controller != controller

    match = _PLAYER_COUNTERS_PUT_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.PLAYER_COUNTERS_PUT:
            return False
        if event.counter_kind != _player_counter_kind(match):
            return False
        # CR 109.5: "you" on a triggered ability's own text is the ability's
        # controller at the moment it triggered - an opponent's own energy
        # (or any other kind) is a real `PLAYER_COUNTERS_PUT` event, just not
        # one that matches "whenever *you* get".
        return event.player == controller

    match = _LEAVES_GRAVEYARD_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.LEAVES_GRAVEYARD:
            return False
        # "your graveyard": whose graveyard the card left, which the event
        # carries as `player` (the graveyard's owner), not the controller of
        # whatever effect moved it.
        if event.player != controller:
            return False
        types = match.group("types")
        return types is None or _types_match(event.subject_types, types)

    if _PUT_INTO_LIBRARY_CONDITION.match(condition):
        return event.event is ExtraTriggerEvent.PUT_INTO_LIBRARY

    if _EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION.match(condition):
        if event.event not in (
            ExtraTriggerEvent.EXILED_FROM_GRAVEYARD,
            TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
        ):
            return False
        # "during your turn" - read off the live turn machine, the same way
        # the CAST_SPELL branch already reads Ral, Monsoon Mage's identical
        # clause, since the condition is checked as the event fires.
        turn = getattr(game, "turn", None)
        return turn is not None and turn.active_player == controller

    match = _NTH_DRAW_CONDITION.match(condition)
    if match is not None:
        if event.event is not TriggerEvent.DRAWS_A_CARD or event.player != controller:
            return False
        ordinal = parse_ordinal(match.group("ordinal"))
        if ordinal is None:
            return False
        # CR 121.2 makes each card its own draw, so the ordinal is a count of
        # this player's draws so far this turn - a running total nothing in
        # `models/game.py` keeps yet (`Game.draw_cards` emits one event per
        # card and counts nothing). Without it the answer is not known, and an
        # unknown answer does not trigger.
        drawn = getattr(game, "cards_drawn_this_turn", None)
        if not isinstance(drawn, dict):
            return False
        return drawn.get(controller, 0) == ordinal

    if _LAND_ADDED_CHOSEN_MANA_CONDITION.match(condition):
        # CR 605.1b's triggered mana ability: Caged Sun's own condition, read
        # off `GameEvent.mana_added` (the colours CR 106.12a's event now
        # carries) and `CardState.choice` (CR 614.12a's as-enters choice).
        if event.event is not ExtraTriggerEvent.MANA_ADDED:
            return False
        if event.subject_controller != controller:
            return False  # "causes **you** to add".
        if Type.LAND not in (event.subject_types or ()):
            return False  # "a **land's** ability".
        chosen = source.choice
        if chosen is None or chosen.kind is not ChoiceKind.COLOR:
            # CR 106.5: with no choice recorded there is no "chosen color" for
            # the condition to be about, so it does not trigger.
            return False
        return any(color.value == chosen.value for color in event.mana_added)

    if _PLAY_A_CARD_EXILED_WITH_CONDITION.match(condition):
        # CR 601.1a: "Playing a card" means playing it as a land or casting it
        # as a spell. "You" is this
        # ability's controller, and the card has to have come out of *this*
        # object's own CR 607.2a pile - the annotation the play event carries
        # from before CR 400.7 wiped it, matched against this incarnation of
        # the source (a Visionary that left and came back reads nothing its
        # earlier self exiled).
        if event.event not in (TriggerEvent.CAST_SPELL, ExtraTriggerEvent.PLAYS_LAND):
            return False
        if event.player != controller:
            return False
        annotation = event.origin_exile_annotation
        return annotation is not None and annotation.links_to(source.id, source.zone_change_stamp)

    if _UNTAPPED_DURING_UNTAP_STEP_CONDITION.match(condition):
        # CR 502.3: only the active player untaps in their untap step, so
        # "you" and "your untap step" are both the event's own player.
        return (
            event.event is ExtraTriggerEvent.UNTAPPED_DURING_UNTAP_STEP
            and event.player == controller
        )

    if _LAST_TIME_COUNTER_CONDITION.match(condition):
        # CR 702.62a's third ability. "This card" is the source itself and
        # nothing else - `machines/casting.remove_suspend_time_counter` raises
        # the event only for the card it just took the last counter off, so
        # two suspended cards reaching zero in the same upkeep each match only
        # their own.
        return (
            event.event is ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED
            and event.subject_id == source.id
        )

    if _REVEALED_THIS_WAY_CONDITION.match(condition):
        # CR 702.94a / CR 607.2h: "this card ... this way" - the source
        # itself, revealed by its own miracle ability, by the player who drew
        # it ("you").
        return (
            event.event is ExtraTriggerEvent.REVEALED_FOR_MIRACLE
            and event.subject_id == source.id
            and event.player == controller
        )

    if _ONE_OR_MORE_DEAL_COMBAT_DAMAGE_RE.fullmatch(condition):
        # CR 603.2c: one trigger per step's damage to a player, however many
        # of the described creatures dealt it.
        if event.event is not ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS:
            return False
        return bool(batched_combat_damage_sources(game, ability.condition, controller, event))

    returned = _returned_subject(condition)
    if returned is not None:
        return _returned_to_hand_matches(game, ability, source, controller, event, returned)

    match = _CLASS_BECOMES_LEVEL_CONDITION.match(condition)
    if match is not None:
        # CR 716.2a: the level of *this* Class, and exactly that level - a
        # level 3 bar resolving is not this Class becoming level 2 again.
        return (
            event.event is ExtraTriggerEvent.CLASS_BECOMES_LEVEL
            and event.subject_id == source.id
            and event.amount == int(match.group("level"))
            and _self_referential(
                match.group("subject"), source.name, legendary=_is_legendary_source(source)
            )
        )

    bending_events = _bending_events_named(condition)
    if bending_events:
        # CR 701.67c: "whenever a player waterbends" - "you", so the event's
        # own player has to be the ability's controller, exactly like every
        # other "whenever you `<verb>`" condition this module reads.
        return event.event in bending_events and event.player == controller

    return False


def _step_matches(condition: str, controller: str, event: GameEvent) -> bool:
    """ "At the beginning of [whose] [step]" against the step that just began."""
    lowered = condition.lower()
    step = next((step for phrase, step in _STEP_PHRASES if phrase in lowered), None)
    if step is None or step is not event.step:
        return False
    if "your" in lowered:
        return event.player == controller
    if "opponent" in lowered:
        # "At the beginning of each opponent's upkeep" (Sheoldred, Whispering
        # One; Urabrask, Heretic Praetor) - CR 102.2's opponent, not "whoever's
        # step it is": without this, the bare "each upkeep" default just below
        # matched the ability's own controller's step too, firing the trigger
        # on the wrong player's turn as well as the right one.
        return event.player is not None and event.player != controller
    # "each upkeep", "the end step" - whoever's step it is.
    return True


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
)


def resolution_key(ability: "AbilityOnStack") -> str:
    """The key `Game.ability_resolutions_this_turn` counts one ability's
    resolutions under: its source as that object (CR 400.7 - a source that
    changed zones is a new object, `source_stamp`) and its own text, so two
    abilities of one permanent are counted apart."""
    return f"{ability.source_id}:{ability.source_stamp}:{ability.ability.text}"


def zones_ability_functions_in(ability: TriggeredAbility, source: CardState) -> frozenset[Zone]:
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
    # only from those zones."
    if "in your graveyard" in lowered or "from your graveyard" in lowered:
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
        return frozenset({Zone.BATTLEFIELD, source.zone})
    if ability.event is None and _returned_subject(lowered) is not None:
        # CR 603.10a's look-back for a returned-to-hand condition the parser
        # left unread: the source returned by the same event is in a hand
        # already. `_returned_to_hand_matches` hears it only then.
        return frozenset({Zone.BATTLEFIELD, Zone.HAND})

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


#: Alania, Divergent Storm's shape: "it's the first instant spell, the first
#: sorcery spell, or the first Otter spell other than Alania you've cast this
#: turn". The excluded name is optional - most cards of this shape (there is
#: only the one in the pool) name themselves so a recast copy of the permanent
#: doesn't retroactively make itself not-the-first.
_FIRST_SPELL_THIS_TURN = re.compile(
    r"^it'?s (?P<segments>.+?)"
    r"(?: other than (?P<excluded>[a-z][a-z' ]*?))?"
    r" you(?:'ve| have)? cast this turn$"
)
_FIRST_SPELL_SEGMENT = re.compile(r"^(?:the )?first (?P<word>[a-z]+) spell$")


def _first_spell_this_turn_holds(
    game: "Game", clause: str, source: CardState, event: "GameEvent | None"
) -> bool | None:
    """CR 603.4: "if it's the first [type] spell ... you've cast this turn".

    Returns `None`, not False, when the clause isn't this shape at all, so the
    caller can tell "read and false" from "not this pattern".
    """
    match = _FIRST_SPELL_THIS_TURN.match(clause)
    if match is None or event is None or event.subject_card is None:
        return None
    segments = [piece.strip() for piece in re.split(r",|\bor\b", match.group("segments"))]
    words: list[str] = []
    for segment in segments:
        if not segment:
            continue
        segment_match = _FIRST_SPELL_SEGMENT.match(segment)
        if segment_match is None:
            return None
        words.append(segment_match.group("word"))
    if not words:
        return None

    excluded = (match.group("excluded") or "").strip()
    controller = source.controller or game.active_player.username
    subject_types = event.subject_types or ()
    subject_subtypes = event.subject_subtypes or ()
    cast_this_turn = game.spells_cast_this_turn.get(controller, [])

    def _category_matches(word: str, types: tuple[Type, ...], subtypes: tuple[str, ...]) -> bool:
        type_ = _TYPE_WORDS.get(word)
        if type_ is not None:
            return type_ in types
        return any(subtype.lower() == word for subtype in subtypes)

    for word in words:
        if not _category_matches(word, subject_types, subject_subtypes):
            continue
        earlier = [
            state
            for state in cast_this_turn
            if state.id != event.subject_id
            and not (excluded and excluded in state.name.lower())
            # `state.types`/`state.subtypes` are `CardState`'s own up-face-aware
            # read (CR 712.8f) rather than `state.card`'s front-face-only one -
            # never actually different for a *cast* spell, since a card is
            # never cast as its MDFC land face, but reading the same field the
            # rest of this module now reads is what keeps this in step with it.
            and _category_matches(word, state.types, state.subtypes)
        ]
        if not earlier:
            return True
    return False


#: CR 702.33d's "if it was kicked" (Sowing Mycospawn) and CR 702.33f's
#: per-kicker variant, "if it was kicked with its [quality] kicker" - not in
#: the pool, so only the plain form is matched; a named-kicker clause falls
#: through to the fail-closed default rather than being misread as the plain
#: form.
_KICKED_CLAUSE = re.compile(r"^it was kicked$")

#: CR 702.56a's own intervening *if*, written out by
#: `machines/keywords._replicate_ability` - "a replicate cost was paid for it".
_REPLICATE_CLAUSE = re.compile(r"^a replicate cost was paid for it$")

#: CR 601.2h's "no mana was spent to cast it" (Vexing Bauble) and "[mana
#: symbols] was spent to cast it" (Wistfulness's "{G}{G}", Drowner of Truth's
#: "{C}") - both always phrased as "... to cast it" in the pool, never "...
#: to cast this spell/creature".
_NO_MANA_SPENT_CLAUSE = re.compile(r"^no mana was spent to cast it$")
_MANA_SPENT_CLAUSE = re.compile(r"^(?P<symbols>(?:\{[wubrgc]\})+) was spent to cast it$")
_MANA_SYMBOL_LETTER = re.compile(r"\{([wubrgc])\}")

#: CR 207.2c's Revolt ability word, both printed phrasings in the pool:
#: Renegade Rallier's and Fatal Push's own "a permanent left the battlefield
#: under your control this turn", and the generic reminder-text order
#: "a permanent you controlled left the battlefield this turn".
_REVOLT_CLAUSES = frozenset(
    {
        "a permanent left the battlefield under your control this turn",
        "a permanent you controlled left the battlefield this turn",
    }
)
_COLOR_LETTERS: dict[str, Color] = {
    "w": Color.WHITE,
    "u": Color.BLUE,
    "b": Color.BLACK,
    "r": Color.RED,
    "g": Color.GREEN,
    "c": Color.COLORLESS,
}


def _cast_record_for_clause(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    event: "GameEvent | None",
    source_stamp: UUID | None = None,
) -> "CastRecord | None":
    """The `CastRecord` a mana-spent or kicked clause's "it" refers to, or
    `None` if there is no longer one to read.

    A self-referential clause - Sowing Mycospawn's "if it was kicked" ("it" is
    "this spell"), Wistfulness's and Drowner of Truth's "if ... was spent to
    cast it" ("it" is "this creature"/"this spell") - means the ability's own
    source, whose record follows it from the stack onto the battlefield (CR
    400.7d) and no further: `Game.cast_record_of` keys it by the object, so a
    permanent that left and returned is a new object with no record (CR 400.7).
    Vexing Bauble's "Whenever a player casts a spell, if no mana was spent to
    cast it" is not self-referential at all: "it" is *that* spell, the trigger
    event's own subject, not Vexing Bauble itself.

    CR 601.2h's spend is recorded by `Game.note_cast` before the CAST_SPELL
    event that reaches this is ever emitted (`Game.put_on_stack`), so the
    record exists by the time this is first asked about, whichever object it
    belongs to. It does not necessarily still exist by CR 608.2a's *recheck*:
    `Game.resolve_top` (both the successful and the fizzled branches) and
    `Game.counter` all discard a spell's `CastRecord` once nothing on the
    normal path will read it again, but an intervening *if* one stack level up
    can still be waiting to ask about that exact spell after it fizzles or is
    countered. Reading `Game.cast_records` directly here, instead of going
    through `Game.cast_record`'s empty-record default, is what keeps "nobody
    ever recorded a cast" and "the record was cleaned up" both distinguishable
    from a genuine "no mana was spent" - the caller is the one that turns a
    missing record into a fail-closed `InterveningIfNotice` rather than a
    silent, wrong-object-shaped true.
    """
    if event is not None and not _self_referential(
        ability.condition, source.name, legendary=_is_legendary_source(source)
    ):
        subject = game.find_by_id(event.subject_id) if event.subject_id else None
        if subject is None:
            return None
        return game.cast_record_of(subject)
    if source_stamp is not None:
        # CR 113.7a, CR 608.2h: the recheck on resolution reads the object
        # the ability came from, even if that object has since moved on.
        return game.cast_record_as_last_known(source_stamp)
    return game.cast_record_of(source)


#: Ruby, Daring Tracker's own clause, split off `condition` into
#: `intervening_if` by `abilities._parse_triggered`'s "while" handling: "you
#: control a creature with power 4 or greater". CR 208.1 is power; the
#: three comparison shapes mirror `_mana_value_comparison`'s above, reused
#: here for a different characteristic rather than duplicated wholesale since
#: the vocabulary ("or greater"/"or less"/a bare number) is the same across
#: both.
_CONTROL_CREATURE_WITH_POWER = re.compile(
    r"^you control a creature with power (?P<threshold>\d+)"
    r"(?P<comparator> or greater| or less)?$"
)


def _control_creature_with_power_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """CR 208.1's power, compared against every creature the controller has on
    the battlefield right now (CR 613.5's `characteristics_of`, not the
    printed `CardState.power`, so a pumped or shrunk creature is read
    correctly). `None`, not False, when `clause` isn't this shape at all."""
    match = _CONTROL_CREATURE_WITH_POWER.match(clause)
    if match is None:
        return None
    threshold = int(match.group("threshold"))
    comparator = (match.group("comparator") or "").strip()
    ops = {
        "or greater": operator.ge,
        "or less": operator.le,
        "": operator.eq,
    }
    op = ops[comparator]
    controller = source.controller or game.active_player.username
    for state in game.permanents_controlled_by(controller):
        characteristics = game.characteristics_of(state)
        if characteristics.is_creature and op(characteristics.power or 0, threshold):
            return True
    return False


#: "there are N or more permanent cards in your graveyard" - the "descend
#: 4"/"descend 8" ability words' own condition (CR 207.2c) read as a plain
#: triggered ability's intervening *if* rather than as `machines/layers.py`'s
#: gated-self-static shape: Coati Scavenger's "When this creature enters, if
#: there are four or more permanent cards in your graveyard, return target
#: permanent card from your graveyard to your hand." and Starving Revenant's
#: "Whenever you draw a card, if there are eight or more permanent cards in
#: your graveyard, target opponent loses 1 life and you gain 1 life." -
#: distinct from CR 700.11's own per-turn "you descended this turn" event
#: count (the clause immediately below): the two mechanics only share the
#: English word "descend". This one is a live graveyard count, re-checked at
#: CR 603.4 and again at CR 608.2a, the same live count `machines/layers.py`'s
#: `count_permanent_cards` answers for the static shape.
_DESCEND_PERMANENT_CARD_COUNT_CLAUSE = re.compile(
    rf"^there are (?P<n>{COUNT}) or more permanent cards in your graveyard$"
)


def _descend_permanent_card_count_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    """`_DESCEND_PERMANENT_CARD_COUNT_CLAUSE`'s shape, or `None` when `clause`
    is not it. `count_permanent_cards` is imported locally, the same way
    `intervening_if_holds` already imports `meld_condition_holds` from
    `.meld` - `machines/layers.py` imports `machines/combat.py`, which
    imports this module for `GameEvent`, so a module-level import here would
    be circular.
    """
    match = _DESCEND_PERMANENT_CARD_COUNT_CLAUSE.fullmatch(clause)
    if match is None:
        return None
    threshold = parse_count(match.group("n"), article=False)
    if threshold is None:
        # Not actually reachable: every string `_DESCEND_PERMANENT_CARD_
        # COUNT_CLAUSE` accepts for its `n` group is itself a `COUNT`
        # alternative, and `parse_count` (with `article=False`, matching how
        # this group was matched) is total over that vocabulary. `None` here
        # would mean the two had drifted apart - return `None` rather than a
        # `bool` so the caller's own `_fail_closed` catches that drift
        # instead of this function silently answering for a shape it does
        # not actually recognise.
        return None

    from .layers import count_permanent_cards

    controller = source.controller or game.active_player.username
    return count_permanent_cards(game.player(controller).graveyard) >= threshold


#: CR 702.176a's own intervening *if*, read over the keyword and the counter
#: kind rather than over one card: "this permanent's impending cost was paid
#: and it has a time counter on it". The paid half is
#: `CardState.cast_with_keyword`, which belongs to this object only (CR
#: 400.7), the same way `Game.cast_record_of` answers only for this object.
_PERMANENT_KEYWORD_COST_PAID_WITH_COUNTER = re.compile(
    r"^this permanent's (?P<keyword>[a-z]+) cost was paid and it has an? "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counter on it$"
)

#: "it had power greater than `<name>`'s power" - Drizzt Do'Urden's own dies
#: trigger, `<name>` printed as the card's own name (CR 201.5) rather than
#: CR 700.7's "this creature". `clause` arrives lowercased (see below), so
#: `<name>` is matched case-insensitively and checked against the source's
#: own printed name the same way `_parse_may_exile_self_then_return_clause`
#: already does for its own CR 201.5 self-reference.
_POWER_GREATER_THAN_SELF_RE = re.compile(r"^it had power greater than (?P<name>.+)'s power$")


def _opponent_cast_color_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Sandstalker Moloch's own intervening if: "if an opponent cast a blue
    and/or black spell this turn" - the identical board fact Veil of
    Summer's trailing "if" reads, in different words.

    Read through `Game.condition_holds`'s own `_CONDITION_OPPONENT_CAST_
    COLOR` branch rather than a second copy of the colour/turn logic here,
    so the two cards can never drift apart on what counts as "cast" or
    which player is "an opponent" of whom - the shape check
    (`fullmatch`, not just importing `condition_is_readable`, which would
    also route every *other* board condition `condition_holds` reads
    through this ability's intervening if, well beyond this one clause)
    is the only thing duplicated, and only so this stays a plain `None`
    for every clause shape this reader is not meant for.
    """
    from ..models.game import _CONDITION_OPPONENT_CAST_COLOR

    if _CONDITION_OPPONENT_CAST_COLOR.fullmatch(clause) is None:
        return None
    controller = source.controller or game.active_player.username
    return game.condition_holds(controller, clause, source)


def _opponent_comparison_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Ticket Tortoise's own intervening if: "if an opponent controls more
    lands than you" - the comparison `Game.condition_holds` reads for Beza,
    the Bounding Spring's and Sunset Revelry's plain "if"s
    (`_CONDITION_OPPONENT_COMPARISON`), asked by CR 603.4 as the event occurs
    and again as the ability resolves. `None` for any other clause."""
    from ..models.game import _CONDITION_OPPONENT_COMPARISON

    if _CONDITION_OPPONENT_COMPARISON.fullmatch(clause) is None:
        return None
    return game.condition_holds(controller_of_source(game, source), clause, source)


def _self_is_a_creature_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Hydro-Man, Fluid Felon's own intervening if: "if Hydro-Man is a
    creature" - `Game.condition_holds`' `_CONDITION_SELF_IS_A_CREATURE`, the
    source on the computed board (CR 613.5), asked by CR 603.4 as the event
    occurs and again as the ability resolves. `None` for any other clause,
    including one whose subject is not this source."""
    from ..models.game import _CONDITION_SELF_IS_A_CREATURE

    if _CONDITION_SELF_IS_A_CREATURE.fullmatch(clause) is None:
        return None
    return game.condition_holds(controller_of_source(game, source), clause, source)


def _you_control_a_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Birthing Ritual's own intervening if: "if you control a creature" -
    the "you control a(n) `<quality>`" board fact `Game.condition_holds`
    already reads for Flame of Anor's trailing "if" (`_CONDITION_CONTROLS_A`),
    asked by CR 603.4 as the event occurs and again by CR 608.2a as the
    ability resolves. `None` for any other clause, and for a quality
    `condition_is_readable` refuses, so those still fail closed."""
    from ..models.game import _CONDITION_CONTROLS_A, condition_is_readable

    if _CONDITION_CONTROLS_A.fullmatch(clause) is None or not condition_is_readable(clause):
        return None
    controller = source.controller or game.active_player.username
    return game.condition_holds(controller, clause, source)


def intervening_if_holds(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    event: "GameEvent | None" = None,
    source_stamp: UUID | None = None,
) -> bool:
    """Whether an intervening *if* clause is true right now (CR 603.4, 608.2a).

    "When the trigger event occurs, the ability checks whether the stated
    condition is true. The ability triggers only if it's true" (CR 603.4);
    CR 608.2a rechecks the same clause again as the ability resolves.

    Clause shapes read: persist's "it had no -1/-1 counters on it"
    (CR 702.79a), Thopter Assembly's "you control no [subtype]s other than
    this creature", Ocelot Pride's "you gained life this turn", Renegade
    Rallier's own Revolt clause "a permanent left the battlefield under your
    control this turn" (CR 207.2c, `_REVOLT_CLAUSES`, `Game.
    revolt_active_for`), Alania,
    Divergent Storm's "it's the first [type] spell ... you've cast this turn",
    kicker's "if it was kicked" (CR 702.33a, 702.33d), replicate's "a
    replicate cost was paid for it" (CR 702.56a), CR 601.2h's "if no
    mana was spent to cast it" / "if [mana symbols] was spent to cast it"
    (Vexing Bauble, Wistfulness, Drowner of Truth), Transcendent Dragon's
    plain "if you cast it" (CR 601.2's cast, as opposed to any other way a
    permanent reaches the battlefield), Ayara's Oathsworn's counter-count
    comparison "it has fewer than four +1/+1 counters on it"
    (`_counter_count_holds`, CR 122.1), Vengevine's ordinal "it's the second
    creature spell you cast this turn" (`_ordinal_spell_cast_this_turn_holds`),
    and Phoenix Fleet Airship's "you sacrificed a permanent this turn"
    (`_sacrificed_this_turn_holds`, CR 701.21a).

    The mana/kicker/cast clauses all read
    `Game.cast_record` - see `_cast_record_for_clause` for whose record "it"
    means, and `machines/casting.Casting.cast`/`Game.note_cast` for where the
    record comes from: `CostPayment.mana_payment.spend` at the moment CR 601.2h
    pays the total cost, and `Casting.kicked` at the moment CR 601.2b announces
    which optional additional costs are being paid.

    Anything else **fails closed**: CR 603.4 only lets the ability trigger if
    the condition is true, and a condition this module cannot read is not
    *known* to be true, so the ability does not trigger. This is the opposite
    of the old default, which read anything it could not recognise as true -
    fail-open is how an unkicked Sowing Mycospawn exiled a land. The refusal
    is recorded on `game.intervening_if_notices` (`InterveningIfNotice`) so it
    reads as an engine gap, not as a legal "nothing happened".
    """
    clause = (ability.intervening_if or "").lower().strip()
    if not clause:
        return True

    from .meld import meld_condition_holds

    meld_holds = meld_condition_holds(game, clause, source)
    if meld_holds is not None:
        # CR 701.42a's "you both own and control this <type> and a[nother]
        # <type> named <partner>" - Graf Rats' own triggered meld shape.
        # Answered directly rather than through `_fail_closed`: this clause
        # is fully readable (`machines/meld.py`'s regex is generic across
        # every meld pair, not keyed to a card name), so a `False` here is
        # a genuine "only one half is present right now", not an unreadable
        # shape.
        return meld_holds

    if clause in ("you cast it", "you cast him", "you cast her", "you cast them"):
        # CR 601.2's cast is a defined action distinct from every other way a
        # permanent can reach the battlefield (reanimation, a search-and-put
        # effect, ...); `Game.note_cast` (CR 601.2h) only ever records a
        # `CastRecord` when a card actually went through that process, so its
        # mere presence for the self-referential source (see
        # `_cast_record_for_clause`) already answers this clause. Unlike the
        # mana-spent clauses above, a missing record here is not an unreadable
        # shape to fail closed on - it is the legitimate, expected answer for
        # a creature that entered some other way, so this returns `False`
        # directly rather than through `_fail_closed`.
        #
        # "Him"/"her"/"them" are the identical CR 700.7 self-reference as
        # "it", spelled with a legendary character's own established pronoun
        # (`machines/abilities.self_normalized_effect_text`'s own gendered
        # candidates read the same idiom for a printed name) - Uldaros
        # Theorix's own "if you cast him" is the reported shape.
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None

    paid_with_counter = _PERMANENT_KEYWORD_COST_PAID_WITH_COUNTER.fullmatch(clause)
    if paid_with_counter is not None:
        # CR 702.176a, see the regex above. Fully readable, so a False here is
        # a real "not paid" or "no counter left", never a fail-closed notice.
        return (
            source.zone is Zone.BATTLEFIELD
            and (source.cast_with_keyword or "").lower() == paid_with_counter.group("keyword")
            and source.counter_count(paid_with_counter.group("kind")) > 0
        )

    if clause == "its evoke cost was paid":
        # CR 702.74a's own intervening *if*, written out by
        # `machines/keywords._evoke_ability`. What makes it answerable is
        # `CastRecord.keyword`: CR 118.9a allows one alternative cost per spell
        # and `machines/casting.Casting.cast` records which keyword's cost was
        # announced, so "was it evoked" is a lookup rather than an inference
        # from what was spent. A permanent that reached the battlefield without
        # being cast at all has no record, and that is the legitimate answer -
        # its evoke cost was not paid - not an unreadable clause, so this
        # returns False directly rather than through `_fail_closed`, exactly as
        # "you cast it" above does.
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None and (record.keyword or "").lower() == "evoke"

    if clause == "its offspring cost was paid":
        # CR 702.175a: "'Offspring [cost]' means 'You may pay an additional
        # [cost] as you cast this spell' and 'When this permanent enters, if
        # its offspring cost was paid, create a token that's a copy of it,
        # except it's 1/1.'" Offspring is an *additional* cost (CR 118.8a),
        # not an alternative one, so unlike evoke this reads
        # `CastRecord.offspring_paid` rather than `.keyword` - a spell can be
        # both kicked and offspring-paid at once, and each linked ability
        # only ever asks about its own cost (CR 702.175b).
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None and record.offspring_paid

    if _KICKED_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.kicked > 0

    if _REPLICATE_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.replicated > 0

    if _NO_MANA_SPENT_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return not record.any_mana_spent

    mana_match = _MANA_SPENT_CLAUSE.match(clause)
    if mana_match is not None:
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        required: dict[Color, int] = {}
        for letter in _MANA_SYMBOL_LETTER.findall(mana_match.group("symbols")):
            color = _COLOR_LETTERS[letter]
            required[color] = required.get(color, 0) + 1
        return all(record.mana_of_color_spent(color) >= count for color, count in required.items())

    if clause == "this card is suspended":
        # CR 702.62a's second ability, and CR 702.62b is its whole definition:
        # "A card is 'suspended' if it's in the exile zone, has suspend, and
        # has a time counter on it." `CardState.is_suspended` is that rule,
        # word for word, so a card already cast, already gone from exile some
        # other way, or already down to zero counters answers False here -
        # on the event (CR 603.4) and again on resolution (CR 608.2a).
        return source.is_suspended

    if clause == "it's exiled":
        # CR 702.62a's third ability. "It" is the card the last time counter
        # came off, which is this ability's own source; CR 406.1's exile zone
        # is the only thing asked about, not the marker that put it there -
        # by this point the card has no time counters left, so CR 702.62b's
        # "suspended" is deliberately *not* what the rule reaches for here.
        return source.zone is Zone.EXILE

    if clause == "this permanent is on the battlefield":
        # CR 702.24a's own intervening *if* for cumulative upkeep, written out
        # by `machines/keywords._cumulative_upkeep_ability`: a zone question
        # (CR 400.1), fully readable, so False is a real answer.
        return source.zone is Zone.BATTLEFIELD

    if match := _POWER_GREATER_THAN_SELF_RE.fullmatch(clause):
        if match.group("name") not in (source.name or "").lower():
            return _fail_closed(game, ability, source)
        dying = event_subject_power(game, event)
        if dying is None:
            return _fail_closed(game, ability, source)
        return dying > (game.power_of(source) or 0)

    if clause == "it isn't a token":
        # Gruff Triplets' own ETB ("if it isn't a token, create two tokens
        # that are copies of it") and Sphinx of False Conclusions' dies
        # trigger ("if it isn't a token, create a token that's a copy of
        # it") - CR 111.1/CR 111.6's own distinction, read straight off
        # `CardState.token` (CR 603.10a's look-back keeps it set on the last
        # known information for a dies trigger the same way every other
        # last-known field here is read).
        return not source.token

    if clause == "it had no -1/-1 counters on it":
        # CR 702.79a asks about the permanent as it last existed on the
        # battlefield, and CR 122.2 has already destroyed its counters on the
        # way to the graveyard. CR 704.8 and CR 603.10a are what make that
        # question answerable at all, and `last_known_counters` is the answer.
        return not source.last_known_counters[Counter.MINUS_ONE]

    match = re.match(r"you control no (\w+?)s? other than this \w+", clause)
    if match is not None:
        subtype = match.group(1)
        controller = source.controller or game.active_player.username
        # CR 613.5: the computed subtypes, not the printed line - hoisted
        # once for the whole scan rather than asked per permanent (see
        # `Game._state_based_actions_once`'s own pattern).
        board = game.computed_board()
        others = [
            state
            for state in game.permanents_controlled_by(controller)
            if state.id != source.id
            and any(word.lower() == subtype for word in board.of(state).subtypes)
        ]
        return not others

    if clause == "you gained life this turn":
        controller = source.controller or game.active_player.username
        return controller in game.life_gained_this_turn

    if clause in (
        "you've scried or surveilled this turn",
        "you have scried or surveilled this turn",
    ):
        # CR 701.22a/701.25a. Surveillance Phantasm prints the same fact as a
        # static "as long as" (S9's own layer-conditional reading);
        # Desperate Futurescribe's own printing folds it into an "instead"
        # continuous-effect upgrade rather than a bare intervening *if* - the
        # predicate is the same fact either way, and this is that predicate,
        # exposed for whichever clause parser needs to ask it. CR 109.5's
        # "you" (`controller_of_source`) rather than the bare `source.
        # controller or active_player` fallback most of this function's
        # older branches still use - Command the Stage's own graveyard-
        # functioning ability is exactly the case that fallback gets wrong,
        # crediting whoever's turn it happens to be instead of the card's
        # own owner (`test_turn_history_predicates.py` caught this live).
        return game.turn_fact_holds("scried_or_surveilled", controller_of_source(game, source))

    if clause == "you've activated a loyalty ability this turn":
        # Kiora of Salt and Sand's own "Whenever you attack, if you've
        # activated a loyalty ability this turn, ..." (CR 606.2).
        return game.turn_fact_holds("loyalty_ability_activated", controller_of_source(game, source))

    noncombat_damage = _opponent_dealt_noncombat_damage_holds(game, clause, source)
    if noncombat_damage is not None:
        return noncombat_damage

    creatures_died = _creatures_died_this_turn_holds(game, clause)
    if creatures_died is not None:
        return creatures_died

    other_subtype_count = _controls_at_least_other_subtype_count_holds(game, clause, source)
    if other_subtype_count is not None:
        return other_subtype_count

    if clause == "you descended this turn":
        # CR 700.11: "This means that a permanent card has been put into
        # that player's graveyard from anywhere this turn." Broodrage
        # Mycoid's own end-step trigger, and every other "if you descended
        # this turn" printing - `Game.descended` is the one shared answer,
        # reading FRA S5's `graveyard_arrivals_this_turn` ledger (see that
        # method's own docstring for the merge note).
        controller = source.controller or game.active_player.username
        return game.descended(controller)

    descend_count = _descend_permanent_card_count_holds(game, clause, source)
    if descend_count is not None:
        return descend_count

    if clause in _REVOLT_CLAUSES:
        # CR 207.2c: Revolt is an ability word, so no numbered rule spells out
        # the condition itself; the wording is the card's own. Renegade
        # Rallier's own ETB prints "a permanent left the battlefield under
        # your control this turn" - the identical clause Fatal Push carries,
        # except Fatal Push's is read directly by `machines/targeting.py`'s
        # `comparison_value_if_revolt` because it modifies a *target
        # restriction* rather than gating a triggered ability at all
        # (`test_fatal_push_revolt.py`). `Game.revolt_active_for` is the one
        # shared answer both readings ask.
        controller = source.controller or game.active_player.username
        return game.revolt_active_for(controller)

    power_control = _control_creature_with_power_holds(game, clause, source)
    if power_control is not None:
        return power_control

    first_spell = _first_spell_this_turn_holds(game, clause, source, event)
    if first_spell is not None:
        return first_spell

    last_turn = _spells_cast_last_turn_holds(game, clause)
    if last_turn is not None:
        return last_turn

    this_turn = _spells_cast_this_turn_holds(game, clause, source)
    if this_turn is not None:
        return this_turn

    another_spell = _another_spell_cast_this_turn_holds(game, clause, source)
    if another_spell is not None:
        return another_spell

    didnt_cast = _didnt_cast_spell_this_turn_holds(game, clause, source)
    if didnt_cast is not None:
        return didnt_cast

    drawn_count = _drawn_card_count_holds(game, clause, source)
    if drawn_count is not None:
        return drawn_count

    self_tapped = _source_tapped_holds(clause, source)
    if self_tapped is not None:
        return self_tapped

    self_prepared = _source_prepared_holds(clause, source)
    if self_prepared is not None:
        return self_prepared

    counter_count = _counter_count_holds(clause, source)
    if counter_count is not None:
        return counter_count

    ordinal_spell = _ordinal_spell_cast_this_turn_holds(game, clause, source, event)
    if ordinal_spell is not None:
        return ordinal_spell

    sacrificed = _sacrificed_this_turn_holds(game, clause, source)
    if sacrificed is not None:
        return sacrificed

    subtype_count = _controlled_subtype_count_holds(game, clause, source)
    if subtype_count is not None:
        return subtype_count

    opponent_cast_color = _opponent_cast_color_holds(game, clause, source)
    if opponent_cast_color is not None:
        return opponent_cast_color

    you_control_a = _you_control_a_holds(game, clause, source)
    if you_control_a is not None:
        return you_control_a

    opponent_comparison = _opponent_comparison_holds(game, clause, source)
    if opponent_comparison is not None:
        return opponent_comparison

    self_is_a_creature = _self_is_a_creature_holds(game, clause, source)
    if self_is_a_creature is not None:
        return self_is_a_creature

    entered_or_cast_from_graveyard = _entered_or_cast_from_graveyard_holds(
        game, clause, source, event
    )
    if entered_or_cast_from_graveyard is not None:
        return entered_or_cast_from_graveyard

    return _fail_closed(game, ability, source)


#: One alternative of Prized Amalgam's and Archfiend's Vessel's clause: "it
#: entered from your graveyard" / "you cast it from your graveyard".
_FROM_GRAVEYARD_ALTERNATIVE = re.compile(
    r"^(?:it entered(?: the battlefield)? from (?P<entered>your|a) graveyard"
    r"|you cast it from (?P<cast>your|a) graveyard)$"
)


def _entered_or_cast_from_graveyard_holds(
    game: "Game", clause: str, source: CardState, event: "GameEvent | None"
) -> bool | None:
    """CR 603.4's "if it entered from your graveyard or you cast it from your
    graveyard" - `None` when the clause is not this shape.

    "It" is the enters event's own object (the entering creature, which is
    the source itself for Archfiend's Vessel's self-trigger). "Entered from
    your graveyard" reads `GameEvent.origin_zone` - the zone the permanent
    left to enter (`Game.enter_the_battlefield`) - and "your" graveyard is
    the one its owner keeps (CR 400.3) belonging to the ability's
    controller. "You cast it from your graveyard" reads the permanent's own
    `CastRecord` (CR 400.7d): cast from the graveyard, by a player who is the
    ability's controller. Either alternative satisfies the clause (the
    English "or"). Both are recorded facts about that one event, so the
    CR 603.4 recheck on resolution reads the same answer.
    """
    parts = [part.strip() for part in clause.split(" or ")]
    matches = [_FROM_GRAVEYARD_ALTERNATIVE.fullmatch(part) for part in parts]
    if not parts or any(match is None for match in matches):
        return None
    if event is None or event.subject_id is None:
        return False
    you = source.controller or source.owner
    subject = game.find_by_id(event.subject_id)
    owner = subject.owner if isinstance(subject, CardState) else None
    for match in matches:
        assert match is not None
        entered_whose = match.group("entered")
        if entered_whose is not None:
            if event.origin_zone is Zone.GRAVEYARD and (entered_whose == "a" or owner == you):
                return True
            continue
        cast_whose = match.group("cast")
        if not isinstance(subject, CardState):
            continue
        record = game.cast_record_of(subject)
        if record is None or record.origin_zone is not Zone.GRAVEYARD:
            continue
        if subject.controller == you and (cast_whose == "a" or owner == you):
            return True
    return False


#: Ayara's Oathsworn's clause: "it has fewer than four +1/+1 counters on it",
#: and the suffix form most cards print: Lightning Coils' "this artifact has
#: five or more charge counters on it", Earthbender Ascension's "it has four or
#: more quest counters on it". "It" is the source itself - the only subject
#: this shape is printed with in this pool, and CR 603.4's clause is read about
#: the ability's own source unless it plainly names something else.
_COUNTER_COUNT_CLAUSE = re.compile(
    r"^(?:it|this [a-z]+) has "
    rf"(?:(?P<comparison>fewer than|more than|at least|exactly) (?P<count>{COUNT})"
    rf"|(?P<suffix_count>{COUNT}) or (?P<direction>more|fewer)"
    r"|(?P<none>no))"
    r" (?P<kind>\S+) counters? on it$"
)

#: How each comparison word answers, given the counters actually there and the
#: number the clause names. "N or more" and "N or fewer" are inclusive.
_COUNTER_COMPARISONS = {
    "fewer than": operator.lt,
    "more than": operator.gt,
    "at least": operator.ge,
    "exactly": operator.eq,
    "more": operator.ge,
    "fewer": operator.le,
}


def _counter_count_holds(clause: str, source: CardState) -> bool | None:
    """CR 603.4's clause as a counter count on the source (CR 122.1's counters
    as "a marker placed on an object ... that modifies its characteristics
    and/or interacts with a rule, ability, or effect").

    `None`, not False, when the clause is not this shape, so an unrelated
    clause still reaches `_fail_closed`. A count word this does not know is
    left unread the same way, rather than guessed at.
    """
    match = _COUNTER_COUNT_CLAUSE.match(clause)
    if match is None:
        return None
    on_it = source.counter_count(match.group("kind"))
    if match.group("none") is not None:
        return on_it == 0
    if match.group("suffix_count") is not None:
        count_word, comparison = match.group("suffix_count"), match.group("direction")
    else:
        count_word, comparison = match.group("count"), match.group("comparison")
    wanted = parse_count(count_word, article=False)
    if wanted is None:
        return None
    return _COUNTER_COMPARISONS[comparison](on_it, wanted)


#: Vengevine's clause: "it's the second creature spell you cast this turn".
#: The ordinal twin of `_FIRST_SPELL_THIS_TURN`, which reads only "first" and
#: so left every other ordinal to fail closed.
_ORDINAL_SPELL_CAST_THIS_TURN = re.compile(
    r"^it'?s the (?P<ordinal>[a-z]+) (?P<word>[a-z]+) spell you(?:'ve| have)? cast this turn$"
)


def _ordinal_spell_cast_this_turn_holds(
    game: "Game", clause: str, source: CardState, event: "GameEvent | None"
) -> bool | None:
    """Whether the spell this trigger is about is exactly the controller's Nth
    spell of the named kind cast this turn (CR 603.4).

    "It" is the cast spell the CAST_SPELL event carries, not the source - the
    same reading `_first_spell_this_turn_holds` already gives its own "it".
    Answered from `Game.spells_cast_this_turn`, which CR 601.2i's completed
    cast has already appended this very spell to, so the spell's 1-indexed
    position among that turn's spells of the named kind *is* the ordinal.

    `None` when the clause is not this shape, or when there is no event to
    identify the spell with, so the caller still fails closed.
    """
    match = _ORDINAL_SPELL_CAST_THIS_TURN.match(clause)
    if match is None or event is None or event.subject_id is None:
        return None
    ordinal = parse_ordinal(match.group("ordinal"))
    card_type = _TYPE_WORDS.get(match.group("word"))
    if ordinal is None or card_type is None:
        return None
    controller = source.controller or game.active_player.username
    of_that_kind = [
        state
        for state in game.spells_cast_this_turn.get(controller, [])
        if card_type in state.types
    ]
    position = next(
        (
            index
            for index, state in enumerate(of_that_kind, start=1)
            if state.id == event.subject_id
        ),
        None,
    )
    return position == ordinal


def _sacrificed_this_turn_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Phoenix Fleet Airship's clause: "you sacrificed a permanent this turn"
    (CR 701.21a's sacrifice, asked about the turn rather than about one
    event) - `Game.condition_holds`' `_CONDITION_SACRIFICED_THIS_TURN`, read
    off `Game.permanents_sacrificed_this_turn`. A bounced or destroyed
    permanent left the battlefield without ever being sacrificed, which is
    why `permanents_left_battlefield_this_turn` cannot answer this. `None`
    for any other clause."""
    from ..models.game import _CONDITION_SACRIFICED_THIS_TURN

    if _CONDITION_SACRIFICED_THIS_TURN.fullmatch(clause) is None:
        return None
    return game.condition_holds(controller_of_source(game, source), clause, source)


#: Command the Stage's "an opponent was dealt noncombat damage last turn"
#: and Grim Repriser's activation-restriction twin "an opponent has been
#: dealt noncombat damage this turn" (CR 120.2a) - the same fact, asked
#: about either turn.
_OPPONENT_DEALT_NONCOMBAT_DAMAGE = re.compile(
    r"^an opponent (?:was|has been) dealt noncombat damage (?P<when>this|last) turn$"
)


def _opponent_dealt_noncombat_damage_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    """Whether any of `source`'s controller's opponents was dealt noncombat
    damage this turn or last turn, off `Game.turn_facts`' "dealt_noncombat_
    damage" ledger (`Game.deal_damage`'s own record of it).

    `controller_of_source`, not a bare `source.controller or active_player`
    fallback: Command the Stage's own printing of this clause functions from
    a graveyard (CR 113.6m) and is checked at *any* player's upkeep, so the
    active player is frequently not this card's owner at all - Grim
    Repriser's activation-restriction twin has the identical shape.
    """
    match = _OPPONENT_DEALT_NONCOMBAT_DAMAGE.match(clause)
    if match is None:
        return None
    controller = controller_of_source(game, source)
    last_turn = match.group("when") == "last"
    return any(
        game.turn_fact_holds("dealt_noncombat_damage", player.username, last_turn=last_turn)
        for player in game.players_in_game
        if player.username != controller
    )


#: Darklight Phoenix's "two or more creatures died this turn" (CR 700.4),
#: an ordinary count over `Game.creatures_died_this_turn` rather than
#: pinned to the number two - a different printing naming a different
#: threshold reads the same way.
_CREATURES_DIED_THIS_TURN = re.compile(rf"^(?P<count>{COUNT}) or more creatures died this turn$")


def _creatures_died_this_turn_holds(game: "Game", clause: str) -> bool | None:
    match = _CREATURES_DIED_THIS_TURN.match(clause)
    if match is None:
        return None
    needed = parse_count(match.group("count"), article=False)
    if needed is None:
        return None
    return game.creatures_died_this_turn >= needed


#: Roiling Canopy's "you control at least five other Forests" (CR 205.3i's
#: land subtype) - the counted twin of the "you control no [subtype]s other
#: than this [type]" shape already read above, generalised the same way: a
#: subtype word and a count, not a fixed number or a fixed subtype.
_CONTROL_AT_LEAST_OTHER_SUBTYPE = re.compile(
    rf"^you control at least (?P<count>{COUNT}) other (?P<subtype>\w+?)s?$"
)


def _controls_at_least_other_subtype_count_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    match = _CONTROL_AT_LEAST_OTHER_SUBTYPE.match(clause)
    if match is None:
        return None
    needed = parse_count(match.group("count"), article=False)
    if needed is None:
        return None
    subtype = match.group("subtype").lower()
    controller = controller_of_source(game, source)
    # CR 613.5: the computed subtypes, not the printed line - a land that is
    # a Forest only because of an animating/typechanging effect still counts,
    # and one that lost the subtype does not.
    board = game.computed_board()
    others = [
        state
        for state in game.permanents_controlled_by(controller)
        if state.id != source.id
        and any(word.lower() == subtype for word in board.of(state).subtypes)
    ]
    return len(others) >= needed


#: "if Kona is tapped" / "if this creature is untapped" - a clause about the
#: source's own tap state. The subject is either CR 700.7's "this [something]"
#: or CR 201.5's self-reference by printed name, which CR 201.5c lets a card
#: shorten ("Kona" for "Kona, Rescue Beastie").
_SOURCE_TAP_STATE = re.compile(r"^(?P<subject>.+?) is (?P<state>tapped|untapped)$")


def _source_tapped_holds(clause: str, source: CardState) -> bool | None:
    """`_SOURCE_TAP_STATE`'s shape - Kona, Rescue Beastie's *survival* trigger.

    `None` when the clause is not this shape, or when its subject is some
    other object than the source itself: this reads only the source's own tap
    state, so a clause about anything else still reaches `_fail_closed`
    rather than being answered from the wrong permanent.

    CR 201.5 is what makes a printed name mean "just that particular object
    and not any other objects with that name", and CR 201.5c is what lets the
    card print only the first part of it.
    """
    match = _SOURCE_TAP_STATE.match(clause)
    if match is None:
        return None
    subject = match.group("subject").strip().lower()
    name = source.name.lower()
    is_self = re.fullmatch(r"this \w+", subject) is not None or (
        subject
        and (name == subject or name.startswith(f"{subject},") or name.startswith(f"{subject} "))
    )
    if not is_self:
        return None
    return source.tapped if match.group("state") == "tapped" else not source.tapped


#: CR 722.3a's own condition guard, printed on most upkeep-triggered prepare
#: creatures: "if this creature isn't prepared". `_SOURCE_TAP_STATE`'s own
#: subject-reading shape, for "prepared"/"unprepared" instead of "tapped"/
#: "untapped" - both polarities read the same way that pair does, though the
#: pool only ever prints the negative ("isn't prepared", Woodwork Prodigy).
_SOURCE_PREPARED_STATE = re.compile(r"^(?P<subject>.+?) (?:is(?P<negated>n'?t)? )?prepared$")


def _source_prepared_holds(clause: str, source: CardState) -> bool | None:
    """`_SOURCE_PREPARED_STATE`'s shape - see its own docstring."""
    match = _SOURCE_PREPARED_STATE.match(clause)
    if match is None:
        return None
    subject = match.group("subject").strip().lower()
    name = source.name.lower()
    is_self = re.fullmatch(r"this \w+", subject) is not None or (
        subject
        and (name == subject or name.startswith(f"{subject},") or name.startswith(f"{subject} "))
    )
    if not is_self:
        return None
    return (not source.prepared) if match.group("negated") else source.prepared


#: "you've cast three or more instant and sorcery spells this turn" - Arclight
#: Phoenix's own combat trigger - and Loan Shark's untyped "you've cast two or
#: more spells this turn". The type list is optional; when printed it is CR
#: 205.2a's card types, joined with a bare "and"/"or"/comma, and a spell
#: matching *any* of them counts once, which is what the card means (an
#: instant is not also a sorcery). Without one, every spell counts.
_SPELLS_CAST_THIS_TURN = re.compile(
    rf"^you(?:'ve| have) cast (?P<count>{COUNT}) or more "
    r"(?:(?P<types>[a-z, ]+?) )?spells this turn$"
)
#: "you've cast another spell this turn" - Sage of the Skies' own cast
#: trigger. "Another" excludes the spell the trigger is printed on, which is
#: itself already recorded in `Game.spells_cast_this_turn` by the time the
#: trigger is checked (CR 601.2i puts the spell on the stack, and the cast
#: trigger fires off that very event).
_ANOTHER_SPELL_THIS_TURN = re.compile(r"^you(?:'ve| have) cast another spell this turn$")


def _another_spell_cast_this_turn_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    """`_ANOTHER_SPELL_THIS_TURN`'s shape, or `None` if the clause is not it.

    Counted off `Game.spells_cast_this_turn`, with the source itself excluded
    by id - CR 201.5's "just that particular object", not "any object with
    that name", so a second copy of the same card cast earlier this turn does
    satisfy the clause.
    """
    if _ANOTHER_SPELL_THIS_TURN.match(clause) is None:
        return None
    controller = source.controller or game.active_player.username
    cast = game.spells_cast_this_turn.get(controller, [])
    return any(state.id != source.id for state in cast)


#: "you didn't cast a spell this turn" (Edgar, Moonlit Sovereign; Nightpack
#: Ambusher) and "that player didn't cast a spell this turn" (Impatience -
#: the same clause read with the third-person subject a per-player "at the
#: beginning of each player's end step" ability prints) - CR 601.2i's
#: already-tracked `Game.spells_cast_this_turn`, negated.
#: `_spells_cast_this_turn_holds` below only ever reads the positive "you've
#: cast N or more spells this turn" form; this is its negated twin, over the
#: identical field.
_DIDNT_CAST_SPELL_THIS_TURN = re.compile(
    r"^(?:you|that player) (?:didn'?t|did not|haven'?t|have not) cast a spell"
    r"(?P<from_hand> from (?:your|their) hand)? this turn$"
)


def _didnt_cast_spell_this_turn_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_DIDNT_CAST_SPELL_THIS_TURN`'s shape, or `None` if the clause is not
    it.

    "You"/"that player" is the ability's own controller (CR 109.5's default,
    absent an explicit "that player" bound to a different per-player
    trigger) - the same fallback `_spells_cast_this_turn_holds` already uses
    for its positive form, over the identical `Game.spells_cast_this_turn`
    list CR 601.2i keeps.
    """
    match = _DIDNT_CAST_SPELL_THIS_TURN.match(clause)
    if match is None:
        return None
    controller = source.controller or game.active_player.username
    if match.group("from_hand"):
        # Prairie Dog's "if you haven't cast a spell from your hand this
        # turn": only a cast whose CR 601.2a move started in a hand counts,
        # recorded as it happened (`Game.put_on_stack`).
        return not game.turn_fact_holds("cast_spell_from_hand", controller)
    cast = game.spells_cast_this_turn.get(controller, [])
    return len(cast) == 0


#: "you've drawn N or more cards this turn" (Lyra, Tolarian Archangel) and
#: the wider family it belongs to - Lake-town Toymaker's own "if you've
#: drawn two or more cards this turn", the identical clause a dozen "as long
#: as you've drawn ... cards this turn" static abilities print (Evangel of
#: Synthesis, Eyekite, Messenger Hawk, and others - read elsewhere as a
#: static condition, not here). A general count comparison over CR 121.2's
#: individual draws this turn (`Game.cards_drawn_this_turn`, incremented once
#: per card drawn), the same four comparison words `_COUNTER_COUNT_CLAUSE`/
#: `_CONTROLLED_SUBTYPE_COUNT` already read for a counter or subtype count -
#: `_COUNTER_COMPARISONS` (below) is the shared answer all three read.
_DRAWN_CARD_COUNT_CLAUSE = re.compile(
    r"^you(?:'ve| have) drawn "
    rf"(?:(?P<comparison>fewer than|more than|at least|exactly) (?P<count>{COUNT})"
    rf"|(?P<suffix_count>{COUNT}) or (?P<direction>more|fewer))"
    r" cards? this turn$"
)


def _drawn_card_count_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_DRAWN_CARD_COUNT_CLAUSE`'s shape, or `None` if the clause is not it.

    Answered from `Game.cards_drawn_this_turn` - the same running per-player
    draw count `_NTH_DRAW_CONDITION`'s own ordinal reading already uses for
    "you draw your Nth card in a turn"'s triggered shape; this is the
    intervening-*if* twin, over a comparison rather than an exact ordinal.
    """
    match = _DRAWN_CARD_COUNT_CLAUSE.match(clause)
    if match is None:
        return None
    if match.group("suffix_count") is not None:
        count_word, comparison = match.group("suffix_count"), match.group("direction")
    else:
        count_word, comparison = match.group("count"), match.group("comparison")
    wanted = parse_count(count_word, article=False)
    if wanted is None:
        return None
    controller = source.controller or game.active_player.username
    drawn = getattr(game, "cards_drawn_this_turn", None)
    if not isinstance(drawn, dict):
        return None
    on_turn = drawn.get(controller, 0)
    return _COUNTER_COMPARISONS[comparison](on_turn, wanted)


def _spells_cast_this_turn_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_SPELLS_CAST_THIS_TURN`'s shape, or `None` if the clause is not it.

    Answered from `Game.spells_cast_this_turn`, the running list this engine
    already keeps for Alania, Divergent Storm's own "the first instant spell
    ... you've cast this turn" - counted at the moment each spell was cast,
    and emptied as a new turn begins.

    "You" is the ability's own controller. Each recorded spell is measured by
    its printed card types (CR 205.2a): the object it was as a spell is long
    gone from the stack by the time this is asked, and CR 400.7 leaves
    whatever it became with no memory of that existence, so the printing is
    the only thing left to read - which is exact here, since no card in the
    pool changes an instant into a sorcery or back.

    Returns `None`, not `False`, for a count word this does not know, so the
    caller still fails closed and records the gap rather than silently
    answering "no".
    """
    match = _SPELLS_CAST_THIS_TURN.match(clause)
    if match is None:
        return None
    wanted = parse_count(match.group("count"), article=False)
    if wanted is None:
        return None
    controller = source.controller or game.active_player.username
    cast = game.spells_cast_this_turn.get(controller, [])
    if match.group("types") is None:
        return len(cast) >= wanted
    wanted_types: set[Type] = set()
    for word in re.split(r",|\band\b|\bor\b", match.group("types")):
        word = word.strip()
        if not word:
            continue
        card_type = next((t for t in Type if t.value == word.rstrip("s")), None)
        if card_type is None:
            return None
        wanted_types.add(card_type)
    if not wanted_types:
        return None
    matching = sum(
        1 for state in cast if wanted_types & set(state.types_as_a_spell(state.card.types))
    )
    return matching >= wanted


#: "if no spells were cast last turn" - the werewolves' transform condition
#: (Duskwatch Recruiter, and every other card printed with this line).
_NO_SPELLS_LAST_TURN = re.compile(r"^no spells were cast last turn$")
#: "if a player cast two or more spells last turn" - the mirror condition on
#: the back face (Krallenhorde Howler), asked of *each* player separately: one
#: player casting two is what it wants, not two spells between them.
_SPELLS_CAST_LAST_TURN = re.compile(r"^a player cast (?P<count>\w+) or more spells last turn$")

#: Valakut, the Molten Pinnacle's clause: "you control at least five other
#: Mountains". A board count of permanents with a named subtype (CR 205.3i's
#: land types here, but the shape is subtype-generic), optionally excluding the
#: ability's own source - which is what "other" means, and what makes Valakut
#: need *six* Mountains on the battlefield rather than five.
#:
#: `clause` reaches this lowercased, so the subtype cannot be told apart by
#: capitalization the way `_ENTERING_SUBTYPE` tells it apart. That is safe
#: here: the clause names the thing being counted and nothing else, and a
#: card-type word ("creatures", "lands") is counted correctly by
#: `_controlled_subtype_count_holds`'s own card-type branch rather than being
#: mistaken for a subtype.
#: Vraska, the Cutting Glare's own ETB clause: "if you control six or more
#: lands" - the same count-a-card-type shape as Valakut's above, but printed
#: with the count-word suffix rather than a leading comparison word, mirroring
#: how `_COUNTER_COUNT_CLAUSE` reads both "fewer than four ... counters" and
#: "five or more ... counters" as the same underlying comparison.
_CONTROLLED_SUBTYPE_COUNT = re.compile(
    r"^you control "
    r"(?:(?P<comparison>at least|more than|fewer than|exactly) (?P<count>[a-z]+)"
    r"|(?P<suffix_count>[a-z]+) or (?P<direction>more|fewer))"
    r" (?P<other>other )?(?P<subtype>[a-z]+?)s$"
)

#: How each comparison word in `_CONTROLLED_SUBTYPE_COUNT` answers.
_SUBTYPE_COUNT_COMPARISONS = {
    "at least": operator.ge,
    "more than": operator.gt,
    "fewer than": operator.lt,
    "exactly": operator.eq,
    "more": operator.ge,
    "fewer": operator.le,
}


def _controlled_subtype_count_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """CR 603.4's clause as "how many <subtype>s do you control right now".

    Valakut, the Molten Pinnacle's "if you control at least five other
    Mountains". Two things make this more than a name count:

    - **CR 613.5** - the subtypes counted are the *computed* ones, so every
      land is a Mountain while Blood Moon is out, and every land you control is
      one while Dryad of the Ilysian Grove is. That is the whole Valakut combo,
      and reading `CardState.subtypes` here would miss all of it.
    - **CR 608.2a** - this same clause is asked again as the ability resolves,
      and the count is taken live both times, so a board that shrank in between
      answers False the second time and the ability is removed from the stack
      doing nothing.

    "Other" excludes the source itself (CR 700.4's "other" is "any object
    other than the object being referred to"). `None`, not False, when the
    clause is not this shape, so anything else still reaches `_fail_closed`.
    """
    match = _CONTROLLED_SUBTYPE_COUNT.match(clause)
    if match is None:
        return None
    comparison_word = match.group("comparison")
    if comparison_word is not None:
        wanted = parse_count(match.group("count"), article=False)
    else:
        comparison_word = match.group("direction")
        wanted = parse_count(match.group("suffix_count"), article=False)
    if wanted is None:
        return None

    subtype = match.group("subtype")
    controller = source.controller or game.active_player.username
    card_type = _card_type_for_word(subtype)

    count = 0
    for state in game.permanents_controlled_by(controller):
        if match.group("other") and state.id == source.id:
            continue
        characteristics = game.characteristics_of(state)
        if card_type is not None:
            if card_type in characteristics.types:
                count += 1
        elif any(word.lower() == subtype for word in characteristics.subtypes):
            count += 1

    return _SUBTYPE_COUNT_COMPARISONS[comparison_word](count, wanted)


def _card_type_for_word(word: str) -> Type | None:
    """The CR 300.1 card type a counted noun names, or `None` for a subtype.

    "you control at least three other creatures" counts a card type; "at least
    five other Mountains" counts a subtype (CR 205.3i). The two are counted off
    different fields of the computed characteristics, so they have to be told
    apart before counting.
    """
    for kind in Type:
        if kind.value == word:
            return kind
    return None


def _spells_cast_last_turn_holds(game: "Game", clause: str) -> bool | None:
    """The two "last turn" spell-count clauses, or None if this is neither.

    Both are ordinary CR 603.4 intervening *if* clauses, and both are answered
    from `Game.spells_cast_last_turn` - the snapshot taken as a turn begins,
    counting each spell at the moment it was cast (CR 601.2a, CR 601.2i).
    """
    if _NO_SPELLS_LAST_TURN.match(clause):
        return not any(game.spells_cast_last_turn.values())

    match = _SPELLS_CAST_LAST_TURN.match(clause)
    if match is not None:
        wanted = parse_count(match.group("count"), article=False)
        if wanted is None:
            return None
        return any(len(cast) >= wanted for cast in game.spells_cast_last_turn.values())

    return None


def event_subject_power(game: "Game", event: "GameEvent | None") -> int | None:
    """The power of `event`'s own subject - the creature that died, entered,
    attacked, or whatever else the event names (CR 603.2) - or `None` when
    there is no event, no subject, or the subject cannot be found at all.

    Reads `CardState.power` directly rather than `Game.power_of`
    (`computed_board().of(...)`, CR 613.5's layer system): a dead or
    otherwise departed subject is not part of any battlefield the layer
    system computes over, and `CardState.power` already falls back to
    `last_known_power` (CR 608.2h) the moment the object leaves the
    battlefield, the same last-known-information convention
    `intervening_if_holds`'s own "it had no -1/-1 counters on it" clause
    reads for a dying creature's counters. Shared by Drizzt Do'Urden's own
    "the difference" between a dying creature's power and its own
    (`machines/effects.py`'s `_parse_put_counters_equal_to_clause`) and
    Gruff Triplets' own "a number of +1/+1 counters equal to its power" on
    its own dies trigger - the same dying-creature's-power read, used two
    different ways.
    """
    if event is None or event.subject_id is None:
        return None
    subject = game.find_by_id(event.subject_id)
    if subject is None:
        return None
    return subject.power


def _fail_closed(game: "Game", ability: TriggeredAbility, source: CardState) -> bool:
    """Record CR 603.4/608.2a's refusal and answer false - never true - for a
    clause this module cannot currently read, whether that is because nothing
    here recognises its shape or because the `CastRecord` it needs is gone
    (see `_cast_record_for_clause`). Shared so every unreadable clause leaves
    the same trail on `game.intervening_if_notices`.
    """
    game.intervening_if_notices.append(
        InterveningIfNotice(
            source_id=source.id,
            source_name=source.name,
            clause=ability.intervening_if or "",
        )
    )
    return False


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
    from .keywords import keyword_triggered_abilities

    printed = [
        ability
        for ability in parse_abilities(card)
        if isinstance(ability, TriggeredAbility)
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
        for split in _expand_attacks_or_blocks(ability):
            for enters_split in _expand_enters_or_attacks(
                split, card.name, legendary=Supertype.LEGENDARY in card.supertypes
            ):
                for leaves_split in _expand_enters_or_leaves(enters_split):
                    expanded.extend(
                        _expand_enters_or_dies(
                            leaves_split,
                            card.name,
                            legendary=Supertype.LEGENDARY in card.supertypes,
                        )
                    )
    return expanded + keyword_triggered_abilities(card)


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


def _expand_attacks_or_blocks(ability: TriggeredAbility) -> list[TriggeredAbility]:
    """One ability whose condition is `_ATTACKS_OR_BLOCKS_RE`'s shape becomes
    two: the same printed effect, once watching CR 508.1's attack and once
    watching CR 509.1's block, each a `TriggeredAbility` in its own right so
    `triggers_for`/`condition_matches` need no special case for a compound
    condition - this is the only place that reads "attacks or blocks" as two
    separate self-referential conditions rather than as raw text.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    match = _ATTACKS_OR_BLOCKS_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    kind = match.group("kind").lower()
    return [
        ability.model_copy(
            update={"condition": f"this {kind} attacks", "event": TriggerEvent.ATTACKS}
        ),
        ability.model_copy(
            update={"condition": f"this {kind} blocks", "event": TriggerEvent.BLOCKS}
        ),
    ]


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
_ENTERS_OR_ATTACKS_RE = re.compile(r"^this (?P<kind>[a-z]+) enters or attacks$", re.IGNORECASE)


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
        if isinstance(ability, ActivatedAbility) and (face is None or ability.face == face)
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
    printed = [line.strip() for line in (permanent.oracle_text or "").splitlines() if line.strip()]
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
    """
    if permanent.zone is not Zone.BATTLEFIELD:
        return ()
    try:
        computed = game.characteristics_of(permanent)
    except KeyError:
        return ()
    printed = {line.strip() for line in (permanent.oracle_text or "").splitlines() if line.strip()}
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
    from .keywords import granted_keyword_triggered_abilities

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
                expanded.extend(_expand_enters_or_leaves(enters_split))
    return expanded + granted_keyword_triggered_abilities(texts)


def controller_of_source(game: "Game", source: CardState) -> str:
    """Whose "you" a trigger on `source` means (CR 109.5, 108.4, 108.4a).

    CR 109.5: "The words 'you' and 'your' on an object refer to the object's
    controller, its would-be controller (if a player is attempting to play,
    cast, or activate it), or its owner (if it has no controller)."

    CR 108.4: "A card doesn't have a controller unless that card represents a
    permanent or spell", and CR 108.4a: "If anything asks for the controller
    of a card that doesn't have one (because it's not a permanent or spell),
    use its owner instead."

    So the zone is what decides, not whether `CardState.controller` happens
    to be filled in: a card on the battlefield is a permanent and a card on
    the stack is a spell, and each has a real controller. A card anywhere
    else - in exile, in a graveyard, in a hand or a library - has none, and
    its owner answers instead. `CardState.controller` is not cleared by
    `move_to` and a scenario can stage an exiled card with one still on it,
    so reading it first would have quietly kept the stale value.

    This is what makes CR 702.62a's "at the beginning of *your* upkeep" the
    **owner's** upkeep for a suspended card - a card another player exiled
    with time counters (Suspended Sentence's own last line, cast by somebody
    else) still ticks on its owner's turn, exactly as `machines/casting.
    finish_suspend` already reads "you" for the third ability.

    The active player is the last resort, for a card with neither: nothing in
    a real game reaches it, since CR 108.3 gives every card in the game an
    owner.
    """
    if source.zone in (Zone.BATTLEFIELD, Zone.STACK):
        return source.controller or game.active_player.username
    return source.owner or source.controller or game.active_player.username


def triggered_abilities_on(game: "Game", source: CardState) -> list[TriggeredAbility]:
    """Every triggered ability `source` has right now, printed and granted,
    before any condition is read - the abilities `triggers_for` asks."""
    # CR 400.7b / CR 611.3d: an ability granted to this object is had by
    # this object, so it is asked here alongside the card's own printed
    # ones. Never *instead* of them - a grant adds.
    granted = granted_triggered_abilities_of(source.granted_ability_texts)
    # CR 613.5 / CR 707.2: a permanent whose computed ability text has been
    # rewritten by a layer 1 copy effect has the *copied* object's triggers
    # and not its own, so the printed card is the wrong thing to read.
    # `rewritten_ability_lines` answers None whenever nothing was taken
    # away, which is every ordinary permanent.
    rewritten = rewritten_ability_lines(game, source)
    if rewritten is not None:
        granted = granted_triggered_abilities_of(rewritten)
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
        had.append(ability)
    return had


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
                if source.zone not in zones_ability_functions_in(ability, source):
                    continue  # CR 113.6: doesn't function from the zone it's in.
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
_ONE_OR_MORE_ATTACK_RE = re.compile(
    r"^one or more (?P<description>.+?) attack(?:\s+(?P<defender>.+))?$", re.IGNORECASE
)
_ONE_OR_MORE_ATTACK_YOURS = re.compile(r"\byou control\b", re.IGNORECASE)

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


def is_batched_attack_condition(condition: str) -> bool:
    """Whether `condition` is "one or more `<description>` attack[
    `<defender>`]" - one trigger for a whole declaration
    (`batched_attackers`)."""
    return _ONE_OR_MORE_ATTACK_RE.fullmatch(condition.strip()) is not None


def _defender_controller_of(game: "Game", attacker: CardState) -> str | None:
    """Whoever controls what `attacker` is attacking - a player directly, or
    a planeswalker's controller (CR 506.4a) - the same resolution
    `Game._emit_attack_event` already does for `GameEvent.defender_
    controller`, read here off `Game.combat` directly since a delayed or
    printed group condition is checked before any one attacker's own event
    exists yet."""
    attack = game.combat.attack_by(attacker.id)
    if attack is None:
        return None
    if attack.defender.is_player:
        return attack.defender.username
    if attack.defender.card_id is not None:
        defending_permanent = game.find_by_id(attack.defender.card_id)
        if isinstance(defending_permanent, CardState):
            return game.controller_of(defending_permanent).username
    return None


def batched_attackers(game: "Game", condition: str, controller: str) -> list[CardState] | None:
    """The attacking creatures a "one or more `<description>` attack[
    `<defender>`]" condition counts, or `None` when `condition` is not that
    shape, its description does not read (`machines/targeting.
    permanent_description`, the grammar a "target" phrase uses, with "you
    control" read here as the attackers' own controller), or it names a
    defender phrase this reader does not recognise (`_DEFENDER_OPPONENT_RE`)
    - fail closed rather than ignore an unread qualifier."""
    match = _ONE_OR_MORE_ATTACK_RE.fullmatch(condition.strip())
    if match is None:
        return None
    from .targeting import permanent_description

    description = match.group("description")
    yours = _ONE_OR_MORE_ATTACK_YOURS.search(description) is not None
    requirement = permanent_description(_ONE_OR_MORE_ATTACK_YOURS.sub("", description).strip())
    if requirement is None:
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
        and requirement.rejects(attacker, controller, game) is None
        and (
            not opponent_only
            or (
                (defender_controller := _defender_controller_of(game, attacker)) is not None
                and defender_controller != controller
            )
        )
    ]


#: "one or more `<description>` deal combat damage to `<recipient>`" - Jacob
#: Frye's "one or more Assassins you control deal combat damage to a player",
#: Invasion Tactics' "one or more Allies you control ...", Professional
#: Face-Breaker's "one or more creatures you control ...". The plural "deal"
#: is the batch: CR 603.2c's one trigger for the step's damage (see
#: `ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS`), where the singular "a
#: creature you control deals combat damage" is one trigger per creature
#: (`TriggerEvent.DEALS_DAMAGE`).
_ONE_OR_MORE_DEAL_COMBAT_DAMAGE_RE = re.compile(
    r"^one or more (?P<description>.+?) deal combat damage to "
    r"(?P<recipient>a player|an opponent|one of your opponents)$",
    re.IGNORECASE,
)

#: A bare list of plural subtypes - "Assassins", "Allies", "Scouts, Pirates,
#: and/or Rogues" - split on its own separators.
_SUBTYPE_LIST_SEPARATOR_RE = re.compile(
    r"\s*(?:,\s*(?:and/or|and|or)?|\band/or\b|\bor\b|\band\b)\s*"
)


def _singular_subtype(plural: str) -> str | None:
    """`plural` as a subtype in CR 205.3's vocabulary, singular and
    lower-cased, or `None`. English plurals the subtype list actually uses:
    a bare "s" (Assassins), "ies" (Allies), "ves" (Elves, Wolves), and the
    Latin "Fungi"."""
    lowered = plural.lower()
    vocabulary = {word.lower() for word in subtype_vocabulary()}
    candidates = [lowered]
    if lowered.endswith("ies"):
        candidates.append(lowered[:-3] + "y")
    if lowered.endswith("ves"):
        candidates.append(lowered[:-3] + "f")
    if lowered.endswith("s"):
        candidates.append(lowered[:-1])
    if lowered == "fungi":
        candidates.append("fungus")
    return next((candidate for candidate in candidates if candidate in vocabulary), None)


def _bare_subtype_list(description: str) -> frozenset[str] | None:
    """The singular subtypes a bare plural-subtype description names, or
    `None` when any item is not a subtype on its own."""
    items = [item for item in _SUBTYPE_LIST_SEPARATOR_RE.split(description.strip()) if item]
    singular = [_singular_subtype(item) for item in items]
    if not singular or any(item is None for item in singular):
        return None
    return frozenset(item for item in singular if item is not None)


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
        from .targeting import permanent_description

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


def _event_for(
    game: "Game", ability: TriggeredAbility, controller: str, event: GameEvent
) -> GameEvent:
    """The event this ability carries onto the stack: `event` itself, or -
    for a batched "one or more `<description>` attack" trigger - a copy
    whose `amount` is how many attackers fit the description, the count
    this ability's own "that many" reads (CR 603.2c)."""
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
            event=_event_for(game, ability, controller, event),
        )
        triggered.append(on_stack)
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

#: The gate half of `_ADDITIONAL_TRIGGER_RE`: "an artifact or creature entering".
_ENTERING_CAUSE_RE = re.compile(r"^an? (?P<types>[a-z ]+?) entering$", re.IGNORECASE)


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


def _entering_cause_matches(game: "Game", cause: str, event: GameEvent) -> bool:
    """Whether this event is the "artifact or creature entering" the multiplier
    names (CR 603.2d's own "an ability may state that a triggered ability
    triggers additional times" is gated by the rest of the printed sentence)."""
    match = _ENTERING_CAUSE_RE.match(cause.strip())
    if match is None or event.event is not TriggerEvent.ENTERS_THE_BATTLEFIELD:
        return False
    wanted = {word.strip().lower() for word in match["types"].split(" or ") if word.strip()}
    entering = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    if isinstance(entering, CardState):
        try:
            types = game.characteristics_of(entering).types
        except KeyError:
            types = tuple(entering.types)
    elif event.subject_card is not None:
        types = tuple(event.subject_card.types)
    else:
        return False
    return bool(wanted & {str(card_type).lower() for card_type in types})


def additional_trigger_times(
    game: "Game", ability: AbilityOnStack, source: CardState, event: GameEvent
) -> int:
    """How many *extra* times this ability triggers, by CR 603.2d.

    CR 603.2d: "An ability may state that a triggered ability triggers
    additional times. In this case, rather than simply determining that such an
    ability has triggered, determine how many times it should trigger, then
    trigger it that many times."

    Every permanent on the battlefield is asked whether one of its own static
    ability lines is a multiplier of this shape, read off the *computed* text
    (CR 613.5). Panharmonicon is the only printing in the pool. Its own gate is
    checked here rather than assumed: the ability's source has to be a permanent
    the Panharmonicon's controller controls, and the event has to be an artifact
    or creature entering.

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
        if controller is None or controller != ability.controller:
            continue  # "a triggered ability of a permanent **you** control".
        for line in _computed_ability_lines(game, permanent):
            match = _ADDITIONAL_TRIGGER_RE.match(line.strip())
            if match is None:
                continue
            if _entering_cause_matches(game, match["cause"], event):
                extra += 1
    return extra


#: CR 603.8's own shape: The Millennium Calendar's "When there are 1,000 or
#: more time counters on The Millennium Calendar, sacrifice it and each
#: opponent loses 1,000 life." and Mazemind Tome's "When there are four or more
#: page counters on this artifact, ...". The count is any `numbers.COUNT` -
#: digits with digit-group commas (which `machines/abilities._split_top_level`
#: already refuses to read as the CR 603.1 condition/effect boundary) or a
#: spelled-out word.
_STATE_COUNTER_TRIGGER_RE = re.compile(
    rf"^there are (?P<count>{COUNT}) or more (?P<kind>.+?) counters on (?P<subject>.+?)$",
    re.IGNORECASE,
)


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


def _state_condition_holds(game: "Game", ability: TriggeredAbility, source: CardState) -> bool:
    """Whether this permanent's game state matches its CR 603.8 condition."""
    match = _STATE_COUNTER_TRIGGER_RE.match(ability.condition.strip())
    if match is None:
        return False
    subject = match["subject"].strip().rstrip(".").lower()
    names = {source.name.lower(), "it", "this permanent", "this creature", "this artifact"}
    with contextlib.suppress(KeyError):
        names.add(game.characteristics_of(source).name.lower())
    if subject not in names:
        # A condition about some *other* object is not something this matcher
        # can read; answering False keeps CR 603.2's "only if it actually
        # matches" rather than guessing.
        return False
    needed = parse_count(match["count"], article=False)
    if needed is None:
        return False
    return source.counters[match["kind"].strip().lower()] >= needed


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

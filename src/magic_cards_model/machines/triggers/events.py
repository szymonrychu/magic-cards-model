from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Literal, NamedTuple
from uuid import UUID

from pydantic import ConfigDict, Field

from ...ids import new_id
from ...models.card import Card, Color, Type
from ...models.card_state import CardState, ExileAnnotation, TargetRef
from ...models.token import TokenState
from ...models.zone import Zone
from ...snapshot import EngineModel
from ..abilities import (
    AbilityKind,
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    parse_mana_count,
    self_counter_mana_count,
)
from ..turn import Step

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ...models.game import Game

    # `.cost` imports names from this module and `.keywords` imports
    # `AbilityOnStack` itself, so neither can be imported for real up here -
    # `keyword_activation`/`unless_payment` below carry these as string
    # annotations, and `keywords.py`'s own `model_rebuild()` call, run once
    # both classes exist, is what resolves them for real.
    from ..cost import CostPayment
    from ..keywords import KeywordActivation


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
    #: "Whenever a time counter is removed from this card while it's exiled"
    #: (Aeon Chronicler, Roiling Horror): every time counter a suspended card
    #: loses, the last one included. `GameEvent.subject_id` is the card.
    #: **Emitted by:** `machines/casting.remove_suspend_time_counter`.
    TIME_COUNTER_REMOVED = "time_counter_removed"
    #: "When the last `<kind>` counter is removed from this permanent" for
    #: any other counter kind - a Siege's intrinsic defeat trigger (CR
    #: 310.12b) is the one that needs it. Raised by `CardState.remove_counters`
    #: itself (through `Game.note_last_counter_removed`) whenever a removal
    #: takes a permanent's count of a kind from above zero to zero, whatever
    #: removed them - damage to a battle (CR 120.3h), a cost, an effect -
    #: with `GameEvent.counter_kind` naming the kind.
    LAST_COUNTER_REMOVED = "last_counter_removed"
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
    #: names alongside waterbend, each raised by `machines/effects.
    #: _record_bending`: earthbend as its delayed return is created (CR
    #: 701.66b), firebend as a firebending ability resolves (CR 702.189b),
    #: airbend once per instruction that exiled anything (CR 701.65b).
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
    #: God-Eternal Kefnet: "You may reveal the first card you draw each turn as
    #: you draw it" - a card revealed through that static ability, linked to
    #: its "Whenever you reveal an instant or sorcery card this way" trigger
    #: (CR 607.2h). `subject_id` is the revealed card, `player` the drawer.
    #: **Emitted by:** `Game.draw_cards`, through `Game._offer_first_draw_
    #: reveals`, and nowhere else.
    REVEALED_FIRST_DRAW = "revealed_first_draw"
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
    #: CR 702.29c: "'When you cycle this card' means 'When you discard this
    #: card to pay an activation cost of a cycling ability.'" - and CR
    #: 702.29f makes a typecycling ability a cycling ability. Its own event
    #: rather than `TriggerEvent.DISCARDS_A_CARD`, which a cycling discard
    #: *also* raises (the cost is a discard, CR 701.9a): a card discarded by
    #: an effect was discarded but never cycled. `GameEvent.subject_id` is
    #: the cycled card, `GameEvent.player` who cycled it. **Emitted by:**
    #: `machines/keywords.KeywordActivation` once a cycling or typecycling
    #: activation is on the stack, its cost paid.
    CYCLED = "cycled"
    #: CR 702.143c: "If an effect refers to foretelling a card, it means
    #: performing the special action associated with a foretell ability" -
    #: raised once that special action (CR 116.2h) has exiled the card.
    #: `GameEvent.subject_id` is the foretold card, `GameEvent.player` who
    #: foretold it. **Emitted by:** `MarkedExile.take` for the foretell marker.
    FORETOLD = "foretold"
    #: CR 602.2: "To activate an ability is to put it onto the stack and pay
    #: its costs" - raised for every activated ability that does that, and
    #: so never for a mana ability (CR 605.3b: it does not use the stack).
    #: Flamescroll Celebrant's and Burning-Tree Shaman's "Whenever
    #: `<a player>` activates an ability that isn't a mana ability" watch it.
    #: `GameEvent.subject_id`/`subject_types` are the ability's source as it
    #: was activated, `GameEvent.origin_zone` the zone that source was in
    #: (CR 109.2 reads "an ability of a creature" as a creature *on the
    #: battlefield*), `GameEvent.player` who activated it. **Emitted by:**
    #: `Game.activate_ability` (every battlefield ability, loyalty included)
    #: and `machines/keywords.KeywordActivation` (cycling, equip and every
    #: other keyword activation), once the ability is on the stack.
    ABILITY_ACTIVATED = "ability_activated"
    #: CR 731.1a: "'day becomes night' and 'night becomes day' refer to the
    #: game losing the first designation and gaining the second one" - so
    #: neither-to-day or neither-to-night is neither event. No subject and no
    #: player: the designation is the game's own (CR 731.1). **Emitted by:**
    #: `Game.set_day_night`, only when a designation is replaced.
    DAY_BECOMES_NIGHT = "day_becomes_night"
    NIGHT_BECOMES_DAY = "night_becomes_day"
    #: CR 701.54d: "Some abilities trigger 'Whenever the Ring tempts you.' The
    #: Ring tempts a player whenever they complete the actions in 701.54a,
    #: even if some or all of those actions were impossible." Nazgul's
    #: "Whenever the Ring tempts you, put a +1/+1 counter on each Wraith you
    #: control". `GameEvent.player` is the player tempted, `GameEvent.
    #: subject_id` the creature they chose as Ring-bearer (`None` when they
    #: controlled none), `GameEvent.amount` how many times the Ring has now
    #: tempted them. **Emitted by:** `Game.ring_tempts`, and nowhere else.
    RING_TEMPTS_YOU = "ring_tempts_you"
    #: CR 702.154b: enlist's own linked trigger - Guardian of New Benalia's
    #: "Whenever this creature enlists a creature, scry 2." `GameEvent.
    #: subject_id` is the *enlisting* creature (CR 700.7's "this creature"),
    #: not the one it taps. **Emitted by:** `machines/enlist.apply_enlist`.
    ENLISTS = "enlists"
    #: CR 701.26a's tapping, as CR 603.2c's one event for every permanent one
    #: instruction, cost or declaration tapped together: Rewrite History's
    #: "Whenever one or more creatures you control become tapped" and Deeproot
    #: Pilgrimage's "one or more nontoken Merfolk you control". Which
    #: permanents were in the batch is `Game.tapped_batch`, live only while
    #: this event is being matched. **Emitted by:** `Game.
    #: announce_batched_events`, from what `CardState.tap`/`.tap_if_untapped`
    #: noted (`Game.note_permanent_tapped`).
    PERMANENTS_TAPPED = "permanents_tapped"
    #: CR 400.6's "put into a graveyard", as CR 603.2c's one event for every
    #: card moved there together: Robot Domination's "Whenever one or more
    #: creature cards are put into your graveyard from anywhere" and Crawling
    #: Infestation's "... from anywhere during your turn". Which cards is
    #: `Game.graveyard_batch` (`GraveyardArrival` records), live only while
    #: this event is being matched. **Emitted by:** `Game.
    #: announce_batched_events`, off `Game.graveyard_arrivals_this_turn`.
    PUT_INTO_GRAVEYARD = "put_into_graveyard"
    #: CR 700.13: "A player commits a crime as that player casts a spell,
    #: activates an ability, or puts a triggered ability on the stack and
    #: that spell or ability targets at least one opponent; at least one
    #: permanent, spell, or ability an opponent controls; and/or at least one
    #: card in an opponent's graveyard." Magda, the Hoardmaster's "Whenever
    #: you commit a crime, ..." and Forsaken Miner's identical condition.
    #: `GameEvent.player` is the player who committed it. `machines/
    #: conditions/history.record_crime` already stamps the turn-scoped fact
    #: an intervening "if" reads ("you've committed a crime this turn"); this
    #: is the same action's own event, for a trigger to watch. **Emitted
    #: by:** `machines/conditions/history.record_crime`, the instant it finds
    #: a qualifying target - once per crime-committing action, never once per
    #: qualifying target (CR 700.13 is about the action, not the count).
    CRIME_COMMITTED = "crime_committed"
    #: CR 701.23a: "To search for a card in a zone, look at all cards in that
    #: zone, either mentally or by looking at each card." Wan Shi Tong,
    #: Librarian's "Whenever an opponent searches their library, ..." and Ob
    #: Nixilis, Unshackled's identical condition. `GameEvent.player` is the
    #: player who searched. **Emitted by:** `Game.search_library`, once per
    #: search (CR 701.23a's own "look at all cards in that zone" is one
    #: action, regardless of how many finds it allows).
    SEARCHES_LIBRARY = "searches_library"
    #: CR 706.2: a player rolled one or more dice (Barbarian Class's "Whenever
    #: you roll one or more dice"). `GameEvent.player` is who rolled.
    #: **Emitted by:** `Game.roll_dice`, once per roll instruction.
    ROLLS_DICE = "rolls_dice"
    #: CR 709.5h: "Some abilities trigger when a player unlocks a particular
    #: half of a permanent. These abilities trigger when that permanent is
    #: given the appropriate unlocked designation, regardless of whether it
    #: was given that designation while entering the battlefield or after
    #: entering the battlefield." Ritual Chamber's "When you unlock this
    #: door, ..." and Central Elevator // Promising Stairs' identical
    #: condition on its own "Central Elevator" door. `GameEvent.subject_id`
    #: is the permanent, `GameEvent.subject_name` the door's own face name
    #: (`BaseAbility.face`, matched against the printed ability's own face so
    #: only the door that was actually unlocked triggers), `GameEvent.player`
    #: who unlocked it. **Emitted by:** `Game.enter_the_battlefield` (CR
    #: 709.5d's cast-half unlock) and `Game.unlock_door` (CR 709.5e's special
    #: action and CR 709.5f's "unlock" instruction alike).
    DOOR_UNLOCKED = "door_unlocked"
    #: "whenever you solve a Case" (Case File Auditor; CR 719.3a-b: a Case
    #: "becomes solved", the solved designation). `GameEvent.subject_id` is
    #: the Case, `GameEvent.player` its controller, the player who solved it.
    #: **Emitted by:** `machines/designations.parse_becomes_solved_clause`,
    #: the resolution of every Case's "To solve" end-step trigger.
    CASE_SOLVED = "case_solved"


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

    subject_stamp: UUID | None = None
    """The subject's own `CardState.zone_change_stamp` at the moment of the
    event - CAST_SPELL's own (`Game._put_on_stack`), so `_cast_trigger_x_
    value`/`_cast_trigger_mana_spent_x_value` can read `Game.cast_record_as_
    last_known` off it once the cast spell has left the stack (CR 608.2h): a
    countered spell moves to its owner's graveyard (CR 701.6a), which stamps
    a new `zone_change_stamp` and makes `Game.cast_record_of` - keyed by the
    *current* stamp - find nothing, even though the Oracle ruling for these
    cast triggers (Hydroid Krasis, Genesis Hydra, Old Stickfingers,
    Geometer's Arthropod) is that the trigger still resolves with the cast
    X. `subject_id` alone is not enough: `Game.find_by_id` still finds the
    same card object after it moves, so a caller that read `cast_record_of`
    off it directly (rather than through this stamp) got `None` back with no
    signal anything was wrong."""

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

    tapped_for_teamwork: bool = False
    """For a `BECOMES_TAPPED` event, whether the tap paid a `machines/
    teamwork.py` Teamwork cost specifically - Agent Maria Hill's own
    "Whenever Agent Maria Hill becomes tapped **to pay a teamwork cost**,
    ..." asks about the *reason* she was tapped, not merely that she was,
    the same way "deals **combat** damage" narrows `combat` above rather
    than matching any damage event. Set by `machines/cost.CostComponent.
    pay`'s own `ComponentKind.TAP` branch off the `TEAMWORK_TAP` description
    `pay_teamwork` alone gives its component - so an equip cost, a
    convoke tap, or any other ordinary tap cost leaves this `False`."""

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

    loyalty_removed: int | None = None
    """On a `LOYALTY_ABILITY_ACTIVATED` event: how many loyalty counters the
    activation's cost actually removed (CR 606.4 - the symbol's cost as
    modified and combined, CR 606.5), 0 for a `[+N]` or `[0]`. Way of the Mind
    Sculptor's "if you removed two or more loyalty counters to activate it"
    reads this on the event and again on resolution (CR 603.4), so the second
    check never depends on the board."""

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

    declared_attacker: bool = False
    """`TriggerEvent.BECOMES_TAPPED` for a creature tapped because it was
    declared as an attacker (CR 508.1f: "attacking simply causes creatures to
    become tapped") - Verity Circle's "if it isn't being declared as an
    attacker" (`machines/conditions/objects.py`) asks exactly this, of the
    event itself, so CR 608.2a's recheck reads the same answer."""

    during_cost_of: str | None = None
    """`"spell"` or `"ability"` when this happened while that spell's
    (CR 601.2h) or ability's (CR 602.2b) total cost was being paid - the
    creature an emerge cost sacrificed, the permanents a craft cost exiled -
    stamped by `Game.emit` from `Game.paying_cost_of`. A trigger event's own
    "while casting a spell with emerge" / "while you're activating a craft
    ability" qualifier reads this (CR 603.2,
    `machines/conditions/events.py`)."""

    during_cost_keyword: str | None = None
    """The keyword that spell was cast with, or that ability expands,
    lowercased (CR 702.119a's emerge, CR 702.167a's craft)."""

    during_cost_player: str | None = None
    """Who was paying that cost - the player casting or activating."""

    keyword_action: str | None = None
    """The keyword action this event happened during, when that is what a
    trigger event's own "while <doing it>" qualifier asks: `"scry"` for a
    `TriggerEvent.LIBRARY_BOTTOM_CHOSEN` made while scrying (CR 701.22a)."""

    mana_ability: bool = False
    """`ExtraTriggerEvent.ABILITY_ACTIVATED` for a mana ability (CR 605.3a:
    it is activated; CR 605.3b: without the stack) - a condition printed
    "that isn't a mana ability" must not meet it, and one that does not say
    so (Elrond, Moon-Reader's "Whenever you activate an ability of a
    creature") does."""

    counters_put_index: int | None = None
    """For a `COUNTERS_PUT` event, which of `Game.counters_put_this_turn`'s
    placements it reports (its position there) - what "if it's the first
    time counters have been put on that permanent this turn" (CR 122.6) asks
    of the event, and still asks on resolution (CR 608.2a) after more
    placements, identical in kind, amount and putter, may have followed."""

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

    entered_together: tuple[tuple[UUID, Zone | None], ...] = ()
    """For a `TriggerEvent.ENTERS_THE_BATTLEFIELD` event raised inside
    `Game.entering_together` with more than one permanent in it, every
    permanent that entered in that one event, each with the zone it came
    from - CR 603.6a: "Each time an event puts one or more permanents onto
    the battlefield, all permanents on the battlefield (including the
    newcomers) are checked for any enters-the-battlefield triggers that match
    the event." A "one or more ... enter" trigger's "them" (Twilight
    Diviner's "a copy of one of them", Kambal, Profiteering Mayor's "for each
    of them") is read off this: the members that match the ability's own
    condition. Empty when the permanent entered on its own - then "them" is
    `subject_id` alone."""


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
    source_times_transformed: int | None = None
    """The source's `CardState.times_transformed` when the ability triggered
    or was activated - the count CR 701.27f compares: an activated or
    triggered ability of a permanent that tries to transform it does so "only
    if it hasn't transformed or converted since the ability was put onto the
    stack". A count, not a face, so a permanent turned over twice in response
    (back where it started) is still recognised as having transformed. `None`
    for an ability that records no source object."""
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

    cost_sacrificed_color_counts: tuple[int, ...] = ()
    """`cost_sacrificed_card_ids`' colour counts, aligned by position and taken
    by `Game.activate_ability` as this object is created, for the same reason
    `cost_sacrificed_mana_values` is (CR 608.2h's last known information; a
    sacrificed token has ceased to exist, CR 704.5d, by resolution) - Evolving
    Door's "Count the colors of the sacrificed creature" (CR 105.1)."""

    cost_sacrificed_powers: tuple[int | None, ...] = ()
    """`cost_sacrificed_card_ids`' powers, aligned by position and taken by
    `Game.activate_ability` as this object is created - CR 608.2h's last known
    information for "the sacrificed creature's power". Pumps, counters and
    anthems are in it, and it survives a sacrificed token ceasing to exist
    (CR 704.5d). `None` where the creature's power was not a number."""

    cost_sacrificed_toughnesses: tuple[int | None, ...] = ()
    """`cost_sacrificed_powers`' toughness twin."""

    mana_spent: dict[Color, int] = Field(default_factory=dict)
    """How much mana of each colour paid this ability's own activation cost
    (CR 601.2h, imported for activation by CR 602.2b), taken from `machines/
    cost.ManaPayment.spend` the same moment `Game.activate_ability` reads
    `cost_sacrificed_card_ids`/`cost_exiled_card_ids` off the same settled
    payment - Paragon of Modernity's own "If exactly three colors of mana
    were spent to activate this ability, put a +1/+1 counter on it instead."
    `CastRecord.mana_spent` is the identical field for a *cast* spell; an
    activated ability was never cast (CR 601.2a) and has no `CastRecord` of
    its own, so this is where its own activation's payment is remembered.
    Empty for a mana ability (CR 605.3b never builds an `AbilityOnStack` at
    all) or one activated with no open `CostPayment` to read back."""

    treasure_mana_spent: int = 0
    """How much of `mana_spent` came from a Treasure (CR 106.3's source of
    mana), from `ManaPayment.treasure_spent` - Jetmir's Fixer's own "If mana
    from a Treasure was spent to activate this ability, put a +1/+1 counter
    on this creature instead." `CastRecord.treasure_mana_spent`'s activation
    twin, for the identical reason `mana_spent` is `CastRecord.mana_spent`'s."""

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


def event_subject_or_source(game: "Game", ability: AbilityOnStack) -> CardState | None:
    """The object a triggered ability's own pronoun subject names - "it deals
    damage equal to its power" (Stalking Vengeance's dying creature), "that
    creature deals ..." (Pyrotechnic Performer's creature turned face up),
    "that Archer deals ..." (Greatbow Doyen's damage dealer).

    CR 603.2: the trigger event is what the effect refers back to, so the
    referent is the event's subject - which is the ability's own source only
    when the condition is self-referential ("When this creature dies, it
    deals ..."). A subject still on the stack is the spell a cast trigger
    watched (heroic's "a spell that targets this creature"), never what a
    damage-dealing pronoun names, so that falls back to the source, as does
    an ability with no event (an activation) or a subject that cannot be
    found. The object is returned in whatever zone it is now; CR 608.2h's
    last-known read of it is `object_stat_or_last_known`'s job.
    """
    event = ability.event
    if event is not None and event.subject_id is not None:
        subject = game.find_by_id(event.subject_id)
        if isinstance(subject, CardState) and subject.zone is not Zone.STACK:
            return subject
    return ability.source_or_last_known(game)


def object_stat_or_last_known(game: "Game", obj: CardState, stat: str) -> int:
    """`obj`'s power or toughness as an effect is applied (CR 608.2h): through
    the layer system while it is on the battlefield (CR 613.5), otherwise its
    last known information, which `CardState.power`/`.toughness` fall back to
    once it has left (CR 113.7a). A negative value reads as 0 (CR 107.1b).

    `CardState.last_known_power_toughness` adds the counters it left with
    back to the printing when no snapshot was taken."""
    if obj.zone is Zone.BATTLEFIELD:
        value = game.power_of(obj) if stat == "power" else game.toughness_of(obj)
    else:
        power, toughness = obj.last_known_power_toughness()
        value = power if stat == "power" else toughness
    return max(value or 0, 0)


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


class TriggerReadability(StrEnum):
    """Whether a printed condition is one of the shapes this module can read."""

    READ = "read"
    UNREAD = "unread"


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


def mana_ability_activated_event(source: CardState, game: "Game") -> GameEvent:
    """`ExtraTriggerEvent.ABILITY_ACTIVATED` for a mana ability of `source`
    that was just activated (CR 605.3a) - raised beside CR 106.12a's own tap
    event by both places a mana ability resolves (`Game.activate_ability`'s
    fast path and `CostPayment.tap_for_mana`), `mana_ability=True` so a
    "that isn't a mana ability" condition is not met."""
    on_battlefield = source.zone is Zone.BATTLEFIELD
    characteristics = game.characteristics_of(source) if on_battlefield else None
    controller = game.controller_of(source).username
    return GameEvent(
        event=ExtraTriggerEvent.ABILITY_ACTIVATED,
        subject_id=source.id,
        subject_name=source.name,
        subject_controller=controller,
        subject_card=source.card,
        subject_types=tuple(characteristics.types if characteristics else source.types),
        subject_subtypes=tuple(characteristics.subtypes if characteristics else source.subtypes),
        origin_zone=Zone.BATTLEFIELD,
        player=controller,
        mana_ability=True,
    )


def resolution_key(ability: "AbilityOnStack") -> str:
    """The key `Game.ability_resolutions_this_turn` counts one ability's
    resolutions under: its source as that object (CR 400.7 - a source that
    changed zones is a new object, `source_stamp`) and its own text, so two
    abilities of one permanent are counted apart."""
    return f"{ability.source_id}:{ability.source_stamp}:{ability.ability.text}"


class _TypedWhose(NamedTuple):
    """A parsed "whose": `equipped` for "equipped creature", else a list of
    `(another, words)` alternatives among the multiplier controller's own."""

    equipped: bool
    alternatives: tuple[tuple[bool, tuple[str, ...]], ...]
    #: "... you control of the chosen type": the source must also be the
    #: creature type the multiplier chose as it entered (CR 614.12a, 205.3m).
    chosen: bool = False

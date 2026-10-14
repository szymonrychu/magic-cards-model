import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from random import Random
from typing import TYPE_CHECKING
from uuid import NAMESPACE_OID, UUID, uuid5

from ...ids import install_id_allocator, reset_id_allocator
from ...machines import combat as combat_rules
from ...machines.abilities import (
    AbilityKind,
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    parse_abilities,
)
from ...machines.casting import (
    annotate_exile,
    search_cast_candidates,
)
from ...machines.casting_restrictions import (
    draw_cap_restriction,
    search_prohibition_source,
)
from ...machines.combat import (
    keywords_as_it_exists,
)
from ...machines.cost import plan_mana_payment, total_cost_for_phrase
from ...machines.decisions import (
    CardSplit,
    Decision,
    DecisionKind,
    source_id_of,
)
from ...machines.keyword_counters import (
    consume_shield_counter,
    enters_with_counters_pronoun_fallback,
    has_shield_counter,
)
from ...machines.keywords import (
    apply_as_enters_day_night,
    apply_daybound_nightbound,
    dredge,
    dredge_count,
    enters_transformed_at_night,
    first_draw_reveal_is_mandatory,
    first_draw_reveal_own_turns_only,
    granted_keyword_triggered_abilities,
    has_first_draw_reveal,
    is_indestructible,
    keyword_triggered_abilities,
    why_cannot_dredge,
)
from ...machines.layers import (
    ContinuousEffect,
    Layer,
    grant_ability,
    only_this_incarnation,
    plays_lands_from_graveyard_line,
)
from ...machines.player_action_prohibitions import (
    discard_caused_by_opponent,
    library_search_blocked,
    sacrifice_caused_by_opponent,
)
from ...machines.replacement import (
    EventKind,
    NextTimeDrawReplacement,
    ReplaceableEvent,
    apply_replacements,
)
from ...machines.revealed_information import additional_looks
from ...machines.spell_grants import granted_hand_keyword_lines
from ...machines.triggers import (
    AbilityOnStack,
    ExtraTriggerEvent,
    GameEvent,
    triggers_for,
)
from ...machines.zone_grants import effective_card
from ...snapshot import command
from ..card import (
    Card,
    Type,
)
from ..card_state import (
    CardState,
    Counter,
    ExileAnnotation,
    ExileMarker,
)
from ..player import Player
from ..token import (
    copiable_card_of,
    is_token,
    move_refused,
)
from ..zone import Zone
from ._common import Targetable
from .records import ExileArrival, GraveyardArrival, Reveal

if TYPE_CHECKING:
    from . import Game


def _exiles_itself_by_name(text: str, permanent: "CardState") -> bool:
    """Whether `text` is "Exile `<permanent's own printed name>`" - CR 201.5's
    other self-reference form: "If an object's text uses the object's own
    name, it's referring to that object, even if there are other objects with
    the same name." The Stone Brain's own "Exile The Stone Brain" (and
    Abstergo Entertainment's "Exile Abstergo Entertainment") is the pool's
    only example of this on a cost line; `_SELF_REFERENCE` only ever catches
    the "this `<type>`" spelling (CR 700.7), not a bare printed name.

    An exact match (case-insensitive) on "exile `<name>`" alone, not a
    substring search - a cost line naming some *other* object by name (a
    hypothetical "Exile a card named `<X>`") is a different shape entirely and
    must not be waved through as if it referred to `permanent`.

    CR 700.7's type-word self-reference is the same cost on a permanent:
    Relic of Progenitus's "Exile this artifact", Brittle Effigy's too.
    `_PHRASE_EXILE` reads the common type words itself; this is the fallback
    for the ones it does not (battle, Equipment, Vehicle, Aura), reached only
    when `cost_component_for_phrase` returned nothing.
    """
    lowered = text.strip().rstrip(".").lower()
    if _EXILE_THIS_PERMANENT.fullmatch(lowered):
        return True
    return lowered == f"exile {permanent.name.lower()}"


#: "Exile this <permanent type word>" (CR 700.7) as a cost.
_EXILE_THIS_PERMANENT = re.compile(
    r"exile this (?:artifact|creature|enchantment|land|permanent|planeswalker|battle"
    r"|equipment|vehicle|aura)"
)


#: Ral, Monsoon Mage's own back-face intrinsic (CR 306.5b's own "additional"
#: shape, layered on top of the printed loyalty number rather than replacing
#: it): "enters with an additional loyalty counter on him/her/it/them for
#: each instant and sorcery spell you've cast this turn." Generalized on the
#: pronoun; the spell-type qualifier is read narrowly (this is the one
#: printing in the pool) but by the words "instant"/"sorcery" rather than by
#: card name, so a future card naming a different type pairing the same way
#: is not silently mismatched onto this one's amount.
_ADDITIONAL_LOYALTY_PER_INSTANT_SORCERY_RE = re.compile(
    r"enters with an additional loyalty counter on (?:it|him|her|them) for each "
    r"instant and sorcery spell you'?ve cast this turn",
    re.IGNORECASE,
)


#: CR 605.1a's fourth criterion, read off the printed text: a word that means a
#: card is moving to or from a library. "Draw" draws from one, "mill" puts
#: library cards into the graveyard, "search" takes cards out of one, "surveil"
#: moves the top card of one, and the bare word "library" is in the list so a
#: phrasing this list does not name is still caught rather than guessed at.
_LIBRARY_MOVEMENT = re.compile(r"\b(draw|mill|search|surveil|library)\b", re.IGNORECASE)


def moves_a_library_card(ability: ActivatedAbility) -> bool:
    """Whether the ability's printed cost or effect moves a card to or from a
    library (CR 605.1a's fourth criterion).

    CR 605.1a: an activated ability is not a mana ability if "its cost and
    effect don't move any card to or from a library" fails - a mill- or
    draw-for-mana ability resolves as an ordinary activated ability, on the
    stack and counterable. The rule also says "Do not take into account
    replacement effects that may apply, other than self-replacement effects,
    when evaluating these criteria", and this does exactly that: the criteria
    are evaluated on the printed text and nothing else - no replacement is
    consulted, so there is no self-replacement to make an exception for.

    The check is honest about being a heuristic over the printed line: the
    words above are the ones the oracle text of a card-moving ability prints.
    A printing that *mentions* the library without moving a card - "reveal the
    top card of your library" moves nothing - would be classified as not a
    mana ability; no known printing of that shape is also an `Add` ability,
    which is what `ability.mana` gates this check behind.
    """
    return _LIBRARY_MOVEMENT.search(ability.raw) is not None


def entered_type_facts(types: object, subtypes: object) -> list[str]:
    """The `turn_facts` keys an entering permanent records for its controller:
    one per card type (CR 205.2a) and one per subtype (CR 205.3), lowercased
    - "entered_type:artifact", "entered_subtype:hero"."""
    return [f"entered_type:{str(kind).lower()}" for kind in (types or ())] + [
        f"entered_subtype:{str(word).lower()}" for word in (subtypes or ())
    ]


#: A sentence that prohibits drawing but is not either shape above - matched
#: only to fail closed with a notice, exactly as
#: `_LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE` does for its own twin.
_LOOKS_LIKE_DRAW_PROHIBITION_RE = re.compile(r"\bcan't draw cards\b", re.IGNORECASE)


class ZonesMixin:
    def _allocate_id(self: "Game") -> UUID:
        """One `uuid5(game_uid, objects_created)` id - see `game_uid`'s own
        docstring for why identity, not `shuffle_seed`, is the namespace, and
        `objects_created`'s for why this is installed per call rather than
        once."""
        allocated = uuid5(NAMESPACE_OID, f"{self.game_uid}:{self.objects_created}")
        self.objects_created += 1
        return allocated

    @contextmanager
    def _id_allocator_scope(self: "Game") -> Iterator[None]:
        """Install `_allocate_id` as this context's id allocator for the
        span of the `with` block, restoring whatever was installed before on
        exit - `objects_created`'s own docstring is why every mutating public
        method needs this rather than installing once for the object's whole
        life.

        Every one of those methods opens its own `with self._id_allocator_
        scope():` rather than sharing one scope across a whole request:
        `install_id_allocator` returns the `ContextVar` `Token` `reset_id_
        allocator` needs, so nesting is safe by construction - an inner
        scope's exit restores the outer scope's allocator (this same one,
        when both belong to the same game) rather than clobbering it with
        `None`. `pass_priority` calling `resolve_top`, which is also called on
        its own by another caller, is exactly this shape.
        """
        token = install_id_allocator(self._allocate_id)
        try:
            # A mutating command: no board is cached while it runs, whatever
            # order it edits lists and assigns fields in, and its end
            # invalidates every scope on this game in any thread
            # (`snapshot.command`).
            with command(self):
                yield
        finally:
            reset_id_allocator(token)

    @property
    def battlefield(self: "Game") -> list[CardState]:
        """The shared battlefield. Only cards ever live here, never abilities."""
        return self.shared_zones[Zone.BATTLEFIELD]  # type: ignore[return-value]

    @property
    def exile(self: "Game") -> list[CardState]:
        return self.shared_zones[Zone.EXILE]  # type: ignore[return-value]

    # -- phasing (CR 702.26) -----------------------------------------------

    def _attached_to_recursively(self: "Game", host: CardState) -> list[CardState]:
        """Everything on the battlefield attached to `host`, and to those in
        turn - the objects CR 702.26g phases out along with it."""
        found: list[CardState] = []
        frontier = [host.id]
        while frontier:
            host_id = frontier.pop()
            for state in self.battlefield:
                if state.attached_to == host_id and state not in found:
                    found.append(state)
                    frontier.append(state.id)
        return found

    def tap_permanent(self: "Game", permanent: CardState) -> bool:
        """Tap `permanent` as an effect instructs, if it is untapped
        (`CardState.tap_if_untapped`), raising "becomes tapped" when it
        actually does (CR 701.26a). Returns whether it tapped."""
        if not permanent.tap_if_untapped():
            return False
        self.emit_became_tapped(permanent)
        return True

    def _find_card_named_anywhere(self: "Game", card_name: str) -> CardState | None:
        """The first card by this name in *any* zone this game can see.

        `_trigger_source_named`'s own battlefield-and-stack search answers
        "where would this trigger actually fire from right now" (CR 603.6a,
        603.2g) - the right, narrow question for the engine's own use of it.
        `why_cannot_target_with_trigger` asks a different question when that
        search comes up empty: "is this card's own printed ability even
        capable of legally targeting this" - answerable from the card's text
        alone, wherever the card currently sits, since a hand card about to
        be cast prints the identical ability a battlefield one would. This
        is what lets a scenario script a trigger's targets before casting
        the card without silently skipping validation for it.
        """
        front = card_name.split("//")[0].strip()

        def matches(state: CardState) -> bool:
            return state.name in (card_name, front) or state.name.split("//")[0].strip() == front

        for zone_cards in self.shared_zones.values():
            for state in zone_cards:
                if isinstance(state, CardState) and matches(state):
                    return state
        for player in self.players:
            for zone_cards in player.zones.values():
                for state in zone_cards:
                    if matches(state):
                        return state
        return None

    def _take_out_of_every_zone(self: "Game", card_state: CardState) -> None:
        """Lift a card out of wherever it currently is, shared zones included.

        A card about to leave exile is noted as having been put there first
        (`machines/conditions/history.note_exile_arrivals`), so a card exiled
        and taken back out before anything else happened still counts."""
        if card_state.zone is Zone.EXILE:
            from ...machines.conditions import history as condition_history

            condition_history.note_exile_arrivals(self)
        for player in self.players:
            for zone_cards in player.zones.values():
                if card_state in zone_cards:
                    zone_cards.remove(card_state)
        for zone_cards in self.shared_zones.values():
            if card_state in zone_cards:
                zone_cards.remove(card_state)

    def _note_left_battlefield(self: "Game", permanent: CardState) -> None:
        """Record Revolt's own condition: a permanent left the battlefield
        this turn (an ability word, CR 207.2c - Fatal Push's own printed
        wording, "a permanent left the battlefield under your control this
        turn", names no further numbered rule).

        Called by every route a permanent takes off the battlefield -
        `destroy`/`sacrifice` (through `put_into_graveyard`), `exile_permanent`,
        `return_to_hand` - at the point each already knows the move started
        there, before the move itself runs. Recorded regardless of where the
        permanent ends up: a replacement effect that redirects the destination
        (Rest in Peace) still moved it *off* the battlefield first, and Revolt
        asks only about leaving, not about arriving anywhere in particular.
        Controller, not owner - CR 108.4a's fallback is for a card with no
        controller at all, which a battlefield permanent always has.
        """
        # CR 608.2h: "If an effect requires information from the game ... the
        # answer is determined only once, when the effect is applied." An
        # effect that has to ask about a permanent which is no longer one -
        # Momentous Fall's "You draw cards equal to the sacrificed creature's
        # power", whose sacrifice CR 601.2h paid before the spell was even on
        # the stack - has nothing left to read once the continuous effects
        # stop applying. This is the last instant they still do.
        permanent.remember_last_known_power_toughness()
        # CR 707.2 for a look-back copy ("a copy of it", Ochre Jelly's Split):
        # a copy effect stops applying once it is not a permanent.
        copiable = copiable_card_of(self, permanent)
        permanent.last_known_copiable = None if copiable is permanent.card else copiable
        permanent.note_departure_epoch(self._departure_epoch)
        if permanent in self.battlefield:
            self._left_battlefield_characteristics[permanent.id] = self.characteristics_of(
                permanent
            )
        # CR 702.90d / 702.80b: the same last instant for its keywords - an
        # ability of this permanent that deals damage after it has gone (Mogg
        # Fanatic's own sacrifice cost) asks whether it had infect or wither
        # as it last existed, grants included.
        permanent.last_known_keywords = keywords_as_it_exists(permanent, self)
        # CR 506.4 removes it from combat as it goes; whether it was attacking
        # as it last existed is what "by attacking creatures" asks (CR 608.2h).
        permanent.last_known_attacking = self.is_attacking(permanent)
        # CR 400.7: whatever comes back is a new object, never goaded.
        permanent.goaded_by = []
        if permanent.prepared:
            # CR 722.3c: the exile copy persists "for as long as the prepared
            # permanent remains on the battlefield and has the prepared
            # designation" - both halves of that end together the moment the
            # permanent itself leaves, so this is the one choke point every
            # route off the battlefield already reaches.
            self.become_unprepared(permanent)
        if permanent.monstrous:
            # CR 701.37b: "Once a permanent becomes monstrous, it stays
            # monstrous until it leaves the battlefield." There is no
            # "becomes unmonstrous" effect anywhere in the rules to call a
            # dedicated unsetter from (unlike `prepared`'s own
            # `become_unprepared`, which real cards do invoke directly) - the
            # designation's only end is this one, so it is cleared right
            # here, the same choke point every route off the battlefield
            # already reaches. A blink (exile then return) leaves through
            # here and comes back as a new object with no memory of it
            # (CR 400.7), so a blinked monstrous permanent is not monstrous.
            permanent.monstrous = False
            permanent.monstrous_x = None
        controller = permanent.controller
        # Void's "a nonland permanent left the battlefield this turn" asks
        # what the permanent *was* as it left (CR 603.10a), whoever
        # controlled it and wherever it went - exile and a library included,
        # which the graveyard/hand entries `machines/conditions/history`
        # writes from events never see. Read by that module's
        # "left the battlefield" reader.
        self.turn_history.append(
            TurnHistoryEntry(
                kind="left_battlefield",
                player=controller,
                owner=permanent.owner,
                object_id=permanent.id,
                characteristics=self._left_battlefield_characteristics.get(permanent.id)
                or self.characteristics_of(permanent),
                face_down=permanent.face_down,
            )
        )
        if controller is None:
            return
        self.permanents_left_battlefield_this_turn[controller] = (
            self.permanents_left_battlefield_this_turn.get(controller, 0) + 1
        )

    def cards_put_into_graveyard_this_turn(
        self: "Game",
        player: str,
        *,
        from_zone: Zone | None = None,
        permanent_only: bool = False,
    ) -> int:
        """How many cards reached `player`'s graveyard this turn, from
        `graveyard_arrivals_this_turn`'s ledger.

        `from_zone=Zone.LIBRARY` answers a mill's own "cards put into a
        graveyard from a library this turn"; `permanent_only=True` answers
        CR 700.11's Descend - "the number of permanent cards put into [a
        player]'s graveyard from anywhere this turn" - reading `arrival.
        is_permanent_card` (CR 110.4a's printed-type question, true "from
        anywhere" and not only for an arrival straight off the battlefield)
        rather than `arrival.permanent_types` (which answers a narrower,
        computed-characteristics question and is `None` for a card that
        skipped the battlefield entirely). Both filters compose, and neither
        filter given counts every arrival, permanent or not."""
        return sum(
            1
            for arrival in self.graveyard_arrivals_this_turn
            if arrival.player == player
            and (from_zone is None or arrival.origin_zone is from_zone)
            and (not permanent_only or arrival.is_permanent_card)
        )

    def _additional_entering_loyalty(self: "Game", card_state: CardState) -> int:
        """Ral, Monsoon Mage's back face: "Ral enters with an additional
        loyalty counter on him for each instant and sorcery spell you've
        cast this turn." CR 306.5b's intrinsic "enters with N loyalty
        counters" (`CardState._enter_with_loyalty`, applied by `move_to`
        before this is ever called) only ever reads the printed number - it
        has no `Game` to ask a dynamic "for each ... this turn" question of,
        so the additional half is read here instead, off whichever face is
        now up, generalized on the spell types named rather than pinned to
        this one printing.

        Read from `card_state.oracle_text` - which already reads the back
        face once `CardState.transform`/`move_to(transformed=True)` has
        flipped it up - so this only ever finds Ral's own sentence on Ral,
        and finds nothing on every other permanent, transformed or not.
        """
        if not card_state.is_planeswalker:
            return 0
        text = card_state.oracle_text or ""
        match = _ADDITIONAL_LOYALTY_PER_INSTANT_SORCERY_RE.search(text)
        if match is None:
            return 0
        controller = card_state.controller or self.active_player.username
        cast = self.spells_cast_this_turn.get(controller, [])
        return sum(
            1 for spell in cast if Type.INSTANT in spell.types or Type.SORCERY in spell.types
        )

    def _entering_counters(
        self: "Game", card_state: CardState, intrinsic: dict[str, int], event: ReplaceableEvent
    ) -> dict[str, int]:
        """Every counter `card_state` enters with, summed by kind: its own
        intrinsic ones (CR 306.5b, CR 310.4b, CR 714.3a), whatever "enters
        with" replacements added to the event (CR 614.1c), Ral, Monsoon
        Mage's additional loyalty, less compleated's reduction.

        All of them are one entering event (CR 614.1c), and putting them on
        is the event contained within it (CR 616.1g) that CR 122.6 makes
        "counters being put on" the object - so each kind is put on once,
        through `add_counters`, where Doubling Season, Vorinclex and "that
        many plus one" apply to the whole count and Solemnity stops it.

        CR 702.150a (compleated) is "enters the battlefield with that many
        loyalty counters minus two for each": it modifies the entering event
        itself, so the reduction comes off before any counter-placing
        replacement sees the count, and never below zero (CR 107.1b).
        """
        counters = dict(intrinsic)
        for kind, amount in event.counters.items():
            counters[kind] = counters.get(kind, 0) + amount
        loyalty = str(Counter.LOYALTY)
        extra_loyalty = self._additional_entering_loyalty(card_state)
        if extra_loyalty:
            counters[loyalty] = counters.get(loyalty, 0) + extra_loyalty
        if event.loyalty_reduction and loyalty in counters:
            counters[loyalty] = max(counters[loyalty] - event.loyalty_reduction, 0)
        return {kind: amount for kind, amount in counters.items() if amount > 0}

    def enter_the_battlefield(
        self: "Game",
        card_state: CardState,
        controller: str,
        *,
        tapped: bool = False,
        transformed: bool = False,
        was_cast: bool,
        attach_to: "Targetable | None" = None,
        counters: Mapping[str, int] | None = None,
    ) -> CardState:
        """A permanent enters the battlefield, replacement effects first (CR 614.12).

        Every route onto the battlefield runs through here: a permanent spell
        resolving, a land being played, a card put there by an effect. CR 614.1c
        and 614.1d make "[this] enters tapped", "[this] enters with N counters",
        and "[objects] enter ..." replacement effects, and CR 614.12 says such an
        effect "may come from the permanent itself if [it affects] only that
        permanent" - so the entering card's own text is consulted while it is
        still on its way in, alongside every effect already on the battlefield.

        A replacement may send it somewhere else entirely (Containment Priest).
        CR 614.6: the entering event then never happens, so nothing enters, no
        enters-the-battlefield ability triggers (CR 603.6a), and the counters and
        the tapped state the modified event was carrying are dropped with it.

        `attach_to` is CR 608.3c's half of the same event: a resolving Aura
        spell "becomes a permanent and is put onto the battlefield under the
        control of the spell's controller attached to the player or object it
        was targeting" - attached as it enters, not mutated afterwards, which is
        why it is applied here rather than by the caller. That is also what
        keeps a Containment Priest redirect honest: if the replacement above
        sends the event to exile or a graveyard instead, `event.destination` is
        no longer `Zone.BATTLEFIELD` and this returns before `attach_to` is ever
        touched, so nothing is left attached to something that never arrived.
        `resolve_top` is the caller, and it is the only one that passes this -
        every other route onto the battlefield leaves it `None` and this is a
        no-op, exactly the old behaviour.

        CR 303.4d says an Aura can't enchant itself, and if it somehow does
        anyway, "the Aura is put into its owner's graveyard" rather than the
        engine raising out of the middle of a spell's resolution - targeting
        already keeps this from happening in practice (an Aura spell cannot
        legally target itself), but the fallback is here so a caller that
        manages to ask for it fails onto a real rule instead of a crash.

        Counters the permanent arrives with are placed after it is on the
        battlefield, through `add_counters`, because CR 122.6 counts them as
        counters being put on the object and effects such as Doubling Season
        watch for exactly that - CR 616.1g's second event inside the first.

        CR 111.8 refuses the whole thing for a token that has already been to the
        battlefield and left: "it remains in its current zone instead". Nothing
        enters, so no replacement effect is consulted and no enters trigger fires
        (CR 603.6a) - the event never happened at all.
        """
        with self._id_allocator_scope():
            if move_refused(card_state, Zone.BATTLEFIELD) is not None:
                return card_state

            event = ReplaceableEvent(
                kind=EventKind.ENTERS_BATTLEFIELD,
                card=card_state,
                origin=card_state.zone,
                destination=Zone.BATTLEFIELD,
                tapped=tapped,
                was_cast=was_cast,
                counters=dict(counters or {}),
                transformed=(transformed or enters_transformed_at_night(self, card_state))
                and card_state.card.back_face is not None,
            )
            card_state.controller = controller
            # CR 614.12: which replacement applies is judged on the permanent
            # "as it would exist on the battlefield" - so CR 113.6c's
            # off-battlefield grant is already gone while they are asked.
            card_state._entering_battlefield = True  # noqa: SLF001
            try:
                apply_replacements(self, event)
            finally:
                card_state._entering_battlefield = False  # noqa: SLF001

            if event.destination is not Zone.BATTLEFIELD:
                self._take_out_of_every_zone(card_state)
                if event.destination is Zone.EXILE:
                    card_state.move_to(Zone.EXILE)
                    self.exile.append(card_state)
                else:
                    self._owner_of(card_state).add(card_state, event.destination or Zone.GRAVEYARD)
                    if (event.destination or Zone.GRAVEYARD) is Zone.GRAVEYARD:
                        self._record_graveyard_arrival(
                            card_state, origin_zone=event.origin, permanent_types=None
                        )
                return card_state

            if not event.counters:
                # `machines/replacement.py::_ENTERS_WITH`'s own trailing
                # group only ever reads "on it" - Captain America, Super-
                # Soldier's own "enters with a shield counter on him" is
                # UNPARSED there and places nothing. Not that file's to fix
                # this round; `enters_with_counters_pronoun_fallback` is the
                # supplemental reader, tried only when the ordinary pipeline
                # placed nothing at all, so a printing it already handles is
                # never double-counted. See that function's own docstring.
                fallback = enters_with_counters_pronoun_fallback(card_state.oracle_text)
                if fallback is not None:
                    kind, amount = fallback
                    event.counters[kind] = event.counters.get(kind, 0) + amount

            if (
                attach_to is not None
                and isinstance(attach_to, CardState)
                and attach_to.id == card_state.id
            ):
                # CR 303.4d: an Aura can't enchant itself - see the docstring above.
                self._take_out_of_every_zone(card_state)
                self._owner_of(card_state).add(card_state, Zone.GRAVEYARD)
                self._record_graveyard_arrival(
                    card_state, origin_zone=event.origin, permanent_types=None
                )
                return card_state

            self._take_out_of_every_zone(card_state)
            # CR 712.14a: "if a spell or ability puts a double-faced card onto the
            # battlefield 'transformed' ..., it enters the battlefield with its
            # back face up." Set *before* the move, because `move_to` is where
            # CR 306.5b's intrinsic "enters with loyalty counters equal to its
            # printed loyalty" is applied, and the printed loyalty a transformed
            # Ajani, Nacatl Pariah enters with is his back face's 3 - read off
            # whichever face is up. A card that has no back face is left alone
            # (CR 701.28c's "nothing happens" for the sibling action).
            # CR 702.145b: a daybound card entering at night enters transformed.
            transformed = transformed or enters_transformed_at_night(self, card_state)
            card_state.transformed = transformed and card_state.card.back_face is not None
            stamp_on_the_stack = card_state.zone_change_stamp
            card_state.move_to(Zone.BATTLEFIELD, place_intrinsic_counters=False)
            # CR 702.30a: a new object comes under its controller's control now.
            entered_under = card_state.stored_controller or controller
            card_state.controlled_since_upkeep = (
                entered_under,
                self.upkeeps_begun.get(entered_under, 0),
            )
            # CR 306.5b / CR 310.4b / CR 714.3a: read off the face now up,
            # before anything else changes what the object is. A permanent
            # entering as a copy has the copied object's instead (CR 707.2),
            # which `_enters_as_copy` already put on the event.
            intrinsic_counters = (
                card_state.intrinsic_entering_counters() if event.entering_as_copy is None else {}
            )
            if was_cast:
                # CR 400.7d: the permanent may read the spell it was, so the
                # record follows this one move and no later one.
                self._carry_cast_record(card_state, stamp_on_the_stack)
                # CR 702.176a asks "if this permanent's impending cost was paid"
                # of the permanent - see `CardState.cast_with_keyword`. Read off
                # the spell's own `CastRecord`, which `resolve_top` has not
                # popped yet; a permanent arriving any other way was never cast
                # for any cost (CR 400.7) and `move_to` has just cleared it.
                record = self.cast_record_of(card_state)
                card_state.cast_with_keyword = record.keyword if record is not None else None
            card_state.tapped = event.tapped
            if event.prepared:
                # CR 722.3a: "This creature enters prepared" (`ENTERS_PREPARED`
                # in `machines/replacement.py`). Applied after the move onto
                # the battlefield, same as counters below, since `become_
                # prepared` requires `permanent.zone is Zone.BATTLEFIELD`.
                self.become_prepared(card_state)
            # CR 702.131 (ascend): "entered this turn" needs a turn-number stamp,
            # not just a boolean, the same way `ExileAnnotation.turn_exiled` is -
            # see `CardState.turn_entered`. Stamped here, the one choke point
            # every route onto the battlefield runs through.
            card_state.turn_entered = self.turn.turns_taken if self.turn is not None else None
            # CR 613.5: from here on this permanent's power and toughness are
            # whatever the layer engine says they are. A characteristic-defining
            # ability (CR 604.3, 613.4a) gives Tarmogoyf a power the printing does
            # not have, and an anthem in layer 7d makes a Grizzly Bears a 3/3.
            # Unbound, `CardState.power` answers with the printed value plus
            # counters (CR 122.1a), which is the wrong answer for anything a
            # continuous effect touches - and combat's CR 510.1a assignment and
            # CR 704.5g's lethal check both read it directly.
            card_state.bind_to_game(self)
            self.battlefield.append(card_state)
            # CR 310.9a: "As a battle enters the battlefield, its controller
            # chooses a player to be its protector" (a Siege's from among
            # their opponents, CR 310.12a). A new object (CR 400.7) never
            # keeps an old protector. The printed up face, or an "enter as a
            # copy" choice (CR 614.1c, a layer-1 effect the printed face does
            # not show), gates the computed read, so any other non-battle
            # entering costs no board computation.
            card_state.protector = (
                combat_rules.choose_protector(self, card_state)
                if (Type.BATTLE in card_state.types or event.entering_as_copy is not None)
                and Type.BATTLE in self.characteristics_of(card_state).types
                else None
            )

            if was_cast and "Room" in card_state.subtypes:
                # CR 709.5d: "A permanent with a shared type line is given
                # the '[left/right] half unlocked' designation as it enters
                # the battlefield if its [that] half was cast as a spell."
                # `face_played` still names the cast half here - `move_to`
                # above never clears it (see its own docstring) - except
                # when the front half was cast with no explicit choice
                # (CR 709.3's choice is still made, just left at its own
                # default), where `Casting.cast` sets it back to `None`
                # unconditionally; the front face's own name is that
                # default (`test_split_cards.py`'s own "no face chosen
                # already reads as its front half"). Done only now, once
                # the permanent is actually on `self.battlefield` - `Game.
                # emit`'s own `sources` is read straight off that list, so
                # a door unlocked before this point would never be asked
                # about the very event it just caused.
                front_face = card_state.card.front_face
                cast_face = card_state.face_played or (
                    front_face.name if front_face is not None else card_state.card.name
                )
                self.unlock_door(card_state, cast_face, controller=controller)

            if attach_to is not None:
                card_state.attach_to(attach_to)  # CR 608.3c, 701.3a
            elif event.attach_to is not None and event.attach_to.zone is Zone.BATTLEFIELD:
                card_state.attach_to(event.attach_to)  # CR 614.12a, 701.3a

            # CR 613.7a: "a continuous effect generated by a static ability has the
            # same timestamp as the object the static ability is on". Stamped as it
            # arrives, so a permanent that entered after a spell resolved is
            # correctly newer than that spell's effect (CR 613.7b).
            self.continuous_effects.note(self.battlefield)

            for kind, amount in self._entering_counters(
                card_state, intrinsic_counters, event
            ).items():
                # CR 122.6a: no effect here names a putter, so it is the
                # entering object's controller.
                self.add_counters(card_state, kind, amount, putter=card_state.controller)
            for kind, putter, amount in event.counters_put_by:
                # CR 702.104a's tribute: the opponent is the one who puts them.
                self.add_counters(card_state, kind, amount, putter=putter)

            if event.grants_haste:
                # CR 702.136a's riot, declined: "it gains haste." No duration
                # is stated, so CR 611.2a's default is indefinite -
                # `only_this_incarnation`-scoped (CR 400.7) the same way dash's
                # `_grant_dash_haste` (CR 702.109a) and unearth's `_unearth_
                # effect` (CR 702.84a) already grant their own haste, so a
                # later re-entry is a new object and is asked again rather
                # than inheriting this incarnation's grant.
                store = self.continuous_effects
                store.add(
                    ContinuousEffect(
                        description=f"{card_state.name}: riot grants haste (CR 702.136a)",
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        selector=only_this_incarnation(card_state, card_state.zone_change_stamp),
                        modification=grant_ability("Haste"),
                    )
                )

            # CR 614.1c: "If it's neither day nor night, it becomes day as this
            # creature enters" - then CR 702.145d/g's "any time" checks, which
            # a daybound or nightbound newcomer may now satisfy.
            apply_as_enters_day_night(self, card_state)
            apply_daybound_nightbound(self)

            # CR 603.4's "if it entered from your graveyard" (Prized Amalgam,
            # Archfiend's Vessel) asks where the permanent came from - the
            # enters event carries it (`GameEvent.origin_zone`).
            self._entry_origins[card_state.id] = event.origin
            if self._entering_together is not None:
                self._entering_together.append(card_state)
                return card_state
            self._announce_entry(card_state)
            return card_state

    @contextmanager
    def entering_together(self: "Game") -> Iterator[None]:
        """Every permanent put onto the battlefield inside the block enters as one event.

        CR 603.6a: "Each time an event puts one or more permanents onto the
        battlefield, all permanents on the battlefield (including the
        newcomers) are checked for any enters-the-battlefield triggers that
        match the event." One instruction putting several cards is one event,
        so each newcomer's "whenever another creature enters" must see every
        other newcomer - which it only can if no enters event is raised until
        the last of them is there. A nested block joins the outer one.
        """
        if self._entering_together is not None:
            yield
            return
        self._entering_together = []
        try:
            yield
        finally:
            entered, self._entering_together = self._entering_together, None
        arrived = [card_state for card_state in entered if card_state.zone is Zone.BATTLEFIELD]
        batch = tuple(
            (card_state.id, self._entry_origins.get(card_state.id)) for card_state in arrived
        )
        self._entry_batch = batch if len(batch) > 1 else ()
        try:
            for card_state in arrived:
                self._announce_entry(card_state)
        finally:
            self._entry_batch = ()

    def put_onto_battlefield(
        self: "Game",
        card_state: CardState,
        controller: str,
        *,
        tapped: bool = False,
        transformed: bool = False,
        counters: Mapping[str, int] | None = None,
    ) -> CardState:
        """Put a card onto the battlefield without casting it (CR 110.2a).

        This is the Tooth and Nail path. CR 601.2 defines casting as taking a
        card "from where it is (usually the hand), put it on the stack, and pay
        its costs" - a card put straight onto the battlefield never does any of
        that, so no casting event occurs and CR 603.2's "an ability triggers only
        if its trigger event actually occurs" (CR 603.2g) means a "when you cast
        this spell" ability never fires. Enters-the-battlefield abilities do
        (CR 603.6a), because that event *did* happen.

        `transformed` is CR 712.14a's "onto the battlefield transformed": the
        permanent arrives with its back face up, and so with that face's
        characteristics from the moment it exists - including the printed
        loyalty CR 306.5b puts on as it enters, which is the only way a
        creature face like Ajani, Nacatl Pariah becomes a planeswalker with any
        loyalty at all.

        `counters` is the effect's own "it enters with N `<kind>` counters on
        it" (CR 614.1c) - Ochre Jelly's token copy's "half that many" - put on
        the entering event alongside every other entering counter.
        """
        with self._id_allocator_scope():
            return self.enter_the_battlefield(
                card_state,
                controller,
                tapped=tapped,
                transformed=transformed,
                was_cast=False,
                counters=counters,
            )

    def _bottom_for_keep(self: "Game", player: Player) -> list[CardState] | None:
        """Which cards this player puts on the bottom when they keep (CR 103.5).

        CR 103.5c and CR 800.6 both name the quantity - "the number of cards that
        player will put on the bottom of their library" - and `cards_to_bottom`
        computes it; *which* cards they are is the player's own choice.

        Asked as a `CHOOSE_CARDS` question through `Game.ask`, the same CR 608.2d
        machinery `ask_cleanup_discard` uses for CR 701.9b's discard, and
        deliberately **not** a new `DecisionKind`: "choose exactly N of these
        cards, from one zone, in an order that matters" is precisely what that
        kind already is, its `exact` validation already refuses a wrong-sized or
        stray-card answer, and every client that can already render a
        `CHOOSE_CARDS` question can render this one with no change.

        This one *is* a `Game.ask`, and it is the one place in the pregame that
        stays one: it is only reached for a player who has already mulliganed at
        least once, it has a correct default (the back of the hand, which is what
        `Player.keep_hand(None)` bottoms), and a client that wants a human to
        choose can script or provide the answer before the declaration that
        triggers it. Two properties that buys:

        - **The default is unchanged.** `default_answer` for an exact
          `CHOOSE_CARDS` returns "the back of `cards`, in the order the caller
          offered them", and the hand is offered here in hand order - byte for
          byte the list `Player.keep_hand(None)` builds. An unscripted,
          unprovided game bottoms exactly what it bottomed before, so every
          seeded replay holds.
        - **Nothing random happens here**, so the reshuffle seeds are untouched
          by asking.

        `None` is returned when there is nothing to bottom, so the question is not
        put at all - a choice among zero cards is not a choice.
        """
        needed = player.cards_to_bottom
        if needed <= 0:
            return None
        hand = list(player.hand)
        chosen = self.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"put {needed} card(s) on the bottom of your library",
                source_id=None,  # CR 103.5: the rules ask, not an object.
                amount=needed,
                cards=tuple(state.id for state in hand),
            )
        )
        assert isinstance(chosen, tuple)
        by_id = {state.id: state for state in hand}
        return [by_id[card_id] for card_id in chosen]

    # -- decisions made during resolution (CR 608.2d) -------------------------

    def _with_card_labels(self: "Game", decision: Decision) -> Decision:
        """Name the cards a question offers (`Decision.card_labels`).

        A question carries `CardState` ids in `cards` - the candidates of a
        `CHOOSE_CARDS`, the cards being looked at by a `SCRY` or a `SURVEIL`,
        the qualifying cards a `MAY` is about - and for a question about a
        *hidden* zone (CR 400.2: the library and the hand) a client
        holding the game state cannot turn those ids into cards - only the
        player looking at the zone may, and the whole point of asking is that
        they are being shown it. Ugin's Labyrinth published "you may exile a
        colorless card with mana value 7 or greater from your hand" to a live
        seat with nothing naming which cards qualified; the choice that follows
        it named them only by id.

        So the label travels with every question, filled in once here rather
        than at each of the thirty-odd askers - a caller that already built its
        own labels (`search_library`, `ask_trigger_order`, whose ids are not
        cards at all) keeps them untouched.

        All-or-nothing: if any id names nothing this game can find, the labels
        are left empty rather than misaligned, because `card_labels` is
        documented as positionally aligned with `cards` and a client indexing
        into a partial list would read the wrong name for the wrong card.
        """
        if decision.card_labels or not decision.cards:
            return decision
        states = [self.find_by_id(card_id) for card_id in decision.cards]
        if any(state is None for state in states):
            return decision
        return replace(decision, card_labels=tuple(state.name for state in states if state))

    def _look_at_top(self: "Game", player: Player, count: int) -> list[CardState]:
        """The top `count` cards, or as many as there are (CR 701.22a, 701.25a)."""
        return list(player.library[: max(count, 0)])

    def _split_top(
        self: "Game",
        player: Player,
        looked_at: list[CardState],
        answer: CardSplit,
    ) -> tuple[list[CardState], list[CardState]]:
        """Work an answer out into (moved away, put back on top), in order.

        "The rest on top of your library in any order" (CR 701.22a, CR 701.25a):
        an order the answer may state and, if it does not, the order they were
        looked at in - which keeps a rigged library rigged when the scenario
        did not ask for anything else.
        """
        by_id = {state.id: state for state in looked_at}
        moved = [by_id[card_id] for card_id in answer.moved if card_id in by_id]
        moved_ids = {state.id for state in moved}
        rest = [state for state in looked_at if state.id not in moved_ids]
        if answer.top_order is not None:
            ranked = {card_id: index for index, card_id in enumerate(answer.top_order)}
            rest.sort(key=lambda state: ranked.get(state.id, len(ranked)))
        return moved, rest

    def _look_before_choosing(
        self: "Game", player: Player, looked_at: list[CardState], source: str | None
    ) -> list[Reveal]:
        """Record the look that comes before the question, and return it.

        "Look at the top N cards of your library, then put" (CR 701.22a,
        CR 701.25a): the chooser has seen the cards, where they sit, while the
        choice of where each goes is still pending - a paused command's
        half-applied game must say so. The put-back ends these records
        (CR 701.20d), so `_end_looks` drops them there and the caller records
        what the chooser knows against the order the put-back makes: one look
        per card either way.
        """
        start = len(self.reveals)
        for state in looked_at:
            self.look(state, player.username, source=source)
        return self.reveals[start:]

    def _end_looks(self: "Game", looks: list[Reveal]) -> None:
        """Drop the records `_look_before_choosing` made (by identity)."""
        ended = {id(look) for look in looks}
        self.reveals[:] = [reveal for reveal in self.reveals if id(reveal) not in ended]

    def scry(
        self: "Game",
        player: Player | str,
        count: int,
        *,
        source: str | None = None,
        source_id: str | None = None,
    ) -> CardSplit:
        """Scry N (CR 701.22a).

        "To 'scry N' means to look at the top N cards of your library, then put
        any number of them on the bottom of your library in any order and the
        rest on top of your library in any order."

        CR 701.22b: "If a player is instructed to scry 0, no scry event occurs."
        So scry 0 asks nothing and this returns an empty split without recording
        a question - which is the only way a scenario can tell the two apart.

        CR 701.22c orders a simultaneous multi-player scry in APNAP order; no
        card in the pool scries more than one player at a time, so that path is
        not exercised. CR 701.22d's "whenever a player scries" trigger has no
        event to emit yet - see `docs/engine-coverage.md`.
        """
        with self._id_allocator_scope():
            if isinstance(player, str):
                player = self.player(player)
            if count <= 0:
                return CardSplit()
            # CR 701.22d has no rule number of its own to cite - the trigger
            # is a plain CR 603.2 "matches the event" question, and CR
            # 701.22b already draws the line this checks: scry 0 "is not a
            # scry event" at all. Denzilore Fatehold's and Matoya, Archon
            # Elder's own "Whenever you scry or surveil" is what reads this.
            # CR 701.22b's own "no scry event occurs" is also why the turn
            # fact below is recorded only past the count-0 refusal above
            # (Proctor of Potential's own "Activate only if you've scried or
            # surveilled this turn").
            # CR 701.22a: the scry looks at the top N cards (plus any extra the
            # effects in play add); the event carries that number for "for each
            # card looked at while scrying this way" (Celeborn the Wise).
            looks = count + additional_looks(self, player.username, "scry")
            self.emit(
                GameEvent(event=TriggerEvent.SCRY_OR_SURVEIL, player=player.username, amount=looks)
            )
            self.record_turn_fact("scried_or_surveilled", player.username)

            looked_at = self._look_at_top(player, looks)
            pending_looks = self._look_before_choosing(player, looked_at, source)
            answer = self.ask(
                Decision(
                    kind=DecisionKind.SCRY,
                    player=player.username,
                    prompt=f"scry {count}",
                    source=source,
                    source_id=source_id,
                    amount=count,
                    # CR 107.1c: "any number" of the cards looked at, zero included.
                    exact=False,
                    cards=tuple(state.id for state in looked_at),
                    # CR 701.22a's own two destinations, quoted above, so a client
                    # does not have to infer them from the kind.
                    moved_label="bottom of your library",
                    kept_label="top of your library",
                )
            )
            assert isinstance(answer, CardSplit)
            to_bottom, on_top = self._split_top(player, looked_at, answer)
            # CR 701.22a's "on the bottom of your library in any order" is
            # CR 401.4's arrangement, asked as its own question while the
            # look is still live; an unscripted seat keeps the named order.
            to_bottom = self.ask_library_bottom_order(
                player, to_bottom, source=source, source_id=source_id
            )
            self._end_looks(pending_looks)
            library = player.library
            for state in looked_at:
                library.remove(state)
            for index, state in enumerate(on_top):
                library.insert(index, state)
            library.extend(to_bottom)
            if on_top or to_bottom:
                # CR 701.20d: the scried cards are reordered; the cards below
                # them keep their order (CR 401.2), so their records stay.
                player.note_library_changed(placed=looked_at)
            # CR 701.20e: the scrier knows where each card went, against the
            # order the put-back just made - the next reordering ends it.
            for state in (*on_top, *to_bottom):
                self.look(state, player.username, source=source)
            if to_bottom:
                # CR 701.22a's choice to put cards on the bottom, as its own
                # event (The Temporal Anchor's "Whenever you choose to put one
                # or more cards on the bottom of your library while scrying").
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LIBRARY_BOTTOM_CHOSEN,
                        player=player.username,
                        amount=len(to_bottom),
                        keyword_action="scry",
                    )
                )
            return CardSplit(
                moved=tuple(state.id for state in to_bottom),
                top_order=tuple(state.id for state in on_top),
            )

    def surveil(
        self: "Game",
        player: Player | str,
        count: int,
        *,
        source: str | None = None,
        source_id: str | None = None,
    ) -> CardSplit:
        """Surveil N (CR 701.25a).

        "To 'surveil N' means to look at the top N cards of your library, then
        put any number of them into your graveyard and the rest on top of your
        library in any order."

        The same shape as a scry with a different destination, so it asks the
        same question - and CR 701.25c mirrors CR 701.22b exactly: surveil 0 is
        no surveil event at all.

        The cards go to the graveyard through `put_into_graveyard`, so a
        replacement effect watching that move (Rest in Peace, CR 614.1) gets its
        say - a surveil into a graveyard is a card being put into a graveyard.
        """
        with self._id_allocator_scope():
            if isinstance(player, str):
                player = self.player(player)
            if count <= 0:
                return CardSplit()
            # CR 701.25c mirrors CR 701.22b: surveil 0 "is not a surveil
            # event" either - see `scry`'s own emit for the rest. The turn
            # fact below is recorded only past this count-0 refusal, same
            # as scry's own.
            self.emit(GameEvent(event=TriggerEvent.SCRY_OR_SURVEIL, player=player.username))
            self.record_turn_fact("scried_or_surveilled", player.username)

            looked_at = self._look_at_top(
                player, count + additional_looks(self, player.username, "surveil")
            )
            pending_looks = self._look_before_choosing(player, looked_at, source)
            answer = self.ask(
                Decision(
                    kind=DecisionKind.SURVEIL,
                    player=player.username,
                    prompt=f"surveil {count}",
                    source=source,
                    source_id=source_id,
                    amount=count,
                    # CR 107.1c: "any number" of the cards looked at, zero included.
                    exact=False,
                    cards=tuple(state.id for state in looked_at),
                    # CR 701.25a's own two destinations, quoted above: the same
                    # "rest on top" as a scry, a different first half.
                    moved_label="your graveyard",
                    kept_label="top of your library",
                )
            )
            assert isinstance(answer, CardSplit)
            to_graveyard, on_top = self._split_top(player, looked_at, answer)
            self._end_looks(pending_looks)
            library = player.library
            for state in looked_at:
                library.remove(state)
            for index, state in enumerate(on_top):
                library.insert(index, state)
            if on_top:
                # CR 701.20d: the surveilled cards are reordered; the cards
                # below them keep their order (CR 401.2), so their records stay.
                player.note_library_changed(placed=looked_at)
            # CR 701.20e for the cards kept on top; a card put into the
            # graveyard is in a public zone (CR 400.2) and needs no record.
            for state in on_top:
                self.look(state, player.username, source=source)
            for state in to_graveyard:
                self.put_into_graveyard(state)
            return CardSplit(
                moved=tuple(state.id for state in to_graveyard),
                top_order=tuple(state.id for state in on_top),
            )

    def look_at_top_and_split(
        self: "Game",
        player: Player | str,
        count: int,
        *,
        moved_label: str,
        kept_label: str,
        source: str | None = None,
        source_id: str | None = None,
        prompt: str | None = None,
        rest_in_random_order: bool = False,
        moved_amount: int | None = None,
        moved_exact: bool = False,
        asked_of: Player | str | None = None,
        before_choosing: Callable[[list[CardState]], None] | None = None,
        moved_candidates: Callable[[CardState], bool] | None = None,
    ) -> tuple[list[CardState], list[CardState]]:
        """Look at the top `count` cards and split them into two groups, the
        same CR 608.2d question `scry` and `surveil` already ask (CR 701.22a,
        CR 701.25a) generalised past those two rules' own fixed pair of
        destinations.

        `scry` always puts the `CardSplit.moved` half on the *bottom* of the
        library and the rest back on *top*; `surveil` always puts `moved` in
        the *graveyard*. Duskwatch Recruiter's activated ability ("look at the
        top three cards of your library. You may reveal a creature card from
        among them and put it into your hand. Put the rest on the bottom of
        your library in any order.") needs neither pair - its chosen half goes
        to *hand* and its rest half goes to the *bottom* - so this method asks
        the identical CardSplit question CR 701.22a/701.25a already share and
        then, unlike `scry`/`surveil`, does nothing to `player.library` at all:
        both returned groups are already off the library, in the answer's own
        order, and it is entirely the caller's job to decide where each group
        actually goes. That is what lets a caller reach a pair of destinations
        neither built-in rule has, without a third method duplicating the
        look-then-split machinery `_look_at_top`/`_split_top` already hold.

        Reuses `DecisionKind.SCRY` rather than adding a new kind - the
        question underneath ("which of these `count` cards move to the first
        group, and in what order do the rest come back") is exactly the one
        `scry` already asks; only what a caller does with the two halves
        afterward differs.

        Returns `(moved, rest)`. `CR 701.22a`'s question, not `CR 701.22a`'s
        answer's placement - callers using this for something CR 701.22a does
        not describe (Duskwatch Recruiter's is CR 702's "look at" wording, not
        scry) are answerable to their own card's printed order, not this
        method's name.

        `moved_label` and `kept_label` are required, and required for exactly
        that reason: the two destinations live only in the caller, so a
        question published without them tells a client nothing about where
        either half goes and every client is left to guess the scry pair.
        Devourer of Destiny is the card that broke on that guess - its picked
        half stays on *top* and its rest is *exiled*, the opposite of a scry
        on both halves - so the destinations now travel with the question,
        stamped onto `Decision.moved_label` / `Decision.kept_label`.

        **What the chooser knows afterwards** (CR 701.20e) is recorded here,
        although the put-back is the caller's. Every looked-at card gets a
        look for the chooser, pinned to the library epoch *one reordering
        on*: the epoch the caller's single put-back produces
        (`note_library_changed` after its direct list writes, CR 701.20d), so
        a card put back is known against the order the chooser made and the
        next reordering ends it. Every other outcome fails closed: a card that
        went to a hand, graveyard or exile has changed zones (CR 400.7), and a
        card put back through `Player.add` carries a new stamp. A caller that
        writes cards back into the library must move the epoch exactly once,
        which is already the rule every direct library write follows.

        `rest_in_random_order` is for a caller that puts the rest back "in a
        random order" (Narset, Parter of Veils; Thundertrap Trainer). That
        order is nobody's arrangement, unlike CR 401.4's "may arrange them in
        any order", so the chooser learns nothing about where the cards went:
        each look is pinned to the current epoch instead, and the caller's one
        put-back ends it (CR 701.20d). The look itself still happened
        (CR 701.20e), so a card taken to hand before the put-back is carried.
        Every looked-at card gets exactly one look either way; a caller never
        records its own.

        Which half is `moved` is the caller's choice and is *not* fixed to
        "the half that leaves the library": `moved` is the pile the player
        actively opts into. For a scry that is the bottomed cards; for
        Devourer's "you may put one of those cards back on top" it is the one
        card put back. Keeping it that way is what makes the empty answer -
        what an unscripted or declining player gives - the correct decline for
        both. See `Decision.moved_label`.

        `moved_amount` and `moved_exact` are how many cards the printed text
        lets the player put in `moved`, published as `Decision.amount` and
        `Decision.exact` and enforced by `ask` (CR 608.2d). The default is a
        scry's "any number of them" (CR 107.1c). Devourer of Destiny's "you may
        put one of those cards back" and Ancient Stirrings' "you may reveal a
        colorless card" are `moved_amount=1`; Waker of Waves' "put one of them
        into your hand" is `moved_amount=1, moved_exact=True`. The count of
        cards looked at is `len(Decision.cards)`, never `amount`.

        **Nothing is asked when there is no choice to make.** An empty library
        looks at nothing (CR 609.3), so there is no split to ask about - the
        same "no event" CR 701.22b gives a scry of 0. And when `moved_exact`
        pins the moved pile to a fixed count that a short library can no
        longer undercut - `moved_amount` clamped to `len(looked_at)` already
        equals `len(looked_at)` - every looked-at card is the only legal
        `moved` (CR 608.2d: "can't choose an option that's ... impossible"),
        so that forced answer is used directly rather than asked for. Stock
        Up's library holding one or two cards ("put two of them into your
        hand") are both this case. A question with candidates but genuine
        freedom - `moved_exact=False`, or fewer forced than were looked at -
        is still asked; a client that cannot answer meaningfully is the
        defect this guards against, not the freedom to choose.

        `asked_of` is who makes the split choice and gains the CR 701.20e
        knowledge, when that is not `player` itself - Architects of Will's
        "look at the top three cards of *target player's* library, then put
        them back in any order" is the controller doing the looking and the
        ordering, over a library that belongs to somebody else entirely (the
        official ruling: "You look at the cards, not the targeted player.").
        `player` still names whose library is read and rewritten - `_look_at_
        top`, `put_back_epoch`, and the final `library.remove` below all stay
        keyed to it - only the question and the knowledge move to `asked_of`.
        `None` (the default) keeps both roles on `player`, exactly as every
        caller before this parameter existed already behaved.

        `before_choosing` runs after the look and before the split question,
        for an instruction printed *between* the two: Birthing Ritual's "look
        at the top seven cards of your library. Then you may sacrifice a
        creature. If you do, you may put a creature card with mana value X or
        less from among those cards" (CR 608.2c: in the order written). It is
        handed the looked-at cards, which stay where they are while it runs.

        `moved_candidates` narrows which looked-at cards may be `moved` at
        all - "a creature card with mana value 4 or less from among them"
        (Aang, at the Crossroads), "up to two creature cards with mana value
        3 or less" (Collected Company). Given it, the question is a
        `CHOOSE_CARDS` over only the cards that qualify, so a client is never
        offered one it may not pick (CR 608.2d), `moved_amount`/`moved_exact`
        bound how many, and nothing is asked when none qualifies or when the
        exact count leaves no choice. It is read after `before_choosing`, so a
        bound that depends on what that did (X from the sacrificed creature)
        is current.
        """
        if isinstance(player, str):
            player = self.player(player)
        chooser = self.player(asked_of) if isinstance(asked_of, str) else (asked_of or player)
        if count <= 0:
            return [], []

        looked_at = self._look_at_top(player, count)
        if not looked_at:
            return [], []
        amount = len(looked_at) if moved_amount is None else min(moved_amount, len(looked_at))
        pending_looks = self._look_before_choosing(chooser, looked_at, source)
        if before_choosing is not None:
            before_choosing(looked_at)
        if moved_candidates is not None:
            answer = self._choose_moved_candidates(
                chooser,
                [state for state in looked_at if moved_candidates(state)],
                moved_amount=moved_amount,
                moved_exact=moved_exact,
                prompt=prompt or f"choose among the top {count} card(s)",
                source=source,
                source_id=source_id,
            )
        elif moved_exact and amount == len(looked_at):
            # CR 608.2d: with the library this short, every card looked at is
            # the only legal `moved` - nothing is left to choose, so nothing
            # is asked.
            answer: CardSplit = CardSplit(moved=tuple(state.id for state in looked_at))
        else:
            asked = self.ask(
                Decision(
                    kind=DecisionKind.SCRY,
                    player=chooser.username,
                    prompt=prompt or f"look at the top {count} card(s)",
                    source=source,
                    source_id=source_id,
                    amount=amount,
                    exact=moved_exact,
                    cards=tuple(state.id for state in looked_at),
                    moved_label=moved_label,
                    kept_label=kept_label,
                )
            )
            assert isinstance(asked, CardSplit)
            answer = asked
        moved, rest = self._split_top(player, looked_at, answer)
        self._end_looks(pending_looks)
        put_back_epoch = player.library_epoch + (0 if rest_in_random_order else 1)
        for state in looked_at:
            self._record_shown(state, [chooser.username], source, library_epoch=put_back_epoch)
        library = player.library
        for state in looked_at:
            if state in library:
                library.remove(state)
        return moved, rest

    # -- shuffling and searching (CR 701.23, CR 701.24) -----------------------

    def shuffle_library(
        self: "Game", player: Player | str, *, keep: list[CardState] | None = None
    ) -> None:
        """Randomize a player's library (CR 701.24a).

        "To shuffle a library or a face-down pile of cards, randomize the cards
        within it so that no player knows their order."

        CR 701.24b is the reason for `keep`: "Some effects cause a player to
        search a library for a card or cards, shuffle that library, then put
        some or all of the found cards into a different zone or in a certain
        position in that library. In such cases, the found cards aren't included
        in the shuffle, even though they remain in the library at that time.
        Rather, all the cards in that library except those are shuffled." The
        kept cards stay where they are, at the front, and everything else is
        randomized around them.

        The randomness is seeded from `shuffle_seed` and the shuffle count, so
        the shuffle is a real shuffle and the game is still reproducible - which
        CR 701.24a permits, since it asks only that no *player* know the order.

        CR 701.24c-e all say the same thing from different angles: the shuffle
        happens even when there is nothing to shuffle in. A library of zero or
        one cards is shuffled here too, and `shuffles_performed` counts it, so
        CR 701.24e's trigger has something to trigger on when triggers on
        shuffling exist.
        """
        if isinstance(player, str):
            player = self.player(player)
        held = list(keep or [])
        held_ids = {state.id for state in held}
        rest = [state for state in player.library if state.id not in held_ids]
        rng = Random(f"{self.shuffle_seed}:{self.shuffles_performed}")  # noqa: S311
        rng.shuffle(rest)
        player.zones[Zone.LIBRARY] = held + rest
        player.note_library_changed()  # CR 701.20d: a shuffled library is a new order
        self.shuffles_performed += 1

    def flip_coin(self: "Game", player: "Player | str | None" = None) -> bool:
        """CR 705.1: flip a coin, "a two-sided object with ... equal likelihood
        that either side lands face up." Returns `True` for a win (heads, by
        this engine's own arbitrary but fixed convention - CR 705.1 leaves
        which side is which to the players, and nothing here distinguishes
        them further than win/lose the way `condition_matches`'s callers
        already read "if you win/lose the flip").

        Seeded from `shuffle_seed` and `coin_flips_performed`, the same
        reproducibility convention `shuffle` uses for its own randomness (see
        that method's own docstring) - a scenario asserting on the result of
        a flip needs a fixed outcome, not a live coin.
        """
        event = ReplaceableEvent(
            kind=EventKind.FLIP_COIN,
            player=self.player(player) if isinstance(player, str) else player,
            amount=1,
        )
        apply_replacements(self, event)
        results = []
        for _ in range(max(event.amount, 1)):
            rng = Random(f"{self.shuffle_seed}:{self.coin_flips_performed}:coin")  # noqa: S311
            self.coin_flips_performed += 1
            results.append(rng.random() < 0.5)
        # CR 614.1a, 705.1: the flipper ignores the losing flips first.
        kept = sorted(results, reverse=True)[: max(len(results) - event.ignore, 1)]
        from ...machines.coin_flip_statics import first_flip_is_forced_heads

        flipper = event.player.username if event.player is not None else None
        if flipper is not None and first_flip_is_forced_heads(self, flipper):
            return True  # CR 705.3: the indicated result replaces the actual one
        return kept[0]

    def roll_dice(self: "Game", player: "Player | str", sides: int, count: int = 1) -> list[int]:
        """CR 706.2: a player rolls `count` dice of `sides` sides; the results are
        returned in rolled order, less the `ignore` lowest ones a replacement
        effect ignores (Pixie Guide: "roll that many dice plus one and ignore the
        lowest roll"). Seeded like `flip_coin`, from the same
        `coin_flips_performed` counter of random outcomes (no new Game field)."""
        who = self.player(player) if isinstance(player, str) else player
        event = ReplaceableEvent(kind=EventKind.ROLL_DICE, player=who, amount=count)
        apply_replacements(self, event)
        rolls = []
        for _ in range(event.amount):
            rng = Random(f"{self.shuffle_seed}:{self.coin_flips_performed}:die")  # noqa: S311
            self.coin_flips_performed += 1
            rolls.append(rng.randint(1, sides))
        for _ in range(event.ignore):
            rolls.remove(min(rolls))
        self.emit(
            GameEvent(event=ExtraTriggerEvent.ROLLS_DICE, player=who.username, amount=len(rolls))
        )
        return rolls

    def replaced_mill_count(self: "Game", player: "Player", count: int) -> int:
        """CR 701.17a, 614.1a: how many cards `player` really mills once the
        replacement effects on a mill (The Water Crystal) have had their say."""
        event = ReplaceableEvent(kind=EventKind.MILL, player=player, amount=count)
        apply_replacements(self, event)
        return event.amount

    def assembling_count(self: "Game", player: "Player | str", source: CardState) -> int:
        """CR 701.45a, 614.1a: how many Contraptions `source` assembles for `player`
        when told to assemble one (Steamflogger Boss: a Rigger "assembles two
        Contraptions instead"). Assemble is an Unstable action outside the
        Comprehensive Rules, so this is the hook an assembling effect asks."""
        who = self.player(player) if isinstance(player, str) else player
        event = ReplaceableEvent(kind=EventKind.ASSEMBLE, player=who, card=source, amount=1)
        apply_replacements(self, event)
        return event.amount

    def proliferation_count(self: "Game", player: "Player | str") -> int:
        """CR 701.34a, 614.1a: how many times `player` proliferates when told to
        once (Tekuthal's "proliferate twice instead")."""
        who = self.player(player) if isinstance(player, str) else player
        event = ReplaceableEvent(kind=EventKind.PROLIFERATE, player=who, amount=1)
        apply_replacements(self, event)
        return event.amount

    def search_library(
        self: "Game",
        player: Player | str,
        matches: Callable[[CardState], bool],
        *,
        count: int = 1,
        optional: bool = False,
        shuffle: bool = True,
        source: str | None = None,
        source_id: str | None = None,
        zone: Zone = Zone.LIBRARY,
        caused_by: str | None = None,
        searcher: str | None = None,
        total_mana_value: int | None = None,
    ) -> list[CardState]:
        """Search one of a player's zones, take what was found out of it, and
        (library only) shuffle.

        `total_mana_value` is "any number of `<cards>` with total mana value N
        or less" (Protean Hulk): the finds may be any number, but their mana
        values (CR 202.3) must add up to at most N. A set over the total is
        an illegal answer (CR 608.2d) and is refused; the default answer is
        the zone-order prefix that fits.

        `searcher` is the player doing the searching when that is not the zone's
        owner ("Search target player's library ...", Nightmare Incursion): CR
        701.23a has the searcher find the cards, so the find is asked of them.
        `None` is the owner searching their own zone.

        `caused_by` is Ashiok, Dream Render's own reader: the username of the
        spell or ability's controller that is causing this search, when the
        caller knows it and it is the same player as `player` - a *self*
        search, the only shape "Spells and abilities your opponents control
        can't cause their controller to search their library" ever reaches
        (see `machines.casting_restrictions.search_prohibition_source`'s own
        docstring for why a different searcher, Bribery's "target opponent's
        library", is deliberately untouched). `None` is every caller that
        either does not yet thread this through or is searching a zone the
        static never names - no behaviour changes for either. When it does
        apply, the whole instruction is refused (CR 101.2): nothing is found,
        nothing is removed, and nothing is shuffled.

        CR 701.23a: "To search for a card in a zone, look at all cards in that
        zone (even if it's a hidden zone) and find a card that matches the given
        description." The whole zone is visible to the searcher, which is why
        this takes a predicate over every card rather than looking only at the
        top. `zone` names *which* zone (CR 701.23a's search is always of one
        zone at a time) and defaults to the library, this method's original and
        still most common use - `search_library` keeps its name so every
        existing library search stays untouched, rather than being renamed out
        from under them for a widening only some callers need.

        The Stone Brain's and Surgical Extraction's own "search its owner's
        graveyard, hand, and library" is not a hidden search of all three zones
        at once; it is CR 701.23a's ordinary single-zone search, run three
        times, once per zone this same predicate applies to unchanged.

        **One choice, over every candidate at once.** CR 701.23a's searcher
        looks at the whole zone and *finds a card*: the choice is which of the
        matching cards they want, made once. This used to be a walk - each
        matching card in zone order got its own yes/no question - and that is a
        different game. A walk never lets the searcher say what they want, only
        decline what they are shown, so a Wooded Foothills activated to fetch a
        Breeding Pool could only decline candidates until Breeding Pool happened
        to come up next, and after CR 701.24b's shuffle "next" is arbitrary. The
        live bug this closes is exactly that: one decline, and the seat was
        handed a basic Forest.

        So the question is a single `DecisionKind.CHOOSE_CARDS` carrying every
        legal candidate in `cards`, with `card_labels` naming them (the zone may
        be hidden, so a client cannot look the ids up itself), and the answer
        names the cards the searcher wants. It is asked at all only when there
        is something to decide: a mandatory search whose candidates do not
        outnumber `count` has exactly one legal answer and is taken without
        asking, the same way `Game.ask` forces a question with one option.

        CR 701.23b is the rule that makes a search *declinable*: "If a player is
        searching a hidden zone for cards with a stated quality ... that player
        isn't required to find some or all of those cards even if they're
        present in that zone." That is `optional=True`, and it is asked as an
        inexact question (`exact=False`): any number of the candidates from zero
        up to `count` is a legal answer, so finding nothing is a real answer a
        searcher may give.

        CR 701.23d is the other branch: "If a player is searching a hidden zone
        simply for a quantity of cards, such as 'a card' or 'three cards,' that
        player must find that many cards (or as many as possible, if the zone
        doesn't contain that many)." That is `optional=False`, asked as an exact
        question for `min(count, len(candidates))` cards - "as many as possible"
        - so the searcher chooses *which*, never *whether*.

        CR 400.2 makes the graveyard, battlefield, stack and exile public zones
        and the library and hand hidden ones, and this method deliberately does
        not branch on that. What CR 400.2 changes is whether CR 701.23b/701.23d
        apply at all - both are written about hidden zones - not whether
        CR 701.23a's find is a choice; a search of a public zone that matches
        more cards than it takes is still the searcher picking which, and
        picking is the same question with the same shape. The hidden/public
        difference is therefore carried by `optional`, which the caller sets
        from its own card's text, rather than inferred from the zone here: a
        public-zone search is simply never `optional=True`, and every
        zone-widened caller in this pool already passes `optional=False`.

        The default answer, when nobody is scripted or provided, is
        `Decision.default_cards`: the candidates in zone order, up to `count`.
        That is what this engine found when the search was a walk whose `MAY`
        questions defaulted to yes, so an unscripted fetch still fetches.

        CR 701.23e: nothing is revealed unless the effect says so, so nothing is
        revealed here.

        The cards found are removed from `zone` and returned; the caller
        decides where they go. `shuffle` only ever does anything when
        `zone` is `Zone.LIBRARY` - CR 701.24b's post-search shuffle is a
        library-specific rule with no hand or graveyard equivalent - so a
        caller searching another zone can leave it at its default with no
        effect.
        """
        with self._id_allocator_scope():
            if isinstance(player, str):
                player = self.player(player)

            if (
                caused_by is not None
                and caused_by == player.username
                and search_prohibition_source(self, caused_by) is not None
            ):
                return []

            if zone is Zone.LIBRARY and library_search_blocked(self, player.username) is not None:
                # CR 101.2: "Players can't search libraries." - nothing is found,
                # raised, removed or shuffled.
                return []

            if zone is Zone.LIBRARY:
                # CR 701.23a: this is the one function every library search in
                # the engine goes through, so it is the one place to raise
                # "Whenever an opponent searches their library, ..." (Wan Shi
                # Tong, Librarian; Ob Nixilis, Unshackled) - fired for the
                # search itself, before the find is even chosen, the same way
                # `Game.ring_tempts` raises its own event for an action rather
                # than for its outcome.
                self.emit(
                    GameEvent(event=ExtraTriggerEvent.SEARCHES_LIBRARY, player=player.username)
                )
                self._offer_casts_while_searching(player)

            searchable = list(player.cards_in(zone))
            if zone is Zone.LIBRARY:
                search = ReplaceableEvent(kind=EventKind.SEARCH, player=player)
                apply_replacements(self, search)
                if search.search_limit is not None:
                    searchable = searchable[: search.search_limit]  # CR 701.23a
            candidates = [state for state in searchable if matches(state)]
            limit = min(count, len(candidates))
            found: list[CardState] = candidates[:limit]
            if total_mana_value is not None:
                found, spent = [], 0
                for state in candidates:
                    if len(found) < limit and spent + state.mana_value <= total_mana_value:
                        found.append(state)
                        spent += state.mana_value
            if candidates and (optional or len(candidates) > limit):
                chosen = self.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=searcher or player.username,
                        prompt=(
                            f"choose up to {limit} card(s) to find while searching "
                            f"{'your' if searcher is None else player.username + chr(39) + 's'} "
                            f"{zone.value}"
                            if optional
                            else f"choose {limit} card(s) to find while searching "
                            f"{'your' if searcher is None else player.username + chr(39) + 's'} "
                            f"{zone.value}"
                        ),
                        source=source,
                        source_id=source_id,
                        amount=limit,
                        cards=tuple(state.id for state in candidates),
                        card_labels=tuple(state.name for state in candidates),
                        exact=not optional,
                        default_cards=tuple(state.id for state in found),
                    )
                )
                assert isinstance(chosen, tuple)
                by_id = {state.id: state for state in candidates}
                found = [by_id[card_id] for card_id in chosen]
                if total_mana_value is not None and (
                    sum(state.mana_value for state in found) > total_mana_value
                ):
                    raise ValueError(
                        f"the chosen cards' total mana value exceeds {total_mana_value} "
                        "(CR 608.2d: an illegal choice cannot be made)"
                    )

            for state in found:
                player.cards_in(zone).remove(state)
            if shuffle and zone is Zone.LIBRARY:
                self.shuffle_library(player)
            return found

    def _offer_casts_while_searching(self: "Game", player: Player) -> None:
        """Panglacial Wurm's "While you're searching your library, you may cast
        this card from your library." (CR 701.23a, CR 601.3): the search is
        under way, so each such card in the library is offered a cast, paying
        its mana cost, before the find is chosen (CR 608.2g - the effect that
        causes the search is still resolving)."""
        for card in search_cast_candidates(player.library):
            if card not in player.library or not self.can_cast_during_resolution(
                card, player.username
            ):
                continue
            cost = total_cost_for_phrase(card.card.mana_cost or "", player.username)
            sources = self._mana_sources_while_resolving(player)
            if (
                cost is not None
                and plan_mana_payment(cost.mana, sources, game=self, payer=player.username) is None
            ):
                continue  # CR 608.2d: a cast that cannot be paid is not offered.
            if self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=player.username,
                    prompt=f"cast {card.name} from your library while searching it",
                    source=card.name,
                    source_id=source_id_of(card),
                )
            ):
                self.cast_during_resolution(
                    card,
                    player.username,
                    source_name=card.name,
                    rule="CR 701.23a: cast while searching the library",
                    pays_mana_cost=True,
                )

    def search_and_put(
        self: "Game",
        player: Player | str,
        matches: Callable[[CardState], bool],
        *,
        destination: Zone,
        count: int = 1,
        reveal: bool = False,
        tapped: bool = False,
        source: str | None = None,
        source_id: str | None = None,
        caused_by: str | None = None,
        total_mana_value: int | None = None,
    ) -> list[CardState]:
        """Search a library for a stated quality, reveal the finds if the text
        says so, put them into the hand, onto the battlefield, or into the
        graveyard, then shuffle.

        The funnel every printed "search your library for ..., [reveal it,]
        put it ..., then shuffle" goes through, in the order it is printed.
        CR 701.23b makes each find optional (a stated quality). CR 701.23e:
        "If the effect that contains the search instruction doesn't also
        contain instructions to reveal the found card(s), then they're not
        revealed", so `reveal` is read off the printed text by the caller.
        The reveal is CR 701.20a's, recorded while the card is still the
        library's object (CR 701.20b), and the put comes before the CR 701.24a
        shuffle so a find put into its owner's hand carries the public record
        (`Player.add`, `carry_knowledge_into_hand`).

        `Zone.GRAVEYARD` (Enroot's own "search your library for a land card,
        put it into your graveyard, then shuffle") is the same `Player.add`
        path `Zone.HAND` already takes - CR 701.23 puts no restriction on
        which zone a search may name, and `player.add` already stamps a
        card's owner correctly for any of the seven rules zones.

        `caused_by` is `Game.search_library`'s own Ashiok, Dream Render gate -
        see that method's docstring. Checked again here, ahead of calling
        `search_library` at all, because this method's own trailing shuffle is
        part of the same printed "search ... then shuffle" instruction: CR
        101.2's "can't" beats the whole thing, not just the find.
        """
        with self._id_allocator_scope():
            if isinstance(player, str):
                player = self.player(player)
            if destination not in (Zone.HAND, Zone.BATTLEFIELD, Zone.GRAVEYARD):
                raise ValueError(
                    "a search puts its finds into a hand, onto the battlefield, or "
                    f"into a graveyard, not {destination.value}"
                )
            if (
                caused_by is not None
                and caused_by == player.username
                and search_prohibition_source(self, caused_by) is not None
            ):
                return []
            if library_search_blocked(self, player.username) is not None:
                return []
            found = self.search_library(
                player,
                matches,
                count=count,
                optional=True,
                shuffle=False,
                source=source,
                source_id=source_id,
                caused_by=caused_by,
                total_mana_value=total_mana_value,
            )
            if reveal:
                for state in found:
                    self.reveal(state, source=source)
            for state in found:
                if destination is Zone.BATTLEFIELD:
                    self.put_onto_battlefield(state, player.username, tapped=tapped)
                elif destination is Zone.GRAVEYARD:
                    # CR 400.6/614.1a: this is an ordinary "put into a
                    # graveyard" - Enroot's own "search your library for a
                    # land card, put it into your graveyard" - and every
                    # replacement effect watching for one (Rest in Peace,
                    # Leyline of the Void) applies to it exactly as it would
                    # to any other, so this goes through the one shared
                    # mover rather than a bespoke zone assignment.
                    self.put_into_graveyard(state)
                else:
                    player.add(state, destination)
            self.shuffle_library(player)
            return found

        # -- revealing, and cards outside the game (CR 701.20, CR 400.11) --------

    def _reveal_drawn_card(self: "Game", drawer: str, card: CardState) -> None:
        """CR 701.20a for "The chosen player reveals each card they draw."
        (Booby Trap): every permanent still showing that line whose chosen
        player (`CardState.chosen_player`, CR 614.12a) is `drawer` has the
        card shown as it is drawn, once per such permanent."""
        for permanent in list(self.battlefield):
            if permanent.chosen_player != drawer:
                continue
            for line in (permanent.card.oracle_text or "").splitlines():
                text = line.strip()
                if self._REVEALS_EACH_CARD_DRAWN_RE.fullmatch(
                    text
                ) is not None and self._still_has_static_line(permanent, text):
                    self.reveal(card, source=permanent.name)

    def reveal(self: "Game", card_state: CardState, source: str | None = None) -> CardState:
        """Show one card to all players (CR 701.20a), and record that it was shown.

        "To reveal a card, show that card to all players for a brief time."
        CR 701.20b: "Revealing a card doesn't cause it to leave the zone it's
        in" - so nothing moves here, and a caller that also moves the card does
        that separately, in the order its own text states.

        The reveal is credited to the card's owner, which is who is holding it
        in every case the rules reach: a card revealed out of a hidden group is
        revealed by the player whose group it is (their hand, their library,
        their sideboard outside the game, CR 400.11a). `Reveal` explains why
        exactly one entry is appended per card shown, and why that matters for
        anything downstream deciding what an opponent may see.
        """
        return self._record_shown(card_state, None, source)

    def look(
        self: "Game", card_state: CardState, viewer: str, source: str | None = None
    ) -> CardState:
        """Show one card to one player (CR 701.20e), and record that it was seen.

        "Some effects instruct a player to look at one or more cards. Looking
        at a card follows the same rules as revealing a card, except that the
        card is shown only to the specified player." So this is `reveal` with
        the audience narrowed to `viewer`, and nothing moves (CR 701.20b).
        """
        return self._record_shown(card_state, [viewer], source)

    def _seat(self: "Game", username: str | None) -> Player | None:
        return next((player for player in self.players if player.username == username), None)

    def note_hideaway_viewers(self: "Game") -> None:
        """Record a look for whoever controls a hideaway permanent now, on
        each face-down card it exiled (CR 702.75a, CR 406.3).

        CR 702.75a's exiled card gains "The player who controls the permanent
        that exiled this card may look at this card in the exile zone" - the
        controller *now*, so a player who gains control of that permanent
        gains the look. CR 406.3 then keeps it: "once a player is allowed to
        look at a card exiled face down, that player may continue to look at
        that card until it leaves the exile zone", so the look is recorded at
        the moment control arrives rather than computed by `known_to`, and a
        player who later loses control keeps it until the card leaves exile.

        Called by `_hideaway_effect` as the card is exiled and by
        `ContinuousEffects.create`/`add` (through the store's bound game)
        whenever a layer 2 control effect is stored - the only way control of
        a permanent changes after it enters in this engine
        (`ContinuousEffects.has_control_effect`). A viewer who already has a
        live record of the card gets no second one.
        """
        for card_state in list(self.exile):
            annotation = card_state.exile_annotation
            if (
                card_state.face_up
                or annotation is None
                or annotation.marker is not ExileMarker.HIDEAWAY
                or annotation.linked_permanent_id is None
            ):
                continue
            permanent = next(
                (state for state in self.battlefield if state.id == annotation.linked_permanent_id),
                None,
            )
            viewer = permanent.controller if permanent is not None else None
            if permanent is None or viewer is None:
                continue
            if any(
                self._live_reveal(reveal, viewer)
                for reveal in self.reveals
                if reveal.card_id == card_state.id
            ):
                continue
            self.look(card_state, viewer, source=permanent.name)

    def keep_untouched_library_records(
        self: "Game", player: Player, placed: Sequence[CardState]
    ) -> None:
        """Move `player.library_epoch` on for a put-back that wrote only
        `placed`, and re-pin every other card's live library record to it.

        CR 701.20d ends a reveal when the library is "shuffled or otherwise
        reordered" - "any revealed cards that are reordered stop being
        revealed". A card put on the bottom goes below every card already
        there, and a scry or surveil moves only its own cards off the top and
        back (CR 701.22a, CR 701.25a); either way CR 401.2's pile keeps every
        other card in its order, so their records stay true. Re-pinning is
        data appended at the moment of the put, the way `KnownCarry` is, so
        `known_to` stays pure. A record of a card in `placed`, or one already
        ended (a stale epoch, a new stamp), is not re-pinned and so ends.
        """
        placed_ids = {state.id for state in placed}
        untouched = {state.id: state for state in player.library if state.id not in placed_ids}
        kept = {
            reveal.card_id: state
            for reveal in self.reveals
            if (state := untouched.get(reveal.card_id)) is not None
            and reveal.zone is Zone.LIBRARY
            and reveal.turn is not None
            and reveal.zone_change_stamp == state.zone_change_stamp
            and self._library_order_holds(
                state.id, state.zone_change_stamp, player, reveal.library_epoch
            )
        }
        player.library_epoch += 1
        for state in kept.values():
            self.library_orders_kept.append(
                LibraryOrderKept(
                    card_id=state.id,
                    zone_change_stamp=state.zone_change_stamp,
                    epoch=player.library_epoch,
                )
            )

    def _library_order_holds(
        self: "Game", card_id: UUID, stamp: UUID, owner: Player, recorded_epoch: int | None
    ) -> bool:
        """Whether a library record made at `recorded_epoch` still describes
        where card `card_id`, as the object `stamp`, sits (CR 701.20d,
        CR 401.2).

        True when the owner's library has not moved since, or when every move
        since was a put that left this card, as this object, in its order - a
        `LibraryOrderKept` row for each epoch in between.
        """
        if recorded_epoch is None or recorded_epoch > owner.library_epoch:
            return False
        if recorded_epoch == owner.library_epoch:
            return True
        kept = {
            row.epoch
            for row in self.library_orders_kept
            if row.card_id == card_id and row.zone_change_stamp == stamp
        }
        return all(epoch in kept for epoch in range(recorded_epoch + 1, owner.library_epoch + 1))

    def face_up_cards_in_exile(
        self: "Game",
        owner: str | None = None,
        matches: Callable[[CardState], bool] | None = None,
    ) -> list[CardState]:
        """Exiled cards that are face up (CR 406.3), optionally narrowed.

        CR 406.3: "Exiled cards are, by default, kept face up and may be
        examined by any player at any time. Cards 'exiled face down' can't be
        examined by any player except when instructions allow it." So a
        face-down exiled card is not merely hidden - it is not a card an effect
        that says "choose a face-up card in exile" may be pointed at, and
        CR 406.3a adds that it "has no characteristics" at all, which means
        asking whether it is an artifact has no answer to give.

        `owner` filters by CR 108.3 ownership, which is what a "you own" clause
        needs - deliberately not by controller: exile is a shared zone and the
        object in it may be one an opponent put there.
        """
        return [
            state
            for state in self.exile
            if not state.face_down
            and (owner is None or state.owner == owner)
            and (matches is None or matches(state))
        ]

    # -- drawing, life, and counters, as replaceable events ------------------

    def draw_cards(
        self: "Game",
        player: Player | str,
        count: int = 1,
        *,
        cycled: "CardState | None" = None,
    ) -> list[CardState]:
        """Draw `count` cards one at a time, replacement effects included.

        CR 121.2: "Cards may only be drawn one at a time. If a player is
        instructed to draw multiple cards, that player performs that many
        individual card draws." Each of those individual draws is its own
        replaceable event (CR 121.6). CR 614.5 gives each replacement effect
        only one opportunity per event or modified event descending from it -
        which is exactly why `apply_replacements` below is called only once
        per instruction and never again on whatever it produces: a second
        call would let the same doubler (Alhammarret's Archive, Thought
        Reflection) double its own output. But CR 121.2a/121.6b make each of
        the resulting cards its own fresh individual draw once the doubler (or
        a redirect such as Plagiarize) has settled the amount and who draws
        it - a *different*, not-yet-applied effect can still apply to each of
        those, dredge (CR 702.52a) chief among them - `_offer_dredge` below is
        called again, once per resulting card, for exactly that reason.

        CR 121.6a applies a draw replacement "even if no cards could be drawn
        because there are no cards in the affected player's library", which is
        why the replacement runs before the library is consulted. `draw_up_to`
        then records the failed draw for CR 704.5b.
        """
        with self._id_allocator_scope():
            if isinstance(player, str):
                player = self.player(player)

            drawn: list[CardState] = []
            for _ in range(count):
                # CR 121.2b: "Some effects say that a player can't draw more
                # than one card each turn. Such an effect applies to
                # individual card draws." - Narset, Parter of Veils's and
                # Spirit of the Labyrinth's cap, checked fresh (CR 611.3a) once
                # per draw in this very loop rather than once per instruction,
                # which is exactly what lets "draw two cards" against a cap of
                # one "still be partially carried out": the first draw below
                # is unaffected, and only the one that would exceed the cap is
                # skipped.
                if self.draw_prohibited(player.username) is not None:
                    # CR 121.3: an effect saying a player can't draw cards
                    # makes this individual draw simply not happen - no
                    # event, no card moved, the same "can't precedence"
                    # `gain_life` already gives `cannot_gain_life` (CR 101.2).
                    continue
                restriction = draw_cap_restriction(self, player.username)
                if restriction is not None:
                    already = self.cards_drawn_this_turn.get(player.username, 0)
                    if already >= (restriction.amount or 0):
                        continue
                if self._offer_dredge(player) is not None:
                    # CR 702.52a: this individual draw was replaced by a mill,
                    # not drawn - nothing here counts as a card drawn, exactly
                    # like a draw replaced down to zero (CR 603.2g, this
                    # method's own docstring above).
                    continue
                event = ReplaceableEvent(
                    kind=EventKind.DRAW,
                    player=player,
                    amount=1,
                    # CR 504.1's draw, and "the first one they draw in each of
                    # their draw steps" (Notion Thief, Alhammarret's Archive):
                    # the first card actually drawn this draw step, not the
                    # first card of whichever draw instruction comes first.
                    draw_step_draw=self._is_draw_step_draw(player)
                    and self.cards_drawn_in_own_draw_step.get(player.username, 0) == 0,
                    cycled_card=cycled,
                )
                apply_replacements(self, event)
                # CR 614.6: a replacement may hand the draw to someone else
                # ("that player skips that draw and you draw a card") - the
                # modified event is what happens, so whoever it now names draws.
                drawer = event.player or player
                if drawer is player and event.amount == 1:
                    # The overwhelmingly common case: nothing besides dredge
                    # (already offered and declined above) touched this draw.
                    # Skip straight to drawing it - re-running the per-card
                    # loop below would ask about dredge a second time for the
                    # exact same, unmodified individual draw.
                    cards = list(player.draw_up_to(1))
                else:
                    # Some other replacement changed who draws and/or how many
                    # cards result (a doubler, a Plagiarize-style redirect).
                    # CR 121.2/121.2a settle that *once*, above; CR 121.6b then
                    # makes each of the resulting cards its own individual
                    # draw, so each gets its own dredge opportunity - this
                    # time the actual drawer's own graveyard, not `player`'s
                    # (CR 616.1: a different effect, never yet applied to this
                    # event, is free to apply to it). This never re-invokes
                    # `apply_replacements`, so the doubler that produced
                    # `event.amount` never gets a second, self-invoked
                    # opportunity at its own output (CR 614.5).
                    cards = []
                    remaining = event.amount
                    while remaining > 0:
                        if self._offer_dredge(drawer) is not None:
                            remaining -= 1
                            continue
                        cards.extend(drawer.draw_up_to(1))
                        remaining -= 1
                # CR 121.2: each card actually drawn is its own draw, so each is
                # its own trigger event - a replacement that turns one draw into
                # two still produces two events. A draw replaced down to nothing
                # never happened, so it triggers nothing (CR 603.2g).
                for card in cards:
                    if drawer is player:
                        # Only `player`'s own draws are what the caller asked
                        # for; a draw handed to someone else is theirs.
                        drawn.append(card)
                    # CR 121.2's individual draw, counted before it is announced.
                    # `machines/triggers` answers "you draw your third card in a
                    # turn" by reading `cards_drawn_this_turn` *while* the event
                    # below is being dispatched, so the count has to already
                    # include this card or the ordinal would never match.
                    self.cards_drawn_this_turn[drawer.username] = (
                        self.cards_drawn_this_turn.get(drawer.username, 0) + 1
                    )
                    if self._is_draw_step_draw(drawer):
                        self.cards_drawn_in_own_draw_step[drawer.username] = (
                            self.cards_drawn_in_own_draw_step.get(drawer.username, 0) + 1
                        )
                    if self.cards_drawn_this_turn[drawer.username] == 1:
                        # CR 702.94a: "as you draw it if it's the first card
                        # you've drawn this turn" - asked here, mid-draw, and
                        # only for this one card (CR 121.2).
                        self._offer_miracle_reveal(drawer, card)
                        self._offer_first_draw_reveals(drawer, card)
                    self._reveal_drawn_card(drawer.username, card)
                    self.emit(
                        GameEvent(
                            event=TriggerEvent.DRAWS_A_CARD,
                            subject_id=card.id,
                            subject_name=card.name,
                            subject_controller=drawer.username,
                            subject_card=card.card,
                            player=drawer.username,
                        )
                    )
            return drawn

    def _offer_dredge(self: "Game", player: Player) -> CardState | None:
        """CR 702.52a's own replacement, offered once for each individual
        draw (CR 121.2) `player` is about to make, before it happens.

        "'Dredge N' means 'As long as you have at least N cards in your
        library, if you would draw a card, you may instead mill N cards and
        return this card from your graveyard to your hand.'" Every graveyard
        card whose dredge is satisfiable right now (`why_cannot_dredge`
        already checks CR 702.52b's own library-size floor) is offered
        together as one `DREDGE` decision, naming each by id
        (`Decision.cards`); the answer is at most one of them (CR 616.1e: any
        one of several applicable optional replacement effects may be
        chosen). Declining - the empty answer, and `default_answer`'s own
        unscripted default - lets the caller's normal draw proceed untouched.

        Not asked at all when nothing is eligible, the same "a question with
        no legal options is not asked" convention `Game.ask`'s own module
        docstring already states.

        Called once for `player`'s own would-draw instruction before any
        other replacement runs, and again by `draw_cards` for each resulting
        individual draw once a doubler or a redirect has settled who draws
        and how many - `player` there is whoever that turns out to be, so a
        redirected draw (Plagiarize, Notion Thief) is offered against *its*
        own graveyard, not the original drawer's (CR 616.1e). This engine
        does not also model a seat *ordering* several other simultaneously-
        applicable, non-dredge draw replacements (two redirects, two
        doublers) against each other for the identical draw - `apply_
        replacements` applies those on its own, in whatever order its own
        registry tries them; see `docs/engine-coverage.md`.
        """
        candidates = [
            card
            for card in player.cards_in(Zone.GRAVEYARD)
            if dredge_count(effective_card(self, card)) is not None
            and why_cannot_dredge(self, card, player.username) is None
        ]
        if not candidates:
            return None
        names = ", ".join(sorted({card.name for card in candidates}))
        answer = self.ask(
            Decision(
                kind=DecisionKind.DREDGE,
                player=player.username,
                prompt=(
                    f"{player.username} is about to draw a card; replace it by dredging "
                    f"one of {names} instead? (CR 702.52a)"
                ),
                cards=tuple(card.id for card in candidates),
                # Several graveyard cards can offer dredge for the one draw, so
                # no single object asks; `cards` names each candidate.
                source_id=None,
            )
        )
        assert isinstance(answer, tuple)
        if not answer:
            return None
        # `Game.ask` has already checked this id names a real, still-eligible
        # graveyard card (`why_cannot_dredge`, its own `DREDGE` branch) before
        # ever returning it here.
        (chosen_id,) = answer
        chosen = self.find_by_id(chosen_id)
        assert isinstance(chosen, CardState)
        dredge(self, chosen, player.username)
        return chosen

    def _offer_miracle_reveal(self: "Game", player: Player, card: CardState) -> None:
        """CR 702.94a's static ability: "You may reveal this card from your
        hand as you draw it if it's the first card you've drawn this turn."

        One `MAY`, asked of the drawing player only, naming the card
        (`Decision.card`). Declining reveals nothing - no `Reveal` record, so
        nobody else learns the card (CR 402.3) - and nothing triggers, because
        the linked trigger only answers a reveal this ability made (CR 603.11,
        CR 607.2h). An unscripted player declines (`Decision.default_may`):
        revealing gives away hidden information, which is not an engine's to
        give on a player's behalf.

        Revealing records the reveal (CR 701.20a; `revealed_for_miracle` is
        how long it lasts, CR 702.94b) and triggers the linked ability, which
        waits in `pending_triggers` for the next time a player would receive
        priority (CR 603.3) - a draw in the middle of a resolving spell puts it
        on the stack only once that spell has finished.

        Each miracle *instance* the card has as it is drawn is its own static
        ability linked to its own trigger (CR 607.2h): the printed one, and
        any a permanent grants the card in hand ("Each instant and sorcery
        card in your hand has miracle {2}.", `machines/spell_grants.py`),
        which has to be in force as the card is drawn - this moment. They are
        offered in that order; revealing through one triggers only its own
        linked ability, so the cast is at that instance's cost.
        """
        if card.zone is not Zone.HAND:
            return
        instances = [
            ability
            for ability in keyword_triggered_abilities(card.card)
            if (ability.keyword or "").lower() == "miracle"
        ] + [
            ability
            for ability in granted_keyword_triggered_abilities(
                granted_hand_keyword_lines(self, card)
            )
            if (ability.keyword or "").lower() == "miracle"
        ]
        for instance in instances:
            revealed = self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=player.username,
                    prompt=(
                        f"reveal {card.name} as you draw it, the first card you've drawn this "
                        f"turn, for its {instance.raw.split('(')[0].strip()} ability "
                        "(CR 702.94a)"
                    ),
                    source=card.name,
                    source_id=source_id_of(card),
                    card=card.id,
                    cards=(card.id,),
                    default_may=False,
                )
            )
            if not revealed:
                continue
            self.reveal(card, source=card.name)
            event = GameEvent(
                event=ExtraTriggerEvent.REVEALED_FOR_MIRACLE,
                subject_id=card.id,
                subject_name=card.name,
                subject_controller=player.username,
                subject_card=card.card,
                player=player.username,
            )
            self.pending_triggers.extend(
                triggered
                for triggered in triggers_for(self, event, [card])
                if triggered.ability.raw == instance.raw
                and triggered.ability.effect == instance.effect
            )
            return

    def _offer_first_draw_reveals(self: "Game", player: Player, card: CardState) -> None:
        """God-Eternal Kefnet's static ability: "You may reveal the first card
        you draw each turn as you draw it."

        One `MAY` per permanent `player` controls that has it (each is its own
        ability, CR 607.2h), asked as the first card is drawn (CR 121.2) and
        naming the card. Declining reveals nothing and triggers nothing; an
        unscripted player declines (revealing gives away hidden information).
        Revealing records the reveal (CR 701.20a) and raises
        `ExtraTriggerEvent.REVEALED_FIRST_DRAW`, which only that permanent's
        linked "Whenever you reveal an instant or sorcery card this way"
        trigger answers (CR 603.11).
        """
        if card.zone is not Zone.HAND:
            return
        for source in [
            permanent
            for permanent in self.battlefield
            if permanent.controller == player.username and has_first_draw_reveal(permanent.card)
        ]:
            if first_draw_reveal_own_turns_only(source.card) and (
                self.turn is None or self.turn.active_player != player.username
            ):
                continue  # "on each of your turns" (Keranos)
            if not first_draw_reveal_is_mandatory(source.card) and not self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=player.username,
                    prompt=(
                        f"reveal {card.name} as you draw it, the first card you've drawn this "
                        f"turn, for {source.name}"
                    ),
                    source=source.name,
                    source_id=source_id_of(source),
                    card=card.id,
                    cards=(card.id,),
                    default_may=False,
                )
            ):
                continue
            self.reveal(card, source=source.name)
            self.emit(
                GameEvent(
                    event=ExtraTriggerEvent.REVEALED_FIRST_DRAW,
                    subject_id=card.id,
                    subject_name=card.name,
                    subject_controller=player.username,
                    subject_card=card.card,
                    player=player.username,
                )
            )

    def revealed_for_miracle(self: "Game", card_state: CardState) -> bool:
        """Whether `card_state` is being played revealed under CR 702.94b:
        "they play with that card revealed until that card leaves their hand,
        that ability resolves, or that ability otherwise leaves the stack."

        Computed, not stored: the card is revealed exactly while it is still
        the same object in hand (CR 400.7: `zone_change_stamp`) and its miracle
        trigger - the one that reveal set off - is still waiting to go on the
        stack, on it, or resolving. CR 701.20a's "if that ability isn't put
        onto the stack the next time a player would receive priority, the card
        ceases to be revealed" falls out the same way: a trigger that never
        reaches the stack is in none of those places.
        """
        if card_state.zone is not Zone.HAND:
            return False
        waiting = [*self.pending_triggers, *self.stack]
        if self.resolving is not None:
            waiting.append(self.resolving)
        return any(
            getattr(item, "state_class", None) == "AbilityOnStack"
            and isinstance(item.ability, TriggeredAbility)
            and (item.ability.keyword or "").lower() == "miracle"
            and item.source_id == card_state.id
            and item.source_stamp == card_state.zone_change_stamp
            for item in waiting
        )

    def draw_prohibited(self: "Game", username: str) -> str | None:
        """Why this player can't draw a card right now, or None (CR 121.3).

        CR 121.3: "if an effect says that a player can't draw cards ...
        [an offered] choice can't be taken" - and, by the same CR 101.2
        "can't" precedence `life_gain_prohibited` already reads Leyline of
        Punishment's twin through, a turn-based draw (CR 121.1) that would
        otherwise happen simply does not. Maralen of the Mornsong's "Players
        can't draw cards." and Mornsong Aria's own combined "Players can't
        draw cards or gain life." are both this same rules-of-the-game
        prohibition (CR 611.1's third category - no characteristic changes,
        so `machines/layers.py` is the wrong home), read fresh off the
        battlefield every call the identical CR 604.2/611.3a way its life-gain
        twin is: a source destroyed mid-turn stops prohibiting at once.
        """
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                if not (
                    _LOOKS_LIKE_DRAW_PROHIBITION_RE.search(text) or "draw cards" in text.lower()
                ):
                    continue
                if not (
                    _DRAW_PROHIBITION_RE.match(text)
                    or _DRAW_OR_LIFE_GAIN_PROHIBITION_RE.match(text)
                ):
                    self._record_unread_static_line(source, text)
                    continue
                if not self._still_has_static_line(source, text):
                    continue
                return f"{username} can't draw cards: {source.name} says so (CR 121.3, CR 611.1)"
        return None

    @property
    def returned_to_hand_batch(self: "Game") -> tuple[GameEvent, ...]:
        """Every permanent returned to hand by the event now being raised, as
        its `LEAVES_BATTLEFIELD_TO_HAND` event, in the order they moved.

        CR 603.10a: a leaves-the-battlefield ability looks back in time, so
        each permanent returned by one event sees every other one - its own
        source included, already in a hand - and CR 603.2c's plural "one or
        more ... are returned" triggers once for all of them. Empty while no
        such event is being raised."""
        return self._returned_to_hand_batch

    @property
    def tapped_batch(self: "Game") -> tuple[CardState, ...]:
        """The permanents of the `PERMANENTS_TAPPED` event being matched."""
        return self._tapped_batch

    @property
    def graveyard_batch(self: "Game") -> tuple[GraveyardArrival, ...]:
        """The arrivals of the `PUT_INTO_GRAVEYARD` event being matched."""
        return self._graveyard_batch

    @property
    def exile_batch(self: "Game") -> tuple[ExileArrival, ...]:
        """The arrivals of the `PUT_INTO_EXILE` event being matched."""
        return self._exile_batch

    def note_permanent_tapped(self: "Game", permanent: CardState) -> None:
        """`permanent` just became tapped (CR 701.26a) - `CardState.tap` and
        `.tap_if_untapped` call this for a bound permanent, whatever tapped it
        (an attack, a cost, an effect)."""
        # Assigned, not appended: the store has to be announced like any
        # other change (`snapshot.py`), a tap can land outside any command.
        self.tapped_since_last_batch = [*self.tapped_since_last_batch, permanent.id]

    @contextmanager
    def returning_together(self: "Game") -> Iterator[None]:
        """Every permanent returned to hand inside the block leaves as one event.

        One instruction returning several permanents - Marang River Regent's
        "return up to two other target nonland permanents", a cost returning
        two lands - is one event (CR 603.2c), and each of them looks back at
        the others (CR 603.10a), which it only can if no departure is raised
        until the last of them has moved. A nested block joins the outer one.
        """
        if self._returning_together is not None:
            yield
            return
        self._returning_together = []
        try:
            yield
        finally:
            returned, self._returning_together = self._returning_together, None
        self._announce_returns(returned)

    def _left_battlefield_for(self: "Game", permanent: CardState, destination: Zone) -> Zone:
        """Where `permanent` really goes when it would leave the battlefield
        for `destination`, after every replacement effect (CR 614.1a) has had
        its say - the same `ZONE_CHANGE` event `put_into_graveyard` raises,
        for the hand and library routes that had none ("If it would leave the
        battlefield, exile it instead")."""
        event = ReplaceableEvent(
            kind=EventKind.ZONE_CHANGE,
            card=permanent,
            origin=Zone.BATTLEFIELD,
            destination=destination,
        )
        apply_replacements(self, event)
        return event.destination or destination

    def return_to_hand(self: "Game", permanent: CardState) -> CardState:
        """Return a permanent to its owner's hand (CR 701.19a is "return").

        CR 111.8 refuses this for a token that has already left the battlefield,
        which is the rule that stops a Raise Dead or a flicker effect recurring a
        dead token: "If such a token would change zones, it remains in its
        current zone instead."

        Emits `TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND` when the move was
        actually from the battlefield - the third of the three "left the
        battlefield" events alongside `DIES` and `LEAVES_BATTLEFIELD_TO_EXILE`,
        added for Static Prison's "until this enchantment leaves the
        battlefield" (CR 610.3c's kind of one-shot return): a bounced
        Static Prison is exactly as much a departure as a destroyed or exiled
        one, and nothing watched this path before.
        """
        with self._id_allocator_scope():
            if move_refused(permanent, Zone.HAND) is not None:
                return permanent
            was_on_battlefield = permanent in self.battlefield
            if was_on_battlefield and self._left_battlefield_for(permanent, Zone.HAND) is (
                Zone.EXILE
            ):
                # CR 614.6: "exile it instead of putting it anywhere else".
                return self.exile_permanent(permanent)
            # CR 603.10a: who controlled it as it last existed on the
            # battlefield - "another nonland permanent you control is
            # returned" asks about then, not about the hand it lands in.
            controller = permanent.controller
            if was_on_battlefield:
                self._note_left_battlefield(permanent)
            self._take_out_of_every_zone(permanent)
            self.combat.remove(permanent.id)  # CR 506.4
            owner = self._owner_of(permanent)
            owner.add(permanent, Zone.HAND)
            self._accompany_meld_partner(permanent, Zone.HAND)
            if was_on_battlefield:
                left = self._left_battlefield_characteristics.get(permanent.id)
                to_hand = GameEvent(
                    event=TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=controller,
                    subject_card=permanent.card,
                    subject_types=left.types if left is not None else None,
                    subject_subtypes=left.subtypes if left is not None else None,
                    # Whose hand it went to: its owner's (CR 108.3) - the
                    # "your hand" of Azorius Aethermage's condition.
                    player=owner.username,
                )
                departure = GameEvent(
                    event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=controller,
                    subject_card=permanent.card,
                    player=controller,
                )
                if self._returning_together is not None:
                    self._returning_together.append((to_hand, departure))
                else:
                    self._announce_returns([(to_hand, departure)])
            return permanent

    def put_cards_into_library(
        self: "Game", cards: Sequence[CardState], *, to_bottom: bool = False
    ) -> list[CardState]:
        """Move cards into their owners' libraries as one instruction (CR 401.1).

        Each card goes into its own owner's library - CR 401.1's "when a game
        begins, each player's deck becomes their library" is a per-player zone,
        and a card put into a library goes into the library of the player who
        owns it. `to_bottom` picks which end; the list order is kept either way,
        so the first card named ends up nearest the top when going to the top.

        One `ExtraTriggerEvent.PUT_INTO_LIBRARY` event is raised for the whole
        instruction, carrying how many cards it moved. CR 603.2c: an ability
        triggers once per event, and "whenever one or more cards are put into a
        library from anywhere" (Wan Shi Tong, All-Knowing) is one event with a
        count, not one event per card - so Brainstorm putting two cards back is
        a single trigger.

        **A card already in a library is not put into one.** Scry and surveil
        (CR 701.22a, CR 701.25a) reorder cards that never left the zone, so
        nothing was "put into" a library and no event is raised for them; such
        a card is still moved to the requested end, but it does not count
        towards the event and, if every card was already there, no event is
        raised at all.

        A card leaving the battlefield or a graveyard on its way raises those
        departures too, the same events the single-card moves already raise:
        CR 603.6c's `LEAVES_THE_BATTLEFIELD` per permanent, and CR 603.10a's
        `LEAVES_GRAVEYARD` batched per graveyard alongside the library event.

        Run under `_id_allocator_scope`, the same as `put_into_graveyard`/
        `exile_permanent`/`return_to_hand`/`ante`: `CardState.move_to` mints a
        fresh `zone_change_stamp` per card and `emit` below may put a
        triggered ability on `pending_triggers`, both persisted ids that need
        to be deterministic for a decoded replay to reproduce them - found by
        T10's own round-trip/replay invariant the moment a scenario actually
        tucked a permanent off the battlefield through this method, which no
        earlier scenario had exercised.
        """
        with self._id_allocator_scope():
            moved: list[CardState] = []
            newly_in_library: list[CardState] = []
            seen_going_in: dict[UUID, Zone] = {}
            left_battlefield: list[CardState] = []
            by_graveyard: dict[str, list[CardState]] = {}
            for card_state in cards:
                if move_refused(card_state, Zone.LIBRARY) is not None:
                    continue
                was_in_library = card_state.zone is Zone.LIBRARY
                if self._face_seen_in_public_zone(card_state):
                    seen_going_in[card_state.id] = card_state.zone
                graveyard_owner = self._graveyard_owner_of(card_state)
                if card_state in self.battlefield:
                    if self._left_battlefield_for(card_state, Zone.LIBRARY) is Zone.EXILE:
                        self.exile_permanent(card_state)  # CR 614.6
                        continue
                    self._note_left_battlefield(card_state)
                    self._detach_dependents(card_state)
                    left_battlefield.append(card_state)
                self._take_out_of_every_zone(card_state)
                self.combat.remove(card_state.id)  # CR 506.4
                owner = self._owner_of(card_state)
                owner.add(card_state, Zone.LIBRARY)
                self._accompany_meld_partner(card_state, Zone.LIBRARY)
                moved.append(card_state)
                if not was_in_library:
                    newly_in_library.append(card_state)
                if graveyard_owner is not None:
                    by_graveyard.setdefault(graveyard_owner, []).append(card_state)
            if not to_bottom:
                # `Player.add` appends, which is the bottom (CR 401.2's single
                # face-down pile, ordered top-first here). Lift this instruction's
                # cards back out and put them on the front, keeping the order they
                # were named in.
                for card_state in reversed(moved):
                    library = self._owner_of(card_state).library
                    library.remove(card_state)
                    library.insert(0, card_state)
                # CR 701.20d, CR 401.2: a card put on top sits above every card
                # already there, and no record of a position survives that.
                for owner in {id(p): p for p in map(self._owner_of, moved)}.values():
                    owner.note_library_changed()
            self._record_cards_seen_going_into_libraries(newly_in_library, seen_going_in)
            for gone in left_battlefield:
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                        subject_id=gone.id,
                        subject_name=gone.name,
                        subject_controller=gone.controller,
                        subject_card=gone.card,
                        player=gone.controller,
                    )
                )
            for owner_name, gone_cards in by_graveyard.items():
                self._emit_left_graveyard(owner_name, gone_cards, exiled=False)
            if newly_in_library:
                self.emit(
                    GameEvent(
                        event=ExtraTriggerEvent.PUT_INTO_LIBRARY,
                        player=self._owner_of(newly_in_library[0]).username,
                        amount=len(newly_in_library),
                    )
                )
            return moved

    # -- targeting and effects --------------------------------------------

    def find_by_id(self: "Game", card_id: UUID) -> CardState | None:
        """Any card the game can see, by id: battlefield, stack, exile, or a player's zones."""
        for zone_cards in self.shared_zones.values():
            for state in zone_cards:
                if isinstance(state, CardState) and state.id == card_id:
                    return state
        for player in self.players:
            for zone_cards in player.zones.values():
                for state in zone_cards:
                    if state.id == card_id:
                        return state
        return None

    def find_ability_by_id(self: "Game", ability_id: UUID) -> AbilityOnStack | None:
        """An activated or triggered ability on the stack, by id (CR 113.1c, 405.1).

        Deliberately separate from `find_by_id`, which answers with a
        `CardState`. An ability is not a card - CR 405.1 puts it on the stack
        "without any card associated with it" - so it exists in exactly one
        place and nowhere else. CR 115.2 makes one a legal target ("Some spells
        and abilities can target abilities on the stack"), and CR 608.2b then
        looks it back up on resolution, which is what this is for.
        """
        for item in self.stack:
            if isinstance(item, AbilityOnStack) and item.id == ability_id:
                return item
        return None

    def _aura_attachment(self: "Game", spell: CardState) -> Targetable | None:
        """What a resolving Aura spell attaches to (CR 608.3c, 303.4a).

        An Aura spell's only target is what it will enchant, so once
        `resolve_top` has confirmed the spell did not fizzle (CR 608.2b), at
        least one target is still legal - and CR 702.5a's enchant ability gives
        it exactly one to begin with. This re-resolves it from the
        announcement through `resolve_targets` rather than trusting the id
        `spell.targets` recorded: the creature it named may have died and come
        back as a new object (CR 400.7), or the id may now belong to nothing at
        all, and attaching to a stale reference would just relocate this bug
        instead of fixing it.

        None means the parser could not read something about this Aura's
        targeting well enough to say - `resolve_top` fails closed on that
        rather than putting the Aura onto the battlefield unattached.
        """
        targets = self.resolve_targets(spell)
        return targets[0] if targets else None

    def create_next_time_draw_replacement(
        self: "Game", replacement: NextTimeDrawReplacement
    ) -> NextTimeDrawReplacement:
        """Record a CR 614.1a "next time [player] would draw a card this
        turn, instead ..." replacement, installed by a resolving ability
        (Urabrask, Heretic Praetor's own second trigger).

        The same division `create_prevention_shield` already draws for CR
        615.1: creating the record *is* the effect; nothing else happens
        when the ability resolves. `machines.replacement._next_time_draw_
        replacement_effects` is what a later draw event actually consumes.
        """
        with self._id_allocator_scope():
            self.next_time_draw_replacements.append(replacement)
            return replacement

    def exile_from_stack(self: "Game", spell: CardState) -> CardState:
        """Exile a spell straight off the stack - CR 701.13a's exile verb, a
        different move from `counter`'s CR 701.6a entirely, not a variant of
        it.

        Knowledge Pool's and Possibility Storm's identical opening clause -
        "Whenever a player casts a spell from their hand, that player exiles
        it" - is CR 601.2a's third way a spell can leave the stack besides
        resolving or being countered ("A spell remains on the stack until it
        resolves ... is countered, or a rule or effect moves it elsewhere").
        This is that move, and it is built as its own method rather than a
        call to `counter(spell, to_exile=True)` because that method's
        `to_exile` branch is wrong for this shape in exactly the two ways its
        own docstring warns against:

        - **`counter`'s `cannot_be_countered` guard sits above its `to_exile`
          branch.** CR 113.6g's "can't be countered" disables CR 701.6a's
          counter verb only; exiling is a different verb (CR 701.13a) that
          the same clause says nothing about, so a spell that can't be
          countered is exiled all the same - going through `counter` would
          wrongly let such a spell resolve untouched instead.
        - **`counter` always emits `TriggerEvent.SPELL_IS_COUNTERED`.**
          Nothing here was countered - CR 701.6a's "cancel it" never
          happened, the spell is simply relocated - so emitting that event
          would wrongly fire every "whenever a spell is countered" ability in
          the game for a spell that only left the stack.

        What *is* reused, because it is correct for both moves: the spell is
        taken out of every zone (`_take_out_of_every_zone` - exile and the
        stack are both shared zones, CR 400.1), removed from combat (CR
        506.4 - moot for a spell that was never a permanent, kept for the
        same symmetry `counter` keeps it for), and its `CastRecord` popped
        so a later intervening *if* about how it was cast fails closed
        instead of reading a stale record for an object that, per CR 400.7,
        is now new (`machines/triggers._cast_record_for_clause`).
        `CardState.move_to` already resets `targets` for every destination
        but the stack (CR 400.7), so the exiled spell keeps none - no
        further cleanup is needed for that half.
        """
        with self._id_allocator_scope():
            if spell not in self.stack:
                raise ValueError(f"{spell.name} is not on the stack")
            self.stack.remove(spell)
            self._take_out_of_every_zone(spell)
            self.combat.remove(spell.id)  # CR 506.4
            spell.move_to(Zone.EXILE)
            self.exile.append(spell)
            self.forget_cast_record(spell)
            return spell

    def destroy(
        self: "Game", permanent: CardState, *, regeneration_allowed: bool = True
    ) -> CardState:
        """Put a permanent into its controller's graveyard.

        `regeneration_allowed=False` is CR 701.19c's prohibition, which a
        caller passes when the effect doing the destroying printed "can't be
        regenerated" (Wrath of God's "Destroy all creatures. They can't be
        regenerated."). CR 701.19c: such effects "cause regeneration shields
        to not be applied" - they do not remove the shield, so an unspent one
        is still standing for the next destruction this turn, which is why
        this is an argument to the destruction rather than a flag stamped on
        the permanent.

        CR 700.4: "dies" means "is put into a graveyard from the battlefield", so
        a permanent that was on the battlefield when this was called has died and
        anything watching for that triggers (CR 603.2). CR 603.10a lets the
        permanent itself be one of the things watching, even though it is in the
        graveyard by the time the trigger is worked out.

        The move is a zone change and goes through the replacement effects first
        (CR 614.1, 616.1). A Rest in Peace or a Kalitas that sends the card to
        exile instead means the card never reaches a graveyard, so by CR 700.4 it
        never died and no dies trigger fires (CR 614.6).

        CR 701.8a is what this call *is*: "To destroy a permanent, move it from
        the battlefield to its owner's graveyard." CR 702.12b then refuses it
        outright for a permanent with indestructible - "a permanent with
        indestructible can't be destroyed" - and the permanent stays where it is,
        undamaged in the bookkeeping sense: nothing is moved, nothing dies, no
        trigger fires.

        Note what this does **not** stop, because CR 701.8b draws the line: "The
        only ways a permanent can be destroyed are as a result of an effect that
        uses the word 'destroy' or as a result of the state-based actions that
        check for lethal damage (see rule 704.5g) or damage from a source with
        deathtouch (see rule 704.5h). If a permanent is put into its owner's
        graveyard for any other reason, it hasn't been 'destroyed.'" Sacrificing,
        exiling, bouncing, and CR 704.5f's toughness of 0 or less are not
        destruction and go through `put_into_graveyard` and friends directly.

        Run under `_id_allocator_scope`: `put_into_graveyard` below mints
        `permanent`'s new `zone_change_stamp` (`CardState.move_to`) and may
        emit a "dies" trigger of its own, both persisted ids. `check_state_
        based_actions`' own CR 704.5g/704.5h handling does not call this -
        `_state_based_actions_once` inlines the same `destruction_happens`-
        then-`put_into_graveyard` shape under its own scope instead - so this
        method has no wrapped caller to rely on: the api's `run_state_based_
        actions` calls it directly, once per creature with lethal damage,
        before ever calling `check_state_based_actions` itself
        (`engine_api.py` around line 861).
        """
        with self._id_allocator_scope():
            return self._destroy_impl(permanent, regeneration_allowed=regeneration_allowed)

    def _destroy_impl(
        self: "Game", permanent: CardState, *, regeneration_allowed: bool = True
    ) -> CardState:
        """The rest of `destroy` - see its own docstring for why it is split out."""
        if is_indestructible(permanent, self):
            return permanent  # CR 702.12b
        if has_shield_counter(permanent):
            # CR 122.1c: "If this permanent would be destroyed as the result
            # of an effect, instead remove a shield counter from it." A
            # hardcoded pre-check ahead of `destruction_happens`'s own
            # `apply_replacements` call, the identical shape indestructible
            # just above already is - `machines/replacement.py` (owned by a
            # different task this round) has no registered effect for a
            # shield counter to discover, so this is where CR 122.1c's own
            # "instead" has to happen instead. Consuming the counter here,
            # ahead of the call, means a permanent regeneration *and* a
            # shield counter would both stop is never asked to choose
            # between them (CR 616.1) - a shield counter always answers
            # first, the same "indestructible wins outright" simplification
            # this method already makes for the pair just above it.
            consume_shield_counter(permanent)
            return permanent
        if not self.destruction_happens(permanent, regeneration_allowed=regeneration_allowed):
            return permanent
        return self.put_into_graveyard(permanent)

    def regenerate(self: "Game", permanent: CardState) -> None:
        """Create a CR 701.19a regeneration shield on `permanent`.

        "If the effect of a resolving spell or ability regenerates a
        permanent, it creates a replacement effect that protects the permanent
        the next time it would be destroyed this turn." Creating the shield is
        all that happens now - CR 701.19c is explicit that "neither activating
        an ability that creates a regeneration shield nor casting a spell that
        creates a regeneration shield is the same as regenerating a
        permanent", so nothing is tapped, no damage is removed, and nothing is
        taken out of combat until the shield is actually spent
        (`machines/replacement._regeneration_effects`).

        A permanent that is no longer on the battlefield gets no shield: CR
        701.19a protects it against being *destroyed*, and CR 701.8a's
        destruction only ever happens there.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            return
        permanent.regeneration_shields += 1

    def destruction_happens(
        self: "Game", permanent: CardState, *, regeneration_allowed: bool = True
    ) -> bool:
        """Whether this destruction survives CR 614's replacement effects.

        CR 701.8c: "A regeneration effect replaces a destruction event", and
        CR 614.8 says regeneration is a destruction-replacement effect whose
        "instead" is implicit. Umbra armor (CR 702.89a) is the same shape
        without the counters. Both need the destruction to be a *replaceable
        event* in its own right rather than the graveyard move it would
        otherwise become, which is why this is raised before
        `put_into_graveyard` and separately from the `ZONE_CHANGE` that
        follows it.

        False means the destruction was called off and the permanent stays on
        the battlefield - nothing moves, nothing dies, no trigger fires.
        """
        event = apply_replacements(
            self,
            ReplaceableEvent(
                kind=EventKind.DESTROY,
                card=permanent,
                player=self.controller_of(permanent),
                regeneration_allowed=regeneration_allowed,
            ),
        )
        return event.happens

    def sacrifice(self: "Game", permanent: CardState) -> CardState:
        """Sacrifice a permanent (CR 701.21a).

        "To sacrifice a permanent, its controller moves it from the battlefield
        directly to its owner's graveyard." A player can't sacrifice something
        that isn't a permanent, so anything not on the battlefield is refused.

        Two trigger events are true of one sacrifice, and both fire. The
        permanent is sacrificed - CR 603.10a names "abilities that trigger when
        a player sacrifices a permanent" among those that look back in time,
        and the event is emitted while the permanent is still on the
        battlefield, so its own trigger reads it as it last existed there. And
        the permanent dies - CR 700.4's "dies" means "is put into a graveyard
        from the battlefield", which is exactly where CR 701.21a sends it - so
        the graveyard move goes through `put_into_graveyard`, whose dies event
        fires on arrival. The two are distinct events about one move, which is
        why a Dragon Appeasement and a "when this creature dies" trigger both
        fire for the same sacrifice.

        Run under `_id_allocator_scope`, the same as `destroy` just above:
        `put_into_graveyard` mints `permanent`'s new `zone_change_stamp` and
        may emit a "dies" trigger of its own, both persisted ids - found
        unscoped by T10's round-trip/replay invariant, which is what a
        sacrifice minting a plain `uuid4()` here looks like once a decoded
        replay is asked to reproduce it.
        """
        with self._id_allocator_scope():
            return self._sacrifice_impl(permanent)

    def _sacrifice_impl(self: "Game", permanent: CardState) -> CardState:
        """The rest of `sacrifice` - see its own docstring for why it is split out."""
        if permanent not in self.battlefield:
            raise ValueError(f"{permanent.name} is not a permanent on the battlefield")
        from ...machines.attacking_statics import cant_be_sacrificed

        if cant_be_sacrificed(self, permanent) is not None or sacrifice_caused_by_opponent(
            self, permanent
        ):
            # CR 101.2: "can't" beats the instruction to sacrifice; the
            # permanent stays where it is.
            return permanent
        # CR 701.21a names the permanent's controller as the player who
        # sacrifices it, so the record is kept under the controller it still
        # has here, before the move to the graveyard takes it away. Recorded
        # alongside the event rather than instead of it: the event is what
        # CR 603.10a's look-back triggers watch, and this is what CR 603.4's
        # "you sacrificed a permanent this turn" clause reads afterwards.
        sacrificer = permanent.controller
        if sacrificer is not None:
            self.permanents_sacrificed_this_turn[sacrificer] = (
                self.permanents_sacrificed_this_turn.get(sacrificer, 0) + 1
            )
            # The same fact as a turn fact, which is what a static ability's
            # "as long as you sacrificed a permanent this turn" reads off
            # `LayerContext` (Goblin Blast-Runner) - the layer engine sees
            # `turn_facts`, never the counter above.
            self.record_turn_fact("sacrificed_permanent", sacrificer)
        # CR 613.5: the sacrificed permanent's characteristics for this event
        # are the computed ones (a land animated by earthbend is a creature
        # only there), taken while it is still on the battlefield above.
        chars = self.characteristics_of(permanent)
        self.emit(
            GameEvent(
                event=TriggerEvent.IS_SACRIFICED,
                subject_id=permanent.id,
                subject_name=permanent.name,
                subject_controller=permanent.controller,
                subject_card=permanent.card,
                subject_types=chars.types,
                subject_subtypes=chars.subtypes,
                player=permanent.controller,
            )
        )
        return self.put_into_graveyard(permanent)

    def discard_cards(
        self: "Game", username: str | None, cards: list[CardState], source: str | None = None
    ) -> list[CardState]:
        """Discard `cards` together, as one CR 701.9a instruction, and fire
        "whenever you discard one or more cards" once for the whole batch.

        CR 603.2c: "An ability triggers only once each time its trigger event
        occurs. However, it can trigger repeatedly if one event contains
        multiple occurrences." A cost or an effect that discards several
        cards at once ("discard two cards", a cleanup discard down to
        maximum hand size, a `{Q}: Discard a card` cost) does so as a single
        instruction with a count, which is exactly what Captain Howler, Sea
        Scourge's own "for each card discarded this way" reads - so this
        emits one `DISCARDS_A_CARD` event carrying `amount=len(cards)`
        rather than one event per card. `machines.keywords.discard` still
        does the actual move, card by card, so madness (CR 702.35a) keeps
        replacing where each one lands.

        This is the one place that emits `DISCARDS_A_CARD` - `machines/
        cost.py`'s discard cost component and `machines/effects.py`'s
        `_discard_cards` both call it instead of moving cards straight to
        the graveyard, so a discard paid as a cost and a discard an effect
        causes both fire the trigger; `Player.discard_to_maximum_hand_size`
        (the cleanup step, CR 514.1) is the one remaining discard path that
        does not yet route through here - see `docs/engine-coverage.md`.
        """
        with self._id_allocator_scope():
            from ...machines.keywords import discard as discard_one  # avoids an import cycle

            if discard_caused_by_opponent(self, username):
                # CR 101.2: Tamiyo, Collector of Tales' "can't cause you to
                # discard cards" beats the opponent's instruction.
                return []
            discarded: list[CardState] = []
            for card in cards:
                discarded.append(discard_one(self, card, username))
            if not discarded:
                return discarded
            # CR 601.2f's "for each card you've cycled or discarded this turn"
            # (Hollow One) counts cards, not instructions, so a two-card discard
            # adds two. `username` may be None for a player-less scenario; there is
            # nobody to attribute the count to then, and nothing can read it back.
            if username is not None:
                self.cards_discarded_this_turn[username] = self.cards_discarded_this_turn.get(
                    username, 0
                ) + len(discarded)
            self.emit(
                GameEvent(
                    event=TriggerEvent.DISCARDS_A_CARD,
                    player=username,
                    amount=len(discarded),
                    # Titanbones, Towering Heart's own self-referential "When
                    # you discard this card, ..." - the batch's own ids, since
                    # a discard fires once for the whole instruction and any
                    # one of the discarded cards may be the self-referencing
                    # source.
                    discarded_ids=tuple(card.id for card in discarded),
                )
            )
            return discarded

    def put_into_graveyard(
        self: "Game", card_state: CardState, *, resolving: bool = False, discarded: bool = False
    ) -> CardState:
        """Move a card to its owner's graveyard, replacement effects included.

        Every route to a graveyard runs through here: a destroyed permanent, a
        resolved instant, a countered spell, a spell that fizzled. Each is "a
        card would be put into a graveyard", which is the event Rest in Peace,
        Leyline of the Void, Necrodominance, and Sanctifier en-Vec all watch for
        (CR 400.6, 614.1a).

        `resolving` is narrower than "this card is leaving the stack": it is
        true only for a spell's own successful CR 608 resolution, never for a
        countered spell (CR 701.6, which never resolves) or a fizzled one (CR
        608.2b, which explicitly "doesn't resolve" either). CR 702.88a's
        rebound reads "as it resolves" and needs exactly that distinction;
        `resolve_top` is the only caller that ever passes it `True`.

        A token's *first* trip here is allowed and is the whole of CR 111.7's
        parenthesis - "if a token changes zones, applicable triggered abilities
        will trigger before the token ceases to exist" - so a dying token really
        does reach a graveyard and really does fire its dies trigger (CR 700.4).
        A second trip is refused by CR 111.8.
        """
        with self._id_allocator_scope():
            if move_refused(card_state, Zone.GRAVEYARD) is not None:
                return card_state

            origin = card_state.zone
            was_on_battlefield = card_state in self.battlefield
            # CR 613.5 / CR 608.2h: the permanent's characteristics for both
            # emitters below are the computed ones - a land animated by
            # earthbend is a creature only there - snapshotted here, while it
            # is still on the battlefield, because the DIES emitter fires
            # after `_take_out_of_every_zone` below, once `characteristics_of`
            # would `KeyError` on it.
            left_battlefield_chars = (
                self.characteristics_of(card_state) if was_on_battlefield else None
            )
            if was_on_battlefield:
                self._note_left_battlefield(card_state)
                assert left_battlefield_chars is not None
                # CR 603.6c: the generic departure fires regardless of where the
                # card ends up - a replacement effect redirecting the destination
                # below still means this permanent left the battlefield.
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                        subject_id=card_state.id,
                        subject_name=card_state.name,
                        subject_controller=card_state.controller,
                        subject_card=card_state.card,
                        subject_types=left_battlefield_chars.types,
                        subject_subtypes=left_battlefield_chars.subtypes,
                        player=card_state.controller,
                    )
                )

            event = ReplaceableEvent(
                kind=EventKind.ZONE_CHANGE,
                card=card_state,
                origin=Zone.BATTLEFIELD if was_on_battlefield else origin,
                destination=Zone.GRAVEYARD,
                resolving=resolving,
                discarded=discarded,
                # CR 701.9a: a discard is caused by the spell or ability
                # resolving right now, if any (a cost or cleanup has none).
                cause_controller=(
                    self.resolving.controller if discarded and self.resolving is not None else None
                ),
            )
            apply_replacements(self, event)

            if event.destination is Zone.BATTLEFIELD:
                # CR 614.1a: a discard replaced by "put it onto the battlefield".
                return self.put_onto_battlefield(
                    card_state,
                    self._owner_of(card_state).username,
                    counters=dict(event.counters) or None,
                )

            self._take_out_of_every_zone(card_state)
            self.combat.remove(card_state.id)  # CR 506.4

            if event.destination is Zone.GRAVEYARD:
                self._owner_of(card_state).add(card_state, Zone.GRAVEYARD)
                # CR 400.6/400.3: one ledger entry per arrival, whoever's
                # graveyard it lands in and wherever it came from - see
                # `GraveyardArrival`'s own docstring for why this is a
                # general record rather than a single-purpose counter.
                self._record_graveyard_arrival(
                    card_state,
                    origin_zone=Zone.BATTLEFIELD if was_on_battlefield else origin,
                    permanent_types=(left_battlefield_chars.types if was_on_battlefield else None),
                )
            elif event.destination is Zone.EXILE:
                card_state.move_to(Zone.EXILE)
                self.exile.append(card_state)
                if event.exile_marker is not None:
                    # CR 715.3d: the controller exiled it, and may play it.
                    annotate_exile(card_state, event.exile_marker, card_state.controller, self)
                elif event.exile_link is not None:
                    # CR 607.1: exiled "with" the replacement's source.
                    card_state.exile_annotation = ExileAnnotation(
                        marker=ExileMarker.LINKED,
                        owner=card_state.owner,
                        turn_exiled=self.turn.turns_taken if self.turn is not None else None,
                        linked_permanent_id=event.exile_link.id,
                        linked_permanent_stamp=event.exile_link.zone_change_stamp,
                    )
                if event.exile_counters or event.exile_rider:
                    # CR 122.1 / CR 603.7: a resolving-exile replacement's
                    # counter and "If you do" rider (`machines/resolving_
                    # exile.py`).
                    from ...machines.resolving_exile import after_resolving_exile

                    after_resolving_exile(self, card_state, event)
            elif event.destination is Zone.LIBRARY:
                # Green Sun's Zenith's own "Shuffle [this] into its owner's
                # library" (`machines/replacement.py`'s `_stack_replacements`
                # redirects the destination here, off that same sentence). CR
                # 701.24c: the library is shuffled the moment the card lands in
                # it, even though it arrived straight off the stack rather than
                # out of a search - there is no separate scripted "then shuffle"
                # clause for this one the way a search effect prints its own.
                owner = self._owner_of(card_state)
                owner.add(card_state, Zone.LIBRARY)
                if event.library_position == "top":
                    # CR 401.4-style placement: "put it on top of its owner's library".
                    owner.library.insert(0, owner.library.pop())
                elif event.library_position is None:
                    self.shuffle_library(owner)
                # "bottom": `Player.add` appended it below every other card (CR 401.2).
            elif event.destination is Zone.HAND:
                self._owner_of(card_state).add(card_state, Zone.HAND)
            elif event.destination is Zone.BATTLEFIELD:
                # CR 614.1a: "put it onto the battlefield instead" - it enters
                # under its owner's control (CR 110.2a).
                self.put_onto_battlefield(card_state, self._owner_of(card_state).username)
            else:
                raise ValueError(f"a graveyard replacement sent {card_state.name} nowhere")

            self._accompany_meld_partner(card_state, event.destination)

            # CR 700.4: it only died if it actually reached a graveyard from the
            # battlefield. Exiled instead, the dies event never happened (CR 614.6).
            if was_on_battlefield and event.destination is Zone.GRAVEYARD:
                assert left_battlefield_chars is not None
                if Type.CREATURE in left_battlefield_chars.types:
                    self.creatures_died_this_turn += 1
                    if not is_token(card_state):
                        died_controller = left_battlefield_chars.controller or card_state.controller
                        if died_controller is not None:
                            self.nontoken_creatures_died_under_control_this_turn[
                                died_controller
                            ] = (
                                self.nontoken_creatures_died_under_control_this_turn.get(
                                    died_controller, 0
                                )
                                + 1
                            )
                self.emit(
                    GameEvent(
                        event=TriggerEvent.DIES,
                        subject_id=card_state.id,
                        subject_name=card_state.name,
                        # CR 603.10a: who controlled it as it died - layer 2
                        # (a borrowed creature, CR 613.1b), not the stored
                        # controller the zone change reset.
                        subject_controller=(
                            left_battlefield_chars.controller or card_state.controller
                        ),
                        subject_card=card_state.card,
                        # CR 603.10a: dies is a look-back event - the
                        # snapshot taken above, while the permanent was still
                        # on the battlefield, is that look-back: a live
                        # `characteristics_of` here would `KeyError` on an
                        # object `_take_out_of_every_zone` has already moved.
                        subject_types=left_battlefield_chars.types,
                        subject_subtypes=left_battlefield_chars.subtypes,
                        player=card_state.controller,
                        # CR 400.7e: the incarnation this move just minted
                        # (`Player.add` above already ran `CardState.move_to`,
                        # which stamped a fresh one), so a dead-self reader
                        # resolving later can tell this exact object apart
                        # from one that has since moved again.
                        zone_change_stamp=card_state.zone_change_stamp,
                    )
                )
            return card_state

    def graveyard_arrival_of(self: "Game", card_id: UUID) -> GraveyardArrival | None:
        """The *latest* arrival of `card_id` in a graveyard this turn, or None
        when it did not arrive this turn: a card that has since moved on is a
        new object (CR 400.7), so only its last trip counts."""
        latest = None
        for arrival in self.graveyard_arrivals_this_turn:
            if arrival.card_id == card_id:
                latest = arrival
        return latest

    def cards_put_into_graveyard_from_battlefield_this_turn(
        self: "Game", owner: str
    ) -> list[CardState]:
        """The cards in `owner`'s graveyard that were put there from the
        battlefield this turn (Supper for Spiders, Faith's Reward) - each
        still in that graveyard, and whose *latest* arrival this turn came off
        the battlefield: a card that has since left the graveyard, or left and
        came back some other way, is a new object (CR 400.7) this turn's
        death does not describe. In graveyard order."""
        latest: dict[UUID, Zone] = {}
        for arrival in self.graveyard_arrivals_this_turn:
            if arrival.card_id is not None and arrival.player == owner:
                latest[arrival.card_id] = arrival.origin_zone
        return [
            card for card in self.player(owner).graveyard if latest.get(card.id) is Zone.BATTLEFIELD
        ]

    def card_imprinted_on(self: "Game", permanent_id: UUID) -> CardState | None:
        """The card exiled *with* `permanent_id`, if any.

        Both markers that mean "exiled with this permanent" count: `ExileMarker.
        IMPRINTED`, left by `_parse_imprint_clause`, and `ExileMarker.HIDEAWAY`,
        left by CR 702.75a's own expansion. The two ability words differ; the
        link they leave behind is the same one, and a later ability naming "the
        exiled card" does not care which sentence exiled it.

        This is what "exiled with this land" means once it is read off the
        card's own printed text (`machines/effects.py`'s `_parse_imprint_
        clause`) rather than remembered from the plain-English sentence: a
        linear scan of the shared exile zone for the annotation `_parse_
        imprint_clause` left on the exiled card, matched by id rather than by
        object identity so it survives a round trip through persistence.
        Ugin's Labyrinth's own conditional mana ability (`ManaCondition.
        imprinted`) and its "Return the exiled card to its owner's hand"
        ability both call this rather than keeping their own pointer.
        """
        found = self.cards_imprinted_on(permanent_id)
        return found[0] if found else None

    def cards_imprinted_on(self: "Game", permanent_id: UUID) -> list[CardState]:
        """Every card exiled *with* `permanent_id` - CR 607.3's plural half of
        `card_imprinted_on`'s own linked-ability read.

        Ugin's Labyrinth and Fight Rigging's hideaway both ever exile at most
        one card with themselves, which is all `card_imprinted_on` (now this
        method's first hit, kept for those two callers) ever needed. Knowledge
        Pool links up to three cards per player on entry (CR 607.2a's own
        "each player exiles the top three cards of their library") plus
        whatever its second ability has exiled on earlier triggers (CR
        607.1c: an ability is linked to itself), and a later trigger has to
        offer *all* of them, not just the first one this scan happens to
        reach - the exact plural CR 607.3 names outright: "the ability refers
        to each of the exiled cards."

        Returned in the shared exile zone's own order, which is insertion
        order (`Game.exile_permanent`/`exile_top_of_library` append), not any
        particular game-meaningful order - nothing in the pool asks for one.
        """
        return self.cards_exiled_with(permanent_id, None)

    def cards_exiled_with(self: "Game", permanent_id: UUID, stamp: UUID | None) -> list[CardState]:
        """Every card exiled with the object `permanent_id`/`stamp` names
        (CR 607.2a), in the shared exile zone's own order.

        `cards_imprinted_on` is this with no stamp - the id alone. A reader
        that knows which incarnation of its source it belongs to passes that
        object's `zone_change_stamp` (or `AbilityOnStack.source_stamp`), and
        then a card an earlier incarnation exiled is not one of its own (CR
        400.7) - see `ExileAnnotation.links_to`."""
        return [
            card
            for card in self.exile
            if (annotation := card.exile_annotation) is not None
            and annotation.links_to(permanent_id, stamp)
        ]

    def meld(self: "Game", source: CardState, partner: CardState, result_card: Card) -> CardState:
        """CR 701.42a/712.4a/712.14c: meld `source` and `partner` into one
        melded permanent with `result_card`'s combined-back-face
        characteristics.

        "Meld is a keyword action ... To meld the two cards in a meld pair,
        put them onto the battlefield with their back faces up and combined.
        The resulting permanent is a single object represented by two
        cards." Both requirements this collapses to (CR 701.42b: "Only two
        cards belonging to the same meld pair can be melded") are the
        caller's to check before calling this at all - `machines/meld.py`'s
        clause parser only ever calls it once it has confirmed the
        controller both owns and controls both named cards on the
        battlefield - so this itself does not refuse anything; it melds.

        The steps, in CR 712.4a's own order: **exile both** (CR 701.13a,
        each its own ordinary leaves-the-battlefield event - they are not
        melded yet), then **put them onto the battlefield combined**
        (CR 712.14c). `source` survives as the one `CardState` this engine
        keeps in `Game.battlefield` for the pair - see `meld_result`'s own
        docstring for why a second, independent object is never created -
        and `partner` moves into `Game.melded_pairs`, off the battlefield
        list entirely, until CR 712.21 sends it back out again.

        `meld_combined_mana_value` (CR 202.3c/712.8g) is computed once, here,
        from both cards' own immutable front-face mana values - it never
        needs recomputing while melded.
        """
        with self._id_allocator_scope():
            controller = self.controller_of(source).username
            self.exile_permanent(source)
            self.exile_permanent(partner)
            # Both cards are momentarily real exiled objects (CR 701.13a) -
            # `partner` is about to stop being one of `Game.exile`'s own
            # cards and become the "held" half `Game.melded_pairs` keeps
            # instead, so it is lifted back out here rather than left
            # sitting in exile *and* referenced from `melded_pairs`, which
            # would be the same double-bookkeeping trap `models/action.py`'s
            # "ids only" convention exists to avoid.
            self._take_out_of_every_zone(partner)
            source.meld_result = result_card
            source.melded_partner_id = partner.id
            source.meld_combined_mana_value = source.card.cmc + partner.card.cmc
            partner.melded_partner_id = source.id
            self.put_onto_battlefield(source, controller)
            self.melded_pairs[source.id] = partner
            return source

    def mutate(self: "Game", permanent: CardState, component: CardState, *, on_top: bool) -> None:
        """CR 702.140c-d: `component` (the resolving mutating creature spell)
        merges with `permanent`, then CR 702.140d's "whenever a creature
        mutates" event is raised with the merged permanent as its subject."""
        from ...machines.abilities import TriggerEvent
        from ...machines.triggers.events import GameEvent

        with self._id_allocator_scope():
            self.merge(permanent, component, on_top=on_top)
            self.emit(
                GameEvent(
                    event=TriggerEvent.MUTATES,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=permanent.controller,
                    subject_card=permanent.card,
                    subject_types=permanent.types,
                    subject_subtypes=permanent.subtypes,
                    player=permanent.controller,
                )
            )

    def merge(self: "Game", permanent: CardState, component: CardState, *, on_top: bool) -> None:
        """CR 730.2: merge `component` (a resolving mutating creature spell,
        CR 702.140c) with `permanent`, over or under it.

        `permanent` stays the one `CardState` in `Game.battlefield` - CR
        730.2c: "a merged permanent is the same object that it was before",
        so its id, counters, attachments and the turn it came under its
        controller's control are untouched, and CR 730.2b: it "isn't
        considered to have just entered the battlefield", so no enters
        event. `component` is held in `Game.merged_components` (the
        `melded_pairs` shape), and the permanent's CR 730.2a copy effect is
        rebuilt from the new order: the topmost component's characteristics
        with every component's abilities (CR 702.140e).
        """
        from ...machines.face_down_keywords import merged_permanent_effect

        with self._id_allocator_scope():
            controller = permanent.controller
            self._take_out_of_every_zone(component)
            component.move_to(Zone.BATTLEFIELD)
            component.controller = controller
            order = list(permanent.merged_order) or [permanent.id]
            if on_top:
                order.insert(0, component.id)
            else:
                order.append(component.id)
            held = [*self.merged_components.get(permanent.id, []), component]
            self.merged_components[permanent.id] = held
            permanent.merged_order = order
            by_id = {state.id: state for state in (permanent, *held)}
            effects = merged_permanent_effect(self, permanent, [by_id[i] for i in order])
            self._end_merged_permanent_effect(permanent)
            for effect in effects:
                self.continuous_effects.add(effect, self)

    def _end_merged_permanent_effect(self: "Game", permanent: CardState) -> None:
        """Drop `permanent`'s CR 730.2a copy effect (a new merge replaces it;
        CR 730.3's departure ends it)."""
        from ...machines.face_down_keywords import MERGED_PERMANENT_EFFECT

        self.continuous_effects.effects = [
            effect
            for effect in self.continuous_effects.effects
            if effect.description != MERGED_PERMANENT_EFFECT or effect.source_id != permanent.id
        ]

    def _accompany_meld_partner(self: "Game", primary: CardState, destination: Zone) -> None:
        """CR 712.21: "If a melded permanent leaves the battlefield, one
        permanent leaves the battlefield and two cards are put into the
        appropriate zone." The primary's own move has already happened by
        the time a caller reaches this - every zone-leaving method
        (`put_into_graveyard`, `exile_permanent`, `return_to_hand`, `put_
        cards_into_library`, `ante`) calls this right after appending
        `primary` to `destination`'s own list - so this only has to bring
        the partner along and revert `primary` to its own printed identity.

        No second `LEAVES_THE_BATTLEFIELD`/`DIES` event is emitted for the
        partner: CR 712.21 counts the pair as *one* permanent leaving, which
        `primary`'s own emit (already done by the caller) already covers.
        CR 712.21a's owner's-choice ordering for a graveyard or library
        destination, and CR 712.21b's exile timestamp choice, are both
        simplified to a fixed order (`primary` then `partner`) rather than a
        live decision - recorded, not silently dropped, in `docs/engine-
        coverage.md`'s Not-modelled table.
        """
        # CR 730.3: "If a merged permanent leaves the battlefield, one
        # permanent leaves the battlefield and each of the individual
        # components are put into the appropriate zone." CR 730.3a's
        # owner's-choice order is simplified to the merge order, as CR
        # 712.21a's is for a melded pair.
        components = self.merged_components.pop(primary.id, None)
        if components is not None:
            self._end_merged_permanent_effect(primary)
            primary.merged_order = []
            for component in components:
                self._accompany_into(component, destination)
        partner = self.melded_pairs.pop(primary.id, None)
        if partner is None:
            return
        primary.meld_result = None
        primary.melded_partner_id = None
        primary.meld_combined_mana_value = None
        partner.melded_partner_id = None
        self._accompany_into(partner, destination)

    def _accompany_into(self: "Game", card: CardState, destination: Zone) -> None:
        """Put a melded partner or merged component into `destination`."""
        if destination.is_shared:
            # A shared zone is appended to directly (there is no `Player.add`
            # for it), so this is the one place that has to call `move_to`
            # itself - `Player.add` below already does, for a per-player one.
            card.move_to(destination)
            self.shared_zones[destination].append(card)
        else:
            self._owner_of(card).add(card, destination)

    def _exile_arrival_of(
        self: "Game", card: CardState, from_battlefield: bool, graveyard_owner: str | None
    ) -> "ExileArrival | None":
        """The ledger entry for a battlefield or graveyard card about to be
        exiled (CR 406.2), read before it moves: a permanent as it last
        existed (CR 603.10a, so a borrowed creature counts for its controller
        and an animated artifact as a creature), a graveyard card by its
        printed types."""
        if from_battlefield:
            chars = self._left_battlefield_characteristics.get(card.id)
            return ExileArrival(
                card_id=card.id,
                player=(chars.controller if chars is not None else None) or card.controller,
                origin_zone=Zone.BATTLEFIELD,
                is_creature=Type.CREATURE in (chars.types if chars is not None else card.types),
                is_token=card.token,
            )
        if graveyard_owner is not None:
            return ExileArrival(
                card_id=card.id,
                player=graveyard_owner,
                origin_zone=Zone.GRAVEYARD,
                is_creature=Type.CREATURE in card.types,
                is_token=card.token,
            )
        return None

    def exile_permanent(self: "Game", permanent: CardState) -> CardState:
        """Move a permanent to the shared exile zone.

        Refused for a token that has already left the battlefield (CR 111.8).

        Emits `TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE` when the move was
        actually from the battlefield - the "or is put into exile" half of
        CR 701.66a's earthbend, and the general battlefield-to-exile event
        `machines/triggers.py` never had before: `DIES` already exists for the
        battlefield-to-graveyard half of the same idea, but nothing watched
        this one, so a delayed trigger waiting for it had nothing to fire on.

        A card exiled *out of a graveyard* raises the graveyard pair as well -
        `ExtraTriggerEvent.LEAVES_GRAVEYARD` (CR 603.10a names "abilities that
        trigger when a card leaves a graveyard" outright) and
        `ExtraTriggerEvent.EXILED_FROM_GRAVEYARD` (CR 406.2: "To exile an
        object is to put it into the exile zone from whatever zone it's
        currently in", read here for the graveyard as that zone). One card, so
        `amount=1`; `exile_cards` is the batch door for an instruction that
        moves several at once.
        """
        with self._id_allocator_scope():
            origin_graveyard_owner = self._graveyard_owner_of(permanent)
            self._exile_move(permanent)
            if origin_graveyard_owner is not None and permanent.zone is Zone.EXILE:
                self._emit_left_graveyard(origin_graveyard_owner, [permanent])
            return permanent

    def _exile_move(self: "Game", permanent: CardState) -> CardState:
        """`exile_permanent`'s move and its battlefield events, with the
        graveyard pair left to the caller - so `exile_cards` can raise one
        event for a whole instruction (CR 603.2c)."""
        if move_refused(permanent, Zone.EXILE) is not None:
            return permanent
        was_on_battlefield = permanent in self.battlefield
        graveyard_owner = self._graveyard_owner_of(permanent)
        if was_on_battlefield:
            self._note_left_battlefield(permanent)
            self._detach_dependents(permanent)
        arrival = self._exile_arrival_of(permanent, was_on_battlefield, graveyard_owner)
        self._take_out_of_every_zone(permanent)
        self.combat.remove(permanent.id)  # CR 506.4
        permanent.move_to(Zone.EXILE)
        self.exile.append(permanent)
        if arrival is not None:
            self.exile_arrivals_pending.append(arrival)
        self._accompany_meld_partner(permanent, Zone.EXILE)
        if was_on_battlefield:
            self.emit(
                GameEvent(
                    event=TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=permanent.controller,
                    subject_card=permanent.card,
                    player=permanent.controller,
                )
            )
            # CR 603.6c: the generic departure, alongside the destination-
            # specific event just above - see `Game.put_into_graveyard`'s
            # matching emit for why both fire.
            self.emit(
                GameEvent(
                    event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=permanent.controller,
                    subject_card=permanent.card,
                    player=permanent.controller,
                )
            )
        return permanent

    @property
    def ante_zone(self: "Game") -> list[CardState]:
        """CR 400.1's optional eighth zone, shared and public (CR 400.2)."""
        return self.shared_zones[Zone.ANTE]  # type: ignore[return-value]

    def ante(self: "Game", card_state: CardState, anteing_player: str | None = None) -> bool:
        """Ante a card, and answer whether it actually moved (CR 407.4).

        CR 407.4: "To ante an object is to put that object into the ante zone
        from whichever zone it's currently in. The owner of an object is the
        only player who can ante that object." Both halves are here: the move
        is out of *whatever* zone the card is in, and a player who is not the
        owner is refused outright rather than quietly succeeding.

        The boolean is what Jeweled Bird's "Ante this artifact. **If you do**,
        ..." reads: an ante that was refused leaves the whole rest of the
        ability undone, which is the stolen-Bird ruling DDR#666 walks through.

        `anteing_player` defaults to the card's own controller, which is who is
        activating the ability that says to ante it - and for a permanent an
        opponent has stolen, that is exactly the player CR 407.4 refuses.

        CR 407.3 is why there is no other door into this zone: "A few cards
        have the text 'Remove this card from your deck before playing if you're
        not playing for ante.' These are the only cards that can add or remove
        cards from the ante zone or change a card's ownership."
        """
        with self._id_allocator_scope():
            anteing_player = (
                anteing_player if anteing_player is not None else card_state.controller_or_owner
            )
            owner = card_state.owner
            if owner is None or anteing_player != owner:
                return False
            was_on_battlefield = card_state in self.battlefield
            if was_on_battlefield:
                self._note_left_battlefield(card_state)
                self._detach_dependents(card_state)
            self._take_out_of_every_zone(card_state)
            self.combat.remove(card_state.id)  # CR 506.4
            card_state.move_to(Zone.ANTE)
            self.ante_zone.append(card_state)
            self._accompany_meld_partner(card_state, Zone.ANTE)
            if was_on_battlefield:
                # CR 603.6c's generic departure. There is no ante-specific trigger
                # event, and nothing in the pool watches for one.
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                        subject_id=card_state.id,
                        subject_name=card_state.name,
                        subject_controller=card_state.controller,
                        subject_card=card_state.card,
                        player=card_state.controller,
                    )
                )
            return True

    def exile_cards(self: "Game", cards: Sequence[CardState]) -> list[CardState]:
        """Exile several cards as one instruction (CR 406.2).

        The batch door onto `exile_permanent`. Everything about the move itself
        is identical - each card goes through the same path, keeping the
        battlefield departure events, CR 111.8's token refusal and CR 506.4's
        combat clean-up - but the graveyard pair is raised **once** for the
        whole instruction rather than once per card.

        That is CR 603.2c: "An ability triggers only once each time its trigger
        event occurs. However, it can trigger repeatedly if one event contains
        multiple occurrences." A condition written "whenever **one or more**
        cards leave your graveyard" (Hardened Academic) is asking about the
        event, not about each card in it, so a delve payment that exiles five
        cards (CR 702.66a: "For each generic mana in this spell's total cost,
        you may exile a card from your graveyard rather than pay that mana") is
        one event with `amount=5`, and the ability triggers once.

        Grouped by whose graveyard each card left, because "your graveyard" is
        read off the owner of the zone: two graveyards emptied by one
        instruction are two events, one per graveyard, each with its own count.
        """
        with self._id_allocator_scope():
            by_graveyard: dict[str, list[CardState]] = {}
            exiled: list[CardState] = []
            for card_state in cards:
                owner = self._graveyard_owner_of(card_state)
                self._exile_move(card_state)
                exiled.append(card_state)
                if owner is not None and card_state.zone is Zone.EXILE:
                    by_graveyard.setdefault(owner, []).append(card_state)
            for owner, gone in by_graveyard.items():
                self._emit_left_graveyard(owner, gone)
            return exiled

    def _graveyard_owner_of(self: "Game", card_state: CardState) -> str | None:
        """Whose graveyard this card is in right now, if it is in one.

        CR 404.1's graveyard is a per-player zone, and the "your" in "whenever
        one or more cards leave **your** graveyard" is the player whose
        graveyard it was - not whoever's effect moved the card - so this
        answers by finding the zone the card is actually sitting in rather than
        by reading `CardState.owner`.
        """
        if card_state.zone is not Zone.GRAVEYARD:
            return None
        for player in self.players:
            if any(state is card_state for state in player.graveyard):
                return player.username
        return None

    def _detach_dependents(self: "Game", permanent: CardState) -> None:
        """Nothing stays attached to a permanent that just left (CR 704.5m, 704.5n).

        `CardState.move_to` (CR 400.7) already clears `permanent`'s *own*
        `attachment` as it leaves - what it cannot clear is every *other*
        permanent's `attached_to`, which points at `permanent.id` rather than
        at the object itself. This engine mutates a `CardState` in place
        rather than minting a fresh id when it returns (`zone_change_stamp`
        is the id-survives-the-round-trip marker instead - see
        `DelayedTrigger.expected_stamp`), so a permanent exiled and put back
        onto the battlefield **within the same resolution** - Ephemerate's
        "exile ..., then return it" is one instruction, with no state-based
        action check in between (CR 704.3 only runs before a player would
        next receive priority) - would otherwise have the exact same id both
        times, and an Aura or Equipment still holding that id would silently
        "follow" the blink with nothing ever catching it: the ordinary
        `aura_state_based_actions`/`equipment_state_based_actions` sweep in
        `check_state_based_actions` never gets a turn to run against the
        moment in between where the id was genuinely gone.

        Clearing the pointer here, the instant the permanent actually leaves,
        is what a live SBA sweep would have found anyway had one run right
        then: the ordinary sweep that *does* run once the whole spell finishes
        resolving is what turns this into the real CR 704.5m/n consequence -
        an Aura pointing at nothing goes to its owner's graveyard, an
        Equipment pointing at nothing simply stays on the battlefield
        unattached - so this only ever moves that discovery earlier, never
        replaces it.
        """
        for other in self.battlefield:
            if other.id != permanent.id and other.attached_to == permanent.id:
                other.unattach()

    def _remember_sources_that_ceased_to_exist(self: "Game", gone: list[CardState]) -> None:
        """Keep each vanished token as the last known information of every
        ability on the stack or waiting to go there that it is the source of.

        CR 113.7a: "Once activated or triggered, an ability exists on the stack
        independently of its source", and CR 608.2h has an effect that needs
        the source use its last known information once it has left its zone. A
        token that ceases to exist (CR 704.5d) leaves nothing to find by id.
        """
        by_id = {state.id: state for state in gone}
        for item in (*self.stack, *self.pending_triggers):
            if (
                isinstance(item, AbilityOnStack)
                and item.source_id in by_id
                and item.source_last_known is None
            ):
                item.source_last_known = by_id[item.source_id]

    def graveyard_land_permission(self: "Game", land: CardState, username: str) -> CardState | None:
        """The permanent whose "You may play lands from your graveyard." lets
        `username` play this land from their own graveyard (CR 305.1, CR
        611.3d), or None. Read off the computed abilities of the permanents
        `username` controls (CR 613.5); "your graveyard" is the land's owner's,
        so only a land `username` owns qualifies."""
        if land.zone is not Zone.GRAVEYARD or land.owner != username:
            return None
        from ...machines.protection_statics import graveyard_land_play_prohibited

        if graveyard_land_play_prohibited(self, username):
            # "Your opponents can't play land cards from graveyards." (Tomik):
            # a "can't" beats any "may" (CR 101.2).
            return None
        board = self.computed_board()
        for permanent in self.permanents_controlled_by(username):
            if any(plays_lands_from_graveyard_line(line) for line in board.of(permanent).abilities):
                return permanent
        from ...machines.casting import static_graveyard_land_source

        source = static_graveyard_land_source(self, land, username)
        return None if source is None else source[0]

    def _looks_at_top_card_any_time_line(self: "Game", text: str) -> bool:
        """Whether one static line is "You may look at the top card of your
        library any time." - Daredevil's own "Radar Sense — " label stripped
        first."""
        stripped = self._static_line_without_ability_word(text)
        if self._LOOK_AT_TOP_CARD_ANY_TIME_RE.fullmatch(stripped) is not None:
            return True
        if self._LOOK_AT_TOP_AND_FACE_DOWN_ANY_TIME_RE.fullmatch(stripped) is not None:
            return True
        from ...machines.casting import static_zone_cast_permission

        permission = static_zone_cast_permission(text)
        return permission is not None and permission.looks_at_top

    def become_prepared(self: "Game", permanent: CardState) -> CardState | None:
        """CR 722.3a: give `permanent` the prepared designation.

        "Some spells and abilities cause a permanent with a prepare spell to
        become prepared or state that a permanent enters prepared. If that
        permanent has the alternative characteristics of a prepare spell,
        this gives the permanent the 'prepared' designation. ... A permanent
        can't gain this designation unless it has a prepare spell.
        Additionally, a permanent can't gain this designation if the
        permanent already has it." Both refusals are silent no-ops, not
        errors: Codie's "each creature you control becomes prepared" and
        Hexhaven Dueling Arena's "target creature becomes prepared" are
        printed to apply to any creature, most of which have no prepare
        spell at all, and CR 722.3a's own second sentence is what makes an
        already-prepared permanent's own upkeep trigger a no-op rather than a
        second copy.

        CR 722.3c: "its controller creates a copy of that object in exile,
        except that copy has only the characteristics of that permanent's
        prepare spell ... Those characteristics become the copy's normal
        characteristics. This copy remains in exile for as long as the
        prepared permanent remains on the battlefield and has the prepared
        designation. This is an exception to rule 704.5e. For as long as the
        copy remains in exile, the prepared permanent's controller may cast
        the copy." The copy is minted here, `prepare_spell_face=True` (read
        by `CardState.up_face`), and a standing `PlayPermission` is granted
        for it with no time limit - `become_unprepared` below, called
        whenever the designation or the permanent itself goes away, is what
        actually enforces the "for as long as" half, since nothing in this
        engine yet dispatches the general CR 704.5e state-based action (see
        `docs/engine-coverage.md`).

        Returns the exile copy, or `None` if the permanent could not gain the
        designation.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            return None
        if permanent.card.prepare_spell is None:
            return None
        if permanent.prepared:
            return None
        controller = permanent.controller or permanent.owner
        if controller is None:
            return None
        with self._id_allocator_scope():
            copy = CardState(
                card=permanent.card,
                zone=Zone.EXILE,
                controller=controller,
                owner=permanent.owner,
                is_copy=True,
                prepare_spell_face=True,
            )
            self.exile.append(copy)
            permanent.prepared = True
            permanent.prepared_copy_id = copy.id
            self.grant_play_permission(
                copy,
                controller,
                source_name=permanent.name,
                rule="CR 722.3c",
                zone=Zone.EXILE,
                until_end_of_turn=False,
            )
        return copy

    def become_unprepared(self: "Game", permanent: CardState) -> None:
        """CR 722.3b: remove the prepared designation from `permanent`.

        "A rule or effect may cause a permanent to become 'unprepared.' This
        removes the prepared designation from that permanent." A no-op if it
        was never prepared. The linked CR 722.3c exile copy is removed along
        with the designation - unless it has already moved to the stack
        (`Game.put_on_stack`'s own CR 601.2i hook clears the designation
        there without touching the copy, which by then is no longer in
        `self.exile` for this to find): the copy's "remains in exile for as
        long as ... the prepared designation" holds is exactly this call's
        other half.

        Called by `Game.enter_the_battlefield`'s "enters prepared" hook (which
        never finds an existing designation to remove), by the "becomes
        unprepared" clause parser, and by `Game._note_left_battlefield` for
        every route a permanent takes off the battlefield.
        """
        if not permanent.prepared:
            return
        permanent.prepared = False
        copy_id = permanent.prepared_copy_id
        permanent.prepared_copy_id = None
        if copy_id is None:
            return
        copy = next((state for state in self.exile if state.id == copy_id), None)
        if copy is not None:
            self.exile.remove(copy)
        self.play_permissions = [
            permission for permission in self.play_permissions if permission.card_id != copy_id
        ]

    def _entered_this_turn(self: "Game", permanent: CardState) -> bool:
        """Whether this permanent arrived on the battlefield this turn.

        `CardState.turn_entered` is the turn-number stamp `Game.
        enter_the_battlefield` writes once, per CR 702.131's own "entered
        this turn" shape (see that field's docstring); this is the plain
        equality check against the game's current turn, shared by every
        caller that only needs the yes/no answer - `activation_cost`'s own
        CR 702.193b discount among them.
        """
        return (
            permanent.turn_entered is not None
            and self.turn is not None
            and permanent.turn_entered == self.turn.turns_taken
        )

    def _owner_of(self: "Game", state: CardState) -> Player:
        """Whose private zones a card goes to when nobody names a player (CR 108.3).

        `CardState.owner` is the actual answer - set once when the card
        entered the game and never keyed to the zone it happens to sit in
        right now, unlike `find_owner`'s zone lookup (which cannot answer at
        all for a card already taken out of every zone on its way to a new
        one - milling from *bob's* library was landing in whoever the active
        player was, because by the time this ran the card had already left
        bob's zones). Only a card with no `owner` set at all - most of this
        engine's own test fixtures, which usually skip it - falls back to
        `controller_of`'s active-player default.
        """
        return self.player(state.owner) if state.owner else self.controller_of(state)

    def find_owner(self: "Game", state: CardState) -> Player | None:
        """Whose card this is, by the zone it is sitting in.

        Ownership is not modelled separately from control (see
        `docs/engine-coverage.md`), so this asks the only question the model can
        answer: which player's zones hold it. A card on the battlefield, the
        stack, or in exile is in a shared zone and has no owner to find that
        way, so its controller stands in.
        """
        for player in self.players:
            for zone_cards in player.zones.values():
                if state in zone_cards:
                    return player
        return self.player(state.controller) if state.controller else None


from ._common import _DRAW_OR_LIFE_GAIN_PROHIBITION_RE, _DRAW_PROHIBITION_RE  # noqa: E402
from .records import LibraryOrderKept, TurnHistoryEntry  # noqa: E402

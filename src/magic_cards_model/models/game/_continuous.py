import itertools
import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Literal
from uuid import NAMESPACE_OID, UUID, uuid5

from ...data.subtypes import canonical_subtype
from ...ids import install_id_allocator, reset_id_allocator
from ...machines.abilities import (
    AbilityKind,
    ActivatedAbility,
    parse_abilities,
    self_normalized_effect_text,
)
from ...machines.casting import (
    PlayAction,
    PlayPermission,
    player_keyword_grant_of_line,
)
from ...machines.casting_restrictions import (
    CastingRuleKind,
)
from ...machines.combat import (
    Keyword,
)
from ...machines.cost import (
    CostModifierKind,
    CostModifierNotice,
    activated_ability_group_discount_effect,
    cost_modifier_effect,
    looks_like_unparsed_cost_modifier,
)
from ...machines.cost.groups import group_spell_modifier
from ...machines.cost.statics import CostContext
from ...machines.decisions import (
    Decision,
    DecisionKind,
)
from ...machines.keyword_counters import (
    conditional_group_keyword_grant_of_line,
)
from ...machines.layers import (
    LOST_LIFE_TURN_FACT,
    SPELLS_HAVE_SPLIT_SECOND_TEXT,
    Characteristics,
    ComputedBoard,
    ContinuousEffect,
    Duration,
    Layer,
    LayerContext,
    all_activated_abilities_grant,
    compute_board,
    effects_for,
    grant_ability,
    off_battlefield_characteristics_of,
    only_this_incarnation,
)
from ...machines.next_spell import (
    next_spell_keyword_grants_for,
    spell_has_quality,
)
from ...machines.protection_statics import player_keyword_grants
from ...machines.replacement import (
    EventKind,
    ReplaceableEvent,
    apply_replacements,
)
from ...machines.revealed_information import hand_revealed_by_others, top_card_revealed_by_others
from ...machines.triggers import (
    ExtraTriggerEvent,
    GameEvent,
)
from ...machines.zone_grants import apply_zone_characteristics
from ...snapshot import board_snapshot, cached_board
from ..card import (
    Card,
    Layout,
    Supertype,
    Type,
    has_changeling,
    with_every_creature_type,
)
from ..card_state import (
    CardState,
    ChoiceKind,
    Counter,
    ExileMarker,
    TargetRef,
)
from ..mana import ManaCost
from ..player import Player, PlayerTargetingGrant
from ..token import (
    TokenDefinition,
)
from ..zone import Zone
from ._common import StackObject

if TYPE_CHECKING:
    from . import Game


#: Every keyword `machines/combat.Keyword` executes, lower case - what
#: `Game._keep_keywords_gained_as_a_spell` carries from a spell onto the
#: permanent it becomes (CR 400.7a).
_COMBAT_KEYWORDS: frozenset[str] = frozenset(keyword.value for keyword in Keyword)


#: "mana value 3 or greater" (Mistmeadow Skulk): CR 202.3's mana value against
#: a number, exactly or with "or greater/more" / "or less/fewer".
_MODE_BULLET_STATIC_RE = re.compile(r"^•\s*(?P<mode>[A-Z][\w'-]*)\s+—\s+(?P<body>.+)$", re.DOTALL)
_MANA_VALUE_QUALITY_RE = re.compile(
    r"^mana values? (?P<number>\d+)(?: or (?P<bound>greater|more|less|fewer))?$", re.IGNORECASE
)


#: "each mana value other than 3" (Haktos the Unscarred's chosen number, once
#: `Game._effective_protection_qualities` has read "the chosen number" off the
#: protected permanent's own choice) or the unresolved "... the chosen number",
#: which protects from nothing because no number was chosen.
_OTHER_MANA_VALUE_QUALITY_RE = re.compile(
    r"^each mana value other than (?P<number>\d+|the chosen number)$", re.IGNORECASE
)


def _characteristic_quality(quality: str) -> Callable[[Characteristics], bool] | None:
    """A protection quality that is a test on the source's computed
    characteristics (CR 702.16a: "any characteristic value or information"),
    or `None` when it is not one: a mana-value comparator, or a counted noun
    phrase `_permanent_quality` reads - a creature type or other subtype in the
    plural ("Demons", "Elves", "Arcane"), a supertype ("snow"), or a type
    qualified by one ("God creatures")."""
    wanted = quality.strip()
    other = _OTHER_MANA_VALUE_QUALITY_RE.match(wanted)
    if other is not None:
        if not other.group("number").isdigit():
            return lambda chars: False
        number = int(other.group("number"))
        return lambda chars: chars.mana_value != number
    match = _MANA_VALUE_QUALITY_RE.match(wanted)
    if match is not None:
        number = int(match.group("number"))
        bound = (match.group("bound") or "").lower()
        if bound in ("greater", "more"):
            return lambda chars: chars.mana_value >= number
        if bound in ("less", "fewer"):
            return lambda chars: chars.mana_value <= number
        return lambda chars: chars.mana_value == number
    return _permanent_quality(wanted)


def _card_characteristics(card: Card, mana_value: float | None = None) -> Characteristics:
    """A bare printing's characteristics as a protection source: changeling's
    every creature type (CR 702.73a) included, since it works everywhere."""
    subtypes = tuple(card.subtypes)
    if has_changeling(card.oracle_text):
        subtypes = with_every_creature_type(tuple(card.types), subtypes)
    return Characteristics(
        card_id=card.id,
        name=card.name,
        mana_value=card.cmc if mana_value is None else mana_value,
        supertypes=tuple(card.supertypes),
        types=tuple(card.types),
        subtypes=subtypes,
        colors=tuple(card.colors),
    )


def _characteristic_word(word: str) -> Callable[[Characteristics], bool] | None:
    """One word of a counted noun phrase as a test on computed characteristics,
    or None when the word names nothing this reads.

    A color (CR 105.1; "colorless" is CR 105.2c's "no color"), a supertype
    (CR 205.4a: basic, legendary, ongoing, snow, world), a card type in the
    singular or plural (CR 205.2a), or a subtype (CR 205.3, read back from its
    printed plural by `canonical_subtype`). A "non" prefix negates any of
    those ("nonland", "non-Human").
    """
    lowered = word.lower()
    if lowered.startswith("non") and len(lowered) > 4:
        inner = _characteristic_word(lowered.removeprefix("non").lstrip("-"))
        if inner is None:
            return None
        return lambda chars: not inner(chars)
    if lowered == "colorless":
        return lambda chars: not chars.colors
    color = _COLOR_WORDS.get(lowered)
    if color is not None:
        return lambda chars: color in chars.colors
    supertype = next((each for each in Supertype if each.value == lowered), None)
    if supertype is not None:
        return lambda chars: supertype in chars.supertypes
    card_type = _card_type_named(lowered)
    if card_type is not None:
        return lambda chars: card_type in chars.types
    subtype = canonical_subtype(word)
    if subtype is not None:
        return lambda chars: any(each.lower() == subtype for each in chars.subtypes)
    return None


#: Solemnity's "Players can't get counters." - CR 122.6's counters given to a
#: player (poison, energy, experience ...) never arrive while it is on the
#: battlefield (CR 604.2, CR 611.3a), read by `Game.player_counters_prohibited`
#: from `add_player_counters`, the one door every player counter uses.
_PLAYER_COUNTERS_PROHIBITION_RE = re.compile(
    r"^(?:players|each player) can'?t get counters\.?$", re.IGNORECASE
)

#: Melira, Sylvok Outcast's "You can't get poison counters." - the same CR
#: 122.6 prohibition, scoped to its controller and to one kind of counter.
_OWN_KIND_COUNTERS_PROHIBITION_RE = re.compile(
    r"^you can'?t get (?P<kind>[a-z]+) counters\.?$", re.IGNORECASE
)


def is_player_rules_static_line(text: str) -> bool:
    """Whether a permanent's static line is one of the rules-of-the-game
    effects `Game` reads straight off the battlefield: "Players can't gain
    life." and "Your opponents can't gain life." (`life_gain_prohibited`, CR
    119.7), "Players can't draw cards[ or
    gain life]." (`draw_prohibited`, CR 121.3), or "[Combat] damage can't be
    prevented." (`damage_cant_be_prevented`, CR 615.12)."""
    line = text.strip()
    return bool(
        _LIFE_GAIN_PROHIBITION_RE.match(line)
        or _OPPONENTS_LIFE_GAIN_PROHIBITION_RE.match(line)
        or _ENCHANTED_PLAYER_LIFE_GAIN_PROHIBITION_RE.match(line)
        or _DRAW_PROHIBITION_RE.match(line)
        or _DRAW_OR_LIFE_GAIN_PROHIBITION_RE.match(line)
        or _DAMAGE_CANT_BE_PREVENTED_RE.fullmatch(line)
        or _PLAYER_COUNTERS_PROHIBITION_RE.match(line)
        or _OWN_KIND_COUNTERS_PROHIBITION_RE.match(line)
    )


#: CR 701.54c: "they get an emblem named The Ring".
RING_EMBLEM_NAME = "The Ring"

#: CR 701.54c's abilities of The Ring, in the order the rule grants them: the
#: first from the first tempt, and each further one "as long as the Ring has
#: tempted that player" two, three and four or more times. Written in the
#: rule's own words so the ordinary readers - `machines/layers.py`'s static
#: parser, `machines/triggers.py`'s conditions and `machines/effects.py`'s
#: clauses - read them off the emblem exactly as they would off a card.
RING_EMBLEM_ABILITIES: tuple[str, ...] = (
    "Your Ring-bearer is legendary and can't be blocked by creatures with greater power.",
    "Whenever your Ring-bearer attacks, draw a card, then discard a card.",
    "Whenever your Ring-bearer becomes blocked by a creature, the blocking creature's "
    "controller sacrifices it at end of combat.",
    "Whenever your Ring-bearer deals combat damage to a player, each opponent loses 3 life.",
)


def _emblem_card(name: str, text: str) -> Card:
    """An emblem's object (CR 114.3): no characteristics but its name and
    abilities. Built through `TokenDefinition`, whose card id is a pure
    function of those - two emblems with different text never share one."""
    definition = TokenDefinition(types=(), name=name, rules_text=text.strip())
    return definition.to_card().model_copy(update={"layout": Layout.EMBLEM, "type_line": "Emblem"})


def ring_emblem_text(tempted: int) -> str:
    """The Ring's rules text for a player the Ring has tempted `tempted`
    times (CR 701.54c) - every ability up to that level, one per line."""
    return "\n".join(RING_EMBLEM_ABILITIES[: max(1, min(tempted, len(RING_EMBLEM_ABILITIES)))])


class ContinuousMixin:
    def permanents_controlled_by(self: "Game", username: str) -> list[CardState]:
        """Battlefield permanents this player controls.

        A permanent with no controller set counts as the active player's, so a
        one-player scenario does not have to label every card.
        """
        return [
            state
            for state in self.battlefield
            if state.controller == username or state.controller is None
        ]

    def _controlled_land_types(self: "Game", controller: str) -> frozenset[str]:
        """Land subtypes (CR 205.3i) this player controls, as single words.

        Feeds `ManaAbility.resolve`'s conditional "If you control an Urza's
        Mine and an Urza's Power-Plant, ..." clauses. CR 305.5: "Land
        subtypes are always a single word", which is why `Card.subtypes`
        already reads "Urza's Mine" as the two words "Urza's" and "Mine" -
        the same words `machines/abilities.py` reads off the condition's own
        printed sentence - so nothing further needs parsing here.

        CR 613.5: read off the computed board, not the printed line - Blood
        Moon (CR 305.7's set-a-land's-subtype path) replaces a nonbasic
        land's subtypes with Mountain, and a permanent controlled by
        `_controlled_land_types` is the one every consumer here means to ask
        about right now, not the printed card underneath it.
        """
        board = self.computed_board()
        return frozenset(
            subtype
            for state in self.permanents_controlled_by(controller)
            if state.zone is Zone.BATTLEFIELD and Type.LAND in board.of(state).types
            for subtype in board.of(state).subtypes
        )

    def static_skips_draw_step(self: "Game") -> bool:
        """Whether a permanent the active player controls says "Skip your draw
        step." (CR 614.10) - `replacement.draw_step_skipped_by`."""
        from ...machines.replacement import draw_step_skipped_by

        assert self.turn is not None
        return draw_step_skipped_by(self, self.turn.active_player) is not None

    def _granted_by_preceding_sentence(
        self: "Game",
        source: CardState,
        before: list[str],
        permanent: CardState,
        ability: ActivatedAbility,
    ) -> bool:
        """Whether `ability` on `permanent` is one of the abilities the grant
        sentence just before a "those abilities" permission gives (Drana and
        Linvala) - the antecedent of "those" (CR 613.1f's grant)."""
        if not before:
            return False
        legendary = Supertype.LEGENDARY in source.card.supertypes
        antecedent = self_normalized_effect_text(source.name, before[-1], legendary=legendary)
        grant = all_activated_abilities_grant(antecedent)
        if grant is None:
            return False
        board = self.computed_board().characteristics
        chars = board.get(permanent.id)
        if chars is None or not grant.selector(source)(chars, board):
            return False
        if grant.from_exile:
            texts = grant.exile_texts(source, LayerContext(exile=tuple(self.exile)))
        else:
            texts = grant.board_modification(source).texts(board, permanent.id)
        return ability.raw in texts

    def _keep_keywords_gained_as_a_spell(self: "Game", permanent: CardState) -> None:
        """CR 400.7a: "Effects from spells, activated abilities, and triggered
        abilities that change the characteristics or controller of a
        permanent spell on the stack continue to apply to the permanent that
        spell becomes." A keyword such an effect gave the spell - Choreographed
        Sparks' "The copy gains haste" - is carried on `granted_ability_texts`
        (kept across this one move, `CardState.move_to`); the layer system
        reads a permanent's abilities off the computed board (CR 613.1f), so
        each combat keyword there is granted in layer 6 to this incarnation of
        the permanent, indefinitely (CR 611.2a's default when no duration is
        printed). Triggered lines need nothing here: `triggered_abilities_on`
        already reads `granted_ability_texts`."""
        if permanent.zone is not Zone.BATTLEFIELD:
            return
        keywords = [
            line for line in permanent.granted_ability_texts if line.lower() in _COMBAT_KEYWORDS
        ]
        if not keywords:
            return
        store = self.continuous_effects
        for line in keywords:
            store.add(
                ContinuousEffect(
                    description=f"{permanent.name}: gained {line} as a spell (CR 400.7a)",
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                    modification=grant_ability(line),
                )
            )

    def create_emblem(
        self: "Game", owner: str, text: str, source_name: str, *, name: str | None = None
    ) -> CardState:
        """Put an emblem with `text`'s abilities into the command zone (CR
        114.2): "[Player] gets an emblem with [ability]" - owned and controlled
        by that player. CR 114.3: it has no characteristics but those
        abilities, so its object carries only them (`Layout.EMBLEM`, no types,
        no cost, no colour); its name is a label, "<source> emblem", unless a
        rule names the emblem itself (`name` - CR 701.54c's "an emblem named
        The Ring"). CR 114.4: its abilities function in the command zone - see
        `emit` and `machines/triggers.zones_ability_functions_in`."""
        with self._id_allocator_scope():
            card = _emblem_card(name or f"{source_name} emblem", text)
            emblem = CardState(card=card, zone=Zone.COMMAND, controller=owner, owner=owner)
            emblem.bind_to_game(self)
            self.shared_zones[Zone.COMMAND].append(emblem)
            return emblem

    def emblems_of(self: "Game", username: str) -> list[CardState]:
        """The emblems `username` controls (CR 114.2)."""
        return [
            state
            for state in self.shared_zones[Zone.COMMAND]
            if isinstance(state, CardState)
            and state.card.layout is Layout.EMBLEM
            and state.controller == username
        ]

    def ring_emblem_of(self: "Game", username: str) -> CardState | None:
        """`username`'s emblem named The Ring (CR 701.54c), or `None` before
        the Ring has ever tempted them."""
        return next(
            (emblem for emblem in self.emblems_of(username) if emblem.name == RING_EMBLEM_NAME),
            None,
        )

    def ring_bearer_of(self: "Game", username: str) -> CardState | None:
        """`username`'s Ring-bearer, or `None` (CR 701.54e): true only of a
        creature "on the battlefield under your control" that has the
        designation. The designation belongs to one object (CR 400.7, the
        stamp) and ends for good once another player gains control of it (CR
        701.54a, `drop_ring_bearers_controlled_by_others`)."""
        player = self.player(username)
        if player.ring_bearer_id is None:
            return None
        found = self.find_by_id(player.ring_bearer_id)
        if not isinstance(found, CardState) or found.zone is not Zone.BATTLEFIELD:
            return None
        if found.zone_change_stamp != player.ring_bearer_stamp:
            return None
        if self.controller_of(found).username != username:
            return None
        return found

    def ring_bearer_designations(self: "Game") -> dict[str, tuple[UUID, UUID]]:
        """Every player's live Ring-bearer designation, as `(id, stamp)` -
        what `machines/layers.LayerContext.ring_bearers` carries to the layer
        engine. Deliberately not `ring_bearer_of`: that asks for control,
        which is the computed board this feeds, so it would recurse. Control
        is enforced where it changes instead
        (`drop_ring_bearers_controlled_by_others`)."""
        return {
            player.username: (player.ring_bearer_id, player.ring_bearer_stamp)
            for player in self.players
            if player.ring_bearer_id is not None and player.ring_bearer_stamp is not None
        }

    def drop_ring_bearers_controlled_by_others(self: "Game") -> None:
        """CR 701.54a: a creature is its player's Ring-bearer "until another
        creature becomes your Ring-bearer or another player gains control of
        it". Called whenever a layer 2 control effect is stored (`machines/
        layers.ContinuousEffects._note_control_change`), the only way control
        of a permanent changes after it enters in this engine: a Ring-bearer
        now controlled by someone else loses the designation, and does not get
        it back when control returns."""
        for player in self.players:
            if player.ring_bearer_id is None:
                continue
            found = self.find_by_id(player.ring_bearer_id)
            if (
                isinstance(found, CardState)
                and found.zone is Zone.BATTLEFIELD
                and self.controller_of(found).username != player.username
            ):
                player.ring_bearer_id = None
                player.ring_bearer_stamp = None

    def ring_tempts(
        self: "Game", username: str, *, source_name: str, source_id: str | None = None
    ) -> CardState | None:
        """CR 701.54a-d: the Ring tempts `username`. Returns the creature
        chosen as their Ring-bearer, or `None` when they control none.

        In the rule's own order: the emblem named The Ring first, if they have
        none (CR 701.54c: "before choosing a creature"); then the choice of a
        creature they control (CR 608.2d, asked only when there is more than
        one to choose between); then the count, which rises whether or not
        anything could be chosen (CR 701.54d); then the emblem's abilities for
        that count (CR 701.54c); then the event a "Whenever the Ring tempts
        you" ability watches (CR 701.54d)."""
        player = self.player(username)
        emblem = self.ring_emblem_of(username)
        if emblem is None:
            emblem = self.create_emblem(
                username, ring_emblem_text(1), source_name, name=RING_EMBLEM_NAME
            )
        creatures = [
            permanent
            for permanent in self.permanents_controlled_by(username)
            if self.characteristics_of(permanent).is_creature
        ]
        chosen: CardState | None = None
        if len(creatures) == 1:
            chosen = creatures[0]
        elif creatures:
            answer = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=username,
                    prompt="choose a creature you control to be your Ring-bearer",
                    source=source_name,
                    amount=1,
                    cards=tuple(creature.id for creature in creatures),
                    source_id=source_id,
                )
            )
            assert isinstance(answer, tuple)
            chosen = next(creature for creature in creatures if creature.id == answer[0])
        if chosen is not None:
            player.ring_bearer_id = chosen.id
            player.ring_bearer_stamp = chosen.zone_change_stamp
        player.ring_tempted_count += 1
        text = ring_emblem_text(player.ring_tempted_count)
        if emblem.card.oracle_text != text:
            # A new printing for the emblem's new abilities, not an edit of the
            # old one: a card's parsed abilities are memoised on `Card.id`
            # (`machines/abilities.parse_abilities`), and `_emblem_card`'s id is
            # a pure function of the text, so the same level always reads the
            # same way and a replay mints the same card.
            emblem.card = _emblem_card(RING_EMBLEM_NAME, text)
        self.emit(
            GameEvent(
                event=ExtraTriggerEvent.RING_TEMPTS_YOU,
                player=username,
                subject_id=chosen.id if chosen is not None else None,
                subject_name=chosen.name if chosen is not None else None,
                subject_controller=username if chosen is not None else None,
                amount=player.ring_tempted_count,
            )
        )
        return chosen

    def _grant_dash_haste(self: "Game", permanent: CardState) -> None:
        """The third of CR 702.109a's three abilities: haste for a dashed permanent.

        "Dash represents three abilities: two static abilities that function
        while the card with dash is on the stack, one of which may create a
        delayed triggered ability, and a static ability that functions while
        the card with dash is on the battlefield" - the battlefield one is the
        haste grant, and it holds for as long as the dash cost was paid, which
        is for as long as this object is this object.

        No new fact is needed to know that: `Game.cast_records` survives a
        permanent spell's resolution (the record is deliberately not popped in
        `resolve_top`'s permanent branch), so `was_cast_with(spell, "Dash")` -
        which the delayed return-to-hand trigger beside this already asks - is
        the whole condition.

        Granting an ability is layer 6 (CR 613.1f: "Layer 6: Ability-adding
        effects, keyword counters, ability-removing effects, and effects that
        say an object can't have an ability are applied"), and haste is a
        static ability (CR 702.10a), so this is a plain `Layer.ABILITY`
        continuous effect - built the same way `machines/casting.
        grant_suspend_haste` builds suspend's, with its own description rather
        than through that function, since the description names the rule it
        comes from and this one is CR 702.109a's, not CR 702.62a's.

        `only_this_incarnation` scopes it to the exact object that just entered
        (CR 400.7 makes a permanent that leaves and returns a new object), so a
        Ragavan bounced by dash's own end-step trigger and recast for its mana
        cost does not inherit haste from the turn it was dashed.
        """
        store = self.continuous_effects
        store.add(
            ContinuousEffect(
                description=f"{permanent.name}: dash grants haste (CR 702.109a)",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                modification=grant_ability("Haste"),
            ),
            self,
        )

    def controls_split_second_grant(self: "Game", controller: str) -> bool:
        """Samut, Tyrant of Naktamun's "Instant and sorcery spells you
        control have split second." - whether `controller` has a permanent
        on the battlefield granting it right now (CR 613.5).

        CR 702.61a's split second is a property of a spell on the stack, not
        of a battlefield permanent, so nothing in `machines/layers.py`'s
        board ever carries it directly - `SPELLS_HAVE_SPLIT_SECOND_TEXT` is
        the fixed marker that grant leaves on its own source, and this is
        the one place that asks for it. A caller checking whether a
        particular instant or sorcery *spell* has split second combines this
        (does its controller have the grant) with the spell's own card type
        - this function alone answers only "is the group grant active for
        this player", the same way `has_ability`/`has_keyword` never assume
        who the caller means by "it".
        """
        board = self.computed_board()
        return any(
            board.of(permanent).controller == controller
            and board.of(permanent).has_ability(SPELLS_HAVE_SPLIT_SECOND_TEXT)
            for permanent in self.battlefield
        )

    def add_counters(
        self: "Game",
        permanent: CardState,
        kind: str,
        amount: int = 1,
        *,
        putter: str | None = None,
        modular: bool = False,
    ) -> int:
        """Put counters on a permanent, replacement effects included (CR 122.1).

        CR 122.6: "Some spells and abilities refer to counters being put on an
        object. This refers to putting counters on that object while it's on the
        battlefield and also to an object that's given counters as it enters the
        battlefield" - so both routes reach the same replaceable event, which is
        what lets Doubling Season double a Kalonian Hydra's four printed counters
        as it arrives.

        `putter` is who puts them; unnamed, `_counter_putter` answers it.

        CR 101.2: a "can't" effect takes precedence over the rule or effect
        that would otherwise apply, and CR 614.17a says such an effect must
        already exist before the event it blocks - checked here, ahead of
        replacement effects, so a permanent an effect says "can't have
        counters put on it" (`CardState.cant_have_counters_put_on_it`) simply
        never receives any, on the battlefield or as it enters (CR 122.6):
        no event, no replacement to apply, no counter. This is the one place
        every route to putting counters on a permanent already passes
        through - `proliferate`, every `AddCounters`/`_counter_gain` effect
        - so gating it here covers all of them at once.
        """
        with self._id_allocator_scope():
            if amount <= 0:
                return permanent.counter_count(kind)
            if permanent.cant_have_counters_put_on_it:
                return permanent.counter_count(kind)
            # Melira, Sylvok Outcast: "Creatures you control can't have -1/-1
            # counters put on them." and Blightbeetle's opponents' twin (CR 101.2,
            # `machines/game_rule_statics.py`).
            if game_rule_statics.permanent_counter_prohibited(self, permanent, kind) is not None:
                return permanent.counter_count(kind)

            event = ReplaceableEvent(
                kind=EventKind.ADD_COUNTERS,
                card=permanent,
                counter_kind=kind,
                amount=amount,
                putter=putter or self._counter_putter(permanent.controller),
                modular=modular,
            )
            apply_replacements(self, event)
            if event.amount <= 0:
                return permanent.counter_count(kind)
            new_total = permanent.add_counters(kind, event.amount)
            if str(kind) == str(Counter.LORE):
                self._emit_lore_counters_added(permanent, event.amount)
            self._emit_counters_put(permanent, str(kind), event.amount, putter=event.putter)
            return new_total

    def stamp_keyword_counter(self: "Game", permanent: CardState, kind: str) -> None:
        """CR 613.7c's timestamp for a keyword counter (CR 122.1b) just put on
        `permanent` - `CardState.add_counters` calls this for every kind, and
        only the keyword kinds are kept (`ContinuousEffects.
        keyword_counter_grants` orders them in layer 6, CR 613.1f)."""
        from ...machines.keyword_counters import KEYWORD_COUNTER_KEYWORDS

        if kind.lower() in KEYWORD_COUNTER_KEYWORDS:
            self.continuous_effects.stamp_keyword_counter(permanent.id, kind.lower())

    def proliferate(
        self: "Game", chosen: Sequence[CardState], chosen_players: Sequence["Player | str"] = ()
    ) -> None:
        """CR 701.34a: "choose any number of permanents and/or players that
        have a counter, then give each one additional counter of each kind
        that permanent or player already has." Both `chosen` (permanents)
        and `chosen_players` are the controller's own choice (CR 608.2d -
        `_parse_proliferate_clause`, `machines/effects.py`, asks a
        `CHOOSE_CARDS` question over every permanent on the battlefield
        carrying at least one counter, and a `CHOOSE_PLAYERS` question over
        every player carrying at least one counter of their own, `exact=
        False` on both so "any number" including zero is legal on each).

        One CR 608.2c instruction, still: the permanent and player choices
        are asked as two separate `Game.ask` questions rather than one
        combined one (`DecisionKind` has no vocabulary for a single mixed
        card-or-player answer), but nothing about the *result* - who ends up
        with what extra counters - depends on which order the two questions
        were asked in, so this reads identically to CR 701.34a's own single
        sentence.
        """
        with self._id_allocator_scope():
            for permanent in chosen:
                if permanent.zone is not Zone.BATTLEFIELD:
                    continue
                for kind, count in list(permanent.counters.counts.items()):
                    if count > 0:
                        self.add_counters(permanent, kind, 1)
            for player_or_username in chosen_players:
                player = (
                    player_or_username
                    if isinstance(player_or_username, Player)
                    else self.player(player_or_username)
                )
                for kind, count in list(player.counters.counts.items()):
                    if count > 0:
                        self.add_player_counters(player, kind, 1)

    def player_counters_prohibited(
        self: "Game", username: str, kind: str | None = None
    ) -> str | None:
        """Why `username` can't get counters right now, or None - Solemnity's
        "Players can't get counters." on the battlefield, or Suncleanser's
        recorded "That player can't get counters for as long as this creature
        remains on the battlefield." (CR 101.2: a "can't" beats whatever would
        put them; CR 614.17a: it must already exist). Rescanned every call,
        as `life_gain_prohibited` is (CR 611.3a)."""
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                own_kind = _OWN_KIND_COUNTERS_PROHIBITION_RE.match(text)
                if own_kind is not None:
                    if (
                        kind is not None
                        and source.controller == username
                        and own_kind["kind"].lower() == str(kind).lower()
                        and self._still_has_static_line(source, text)
                    ):
                        return (
                            f"{username} can't get {kind} counters: "
                            f"{source.name} says so (CR 101.2)"
                        )
                    continue
                if not _PLAYER_COUNTERS_PROHIBITION_RE.match(text):
                    continue
                if self._still_has_static_line(source, text):
                    return f"players can't get counters: {source.name} says so (CR 101.2)"
        for effect in self.casting_rule_effects:
            if (
                effect.kind != CastingRuleKind.PLAYER_CANT_GET_COUNTERS
                or effect.restricted_player != username
            ):
                continue
            source = (
                self.find_by_id(effect.while_source_id)
                if effect.while_source_id is not None
                else None
            )
            if (
                source is not None
                and source.zone is Zone.BATTLEFIELD
                and source.zone_change_stamp == effect.while_source_stamp
            ):
                return (
                    f"{username} can't get counters while {effect.source_name} remains (CR 611.2b)"
                )
        return None

    def add_player_counters(
        self: "Game", player: "Player | str", kind: str, amount: int = 1
    ) -> int:
        """Give a player counters, replacement effects included (CR 122.1,
        122.6).

        The player twin of `add_counters` above: Winding Constrictor's own
        two-line static ability doubles+1 both halves of CR 122.6's "counters
        being put on an object" - "an artifact or creature you control" and
        "you [get counters]", CR 122.1's "some kinds of counters are normally
        placed on players rather than on objects" (poison, energy, experience
        chief among them). Before this, `Player.add_counters` was called
        directly with no `ReplaceableEvent` in between, so a replacement
        effect written "If you would get one or more counters, ..." had
        nothing to apply to and silently never ran.
        """
        with self._id_allocator_scope():
            if isinstance(player, str):
                player = self.player(player)
            if amount <= 0 or self.player_counters_prohibited(player.username, kind) is not None:
                return player.counter_count(kind)
            # "You can't get poison counters." (Melira, Sylvok Outcast; CR 101.2).
            if game_rule_statics.player_counter_prohibited(self, player.username, kind):
                return player.counter_count(kind)

            event = ReplaceableEvent(
                kind=EventKind.ADD_COUNTERS,
                player=player,
                counter_kind=kind,
                amount=amount,
                putter=self._counter_putter(player.username),
            )
            apply_replacements(self, event)
            if event.amount <= 0:
                return player.counter_count(kind)
            new_total = player.add_counters(kind, event.amount)
            self._emit_player_counters_put(player, str(kind), event.amount)
            return new_total

    def _counter_putter(self: "Game", fallback: str | None) -> str | None:
        """Who is putting counters right now: the controller of the resolving
        spell or ability, which follows its instructions (CR 608.2c). Outside
        a resolution (a cost, a turn-based action) `fallback` - the recipient's
        controller, CR 122.6a's default."""
        if self.resolving is not None and self.resolving.controller:
            return self.resolving.controller
        return fallback

    def _player_static_keyword_grants(self: "Game", player: Player) -> list[tuple[str, list[str]]]:
        """Every "You have hexproof." / "You have shroud." (and "hexproof from
        [quality]") line on a permanent `player` controls, read fresh off the
        computed board each time so the grant ends with its permanent (CR
        604.2) and an ability an effect removed grants nothing (CR 613.1f) -
        the same fresh read `player_protection_qualities` makes for Runed Halo.

        Also Captain America, Super-Soldier's own "As long as ... has a
        shield counter ..., you and other Heroes you control have
        hexproof." - `machines/casting.py::player_keyword_grant_of_line`
        (owned by a different task this round) only reads the bare "You have
        `<keyword>`." shape, so `conditional_group_keyword_grant_of_line`
        (`machines/keyword_counters.py`) is tried on the same lines as a
        fallback, and the *player* half of its compound grant is what lands
        here; the *creature* half is `_supplement_characteristics`'s own
        business, on the other side of the identical condition check.
        """
        grants: list[tuple[str, list[str]]] = []
        board = self.computed_board()
        for permanent in self.battlefield:
            if self.controller_of(permanent).username != player.username:
                continue
            try:
                lines = board.of(permanent).abilities
            except KeyError:
                lines = tuple(permanent.oracle_text.splitlines())
            for line in lines:
                grant = player_keyword_grant_of_line(line)
                if grant is not None:
                    grants.append(grant)
                    continue
                conditional = conditional_group_keyword_grant_of_line(line)
                if conditional is not None and permanent.counters[conditional[0]] > 0:
                    grants.append((conditional[2], []))
            # "You and Humans you control have hexproof." and the other static
            # group grants whose subject names the player (CR 702.11c).
            grants.extend(player_keyword_grants(self, permanent, board, player.username))
        return grants

    def grant_player_hexproof(
        self: "Game",
        username: str,
        qualities: Sequence[str] = (),
        *,
        duration: Duration,
        source_name: str,
    ) -> None:
        """Give a player hexproof (CR 702.11c), or hexproof from each of
        `qualities` (CR 702.11d, one ability per quality per CR 702.11f), for
        `duration` (CR 611.2a).

        The call a resolving "you gain hexproof [from ...] until ..." clause
        makes. `Duration.UNTIL_END_OF_TURN` ends in `cleanup_step` (CR 514.2);
        `Duration.UNTIL_YOUR_NEXT_TURN` ends as `username`'s next turn begins
        (`begin_turn_for`) - "your" is the grant's own controller, the player
        receiving it.
        """
        self._grant_player_keyword(
            username,
            [("hexproof", quality) for quality in qualities] or [("hexproof", None)],
            duration=duration,
            source_name=source_name,
        )

    def grant_player_shroud(
        self: "Game", username: str, *, duration: Duration, source_name: str
    ) -> None:
        """Give a player shroud (CR 702.18a's "or player") for `duration`."""
        self._grant_player_keyword(
            username, [("shroud", None)], duration=duration, source_name=source_name
        )

    def _grant_player_keyword(
        self: "Game",
        username: str,
        grants: Sequence[tuple[Literal["hexproof", "shroud"], str | None]],
        *,
        duration: Duration,
        source_name: str,
    ) -> None:
        if duration not in (Duration.UNTIL_END_OF_TURN, Duration.UNTIL_YOUR_NEXT_TURN):
            raise ValueError(
                f"a player grant lasts until end of turn or until your next turn, not {duration}"
            )
        player = self.player(username)
        for keyword, quality in grants:
            player.targeting_grants.append(
                PlayerTargetingGrant(
                    keyword=keyword,
                    quality=quality,
                    duration=duration,
                    until_next_turn_of=(
                        username if duration is Duration.UNTIL_YOUR_NEXT_TURN else None
                    ),
                    source_name=source_name,
                )
            )

    # -- what the board actually is (CR 613.5) -----------------------------

    def computed_board(self: "Game") -> ComputedBoard:
        """Every permanent's characteristics with every continuous effect applied.

        CR 613.5: "The application of continuous effects as described by the
        layer system is continually and automatically performed by the game. All
        resulting changes to an object's characteristics are instantaneous."
        Recomputed on every call rather than cached, because that is what
        "continually" means: an anthem that left the battlefield a moment ago is
        already not applying.

        `CardState.power` and `.toughness` are the *printed* values plus counters
        (CR 122.1a) and know nothing about layers, so anything in this file that
        needs a real power or toughness asks here instead.

        A `LayerContext` of every graveyard goes with the battlefield, because a
        characteristic-defining ability can be printed on the card it affects
        while counting something the layer engine never sees on its own -
        Tarmogoyf's power (CR 604.3, CR 604.3a, CR 613.4a) counts card types
        "among cards in all graveyards" (CR 300.1), and Boneyard Wurm's counts
        creature cards in its own controller's graveyard only. Without this,
        every such CDA is built against an empty world and reads as if every
        graveyard were empty, whatever is actually in them.

        Inside `board_snapshot()` the board is computed once and reused until
        the game changes; outside every scope it is recomputed on every call,
        exactly as described above.
        """
        return cached_board(self, self._compute_board)

    def board_snapshot(self: "Game") -> AbstractContextManager[None]:
        """A scope in which `computed_board` is computed once and reused.

        For read-only work that asks the board many times - enumerating legal
        actions, serialising every card's characteristics - so the board is
        built once rather than once per question. Any change to the game made
        inside the scope drops the cached board or, when the engine could not
        see the change happen, raises `snapshot.BoardSnapshotStale`; nested
        scopes share one board. The full contract is `magic_cards_model/
        snapshot.py`'s module docstring.
        """
        return board_snapshot(self)

    def base_power_toughness_board(self: "Game") -> ComputedBoard:
        """The board as CR 208.4b's "base power and toughness" sees it: every
        continuous effect applied except sublayers 7c and 7d, and no counters -
        Baird, Argivian Recruiter's "a creature with power greater than its
        base power". Computed afresh on every call, never cached."""
        return self._compute_board(base_power_toughness=True)

    def _compute_board(self: "Game", *, base_power_toughness: bool = False) -> ComputedBoard:
        """`computed_board`, always computed afresh."""
        self.continuous_effects.note(self.battlefield)
        context = self._layer_context()
        # The effects a board is built from are rebuilt on every computation and
        # discarded with it, so they must not draw on `_allocate_id`: how often a
        # command computes the board (which a snapshot scope, or another
        # thread's change moving its epoch, decides) would otherwise move
        # `objects_created` and every id minted after it, and a replayed command
        # would stop minting the ids it minted the first time. Each computation
        # numbers its own effects from zero instead, the same way every time.
        minted = itertools.count()

        def board_effect_id() -> UUID:
            return uuid5(NAMESPACE_OID, f"{self.game_uid}:board:{next(minted)}")

        token = install_id_allocator(board_effect_id)
        try:
            return self.continuous_effects.board(
                self.battlefield, context, self, base_power_toughness=base_power_toughness
            )
        finally:
            reset_id_allocator(token)

    def _layer_context(self: "Game") -> LayerContext:
        """The transient `LayerContext` every board computation reads: what the
        layer engine cannot see standing on the battlefield (graveyards, exile,
        life totals, turn facts, ...)."""
        return LayerContext(
            face_down_creatures=sum(1 for permanent in self.battlefield if permanent.face_down),
            hand_size_by_controller={
                player.username: len(player.hand) for player in self.players_in_game
            },
            life_by_controller={player.username: player.life for player in self.players_in_game},
            graveyards=tuple(card for player in self.players_in_game for card in player.graveyard),
            graveyard_by_controller={
                player.username: tuple(player.graveyard) for player in self.players_in_game
            },
            # And the mana pools go with them, for the same reason: Omnath,
            # Locus of Mana's "Omnath gets +1/+1 for each unspent green mana
            # you have" counts something the layer engine cannot see standing
            # on the battlefield either.
            unspent_mana_by_controller={
                player.username: dict(self.unspent_mana_of(player).floating)
                for player in self.players_in_game
            },
            active_player=self.turn.active_player if self.turn is not None else None,
            current_step=self.turn.step.value if self.turn is not None else None,
            turn_facts={
                **{fact: frozenset(players) for fact, players in self.turn_facts.items()},
                # CR 119.3's life lost this turn (Essence Channeler's "as long
                # as you've lost life this turn"), off the per-turn tally
                # `Player.life_lost_this_turn` spectacle already reads.
                LOST_LIFE_TURN_FACT: frozenset(
                    player.username
                    for player in self.players_in_game
                    if player.life_lost_this_turn > 0
                ),
            },
            # Infusion's own turn-history fact (CR 207.2c's ability word),
            # for a static "as long as you gained life this turn" gate
            # (`LayerContext.gained_life_this_turn`) - `Game.life_gained_
            # this_turn` is the same set `machines/conditions/history.py`'s
            # H4 reader and `machines/triggers.py`'s own intervening-if
            # branch already read for every other "gained life this turn"
            # question; a static ability asks a `LayerContext` rather than a
            # live `Game` (CR 611.3a: recomputed on every board query), so
            # the fact travels here the identical way `turn_facts` already
            # does for its own family of per-turn questions.
            life_gained_this_turn=frozenset(self.life_gained_this_turn),
            combat_damage_dealt_this_turn=frozenset(self.combat_damage_dealt_this_turn_by),
            # CR 122.6's per-turn placement history (Beast, Erudite
            # Aerialist; Kid Loki), who put what kind on which permanent.
            counters_put_this_turn=tuple(
                (record.putter, record.card_id, record.kind, record.zone_change_stamp)
                for record in self.counters_put_this_turn
            ),
            # CR 607.2a: Keen-Eyed Curator's "card types among cards exiled
            # with this creature" counts a pile in the shared exile zone.
            exile=tuple(self.exile),
            # CR 701.54c: The Ring's static ability applies to its
            # controller's Ring-bearer, a designation the layer engine cannot
            # see on the battlefield either.
            ring_bearers=self.ring_bearer_designations(),
            # CR 119.1's life totals and CR 700.5's devotion: Serra Ascendant's
            # "you have 30 or more life" and a Theros god's "your devotion to
            # ..." read their controller's, neither of which stands on the
            # battlefield as a characteristic the layer engine could see.
            life_by_player={player.username: player.life for player in self.players_in_game},
            counters_by_player={
                player.username: dict(player.counters.counts) for player in self.players_in_game
            },
            starting_life_by_player={
                player.username: player.starting_life for player in self.players_in_game
            },
            # CR 402.2: Ms. Marvel, Kamala Khan's own granted "'s base power
            # is equal to the number of cards in your hand." reads a hand
            # size, which no more stands on the battlefield as a
            # characteristic than a life total does.
            hand_size_by_player={
                player.username: len(player.hand) for player in self.players_in_game
            },
            # CR 702.143a: Alrund, God of the Cosmos' "each foretold card you own
            # in exile" - a shared zone's cards, counted per owner.
            foretold_in_exile_by_player=self._foretold_in_exile_counts(),
            # CR 709.5c: the unlocked doors of the Rooms a player controls.
            unlocked_doors_by_player=self._unlocked_door_counts(),
            # CR 401.1: Living Conundrum's "As long as there are no cards in
            # your library" reads a library size, no more a characteristic
            # than a hand size is.
            library_size_by_player={
                player.username: len(player.library) for player in self.players_in_game
            },
            cards_drawn_this_turn=dict(self.cards_drawn_this_turn),
            top_card_by_player={
                player.username: player.library[0]
                for player in self.players_in_game
                if player.library
            },
            # CR 702.195b's enduring story, which "As long as you have an
            # enduring story, ..." statics read off their controller.
            enduring_story_players=frozenset(
                player.username for player in self.players_in_game if player.has_enduring_story
            ),
            mana_cost_by_id={
                permanent.id: permanent.mana_cost
                for permanent in self.battlefield
                if permanent.mana_cost
            },
            # CR 508.1k: "Attacking tokens you control have flying" reads who
            # is attacking, which is combat state, not a characteristic.
            attacking=frozenset(self.combat.attacker_ids),
            # CR 509.1g's blocking status, the twin of the line above
            # (Tromokratis' "hexproof unless it's attacking or blocking").
            blocking=frozenset(self.combat.blocker_ids),
            # CR 702.131c's designation: "As long as you have the city's
            # blessing, ..." (Slippery Scoundrel).
            citys_blessing_players=frozenset(
                player.username for player in self.players_in_game if player.has_citys_blessing
            ),
            # CR 110.5: "Other tapped creatures you control have
            # indestructible." (Adept Watershaper) reads tapped status,
            # which is a permanent's physical state, not a characteristic.
            tapped_ids=frozenset(
                permanent.id for permanent in self.battlefield if permanent.tapped
            ),
            # `Game.turn_counts`, carried the same way `turn_facts` already
            # is - Kinbinding's own "the number of creatures that entered the
            # battlefield under your control this turn."
            turn_counts={fact: dict(players) for fact, players in self.turn_counts.items()},
            creatures_died_under_control=self._creatures_died_under_control_this_turn(),
            # Bristlebane Outrider's own "another creature entered ... this
            # turn" - see `LayerContext.entered_this_turn_ids`'s own docstring
            # for why this needs the object identity, not just the count.
            entered_this_turn_ids=frozenset(
                permanent.id
                for permanent in self.battlefield
                if self.turn is not None and permanent.turn_entered == self.turn.turns_taken
            ),
        )

    def characteristics_of(self: "Game", permanent: CardState) -> Characteristics:
        """This permanent's characteristics right now, layers included (CR 613.5).

        CR 613's whole layer system is about the battlefield - "the game
        applies each applicable effect in a series of layers" governs what
        that object *currently is*, a question only a permanent has - so an
        object anywhere else (a graveyard-zone CR 113.6m ability's own
        source, an exiled card, one still in a library or hand) falls back
        to `off_battlefield_characteristics_of` - `printed_characteristics`,
        the same layer-1 starting point every computed board itself begins
        from, with no continuous effect able to reach it there to begin with
        (CR 611.1, 613.1a: an effect that could apply "as long as" or "for as
        long as" a permanent condition holds needs a permanent to hold it),
        plus the one ability that functions *only* off the battlefield, CR
        113.6c's "as long as this isn't on the battlefield" grant. Grim Repriser's and Proctor of
        Potential's own graveyard-zone activation is what first needed this:
        `CostPayment.for_total`'s own `ManaSpend.activating` call asks for
        this unconditionally, for every activation, not only a battlefield
        one.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            # CR 113.6c: plus an "as long as this isn't on the battlefield"
            # grant, which applies exactly here (Grist, the Hunger Tide).
            return self._with_defined_power_toughness(
                permanent,
                apply_zone_characteristics(
                    self, permanent, off_battlefield_characteristics_of(permanent)
                ),
            )
        board = self.computed_board()
        return self._supplement_characteristics(permanent, board.of(permanent), board)

    def _with_defined_power_toughness(
        self: "Game", card: CardState, chars: Characteristics
    ) -> Characteristics:
        """CR 604.3: a characteristic-defining ability "functions in all
        zones", so a creature card in a hand, graveyard, library or exile whose
        printed power or toughness is `*` has the value its CDA defines (CR
        208.2a) - Tarmogoyf in the graveyard is not a blank-boxed card. Only
        the characteristic-defining effects of the card's own text are applied
        (sublayer 7a, CR 613.4a); nothing else reaches an object off the
        battlefield (CR 611.1)."""
        if Type.CREATURE not in chars.types or (
            chars.power is not None and chars.toughness is not None
        ):
            return chars
        owner = card.owner or card.controller
        source = card.model_copy(update={"controller": owner})
        defining = [
            effect
            for effect in effects_for(source, 0, (), self._layer_context(), [], static_only=True)
            if effect.characteristic_defining and effect.layer is Layer.POWER_TOUGHNESS
        ]
        if not defining:
            return chars
        defined = compute_board([source], defining).of(source)
        return chars.model_copy(
            update={
                "power": chars.power if chars.power is not None else defined.power,
                "toughness": chars.toughness if chars.toughness is not None else defined.toughness,
            }
        )

    def _supplement_characteristics(
        self: "Game", permanent: CardState, chars: Characteristics, board: ComputedBoard
    ) -> Characteristics:
        """What `characteristics_of` adds on top of `computed_board`'s own
        answer - three gaps `machines/layers.py` (owned by a different task
        this round, so not a file this task may edit) leaves, closed here
        additively instead, on top of what it already computed:

        - (CR 122.1b's indestructible/hexproof keyword counters used to be
          added here, after every layer; they are now layer 6 grants at
          their own CR 613.7c timestamps - `ContinuousEffects.
          keyword_counter_grants` - so a later "loses all abilities" can
          take them away, CR 613.1f.)
        - **CR 702.186b's own harness gate** ("As long as this permanent is
          harnessed, it has [Ability]") - an Infinity permanent's "∞ —
          [Ability]" line (parsed as an ordinary triggered ability now that
          `machines/abilities.py::_ABILITY_WORD` reads the ∞ keyword) is
          present in `chars.abilities` only while `is_harnessed` says so;
          removed otherwise. `machines/triggers.py::triggered_abilities_on`
          already reads a printed line's absence from the computed board as
          CR 613.1f removal (`rewritten_ability_lines`), which is exactly
          what CR 702.186b's own "as long as" wording means - so gating the
          line here is enough to gate the trigger itself, with nothing to
          change in `machines/triggers.py`.
        - **A CDA whose qualifier `machines/layers.py::_QUALIFIER_COUNT_CDA_
          RE` cannot read** - that reader's `qualifier` group is a single
          bare word, so Super-Adaptoid's own "Super-Adaptoid's power is
          equal to the number of legendary creatures you control" (CR
          604.3a) leaves `chars.power` undefined (`None`) rather than
          computed. Supplemented only when `chars.power` is still `None` -
          never overriding a value `_QUALIFIER_COUNT_CDA_RE` or any other
          layer-7a reader already supplied - and only for the self-
          referential "this permanent's/`<name>`'s power is equal to the
          number of legendary `<type>` you control" shape, read generally
          off the printed text rather than keyed to Super-Adaptoid's own
          name.
        - **The creature half of a conditional group grant `machines/
          layers.py` has no reader for** - Captain America, Super-Soldier's
          own "As long as Captain America has a shield counter on him, you
          and other Heroes you control have hexproof.": every *other*
          permanent with the named subtype, controlled by the granting
          permanent's own controller, gets the keyword while the condition
          holds. The player half of the identical grant is
          `_player_static_keyword_grants`'s own business; see that method's
          docstring for why both live in this file rather than in `machines/
          casting.py`/`machines/layers.py`.
        """
        abilities = chars.abilities
        infinity_lines = [
            stripped
            for raw in (permanent.oracle_text or "").splitlines()
            if (stripped := raw.strip()).startswith("∞")
        ]
        if infinity_lines:
            harnessed = self.is_harnessed(permanent)
            for line in infinity_lines:
                present = line in abilities
                if harnessed and not present:
                    abilities = abilities + (line,)
                elif not harnessed and present:
                    abilities = tuple(entry for entry in abilities if entry != line)
        for keyword_text in self._group_keyword_grants_for(permanent, chars, board):
            if keyword_text not in abilities:
                abilities = abilities + (keyword_text,)
        if abilities != chars.abilities:
            chars = chars.with_(abilities=abilities)
        if chars.power is None:
            legendary_count = self._legendary_creature_count_power(permanent, board)
            if legendary_count is not None:
                chars = chars.with_(power=legendary_count)
        return chars

    def _group_keyword_grants_for(
        self: "Game", permanent: CardState, chars: Characteristics, board: ComputedBoard
    ) -> tuple[str, ...]:
        """`_supplement_characteristics`'s own creature-half reader for a
        conditional group grant (`conditional_group_keyword_grant_of_line`) -
        see that method's own docstring. `subtype` is matched against
        `chars.subtypes` both as printed ("Heroes") and singularised
        ("Hero"), since `CardState.subtypes` stores the singular form
        (Scryfall's own type-line spelling) while the grant's own sentence
        names the plural; "other" excludes the granting permanent itself.
        """
        granted: list[str] = []
        # Controllers off the computed board, never `CardState.controller`:
        # under a control-changing effect that property asks
        # `characteristics_of`, which calls back into this method for every
        # other permanent - a mutual recursion across the whole battlefield.
        # `board` is the one `characteristics_of` already computed.
        controller = chars.controller
        for source in self.battlefield:
            if board.of(source).controller != controller or source.id == permanent.id:
                continue
            for line in (source.oracle_text or "").splitlines():
                conditional = conditional_group_keyword_grant_of_line(line)
                if conditional is None:
                    continue
                counter_kind, subtype, keyword = conditional
                if source.counters[counter_kind] <= 0:
                    continue
                # CR 205.3's own subtypes have no fixed pluralisation rule
                # ("Hero"/"Heroes" adds "-es"; most others just add "-s"),
                # so every plausible singular is tried rather than one
                # guessed shape - "Heroes" stripped of a bare trailing "s"
                # gives "Heroe", which matches nothing, and would have
                # silently refused this exact grant.
                candidates = {subtype}
                if subtype.lower().endswith("es"):
                    candidates.add(subtype[:-2])
                if subtype.lower().endswith("s"):
                    candidates.add(subtype[:-1])
                if not candidates & set(chars.subtypes):
                    continue
                text = keyword.title()
                if text not in granted:
                    granted.append(text)
        return tuple(granted)

    def power_of(self: "Game", permanent: CardState) -> int | None:
        """This creature's power right now, layers included (CR 613.4, 613.5).

        `machines/combat.py` assigns combat damage equal to a creature's power
        (CR 510.1a) and reads `CardState.power` to get it, which is the printed
        value plus counters. This is the answer that counts an anthem, a
        characteristic-defining ability (CR 604.3, layer 7a), and a switch
        (CR 613.4d).
        """
        return self.characteristics_of(permanent).power

    def toughness_of(self: "Game", permanent: CardState) -> int | None:
        """This creature's toughness right now, layers included (CR 613.4, 613.5)."""
        return self.characteristics_of(permanent).toughness

    def _toughness_is_zero_or_less(self: "Game", state: CardState, board: ComputedBoard) -> bool:
        """CR 704.5f alone, against the computed toughness (CR 613.5).

        Split out because it is the only one of the three that reaches a
        permanent with indestructible: CR 704.5f puts a creature into its
        graveyard rather than destroying it, which CR 701.8b makes a different
        event, so CR 702.12b has nothing to say about it. A toughness that is not
        a number is not zero or less and is left alone, exactly as above.
        """
        try:
            toughness = board.of(state).toughness
        except KeyError:
            toughness = state.toughness
        return toughness is not None and toughness <= 0

    @classmethod
    def _static_line_without_ability_word(cls, text: str) -> str:
        match = cls._ABILITY_WORD_PREFIX_RE.match(text.strip())
        without_word = match.group("rest").strip() if match else text.strip()
        return cls._TRAILING_REMINDER_TEXT_RE.sub("", without_word).strip()

    def hand_is_revealed(self: "Game", username: str) -> bool:
        """Whether `username` controls a permanent that makes them "play with
        your hand revealed" right now (CR 701.20a: a reveal shows the cards to
        every player) - read fresh off the computed board every call, like
        `controls_look_at_top_permission`, so it ends when the permanent does."""
        board = self.computed_board()
        return hand_revealed_by_others(self, username) or any(
            self._PLAY_WITH_HAND_REVEALED_RE.fullmatch(self._static_line_without_ability_word(line))
            is not None
            for permanent in self.permanents_controlled_by(username)
            for line in board.of(permanent).abilities
        )

    def controls_look_at_top_permission(self: "Game", username: str) -> bool:
        """Whether `username` controls a permanent granting CR 611.3d's "you
        may look at the top card of your library any time" - read fresh off
        the computed board every call, so the answer tracks the grant's own
        source leaving the battlefield (`known_to`'s own purity contract)."""
        board = self.computed_board()
        return any(
            self._looks_at_top_card_any_time_line(line)
            for permanent in self.permanents_controlled_by(username)
            for line in board.of(permanent).abilities
        )

    def looks_at_opposing_face_down_creatures(self: "Game", username: str) -> bool:
        """Whether `username` controls a permanent granting Lens of Clarity's
        "... and at face-down creatures you don't control any time" (CR 708.3's
        look, extended by a rules-modifying static, CR 611.3d) - read fresh off
        the computed board every call."""
        board = self.computed_board()
        return any(
            self._LOOK_AT_TOP_AND_FACE_DOWN_ANY_TIME_RE.fullmatch(
                self._static_line_without_ability_word(line)
            )
            is not None
            for permanent in self.permanents_controlled_by(username)
            for line in board.of(permanent).abilities
        )

    def reveals_top_card(self: "Game", username: str) -> bool:
        """Whether `username` controls a permanent whose static line is
        "Play with the top card of your library revealed." (CR 400.2),
        read fresh off the computed board every call."""
        board = self.computed_board()
        return top_card_revealed_by_others(self) or any(
            self._TOP_CARD_REVEALED_RE.fullmatch(self._static_line_without_ability_word(line))
            is not None
            for permanent in self.permanents_controlled_by(username)
            for line in board.of(permanent).abilities
        )

    def has_granted_improvise(self: "Game", caster: str, spell: CardState) -> bool:
        """Whether some permanent `caster` controls grants `spell` CR
        702.126a's improvise right now via `_SPELLS_YOU_CAST_HAVE_IMPROVISE_
        RE`'s shape (CR 113.6), regardless of `spell`'s own printed
        keywords. A type qualifier ("Noncreature spells ...") is checked
        against `spell.types`; "non`<type>`" reads as that type's absence
        the same way `_named_type_matcher`'s own "non`<type>`" branch does.
        """
        if any(
            grant.keyword == "improvise"
            for grant in next_spell_keyword_grants_for(self, spell, caster)
        ):
            # "The next spell you cast this turn has improvise." (Archway of
            # Innovation) - a resolved effect's grant rather than a static.
            return True
        board = self.computed_board()
        for permanent in self.permanents_controlled_by(caster):
            for line in board.of(permanent).abilities:
                match = self._SPELLS_YOU_CAST_HAVE_IMPROVISE_RE.fullmatch(
                    self._static_line_without_ability_word(line)
                )
                if match is None:
                    continue
                type_word = match.group("type")
                if type_word is None:
                    return True
                try:
                    wanted = Type(type_word.lower())
                except ValueError:
                    continue
                if match.group("negated"):
                    if wanted not in spell.types:
                        return True
                    continue
                if wanted in spell.types:
                    return True
        return False

    def grant_extra_land_play(self: "Game", username: str, amount: int = 1) -> None:
        """CR 305.2's allowance increase for the rest of this turn only -
        Way of the Paradox's own "You may play an additional land this
        turn.", one instruction resolving once rather than a permanent's own
        ongoing static ability. Reset with `lands_played` at the start of
        each turn (`Game.begin_turn`)."""
        self.extra_land_plays[username] = self.extra_land_plays.get(username, 0) + amount

    # -- permission to play a card from somewhere else (CR 601.3) ----------

    def grant_play_permission(
        self: "Game",
        card: CardState,
        player: str,
        *,
        action: PlayAction = PlayAction.CAST,
        pays_mana_cost: bool = True,
        source_name: str = "",
        rule: str = "CR 601.3",
        zone: Zone = Zone.EXILE,
        until_end_of_turn: bool = True,
        immediate: bool = False,
        until_next_turn_of: str | None = None,
        expires_end_of_next_turn: bool = False,
        flashback: bool = False,
        any_type_mana: bool = False,
        condition: str | None = None,
        exile_instead_of_graveyard: bool = False,
        until_next_end_step_of: str | None = None,
        pays_life_for_mana_value: bool = False,
        choice_group: UUID | None = None,
        while_controlling: str | None = None,
        cost_increase: ManaCost | None = None,
    ) -> PlayPermission:
        """CR 601.3: let `player` play this one card out of `zone`, for a turn.

        The primitive behind Ugin, Eye of the Storms' "−11: ... Until end of
        turn, you may cast those cards without paying their mana costs." and
        Ragavan, Nimble Pilferer's "... Until end of turn, you may cast that
        card." Both are the same shape: a resolving ability names cards it has
        just exiled and says who may play them and for how long.

        `immediate=True` is the other shape - CR 117.2e's own "resolving...
        abilities may instruct players to take actions" grant, with no printed
        "until end of turn" - Suspend's third ability (CR 702.62a) is the one
        that uses it. See `PlayPermission.immediate`'s own docstring for why
        that needs `granted_step` rather than `until_end_of_turn`.

        The permission is stamped with the object's `zone_change_stamp`
        (CR 400.7), so it dies the moment the card moves - it cannot be
        re-earned by a card that leaves exile and returns, and it never leaks
        to a different card in the same pile.

        `player` is who may play it, which CR 108.3 leaves free to differ from
        the owner: Ragavan exiles from the damaged player's library and hands
        the permission to the Ragavan controller.

        `pays_mana_cost=False` is CR 118.9's "without paying its mana cost".
        `action=PlayAction.PLAY` is CR 601.1a's wider word, which reaches the
        land drop; `PlayAction.CAST` never does.

        `until_next_turn_of` is CR 611.2a's "until the end of your next turn"
        duration (Hex Magic) rather than a plain "until end of turn" - see
        `PlayPermission.until_next_turn_of`'s own docstring. Passing it forces
        `until_end_of_turn=False` regardless of the argument given, since the
        two durations are mutually exclusive and `Game.begin_turn_for` (not
        `Game.cleanup_step`) is what drops this one.
        `expires_end_of_next_turn=True` is Wrenn's Resolve's/Reckless
        Impulse's longer "until the end of your next turn" grant - see
        `PlayPermission.expires_end_of_next_turn`'s own docstring. A caller
        passing this should also pass `until_end_of_turn=False`, so
        `Game.cleanup_step`'s ordinary same-turn sweep leaves it alone.

        `until_next_end_step_of` is "until your next end step" (Riveteers
        Charm) - see `PlayPermission.until_next_end_step_of`. Like
        `until_next_turn_of`, passing it forces `until_end_of_turn=False`.

        `flashback=True` is CR 702.34a's grant handed out as a permission
        rather than read off a printed keyword line - Past in Flames' and the
        spell Flashback's "... gains flashback ... equal to its mana cost" -
        see `PlayPermission.flashback`'s own docstring for why its second,
        exile-on-leaving-the-stack half still has to apply, and for why
        Underworld Breach (which grants escape, not flashback) is not one.
        """
        with self._id_allocator_scope():
            turn = self.turn
            permission = PlayPermission(
                card_id=card.id,
                zone_change_stamp=card.zone_change_stamp,
                player=player,
                zone=zone,
                action=action,
                pays_mana_cost=pays_mana_cost,
                flashback=flashback,
                source_name=source_name,
                rule=rule,
                until_end_of_turn=until_end_of_turn
                and until_next_turn_of is None
                and until_next_end_step_of is None,
                granted_turns_taken=None if turn is None else int(turn.turns_taken),
                immediate=immediate,
                granted_step=None if turn is None else turn.step,
                until_next_turn_of=until_next_turn_of,
                expires_end_of_next_turn=expires_end_of_next_turn,
                any_type_mana=any_type_mana,
                condition=condition,
                exile_instead_of_graveyard=exile_instead_of_graveyard,
                until_next_end_step_of=until_next_end_step_of,
                pays_life_for_mana_value=pays_life_for_mana_value,
                choice_group=choice_group,
                while_controlling=while_controlling,
                cost_increase=cost_increase,
            )
            self.play_permissions.append(permission)
            return permission

    def static_life_costs_for(
        self: "Game",
        spell: CardState,
        caster: str,
        targets: Sequence[TargetRef] | None = None,
    ) -> list[tuple[int, str]]:
        """The additional life costs (amount, source name) the board's static
        abilities put on `spell` as `caster` casts it (CR 118.8, CR 601.2f):
        Terror of the Peaks' "Spells your opponents cast that target this
        creature cost an additional 3 life to cast." - keyed on the targets
        announced at CR 601.2c, and only an opponent of the permanent's
        controller pays it."""
        from ...machines.cost.text import targeting_this_life_cost

        costs: list[tuple[int, str]] = []
        if not targets:
            return costs
        board = self.computed_board()
        for permanent in self.battlefield:
            if permanent.controller == caster:
                continue
            if not any(target.card_id == permanent.id for target in targets):
                continue
            for line in board.of(permanent).abilities:
                amount = targeting_this_life_cost(self._static_line_without_ability_word(line))
                if amount is not None:
                    costs.append((amount, permanent.name))
        return costs

    def static_cost_modifiers_for(
        self: "Game",
        spell: CardState,
        caster: str | None = None,
        *,
        origin_zone: Zone | None = None,
        targets: Sequence[TargetRef] | None = None,
        casting: object | None = None,
    ) -> tuple[list[ManaCost], list[ManaCost], int | None]:
        """Board-wide static cost increases, decreases, and the floor in play
        right now (CR 601.2f, 611.3).

        Unlike `cost_reduction_for`, which reads *this* spell's own text for a
        self-discount, this reads every *other* permanent's static ability for
        a tax, a discount, or a floor on spells in general: Sphere of
        Resistance and Thorn of Amethyst's flat increases, Damping Sphere's
        per-spell-this-turn increase, Trinisphere's floor, the Medallion
        cycle's/Ral, Monsoon Mage's own color- or type-scoped discount.
        `Casting.total_cost` folds this in for every ordinary cast, so nothing
        has to opt in the way `determine_total_cost` does for a self-reduction.

        A permanent whose text names a card-type qualifier ("Noncreature
        spells cost {1} more") only taxes a spell that lacks that type
        (CR 205.2b: a multi-type card is checked against all of them). A
        permanent whose ability requires being untapped (Trinisphere's own
        clause) is skipped while tapped (CR 611.3b: a static ability's effect
        applies only while its source carries it). `COLOR_DECREASE`/
        `TYPE_DECREASE` are controller-scoped ("spells *you* cast"): only
        counted when the permanent's controller is `caster`.

        Text that reads like a cost modifier but does not match one of
        `cost_modifier_effect`'s recognised shapes is neither applied nor
        silently skipped: a `CostModifierNotice` is appended to
        `cost_modifier_notices` instead (DDR#978 - an increase that fails to
        apply looks identical to ordinary play). Deduplicated by source,
        since this runs every time a cost is priced.

        A loyalty-ability-granted, time-boxed discount - Ral, Monsoon Mage's
        own "+1: Until your next turn, instant and sorcery spells you cast
        cost {1} less to cast." - is not read off any live permanent's text
        (Ral may have transformed away since granting it), so it is folded in
        separately here from `casting_rule_effects`
        (`CastingRuleKind.INSTANT_SORCERY_COST_REDUCTION_GRANT`), the same
        `Duration.UNTIL_YOUR_NEXT_TURN` record Teferi, Time Raveler's own +1
        already uses.
        """
        caster = caster or spell.controller or self.active_player.username
        # CR 601.2a: where the spell was cast from - handed in by a casting
        # already on the stack, read off the card before it has moved.
        cast_from = origin_zone if origin_zone is not None else spell.zone
        increases: list[ManaCost] = []
        decreases: list[ManaCost] = []
        floor: int | None = None
        already_noticed = {notice.source_id for notice in self.cost_modifier_notices}

        for permanent in self.battlefield:
            # Same DFC-family fix as `effect_for`: `oracle_text` reads the up
            # face, `card.oracle_text` is null for a modal-DFC/transform
            # permanent and would silently skip its static ability.
            # `class_ability_text` narrows further for a Class permanent
            # (CR 716.2a): a level-gated paragraph is not "in effect" yet.
            #
            # Read line by line, not as one blob: CR 604.1 makes each
            # sentence-per-line its own static ability (Grand Arbiter
            # Augustin IV prints three - two color discounts and an
            # opponent-scoped tax, all three readable), and
            # `cost_modifier_effect` only ever answers for the *first* shape
            # it recognises in whatever text it is given. Reading the whole
            # card at once would either apply only the first ability and
            # silently drop the rest, or (worse) let one recognised line's
            # match suppress the fail-closed notice the *other*, unreadable
            # line still needs - splitting first is what keeps each ability
            # independent, matching this project's "one paragraph is one
            # ability" rule instead of quietly merging every line on a card
            # into a single verdict.
            #
            # Only a genuine `AbilityKind.STATIC` line qualifies (CR 604.1's
            # own "written as statements" versus CR 602.1's "[Cost]:
            # [Effect]" for an activated ability). `class_ability_text` still
            # prints an activated or triggered ability's line right alongside
            # a static one, and `cost_modifier_effect`'s own shapes are
            # unanchored substring matches - Ral, Leyline Prodigy's +1
            # ("Until your next turn, instant and sorcery spells you cast
            # cost {1} less to cast.") contains that exact discount sentence
            # inside an activated ability's *effect*, gated on the loyalty
            # cost being paid and on `Duration.UNTIL_YOUR_NEXT_TURN` (recorded
            # separately as a `CastingRuleEffect` once actually activated -
            # see `create_instant_sorcery_cost_reduction_grant`). Without this
            # filter the mere printed line made the discount permanent and
            # unconditional the instant Ral transformed, whether or not the
            # +1 was ever activated: a real defect this wave closes.
            up_face_name = permanent.up_face_name or permanent.card.name
            static_lines = {
                ability.raw.strip()
                for ability in parse_abilities(permanent.card)
                if ability.face == up_face_name
                and ability.kind is AbilityKind.STATIC
                and (ability.class_level is None or ability.class_level <= permanent.class_level)
                and permanent.station_threshold_met(ability.station_threshold)
            }
            for line in (permanent.class_ability_text or "").split("\n"):
                text = line.strip()
                if not text or text not in static_lines:
                    continue
                # CR 614.12a: "• Dragons — <static>" under an as-enters
                # "choose Khans or Dragons" is in effect only while that mode
                # is the recorded choice (the static twin of
                # `abilities._parse_line_mode_gated`).
                if (bullet := _MODE_BULLET_STATIC_RE.match(text)) is not None:
                    chosen_mode = permanent.choice
                    if (
                        chosen_mode is None
                        or chosen_mode.kind is not ChoiceKind.MODE
                        or chosen_mode.value.lower() != bullet.group("mode").lower()
                    ):
                        continue
                    text = bullet.group("body")
                # Read before `cost_modifier_effect` (`machines/cost.py`, not
                # this task's file - see the reader just below): The Scarlet
                # Witch's own "Instant and sorcery spells you cast with mana
                # value `<N>` or greater cost `{X}` less to cast, where X is
                # The Scarlet Witch's power." scales by the granting
                # permanent's own live power (CR 107.3a's X, CR 613.1's
                # layer-7c stat), a shape no `CostModifierEffect` kind reads.
                self_power_reduction = self._type_mv_threshold_cost_less_self_power(
                    text, permanent, spell, caster
                )
                if self_power_reduction is not None:
                    if self_power_reduction.symbols:
                        decreases.append(self_power_reduction)
                    continue

                # Read before `cost_modifier_effect`, which has no shape for a
                # discount *gated* on a count rather than scaled by one:
                # Gran-Gran's "Noncreature spells you cast cost {1} less to
                # cast as long as there are three or more Lesson cards in your
                # graveyard." The gate is checked against the graveyard as it
                # stands when CR 601.2f determines the cost, which is five
                # steps after CR 601.2a moved the spell being cast off it -
                # so flashing back one of exactly three Lessons leaves two and
                # gets no discount.

                effect = cost_modifier_effect(text)
                if effect is not None and effect.condition is not None:
                    # Gran-Gran's "as long as <condition>" (CR 611.3a): read
                    # now, about the permanent's own controller - "your".
                    owner = permanent.controller or caster
                    if not self.condition_holds(owner, effect.condition, permanent):
                        continue
                if effect is None:
                    # EP-01 T7: the group-spell grammar of `machines/cost/
                    # groups.py` (qualities, ordinals, "that target ...",
                    # counts, "where X is", "if <condition>").
                    group = group_spell_modifier(text)
                    if group is not None:
                        priced = group.modification(
                            CostContext(
                                game=self,
                                owner=caster,
                                spell=spell,
                                source=permanent,
                                targets=tuple(targets or ()),
                                casting=casting,
                            ),
                            caster,
                            cast_from,
                        )
                        if priced is not None:
                            (decreases if group.sign < 0 else increases).append(priced)
                        continue
                    if (
                        looks_like_unparsed_cost_modifier(text)
                        and permanent.id not in already_noticed
                    ):
                        already_noticed.add(permanent.id)
                        self.cost_modifier_notices.append(
                            CostModifierNotice(
                                source_id=permanent.id, source_name=permanent.name, text=text
                            )
                        )
                    continue

                if effect.kind is CostModifierKind.FLOOR:
                    if effect.requires_untapped and permanent.tapped:
                        continue
                    if floor is None or effect.amount > floor:
                        floor = effect.amount
                elif effect.kind is CostModifierKind.FLAT_INCREASE:
                    if (
                        effect.excludes_type is not None
                        and effect.excludes_type in spell.types_as_a_spell(spell.card.types)
                    ):
                        continue
                    increases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.OPPONENT_TYPE_INCREASE:
                    # Thalia, the Survivor: "your opponents cast" - only when
                    # the permanent's controller is not the caster, the exact
                    # mirror of COLOR_DECREASE/TYPE_DECREASE's own "you cast"
                    # scoping below.
                    if permanent.controller == caster:
                        continue
                    if (
                        effect.excludes_type is not None
                        and effect.excludes_type in spell.types_as_a_spell(spell.card.types)
                    ):
                        continue
                    increases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.TARGETING_THIS_INCREASE:
                    # Pursued Whale: "Spells your opponents cast that target
                    # this creature cost {3} more" - CR 601.2c's announced
                    # targets are what the tax is keyed on, and a caster
                    # who controls the permanent is not "your opponents".
                    if permanent.controller == caster:
                        continue
                    if any(target.card_id == permanent.id for target in targets or ()):
                        increases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.TARGETING_CONTROLLER_INCREASE:
                    # Monastery Siege (Dragons): "that target you or a
                    # permanent you control" - CR 601.2c's announced targets,
                    # a player target by username, an object by the controller
                    # of the permanent it names.
                    if permanent.controller == caster:
                        continue
                    for target in targets or ():
                        if target.username is not None:
                            hit = target.username == permanent.controller
                        else:
                            aimed = (
                                self.find_by_id(target.card_id)
                                if target.card_id is not None
                                else None
                            )
                            hit = aimed is not None and aimed.controller == permanent.controller
                        if hit:
                            increases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                            break
                elif effect.kind is CostModifierKind.NAMED_INCREASE:
                    # Disruptor Flute: "Spells with the chosen name cost {3}
                    # more to cast." The name is CR 614.12a's choice, made as
                    # the permanent entered and recorded on `CardState.choice`;
                    # nothing about the printed line says who it taxes, so a
                    # Flute that somehow never made its choice taxes nothing
                    # and says so rather than quietly applying to everything.
                    chosen = permanent.choice
                    if chosen is None or chosen.kind is not ChoiceKind.CARD_NAME:
                        if permanent.id not in already_noticed:
                            already_noticed.add(permanent.id)
                            self.cost_modifier_notices.append(
                                CostModifierNotice(
                                    source_id=permanent.id, source_name=permanent.name, text=text
                                )
                            )
                        continue
                    if chosen.value == spell.name or chosen.value == spell.card.name:
                        increases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.NAMED_DECREASE:
                    # Council of the Absolute: the discount twin of
                    # `NAMED_INCREASE`, for the permanent's controller's own
                    # spells ("you cast").
                    if permanent.controller != caster:
                        continue
                    chosen = permanent.choice
                    if chosen is None or chosen.kind is not ChoiceKind.CARD_NAME:
                        if permanent.id not in already_noticed:
                            already_noticed.add(permanent.id)
                            self.cost_modifier_notices.append(
                                CostModifierNotice(
                                    source_id=permanent.id, source_name=permanent.name, text=text
                                )
                            )
                        continue
                    if chosen.value == spell.name or chosen.value == spell.card.name:
                        decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.CHOSEN_TYPE_DECREASE:
                    # Gathering Stone: "Spells you cast of the chosen type
                    # cost {1} less to cast." `NAMED_INCREASE`'s own mirror -
                    # "you cast" scopes it to the permanent's own controller
                    # the same way `COLOR_DECREASE`/`TYPE_DECREASE` already
                    # are. Urza's Incubator prints the same choice with
                    # neither "you cast" (so `scoped_to_caster` is False and
                    # every player's matching spell is discounted, not only
                    # this permanent's controller's) nor a bare "spells" (so
                    # `creature_only` demands CR 300.1's own type too) - a
                    # Stone/Incubator that somehow never made its choice
                    # discounts nothing rather than quietly discounting
                    # everything.
                    if effect.scoped_to_caster and permanent.controller != caster:
                        continue
                    if effect.creature_only and Type.CREATURE not in spell.types_as_a_spell(
                        spell.card.types
                    ):
                        continue
                    chosen = permanent.choice
                    if chosen is None or chosen.kind is not ChoiceKind.CREATURE_TYPE:
                        if permanent.id not in already_noticed:
                            already_noticed.add(permanent.id)
                            self.cost_modifier_notices.append(
                                CostModifierNotice(
                                    source_id=permanent.id, source_name=permanent.name, text=text
                                )
                            )
                        continue
                    if chosen.value.lower() in {subtype.lower() for subtype in spell.subtypes}:
                        decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.PER_SPELL_INCREASE:
                    prior = len(self.spells_cast_this_turn.get(caster, []))
                    if prior:
                        increases.append(ManaCost.parse(f"{{{effect.amount * prior}}}"))
                elif effect.kind is CostModifierKind.SYMBOL_DECREASE:
                    # "Spells you cast": only the permanent's controller's.
                    if permanent.controller != caster or effect.reduction is None:
                        continue
                    decreases.append(ManaCost.parse(effect.reduction))
                elif effect.kind is CostModifierKind.ZONE_DECREASE:
                    # Bilbo: "Spells you cast from anywhere other than your
                    # hand" - the caster's own, by the zone cast from.
                    if permanent.controller != caster:
                        continue
                    if (effect.from_zone is not None and cast_from is effect.from_zone) or (
                        effect.not_from_zone is not None and cast_from is not effect.not_from_zone
                    ):
                        decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.COLOR_DECREASE:
                    if permanent.controller != caster:
                        continue
                    if effect.applies_to_color in spell.colors:
                        decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.TYPE_DECREASE:
                    if permanent.controller != caster:
                        continue
                    if effect.excludes_type is not None:
                        if effect.excludes_type not in spell.types:
                            decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                    elif effect.applies_to_types is not None and any(
                        t in spell.types for t in effect.applies_to_types
                    ):
                        decrease = self._counted_type_decrease(effect, permanent, spell, caster)
                        if decrease is not None:
                            decreases.append(decrease)
                    elif (
                        effect.applies_to_supertype is not None
                        and effect.applies_to_supertype in spell.supertypes
                    ):
                        # CR 205.4: "Legendary spells you cast cost {1} less for
                        # each card exiled with ~" - the permanent's linked pile
                        # (CR 607.2a), counted now (CR 611.3a).
                        units = effect.amount
                        if effect.per_card_exiled_with_source:
                            units *= len(
                                self.cards_exiled_with(permanent.id, permanent.zone_change_stamp)
                            )
                        if units > 0:
                            decreases.append(ManaCost.parse(f"{{{units}}}"))
                    elif effect.applies_to_subtype is not None and any(
                        subtype.lower() == effect.applies_to_subtype for subtype in spell.subtypes
                    ):
                        # `CardState.subtypes`: the spell is off the battlefield,
                        # so its changeling CDA is read there (CR 702.73a).
                        decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))

        for reduction in self.spell_cost_reduction_grants:
            # CR 601.2f: "<quality> spells you cast this turn cost {N} less".
            if (
                reduction.controller == caster
                and self.turn is not None
                and reduction.turn == self.turn.turns_taken
                and spell_has_quality(spell, reduction.quality)
            ):
                decreases.append(ManaCost.parse(f"{{{reduction.amount}}}"))

        for grant in self.casting_rule_effects:
            if (
                grant.kind == CastingRuleKind.INSTANT_SORCERY_COST_REDUCTION_GRANT
                and grant.controller == caster
                and grant.amount is not None
                and (Type.INSTANT in spell.types or Type.SORCERY in spell.types)
            ):
                decreases.append(ManaCost.parse(f"{{{grant.amount}}}"))

        return increases, decreases, floor

    def _unlocked_door_counts(self: "Game") -> dict[str, int]:
        """Unlocked doors (CR 709.5c) on the Room permanents each player controls."""
        counts: dict[str, int] = {}
        for permanent in self.battlefield:
            if permanent.unlocked_doors and permanent.controller is not None:
                counts[permanent.controller] = counts.get(permanent.controller, 0) + len(
                    permanent.unlocked_doors
                )
        return counts

    def _foretold_in_exile_counts(self: "Game") -> dict[str, int]:
        """Foretold cards (CR 702.143a) in exile, per owner."""
        counts: dict[str, int] = {}
        for card in self.exile:
            annotation = getattr(card, "exile_annotation", None)
            if (
                annotation is not None
                and annotation.marker is ExileMarker.FORETOLD
                and card.owner is not None
            ):
                counts[card.owner] = counts.get(card.owner, 0) + 1
        return counts

    def has_static_spells_flash_grant(self: "Game", caster: str, spell: CardState) -> bool:
        """Whether some permanent `caster` controls grants *every* spell
        flash right now via `_CAST_SPELLS_AS_THOUGH_FLASH_RE`'s shape - wider
        than `has_first_spell_flash_grant`'s own type-and-cost-reduction
        template, and never conditioned on `spell`'s own type at all.

        A conditional grant's "as long as `<condition>`" is read through
        `condition_holds` the same way an "Activate only if" restriction is
        (CR 602.5b's own fail-closed default): an unreadable condition
        refuses the grant rather than allowing it unchecked.
        """
        board = self.computed_board()
        for permanent in self.permanents_controlled_by(caster):
            for line in board.of(permanent).abilities:
                match = self._CAST_SPELLS_AS_THOUGH_FLASH_RE.fullmatch(
                    self._static_line_without_ability_word(line)
                )
                if match is None:
                    continue
                condition = match.group("condition")
                if condition is None:
                    return True
                if self.condition_holds(caster, condition.strip(), permanent) is True:
                    return True
        return False

    def _creatures_died_under_control_this_turn(self: "Game") -> dict[str, int]:
        """Per player, the creatures put into a graveyard from the battlefield
        under their control this turn (CR 700.4), each judged by its type as
        it last existed (`TurnHistoryEntry.characteristics`)."""
        died: dict[str, int] = {}
        for entry in self.turn_history:
            if (
                entry.kind == "to_graveyard"
                and entry.player is not None
                and entry.characteristics is not None
                and Type.CREATURE in entry.characteristics.types
            ):
                died[entry.player] = died.get(entry.player, 0) + 1
        return died

    @classmethod
    def reads_enforced_static_line(cls, text: str, card_name: str) -> bool:
        """`support.py`'s credit: whether one printed static line is a shape
        one of this class's own battlefield readers enforces, matched exactly
        the way that reader matches it - `controls_look_at_top_permission`,
        `land_from_top_of_library_permission`, `has_granted_improvise`,
        `_type_mv_threshold_cost_less_self_power`, `_power_up_group_discount`,
        `_power_up_activation_limit`, `_legendary_creature_count_power` and
        `_activated_ability_group_discount` (via `activated_ability_group_
        discount_effect`)."""
        line = cls._static_line_without_ability_word(text)
        return (
            cls._LOOK_AT_TOP_CARD_ANY_TIME_RE.fullmatch(line) is not None
            or cls._PLAY_WITH_HAND_REVEALED_RE.fullmatch(line) is not None
            or cls._TOP_CARD_REVEALED_RE.fullmatch(line) is not None
            or cls._REVEALS_EACH_CARD_DRAWN_RE.fullmatch(line) is not None
            or cls._PLAYS_LANDS_FROM_TOP_OF_LIBRARY_RE.fullmatch(line) is not None
            or cls._SPELLS_YOU_CAST_HAVE_IMPROVISE_RE.fullmatch(line) is not None
            or cls._TYPE_MV_THRESHOLD_COST_LESS_SELF_POWER_RE.fullmatch(
                self_normalized_effect_text(card_name, text, legendary=True).strip()
            )
            is not None
            or cls._POWER_UP_GROUP_DISCOUNT_RE.fullmatch(text.strip()) is not None
            or text.strip() == cls._POWER_UP_EXTRA_ACTIVATION_TEXT
            or activated_ability_group_discount_effect(text.strip()) is not None
            or _LEGENDARY_TYPE_COUNT_POWER_RE.fullmatch(
                self_normalized_effect_text(card_name, text).strip()
            )
            is not None
        )

    def _still_has_static_line(self: "Game", permanent: CardState, text: str) -> bool:
        """Whether the computed board still shows this static line (CR 613.1f).

        The static-ability twin of `_still_has_ability`: a permanent that lost
        all abilities in layer 6 has no prohibition to enforce either.
        """
        try:
            computed = self.characteristics_of(permanent)
        except KeyError:
            return True
        if not computed.abilities:
            return not (permanent.oracle_text or "").strip()
        return any(text in line or line in text for line in computed.abilities)

    def _has_computed_type(self: "Game", permanent: CardState, card_type: Type) -> bool:
        """Whether the permanent has this card type right now (CR 613.5)."""
        try:
            return card_type in self.characteristics_of(permanent).types
        except KeyError:
            return card_type in permanent.types

    # -- controlling another player (CR 723) -------------------------------

    def _sync_player_control(self: "Game") -> None:
        """Show the priority machine who is deciding for whom (CR 723.5).

        The effect itself lives on `TurnMachine`, because CR 723.1 scopes it to
        a whole turn. `PriorityMachine` only needs to know who may act.
        """
        assert self.turn is not None
        if self.priority is not None:
            self.priority.controlled_by = dict(self.turn.player_control)

    def gain_control_of_player(self: "Game", controller: str, controlled: str) -> None:
        """Gain control of another player during their next turn (CR 723.1).

        This is Emrakul, the Promised End's cast trigger and the only shape of
        the effect this engine models. CR 723.1: "This effect applies to the
        next turn that the affected player actually takes", so nothing changes
        now - the effect waits on `TurnMachine` until that turn begins, and
        CR 723.1b keeps it waiting through any skipped turn.

        A later effect on the same player replaces this one (CR 723.1a).
        """
        with self._id_allocator_scope():
            assert self.turn is not None
            self.player(controller)  # raises if unknown
            self.player(controlled)
            self.turn.gain_control_of_player(controller, controlled)
            self._sync_player_control()

    def controller_of_player(self: "Game", username: str) -> str:
        """Who is making this player's decisions (CR 723.5, 723.8, 723.9).

        Themselves, unless a player-controlling effect is in force this turn.
        """
        assert self.turn is not None
        return self.turn.controller_of_player(username)

    def is_controlling_player(self: "Game", controller: str, controlled: str) -> bool:
        """Whether `controller` is deciding for `controlled` right now (CR 723.1)."""
        return controller != controlled and self.controller_of_player(controlled) == controller

    # -- extra turns (CR 500.7) --------------------------------------------

    def grant_extra_turn(self: "Game", username: str) -> None:
        """This player takes an extra turn after the current one (CR 500.7).

        The turns are added directly after the turn in progress; several of them
        are added one at a time and the most recently created is taken first.
        """
        assert self.turn is not None
        self.player(username)  # raises if unknown
        self.turn.grant_extra_turn(username)

    def controller_of(self: "Game", state: StackObject) -> Player:
        """Who controls this object. Unlabelled cards belong to the active player.

        For a permanent this is CR 613.1b's layer 2 answer, not a stored one:
        `CardState.controller` consults the computed board (CR 613.5), so a
        "gain control of it until end of turn" effect reaches every caller
        here - combat, the state-based actions, a delayed trigger - without
        any of them knowing the layer system exists. An `AbilityOnStack`'s
        controller is a plain field, and rightly: CR 603.3 fixes it when the
        ability is put on the stack.
        """
        return self.player(state.controller) if state.controller else self.active_player


from ...machines import game_rule_statics  # noqa: E402
from ._common import (  # noqa: E402
    _COLOR_WORDS,
    _DAMAGE_CANT_BE_PREVENTED_RE,
    _DRAW_OR_LIFE_GAIN_PROHIBITION_RE,
    _DRAW_PROHIBITION_RE,
    _ENCHANTED_PLAYER_LIFE_GAIN_PROHIBITION_RE,
    _LEGENDARY_TYPE_COUNT_POWER_RE,
    _LIFE_GAIN_PROHIBITION_RE,
    _OPPONENTS_LIFE_GAIN_PROHIBITION_RE,
)
from ._conditions import _card_type_named, _permanent_quality  # noqa: E402

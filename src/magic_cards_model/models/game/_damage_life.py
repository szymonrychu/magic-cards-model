import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING
from uuid import UUID

from ...machines.abilities import (
    AbilityKind,
    TriggerEvent,
    parse_abilities,
)
from ...machines.casting_restrictions import (
    CastingRuleKind,
)
from ...machines.combat import (
    Keyword,
    source_had_keyword,
)
from ...machines.keyword_counters import (
    consume_shield_counter,
    has_shield_counter,
)
from ...machines.replacement import (
    EventKind,
    ReplaceableEvent,
    apply_replacements,
)
from ...machines.triggers import (
    GameEvent,
)
from ..card import (
    Type,
)
from ..card_state import (
    CardState,
    Counter,
)
from ..player import Player
from ..zone import Zone
from ._common import Targetable
from .records import PreventionShield

if TYPE_CHECKING:
    from . import Game


#: A sentence that prohibits life gain but is not the symmetric shape above -
#: matched only to fail closed with a notice rather than let it read as
#: permission, exactly as `_LOOKS_LIKE_ACTIVATION_PROHIBITION_RE` does.
_LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE = re.compile(r"\bcan't gain life\b", re.IGNORECASE)


class DamageLifeMixin:
    @contextmanager
    def recording_damage_from(self: "Game", source: CardState) -> Iterator[list[UUID]]:
        """Collect, for the span of the block, every permanent `source`
        deals damage to - damage that was actually dealt, after prevention
        (CR 615.1a) - for a rider that names the permanents "dealt damage
        this way" (Anger of the Gods' "If a creature dealt damage this way
        would die this turn, exile it instead")."""
        recorded: list[UUID] = []
        previous = self._damage_recorders.get(source.id)
        self._damage_recorders[source.id] = recorded
        try:
            yield recorded
        finally:
            if previous is None:
                self._damage_recorders.pop(source.id, None)
            else:
                self._damage_recorders[source.id] = previous

    def remove_all_damage(self: "Game") -> None:
        """Wipe damage marked on every permanent (CR 514.2, 703.4p).

        The unspent regeneration shields go with it, for the same reason and
        in the same breath: CR 701.19a's shield protects a permanent "the next
        time it would be destroyed **this turn**", so one nobody spent expires
        exactly when every other "until end of turn" effect does.
        """
        for permanent in self.battlefield:
            permanent.damage = 0
            permanent.regeneration_shields = 0

    def become_monarch(self: "Game", player: Player | str) -> None:
        """`player` becomes the monarch (CR 725.1).

        CR 725.3: "As a player becomes the monarch, the current monarch
        ceases to be the monarch" - a plain reassignment already is this,
        since `monarch` holds at most one username. Idempotent when `player`
        already is the monarch, which is not a rules question this method
        needs an opinion on - CR 725 never distinguishes becoming the monarch
        from staying it.
        """
        username = player.username if isinstance(player, Player) else player
        self.monarch = username

    def gain_life(self: "Game", player: Player | str, amount: int) -> int:
        """A player gains life, replacement effects included (CR 119.3).

        "If an effect causes a player to gain life or lose life, that player's
        life total is adjusted accordingly" - and CR 614.1a lets an effect such
        as Alhammarret's Archive replace how much before it is.
        """
        if isinstance(player, str):
            player = self.player(player)
        if amount <= 0:
            return player.life

        event = ReplaceableEvent(kind=EventKind.GAIN_LIFE, player=player, amount=amount)
        apply_replacements(self, event)
        # CR 119.9: a trigger written "Whenever [a player] gains life" is
        # treated as written "Whenever a source causes [a player] to gain
        # life". One event per gain (CR 702.15e makes even simultaneous
        # lifelink sources separate gains), and only if life was actually
        # gained - a gain replaced to zero never happened (CR 603.2g).
        if event.amount > 0:
            player.gain_life(event.amount)
            # The amount travels too: Heroic Feast's "choose up to that many
            # target creatures" counts the life this event gained (CR 119.9).
            self.emit(
                GameEvent(
                    event=TriggerEvent.GAINS_LIFE, player=player.username, amount=event.amount
                )
            )
        return player.life

    def lose_life(self: "Game", player: Player | str, amount: int) -> int:
        """A player loses life, returning the new total (CR 119.3).

        Every life loss comes through here - an effect's "loses N life",
        damage (CR 119.2, via `deal_damage_to_player`) and a life payment,
        which CR 119.4 says is life loss ("in other words, the player loses
        that much life") - so a "whenever a player loses life" trigger sees
        each one. The event carries the amount lost, what a "that player
        mills that many cards" trigger reads (The Master of Lake-town,
        Mindcrank); a loss of 0 is no event (CR 603.2g).

        Replacement effects get first refusal (CR 614.1a), the identical
        shape `gain_life` already gives CR 119.10's own gain-side doublers -
        Enduring Angel's own "if your life total would be reduced to 0 or
        less, instead ..." is what this opens up, and it sees damage-caused
        loss too: `deal_damage_to_player` always ends by calling this same
        method, *after* `EventKind.DAMAGE`'s own replacements (Elderscale
        Wurm's, Angel of Grace's floor) have already had their say, so the
        amount here is whatever survived those.
        """
        if isinstance(player, str):
            player = self.player(player)
        if amount <= 0:
            return player.life
        event = ReplaceableEvent(kind=EventKind.LOSE_LIFE, player=player, amount=amount)
        apply_replacements(self, event)
        if event.amount <= 0:
            return player.life
        new_total = player.lose_life(event.amount)
        self.emit(
            GameEvent(event=TriggerEvent.LOSES_LIFE, player=player.username, amount=event.amount)
        )
        return new_total

    def set_life_total(self: "Game", player: Player | str, amount: int) -> int:
        """A player's life total becomes a specific number (CR 119.5).

        CR 119.5: "If an effect sets a player's life total to a specific
        number, the player gains or loses the necessary amount of life to end
        up with the new total." So this is never a third way a life total
        moves - it is CR 119.3's gain or loss, worked out as a delta and sent
        through `gain_life`/`lose_life` exactly like any other one, which is
        what lets a "whenever you gain/lose life" trigger (CR 119.9), a life
        gain doubler (Alhammarret's Archive) or a can't-gain-life prohibition
        (CR 119.7) see this exactly the way they see a plain "you gain/lose N
        life" - reusing the one gain/loss path rather than writing `player.
        life = amount` directly, which would skip all three.

        Named `set_life_total` (not `life_total_becomes`) because it is the
        primitive every "life total becomes ..." reader calls once it has
        worked out the number - `machines/effects.py`'s trigger/resolution
        reader and `machines/replacement.py`'s "if you would lose the game"
        compilers both call this one function so the two stay in agreement
        about what CR 119.5 means.

        Already at the target total, this asks for neither a gain nor a loss
        (CR 603.2g: an amount of zero is not an event), so a `Player` already
        sitting at their starting life total (or a total already reset) is
        left alone rather than reported as a gain of zero.
        """
        if isinstance(player, str):
            player = self.player(player)
        delta = amount - player.life
        if delta > 0:
            self.gain_life(player, delta)
        elif delta < 0:
            self.lose_life(player, -delta)
        return player.life

    def exchange_life_totals(self: "Game", a: Player | str, b: Player | str) -> int:
        """Two players exchange life totals (CR 701.12a, CR 701.12c).

        CR 701.12a: "A spell or ability may instruct players to exchange
        something (for example, life totals ...) as part of its resolution.
        When such a spell or ability resolves, if the entire exchange can't
        happen, no part of the exchange occurs." `Player.exchange_life_totals`
        is where that all-or-nothing decision lives, together with CR 119.7 and
        CR 119.8's two reasons for refusing; this is the wrapper a resolving
        spell or ability actually reaches, the counterpart of `gain_life`.

        The **events** are this method's own job. CR 701.12c makes the exchange
        gains and losses ("each player gains or loses the amount of life
        necessary to equal the other player's previous life total"), so a
        trigger watching "whenever a player gains life" (CR 119.9) or loses it
        must see them - and the `Player` primitive adjusts the totals without
        emitting anything, exactly as `Player.gain_life` does under
        `Game.gain_life`. One event per player who actually moved: a player
        whose total was already equal gained and lost nothing, and CR 603.2g
        gives a trigger nothing to fire on there.

        No replacement effects are applied to the halves. CR 701.12c does say
        "Replacement effects may modify these gains and losses", and this does
        not do that yet - routing the halves back through `Game.gain_life`
        would re-ask CR 119.7 *after* the all-or-nothing decision had already
        been made on the pre-replacement amounts, which is the wrong order. It
        is recorded in `docs/engine-coverage.md` rather than half-built here.

        Returns the life **this** player - `a` - lost by the exchange, negative
        if they gained: Mister Negative's "If you lost life this way, draw that
        many cards" is the question, and it is asked from one side.
        """
        if isinstance(a, str):
            a = self.player(a)
        if isinstance(b, str):
            b = self.player(b)

        before = {a.username: a.life, b.username: b.life}
        lost = a.exchange_life_totals(b)
        for player in (a, b):
            moved = player.life - before[player.username]
            if moved > 0:
                self.emit(
                    GameEvent(event=TriggerEvent.GAINS_LIFE, player=player.username, amount=moved)
                )
            elif moved < 0:
                self.emit(
                    GameEvent(event=TriggerEvent.LOSES_LIFE, player=player.username, amount=-moved)
                )
        return lost

    def life_gain_prohibited(self: "Game", username: str) -> str | None:
        """Why this player can't gain life right now, or None (CR 119.7).

        CR 119.7: "If an effect says that a player can't gain life ..." - this
        is where that effect is found. Leyline of Punishment's "Players can't
        gain life." changes no characteristic of any object, so CR 613's layers
        have nothing to write and `machines/layers.py` is the wrong home; the
        effect belongs to CR 611.1's third category, "affects players or the
        rules of the game", and is read where the rules ask the question.

        The battlefield is rescanned on every call rather than cached, because
        CR 604.2 bounds a static ability's continuous effect to while its
        source is on the battlefield and CR 611.3a says such an effect "isn't
        'locked in'". A Leyline destroyed mid-turn stops prohibiting at once.

        The shapes in the pool are symmetric - "Players can't gain life"
        catches its own controller too - so no controller comparison is made.
        A sentence that prohibits life gain in a shape
        `_LIFE_GAIN_PROHIBITION_RE` cannot read records a `LayerNotice` and is
        **not** treated as permission, the same way `_activation_prohibition`
        fails closed on an unreadable prohibition.
        """
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                if not (
                    _LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE.search(text) or "gain life" in text.lower()
                ):
                    continue
                if not (
                    _LIFE_GAIN_PROHIBITION_RE.match(text)
                    or _DRAW_OR_LIFE_GAIN_PROHIBITION_RE.match(text)
                ):
                    self._record_unread_static_line(source, text)
                    continue
                if not self._still_has_static_line(source, text):
                    continue
                return f"{username} can't gain life: {source.name} says so (CR 119.7, CR 611.1)"
        # A resolved spell's or ability's "Players can't gain life this turn." /
        # "Your opponents can't gain life this turn." (CR 611.2c: recorded,
        # since its source is gone; CR 514.2 ends it in the cleanup step).
        for effect in self.casting_rule_effects:
            if effect.kind == CastingRuleKind.PLAYERS_CANT_GAIN_LIFE or (
                effect.kind == CastingRuleKind.OPPONENTS_CANT_GAIN_LIFE
                and effect.controller != username
            ):
                return (
                    f"{username} can't gain life this turn: {effect.source_name} says so "
                    "(CR 119.7, CR 611.2c)"
                )
        return None

    def damage_cant_be_prevented(self: "Game", event: ReplaceableEvent) -> str | None:
        """Why this damage can't be prevented, or None (CR 615.12).

        Two sources: a resolved "Damage can't be prevented this turn."
        (Skullcrack, recorded on `casting_rule_effects`), and a permanent's
        static "Damage can't be prevented." / "Combat damage can't be
        prevented." (Leyline of Punishment, Frenzied Baloth), read fresh off
        the battlefield like `life_gain_prohibited` (CR 604.2, CR 611.3a).
        """
        if event.kind is not EventKind.DAMAGE:
            return None
        for effect in self.casting_rule_effects:
            if effect.kind == CastingRuleKind.DAMAGE_CANT_BE_PREVENTED:
                return f"{effect.source_name}: damage can't be prevented this turn (CR 615.12)"
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                match = _DAMAGE_CANT_BE_PREVENTED_RE.fullmatch(text)
                if match is None or (match.group("combat") and not event.combat):
                    continue
                if not self._still_has_static_line(source, text):
                    continue
                return f"{source.name}: damage can't be prevented (CR 615.12)"
        return None

    # -- damage and life ---------------------------------------------------

    def _apply_damage_to_permanent(
        self: "Game", permanent: CardState, amount: int, *, as_counters: bool = False
    ) -> None:
        """What damage does to a permanent, by what the permanent is (CR 120.3).

        CR 120.3 opens with "Damage may have **one or more** of the following
        results, depending on ... the characteristics of the damage's recipient"
        - so this is a list of independent results, not a dispatch table with a
        fallback, and a permanent that is both a creature and a planeswalker
        (an animated Gideon) takes both.

        - **CR 120.3c** - "Damage dealt to a planeswalker causes that many
          loyalty counters to be removed from that planeswalker." **CR 306.8**
          says the same from the planeswalker's side. This is a result of the
          damage event itself and happens now; no state-based action is
          involved. The only state-based action here is the one *after* it -
          CR 306.9 / CR 704.5i put a planeswalker at 0 loyalty into its owner's
          graveyard, which `check_state_based_actions` already does.
        - **CR 120.3d** - "Damage dealt to a creature by a source with wither
          and/or infect causes that source's controller to put that many -1/-1
          counters on that creature." `as_counters` is that source question,
          answered by `deal_damage`; the counters go through `add_counters`,
          because CR 120.4c processes damage into its results "as modified by
          replacement effects that interact with those results (such as ...
          counters)".
        - **CR 120.3e** - "Damage dealt to a creature by a source with neither
          wither nor infect causes that much damage to be marked on that
          creature." Marking is the *creature* result, which is why it is not
          this method's default: marking damage on anything else invents
          bookkeeping the rules never asked for, and it is exactly what hid the
          missing CR 120.3c - a planeswalker attacked for lethal came out of
          combat with `damage=9` and its nine loyalty counters intact.
        - **CR 120.3h** - "Damage dealt to a battle causes that many defense
          counters to be removed from that battle." Removing the last one is
          what raises a Siege's defeat trigger (CR 310.12b).

        Anything that is none of these takes the damage and nothing happens,
        which is CR 120.3's own answer: no listed result applies to it.

        Which types those are is CR 613.5's question, so it is asked of the
        computed board rather than the printing: an animated planeswalker is a
        creature only there, and a planeswalker turned into a plain enchantment
        by Song of the Dryads is no longer one there either.
        """
        types = (
            self.characteristics_of(permanent).types
            if permanent.zone is Zone.BATTLEFIELD
            else permanent.types
        )
        if Type.BATTLE in types:
            # CR 120.3h: "Damage dealt to a battle causes that many defense
            # counters to be removed from that battle" - clamped to what is
            # there, the same as loyalty below.
            present = permanent.counter_count(Counter.DEFENSE)
            if present > 0:
                permanent.remove_counters(Counter.DEFENSE, min(amount, present))
        if Type.PLANESWALKER in types:
            # CR 120.3c removes "that many" counters, and there may not be that
            # many: `Counters.remove` refuses to take more than are present
            # (CR 118.3), so the removal is clamped to what is on the walker.
            # The excess is not damage that goes anywhere else - CR 702.19f is
            # explicit that even trample's excess cannot reach the player
            # unless the attacker has trample over planeswalkers.
            present = permanent.counter_count(Counter.LOYALTY)
            if present > 0:
                permanent.remove_counters(Counter.LOYALTY, min(amount, present))
        if Type.CREATURE in types:
            if as_counters:
                self.add_counters(permanent, Counter.MINUS_ONE, amount)
            else:
                permanent.mark_damage(amount)

    def deal_damage(
        self: "Game", target: Targetable, amount: int, *, source: "CardState | None" = None
    ) -> int:
        """Deal damage to a permanent or a player, and say how much landed.

        What damage *does* is CR 120.3's list, and it depends on what took it:
        a player loses that much life (CR 120.3a), a planeswalker has that many
        loyalty counters removed (CR 120.3c), a creature has that much damage
        marked on it (CR 120.3e). `_apply_damage_to_permanent` is the whole of
        the permanent half - see it for why marking is not the default.

        CR 120.1: "An object that deals damage is the source of that damage",
        and CR 120.7 says the source is simply "the object that dealt it". That
        object is `source`, and it is what makes three rules writable that were
        not before:

        - **CR 609.7b** - a prevention or replacement effect that watches for
          damage "from sources with certain properties" rechecks the source when
          the damage would be dealt.
        - **CR 615.8** - "the next time a specific source would deal damage".
        - **CR 702.16e** - "Any damage that would be dealt by sources that have
          the stated quality to a permanent or player with protection is
          prevented."

        - **CR 120.3b / 120.3d** - infect and wither turn the damage's results
          into poison and -1/-1 counters, read off the source (see below).

        It is optional because CR 120.2b's "the spell or ability will specify
        which object deals that damage" is a fact the caller holds; every
        permanent or spell that deals damage in `machines/combat.py`,
        `machines/effects.py` and here passes it. Anonymous damage is what a
        caller with no source object has left.

        Prevention and replacement effects get first refusal (CR 615.1, 616.1).
        CR 615.1a: "Effects that use the word 'prevent' are prevention effects.
        Prevention effects use 'prevent' to indicate what damage will not be
        dealt" - so a prevented event deals zero damage rather than dealing
        damage and undoing it.

        Returns the damage actually dealt, which is what CR 702.2b's deathtouch
        and CR 702.15b's lifelink both key off: zero damage is not damage dealt.
        """
        with self._id_allocator_scope():
            event = ReplaceableEvent(
                kind=EventKind.DAMAGE,
                card=None if isinstance(target, Player) else target,
                player=target if isinstance(target, Player) else None,
                amount=amount,
                combat=self._dealing_combat_damage,
                source=source,
            )
            apply_replacements(self, event)
            if event.happens and event.amount > 0 and event.card is not None:
                # CR 122.1c: "If damage would be dealt to this permanent,
                # prevent that damage and remove a shield counter from it."
                # A single hardcoded check at this one choke point, not a
                # registered `ContinuousEffect`/replacement `apply_
                # replacements` already ran - the identical shape CR
                # 122.1d's stun counter already gets at its own one choke
                # point (`CardState.untap`), and the reason is the same:
                # this is engine-intrinsic support for a counter kind, not a
                # printed ability `machines/replacement.py` (owned by a
                # different task this round) discovers from oracle text.
                # `event.card`, not `target`: CR 609.7b's own "the shield
                # rechecks" posture is what every other check here already
                # reads off the (possibly redirected) event, not the
                # original argument.
                recipient = event.card
                if recipient.zone is Zone.BATTLEFIELD and has_shield_counter(recipient):
                    consume_shield_counter(recipient)
                    event.amount = 0  # `ReplaceableEvent.happens` reads this back.
            if not event.happens or event.amount <= 0:
                return 0

            # CR 120.3's results depend on "the characteristics of the
            # damage's source": infect and wither are read here, inside the
            # damage event, not as replacements of it (CR 120.4c). By last
            # known information once the source has left the battlefield
            # (CR 702.90d, 702.80b), from any zone (CR 702.90e, 702.80c).
            infect = source is not None and source_had_keyword(source, Keyword.INFECT, self)
            wither = source is not None and source_had_keyword(source, Keyword.WITHER, self)
            if isinstance(target, Player):
                if infect:
                    # CR 120.3b / 702.90b: poison counters, and no life lost -
                    # so no CR 119.3 life-loss event either.
                    self.add_player_counters(target, Counter.POISON, event.amount)
                else:
                    self.deal_damage_to_player(target, event.amount)
            else:
                # CR 120.10: excess is measured against the recipient as it
                # was before this damage, so it is worked out now and carried
                # to the event raised below.
                from ...machines.conditions import history as condition_history

                self._pending_damage_excess = condition_history.excess_damage(
                    self, target, event.amount, source
                )
                self._apply_damage_to_permanent(target, event.amount, as_counters=infect or wither)
                ledger = self._combat_damage_this_step
                if event.combat and ledger is not None and not (infect or wither):
                    ledger[target.id] = ledger.get(target.id, 0) + event.amount
                if source is not None and source.id in self._damage_recorders:
                    self._damage_recorders[source.id].append(target.id)
            # CR 613.5: the source's characteristics for this event are the
            # computed ones while it is still a permanent - a land animated
            # by earthbend is a creature only there - and the printed type
            # line otherwise (a spell or ability off the battlefield has
            # nothing for the layer system to compute).
            source_types = source.types if source is not None else None
            source_subtypes = source.subtypes if source is not None else None
            if source is not None and source.zone is Zone.BATTLEFIELD:
                source_chars = self.characteristics_of(source)
                source_types = source_chars.types
                source_subtypes = source_chars.subtypes
            # CR 613.5, the recipient's own side of the same read above - for
            # Hexhaven Invigorator's own "Whenever this creature is dealt
            # damage" (`GameEvent.target_id`, the receiving end, as opposed to
            # `subject_id`'s dealing end).
            target_types = None
            target_controller = None
            if not isinstance(target, Player):
                target_types = target.types
                if target.zone is Zone.BATTLEFIELD:
                    target_chars = self.characteristics_of(target)
                    target_types = target_chars.types
                target_controller = self.controller_of(target).username
            damaged_player = target if isinstance(target, Player) else None
            # CR 120.1: "An object that deals damage is the source of that
            # damage" - the subject is the source, and the player, when there is
            # one, is who the damage went to. A prevention or replacement that
            # stopped the damage entirely has stopped the event too (CR 603.2g).
            self.emit(
                GameEvent(
                    event=TriggerEvent.DEALS_DAMAGE,
                    subject_id=source.id if source is not None else None,
                    subject_name=source.name if source is not None else None,
                    subject_controller=source.controller if source is not None else None,
                    subject_card=source.card if source is not None else None,
                    subject_types=source_types,
                    subject_subtypes=source_subtypes,
                    target_id=target.id if not isinstance(target, Player) else None,
                    target_controller=target_controller,
                    target_types=target_types,
                    player=damaged_player.username if damaged_player is not None else None,
                    combat=event.combat,
                    amount=event.amount,
                )
            )
            self._pending_damage_excess = 0
            if damaged_player is not None and not event.combat:
                # Master of Barbs' and Massacre Girl, Most Wanted's own
                # "whenever [an/one or more] opponent[s] [is/are] dealt
                # noncombat damage" (CR 120.2a) are matched straight off the
                # event above; this is the this-turn/last-turn half - Grim
                # Repriser's "an opponent has been dealt noncombat damage
                # this turn" and Command the Stage's "... last turn".
                self.record_turn_fact("dealt_noncombat_damage", damaged_player.username)
            if source is not None and not event.combat and event.amount > 0:
                self._noncombat_deathtouch_and_lifelink(source, target, event.amount)
            return event.amount

        # -- prevention effects with a duration (CR 615) --------------------------

    def create_prevention_shield(self: "Game", shield: PreventionShield) -> PreventionShield:
        """Record a prevention effect created by a resolving spell (CR 615.1, 615.4).

        CR 615.4: "Prevention effects must exist before the appropriate damage
        event occurs - they can't 'go back in time' and change something that's
        already happened." Creating the shield *is* the effect; nothing else
        happens when the spell resolves.

        CR 615.3: "There are no special restrictions on casting a spell or
        activating an ability that generates a prevention effect. Such effects
        last until they're used up or their duration has expired."
        """
        with self._id_allocator_scope():
            self.prevention_shields.append(shield)
            return shield

    def active_prevention_shields(self: "Game") -> list[PreventionShield]:
        """The shields that are neither used up nor expired (CR 615.3)."""
        return [shield for shield in self.prevention_shields if not shield.spent]

    def shield_applies(self: "Game", shield: PreventionShield, event: ReplaceableEvent) -> bool:
        """Whether this shield would prevent any of this damage (CR 615.7-615.9).

        CR 609.7b: "When the source would deal damage, the 'shield' rechecks the
        source's properties. If the properties no longer match, the damage isn't
        prevented or replaced." That recheck happens here, every time, against
        the source as it is now - not against the source as it was when the
        shield was made.

        A shield that names a source or a source quality never applies to
        anonymous damage: an unknown source is not a source that matches.
        """
        if shield.spent or event.kind is not EventKind.DAMAGE or event.amount <= 0:
            return False
        if shield.combat_only and not event.combat:
            return False
        if shield.card_id is not None and (event.card is None or event.card.id != shield.card_id):
            return False
        if shield.player is not None and (
            event.player is None or event.player.username != shield.player
        ):
            return False
        if shield.source_id is not None and (
            event.source is None or event.source.id != shield.source_id
        ):
            return False
        if shield.source_stamp is not None and (
            event.source is None or event.source.zone_change_stamp != shield.source_stamp
        ):
            return False  # CR 400.7: a new object the shield never named
        if shield.lasts_while is not None and not shield.lasts_while.holds_in(self):
            return False  # CR 611.2b: the duration has ended
        if shield.excluded_source_subtypes and event.source is not None:
            # CR 609.7b's recheck, against the source's subtypes as they are
            # now. An anonymous source is not excluded by name, so it stays
            # covered - the opposite of `source_quality`'s rule below, and for
            # the same reason: a shield that *names* what it covers cannot
            # match an unknown source, and one that names what it does *not*
            # cover cannot rule an unknown source out.
            subtypes = {
                subtype.lower() for subtype in self.characteristics_of(event.source).subtypes
            }
            if subtypes & {excluded.lower() for excluded in shield.excluded_source_subtypes}:
                return False
        return not (
            shield.source_quality is not None
            and (
                event.source is None
                or not self.source_has_quality(event.source, shield.source_quality)
            )
        )

    def apply_prevention_shield(
        self: "Game", shield: PreventionShield, event: ReplaceableEvent
    ) -> None:
        """Prevent what this shield prevents, and use it up if it prevented any.

        CR 615.7: "Each 1 damage that would be dealt to the 'shielded' permanent
        or player is prevented. Preventing 1 damage reduces the remaining shield
        by 1 ... Once the shield has been reduced to 0, any remaining damage is
        dealt normally."

        CR 615.8: a next-instance shield "prevents the next instance of damage
        from that source, regardless of how much damage that is."

        CR 609.7b's last sentence is the one that has to be honoured explicitly:
        "If for any reason the shield prevents no damage or replaces no damage,
        the shield isn't used up." So each branch sets `used_up` from what it
        actually prevented.

        CR 615.5 is the last step: "Some prevention effects also include an
        additional effect, which may refer to the amount of damage that was
        prevented. The prevention takes place at the time the original event would
        have happened; **the rest of the effect takes place immediately
        afterward**." `shield.prevented` is what such a rider reads, and it is
        recorded whether or not the shield carries one - a rider that is added
        later has the number waiting for it, and a scenario can assert on how much
        a shield ate without a card that says so.
        """
        prevented = 0
        if shield.kind is ShieldKind.AMOUNT:
            prevented = min(shield.amount, event.amount)
            shield.amount -= prevented
        else:
            prevented = event.amount
            if prevented > 0 and shield.kind is ShieldKind.NEXT_INSTANCE:
                shield.used_up = True
        event.amount -= prevented
        shield.prevented += prevented

        # CR 615.5's "immediately afterward". The life is gained now rather than
        # queued, because the prevention has already taken place - the damage
        # event in hand has had `amount` taken off it and cannot be undone
        # (CR 615.6: "if damage that would be dealt is prevented, it never
        # happens").
        if prevented > 0 and shield.gains_life_when_prevented:
            self.gain_life(shield.controller, prevented)

    def _noncombat_deathtouch_and_lifelink(
        self: "Game", source: "CardState", target: Targetable, dealt: int
    ) -> None:
        """CR 702.2b and CR 702.15b for damage that is not combat damage -
        `machines/combat._deal_combat_damage` applies both to combat damage
        itself. CR 702.2b destroys "a creature with toughness greater than 0
        that's been dealt damage by a source with deathtouch", and CR 702.15b
        has "damage dealt by a source with lifelink" gain "that source's
        controller ... that much life" - whatever deals it: a spell that gained the keywords
        (Judith, Carnage Connoisseur's "That spell gains deathtouch and
        lifelink.") or a permanent dealing noncombat damage. Read by last
        known information for a source that has left (`source_had_keyword`).
        """
        from ...machines.combat import Keyword, source_had_keyword

        if isinstance(target, CardState) and source_had_keyword(source, Keyword.DEATHTOUCH, self):
            target.dealt_deathtouch_damage = True
        if source_had_keyword(source, Keyword.LIFELINK, self):
            controller = source.controller or source.owner
            if controller is not None:
                self.gain_life(controller, dealt)

    def deal_damage_to_player(self: "Game", player: Player | str, amount: int) -> int:
        """Damage dealt to a player causes that much life loss (CR 119.2, 120.3a).

        Losing the game is not part of dealing damage: a player at zero or
        less life loses the next time state-based actions are checked
        (CR 704.5a), which is what `check_state_based_actions` does.

        The life loss is its own event as well (CR 119.3), because a trigger
        watching "a player loses life" fires for loss by damage the same as
        any other loss. A player who loses none triggers nothing.
        """
        with self._id_allocator_scope():
            if amount < 0:
                raise ValueError("cannot deal negative damage")
            if isinstance(player, str):
                player = self.player(player)
            if amount == 0:
                return player.life
            return self.lose_life(player, amount)

    def _reassign_monarch_after_departure(self: "Game", username: str) -> None:
        """CR 725.4: `username`, who held the monarch, has just left the game.

        "If the monarch leaves the game, the active player becomes the
        monarch at the same time as that player leaves the game. If the
        active player is leaving the game or if there is no active player,
        the next player in turn order who can become the monarch becomes the
        monarch. If no player still in the game can become the monarch, the
        game continues with no monarch."

        One loop reads both sentences at once: `order` is the fixed seating
        (CR 103.8), starting at the active player's own seat, so offset 0
        checks the active player first (the rule's first sentence) and each
        later offset walks forward in turn order (the second sentence) - the
        active player is skipped automatically the moment they are not
        `is_in_game` (already true here: `_player_left` is called only after
        `losers`/conceded bookkeeping already dropped `username`, and this
        runs for whichever player just left, active or not). No player found
        at all (`order` empty, or nobody left `is_in_game`) leaves `monarch`
        `None` - the rule's own last sentence.
        """
        if self.monarch != username:
            return
        order = self.turn.players if self.turn is not None else []
        if not order:
            self.monarch = None
            return
        active = self.turn.active_player
        start = order.index(active) if active in order else 0
        for offset in range(len(order)):
            candidate = order[(start + offset) % len(order)]
            if self.is_in_game(candidate):
                self.monarch = candidate
                return
        self.monarch = None


from ._common import (  # noqa: E402
    _DAMAGE_CANT_BE_PREVENTED_RE,
    _DRAW_OR_LIFE_GAIN_PROHIBITION_RE,
    _LIFE_GAIN_PROHIBITION_RE,
)
from .records import ShieldKind  # noqa: E402

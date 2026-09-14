"""Enumerating every legal action a player could take right now.

The library owes two guarantees. "Decode any game state" is `Game` itself,
which round-trips through `model_dump_json`. This is the other one:
`legal_actions(game, player)` enumerates what `player` could legally do at
this exact point, as a list of `Action` (`models/action.py`). Its answers are
written into an append-only log beside every action a seat actually takes -
"what else was legal at that moment" - so it has to be exhaustive, cheap
(`mise run rules:find` never runs in a hot loop; `_auto_tap_candidates` used
to), and free of side effects: nothing here taps a permanent, opens a
`CostPayment`, or moves a card.

**Legality and affordability are two different questions, answered
separately.** CR 118.6: "Attempting to cast a spell, activate an ability, or
take a special action that has an unpayable cost is a legal action." A `CAST`
or `ACTIVATE` action is included whenever the *begin-to-cast*/*begin-to-
activate* checks pass (zone, timing, CR 611.1 prohibitions), never gated on
whether the cost happens to be payable - that is what `Action.affordable`/
`Action.unaffordable_reason` report, alongside the action, not instead of it.

**A pending `Decision` changes what "legal" even means.** `Game` never
carries one - it is raised as a `DecisionPending` exception and held by
whichever caller catches it (the api's own mailbox is one such holder; see
`Action.decision_seq`'s own docstring) - so `legal_actions` cannot discover
one on its own. A caller that already knows a decision is outstanding passes
it as `pending`; the enumeration then answers *only* that decision (CR
608.2d, or whichever more specific rule `rule_for_kind` cites) for the
player it addresses, and nothing for anyone else, because nothing else in
this engine's own execution can happen until it is answered. The old API
probe returned `{}` when a decision was pending - not a permissive "nothing
you can do", but an honest hole, and one that cost eighteen defaulted
decisions in one recorded game (`memory/harness-deadlock-defaulted-every-
decision.md`).

**Modes and X are a parameter space, not an enumeration.** A modal spell with
an unbounded X has an unbounded number of (modes, X) combinations; `Action`
carries `modes` (the printed mode texts) and `x_range` (a `(minimum,
maximum)` pair, or an open-ended one) instead of one `Action` per
combination, the same treatment `Action.decision_candidates` gives a
`CHOOSE_CARDS`/`CHOOSE_TARGETS`-shaped decision's candidate pool rather than
enumerating every legal subset or permutation of it.

**What this does not enumerate**, named rather than silently dropped:

- **CR 116.2's other special actions** - CR 116.2c/d/e (an effect's own
  "ignore this" or "stop this" window, and the one Circling Vultures-specific
  discard), CR 116.2g (companion), CR 116.2i (Planechase's planar die),
  CR 116.2j (Conspiracy draft face-up), CR 116.2m (an unlock cost) - none of
  which this engine models at all (`grep`-confirmed empty for "companion",
  "planechase", "unlock cost", "locked half" across `src/`), so there is
  nothing here to enumerate a refusal for.
- **A targeted off-battlefield activation with no legal target to name.**
  `keywords.off_battlefield_activation` checks targets while it builds, so
  `_off_zone_actions` hands it the first legal candidates of the row's own
  `target_slots` (cost and timing do not depend on which legal target is
  named). When a requirement has too few - Boseiju, Who Endures's Channel
  with no artifact, enchantment, or nonbasic land an opponent controls - the
  build still refuses, and the row is reported `affordable=UNKNOWN` with the
  engine's own reason rather than dropped.
- **Multiplayer attack-declaration wrinkles** CR 508.1e (banding) and the
  CR 508.1b "multiple defending players" case beyond planeswalkers/battles -
  this engine's own `combat.py` does not model banding at all, and the
  defender pool built here is opposing players plus their planeswalkers and
  battles, not a wider multiplayer-attack-target menu.
"""

from collections.abc import Iterable
from typing import Any, NamedTuple

from ..models.action import (
    Action,
    ActionKind,
    Affordability,
    ManaPlanEntry,
    SpliceOption,
    TargetSlot,
)
from ..models.card import Card, Layout, Type
from ..models.card_state import CardState
from ..models.mana import ManaCost, ManaSpend
from ..models.player import Player
from ..models.zone import Zone
from ..snapshot import board_snapshot
from .abilities import printed_production
from .casting import (
    AlternativeCostSource,
    MarkedExile,
    PlayAction,
    adventure_face,
    granted_cast_options,
    keyword_cast_options,
    marker_cast_options,
    play_permissions_on,
    splice_candidates,
    why_cannot_cast_a_land,
    why_cannot_cast_from,
    why_cannot_cast_now,
    why_cannot_cast_restriction,
    why_mana_cost_unpayable,
)
from .combat import ATTACKABLE_PERMANENT_TYPES, unobeyed_attack_requirement
from .cost import (
    ComponentKind,
    CostComponent,
    TapPlan,
    TotalCost,
    _ScannedCandidate,
    _SpendContext,
    _withheld_mana_sources,
    mana_ability_index,
    mana_candidate_scan,
    plan_mana_payment,
    spend_restriction,
)
from .decisions import (
    Decision,
    DecisionKind,
    PendingDecision,
    legal_options,
    rule_for_kind,
)
from .keywords import (
    EQUIP_EFFECT,
    dredge_count,
    has_equip,
    off_zone_abilities,
    off_zone_activation,
    turn_face_up_cost,
    unannounced_equip_activation,
    why_cannot_dredge,
    why_cannot_turn_face_up,
)
from .modes import modal_profile
from .targeting import profile_for_text
from .turn import Step

_BOOLEAN_DECISION_KINDS = frozenset(
    {
        DecisionKind.MAY,
        DecisionKind.PAY_LIFE,
        DecisionKind.PAY_ENERGY,
        DecisionKind.PAY_MANA,
        DecisionKind.PUT_ON_TOP_OR_BOTTOM,
        DecisionKind.MULLIGAN,
        DecisionKind.OPENING_HAND_ACTION,
    }
)
#: `DECLARE_ATTACKERS`/`DECLARE_BLOCKERS` used to sit in the set above, which
#: `legal_options` reads as a plain `(True, False)` - but their answer is
#: `(creature, defender)` pairs (`Decision.kind`'s own docstring), never a
#: bare boolean, and `legal_options` (`machines/decisions.py`) has no branch
#: for either kind at all, so it fell through to its own `(True, False)`
#: catch-all. That produced two `decision_option`s ("true"/"false") nothing
#: downstream accepts, and - because the `pending` branch in `legal_actions`
#: short-circuits straight to `decision_answers`, never reaching `_attacker_
#: actions`/`_blocker_actions` - made the real per-pair actions unreachable
#: for exactly as long as one of these two decisions was outstanding.
#: `decision_answers` now special-cases both kinds directly (see below).


# ---------------------------------------------------------------------------
# Affordability: reported alongside legality, never used to gate it.
# ---------------------------------------------------------------------------


def _mana_affordability(
    game: Any,
    payer: str,
    mana: ManaCost,
    spend: ManaSpend | None,
    candidate_scan: list[_ScannedCandidate],
) -> tuple[Affordability, str | None, TapPlan | None]:
    """Whether `payer` could pay `mana` right now, **and how** -
    `plan_mana_payment`, with the enumeration's own `candidate_scan` threaded
    through so this never re-runs the board scan `mana_candidate_scan` already
    paid for once.

    The plan is what `could_pay_mana_cost` used to compute and reduce to a
    bool: which sources get tapped and for what, reported alongside the
    verdict instead of thrown away and solved a second time when the action is
    actually taken. `None` whenever there is no verdict to plan against (an
    unannounced X) or the cost cannot be paid at all - see `Action.pays_with`
    for the two gates that decide whether it reaches the record.
    """
    if mana.x_count:
        return Affordability.UNKNOWN, "X has not been announced yet (CR 107.3a)", None
    plan = plan_mana_payment(
        mana, game.battlefield, game=game, payer=payer, spend=spend, candidate_scan=candidate_scan
    )
    if plan is not None:
        return Affordability.YES, None, plan
    context = _SpendContext(game=game, payer=payer, spend=spend)
    withheld = _withheld_mana_sources(context, game.battlefield)
    reason = f"no combination of the available mana sources can pay {mana}"
    if withheld:
        named = "; ".join(
            f"{source.name} was not auto-tapped because its only mana ability costs more "
            f"than {{T}} ({ability.cost}: {ability.effect}) - activate it manually to include it"
            for source, ability in withheld
        )
        reason = f"{reason}; {named}"
    return Affordability.NO, reason, None


def _candidate_pool_for(game: Any, payer: str, component: CostComponent) -> list[CardState] | None:
    """Where `component`'s still-unchosen objects would come from, or `None`
    when this is not one of the shapes judged here (see `_component_
    affordability`'s own `UNKNOWN` fallback)."""
    kind = component.kind
    if kind in (ComponentKind.DISCARD, ComponentKind.REVEAL):
        return list(game.player(payer).hand)
    if kind is ComponentKind.EXILE:
        if component.zone.is_shared:
            # CR 406.2: exile moves an object "from whatever zone it's
            # currently in" - not only one of `payer`'s own zones. `exile_
            # cost`'s own `zone` can be `Zone.BATTLEFIELD` (Abstergo
            # Entertainment's own "Exile Abstergo Entertainment", `cost.py`'s
            # `CostComponent.pay` docstring on this exact gap), and a shared
            # zone (CR 400.1) has no entry in `Player.zones` at all - reading
            # it there returned an always-empty pool (so the component was
            # wrongly reported unpayable) and, because `Player.cards_in`
            # was `zones.setdefault(zone, [])`, permanently added a spurious
            # empty key to the player's own serialized zones as a side
            # effect. `cards_in` refuses a shared zone outright now.
            # Every card in the shared zone is the real pool; `_
            # component_affordability`'s own `requirement.why_not` filter
            # below narrows it to whichever ones this cost can actually name.
            return [
                card
                for card in game.shared_zones.get(component.zone, [])
                if isinstance(card, CardState)
            ]
        return list(game.player(payer).cards_in(component.zone))
    if kind in (
        ComponentKind.SACRIFICE,
        ComponentKind.TAP,
        ComponentKind.UNTAP,
        ComponentKind.EXERT,
    ):
        pool = game.permanents_controlled_by(payer)
        if kind is ComponentKind.TAP:
            return [card for card in pool if not card.tapped]
        if kind is ComponentKind.UNTAP:
            return [card for card in pool if card.tapped]
        return pool
    return None


def _component_affordability(
    game: Any, payer: str, component: CostComponent
) -> tuple[bool | None, str | None]:
    """Whether one non-mana `CostComponent` could be paid, without actually
    choosing anything to pay it with.

    `CostComponent.why_not` is built for a component whose objects are
    *already chosen* (`len(cards) == required`) - loyalty, self-tap, and a
    counter placed on the ability's own source are always built that way, so
    calling it straight through is correct for them. A component that still
    needs a player's choice (sacrifice a creature, discard a card, exile one
    from a named zone) has `cards == []` at this point, and `why_not` would
    only ever report "0 given, N needed" - which is true of every such cost
    before anyone answers and says nothing about whether *this player* could
    pay it. This counts eligible candidates instead, the same
    `CardRequirement.why_not` check `why_not` itself would run once objects
    were chosen, so the two can never disagree about which objects qualify.
    """
    if len(component.cards) >= component.required:
        refusal = component.why_not(game)
        return refusal is None, refusal
    pool = _candidate_pool_for(game, payer, component)
    if pool is None:
        return None, (
            f"{component.description or component.kind.value} affordability is not judged "
            "before its objects are chosen"
        )
    needed = component.required - len(component.cards)
    eligible = [
        card
        for card in pool
        if component.requirement is None
        or component.requirement.why_not(card, game, component.payer or payer) is None
    ]
    if len(eligible) < needed:
        return False, (
            f"needs {needed} more object(s) for {component.description or component.kind.value}, "
            f"found {len(eligible)} eligible"
        )
    return True, None


def _cost_affordability(
    game: Any,
    payer: str,
    total: TotalCost,
    candidate_scan: list[_ScannedCandidate],
    *,
    spend: ManaSpend | None = None,
) -> tuple[Affordability, str | None, tuple[ManaPlanEntry, ...]]:
    """The combined affordability of a `TotalCost`'s mana and every
    non-mana component, worst answer wins (`NO` over `UNKNOWN` over `YES`),
    every reason kept rather than only the first - plus the mana half's own
    tap plan, ready for `Action.pays_with`.

    The plan is dropped whenever a component drags the combined verdict off
    `YES`: the mana would indeed be payable, but the action as a whole is not,
    and reporting how a cost that is not going to be paid would have been paid
    is a plan for something that never happens. `Action.pays_with`'s two gates
    are exactly this and the "has a mana cost at all" one below."""
    status, reason, plan = _mana_affordability(game, payer, total.mana, spend, candidate_scan)
    reasons = [reason] if reason else []
    for component in total.components:
        ok, component_reason = _component_affordability(game, payer, component)
        if ok is False:
            status = Affordability.NO
        elif ok is None and status is not Affordability.NO:
            status = Affordability.UNKNOWN
        if component_reason:
            reasons.append(component_reason)
    return (
        status,
        ("; ".join(reasons) if reasons else None),
        _pays_with(game, payer, total, status, plan, candidate_scan),
    )


def _pays_with(
    game: Any,
    payer: str,
    total: TotalCost,
    affordable: Affordability,
    plan: TapPlan | None,
    candidate_scan: list[_ScannedCandidate],
) -> tuple[ManaPlanEntry, ...]:
    """`plan` in the shape `Action.pays_with` records, or `()`.

    The two gates its docstring names are applied here and nowhere else: the
    action has to owe mana at all (`total.mana.symbols` - the same test
    `_cost_strings` uses to decide whether `Action.mana_cost` is even set),
    and the engine has to have said the whole cost is payable. A plan for an
    unaffordable action would be a plan for something that cannot happen.

    `mana_ability_index` supplies each entry's ability index, reading it back
    off the same hoisted `candidate_scan` every plan entry was solved out of -
    so the number reported is the ability the solver chose, and costs no
    further board survey per entry.
    """
    if affordable is not Affordability.YES or not total.mana.symbols or not plan:
        return ()
    return tuple(
        ManaPlanEntry(
            card_id=source.id,
            name=source.name,
            ability_index=mana_ability_index(
                source,
                colors,
                restriction,
                game=game,
                payer=payer,
                candidate_scan=candidate_scan,
            ),
            adds="".join(color.value for color in colors),
            restriction=restriction.text if restriction is not None else None,
        )
        for source, colors, restriction in plan
    )


def _cost_strings(total: TotalCost) -> tuple[str | None, str | None]:
    """`(cost, mana_cost)` the way `Action` wants them - see its own
    docstring for why this is a string and never the `TotalCost` object."""
    cost = None if total.is_free else str(total)
    mana_cost = str(total.mana) if total.mana.symbols else None
    return cost, mana_cost


# ---------------------------------------------------------------------------
# Casting: one Action per cast option (CR 601.2), never one per card. CR
# 702.47a's splice rides along on every cast option a matching spell has
# (Action.splice_options) rather than being a further cast option of its
# own - CR 702.47b lets more than one splice card apply to the same cast at
# once, so it is a candidate pool, the same treatment Action.modes already
# gives a modal spell's bullets.
# ---------------------------------------------------------------------------


def _widen_for_object_costs(
    game: Any, player: str, card: CardState, affordable: Affordability, reason: str | None
) -> tuple[Affordability, str | None]:
    """Convoke (CR 702.51a), delve (CR 702.66a), improvise (CR 702.126a) and
    crew (CR 702.122a) all pay part of a cost by spending objects rather than
    mana - `_cost_affordability` only ever asked `could_pay_mana_cost`/
    `CostComponent.why_not`, neither of which knows a tapped creature, an
    exiled graveyard card, or a tapped artifact could have covered part of
    what looked unpayable. Never used to *narrow* a `NO` into a `YES` (this
    function does not replicate `machines/objects_as_costs.py`'s own
    reduction arithmetic - that would be reimplementing the machine, not
    reading it), only to say the honest thing instead of a wrong one: a `NO`
    in front of a real convoke/delve/improvise/crew offer becomes `UNKNOWN`,
    naming which offer this check did not evaluate.
    """
    if affordable is not Affordability.NO:
        return affordable, reason
    offers = game.object_cost_offers(card, player)
    if not offers:
        return affordable, reason
    names = "/".join(sorted(offers))
    extra = f"{names} could reduce this cost and is not evaluated by this affordability check"
    return Affordability.UNKNOWN, f"{reason}; {extra}" if reason else extra


def _target_candidates(
    game: Any, player: str, source: CardState, profile: Any, *, source_is_spell: bool
) -> list[tuple[Any, list[Any]]]:
    """Each requirement of `profile` with every object and player it could
    legally name right now (CR 601.2c, and CR 602.2b for an activation).

    The per-target half of `TargetingProfile.check`: `TargetRequirement.
    rejects`, plus CR 702.16b's protection refusal when the profile knows its
    source card. CR 115.5 makes a spell an illegal target for itself, so a
    cast leaves its own card out; an activated ability is a different object
    from its source, so a permanent may be a candidate for its own ability
    unless the phrase says "other" (`excludes_source`, checked by `rejects`).
    """
    if not profile.understood or not profile.requirements:
        return []
    pool = game.targetable_objects()
    source_card = getattr(profile, "source_card", None)
    refusal_of = getattr(game, "protection_refusal", None) if source_card is not None else None
    found: list[tuple[Any, list[Any]]] = []
    for requirement in profile.requirements:
        legal = [
            thing
            for thing in pool
            if not (source_is_spell and thing is source)
            and requirement.rejects(thing, player, game, source.id) is None
            and (refusal_of is None or refusal_of(thing, source_card) is None)
        ]
        found.append((requirement, legal))
    return found


def _slots_from(found: list[tuple[Any, list[Any]]]) -> tuple[TargetSlot, ...]:
    """`Action.target_slots` from `_target_candidates`' answer: each
    requirement's phrase, bounds and current candidates, as ids and usernames
    only."""
    return tuple(
        TargetSlot(
            phrase=requirement.phrase,
            minimum=requirement.minimum,
            maximum=requirement.maximum,
            candidates=tuple(thing.id for thing in legal if not isinstance(thing, Player)),
            player_candidates=tuple(thing.username for thing in legal if isinstance(thing, Player)),
        )
        for requirement, legal in found
    )


def _target_slots(
    game: Any, player: str, source: CardState, profile: Any, *, source_is_spell: bool
) -> tuple[TargetSlot, ...]:
    """`Action.target_slots` for one announcement of `source`."""
    return _slots_from(
        _target_candidates(game, player, source, profile, source_is_spell=source_is_spell)
    )


def _cast_action(
    game: Any,
    player: str,
    card: CardState,
    *,
    rule: str,
    keyword: str | None,
    alternative_cost: str | None,
    total: TotalCost,
    candidate_scan: list[_ScannedCandidate],
    spell_face: str | None = None,
    splice_options: tuple[SpliceOption, ...] = (),
) -> Action:
    modal = modal_profile(card.card)
    modes = tuple(mode.text for mode in modal.modes) if modal is not None else ()
    x_range = (0, None) if "{X}" in (card.card.mana_cost or "") and modal is None else None
    # CR 709.3b/715.3b: the row is about one face, so the phrase it reports
    # has to be that face's own. `announcement_profile` took no face and fell
    # through to `targeting_profile(card)`, which reads the *front* half - so
    # the Tear row of Wear // Tear advertised Wear's "target artifact".
    profile = game.announcement_profile(card, spell_face=spell_face)
    target_slots = _target_slots(game, player, card, profile, source_is_spell=True)
    # CR 106.6 read against the zone this cast would start from - the card has
    # not moved yet here (CR 601.2a happens when the cast is actually
    # announced), so `card.zone` is that zone and is the same answer
    # `from_zone` below reports.
    spend = ManaSpend.casting(card.card, zone=card.zone)
    unpayable = (
        None if alternative_cost is not None else why_mana_cost_unpayable(card.name, total.mana)
    )
    pays_with: tuple[ManaPlanEntry, ...] = ()
    if x_range is not None:
        affordable, reason = Affordability.UNKNOWN, "X has not been announced yet (CR 107.3a)"
    elif unpayable is not None:
        # CR 118.6: a card with no mana symbols at all (Living End, Ancestral
        # Vision) has an unpayable cost, and CR 118.6 itself is explicit that
        # attempting to *pay* one is illegal - `Game.cast` would refuse with
        # this identical reason (`why_mana_cost_unpayable`, shared with
        # `Casting._refuse_unless_mana_cost_payable`), so this is `NO`, never
        # `YES` from a naive "nothing owed" reading of an empty `ManaCost`.
        affordable, reason = Affordability.NO, unpayable
    else:
        affordable, reason, pays_with = _cost_affordability(
            game, player, total, candidate_scan, spend=spend
        )
        affordable, reason = _widen_for_object_costs(game, player, card, affordable, reason)
    cost_str, mana_cost_str = _cost_strings(total)
    return Action(
        kind=ActionKind.CAST,
        player=player,
        rule=rule,
        card_id=card.id,
        from_zone=card.zone,
        keyword=keyword,
        alternative_cost=alternative_cost,
        spell_face=spell_face,
        cost=cost_str,
        mana_cost=mana_cost_str,
        affordable=affordable,
        unaffordable_reason=reason,
        pays_with=pays_with,
        target_slots=target_slots,
        modes=modes,
        x_range=x_range,
        splice_options=splice_options,
    )


#: CR 300.1's six other card types - every one a card could actually be cast
#: as a spell under (CR 601.2a: "spells are... on the stack", and a land is
#: never on the stack, CR 305.1). A card whose whole type line is `{LAND}`
#: has no such type and so is never a cast candidate at all, MDFC land faces
#: included (`Card.types` reads the *front* face, which is what makes an
#: ordinary land-producing MDFC like Turntimber, Serpentine Deep correctly
#: pass this check on its castable front). `casting.py`'s own `Casting` now
#: refuses a land outright too (`why_cannot_cast_a_land`, CR 305.1: "the land
#: doesn't go on the stack, it is never a spell") - this is no longer the
#: only guard, just the cheap early one that skips asking `why_cannot_cast_
#: from`/`why_cannot_cast_now` about a card that was never going to pass
#: anyway.
_CASTABLE_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.PLANESWALKER, Type.SORCERY}
) | frozenset({Type.INSTANT})


def _why_cannot_cast_face(
    game: Any, player: str, card: CardState, face_name: str | None
) -> str | None:
    """Both of CR 601.3's per-face questions as one, for one enumerated row,
    or None if this face may be cast right now.

    CR 601.3: "A player can begin to cast a spell only if a rule or effect
    allows that player to cast it and no rule or effect prohibits that player
    from casting it." CR 117.1a's timing (`why_cannot_cast_now`) and CR 611.1's
    rules-modifying prohibitions (`why_cannot_cast_restriction`) are the two
    halves of that, and both read card types - which CR 601.3e makes a read of
    the *chosen* face's characteristics, not the printing's ("These
    alternative characteristics replace the object's characteristics for this
    determination"), with CR 709.3a and CR 715.3a as the two instances.

    Bundled into one function because every call site needs both and because
    asking them together is what stops one from being hoisted above a per-face
    loop while the other stays inside it. Both used to sit above the loop over
    `_base_cost_options`, so one answer - the front face's - was reported for
    every row: both halves of Repudiate // Replicate (`Instant // Sorcery`)
    were offered during an upkeep step, neither half of Incubation //
    Incongruity (`Sorcery // Instant`) was offered at all, and
    `spell_face=Stomp` was offered while "your opponents can't cast
    noncreature spells this turn" was live.

    `face_name=None` is "no face named", which is every single-faced card, an
    adventurer card's own creature half, and every option that enumerates no
    faces at all - the same value `Action.spell_face` carries for those rows.
    """
    return why_cannot_cast_now(card, player, game, face=face_name) or why_cannot_cast_restriction(
        card, player, game, face=face_name
    )


def _base_cost_options(card: Card) -> list[tuple[str | None, ManaCost]]:
    """Every face this card could announce a plain cast for (CR 709.3's
    split-card choice, CR 715.3's Adventure), as `(face name to record via
    `spell_face`, or None for the plain front-face cast, that face's own
    mana cost)`.

    A split card's `card.mana_cost` is both halves joined by `" // "` -
    `Wear // Tear` is `"{1}{R} // {W}"` - and `ManaCost.parse` reads a split
    string as the two halves' *combined* cost (CR 709.4b's own reading,
    correct for a card sitting anywhere off the stack), not what casting
    either half alone costs (CR 709.3b: "while it's on the stack, a split
    card has only the characteristics of the chosen half"). Reading each
    face's own `mana_cost` instead is what `Casting.base_cost` already does
    once a half has been chosen; this is the same read before any `Casting`
    exists, for every half at once.

    An Adventure card's front face (the creature) is cast the ordinary way -
    `Casting.base_cost` falls back to `card_faces[0]` for it, since the
    top-level `mana_cost` is the same joined string - and its Adventure half
    (`adventure_face`) is the second option, recorded the way `Casting.
    cast_as_adventure` records it.
    """
    faces = card.card_faces or []
    if card.layout is Layout.SPLIT and faces:
        return [(face.name, ManaCost.parse(face.mana_cost or "")) for face in faces]
    if card.layout is Layout.ADVENTURE and faces:
        options: list[tuple[str | None, ManaCost]] = [
            (None, ManaCost.parse(faces[0].mana_cost or ""))
        ]
        inset = adventure_face(card)
        if inset is not None:
            options.append((inset.name, ManaCost.parse(inset.mana_cost or "")))
        return options
    return [(None, ManaCost.parse(card.mana_cost or ""))]


def _splice_options_for(game: Any, player: str, card: CardState) -> tuple[SpliceOption, ...]:
    """CR 702.47a's splice pool for casting `card` - every card in `player`'s
    own hand whose splice ability could be revealed onto it, read straight
    off `casting.splice_candidates` rather than reproducing its quality-
    matching and additional-cost arithmetic here a second time. The same
    pool applies to every cast option this card offers (pitch cost, keyword,
    face) - CR 702.47a's "as you cast a [quality] spell" is not conditioned
    on which cost path paid for that cast."""
    return tuple(
        SpliceOption(card_id=candidate.card.id, cost=str(candidate.cost))
        for candidate in splice_candidates(game, card, player)
    )


def _permission_cast_actions(
    game: Any,
    player: str,
    card: CardState,
    candidate_scan: list[_ScannedCandidate],
    splice_options: tuple[SpliceOption, ...] = (),
) -> list[Action]:
    """CAST under a live `PlayPermission` (CR 601.3) naming this exact
    object - cascade's hit, Ugin's exiled card, Wrenn's Resolve's Bolt.

    None of `keyword_cast_options`/`marker_cast_options`/`granted_cast_
    options` ever see one of these: all three read a card's or a permanent's
    own *printed* text (CR 610.5, CR 611.3d), never a resolving ability's
    one-shot grant to one specific object. `why_cannot_cast_from` already
    treats a usable permission as sufficient reason casting from this zone
    is allowed at all (`usable_play_permission`), which is exactly why the
    zone-HAND branch above never reaches this case - a bare permission is in
    none of the collections it enumerates.
    """
    actions: list[Action] = []
    for permission in play_permissions_on(game, card):
        # `PlayPermission.why_not` is the sole judge of whether a CAST
        # request is covered - `PlayAction.PLAY` is the *wider* grant
        # (CR 601.1a: it reaches the land drop too), so a permission handed
        # out as PLAY (Wrenn's Resolve, Ugin) still covers a cast; only a
        # permission granted as plain CAST would refuse a PLAY request, the
        # other way round.
        if permission.why_not(card, player, game, action=PlayAction.CAST) is not None:
            continue
        if permission.pays_mana_cost:
            for face_name, mana in _base_cost_options(card.card):
                # CR 709.3a/715.3a: both of CR 601.3's questions belong to the
                # *named* face - see the plain-hand branch in `_cast_actions`
                # for what the face-blind versions of these calls reported.
                if _why_cannot_cast_face(game, player, card, face_name) is not None:
                    continue
                actions.append(
                    _cast_action(
                        game,
                        player,
                        card,
                        rule=permission.rule,
                        keyword=None,
                        alternative_cost=None,
                        total=TotalCost.of(mana),
                        candidate_scan=candidate_scan,
                        spell_face=face_name,
                        splice_options=splice_options,
                    )
                )
        elif _why_cannot_cast_face(game, player, card, None) is None:
            actions.append(
                _cast_action(
                    game,
                    player,
                    card,
                    rule=permission.rule,
                    keyword=None,
                    alternative_cost=permission.source_name,
                    total=TotalCost(),
                    candidate_scan=candidate_scan,
                    splice_options=splice_options,
                )
            )
    return actions


def _cast_actions(
    game: Any, player: str, card: CardState, candidate_scan: list[_ScannedCandidate]
) -> list[Action]:
    if not set(card.card.types) & _CASTABLE_TYPES:
        return []
    if why_cannot_cast_a_land(card) is not None:
        # `_CASTABLE_TYPES` gates on `card.card.types` alone, so a land that
        # is *also* one of the six other types (Dryad Arbor: land and
        # creature, CR 300.2a) passes it - CR 305.1: "the land doesn't go on
        # the stack, it is never a spell", checked here the same way
        # `Casting.model_post_init` checks it first, ahead of every other
        # refusal. Without this a CAST action was built anyway and its
        # `unaffordable_reason` came from `why_mana_cost_unpayable` ("no mana
        # cost") instead of the real reason `Game.cast` refuses with ("is a
        # land") - the wrong-message failure `why_cannot_cast_a_land`'s own
        # docstring exists to prevent. A land is never a legal cast to
        # attempt in the first place, so this omits the action outright
        # rather than reporting it with any `Affordability` at all.
        return []
    actions: list[Action] = []
    zone = card.zone
    # CR 702.47a's "as you cast a [quality] spell" is not conditioned on
    # which cost path pays for that cast, so the same pool is attached to
    # every cast option below, computed once rather than once per option.
    splice_options = _splice_options_for(game, player, card)

    if zone is Zone.HAND:
        if why_cannot_cast_from(card, player, Zone.HAND, game) is None:
            for face_name, mana in _base_cost_options(card.card):
                # CR 709.3a/715.3a: "only the chosen half is evaluated to see
                # if it can be cast", and CR 601.3e makes that substitution
                # cover CR 117.1a's timing and CR 611.1's prohibitions alike -
                # so both are asked once per face, not once for the card.
                # Asked for the card they read `Card.types`, the *front*
                # face's type line, and measured live that reported both
                # halves of Repudiate // Replicate (`Instant // Sorcery`) as
                # castable during an upkeep step, neither half of Incubation
                # // Incongruity (`Sorcery // Instant`) as castable at all,
                # and `spell_face=Stomp` as castable while "your opponents
                # can't cast noncreature spells this turn" was live.
                if _why_cannot_cast_face(game, player, card, face_name) is not None:
                    continue
                actions.append(
                    _cast_action(
                        game,
                        player,
                        card,
                        rule="CR 601.2",
                        keyword=None,
                        alternative_cost=None,
                        total=TotalCost.of(mana),
                        candidate_scan=candidate_scan,
                        spell_face=face_name,
                        splice_options=splice_options,
                    )
                )
    else:
        actions.extend(_permission_cast_actions(game, player, card, candidate_scan, splice_options))

    keyword_options: list[tuple[str | None, Any]] = [
        (None, option) for option in keyword_cast_options(card.card) + marker_cast_options(card)
    ]
    keyword_options.extend(
        (granted.source_name, granted.option)
        for granted in granted_cast_options(game, card, player, zone)
    )
    for _source_name, option in keyword_options:
        if option.zone is not zone:
            continue
        if option.why_not(card, player, game, origin=zone) is not None:
            continue
        # `option.why_not` judges the option's own shape (right zone, its own
        # per-keyword conditions) but never CR 117.1a's timing - unlike the
        # plain hand branch above (509-513) and `_permission_cast_actions`
        # (464-466), this loop asked only the one question. Verified live:
        # with Grief in bob's hand during *alice's* main phase, this used to
        # report `CAST keyword=Evoke affordable=yes`, while `Game.cast(...,
        # keyword="Evoke")` refuses on timing (`Casting.model_post_init` runs
        # `why_cannot_cast_now`/`why_cannot_cast_restriction` unconditionally,
        # regardless of which keyword or alternative cost pays for the cast).
        # Both CR 601.3 questions are asked per face below wherever this
        # option enumerates faces at all (CR 709.3a/715.3a/601.3e) and once
        # for the card otherwise.
        if option.pays_mana_cost:
            for face_name, mana in _base_cost_options(card.card):
                if _why_cannot_cast_face(game, player, card, face_name) is not None:
                    continue
                actions.append(
                    _cast_action(
                        game,
                        player,
                        card,
                        rule=option.rule,
                        keyword=option.keyword,
                        alternative_cost=None,
                        total=TotalCost.of(mana),
                        candidate_scan=candidate_scan,
                        spell_face=face_name,
                        splice_options=splice_options,
                    )
                )
        elif _why_cannot_cast_face(game, player, card, None) is None:
            total = option.cost if option.cost is not None else TotalCost()
            actions.append(
                _cast_action(
                    game,
                    player,
                    card,
                    rule=option.rule,
                    keyword=option.keyword,
                    alternative_cost=option.keyword,
                    total=total,
                    candidate_scan=candidate_scan,
                    splice_options=splice_options,
                )
            )

    if zone is Zone.HAND:
        for alternative in game.alternative_costs_for(card, player):
            if alternative.source in (
                AlternativeCostSource.KEYWORD,
                AlternativeCostSource.PERMISSION,
            ):
                # KEYWORD-sourced options are already covered above, straight
                # off `keyword_cast_options`/`marker_cast_options`/
                # `granted_cast_options` - asking `alternative_costs_for` for
                # them too would list Evoke, say, twice. PERMISSION options
                # are covered by `_permission_cast_actions` for a card that
                # actually carries one (a hand card practically never does -
                # a `PlayPermission` exists to reach a card the rules would
                # not otherwise let this player cast from where it sits).
                continue
            if not alternative.available:
                continue
            # The identical timing gap the keyword loop above had: a STATIC
            # or PRINTED alternative cost still pays for casting the same
            # card, which is still subject to CR 117.1a's timing rule unless
            # the card itself is exempt (instant, flash, an `immediate`
            # permission) - `alternative.available` never asked either
            # question.
            if _why_cannot_cast_face(game, player, card, None) is not None:
                continue
            # `alternative.cost is None` is a real answer for a STATIC grant
            # (Omniscience: "nothing" is the whole cost, CR 107.3b), not a
            # failure - only `TotalCost()` (free) belongs there, never a
            # skip.
            total = alternative.cost if alternative.cost is not None else TotalCost()
            actions.append(
                _cast_action(
                    game,
                    player,
                    card,
                    rule=alternative.rule,
                    keyword=None,
                    alternative_cost=alternative.description
                    if alternative.source is AlternativeCostSource.PRINTED
                    else alternative.source_name,
                    total=total,
                    candidate_scan=candidate_scan,
                    splice_options=splice_options,
                )
            )
    return actions


# ---------------------------------------------------------------------------
# Land drops (CR 305.1), MDFC land face included (CR 712.12).
# ---------------------------------------------------------------------------


def _land_actions(game: Any, player: str, card: CardState) -> list[Action]:
    """CR 305.1's own land drop, from the hand it names by default, or from
    wherever else a `PlayAction.PLAY` `PlayPermission` reaches - Wrenn's
    Resolve's own exiled Mountain, say. `Game.play_land` already supports
    `PlayAction.PLAY` out of a non-hand zone (`play_permission_for`); this
    used to hard-gate `card.zone is Zone.HAND` and was only ever called over
    `me.hand`, so a land under a live PLAY permission never appeared here at
    all even though playing it would have succeeded.
    """
    if game.why_cannot_play_land(player) is not None:
        return []
    if (
        card.zone is not Zone.HAND
        and game.play_permission_for(card, player, PlayAction.PLAY) is None
    ):
        return []
    actions: list[Action] = []
    if card.card.is_land:
        actions.append(
            Action(
                kind=ActionKind.PLAY_LAND,
                player=player,
                rule="CR 305.1",
                card_id=card.id,
                from_zone=card.zone,
                affordable=Affordability.YES,
            )
        )
    land_face = card.card.land_face
    if land_face is not None:
        actions.append(
            Action(
                kind=ActionKind.PLAY_LAND,
                player=player,
                rule="CR 712.12",
                card_id=card.id,
                from_zone=card.zone,
                land_face=land_face.name,
                affordable=Affordability.YES,
            )
        )
    return actions


# ---------------------------------------------------------------------------
# Bringing a companion into hand (CR 116.2g, CR 702.139).
# ---------------------------------------------------------------------------


def _companion_action(
    game: Any, player: str, candidate_scan: list[_ScannedCandidate]
) -> Action | None:
    me = game.player(player)
    if game.why_cannot_bring_companion_to_hand(player) is not None:
        return None
    assert me.companion_id is not None
    total = TotalCost.of("{3}")
    affordable, reason, pays_with = _cost_affordability(game, player, total, candidate_scan)
    cost_str, mana_cost_str = _cost_strings(total)
    return Action(
        kind=ActionKind.COMPANION,
        player=player,
        rule="CR 116.2g",
        card_id=me.companion_id,
        from_zone=Zone.SIDEBOARD,
        cost=cost_str,
        mana_cost=mana_cost_str,
        affordable=affordable,
        unaffordable_reason=reason,
        pays_with=pays_with,
    )


# ---------------------------------------------------------------------------
# Turning a face-down permanent face up (CR 702.37e).
# ---------------------------------------------------------------------------


def _turn_face_up_action(
    game: Any, player: str, permanent: CardState, candidate_scan: list[_ScannedCandidate]
) -> Action | None:
    if why_cannot_turn_face_up(permanent) is not None:
        return None
    total = turn_face_up_cost(permanent, player) or TotalCost()
    affordable, reason, pays_with = _cost_affordability(game, player, total, candidate_scan)
    cost_str, mana_cost_str = _cost_strings(total)
    return Action(
        kind=ActionKind.TURN_FACE_UP,
        player=player,
        rule="CR 702.37e",
        card_id=permanent.id,
        from_zone=Zone.BATTLEFIELD,
        cost=cost_str,
        mana_cost=mana_cost_str,
        affordable=affordable,
        unaffordable_reason=reason,
        pays_with=pays_with,
    )


# ---------------------------------------------------------------------------
# Suspend, foretell, plot (CR 116.2f/h/k) - `MarkedExile` in `casting.py`.
# ---------------------------------------------------------------------------

_MARKED_EXILE_BUILDERS: tuple[tuple[ActionKind, Any], ...] = (
    (ActionKind.SUSPEND, MarkedExile.suspend),
    (ActionKind.FORETELL, MarkedExile.foretell),
    (ActionKind.PLOT, MarkedExile.plot),
)


def _marked_exile_actions(
    game: Any, player: str, card: CardState, candidate_scan: list[_ScannedCandidate]
) -> list[Action]:
    if card.zone is not Zone.HAND:
        return []
    actions: list[Action] = []
    for kind, builder in _MARKED_EXILE_BUILDERS:
        try:
            marked = builder(game, card, player)
        except ValueError:
            # Not a legal action at all right now - no such keyword, wrong
            # timing, wrong zone. Distinct from an unpayable cost (CR 118.6),
            # which `MarkedExile.suspend`'s own docstring is explicit never
            # blocks the *build* - only affordability, reported below.
            continue
        affordable, reason, pays_with = _cost_affordability(
            game, player, marked.cost, candidate_scan
        )
        cost_str, mana_cost_str = _cost_strings(marked.cost)
        actions.append(
            Action(
                kind=kind,
                player=player,
                rule=marked.rule,
                card_id=card.id,
                from_zone=Zone.HAND,
                cost=cost_str,
                mana_cost=mana_cost_str,
                affordable=affordable,
                unaffordable_reason=reason,
                pays_with=pays_with,
            )
        )
    return actions


# ---------------------------------------------------------------------------
# Dredge (CR 702.52a-b).
# ---------------------------------------------------------------------------


def _dredge_action(game: Any, player: str, card: CardState) -> Action | None:
    if dredge_count(card.card) is None or why_cannot_dredge(game, card, player) is not None:
        return None
    return Action(
        kind=ActionKind.DREDGE,
        player=player,
        rule="CR 702.52a",
        card_id=card.id,
        from_zone=Zone.GRAVEYARD,
        affordable=Affordability.YES,
    )


# ---------------------------------------------------------------------------
# Activated abilities on the battlefield (CR 602), mana abilities included.
# ---------------------------------------------------------------------------


class _ManaDescriptor(NamedTuple):
    """What an `ACTIVATE_MANA` action says about itself beyond its index.

    Built once per ability by `_mana_descriptor` and read by *both* `Action`
    construction sites below - the `Affordability.UNKNOWN` fallback for an
    activation cost this module cannot price, and the priced branch. One
    value read twice, rather than two constructions that could drift: the
    fallback is exactly where a descriptor would otherwise be quietly
    dropped, since an unpriceable mana ability is the one whose text a caller
    can least afford to be guessing at.
    """

    produces: str | None = None
    restriction: str | None = None
    restriction_understood: bool | None = None


_NO_MANA_DESCRIPTOR = _ManaDescriptor()


def _mana_descriptor(ability: Any, permanent: CardState) -> _ManaDescriptor:
    """The three `Action` fields that say what a mana ability *does*.

    See `Action.produces`/`Action.restriction`/`Action.restriction_understood`
    for what each promises. Two calls do the work:

    - `machines/abilities.printed_production` reads the printed "Add ..."
      phrase. Not `ManaAbility.produces()`, which resolves against a board
      this row deliberately does not consult - see `Action.produces`.
    - `machines/cost.spend_restriction(ability.effect, permanent)` reads
      CR 106.6's sentence. That is the same call a real activation makes
      (`Game.activate_ability`), so what an agent is told here and what the
      mana actually carries come from one reading. Not `restriction_for_
      production`, which reverse-infers a restriction from mana already in a
      pool and resolves ambiguity towards *unrestricted* - the wrong
      direction entirely for an offer a caller has yet to accept.

    Every field is `None` for an ability that is not a mana ability, which is
    what keeps a non-mana `Action` carrying nothing at all.
    """
    if getattr(ability, "mana", None) is None:
        return _NO_MANA_DESCRIPTOR
    restriction = spend_restriction(ability.effect, permanent)
    return _ManaDescriptor(
        produces=printed_production(ability.effect),
        restriction=None if restriction is None else restriction.text,
        restriction_understood=None if restriction is None else restriction.understood,
    )


def _battlefield_ability_actions(
    game: Any,
    player: str,
    permanent: CardState,
    candidate_scan: list[_ScannedCandidate],
    board: Any,
) -> list[Action]:
    if permanent.controller != player:
        return []
    actions: list[Action] = []
    for index, ability in enumerate(game.activated_abilities(permanent)):
        if game.why_cannot_activate(permanent, index, player) is not None:
            continue
        is_mana = getattr(ability, "mana", None) is not None
        # `Action` has no field for a `CardState`/live object, so the choice a
        # caller would need to pass to `Game.activate_ability(..., color=...)`
        # has to be named here as plain data - see `Action.color_options`'s
        # own docstring for why an `ACTIVATE_MANA` action was unusable
        # without it (Steam Vents: reported `affordable=YES`, then
        # `activate_ability` refused with "this ability offers [['U'],
        # ['R']]; pass the colour chosen"). `color_choice_count` is the other
        # half of that parameter space: how many of those colours are named,
        # one per mana for "Add N mana in any combination of colors", which
        # the flat pool cannot say by itself.
        color_options = game.mana_color_options(permanent, index, player) if is_mana else ()
        color_choice_count = (
            game.mana_color_choice_count(permanent, index, player) if is_mana else 0
        )
        # What the ability *does*, as plain data, for the same reason
        # `color_options` above is here: `ability_index` alone made Eldrazi
        # Temple's two mana abilities byte-identical rows. Computed once,
        # ahead of the `try`, so both `Action`s below are filled from the one
        # value and cannot drift apart.
        descriptor = _mana_descriptor(ability, permanent)
        # CR 602.2b: an activation announces its targets as a cast does
        # (CR 601.2c). A mana ability never targets (CR 605.1a).
        target_slots = (
            ()
            if is_mana
            else _target_slots(
                game,
                player,
                permanent,
                game.announcement_profile(permanent, ability_index=index),
                source_is_spell=False,
            )
        )
        try:
            total = game.activation_cost(permanent, index, player)
        except ValueError as error:
            # `CostKind.OTHER` cost pieces `machines/cost.cost_component_for_
            # phrase` declines to read - Relic of Progenitus's own "Exile
            # this artifact" - raise here rather than build. CR 118.6:
            # "Attempting to cast a spell or activate an ability that has an
            # unpayable cost is a legal action" - the attempt is still legal
            # even though this enumeration cannot price it, so this reports
            # `Affordability.UNKNOWN` with the engine's own reason instead of
            # letting the exception escape `legal_actions` outright, which
            # used to take every other action - even `PASS_PRIORITY` - down
            # with it. The same treatment `_off_zone_actions` already gives
            # an unbuildable off-battlefield activation.
            actions.append(
                Action(
                    kind=ActionKind.ACTIVATE_MANA if is_mana else ActionKind.ACTIVATE,
                    player=player,
                    rule="CR 602.5",
                    card_id=permanent.id,
                    from_zone=Zone.BATTLEFIELD,
                    ability_index=index,
                    keyword=getattr(ability, "ability_word", None),
                    color_options=color_options,
                    color_choice_count=color_choice_count,
                    produces=descriptor.produces,
                    restriction=descriptor.restriction,
                    restriction_understood=descriptor.restriction_understood,
                    affordable=Affordability.UNKNOWN,
                    unaffordable_reason=str(error),
                    target_slots=target_slots,
                )
            )
            continue
        # CR 106.6's restrictions ("only to activate abilities of creature
        # sources") ask what the source *is*, which CR 613.5 makes the
        # layer-computed answer - a land animated into a creature is a creature
        # source. `ManaSpend.activating` takes either shape (see its
        # `HasCharacteristics` protocol); `permanent.card` here was the printed
        # front face, wrong for a transformed permanent even before layers.
        spend = ManaSpend.activating(board.of(permanent))
        affordable, reason, pays_with = _cost_affordability(
            game, player, total, candidate_scan, spend=spend
        )
        cost_str, mana_cost_str = _cost_strings(total)
        actions.append(
            Action(
                kind=ActionKind.ACTIVATE_MANA if is_mana else ActionKind.ACTIVATE,
                player=player,
                rule="CR 602.5",
                card_id=permanent.id,
                from_zone=Zone.BATTLEFIELD,
                ability_index=index,
                keyword=getattr(ability, "ability_word", None),
                cost=cost_str,
                mana_cost=mana_cost_str,
                color_options=color_options,
                color_choice_count=color_choice_count,
                produces=descriptor.produces,
                restriction=descriptor.restriction,
                restriction_understood=descriptor.restriction_understood,
                affordable=affordable,
                unaffordable_reason=reason,
                pays_with=pays_with,
                target_slots=target_slots,
            )
        )
    return actions


def _equip_action(
    game: Any,
    player: str,
    permanent: CardState,
    candidate_scan: list[_ScannedCandidate],
    board: Any,
) -> Action | None:
    """CR 702.6a's equip, as an `ACTIVATE` row with `keyword="Equip"` and no
    `ability_index`.

    Equip is a keyword ability, so `Game.activated_abilities` has no entry for
    it and `_battlefield_ability_actions` never offered it. A caller takes it
    with `keywords.equip_activation(game, equipment, target, player)`. CR
    115.1e puts its target in the keyword's rule, so the slot is read off
    `EQUIP_EFFECT`. Omitted outside its CR 307.5 sorcery window, the way
    `_battlefield_ability_actions` omits a refused activation.
    """
    if permanent.controller != player or not has_equip(permanent.card):
        return None
    target_slots = _target_slots(
        game, player, permanent, profile_for_text(EQUIP_EFFECT), source_is_spell=False
    )
    try:
        activation = unannounced_equip_activation(game, permanent, player)
    except ValueError as error:
        return Action(
            kind=ActionKind.ACTIVATE,
            player=player,
            rule="CR 702.6a",
            card_id=permanent.id,
            from_zone=Zone.BATTLEFIELD,
            keyword="Equip",
            affordable=Affordability.UNKNOWN,
            unaffordable_reason=str(error),
            target_slots=target_slots,
        )
    if activation.why_not() is not None:
        return None
    affordable, reason, pays_with = _cost_affordability(
        game,
        player,
        activation.cost,
        candidate_scan,
        spend=ManaSpend.activating(board.of(permanent)),
    )
    cost_str, mana_cost_str = _cost_strings(activation.cost)
    return Action(
        kind=ActionKind.ACTIVATE,
        player=player,
        rule=activation.rule,
        card_id=permanent.id,
        from_zone=Zone.BATTLEFIELD,
        keyword=activation.keyword,
        cost=cost_str,
        mana_cost=mana_cost_str,
        affordable=affordable,
        unaffordable_reason=reason,
        pays_with=pays_with,
        target_slots=target_slots,
    )


# ---------------------------------------------------------------------------
# Activated abilities that function off the battlefield (CR 113.6j/113.6m):
# cycling, a channel-style ability, Greater Gargadon.
# ---------------------------------------------------------------------------


def _off_zone_actions(
    game: Any, player: str, card: CardState, candidate_scan: list[_ScannedCandidate]
) -> list[Action]:
    """One `ACTIVATE_OFF_ZONE` per entry in `off_zone_abilities(card.card)` -
    cycling (CR 702.29a) and any printed ability whose own text puts it in a
    zone other than the battlefield (CR 113.6j, CR 113.6m), in the single
    index space `off_zone_activation` reads, so `Action.ability_index` here
    is exactly the number a caller passes back to it (and, through it, to
    `POST .../actions/activate`) - never a second, family-local count a
    caller would have to guess which entry point resolves.
    """
    actions: list[Action] = []
    spend = ManaSpend.activating(card.card)
    for index, entry in enumerate(off_zone_abilities(card.card)):
        # CR 602.2b: announced like any activation. Only a printed line can
        # target; cycling, unearth and transmute spell out untargeted effects.
        found = _target_candidates(
            game,
            player,
            card,
            profile_for_text(entry.ability.text if entry.family == "printed" else ""),
            source_is_spell=False,
        )
        target_slots = _slots_from(found)
        targets = [thing for requirement, legal in found for thing in legal[: requirement.minimum]]
        try:
            activation = off_zone_activation(game, card, player, index, targets=targets or None)
        except ValueError as error:
            # A requirement with too few legal candidates still refuses the
            # build (CR 601.2c), and so does a cost this module cannot read.
            # The activation is real either way (CR 118.6), so it is reported
            # `UNKNOWN` with the engine's own reason rather than dropped.
            actions.append(
                Action(
                    kind=ActionKind.ACTIVATE_OFF_ZONE,
                    player=player,
                    rule=entry.rule,
                    card_id=card.id,
                    from_zone=card.zone,
                    ability_index=index,
                    keyword=entry.keyword,
                    affordable=Affordability.UNKNOWN,
                    target_slots=target_slots,
                    unaffordable_reason=str(error),
                )
            )
            continue
        if activation.why_not() is not None:
            continue
        affordable, reason, pays_with = _cost_affordability(
            game, player, activation.cost, candidate_scan, spend=spend
        )
        cost_str, mana_cost_str = _cost_strings(activation.cost)
        actions.append(
            Action(
                kind=ActionKind.ACTIVATE_OFF_ZONE,
                player=player,
                rule=activation.rule,
                card_id=card.id,
                from_zone=card.zone,
                ability_index=index,
                keyword=entry.keyword,
                cost=cost_str,
                mana_cost=mana_cost_str,
                affordable=affordable,
                unaffordable_reason=reason,
                pays_with=pays_with,
                target_slots=target_slots,
            )
        )
    return actions


# ---------------------------------------------------------------------------
# Combat declarations, one pair at a time (CR 508.1a, CR 509.1a).
# ---------------------------------------------------------------------------


def _attacker_actions(game: Any, player: str) -> list[Action]:
    """One `DECLARE_ATTACKER` per legal `(creature, defender)` pair (CR
    508.1a) - every creature `player` controls that could still attack, not
    only the first: this used to return `[]` outright once any attacker had
    been declared (`game.combat.attacks` non-empty), which is right for a
    creature already attacking but wrong for every other one, since `Game.
    declare_attacker` is a single-attacker entry point and `why_cannot_attack`
    still answers `None` for the rest.
    """
    if (
        game.turn is None
        or game.turn.step is not Step.DECLARE_ATTACKERS
        or game.turn.active_player != player
    ):
        return []
    opponents = [p for p in game.players_in_game if p.username != player]
    if not opponents:
        return []
    opponent_names = {p.username for p in opponents}
    # One computed board for the whole enumeration (`Game.computed_board`
    # recomputes on every call) - both loops below read a permanent's
    # *computed* types (CR 613.5), not `CardState.types`'s printed starting
    # point (CR 613.1), so a layer-4 type change is seen the same way
    # `why_cannot_attack`/`combat_rules.attack_refusal` already sees it.
    board = game.computed_board()
    defenders: list[tuple[str, Any]] = [(p.username, p.username) for p in opponents]
    for permanent in game.battlefield:
        if permanent.controller in opponent_names and (
            set(board.of(permanent).types) & ATTACKABLE_PERMANENT_TYPES
        ):
            defenders.append((str(permanent.id), permanent))
    already_attacking = {attack.attacker_id for attack in game.combat.attacks}
    actions: list[Action] = []
    for creature in game.permanents_controlled_by(player):
        # Computed, not printed: an animated land (Badgermole Cub's
        # earthbend, CR 701.66a) is a creature by CR 613.1d, and
        # `why_cannot_attack` already answers `None` for it - this
        # enumeration must offer the same `DECLARE_ATTACKER` action or the
        # two disagree about what may attack.
        if not board.of(creature).is_creature or creature.id in already_attacking:
            continue
        for label, target in defenders:
            if game.why_cannot_attack(creature, target) is None:
                actions.append(
                    Action(
                        kind=ActionKind.DECLARE_ATTACKER,
                        player=player,
                        rule="CR 508.1a",
                        card_id=creature.id,
                        from_zone=Zone.BATTLEFIELD,
                        defender=label,
                        affordable=Affordability.YES,
                    )
                )
    return actions


def _blocker_actions(game: Any, player: str) -> list[Action]:
    if (
        game.turn is None
        or game.turn.step is not Step.DECLARE_BLOCKERS
        or game.turn.active_player == player
        or game.combat.blockers_declared
        or not game.combat.attacks
    ):
        return []
    actions: list[Action] = []
    attackers = [game.find_by_id(attack.attacker_id) for attack in game.combat.attacks]
    # One computed board for every attacker's inner loop, not one per
    # `permanents_controlled_by` scan - see `_attacker_actions`'s identical
    # reasoning. An animated land can block just as legally as it can attack
    # (`why_cannot_block` already answers `None` for it), so this enumeration
    # has to offer it too.
    board = game.computed_board()
    for attacker in attackers:
        if attacker is None:
            continue
        for creature in game.permanents_controlled_by(player):
            if not board.of(creature).is_creature:
                continue
            if game.why_cannot_block(creature, attacker) is None:
                actions.append(
                    Action(
                        kind=ActionKind.DECLARE_BLOCKER,
                        player=player,
                        rule="CR 509.1a",
                        card_id=creature.id,
                        from_zone=Zone.BATTLEFIELD,
                        attacker_id=attacker.id,
                        affordable=Affordability.YES,
                    )
                )
    return actions


# ---------------------------------------------------------------------------
# Answering an outstanding Decision - see the module docstring.
# ---------------------------------------------------------------------------


def decision_answers(decision: Decision, game: Any = None) -> list[Action]:
    """Every legal answer to `decision`, as `Action`s.

    A boolean-shaped kind (see `_BOOLEAN_DECISION_KINDS`) is enumerated
    outright - `legal_options` already names exactly its legal answers, which
    is what makes this case a true enumeration rather than a parameter-space
    summary. `CHOOSE_A_QUALITY`/`CHOOSE_A_MODE` do the same over `decision.
    options` when there are any to name. Every other kind - a card/target
    subset, a scry/surveil split, a trigger order, an unbounded amount - is
    reported as one `Action` naming the parameter space (`decision_
    candidates`, `x_range`) rather than one `Action` per legal subset or
    permutation, the same treatment `Action.modes`/`Action.x_range` give a
    modal, X-costed spell.

    `DECLARE_ATTACKERS`/`DECLARE_BLOCKERS` are neither: `Decision.kind`'s own
    docstring says the answer is a tuple of `(creature, defender)` pairs, not
    a boolean, so this reuses `_attacker_actions`/`_blocker_actions` - the
    same per-pair enumeration `legal_actions` already offers outside a
    pending decision - plus one `ANSWER_DECISION` naming CR 508.1's/CR
    509.1's own "if any"/"may" floor: declaring nobody, always legal.
    `game` is `None` only when a caller asks about one of these kinds
    without it, which cannot happen through `legal_actions` itself (it
    always has a `Game` on hand) - in that case only "declare nobody" is
    offered, since the per-pair actions have no board to be read off.
    """
    rule = rule_for_kind(decision.kind)

    def build(**fields: Any) -> Action:
        return Action(kind=ActionKind.ANSWER_DECISION, player=decision.player, rule=rule, **fields)

    if decision.kind in (DecisionKind.DECLARE_ATTACKERS, DecisionKind.DECLARE_BLOCKERS):
        pair_actions: list[Action] = []
        if game is not None:
            pair_actions = (
                _attacker_actions(game, decision.player)
                if decision.kind is DecisionKind.DECLARE_ATTACKERS
                else _blocker_actions(game, decision.player)
            )
        nobody_is_legal = not (
            decision.kind is DecisionKind.DECLARE_ATTACKERS
            and game is not None
            and unobeyed_attack_requirement(game, set()) is not None
        )
        nobody = [build(decision_option="declare_nobody")] if nobody_is_legal else []
        return [*pair_actions, *nobody]

    if decision.kind in _BOOLEAN_DECISION_KINDS:
        return [
            build(
                decision_option=str(option).lower(),
                # CR 608.2g / CR 605.3a: paying may activate these mana sources,
                # so the "pay" answer names them for the seat to choose among.
                decision_candidates=(
                    decision.mana_sources
                    if option and decision.kind is DecisionKind.PAY_MANA
                    else ()
                ),
            )
            for option in legal_options(decision)
        ]

    if decision.kind in (DecisionKind.PAY_ENERGY_AMOUNT, DecisionKind.PAY_LIFE_AMOUNT):
        return [build(x_range=(0, decision.amount))]

    if decision.kind is DecisionKind.CHOOSE_A_QUALITY:
        if decision.options:
            return [build(decision_option=option) for option in decision.options]
        # A card name: too large a universe to enumerate,
        # the same "name what is not modelled" treatment CR 116.2's own
        # unmodelled subrules get in this module's docstring.
        return [
            build(
                affordable=Affordability.UNKNOWN,
                unaffordable_reason="a card name choice is not enumerated",
            )
        ]

    if decision.kind is DecisionKind.CHOOSE_A_MODE:
        if decision.options:
            return [build(decision_option=option) for option in decision.options]
        # The same hole `CHOOSE_A_QUALITY` above is guarded against: an
        # empty `options` must never fall through to an empty list while a
        # decision is pending - that is the exact gap this module's own
        # docstring says it exists to eliminate.
        return [
            build(
                affordable=Affordability.UNKNOWN,
                unaffordable_reason="a mode choice with no offered options is not enumerated",
            )
        ]

    if decision.kind is DecisionKind.CHOOSE_CARDS:
        minimum = decision.amount if decision.exact else 0
        return [build(decision_candidates=decision.cards, x_range=(minimum, decision.amount))]

    if decision.kind is DecisionKind.CHOOSE_TARGETS:
        maximum = (
            decision.target_maximum
            if decision.target_maximum is not None
            else len(decision.targets)
        )
        # CR 115.1: "The targets are object(s) and/or player(s)" - a
        # `TargetRef` for a player (`.is_player`) carries a `username` and no
        # `card_id`, so filtering on `card_id is not None` alone silently
        # dropped every player candidate from an "any target"/"target
        # player" question's own pool. `decision_candidates` stays ids-only
        # (cards); `decision_player_candidates` is the other half `Action`
        # had no field for at all.
        card_ids = tuple(target.card_id for target in decision.targets if target.is_card)
        player_names = tuple(target.username for target in decision.targets if target.is_player)
        return [
            build(
                decision_candidates=card_ids,
                decision_player_candidates=player_names,
                x_range=(decision.target_minimum, maximum),
            )
        ]

    if decision.kind is DecisionKind.ASSIGN_COMBAT_DAMAGE:
        # CR 510.1c / 702.19b: one answer naming every legal recipient; the
        # whole division is checked by `Game.ask` (CR 510.1e), not enumerated.
        return [
            build(
                decision_candidates=tuple(t.card_id for t in decision.targets if t.is_card),
                decision_player_candidates=tuple(
                    t.username for t in decision.targets if t.is_player
                ),
                x_range=(decision.amount, decision.amount),
            )
        ]

    if decision.kind is DecisionKind.ORDER_TRIGGERS:
        return [build(decision_candidates=decision.cards)]

    if decision.kind in (DecisionKind.SCRY, DecisionKind.SURVEIL):
        return [build(decision_candidates=decision.cards, x_range=(0, len(decision.cards)))]

    return []  # pragma: no cover - every DecisionKind is handled above


# ---------------------------------------------------------------------------
# The entry point.
# ---------------------------------------------------------------------------


def legal_actions(
    game: Any, player: str, *, pending: PendingDecision | None = None
) -> list[Action]:
    """Every legal action `player` could take right now.

    See the module docstring for what "legal" means here (never gated on
    affordability), what a pending `Decision` does to the answer, and what is
    deliberately not enumerated.

    Mutates nothing a caller can observe through `Game.model_dump_json`:
    every predicate this calls (`why_cannot_*`, `could_pay_mana_cost`,
    `TargetRequirement.rejects`) is already pure, and the one board-scan
    this hoists (`mana_candidate_scan`) is read-only by construction
    (`memory/flow-based-auto-tap-source-grouping.md`). The one exception is
    `Game.computed_board`'s own lazily-populated CR 613.7 timestamp registry
    (`continuous_effects.note`, `entered`): the *first* call against a cold
    `Game` populates that cache the same way any other legality check would
    have, and every call after is a plain cache hit - idempotent, and no
    different from the lazy caching this engine already does elsewhere, but
    real enough that a caller diffing `model_dump_json` before and after a
    cold game's first call will see it move.

    Runs inside `Game.board_snapshot()`, so the whole enumeration shares one
    layered board instead of rebuilding it for every permanent and ability it
    asks about; a caller already holding a scope on this game shares that one.
    """
    with board_snapshot(game):
        return _legal_actions(game, player, pending=pending)


def _legal_actions(
    game: Any, player: str, *, pending: PendingDecision | None = None
) -> list[Action]:
    """`legal_actions`, inside its board snapshot."""
    if game.is_over:
        return []  # CR 104.1: nothing is legal in a game that has ended
    if pending is not None:
        if pending.decision.player != player:
            return []
        return [
            action.model_copy(update={"decision_seq": pending.seq, "rule": pending.rule})
            for action in decision_answers(pending.decision, game)
        ]

    if not game.is_in_game(player):
        return []

    candidate_scan = mana_candidate_scan(game.battlefield, game=game, payer=player)
    actions: list[Action] = [
        Action(
            kind=ActionKind.PASS_PRIORITY,
            player=player,
            rule="CR 117.3d",
            affordable=Affordability.YES,
        ),
        Action(
            kind=ActionKind.CONCEDE, player=player, rule="CR 104.3a", affordable=Affordability.YES
        ),
    ]
    companion_action = _companion_action(game, player, candidate_scan)
    if companion_action is not None:
        actions.append(companion_action)

    me = game.player(player)
    for card in list(me.hand):
        actions.extend(_cast_actions(game, player, card, candidate_scan))
        actions.extend(_land_actions(game, player, card))
        actions.extend(_marked_exile_actions(game, player, card, candidate_scan))
        actions.extend(_off_zone_actions(game, player, card, candidate_scan))
    for card in list(me.graveyard):
        actions.extend(_cast_actions(game, player, card, candidate_scan))
        actions.extend(_land_actions(game, player, card))
        dredge_action = _dredge_action(game, player, card)
        if dredge_action is not None:
            actions.append(dredge_action)
        actions.extend(_off_zone_actions(game, player, card, candidate_scan))
    for card in list(game.shared_zones.get(Zone.EXILE, [])):
        if not isinstance(card, CardState):
            continue
        actions.extend(_cast_actions(game, player, card, candidate_scan))
        actions.extend(_land_actions(game, player, card))
        actions.extend(_off_zone_actions(game, player, card, candidate_scan))

    # One board for the whole battlefield sweep (CR 613.5's answer is the same
    # for every permanent in it): `Game.computed_board` re-runs the entire
    # layer stack per call, so asking it once per permanent would make this
    # enumeration quadratic in the board size.
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(player):
        actions.extend(_battlefield_ability_actions(game, player, permanent, candidate_scan, board))
        equip = _equip_action(game, player, permanent, candidate_scan, board)
        if equip is not None:
            actions.append(equip)
        if not permanent.face_up:
            turn_up = _turn_face_up_action(game, player, permanent, candidate_scan)
            if turn_up is not None:
                actions.append(turn_up)

    actions.extend(_attacker_actions(game, player))
    actions.extend(_blocker_actions(game, player))
    return actions


__all__: Iterable[str] = ["decision_answers", "legal_actions"]

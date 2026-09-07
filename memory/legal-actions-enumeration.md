---
name: legal-actions-enumeration
description: T8c added Game.legal_targets/alternative_costs_for/object_cost_offers and machines/legal_actions.legal_actions - what "legal" means there (never gated on affordability), the one land-type gap found in why_cannot_cast_now, and the two off-battlefield/alternative-cost sources deliberately left out
metadata:
  type: project
---

**2026-09-07.** T8c built the library's second guarantee ("decode any game
state" is `Game`; this is "enumerate the legal actions available to each
player at that point"): `models/action.py` (`Action`, ids only - never a
`CardState`/`Player`/`Card`, per the `CostPayment.tapped_for_mana` and
`KeywordActivation.card` identity bugs `keyword-activation-round-trip-
identity.md` already found), `machines/legal_actions.py` (`legal_actions`,
`decision_answers`), plus two pure `Game` methods (`alternative_costs_for`,
`object_cost_offers`) and one new pair (`Game.legal_targets`/
`Game.targetable_objects`, alongside the existing singular `legal_target`).

**Legality and affordability are answered separately, on purpose.** CR 118.6:
attempting a spell/ability/special action with an unpayable cost is still a
legal action. A `CAST`/`ACTIVATE` is included whenever the *begin* checks
pass, never gated on `could_pay_mana_cost` - that only sets `Action.
affordable`/`unaffordable_reason`. Found live: `why_cannot_cast_now` never
checks that a card actually has a castable type at all - `game.
can_cast_sorcery(caster)` being true (active player's main phase, empty
stack) waves a *land* card straight through every one of `why_cannot_cast_
from`/`why_cannot_cast_now`/`why_cannot_cast_restriction`, and `Casting`'s own
`model_post_init` carries no land guard either. `legal_actions._CASTABLE_
TYPES` filters it directly rather than touching `casting.py` for a pre-
existing gap this task was not asked to fix.

**Hoisting `_auto_tap_candidates` (`cost.py`) needed a split, not just a
cache.** The scan's own board reads (`can_tap_for_mana`, CR 602.5's
`_activation_refused`, `ability.effective`) never touch `payment.spend` -
only the trailing CR 106.6 restriction filter does. Split into `_scan_mana_
candidates` (spend-independent, the expensive half - `Game.computed_board`/
`characteristics_of` underneath it) and `_filter_candidate_scan` (the cheap
spend check), with `mana_candidate_scan(sources, game=, payer=)` as the public
hoist point and `could_pay_mana_cost(..., candidate_scan=...)` threading it
through. Filtering after sorting is safe because the sort key never reads
spend. Measured on a 21-permanent real board (17 lands including Cavern of
Souls, two creatures, six hand spells): 471.8ms -> 147.8ms per `legal_actions`
call (candidate identical both ways). Profiling the *hoisted* path afterward
found a second, larger cost this task's own ask did not cover:
`Game.activated_abilities`/`why_cannot_activate` recompute `computed_board()`
fresh per permanent per ability check (~96% of profiled time on that board) -
`computed_board`'s own docstring says it is deliberately never cached
("continually" - CR 613.5), so caching it even read-only for one enumeration
call is a bigger, separate change; noted, not done here, and the 147.8ms
total is already under the ~200ms bar this task set.

**Two things named rather than modelled**, both explicit in `Game.
alternative_costs_for`'s and `legal_actions`'s own docstrings: CR 118.9's
PERMISSION (`play_permissions_on` - cascade, Ugin) and STATIC (Omniscience)
alternative-cost sources need an in-flight `Casting`'s `origin_zone`/proposal
state that a pure pre-announcement query does not have; and a *targeted*
off-battlefield activation (`keywords.off_battlefield_activation`) raises
inside `TargetingProfile.check` before `.why_not()` is ever reached, because
building the activation announces and checks targets as one step - every
printing this pool models that way (cycling, Channel, Greater Gargadon)
targets nothing, so it is not exercised, but a future targeted one needs
targets threaded into `legal_actions` from somewhere this enumeration does
not have them yet.

**`Game` never carries a pending `Decision`** - it is raised as
`DecisionPending` and held by whichever caller catches it (the api's own
`magic_cards_model_api.decisions.PendingDecision` mailbox is one such
holder), so `legal_actions(game, player, pending=...)` takes it as a
parameter rather than discovering one. While one is outstanding, the answer
for its own `.player` is `decision_answers(pending.decision)` and the answer
for everyone else is `[]` - nothing else in this engine's own execution can
happen until it is answered.

Related: [[keyword-activation-round-trip-identity]],
[[could-pay-mana-cost-predicate]], [[flow-based-auto-tap-source-grouping]],
[[harness-deadlock-defaulted-every-decision]].

**2026-09-07, review-fix pass.** Two of this doc's own deferral reasons above
were factually wrong, not just incomplete - both are now fixed rather than
still deferred:

- **PERMISSION/STATIC alternative costs did not need in-flight `Casting`
  state.** `play_permissions_on` is keyed off the object's own CR 400.7
  identity (`card_id`/`zone_change_stamp`), which `card` already carries
  before any `Casting` exists, and `_static_free_cast_grants` (now the free
  function `casting.static_free_cast_grants(game, caster)`) reads only
  `game.battlefield`/`caster`. Both are ported into `Game.
  alternative_costs_for` verbatim from `Casting.alternative_costs`. This was
  the gap that made a cascade hit or an Omniscience-enabled spell invisible
  to that menu; it no longer is.
- **A targeted off-battlefield activation is in the pool.** Boseiju, Who
  Endures's Channel ("destroy target artifact, enchantment, or nonbasic
  land") targets, and it is a real printing here - the earlier claim that
  "every printing this pool models that way targets nothing" was wrong.
  `legal_actions._off_zone_actions` still has no targets to supply
  `off_battlefield_activation` (`TargetingProfile.check` still raises before
  `.why_not()` is reached), but the `ValueError` is no longer swallowed: the
  activation is reported with `affordable=Affordability.UNKNOWN` and the
  engine's own reason, rather than silently vanishing from the enumeration.

Also found and fixed in the same pass: `CAST` under a live `PlayPermission`
in a non-hand zone produced nothing (`_permission_cast_actions`, new);
`Living End`/`Ancestral Vision`'s blank mana-cost corner (CR 118.6, no mana
symbols at all) was reported `affordable=YES` instead of `NO`
(`why_mana_cost_unpayable`, shared with `Casting._refuse_unless_mana_cost_
payable` so the two can never disagree); `DECLARE_ATTACKERS`/
`DECLARE_BLOCKERS` sat in `_BOOLEAN_DECISION_KINDS` even though their answer
is `(creature, defender)` pairs, not a boolean, which made the per-pair
actions unreachable while one was pending; split cards and Adventure cards
got one `CAST` with a fabricated combined cost (`Wear // Tear`'s `{1}{R} //
{W}` parses to converted mana value 3) instead of one action per face
(`Action.spell_face`, new field); only the first declared attacker was ever
enumerable per turn; `PLAY_LAND` was hard-gated to `Zone.HAND` even though
`Game.play_land` already supports playing from exile/graveyard under a
`PlayAction.PLAY` permission; and, at the actual source rather than
`legal_actions`'s own `_CASTABLE_TYPES` guard, `Casting` never refused a
land outright (CR 305.1: "since the land doesn't go on the stack, it is
never a spell") - `Game.cast(a_land)` used to fail deep inside cost
determination with a CR 118.6 message that implied Suspend would make a land
castable, which is a lie this project's own refusal text cannot afford;
`why_cannot_cast_a_land` now refuses it first, honestly.

**2026-09-07, second review-fix pass: a whole-diff review found seven more
defects, all fixed.** (1) `_battlefield_ability_actions` called `Game.
activation_cost` unguarded - a `CostKind.OTHER` phrase the cost reader
declines (Relic of Progenitus's "Exile this artifact", six other pool cards)
raises `ValueError` and used to escape `legal_actions` entirely, costing the
caller every action including `PASS_PRIORITY`/`CONCEDE`; now caught and
reported `Affordability.UNKNOWN`, the same treatment `_off_zone_actions`
already gave an unbuildable off-battlefield activation. (2) The keyword/
marker/granted cast-option loop and the `alternative_costs_for` loop both
asked only `option.why_not`/`alternative.available`, never CR 117.1a's
timing (`why_cannot_cast_now`/`why_cannot_cast_restriction`) - Grief's Evoke
was offered during the *opponent's* main phase. (3) `_CASTABLE_TYPES` gates
on `card.card.types` alone, so Dryad Arbor (land + creature) passed it and
got a `CAST` action with the wrong refusal text; now `why_cannot_cast_a_land`
is checked in `_cast_actions` too and the card gets no `CAST` action at all.
(4) `ACTIVATE_MANA` for a choice-offering mana ability (49 pool cards: every
shock/fast/painland, Birds of Paradise, Mox Amber, Reflecting Pool) was
reported affordable with no way to actually call `activate_ability` -
`Action.color_options` (new field) plus `Game.mana_color_options` (new
method, mirrors `activate_ability`'s own mana fast path including Mox
Amber's `among_colors` narrowing) close the gap. (5) `CHOOSE_TARGETS`'s
`decision_candidates` silently dropped every player candidate (`TargetRef`
for a player carries `username`, not `card_id`) - `Action.
decision_player_candidates` (new field) is the other half. (6)
`_candidate_pool_for`'s `EXILE` branch read a cost component's zone through
`Player.cards_in` unconditionally, wrong for a shared zone (`Zone.
BATTLEFIELD`/`EXILE`/etc, CR 400.1) - latent in today's pool (every printed
self-referential exile is filled in before this pool is consulted) but a
real bug: an always-empty pool plus a spurious `zones` key added as a side
effect. (7) `Game.targetable_objects` called `player.cards_in(Zone.
BATTLEFIELD)`/`.cards_in(Zone.EXILE)` for every player - both shared zones,
never in `Player.zones` - permanently adding two empty keys per player as a
side effect of a read-only query; fixed by walking only `Zone.GRAVEYARD` per
player (battlefield/exile are already walked once via `shared_zones`).
`test_legal_actions_mutates_nothing`'s own warming call (`legal_actions`
before the snapshot) could never have caught (7), since the mutation would
already be baked into the "before" snapshot - a new `test_targetable_
objects_mutates_nothing` snapshots before any call at all instead.

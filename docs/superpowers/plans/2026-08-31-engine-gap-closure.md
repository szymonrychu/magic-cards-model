# Engine gap closure - prioritised implementation plan

Date: 2026-08-31. Status: **plan only, nothing implemented, no source file changed.**

Inputs: the 109 `xfail` scenarios in the current tree (`uv run pytest -rx -q`),
the 19 deck-gap reports in `docs/deck-gaps/`, and two mid-flight corrections
from the coordinator (the `devoted combo` and `grinding cam` measurements).
Every claim below was **re-measured against the current tree** with
`effect_for` / `trigger_effect_for` / `activated_effect_for`,
`parse_mana_abilities`, `parse_replacement_effects`, `replacements_of`,
`layers.parsed_layer_effects`, `layers.looks_like_unparsed_layer_effect` and
`sweep_pool.classify_card`. Where a report turned out to be wrong, it is named
in [What the gap reports got wrong](#what-the-gap-reports-got-wrong).

---

## One-screen summary

| Number | Value |
|---|---|
| `xfail` scenarios in the tree | **109** (not 108) |
| Of those, xfails whose stated reason is now **stale** | 4 (see below) |
| Xfails closed by the top five clusters | **51** |
| Xfails closed by all 20 clusters | **107** (2 are permanent no-ops) |
| Real Modern archetypes measured | 19 |
| Archetypes that go from dead to functional | **18 of 19** |
| Waves | 3 |
| Tasks | 32, each owning exactly one source file within its wave |

**Top five clusters by xfail leverage:**

| Rank | Cluster | Xfails | Owning file | Effort |
|---|---|---|---|---|
| 1 | C6 Spell/ability text-parser shapes | 12 | `machines/effects.py` | parser shapes (split across 3 waves) |
| 2 | C5 Replacement-effect application and registry | 11 | `machines/replacement.py` | new parser shapes + registry |
| 3 | C3 Continuous-effect (layer) vocabulary | 10 | `machines/layers.py` | text-keying + vocabulary |
| 4 | C4a/b/c Cost determination | 9 | `models/game.py`, `machines/cost.py`, `machines/objects_as_costs.py` | mixed |
| 5 | C12 `CardState` computed characteristics | 9 | `models/card_state.py` | subsystem |

**But xfail count is not the whole leverage story.** Two clusters with small
xfail counts revive more archetypes than any of the five above:

- **C1 anaphoric delayed triggered ability** (2 xfails) revives esper-goryo,
  grixis-reanimator and instant-reanimator - the whole Modern reanimator shell.
- **C0 false greens** (0 xfails, by construction - nothing tests them) is
  ranked **first for execution** because it is the only cluster producing a
  *wrong board state* rather than an absent one, and one of its three members
  lets a player cast off Mox Opal on turn one through the API's own default
  payment path.

Execution order therefore differs from the xfail ranking. See
[Waves](#waves).

### The structural finding that reframes half this plan

An ability paragraph resolves whole or fails closed. That invariant is right,
and it has a consequence nobody had named until this pass:

> **One unreadable clause in a paragraph kills every readable clause beside
> it.**

Goryo's Vengeance is the famous case - "Exile it at the beginning of the next
end step" cannot be built, so the reanimation in sentence one never runs. But
it is not a delayed-trigger phenomenon. Five more confirmed instances, none of
which involves a delayed trigger at all:

| Card | The clause that parses | The clause that kills it |
|---|---|---|
| Geier Reach Sanitarium | "discards a card" | "Each player draws a card" |
| Ashiok, -1 | "mills four cards" | the exile |
| Day's Undoing | "draws seven cards" | three other clauses |
| Metallic Rebuke | "Counter target spell unless its controller pays {3}." | the **Improvise** keyword line above it |
| Lórien Revealed | "Draw three cards." | the **Islandcycling** keyword line below it |

Three consequences for how this plan is read:

1. **Task 1.13's preamble-stripper generalisation is the highest value-per-line
   change in the plan**, because keyword lines are the most common killer and
   the fix is structural rather than per-card.
2. **Every newly-parseable clause has compounding value.** A clause added in
   Wave 2 does not just make its own card work - it un-blocks every other
   clause sharing a paragraph with it. Effort estimates that treat clauses as
   independent will under-count.
3. **The delayed-trigger cluster (Task 1.12) is narrower than "CR 603.7 is
   missing"** - delayed triggers demonstrably work for Summoner's Pact, dash,
   warp, Dalkovan Encampment and Mishra's Bauble. What is missing is the
   *anaphoric* shape. Scope it that way or you will rebuild working code.

---

## Sanity: what the gap reports got wrong

The reports contradict each other and the tree. Everything below was
re-measured today; a cluster built on any of these premises would have been
wasted work.

### Reports that overstate a gap

| Claim | Report | Measured today | Verdict |
|---|---|---|---|
| "Four Eldrazi/utility lands add no mana AT ALL" (assignment brief, from `broodscale-bloodchief.md`) | broodscale | **Eldrazi Temple** parses *both* mana abilities (`{C}` and `{C}{C}`). **Cavern of Souls** parses both, including the any-colour one. **Ugin's Labyrinth** parses a conditional with `imprinted=True`. **Gemstone Caverns** parses a conditional keyed on `counter='luck'`. | **WRONG.** The mana is produced. What is dropped is the CR 106.6 spend restriction and, for Ugin's Labyrinth, `auto_tap` not reading the condition. Only **Sunken Citadel** and **Reflecting Pool** genuinely parse to `[]`. Two mute lands, not four. |
| "Goryo's Vengeance reads; the delayed rider is on the path, noted as covered" | `instant-reanimator.md` | `effect_for("Goryo's Vengeance", ...)` returns **`delayed_notice_only`**; `classify_card` says `notice`. | **WRONG.** `esper-goryo.md` is correct and `instant-reanimator.md` is not. |
| Revolt is an ignored keyword (Fatal Push) | dimir-frog, esper-control, and `sweep_pool.ignored_keywords` itself | `Game.revolt_active_for` and `_parse_revolt_destroy_or_exile_clause` both exist; Fatal Push classifies `handled`. | **WRONG - measurement-tool false positive.** Confirms the coordinator. |
| Undergrowth / Fight have no execution path (Kraul Harpooner, Bridgeworks Battle) | allosaurus-combo | `_parse_undergrowth_pump_and_fight_clause` and `_fight` both exist in `effects.py`. | **Partly wrong.** Kraul Harpooner's shape works. Bridgeworks Battle's *own* pump-then-fight shape is a separate, genuinely unread sentence. |
| Converge is an ignored keyword | esper-goryo, jeskai-aggro, uw-control, hollow-one | Converge is an ability word (CR 207.2c) that `sweep_pool.ABILITY_WORDS` omits; `_parse_converge_exile_by_colors_spent` reads the clause. | **WRONG - measurement-tool false positive.** |
| Sink into Stupor silent | dimir-control | `classify_card` = `handled`, both faces. | **WRONG**, and already contradicted by dimir-frog. |
| Subtlety / Quantum Riddler ETB triggers unmodelled; warp, evoke, channel unmodelled | dimir-control | All confirmed working (`executed_keywords` maps warp and evoke to `casting.py`; Otawara's channel classifies `handled`). | **WRONG**, already contradicted by dimir-frog. |
| Vizier of Remedies, Collector Ouphe, Delighted Halfling, Shang-Chi, Badgermole Cub's earthbend unmodelled | implied by any registry-membership reading | `replacements_of(Vizier of Remedies)` returns 1 live replacement; `game.py:449` and `game.py:6289` name Collector Ouphe; `mana.py:492/553` name Shang-Chi and Delighted Halfling; `abilities.py` names earthbend. | **WRONG.** Confirms the coordinator. |
| "Force of Negation's pitch cost is unread; `keyword_cast_options` is empty; the free mode does not exist" | `scepter chant`, listed as a false green | `cost.alternative_cost_offers(Force of Negation)` returns `[AlternativeCostOffer(phrase='exile a blue card from your hand', requires_not_your_turn=True)]`. `keyword_cast_options` is empty **and that is correct**: the pitch cost is a printed sentence (CR 118.9), not a keyword, so `machines/cost.py` owns it, not `machines/casting.py`. Allosaurus Rider is the control: same empty `keyword_cast_options`, same live offer, and its pitch cast is proven end to end. | **WRONG.** `grinding cam` is right. **Plan no work.** |
| "Mystical Dispute's {2} discount is unread; always three mana" | `scepter chant` | `_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE` matches Mystical Dispute's printed sentence (verified by running the regex against the fixture text today), and `Game.cost_reduction_for` consumes it. | **WRONG.** `belcher` and `devoted combo` are right. **One real caveat, recorded as a risk on Task 1.5:** the branch is gated on a truthy `targets` argument and returns an empty `ManaCost` when a caller passes none. A caller that determines the total cost before announcing targets would see no discount - that is a *caller* defect to check, not the parser gap `scepter chant` reported. |
| Prevention effects are not modelled (xfail on Fog Bank) | the xfail's own reason | `models/game.py` carries a full CR 615 `PreventionShield` with 615.7 / 615.1a / 615.8 / 510.2 shapes, and `parse_replacement_effects(Fog Bank)` returns `prevent_all` with `replacements_of` = 1. | **STALE xfail reason.** The gap is narrower: `machines/combat.py` does not consult it. |
| Triggered abilities are not modelled (xfail on dies triggers) | the xfail's own reason | `TriggerEvent` has 23 members and dies triggers dispatch. | **STALE xfail reason.** |
| Ragavan's trigger is unparsed because `TriggerEvent` has only six members | the xfail's own reason | `TriggerEvent` has 23 members; Ragavan parses with `event=deals_damage` and `classify_card` = `handled`. | **STALE xfail reason.** The real gap is that `machines/combat.py` never *emits* the event. |

### Reports that understate a gap

- `sweep_pool.has_rules_text` returns `False` for **Hollow One, Scion of Draco,
  Grafdigger's Cage, Voice of Victory, Mox Opal, Kaheera, Stormscale Scion,
  Trinisphere, Pithing Needle, Damping Sphere, Soulless Jailer, Harbinger of
  the Seas, Yavimaya, Leyline of the Guildpact, Arena of Glory, Panharmonicon,
  Exotic Orchard, Disruptor Flute, Detective's Phoenix, Lakeside Shack,
  Thought Reflection, Fog Bank, Millikin** - all measured today. Every one of
  those either has an unmodelled static or is a false green.
- `classify_card` reports the best outcome per card, so Territorial Kavu
  (`handled` on its attack trigger, dead CDA), Obsidian Charmaw (`handled` on
  its ETB, dead cost reduction) and Engineered Explosives (`handled` on its
  activation, dead sunburst) all read clean.
- `looks_like_unparsed_layer_effect(static_only=True)` returns `False` for
  **Stormscale Scion**, **Leyline of the Guildpact**, **Kaheera**,
  **Harbinger of the Seas**, **Yavimaya** and **Toph** - measured today. Not
  one of them even produces a `LayerNotice`. They fail silently **open**.
  Three of those six (Stormscale Scion, Kaheera, Harbinger) were each found
  independently by a different deck agent, which is why the detector's
  false-negative case gets its own numbered item in Task 1.2 rather than
  being folded into the layer work: **it is what makes every other layer gap
  invisible**, and until it is fixed no sweep can tell you how many more
  there are.
- `activated_effect_for("Isochron Scepter", 1, ...)` returns `None` and
  **every `_unreadable_*` probe also returns `None`**, so the card's whole
  lock is silent with no notice - measured today. Imprint works (it is an
  ability word, CR 207.2c, so the ETB is an ordinary trigger and
  `Game.card_imprinted_on` finds the card); the activation that would use it
  does not exist. CR 112.1b and CR 707.12 have no representation anywhere.

### The CR citation disputes, settled by lookup

| Dispute | Verified answer |
|---|---|
| Converge | `knowledge_search(type="rules")` returns **no CR entry for converge** - the query surfaces **convoke** instead. Three agents have now left it uncited. If the plan or the code needs to name it: it is an **ability word under CR 207.2c** and nothing more specific may be cited. |
| Starting life total: 103.4 or 119.1? | **Both are correct and textually identical.** CR 103.4: "Each player begins the game with a starting life total of 20." CR 119.1: identical sentence. 103.4 sits in the pregame procedure, 119.1 in the life rules. **The dozen committed tests citing 103.4 for the pregame set-up are right. No correction is owed.** |
| Starting player's first turn: 103.7, 103.8 or 103.8a? | **CR 103.8**: "The starting player takes their first turn." **CR 103.8a**: "In a two-player game, the player who plays first skips the draw step (see rule 504, 'Draw Step') of their first turn." 103.7 is neither. `tests/scenarios/test_starting_a_game.py` should cite **103.8** for taking the first turn and **103.8a** for the skipped draw step. Both correcting agents were right that 103.7 is wrong; use the specific one for whichever assertion the test makes. |
| Revolt, undergrowth, converge | `knowledge_search(type="rules")` returns **no numbered rule** for any of the three. They are ability words under **CR 207.2c**. Leave them uncited. |
| Bare "enters tapped" | **CR 614.1d**: "Continuous effects that read '[This permanent] enters . . .' or '[Objects] enter [the battlefield] . . .' are replacement effects." **CR 614.1c** covers "enters with", "As [this permanent] enters" and "enters as". `machines/replacement.py:141` cites 614.1c for the bare form; that is the known-wrong citation and Task 1.4 fixes it. |

---

## Every CR number verified this session

All looked up with `knowledge_search(type="rules")` in the session that wrote
this file, and quoted from the returned text, not from memory:

101.2, 103.2, 103.2b, 103.4, 103.6, 103.6a, 103.6b, 103.8, 103.8a,
106.1, 106.4a, 106.5, 106.6, 107.3a, 107.3f, 107.3h, 111.3, 111.10, 111.10a,
111.10f, 112.1b, 113.1a, 113.3c, 113.3d, 113.6, 113.6a, 113.6e, 113.6f,
113.6g, 113.9, 118.7, 118.7a, 118.9, 118.9d, 118.14, 119.1, 122.6, 122.7,
122.8, 202.3, 202.3e, 207.2c, 208.1, 208.2a, 208.4b, 302.4, 302.4c,
400.7b, 403.1, 405.6b, 406.5, 406.8, 509.1f, 510.1, 510.1c, 510.1d, 513.2,
601.2d, 601.2e, 601.2f, 601.3, 601.3a, 601.6, 602.5, 603.1, 603.1a, 603.1b,
603.2g, 603.4, 603.5, 603.6d, 603.7, 603.7a, 603.7d, 603.7h, 603.10, 603.12,
604.2, 604.3, 604.3a, 604.5, 605.3c, 605.5, 608.2a, 608.2d, 608.2p, 608.3f,
608.3g, 609.7b, 610.2, 610.5, 611.2, 611.3, 611.3a, 611.3b, 611.3c, 611.3d,
612.4, 613.1a, 613.1b, 613.1c, 613.1d, 613.1e, 613.1f, 613.3, 613.4, 613.4a,
613.4b, 613.7c, 614.1c, 614.1d, 614.4, 614.5, 614.8, 614.12, 614.12a,
614.13a, 614.13b, 614.13c, 614.16, 615.1, 615.2, 615.3, 615.4, 615.7, 615.9,
615.11, 615.12, 616.1c, 616.1f, 700.2, 700.2a, 700.2b, 700.2c, 700.2d,
700.2f, 700.2h, 701.6, 701.6a, 701.7c, 701.16, 701.16a, 701.19, 701.19a,
701.19b, 701.19c, 701.20d, 701.23j, 701.24a, 701.24b, 701.24c, 701.24d,
701.24e, 701.47, 701.47a, 701.47c, 701.67a, 702.16e, 702.21b, 702.42b,
702.44, 702.44a, 702.44b, 702.44c, 702.44d, 702.56, 702.56a, 702.56b,
702.61a, 702.84a, 702.88a, 702.93a, 702.117a, 702.126, 702.126a, 702.126b,
702.131b, 702.136a, 702.138, 702.138a, 702.138b, 702.139, 702.139a, 702.139c,
702.146a, 702.165b, 702.191a, 702.192a, 707.2, 707.4, 707.5, 707.6, 707.9a,
707.9b, 707.10, 707.10d, 707.10e, 707.10f, 707.12, 708.3, 708.10, 116.2g,
122.1c.

`knowledge_search` returned **no numbered rule** for revolt, undergrowth or
converge; per CLAUDE.md those are left uncited rather than guessed at.

---

## The partitioning rule

Fixes are executed by parallel subagents in git worktrees. Today's deck sweep
succeeded because **no agent touched `machines/effects.py`**; that one shared
file would have shredded 20 branches.

**Rule: within a wave, no two tasks touch the same source file.** Each task
below names the single file it owns. `machines/effects.py` is 16 308 lines and
is the natural home for a dozen clusters, so it gets **exactly one owner per
wave** and its work is bundled into that task. The same is true of
`machines/layers.py`, `machines/replacement.py`, `models/game.py`,
`models/card_state.py`, `machines/triggers.py` and `machines/keywords.py`.

Clusters that unavoidably span files are called out explicitly and get an
`owns` / `touches (coordinate)` split. There are four of them:

1. **C1 delayed triggers** - `machines/delayed.py` owns the primitive,
   `machines/effects.py` owns the call site. Split across Wave 1 (delayed.py,
   builds the primitive with a unit test) and Wave 2 (effects.py, wires the
   parser to it).
2. **C4 cost** - `models/game.py` (`cost_reduction_for`),
   `machines/cost.py` (`cost_component_for_phrase`, `auto_tap`),
   `machines/objects_as_costs.py` (improvise). Three genuinely distinct
   owners; three tasks, same wave, no overlap.
3. **C10 copy** - needs a new `machines/copy.py` plus `models/card_state.py`
   plus `machines/layers.py` sublayers. Wave 3, three tasks, ordered.
4. **C14 combat damage events** - `machines/combat.py` emits,
   `machines/triggers.py` matches. Wave 1 (triggers.py adds the matcher),
   Wave 2 (combat.py emits).

---

## Waves

### Wave 1 - 13 tasks, 13 distinct files

Everything here is independently landable and unblocks measurement or a
downstream wave.

| # | Task | Owns |
|---|---|---|
| 1.1 | **False greens (rank 1 for execution)** | `machines/cost.py` |
| 1.2 | Measurement-tool defects | `scripts/sweep_pool.py` |
| 1.3 | Layer effects: key by text, not by name | `machines/layers.py` |
| 1.4 | Replacement: conditional `enters tapped`, draw replacements, CR 614.1d citation | `machines/replacement.py` |
| 1.5 | Cost reduction shapes | `models/game.py` |
| 1.6 | Improvise (and the convoke/delve family it joins) | `machines/objects_as_costs.py` |
| 1.7 | Trigger-event coverage: matchers | `machines/triggers.py` |
| 1.8 | Mana abilities: chosen colour, could-produce, spend restrictions | `machines/abilities.py` |
| 1.9 | Casting restrictions: zone prohibitions, can't-be-countered, per-turn spell count | `machines/casting_restrictions.py` |
| 1.10 | Target predicates | `machines/targeting.py` |
| 1.11 | Player-level state | `models/player.py` |
| 1.12 | Delayed triggered ability: the anaphoric primitive | `machines/delayed.py` |
| 1.13 | **effects.py bundle A** - generalise the preamble stripper; counter-qualifier family; "in a random order" tail | `machines/effects.py` |

### Wave 2 - 11 tasks, 11 distinct files

| # | Task | Owns |
|---|---|---|
| 2.1 | Keyword execution, batch A | `machines/keywords.py` |
| 2.2 | `CardState` computed characteristics | `models/card_state.py` |
| 2.3 | Casting: plain-sentence alternative costs, granted keywords, CR 601.2a | `machines/casting.py` |
| 2.4 | Modes recorded on the object; X threaded to resolution | `machines/modes.py` |
| 2.5 | Decisions during resolution | `machines/decisions.py` |
| 2.6 | Pregame procedure (CR 103.6) | `models/match.py` |
| 2.7 | Turn structure: step skips, "end the turn" | `machines/turn.py` |
| 2.8 | Ante zone | `models/zone.py` |
| 2.9 | Combat: read the computed board; emit combat-damage events; consult prevention | `machines/combat.py` |
| 2.10 | Layer effects: layer 2 control-changing, land animation | `machines/layers.py` |
| 2.11 | **effects.py bundle B** - reanimation, search-into-play, each-player clauses, mass-damage filters, delayed-trigger wiring | `machines/effects.py` |

### Wave 3 - 8 tasks, 8 distinct files

| # | Task | Owns |
|---|---|---|
| 3.1 | Copy subsystem (new module) | `machines/copy.py` (new) |
| 3.2 | Copiable values on the permanent | `models/card_state.py` |
| 3.3 | Layer 1 sublayers 1a/1b | `machines/layers.py` |
| 3.4 | Replacement: copy-on-enter, regeneration, CR 616.1 ordering | `machines/replacement.py` |
| 3.5 | State triggers (CR 603.8) and trigger multiplying | `machines/triggers.py` |
| 3.6 | Keyword execution, batch B (suspend, splice, fuse, bestow, companion, learn) | `machines/keywords.py` |
| 3.7 | APNAP ordering and the legend-rule choice | `machines/decisions.py` |
| 3.8 | **effects.py bundle C** - retargeting, spell exile, transform-all, Nashi-shaped mixed clauses | `machines/effects.py` |

---

## Task detail

Each task states the primitive with its verified CR rule, its leverage (xfail
ids and archetypes), its owning file, effort, regression risk, and the test to
write **first**.

---

### Task 1.1 - False greens: a wrong board state, not a missing one

**Owns:** `machines/cost.py`.
**Effort:** two small fixes plus one regex. **This is the cheapest high-value
task in the plan and should be started first.**

**The primitive:** an activation's own restriction (CR 602.5, "A player can't
begin to activate an ability that's prohibited from being activated") and a
mana ability's own qualifier (CR 106.5, "If an ability would produce one or
more mana of an undefined type, it produces no mana instead") must be honoured
by **every** payment path, not just the naive legality check.

Three measured defects:

1. **Mox Opal.** `why_cannot_activate` enforces metalcraft correctly through
   `game.py::_activation_condition_holds`. `CostPayment.auto_tap`
   (`cost.py:2429`) never asks it, so the default API payment path taps Mox
   Opal with zero artifacts on the battlefield. A split brain between two code
   paths, and the API path is the one the MCP agents and the UI use.
2. **Mox Amber.** Measured today: `parse_mana_abilities` returns
   `any_color=True` over the full WUBRG option set with `conditional=[]`. The
   "among legendary creatures and planeswalkers you control" qualifier is
   dropped entirely, so on an empty board it is an unconditional Black Lotus
   for one. (The coordinator's note said "plus `{C}`"; measured, the option
   set is WUBRG only - the correction stands, the `{C}` does not.)
   CR 106.5 is the rule: with no legendary creature or planeswalker, the type
   is undefined and it should produce **no mana at all**.
3. **Key to the Side-Door.** Its same-name restriction is dropped from the
   discard cost. (Measured: `parse_mana_abilities` returns `[]`, so this is a
   cost-component defect, not a mana defect - it belongs in the same task
   because `cost.py` owns it.)

Also fold in here, from `45c-aggro.md` and re-measured: **Arena of Glory**'s
`ENTERS_TAPPED` with `condition="unless you control a Mountain"` is parsed and
then ignored. That guard is evaluated in `machines/replacement.py`, so it is
**Task 1.4**, not this one.

**Leverage:** 0 xfails - nothing tests these, which is exactly the point.
Archetypes: pinnacle-affinity (Mox Opal is 4-of), any Mox Amber deck.
**Regression risk:** low, but `auto_tap` is on the hot path of every cast in
the suite. Run the full suite, not just the new test.

**Test first:** `tests/scenarios/test_mox_activation_restrictions.py` -
build a board with Mox Opal and zero other artifacts, call the API's own
payment path (not `why_cannot_activate`), and assert the pool stays empty.
Then Mox Amber on an empty board, asserting `parse_mana_abilities` produces
no defined type.

---

### Task 1.2 - Measurement-tool defects

**Owns:** `scripts/sweep_pool.py`.
**Effort:** three targeted changes.

Everything else in this plan is measured through this file, so it lands in
Wave 1 and every later wave re-measures against the fixed tool.

1. **`has_rules_text` skips a permanent's static line** unless
   `_layer_category` recognises the shape. Measured today, it returns `False`
   for 23 cards carrying real unmodelled statics (list in the sanity section).
   Fix: report a permanent's static lines in a distinct fourth bucket
   (`static_unaudited`) rather than folding them into `no_rules_text`, so a
   count can never read as coverage. Static abilities are **CR 604.2** and
   **CR 113.3d**.
2. **`classify_card` reports the best outcome per card.** Territorial Kavu,
   Obsidian Charmaw and Engineered Explosives all read `handled` with a dead
   clause behind. Fix: return per-clause outcomes, and make the card-level
   verdict the **worst** non-trivial one, or emit both.
3. **`looks_like_unparsed_layer_effect` returns `False`** for Stormscale
   Scion's `Other Dragons you control get +1/+1.`, Leyline of the Guildpact,
   Kaheera, Harbinger of the Seas, Yavimaya and Toph. All six fail silently
   **open**. Fix: widen `_LOOKS_LIKE_LAYER_EFFECT_RE` so an anthem and a
   board-wide type grant are near-misses that produce a `LayerNotice`.
4. **`ABILITY_WORDS` omits converge**, which makes a fully-read clause look
   ignored on Prismatic Ending in four reports. Add it. Also audit the
   `IGNORED` keyword table against behaviour: Revolt and Undergrowth are
   confirmed false positives today.

**Leverage:** 0 xfails directly; unblocks honest measurement of all 20
clusters. **Regression risk:** none to the engine (a script), but it will
change every sweep count in `docs/engine-coverage.md`; that document must be
regenerated as part of this task.

**Test first:** `tests/test_sweep_pool.py::test_a_permanent_with_an_unmodelled_static_is_not_reported_as_clean`
- Grafdigger's Cage must not land in `no_rules_text`.

---

### Task 1.3 - Layer effects: key by text, not by card name

**Owns:** `machines/layers.py`.
**Effort:** structural - a text-shape lookup replacing name keys, plus
vocabulary entries.

**The primitive:** a continuous effect generated by a static ability
(**CR 604.2**, **CR 611.3**, **CR 611.3b**: "The effect applies at all times
that the permanent generating it is on the battlefield") must be built from
the *printed sentence*, not from the card's name.

Two independent instances of the same defect, both confirmed today:

- `LAYER_EFFECTS["Dryad of the Ilysian Grove"]` implements "Lands you control
  are every basic land type in addition to their other types" - **CR 613.1d**,
  layer 4. **Leyline of the Guildpact** prints the identical sentence, has no
  row, and `parsed_layer_effects` returns `None` for it. Measured today.
- `layers.py::_blood_moon` implements exactly the shape **Harbinger of the
  Seas** needs ("Nonbasic lands are Islands"), keyed by the literal string
  `"Blood Moon"`. Harbinger gets no row and not even a `LayerNotice`.

Fix: move both to `parsed_layer_effects` as text shapes. Then add the
vocabulary this cluster is missing:

| Shape | CR | Cards |
|---|---|---|
| Anthem over a filtered subset ("Other Dragons you control get +1/+1") | 613.4c via 611.3 | Stormscale Scion, Kaheera |
| Board-wide land-subtype grant, in-addition-to | 613.1d | Yavimaya, Leyline of the Guildpact |
| Board-wide card-type grant ("Nontoken artifacts you control are lands in addition to their other types") | 613.1d | Toph |
| CDA setting P/T from a board count | 604.3, 604.3a, 613.4a | Territorial Kavu (domain), Tarmogoyf |
| Keyword grant vocabulary: **indestructible** is missing ("gains flying until end of turn" parses, "gains indestructible" does not) | 613.1f | Tyvar the Pummeler, Xenagos |
| Team pump whose magnitude is a computed X | 613.4c, 107.3f | Tyvar the Pummeler |
| Conditional per-object keyword grant ("has X if it's [colour]") | 613.1f | Scion of Draco |
| Grant counted as N separate instances | 613.1f, 613.3 | Innkeeper's Talent (two wards) |
| Equipped-creature static bonus | 613.1f, 613.4c | Cori-Steel Cutter |
| Delirium-gated self-static | 613.1f, 613.4c | Dragon's Rage Channeler |
| Dash's haste grant | 613.1f | (keyword-sourced, needs a `LAYER_EFFECTS` producer) |

**Leverage:** 10 xfails - `test_deck_45c_aggro.py::test_leyline_of_the_guildpact_makes_every_land_every_basic_land_type`,
`::test_territorial_kavu_has_power_equal_to_its_domain`,
`judge/test_judge_layers.py::test_two_innkeepers_talents_grant_two_separate_ward_instances`,
`::test_toph_makes_artifacts_lands_and_blood_moon_then_makes_them_mountains`,
`judge/test_judge_mana_abilities.py::test_toph_turning_caged_sun_into_a_land_draws_the_game`,
`judge/test_judge_blood_moon_layers.py::test_hydro_man_becomes_a_land_and_blood_moon_then_applies_to_it`,
`judge/test_judge_names.py::test_animating_mishras_factory_changes_its_types_but_not_its_name`,
`test_dash.py::test_a_dashed_creature_has_haste`,
`judge/test_judge_cost_payment_order.py::test_sacrificing_omnath_before_paying_the_mana_draws_five` (half),
`judge/test_judge_bending.py::test_an_earthbent_land_returns_to_the_earthbender_even_if_someone_else_killed_it` (half).
Archetypes revived: **45c-aggro** (this is the whole colour-fixing and domain
engine), **storm** (Stormscale Scion's anthem), **dimir-frog** (Harbinger),
**uw-control** (Kaheera), **izzet-prowess** (DRC, Cutter), **boros-ponza**
(Kaheera).

**Regression risk: HIGH.** `layers.py` is 3 346 lines and the whole suite
leans on `compute_board`. Two specific hazards: (a) moving a name-keyed row to
a text shape changes *which* permanents generate the effect, so Dryad and
Blood Moon must be pinned by existing tests before the move; (b) widening
`_LOOKS_LIKE_LAYER_EFFECT_RE` (Task 1.2's mirror) can fire false notices on
triggered-ability effect text - `static_only=True` exists exactly to stop
that, and Kraul Harpooner is the canary.

**Test first:** `tests/scenarios/test_layer_effects_are_text_keyed.py` -
assert `parsed_layer_effects` builds an effect for Leyline of the Guildpact's
sentence and for Harbinger of the Seas', **and** that Dryad and Blood Moon
still produce theirs.

---

### Task 1.4 - Replacement effects: conditions, draw replacements, and a wrong citation

**Owns:** `machines/replacement.py`.
**Effort:** condition evaluation + new parser shapes.

**The primitive:** a replacement effect that modifies how a permanent enters
(**CR 614.1c** for "enters with" / "As ... enters" / "enters as", **CR 614.1d**
for the bare "[This permanent] enters ..." form) must have its **condition
evaluated**, not merely parsed; and a draw replacement (**CR 614.5**: "A
replacement effect doesn't invoke itself repeatedly; it gets only one
opportunity to affect an event") must be applied per-effect rather than once
per draw.

Measured today:

- **Arena of Glory** parses `ENTERS_TAPPED` with
  `condition="unless you control a Mountain"` and enters untapped on an empty
  board. Same for **Monumental Henge** ("unless you control a Plains"),
  **Hall of Storm Giants** ("if you control two or more other lands"),
  **Shifting Woodland** ("unless you control a Forest"), **Lakeside Shack**
  ("unless a player has 13 or less life"), **Cori Mountain Monastery**.
  One condition evaluator closes six cards.
- **Quantum Riddler**, **Thought Reflection**, **Consult the Star Charts**,
  **Galvanic Blast**, **Goblin Charbelcher**, **Firebending Lesson**,
  **Ugin's Labyrinth**, **Gemstone Caverns**, **Stubborn Denial** and
  **Fatal Push** all return `kind=unparsed` from
  `parse_replacement_effects` - a fail-closed notice, correct behaviour, and
  ten cards' worth of shapes to add.
- `replacements_of` returns **0** for Ancient Adamantoise, The Darkness
  Crystal, Stridehangar Automaton and Superior Spider-Man - the hand-written
  registry has no rows for them even where the parse succeeds.
- **The citation defect:** `machines/replacement.py:141` cites CR 614.1c for
  the bare "enters tapped" form. Verified today: the bare form is
  **CR 614.1d**. Fix the comment.

**Leverage:** 11 xfails -
`judge/test_judge_entering_replacements.py::test_lakeside_shack_enters_tapped_when_nobody_is_low_enough`,
`::test_the_shack_reads_the_life_total_from_before_the_pools_payment`,
`judge/test_judge_draw_replacements.py::test_a_second_copy_applies_to_the_already_modified_draw`,
`::test_both_of_the_episodes_cards_carry_a_draw_replacement`,
`judge/test_judge_replacement_effects.py::test_ancient_adamantoise_should_catch_damage_aimed_at_its_controller`,
`::test_the_darkness_crystal_should_exile_the_dying_blocker_and_add_two_more_life`,
`::test_umbra_armor_eats_the_destruction_and_the_creature_survives`,
`::test_only_one_destruction_replacer_gets_to_apply`,
`::test_stridehangar_automaton_should_add_an_extra_thopter_to_any_artifact_token_event`,
`test_foretell.py::test_it_enters_with_a_counter_for_each_turn_since_it_was_foretold`,
`tests/test_replacement.py::test_a_player_skips_wording_is_parsed`.
Archetypes: **jeskai-aggro** and **dimir-frog** (Quantum Riddler is a 4-of in
both), **45c-aggro** (Arena of Glory), **uw-control** (Monumental Henge, Hall
of Storm Giants), **broodscale-bloodchief** (Shifting Woodland).

**Regression risk: HIGH.** `replacement.py` is 2 485 lines and owns the
shockland path every deck test drives. Specific hazard: the shocklands'
`condition="you don't"` must keep meaning "the optional payment was declined"
and not be swept into a new board-condition evaluator.

**Test first:** `tests/scenarios/test_conditional_enters_tapped.py` - play
Arena of Glory with no Mountain and assert `tapped is True`; play it with a
Mountain and assert `tapped is False`; then the same for a shockland, to prove
the existing path is untouched.

---

### Task 1.5 - Cost reduction shapes

**Owns:** `models/game.py`.
**Effort:** four new regexes plus one per-turn counter.

**The primitive:** CR 601.2f - "The player determines the total cost of the
spell ... Some effects may increase or reduce the cost to pay." Measured
today, `Game.cost_reduction_for` reads **exactly two** shapes:
`_COSTS_LESS_PER_CARD_TYPE` and `_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE`.
Everything else pays full price.

| Card | Sentence | What it needs |
|---|---|---|
| Hollow One | "costs {2} less to cast for each card you've cycled or discarded this turn" | a per-turn discard/cycle counter on `Game` (there is none today) plus a per-count shape |
| Obsidian Charmaw | "for each land your opponents control that could produce {C}" | a board-count shape, plus "could produce {X}" as a queryable land property (shares the CR 106.6 work in Task 1.8) |
| Scion of Draco, Leyline Binding | "Domain - costs {2} less to cast for each basic land type among lands you control" | a board-count shape over basic land types |
| Gran-Gran | "cost {1} less to cast as long as there are three or more Lesson cards in your graveyard" | a conditional (not per-count) reduction keyed on a zone count |
| Emry | Affinity for artifacts | CR 118.7a's generic-only reduction, keyed to a board count |

Note CR 118.7a: "Effects that reduce a cost by an amount of generic mana affect
only the generic mana component of that cost" - Scion of Draco's `{12}` really
does go to `{0}` at five basic land types.

**Leverage:** 3 xfails -
`test_hollow_one_deck.py::test_hollow_one_is_cheaper_after_a_discard`,
`judge/test_judge_costs.py::test_gran_grans_discount_counts_the_graveyard_after_the_spell_left_it`,
plus the domain half of `test_deck_45c_aggro.py`. Archetypes: **hollow-one**
(this single gap kills the archetype - the deck exists to cast a 4/4 for zero
on turn one), **45c-aggro**, **pinnacle-affinity** (Emry).

**Also audit while you are in here (not a parser gap):** the existing
`_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE` branch is gated on a truthy `targets`
argument and silently returns an empty `ManaCost` when a caller passes none.
The regex itself matches Mystical Dispute (verified today) - one agent
reported the discount as unread and was wrong about the cause, but a caller
that determines the total cost before announcing targets would produce the
same symptom. Confirm every call site passes `Casting.targets`.

**Regression risk:** medium. `models/game.py` is the largest model file and
several other tasks in Wave 1 and 2 want to touch it; it is reserved for this
task in Wave 1 and for Task 3.x work later.

**Test first:** `tests/scenarios/test_hollow_one_deck.py::test_hollow_one_is_cheaper_after_a_discard`
already exists as an `xfail`. Un-`xfail` it as the first act of the task.

---

### Task 1.6 - Improvise

**Owns:** `machines/objects_as_costs.py`.
**Effort:** one new payment option on an existing subsystem.

**The primitive:** **CR 702.126a** - "Improvise is a static ability that
functions while the spell with improvise is on the stack. 'Improvise' means
'For each generic mana in this spell's total cost, you may tap an untapped
artifact you control rather than pay that mana.'" **CR 702.126b**: it is
neither an additional nor an alternative cost and applies only *after* the
total cost is determined - so it must sit downstream of Task 1.5's
`cost_reduction_for`, not inside it.

`machines/objects_as_costs.py` already pays costs with objects (crew, convoke,
delve - per commit `4e4d4bc`). Improvise is the same subsystem with a
different filter. Waterbend (**CR 701.67a**: "Pay [cost]. For each generic
mana in that cost, you may tap an untapped artifact **or creature** you
control rather than pay that mana") is the same shape one step wider and
should land in the same task.

**Leverage:** 2 xfails -
`test_pinnacle_affinity_deck.py::test_improvise_lets_artifacts_pay_the_generic_part_of_a_cost`,
`judge/test_judge_costs.py::test_waterbend_lets_an_untapped_creature_pay_part_of_the_cost`.
Archetypes: **pinnacle-affinity** (improvise *is* the archetype's engine -
without it the deck has no clock), **belcher** (Whir of Invention).

**Regression risk:** low. Isolated subsystem with existing coverage for crew,
convoke and delve to guard against.

**Test first:** `tests/scenarios/test_improvise.py` - cast Metallic Rebuke
`{2}{U}` with two untapped artifacts and one Island; assert the artifacts tap
and the pool is untouched beyond `{U}`.

---

### Task 1.7 - Trigger-event coverage: matchers

**Owns:** `machines/triggers.py`.
**Effort:** new matchers + intervening-if shapes.

**The primitive:** a triggered ability is
"[When/Whenever/At] [trigger condition or event], [effect]" (**CR 603.1**);
an intervening *if* is checked both when the event occurs and again on
resolution (**CR 603.4**, **CR 608.2a**).

Measured today, `TriggerEvent` has **23** members (the xfail claiming six is
stale). What is missing splits three ways:

**(a) Conditions that parse to `event=None`** - measured today:

| Card | Condition | CR |
|---|---|---|
| Basking Broodscale | "Whenever one or more +1/+1 counters are put on this creature" | 122.6, 122.7 |
| Murktide Regent, Hardened Academic | "Whenever an instant or sorcery card leaves your graveyard" | 603.1 |
| Ketramose | "Whenever one or more cards are put into exile from graveyards and/or the battlefield during your turn" | 603.1 |
| Tamiyo | "When you draw your third card in a turn" | 603.1 |
| Wan Shi Tong | "one or more cards are put into a library" | 603.1 |
| Sewer-veillance Cam | "enters **or leaves**" - parses as ETB only, the leaves half is silently dropped | 603.1b |

**(b) Events that exist but are emitted from too few call sites.**
`BECOMES_TARGET` is emitted only from `machines/casting.py:2264` (permanents,
by `Casting`) and `machines/keywords.py:245` (ward), and
`machines/triggers.py:1101` matches only the ward self-referential form. Loki
reports `handled` and never fires. `DEALS_DAMAGE` is parsed on Ragavan but
never emitted from combat - that emitter is **Task 2.9**, the matcher work is
here.

**(c) Intervening-if shapes `intervening_if_holds` cannot read**, which fail
closed and so never trigger even when plainly true: "it has fewer than four
+1/+1 counters on it" (counter-count comparison), "you sacrificed a permanent
this turn" (needs per-turn sacrifice tracking), "if it's the second creature
spell you cast this turn" (Vengevine).

**Leverage:** 7 xfails -
`judge/test_judge_intervening_if.py::test_three_counters_still_triggers_and_puts_the_fourth_on`,
`judge/test_judge_triggers.py::test_the_airship_does_trigger_once_a_permanent_really_was_sacrificed`,
`judge/test_judge_put_into_library.py::test_a_brainstorm_puts_two_cards_into_the_library_and_triggers_once`,
`test_hollow_one_deck.py::test_vengevine_has_a_recursion_effect_to_run`,
`judge/test_judge_dies_triggers.py::test_a_dies_trigger_goes_on_the_stack_when_the_death_actually_happens`
(stale reason - re-verify and likely convert to a passing test),
`judge/test_judge_state_triggers.py` (deferred to Task 3.5),
`judge/test_judge_triggers.py::test_panharmonicon_doubles_the_exile_but_not_the_delayed_counter_trigger`
(deferred to Task 3.5).
Archetypes: **broodscale-bloodchief** (the counters trigger *is* the deck's
engine), **hollow-one** (Vengevine, Marauding Mako, Hardened Academic),
**dimir-frog** (Murktide, Tamiyo), **esper-control** (Ketramose).

**Regression risk:** medium. Widening the matcher risks a *false* trigger,
which is worse than a missing one; every new matcher needs a negative test.

**Test first:** `tests/scenarios/test_counter_placement_triggers.py` - put a
+1/+1 counter on Basking Broodscale via its own adapt and assert exactly one
Eldrazi Spawn is created, and that a second adapt on a creature that already
has a counter creates none.

---

### Task 1.8 - Mana abilities: chosen colour, could-produce, spend restrictions

**Owns:** `machines/abilities.py`.
**Effort:** two new mana-ability shapes plus a restriction field.

**The primitive:** **CR 106.6** - "Some spells or abilities that produce mana
restrict how that mana can be spent, have an additional effect that affects
the spell or ability that mana is spent on, or create a delayed triggered
ability." And **CR 106.5** - an ability producing mana of an undefined type
produces none.

Measured today, only **two** lands genuinely parse to no mana ability at all:

| Card | Measured | What it needs |
|---|---|---|
| **Sunken Citadel** | `parse_mana_abilities` = `[]` | an as-enters colour choice recorded on the permanent (CR 614.1c) and two abilities reading it (`abilities.py` parses only literal `{T}: Add {R}`) |
| **Reflecting Pool** | `[]` | CR 106.7's "could produce" survey over the other lands |

Everything else in the "Eldrazi/utility lands add no mana" claim is **false**:
Eldrazi Temple parses both abilities, Cavern of Souls parses both including
the any-colour one, Ugin's Labyrinth parses `conditional=[imprinted=True]`,
Gemstone Caverns parses `conditional=[counter='luck']`. What those four
actually lack is the **CR 106.6 restriction field** on the produced mana:
"Spend this mana only to cast colorless Eldrazi spells", "only to cast a
creature spell of the chosen type, and that spell can't be countered", "Spend
this mana only to activate abilities of land sources".

Also here: **Exotic Orchard** parses as an *unconditional* any-colour ability
- the "that a land an opponent controls could produce" clause (CR 106.7) is
dropped, so it makes red off an opponent whose only land is a Plains. That is
a **wrong** answer, not a missing one, so it belongs with the false-green
family in spirit; it is filed here because `abilities.py` owns it.

And: Arena of Glory's `{R}, {T}, Exert: Add {R}{R}` rider ("If that mana is
spent on a creature spell, it gains haste") comes back with both `rider=None`
and `unparsed_rider=None` - silently dropped with no notice. CR 106.6's second
clause is exactly this.

**Leverage:** 3 xfails -
`judge/test_judge_mana_could_produce.py::test_the_pool_taps_for_what_an_island_could_produce`,
`::test_the_orchard_makes_nothing_an_opponents_lands_could_not`,
`judge/test_judge_mana_abilities.py::test_caged_sun_adds_an_additional_mana_when_a_land_makes_the_chosen_color`.
Archetypes: **boros-ponza** (Sunken Citadel is load-bearing - its restricted
mana is what pays for the Field of Ruin / Demolition Field / Cori Mountain
activations), **broodscale-bloodchief** (Eldrazi Temple's restriction, Cavern
of Souls' chosen type).

**Regression risk:** medium-high. `parse_mana_abilities` feeds `auto_tap`,
which feeds every cast in the suite. A restriction field that `auto_tap` does
not yet understand must default to *unrestricted* so nothing regresses; the
enforcement lands in Task 1.1's file and must be coordinated across the wave
boundary (declare the field in Wave 1, enforce in Wave 2).

**Test first:** `tests/scenarios/test_mana_spend_restrictions.py` - tap
Eldrazi Temple for `{C}{C}` and assert the pool carries a restriction naming
colorless Eldrazi; assert a Lightning Bolt cannot be paid from it.

---

### Task 1.9 - Casting restrictions: zone prohibitions, can't-be-countered, spell-count

**Owns:** `machines/casting_restrictions.py`.
**Effort:** three new restriction shapes on an existing module.

**The primitive:** **CR 601.3** - "A player can begin to cast a spell only if
a rule or effect allows that player to cast it and no rule or effect prohibits
that player from casting it", with **CR 101.2** giving "can't" precedence over
"may". Zone-scoped prohibitions function everywhere (**CR 113.6f**).

Measured today, `casting_restrictions.py` carries five shapes, all keyed to
literal sentences. Missing:

| Card | Sentence | CR |
|---|---|---|
| **Grafdigger's Cage** | "Creature cards in graveyards and libraries can't enter the battlefield." / "Players can't cast spells from graveyards or libraries." | 601.3, 113.6f |
| **Soulless Jailer** | permanent-card filter, noncreature filter, exile added as an origin zone | same |
| **Voice of Victory** | "Your opponents can't cast spells during your turn." - needs a *live* static (CR 604.2, 611.3a: "isn't 'locked in'") re-read off the battlefield, combining "your opponents", all spells, and a turn-ownership window | 601.3, 604.2, 611.3a |
| **High Noon** | "Each player can't cast more than one spell each turn." The data already exists as `Game.spells_cast_this_turn`; no static reads it | 601.3, 101.2 |
| **Supreme Verdict** | "This spell can't be countered." **CR 113.6g**: "An object's ability that states it can't be countered or can't be copied functions on the stack." Measured today: `_CANT_BE_COUNTERED_LINE_RE` strips the line so the destroy clause parses, and grep for `cant_be_countered` / `uncounterable` / `can_be_countered` over `src/` finds **only a comment** at `replacement.py:1973`. Counterspell would happily counter Supreme Verdict. **This is a false green**, independently confirmed by two agents, and is the reason the card is in a deck that also plays Wrath of the Skies. | 113.6g, 604.5, 701.6a |

**Leverage:** 1 xfail -
`test_esper_control_deck.py::test_grafdiggers_cage_is_a_modelled_static_ability`.
The other four have no test at all, which is precisely why they went unnoticed.
Archetypes: **jeskai-aggro** (Voice of Victory is the deck's single biggest
gap - three maindeck copies of a card whose defining ability is absent),
**uw-control** (Supreme Verdict, High Noon), **esper-control** and
**broodscale-bloodchief** and **belcher** (Grafdigger's Cage).

**Regression risk:** low-medium. A prohibition that fires too broadly makes
legal casts illegal and will fail loudly rather than silently, which is the
right failure mode.

**Test first:** `tests/scenarios/test_cant_be_countered.py` - cast Supreme
Verdict, respond with Counterspell targeting it, assert the announcement is
refused at CR 601.2c and that the Verdict resolves.

---

### Task 1.10 - Target predicates

**Owns:** `machines/targeting.py`.
**Effort:** predicate vocabulary.

**The primitive:** target legality is checked at announcement (CR 601.2c) and
re-checked on resolution (CR 608.2b). Measured today, `machines/targeting.py`
reports `understood=False` for three phrase families:

| Shape | Cards | CR |
|---|---|---|
| Mana-value predicate on a **spell** on the stack | Spell Snare, Stern Scolding, Disrupting Shoal, Drown in the Loch (3 unreadable phrases) | 202.3, 202.3e |
| Bound computed from a zone count ("less than or equal to the number of cards in its controller's graveyard") | Drown in the Loch | 202.3 |
| Ability-word prefix + trailing `if <condition>` | Prismatic Ending's converge clause - the *effect* is read, the targeting is not | 207.2c |
| "controlled by different players" | Run Away Together | 601.2c |
| Protection read on the **target's** text rather than the caster's | Mother of Runes, granted colour protection | 702.16e |

**Leverage:** 4 xfails -
`test_protection.py::test_announcing_a_protected_target_is_refused_as_the_spell_is_cast`,
`::test_a_player_can_have_protection_too` (needs Task 1.11 too),
`test_protection_grants.py::test_granted_color_protection_still_stops_a_same_colored_spell_from_targeting`,
`judge/test_judge_targeting.py::test_run_away_together_refuses_two_creatures_the_same_player_controls`,
`::test_protection_gained_in_response_makes_the_creature_an_illegal_target`.
Archetypes: this is the *targeting* half of the counter-qualifier family whose
*effect* half is Task 1.13 - together they revive **dimir-frog**,
**dimir-control**, **esper-control**, **esper-goryo**, **uw-control**,
**jeskai-aggro**, **izzet-prowess**, **belcher** (Spell Snare is in eight of
the nineteen lists).

**Regression risk:** low. `understood=False` today means "not checked", so
adding a predicate can only tighten legality; the hazard is tightening it
*wrongly* and refusing a legal target.

**Test first:** `tests/scenarios/test_counter_by_mana_value.py` - assert
Spell Snare refuses a mana-value-3 spell at announcement and accepts a
mana-value-2 one.

---

### Task 1.11 - Player-level state

**Owns:** `models/player.py`.
**Effort:** four fields plus their accessors.

**The primitive:** a player is an object continuous effects can modify.
Measured today `Player` has `life`, `gain_life`, `lose_life` and no flag for
any prohibition or history.

| Missing | For | CR |
|---|---|---|
| "can't gain life" prohibition | Screaming Nemesis, Leyline of Punishment | 101.2 (the "can't" precedence) |
| Life *lost* this turn (there is a `life_gained_this_turn` and no counterpart) | Children of Korlis, Kaito's "each opponent who lost life this turn" | 603.1 |
| Exchange primitive ("if the entire exchange can't happen, no part of it occurs") | the life-exchange judge episode | (look up 701.12 before writing the number - not verified in this session) |
| Protection for a *player* with a chosen name | Runed Halo | 702.16e |

**Note for the implementer:** CR 701.12 for exchange was **not looked up in
this session**. Look it up before writing it into code or a docstring; per
CLAUDE.md an unverified number is a defect even if it turns out right.

**Leverage:** 5 xfails -
`judge/test_judge_life_exchange.py::test_a_player_who_cannot_gain_life_does_not_gain_life`,
`::test_the_exchange_is_refused_outright_when_one_half_cannot_happen`,
`judge/test_judge_paying_life.py::test_leyline_of_punishment_stops_only_the_life_gain_half`,
`::test_children_of_korlis_gives_back_the_life_paid_as_well_as_the_damage`,
`test_protection.py::test_a_player_can_have_protection_too`.
Archetypes: **dimir-control** (Kaito's 0 ability).

**Regression risk:** low. Additive fields on a small model.

**Test first:** `tests/scenarios/test_life_gain_prohibition.py` - with Leyline
of Punishment on the battlefield, resolve a lifelink hit and assert life is
unchanged.

---

### Task 1.12 - Delayed triggered ability: the anaphoric primitive

**Owns:** `machines/delayed.py`.
**Touches (Wave 2):** `machines/effects.py` - the call site is Task 2.11.
**Effort:** one new primitive on an existing, working subsystem.

**The primitive:** **CR 603.7a** - "Delayed triggered abilities are created
during the resolution of spells or abilities, as the result of a replacement
effect being applied, or as a result of a static ability"; **CR 610.2** -
"Some one-shot effects create a delayed triggered ability, which instructs a
player to do something later in the game"; **CR 603.7d** - the source is the
spell and the controller is whoever controlled it as it resolved.

**Scope this carefully - delayed triggers are NOT uniformly missing.**
Confirmed working today: Summoner's Pact's pay-or-lose, dash's end-step
return, warp's exile (`delayed.py:287`), Dalkovan Encampment's
`_parse_attack_this_turn_create_tapped_attacking_tokens`, Mishra's Bauble's
rider. What is missing is one narrow shape: **a delayed trigger whose subject
is anaphoric - "it" or "that token" - referring to an object the same
paragraph just moved or created.**

That single shape is why Goryo's Vengeance returns `delayed_notice_only`
(measured today, contradicting `instant-reanimator.md`): the paragraph's third
sentence, "Exile **it** at the beginning of the next end step", cannot be
built, and because an ability paragraph resolves whole or fails closed
(project invariant), the reanimation in sentence one never runs either.

Same shape, same failure: Fire Navy Trebuchet ("Sacrifice **that token** at
the beginning of the next end step"), Ilharg's returned creature, Emperor of
Bones' delayed sacrifice, First Day of Class's "whenever a creature you
control enters **this turn**" (a duration-bounded delayed trigger installed by
an instant that does not survive resolution - CR 603.7b bounds it).

**Leverage:** 2 xfails directly -
`test_esper_goryo_deck.py::test_goryos_vengeance_reanimates_a_legendary_creature`,
`judge/test_judge_triggers.py::test_fire_navy_trebuchet_creates_the_ballistic_boulder_it_will_sacrifice`
- plus one half of
`judge/test_judge_put_onto_the_battlefield_attacking.py::test_purphoros_is_put_in_attacking_and_returns_to_hand_at_end_of_turn`.
**Archetypes: esper-goryo, grixis-reanimator, instant-reanimator** (the whole
Modern reanimator shell is inert without it - this is not a corner case, it is
what those decks do), plus **storm** (First Day of Class, 4 copies, is how the
Dragons get haste; without it the deck storms out a pile of 4/4s that cannot
attack until the following turn).

**Regression risk:** low. Additive on a subsystem with existing coverage; the
existing delayed triggers listed above are the guard.

**Test first:** `tests/test_delayed.py::test_a_delayed_trigger_can_name_the_object_the_effect_just_moved`
- a unit test on `delayed.py` alone, so Wave 1 can land it without the
`effects.py` wiring. The scenario test
(`test_esper_goryo_deck.py::test_goryos_vengeance_reanimates_a_legendary_creature`)
un-`xfail`s in Wave 2.

---

### Task 1.13 - effects.py bundle A

**Owns:** `machines/effects.py`. **Nothing else in Wave 1 touches this file.**
**Effort:** one structural change plus two parser families.

Three items, ordered by value per unit of work.

**A1. Generalise `_strip_non_effect_preamble` (highest value in the whole
plan per line changed).** Measured today: the stripper is a **whitelist** of
~20 per-keyword regexes (`_REPLICATE_LINE_RE`, `_CYCLING_LINE_RE`,
`_FLASHBACK_LINE_RE`, `_SPLICE_LINE_RE`, `_DELVE_LINE_RE`, ...). Because
`_REPLICATE_LINE_RE` exists, Consign to Memory works. Because there is **no
`_IMPROVISE_LINE_RE`**, Metallic Rebuke - whose "Counter target spell unless
its controller pays {3}." parses perfectly on its own - returns `None` for the
whole card, and in play the countered spell just stays on the stack.
**Lórien Revealed** is the same shape via Islandcycling: measured today,
`effect_for("Lórien Revealed", "Draw three cards.")` is handled and
`effect_for` on the printed text is `None`.

The fix is not "add N regexes". It is to recognise a *keyword-ability line*
structurally - a line that `parse_abilities` classified as
`AbilityKind.KEYWORD` - and strip every such line before spell dispatch,
whatever the keyword is. Keyword abilities are **CR 113.3** ability
categories; reminder text is **CR 207.2**.

**A2. The counter-qualifier family.** Measured today, `effects.py` reads three
counter shapes: `_COUNTER_TARGET_SPELL_RE` (one qualifier word from
`_SPELL_QUALIFIER_WORD`, with a trailing `$`), `_COUNTER_UNLESS_PAYS_RE` (no
qualifier slot at all), and `_COUNTER_TARGET_ABILITY_OR_SPELL_RE`. Result:

| Card | Why it is silent |
|---|---|
| Spell Snare | "with mana value 2" is numeric, not one of `_SPELL_QUALIFIER_WORD`'s type/colour words, and the trailing `$` refuses the tail |
| Stern Scolding | "with power or toughness 2 or less" - a disjunction over two printed characteristics of a creature spell |
| Spell Pierce | `_COUNTER_UNLESS_PAYS_RE` has no qualifier slot for "noncreature" |
| Flusterstorm | same, for "instant or sorcery". Half alive: storm executes, so N copies go on the stack and every one resolves doing nothing |
| Metallic Rebuke | see A1 - the clause parses, the preamble kills it |
| Stubborn Denial | conditional counter plus an ability-word-gated upgrade replacing the first sentence's outcome |
| Disrupting Shoal | counter-if-mana-value-X, plus an X-keyed pitch cost `total_cost_for_phrase` cannot read |

The primitive: a counter effect (**CR 701.6a**: "To counter a spell or ability
means to cancel it, removing it from the stack") with **(a)** a qualifier slot
on the unless-pays shape and **(b)** a predicate slot accepting a mana-value
or P/T bound (**CR 202.3e** for a spell's real on-stack mana value with X).
The targeting half is Task 1.10.

**A3. "In a random order" as an accepted tail.** `_PUT_REST_ON_BOTTOM_ANY_ORDER_RE`
matches "in any order" and not "in a random order", so the four-clause
`_merge_look_top_reveal_to_hand_clauses` family rejects the whole run.
Measured today, this kills **Narset, Parter of Veils**, **Monumental Henge**,
**Thundertrap Trainer** and **Atraxa, Grand Unifier** (whose per-card-type
selection is a separate, larger gap - only the tail is in scope here), and
sits behind **Ancient Stirrings**, **Stock Up** and **Planar Genesis**.
One phrase, four dead cards.

**Leverage:** 6 xfails -
`test_deck_45c_aggro.py::test_stubborn_denial_counters_a_noncreature_spell`,
`judge/test_judge_warp_from_exile.py::test_syncopate_exiles_the_countered_warp_spell_without_granting_a_recast`,
plus the four spell-level silences that have deck-test coverage. Archetypes:
**uw-control, jeskai-aggro, dimir-frog, dimir-control, esper-control,
esper-goryo, izzet-prowess, ur-aggro, belcher, pinnacle-affinity** - Spell
Snare alone appears in eight lists, and Metallic Rebuke plus Kappa Cannoneer
are pinnacle-affinity's curve.

**Regression risk:** medium-high for A1, low for A2/A3. Generalising the
preamble stripper changes what text *every* card's spell dispatcher sees. It
must not strip a line `parse_abilities` classified as anything other than
`KEYWORD`, and the full suite is the guard.

**Test first:** `tests/scenarios/test_keyword_lines_do_not_silence_a_spell.py`
- assert `effect_for` on Lórien Revealed's and Metallic Rebuke's *printed*
text returns the same effect it returns for the resolution sentence alone.

---

### Wave 2 tasks

Wave 2 is written at one level less detail; each entry names the primitive,
CR rule, owner, leverage and first test. Full step lists are deferred to the
executing agent, which is the point of the wave boundary - Wave 1's results
will change what Wave 2 needs.

---

**Task 2.1 - Keyword execution, batch A.** Owns `machines/keywords.py`.
Sunburst (**CR 702.44a/b**: counters only when entering from the stack as a
resolving spell and only if coloured mana was spent - so this needs
`Game` to record *which* mana paid, coordinate with Task 1.5's file),
replicate (**CR 702.56a**: a static ability on the stack plus a triggered
copy ability), escape (**CR 702.138a**), amass (**CR 701.47a**), investigate
(**CR 701.16a** creating the **CR 111.10f** Clue token), regenerate
(**CR 701.19a** / **CR 614.8**; note **CR 701.19c** for what "can't be
regenerated" turns off), evoke's sacrifice trigger (**CR 702.74a** - look this
one up, it was not verified this session), cycling as an activated ability
from hand (**CR 702.29a** - likewise unverified here), firebending, airbend.
**Leverage:** 7 xfails (`judge/test_judge_bending.py` x2,
`judge/test_judge_mana_abilities.py::test_firebending_*` x2,
`test_evoke.py`, `test_keyword_cost_forms.py::test_a_card_with_cycling_can_be_cycled`,
plus Engineered Explosives' false green with no test).
**Risk:** medium. **Test first:** Engineered Explosives cast with three
colours of mana enters with three charge counters.

**Task 2.2 - `CardState` computed characteristics.** Owns
`models/card_state.py`. `CardState.power` / `.toughness` are the printed value
plus counters; the layer engine already computes CDAs in 7a
(**CR 604.3**, **CR 613.4a**) and `card_state.py` does not ask it. Also: face-
down in exile (**CR 708.3**), Adventure's on-stack characteristics
(**CR 715.3b** - unverified here, look it up), a new object on returning to a
zone (**CR 400.7** - unverified here, look it up), transform refusing an
instant back face.
**Leverage:** 9 xfails. **Risk:** HIGH - `combat.py` reads these for CR 510.1a
and the whole suite reads them for SBAs.
**Test first:** `test_characteristic_defining_abilities.py::test_the_game_agrees_with_the_layer_engine_about_a_goyfs_power`.

**Task 2.3 - Casting.** Owns `machines/casting.py`. Alternative costs printed
as a plain sentence rather than a keyword (**CR 118.9**; Mindbreak Trap);
keywords *granted* to a spell by another permanent's static ability
(**CR 610.5**: "Some static abilities create one-shot effects that cause
spells a player casts to gain an ability as that player casts them"; Ashling's
granted evoke); a cast permission gated on the origin zone (**CR 113.6f**;
Iroh's granted flashback, Detective's Phoenix's graveyard bestow); and
**CR 601.2a** - the card goes on the stack as the *first* step of proposing a
cast, before costs are determined.
**Leverage:** 6 xfails. **Risk:** HIGH - the 601.2a reordering touches every
cast. **Test first:** `judge/test_judge_illegal_play_win.py::test_announcing_a_cast_moves_the_card_to_the_stack_immediately`.

**Task 2.4 - Modes and X.** Owns `machines/modes.py`. **CR 700.2a**: modes are
chosen as part of casting; nothing records the choice on the object, and
`EFFECTS` is keyed by card name alone. **CR 107.3a**: the announced X is not
exposed to a resolving non-modal spell either. Entwine is **CR 702.42b**.
**Leverage:** 2 xfails (`test_entwine.py`, `test_tokens.py::test_kozileks_command_creates_x_eldrazi_spawn`).
**Risk:** medium. **Test first:** Kozilek's Command with X=2 creates two Spawn.

**Task 2.5 - Decisions during resolution.** Owns `machines/decisions.py`.
**CR 601.2d** (announced division of damage among targets - "the player
announces the division", and it has nowhere to live today), **CR 603.3b**
(a controller orders their own simultaneous triggers - `put_triggers_on_stack`
never asks), **CR 608.2d** (choices made on resolution: the optional mana
payment inside a trigger, "you may pay {B}. If you do, draw a card").
**Leverage:** 3 xfails. **Risk:** low. **Test first:**
`test_damage_division.py::test_the_caster_chooses_how_the_damage_is_divided`.

**Task 2.6 - Pregame procedure.** Owns `models/match.py`. **CR 103.6**:
"Once the mulligan process (see rule 103.5) is complete, the starting player
may take any such actions in any order"; **CR 103.6a** for beginning the game
with a card on the battlefield; **CR 103.6b** for revealing from the opening
hand. Also **CR 103.2b** and **CR 116.2g** for companion.
**Leverage:** 2 xfails (`judge/test_judge_starting_the_game.py`,
`test_broodscale_bloodchief_deck.py::test_gemstone_caverns_can_begin_the_game_on_the_battlefield`).
**Risk:** low-medium. **Test first:** Gemstone Caverns begins on the
battlefield with a luck counter.

**Task 2.7 - Turn structure.** Owns `machines/turn.py`. Step skipping
(**CR 614.10** - unverified here, look it up) for Savor the Moment; the "end
the turn" action (Day's Undoing; **CR 724** - unverified here, look it up).
**Leverage:** 2 xfails (`test_extra_turns.py`, `judge/test_judge_ending_the_turn.py`).
**Risk:** medium.

**Task 2.8 - Ante zone.** Owns `models/zone.py`. **CR 400.1**'s optional
eighth zone (unverified here - look it up before writing the number).
**Leverage:** 2 xfails (`judge/test_judge_ante.py` x2). **Risk:** low.

**Task 2.9 - Combat.** Owns `machines/combat.py`. Three things: `has_keyword`
answers off `state.card.keywords` (the printed Scryfall field) and never
consults `Game.characteristics_of`, so a Role's layer-6 trample grant is
recorded and ignored; combat never emits the `DEALS_DAMAGE` event that
`Ragavan` already parses (matcher work is Task 1.7); and `Game.combat_damage`
deals damage without consulting the CR 615 `PreventionShield` that `game.py`
already implements (Fog Bank).
**Leverage:** 3 xfails (`test_role_tokens.py`, `test_tokens.py::test_ragavan_creates_a_treasure_on_combat_damage`,
`judge/test_judge_combat_damage.py::test_fog_bank_prevents_the_combat_damage_in_both_directions`).
**Risk:** HIGH - combat damage is load-bearing for dozens of scenarios.
**Test first:** `test_role_tokens.py::test_the_granted_trample_reaches_combat_damage`.

**Task 2.10 - Layer effects, round two.** Owns `machines/layers.py`. Layer 2
control-changing (**CR 613.1b**) for Threaten; land animation as a combined
layer 4 + 7b + 6 effect created by a resolving activated ability
(**CR 611.2**) for Hall of Storm Giants and Mishra's Factory.
**Leverage:** 2 xfails. **Risk:** HIGH (same file as Task 1.3 - different
wave, which is why they are separated).

**Task 2.11 - effects.py bundle B.** Owns `machines/effects.py`. Wire the
Task 1.12 delayed primitive into `_spell_effect_or_notice` so Goryo's
Vengeance builds whole. Then: return-from-graveyard-to-battlefield with a
rider (Persist, Unearth); search-by-computed-mana-value into play
(**CR 701.23j**/**CR 701.24b**; Neoform, Eldritch Evolution, Whir of
Invention); each-player fan-out (Field of Ruin, Burning Inquiry, Geier Reach
Sanitarium, Day's Undoing); mass damage with a subset filter (Rough // Tumble,
Whipflare, End the Festivities); Charbelcher's reveal-until; the chained
gain/draw/discard sequence (Faithful Mending); mill-then-linked-selection
(Fallaji Archaeologist, Nashi); reveal-N-then-one-per-card-type (Atraxa,
**CR 111.3** for what the effect defines).
**Leverage:** 6 xfails plus the archetype revivals for **belcher**,
**allosaurus-combo**, **grixis-reanimator**, **boros-ponza**, **hollow-one**,
**uw-control**. **Risk:** medium.

---

### Wave 3 tasks

**Task 3.1 - Copy subsystem.** Owns a new `machines/copy.py`. **CR 707.2**:
"the copy acquires the copiable values of the original object's characteristics
and, for an object on the stack, choices made when casting or activating it";
**CR 707.5** for entering as a copy; **CR 707.9a** for "except it has ...";
**CR 707.10** for copying a spell or ability; **CR 707.12** for casting a copy
of a card. **Leverage:** 8 xfails. **Risk:** low for a new file, high for its
consumers.

**Task 3.2 - Copiable values on the permanent.** Owns `models/card_state.py`.

**Task 3.3 - Layer 1 sublayers.** Owns `machines/layers.py`. **CR 613.1a**
(layer 1: rules and effects that modify copiable values) and the 1a/1b split
(**CR 613.2** - unverified here, look it up). **Risk:** HIGH.

**Task 3.4 - Replacement, round two.** Owns `machines/replacement.py`.
Copy-on-enter (**CR 616.1c**), regeneration (**CR 701.19a**, **CR 614.8**),
and the **CR 616.1f** repeated-application loop for choosing between two
applicable effects. **Risk:** HIGH.

**Task 3.5 - State triggers and trigger multiplying.** Owns
`machines/triggers.py`. **CR 603.8** state triggers (unverified here - look it
up); Panharmonicon-style trigger multiplying.

**Task 3.6 - Keyword execution, batch B.** Owns `machines/keywords.py`.
Suspend, splice (**CR 702.47a** - unverified here), fuse (**CR 702.102a** -
unverified here), bestow, collect evidence, companion (**CR 702.139a**,
**CR 116.2g**, **CR 103.2b**), learn, gift, offspring, manifest / manifest
dread, blight, mayhem, ninjutsu, paradigm (**CR 702.192a**).

**Task 3.7 - APNAP and the legend rule.** Owns `machines/decisions.py`.
**CR 101.4** and **CR 704.5j** (both unverified here - look them up).

**Task 3.8 - effects.py bundle C.** Owns `machines/effects.py`. Retargeting a
spell already on the stack (**CR 115.7f** for the division half; the general
"choose new targets" rule is unverified here); exiling spells off the stack
(Mindbreak Trap); "Transform all Humans"; Isochron Scepter's copy-and-cast
(**CR 112.1b**); the ordinal-branch trigger counter (Belladonna Took;
**CR 603.7h** is the neighbouring shape but not the same thing).

---

## The two permanent no-ops

Two xfails are not gaps and should be left alone or deleted:

- `test_protection.py::test_damage_from_an_instant_source_is_prevented` - the
  test's own call deals damage anonymously (`deal_damage(emrakul, 3)`, no
  `source=`). CR 702.16e needs a source with a quality. This is the test's
  choice, not an engine gap.
- `test_unparsed_trigger_targets.py::test_an_unparsed_restriction_is_logged_not_silent`
  - no card in the pool exercises `TargetingNoticeKind.UNPARSED` any more,
  because both control cards were fixed for real. The machinery is correct.

---

## Notes for executing agents

1. **Re-measure before you implement.** Nineteen reports and 109 xfail reasons
   were written by agents who could not see the current tree. Four xfail
   reasons in this file are already stale. Probe the dispatcher before you
   build anything.
2. **Never write a CR number you did not look up this session.** Every rule
   marked "unverified here" above is a deliberate hole; fill it with
   `knowledge_search(q="...", type="rules")`, not with memory.
3. **Stay inside your task's owned file.** If the fix genuinely needs a second
   file, stop and say so rather than reaching across a wave boundary.
4. **A paragraph resolves whole or fails closed.** If one sentence of an
   ability cannot be built, the whole ability must record a notice and do
   nothing - never half-execute.
5. **No mocks, real decklists only.** See CLAUDE.md.

# Engine coverage

The goal is a full MTG rules engine. This file is the honest state of it: what
the model actually implements, and what it does not. Scenario tests are written
against this list, so keep it current - a mechanic moves from "not modelled" to
"modelled" only when a scenario test covers it.

Read this before writing a scenario. If the mechanic is in the second table, the
test you write should be `xfail` with a reason, not a test bent until it passes.

## Modelled

| Area | Rules | Where | Tests |
|---|---|---|---|
| Card data | - | `models/card.py` | `test_card.py` |
| Tokens: what one is, creating one, copying one | CR 111.1-111.4, 111.6, 111.10, 111.13, 701.7a, 707.2, 110.1, 205.2c, 202.3a | `models/token.py` | `scenarios/test_tokens.py`, `scenarios/test_role_tokens.py` |
| A token put onto the battlefield attacking | CR 508.4, 508.4a, 508.4c, 506.3a-c | `token._put_onto_the_battlefield_attacking` | `scenarios/test_tokens.py` |
| A token that has left the battlefield staying gone | CR 111.8 | `TokenState.move_to` refuses the move; `models/token.move_refused` is asked by `Player.add`/`Player.move` and by every zone helper in `models/game.py`, so the token's `zone` and the list it sits in agree | `scenarios/test_tokens.py` |
| A dead token ceasing to exist, dispatched | CR 704.5d, 111.7, 704.3 | `tokens_that_cease_to_exist`, called at the start of `Game._state_based_actions_once` | `scenarios/test_tokens.py`, `scenarios/test_role_tokens.py` |
| Replacing a token *being created* | CR 701.7b, 111.2, 614.5, 616.2 | `EventKind.CREATE_TOKENS` raised by `create_tokens`/`token_copy_of`, Doubling Season's token half in `machines/replacement.py` | `scenarios/test_token_creation_replacement.py` |
| An Aura on an illegal object, dispatched | CR 704.5m, 303.4c, 702.5a | `machines/keywords.aura_state_based_actions`, called from `Game._state_based_actions_once` before `equipment_state_based_actions`. Also judges an Aura attached to a *player* now - the attachment is read off `attachment` directly rather than through `attached_to`, which only ever narrows to a card | `scenarios/test_aura_attachment.py`, `scenarios/test_enchant.py` |
| A resolving Aura spell attaching to what it targeted | CR 608.3c, 303.4a, 303.4d, 701.3a | `Game.resolve_top` re-resolves the Aura's announced target through `_aura_attachment` (which is `resolve_targets`, so a target that changed identity or left is read fresh, not off a stale id) and passes it to `Game.enter_the_battlefield`'s new `attach_to` parameter, which attaches in the same event a Containment Priest-style redirect is applied in - not as a second mutation afterwards, so a redirect to exile never leaves the Aura attached to something that never arrived. Before this, every permanent spell went through `enter_the_battlefield` identically, an Aura landed with no attachment at all, and `aura_state_based_actions` correctly binned it a moment later - CR 704.5m was right, CR 608.3c's attach was simply never done. `CardState.attach_to` also self-attach-guards and, if `enter_the_battlefield` is ever asked to attach an Aura to itself anyway, routes it to its owner's graveyard (CR 303.4d) instead of raising out of a spell's resolution | `scenarios/test_aura_resolution.py` |
| Every Role but the newest | CR 704.5z, 303.7a, 613.7a | `Game._roles_beyond_the_newest`, reading `machines/layers.ContinuousEffects.entered` for the timestamp | `scenarios/test_role_tokens.py` |
| How much a prevention shield prevented | CR 615.5, 609.7b | `PreventionShield.prevented` and `gains_life_when_prevented`, set by `Game.apply_prevention_shield` | `scenarios/test_prevention_effects.py` |
| A keyword ability's effect on resolution | CR 608.2, 702.108a, 702.21a, 702.79a, 702.85a, 702.35a | `Game._effect_of` asks `machines/keywords.keyword_effect_for` before the card-name registries, so prowess, ward, persist, cascade, cycling, equip and madness resolve | `scenarios/test_prowess.py`, `test_ward.py`, `test_persist.py`, `test_cascade.py`, `test_madness.py` |
| Earthbend, a CR 701 keyword *action* embedded in another ability's effect text | CR 701.66a, 205.1b, 613.4b, 613.4c, 603.7a, 603.7e | `machines/effects._parse_earthbend_clause`/`earthbend`. Not printed with the word "target" - `machines/targeting.profile_for_text` is taught the keyword's own implied "target land you control" restriction so CR 601.2c's announcement still works. The land gains the creature type additively (`layers.add_type`, never `layers.set_basic_land_type`'s CR 305.7 path, which would strip its mana ability) and is set to 0/0 in sublayer 7b, with the `N` +1/+1 counters going on as real counters (`Game.add_counters`) rather than a second continuous effect, so CR 613.4's fixed sublayer order makes 0/0 + one counter unconditionally a 1/1 with no window where it is a legal-to-die 0/0. The animate/0-0/haste continuous effects are `Duration.INDEFINITE` and scoped with `layers.only_this_incarnation` to the exact pre-return incarnation of the land (by `zone_change_stamp`, not just `id`) - without that scoping the land would come back animated forever after its own delayed return, since `ContinuousEffects.end_the_turn` never clears an indefinite effect. "Dies or is put into exile" is represented as two `DelayedTrigger`s (`TriggerEvent.DIES`, and the new `TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE` now emitted by `Game.exile_permanent`, which previously emitted no event at all), returning tapped under the earthbend ability's own controller (CR 603.7e) rather than the owner-and-untapped default `delayed.return_subject_to_battlefield_under_owner` uses for a blink effect; whichever fires first drops its sibling. Fixed alongside it: `DelayedTrigger.matches` ignored `subject_id` entirely - harmless for every delayed trigger before this one, since they all watch `BEGINNING_OF_STEP`, whose event never carries a subject, but earthbend is the first event-keyed, subject-scoped delayed trigger and would otherwise have its one-shot `remaining` spent by an unrelated creature's death | `scenarios/test_earthbend.py` |
| A keyword or reminder-text line ahead of a spell's own resolution sentence | CR 207.2a, 702.62a | `_SUSPEND_LINE_RE`/`_CASCADE_LINE_RE` in `machines/effects.py` strip a card's own "Suspend N—\[cost]" or "Cascade (reminder)" line before `_CLAUSE_SEPARATOR` ever splits the rest - without this, the periods inside Cascade's reminder text (or a leading Suspend line with none of its own) were read as sentence boundaries and the *real* resolution sentence after it was silently dropped along with the garbage. Found by dissecting Living End (its own "Each player exiles..." sentence) and Violent Outburst (its own "Creatures you control get +1/+0..." pump) | `scenarios/test_living_end.py`, `scenarios/test_cascade.py::test_violent_outbursts_own_pump_fails_closed_instead_of_silently` |
| "Each player \<sequence of actions>", read whole | CR 608.2c, 701.13a, 701.21a, 400.7, 110.2a | `_EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE` and `each_player_exiles_sacrifices_and_returns_creatures` in `machines/effects.py`, matched against the whole (preamble-stripped) sentence in `_spell_effect_or_notice` ahead of the ordinary per-clause split, because CR 608.2c's own "then"s inside one sentence are not CR 608.2c's *own* clause boundaries the way `_CLAUSE_SEPARATOR`'s bare "then" reads them | `scenarios/test_living_end.py` |
| A duration-bearing group pump, told apart from CR 611.3's anthem | CR 611.2, 611.3 | `is_resolution_layer_effect_text` in `machines/layers.py` used to route *any* "Creatures you control get +N/+N..." opening to the anthem exemption regardless of what followed, so "Creatures you control get +1/+0 until end of turn." (Violent Outburst) never even reached the fail-closed check. An explicit duration can never be CR 611.3's forever-lasting static shape, so it now falls through to a `LayerNotice` instead - the actual continuous effect for a team-wide temporary pump is still not built (queued below) | `scenarios/test_cascade.py::test_violent_outbursts_own_pump_fails_closed_instead_of_silently` |
| A discard that goes through the replacement effects | CR 701.9a, 702.35a, 614.1 | `machines/keywords.discard`, reached by `CostComponent.pay` and by `Player.discard` through the `Player.game` back-reference | `scenarios/test_madness.py` |
| Indestructible, enforced | CR 702.12b, 701.8a, 701.8b, 704.5f-h | `Game.destroy` refuses it; `Game._dies_to_state_based_action` drops CR 704.5g and CR 704.5h and keeps CR 704.5f, which CR 701.8b says is not destruction | `scenarios/test_indestructible.py` |
| A cost sentence no `CostKind` fits, activated | CR 602.1a, 701.43a, 118.3 | `Game.activation_cost` routes `CostKind.OTHER` to `machines/cost.cost_component_for_phrase` and fills in the source permanent for a `this` phrase | `scenarios/test_exert.py` |
| Role tokens and what they grant | CR 111.10k, 303.7 | `LAYER_EFFECTS["Monster"]` in `machines/layers.py` | `scenarios/test_role_tokens.py` |
| Zones | CR 400 | `models/zone.py` | `test_zone.py` |
| Outside the game, and bringing a card in from it | CR 400.11, 400.11a, 400.11b, 400.11c, 100.4, 100.4a, 108.3b, 103.2a | **Not an eighth zone.** CR 400.1 numbers seven zones and outside the game is not among them; CR 400.11a says only that "cards in a player's sideboard are outside the game", so `Zone.SIDEBOARD` stays the *storage* for those objects and `Zone.is_outside_the_game` / `Player.outside_the_game` are the rules-level reading of it. `Player.owned_outside_the_game` filters by CR 108.3b's **owner** (not controller), and `Player.bring_into_the_game` is CR 400.11b's one-way move, refusing a card that is not outside the game and a card the player does not own. Deck legality is untouched by a fetch: `Deck.check_legality` counts the registered decklist (CR 100.2a, 100.4a), not the physical sideboard, and `Match._fresh` reloads the whole list next game, which is CR 400.11b's "until the game ends" bound. Reachable only by an ability CR 400.11c's exception allows - Karn, the Great Creator's `−2` is the pool's one such card | `scenarios/test_outside_the_game.py` |
| Revealing a card | CR 701.20a, 701.20b, 701.20c | `Game.reveal` appends one `Reveal` per card actually shown and moves nothing (CR 701.20b). Public information is the *reveal*, not the group it came from: a card revealed out of a sideboard nobody may look at makes exactly one card public. `Game.reveals` is the whole record; there is no "revealed zone" | `scenarios/test_outside_the_game.py` |
| Face-up versus face-down exile, as a choosability question | CR 406.3, 406.3a | `Game.face_up_cards_in_exile(owner, matches)`. A card exiled face down "can't be examined by any player" and "has no characteristics" (CR 406.3a), so it can never answer "a face-up artifact card you own in exile" | `scenarios/test_outside_the_game.py` |
| A static ability that prohibits activating another permanent's abilities | CR 602.5, 611.1, 611.3, 611.3a, 611.3b, 604.2, 605.1a | Not a layer effect: CR 611.1's third case is a continuous effect that "affects players or **the rules of the game**", which writes no characteristic, so `machines/layers.py` has nothing to compute and the prohibition is felt at `Game.why_cannot_activate` instead (CR 602.5). `_parse_activation_prohibition` reads "Activated abilities of \<card types> \[your opponents control] can't be activated \[unless they're mana abilities]" off a battlefield permanent's own static line, re-read on every query (CR 611.3a: not locked in) and gone the moment its source leaves (CR 611.3b). "Your opponents control" is resolved against the **source's** controller, so Karn, the Great Creator does not stop his own controller's artifacts, while the symmetric printings (Collector Ouphe, Clarion Conqueror) do. The affected permanent's card types are read off the computed board (CR 613.5), so an artifact Karn's own `+1` animated is still prohibited. A prohibition sentence in another shape records a `LayerNotice` and blocks nothing - except Pithing Needle's and Disruptor Flute's "sources with the chosen name", which already have an `UnwiredChoiceNotice` and are skipped rather than counted twice | `scenarios/test_outside_the_game.py` |
| A continuous effect that restricts or loosens *casting*, rather than activating | CR 611.1, 611.3, 611.3a, 611.3b, 602.1a, 800.4m | **W5.** The casting-side twin of the activation-prohibition row above, in a new small module rather than a bigger one: `machines/casting_restrictions.py`. Two shapes, told apart by whether a live battlefield permanent can answer for them. **A live static** - Teferi, Time Raveler's "Each opponent can cast spells only any time they could cast a sorcery." - is read fresh off the battlefield on every query by `sorcery_speed_restriction_source`, exactly like `_parse_activation_prohibition` above, and dies the instant Teferi does. **A recorded `CastingRuleEffect`** covers the two shapes a live read cannot answer for: Ranger-Captain of Eos's "Sacrifice this creature: Your opponents can't cast noncreature spells this turn" is created when the ability *resolves*, by which point the sacrifice (its own cost, CR 602.1a) has already sent the source to the graveyard, so nothing is left to scan; and Teferi's own `+1`, "Until your next turn, you may cast sorcery spells as though they had flash," is a temporary grant to its controller alone, reusing `Duration.UNTIL_YOUR_NEXT_TURN` (CR 800.4m) rather than `machines.casting.PlayPermission`, which names one specific card and is the wrong shape for a blanket permission over every sorcery cast. Both recorded effects are dropped by `Game.casting_rule_effects` list rewrites - `cleanup_step` for the "this turn" restriction (CR 514.2) and `begin_turn_for` for the "until your next turn" grant (CR 800.4m), mirroring how `play_permissions` already drops its own two durations. Read from two sites: `machines.casting.why_cannot_cast_now` (the static, folded into the CR 117.1a timing question, checked *before* the ordinary instant/flash exceptions so a restricted opponent loses them, but *after* `can_cast_sorcery` so a legally-timed cast needs no exception at all) and the new `why_cannot_cast_restriction` (the flat noncreature ban, unrelated to timing). Both are asked only once, in `Casting.model_post_init`, as a `Casting` is created - never re-asked of one already on the stack, so a restriction that appears mid-response does not reach back and unmake an announcement that already finished (CR 601.6) | `scenarios/test_casting_restrictions.py` |
| Turn structure | CR 500-514 | `machines/turn.py` | `test_turn.py`, `scenarios/test_turn_cycle.py` |
| Priority | CR 117 | `machines/priority.py` | `scenarios/test_priority.py` |
| `Game.advance` refusing to leave a step while the stack is non-empty, and authorizing who may call it | CR 500.2, 500.3, 117.4, 405.5, 117.3a, 723.5 | `Game.advance` raises rather than crossing a step boundary while `grants_priority` is true and the stack is non-empty (the untap/cleanup exception is `NO_PRIORITY`), and raises when `player` is neither the active player nor their CR 723.5 controller | `scenarios/test_advancing_the_turn.py` |
| Casting announcement | CR 601.2 | `machines/casting.py` | `test_casting.py` |
| Paying mana costs | CR 601.2f-h | `machines/cost.py`, `models/mana.py` | `test_cost.py`, `test_mana.py` |
| Floating mana pays costs | CR 106.4, 106.4a, 118.3a, 202.1a, 601.2g, 733.1 | `CostPayment.for_total` seeds the payment's pool with a copy of the payer's floating mana, `pay()` writes the remainder back into the payer's pool, and a rewind from PAID restores the pre-payment pool - while a cancelled payment's own activations die with the copy (CR 733.1's "any payments already made are canceled") | `scenarios/test_costs.py` |
| Every printed mana symbol | CR 107.4a-h, 202.3f-g | `ManaSymbol` in `models/mana.py` | `test_mana.py` |
| Paying a symbol that has more than one half | CR 118.13, 118.13a | `ManaPool.payment_for`, `CostPayment.choices` | `test_mana.py`, `scenarios/test_costs.py` |
| Phyrexian mana paid with life | CR 107.4f, 119.4 | `CostPayment.pay` appends a `pay_life_cost` component | `scenarios/test_costs.py` |
| Snow mana and snow sources | CR 106.3, 107.4h, 205.4g | `CostPayment.tap_for_mana`, `ManaPool.snow` | `test_cost.py`, `scenarios/test_costs.py` |
| Costs other than mana | CR 118.3, 118.8, 601.2b, 601.2h | `CostComponent`/`TotalCost` in `machines/cost.py` | `test_cost.py`, `scenarios/test_costs.py` |
| Alternative costs and cost modification | CR 118.7, 118.9, 601.2f | `machines/cost.py`, `machines/casting.py` | `test_cost.py`, `scenarios/test_costs.py` |
| A keyword cost printed after an em dash | CR 702.1a | `KeywordAbility` in `machines/abilities.py` reads `Evoke—Exile a black card from your hand.`, `Suspend 3—{2}{B}{B}` | `scenarios/test_keyword_cost_forms.py` |
| A printed cost sentence turned into something payable | CR 118.3 | `cost_component_for_phrase`/`total_cost_for_phrase` and `CardRequirement` in `machines/cost.py` | `scenarios/test_keyword_cost_forms.py`, `scenarios/test_evoke.py` |
| Which zone a keyword lets a card be cast from | CR 601.3 | `KeywordCastOption`, `keyword_cast_options`, `why_cannot_cast_from` in `machines/casting.py` | `scenarios/test_flashback.py` |
| An effect's **time-boxed permission to play specific exiled cards** | CR 601.3, 601.1a, 701.5b, 701.18a, 701.18b, 118.9, 118.9c, 107.3b, 514.2, 400.7, 108.3 | `PlayAction`/`PlayPermission`/`play_permissions_on`/`usable_play_permission` in `machines/casting.py`, `Game.grant_play_permission`/`Game.play_permission_for`/`Game.play_permissions`, announced on a cast with `Casting.use_permission` and enforced by `Casting._refuse_unless_allowed_from_its_zone` (CR 601.3) and by `Game.play_land`'s own zone check (CR 305.1, 701.18a). The dynamic twin of `KeywordCastOption`: that one is a *static* grant read off a card's own printed keyword, this is one a **resolving ability** hands out. Deliberately per object rather than per zone - a blanket "exile is castable" would let a player cast anything ever exiled, including an opponent's. Keyed by `card_id` **and** `zone_change_stamp`, so CR 400.7's new object loses it; `player` is who may play it, which CR 108.3 lets differ from the owner; `action` keeps CR 701.5b's *cast* apart from CR 701.18b's wider *play*, so only a `PLAY` permission reaches the land drop and it still costs CR 305.2a's one-per-turn allowance; `pays_mana_cost=False` is CR 118.9's "without paying its mana cost", announced separately (CR 118.9b) so "may cast this" and "may cast this free" stay two different grants. Timing is untouched: a sorcery under the permission is still refused outside a main phase (CR 117.1a). Dropped in the cleanup step (CR 514.2), with `granted_turns_taken` as the backstop for a game driven step by step that never reaches one. | `scenarios/test_play_from_exile.py` |
| Reading "[exile some cards]. Until end of turn, you may cast/play them." off printed text | CR 608.2c, 607.1, 107.1c, 701.23b, 601.3 | `_parse_exile_then_play_permission_pair` in `machines/effects.py`, with `_parse_exile_antecedent`'s two shapes ("exile the top card of that player's library" - Ragavan; "search your library for any number of `<quality>` cards, exile them, then shuffle" - Ugin's −11) and `_PLAY_PERMISSION_RE`'s permission sentence. Read as one CR 608.2c instruction, never two, because the pronoun is CR 607.1's anaphora back to what the first clause exiled; number has to agree ("that card" is not "those cards"), and an unreadable stated quality refuses the whole pair rather than searching for something it cannot describe. "Any number" is CR 107.1c's zero-or-more, asked card by card through `Game.search_library(optional=True)` (CR 701.23b), so finding nothing is legal and grants nothing. `_named_type_matcher` now reads a "non`<type>`" quality word (CR 109.2), which is what "colorless nonland" needs. | `scenarios/test_play_from_exile.py` |
| "Add `<mana>`" as the resolution of an ability that is **not** a mana ability | CR 605.1a, 605.5, 606.2, 602.2, 113.3b, 106.4 | `_parse_add_mana_clause` in `machines/effects.py`. Ugin, Eye of the Storms' `0: Add {C}{C}{C}.` is a loyalty ability (CR 606.2: a loyalty symbol in the cost), and CR 605.1a's criteria include "it's not a loyalty ability" - so CR 605.3b's "doesn't go on the stack" is false of it. `Game.activate_ability` already refused it the mana-ability fast path; nothing resolved it afterwards, so the mana silently never arrived. It does now, at resolution, into the controller's pool (CR 106.4). | `scenarios/test_loyalty_abilities.py` |
| Evoke, as an alternative cost | CR 702.74a, 118.9, 118.9a, 118.9c | `Casting.use_keyword` | `scenarios/test_evoke.py` |
| Flashback, as permission plus an alternative cost | CR 702.34a | `Casting.use_keyword` from `Zone.GRAVEYARD` | `scenarios/test_flashback.py` |
| Escalate, as an additional cost per extra mode | CR 702.120a, 118.8a | `Casting.pay_escalate` | `scenarios/test_escalate.py` |
| Annotated exile: which pile a card is in | CR 406.4, 400.2, 400.7 | `ExileMarker`/`ExileAnnotation` and `CardState.exile_annotation` | `scenarios/test_plot.py`, `test_foretell.py`, `test_warp.py` |
| Plot: the special action and the later cast | CR 116.2k, 702.170a-d | `MarkedExile.plot` in `machines/casting.py` | `scenarios/test_plot.py` |
| Foretell: the {2} special action and the later cast | CR 116.2h, 702.143a-c, 406.3 | `MarkedExile.foretell` | `scenarios/test_foretell.py` |
| Warp: the cheap cast, and the warped card in exile | CR 702.185a-c | `Casting.use_keyword("Warp")`, `casting.exile_warped` | `scenarios/test_warp.py` |
| Adventure: which face is cast, and the exiled card after | CR 715.1, 715.3, 715.3a, 715.3d | `Casting.cast_as_adventure`, `adventure_face`, `casting.exile_adventured` | `scenarios/test_adventure.py` |
| Casting a card out of a shared zone | CR 400.2 | `Casting._leave_shared_zone` - `Game.put_on_stack` only searches a player's own zones | `scenarios/test_plot.py` |
| Checking an **ability's** targets as it goes on the stack | CR 115, 601.2c, 602.2b, 603.3d | `Game.choose_trigger_targets`/`why_cannot_target_with_trigger`, `Game.activate_ability`, through `targeting.profile_for_text` | `scenarios/test_targeting_adjectives.py` |
| A triggered ability's controller is **asked** for its targets | CR 115.1, 601.2c-d, 603.3d, 608.2d | `DecisionKind.CHOOSE_TARGETS`; `Game.put_triggers_on_stack` → `Game._ask_trigger_targets` asks each ability *instance* through `Game.ask`, addressed to `ability.controller`, before it is appended to the stack; candidates come from `Game._legal_target_candidates` running `TargetRequirement.rejects` over the board. `Game.choose_trigger_targets` is the scripted `DecisionScript` path used by ~34 existing scenario call sites, kept working by staging a `CHOOSE_TARGETS` answer that `put_triggers_on_stack` throws away once its batch is processed, so it cannot leak into a later, unrelated trigger of the same card name. Fixes the defect where every targeted trigger went on the stack with `targets: []` unconditionally (no production caller ever populated the old `trigger_targets: dict[str, list[TargetRef]]`), plus three bugs that dict had from being keyed by name instead of by ability instance: a stale answer reused by a later trigger, two simultaneous copies of a card unable to be targeted separately, and a delayed triggered ability inheriting another trigger's targets while ignoring `ability.controller`. | `scenarios/test_trigger_target_decisions.py` |
| A restriction that is game state rather than a characteristic | CR 109.3, 508.1k, 509.1g, 511.3, 608.2b | `Game.legal_target` passes itself to `TargetRequirement.rejects`, so "target attacking creature" is rechecked on resolution | `scenarios/test_targeting_adjectives.py` |
| Targeting legality | CR 115, 601.2c | `machines/targeting.py` | `test_targeting.py`, `scenarios/test_targeting_legality.py` |
| The same target once per instance of "target" | CR 115.3 | `TargetingProfile.check` | `test_targeting.py`, `scenarios/test_damage_division.py`, `scenarios/test_variable_target_counts.py` |
| A target count that is a range, not a number | CR 115.4, 115.6, 107.1c, 107.3a | `TargetRequirement.minimum`/`count`/`unbounded` in `machines/targeting.py` | `test_targeting.py`, `scenarios/test_variable_target_counts.py` |
| Reading a division off the card, checking one, and **recording the caster's own announcement (W13)** | CR 601.2d, 115.7f, 107.1a | `TargetingProfile.division`, `TargetingProfile.check_division`; `Casting.announce_division` records the caster's actual per-target shares on `CardState.division`, read back by `machines/effects.py`'s `_deal_divided_damage_shares` in place of the even-split fallback (kept for any spell that never calls it, Electrolyze's own pre-W13 scenarios included). `Division.amount` is `int \| None` - `None` for a variable (X) amount, resolved by the caller from `Casting.x_value` and `Division.doubled_if_x_at_least` (Shatterskull Smashing's "doubled if X is 6 or more") | `test_targeting.py`, `scenarios/test_damage_division.py`, `scenarios/test_mdfc_spell_side.py` |
| An ability on the stack as a legal target | CR 115.2, 113.1c, 605.3b, 605.4a | `TargetRequirement.allows_abilities`, `targeting.profile_for_text` | `test_targeting.py`, `scenarios/test_targeting_an_ability.py` |
| A negated type adjective: "noncreature spell", "nonland permanent card" | CR 109.2, 109.2a, 109.2b, 110.3, 300.1, 300.2 | `TargetRequirement.excluded_card_types`, `_negated_type` in `machines/targeting.py` | `test_targeting.py`, `scenarios/test_targeting_adjectives.py` |
| A negated *supertype* adjective: "nonbasic land" | CR 205.4a, 205.4b, 205.4c | `_SUPERTYPE_NOUNS`/`_negated_supertype` in `machines/targeting.py` (the sibling of `_negated_type`, added because `basic` is a supertype, not a card type - a stem lookup in `_TYPE_NOUNS` alone left it unread); `TargetRequirement.required_supertypes`/`excluded_supertypes`. Fixes White Orchid Phantom, which used to `understood=False` on its own text and go on the stack through the old silent `_ask_trigger_targets` fallback with no target ever offered | `scenarios/test_negated_supertypes.py` |
| An unreadable trigger-target restriction is **audible**, not silent | CR 603.3d, 608.2d; CR 608.2b for the distinction from a real fizzle | `Game._ask_trigger_targets` used to `return []` for both "the parser cannot read this" and "nothing here is a legal target" alike. `TargetingNotice`/`TargetingNoticeKind` (`machines/triggers.py`), appended to `Game.targeting_notices`, tell the two apart: `UNPARSED` for the first (an engine gap), `NO_LEGAL_TARGET` for the second (CR 608.2d's own default, a legitimate game state). Neither changes CR 603.3d's outcome - the ability still goes on the stack with no targets - only whether that outcome is recorded anywhere | `scenarios/test_unparsed_trigger_targets.py` |
| "up to one **other** target ...", and "another"/"other" excluding the source | CR 115.6 for "up to"; no single CR number found for "another"/"other" itself (`knowledge_search`, this session) | `_read_count` in `machines/targeting.py` used to read the last three words before "target" without skipping "other"/"another", so "up to one other" landed on the fallback mandatory-one instead of "up to one" - `_SOURCE_EXCLUDING` now strips them before counting. `_excludes_source` reads the word for what it separately means - `TargetRequirement.excludes_source`, checked against `AbilityOnStack.source_id` threaded through `TargetingProfile.check`/`rejects`. Fixes Phelia, Exuberant Shepherd and Solitude, both printed as mandatory-and-self-targetable before this | `scenarios/test_up_to_and_source_exclusion.py` |
| An Oxford-comma noun list: "target artifact, enchantment, or nonbasic land" | CR 115.1 | The noun-reading loop in `_read_phrase` kept the comma as its own token (previously stripped by the word tokenizer, which is why a bare "or" list read correctly but a comma-separated one silently kept only the first noun) and now tries a fresh leading adjective before every item, not only the first, so "nonbasic" still binds only to "land" rather than to the whole list. Landed *after* the negated-supertype fix on purpose: fixing the comma first would have widened Boseiju from "artifact only" to "any land, including a basic one" - narrower-than-correct is a smaller bug than wider-than-correct | `scenarios/test_oxford_comma_target_lists.py` |
| Instant and sorcery as target types | CR 300.1, 109.2a | `_TYPE_NOUNS` in `machines/targeting.py` reads "target instant or sorcery card in your graveyard" | `test_targeting.py` |
| "target attacking creature", and being removed from combat | CR 508.1k, 509.1g, 506.4, 511.3, 109.3, 608.2b | `CombatState`, `TargetRequirement.combat_states`, `check(..., game=...)` | `test_targeting.py`, `scenarios/test_targeting_adjectives.py` |
| A target count that is an unannounced X | CR 107.3, 107.3a, 601.2b, 601.2c | `TargetRequirement.variable_count` - the kind is checked, the number is left open | `test_targeting.py` |
| Modal spells: reading the modes, choosing them, and the targets that follow | CR 700.2, 700.2a, 700.2c, 700.2d, 700.2f, 115.8, 601.2b | `machines/modes.py`, `Casting.choose_modes`, `targeting.profile_for_modes` | `test_modes.py`, `test_targeting.py`, `test_casting.py`, `scenarios/test_modal_spells.py` |
| A modal spell cast with its mode count unsatisfied is refused, not accepted-and-inert | CR 700.2a, 601.2b, 601.2e, 601.6 | `choose_modes` already rejects an out-of-range/duplicate/unknown choice via `ModalProfile.resolve`, but a caller can skip calling it entirely (Kozilek's Command cast with `--x 2` and no `--modes` used to return `allowed: true` and resolve doing nothing). `Casting._refuse_unless_modes_satisfied`, called from `Casting.cast` - the one step every path reaches - refuses whenever the announced mode count falls outside `ModalProfile.allowed_range`, naming the numbered modes and the required count. Left alone on purpose when `modal.understood` is False, so Elder Gargaroth's modal *triggered* ability (its creature spell is not modal) still casts normally | `scenarios/test_modal_spells.py` |
| Entwine and escalate, as far as their cost | CR 702.42a, 702.120a | `ModalProfile.entwine_cost`/`escalate_cost`, `Casting.choose_modes(entwined=True)` | `test_modes.py` |
| What a mode does on resolution | CR 700.2a, 702.42b, 700.2f, 101.3 | `Game.resolve_top` reads `Game.cast_record(spell).modes` and, when the spell was cast with modes chosen, hands off to `machines/effects.py`'s `resolve_modal_spell` instead of the ordinary card-name/oracle-text lookup - each chosen mode runs its own text independently, in the printed order (CR 702.42b generalizes past entwine: "follow the text of each of the modes in the order written on the card"), reusing the same targeted/token/search/player clause parsers a non-modal card's whole text goes through. Two shapes exist only for a mode: a mode whose grammatical subject is "target player" rather than "you" (Kozilek's Command's token-creation and scry-then-draw modes), read by `_parse_target_player_token_mode`/`_parse_target_player_mode` off the mode's own X-substituted text with its quoted granted ability intact (`substitute_x`, not the target-parsing `mode_rules_text`, which blanks quotes). **Per-mode targets are sliced, not flattened**: `Casting.choose_targets` calls `TargetingProfile.assign_to_owners` (fed by `targeting.profile_for_modes_with_owners`) to bucket one flat target announcement into one list per chosen mode instance, stored as `CastRecord.mode_targets` - CR 700.2f's "different targeting requirements for each mode" made structural. **Fail-closed per mode, not per spell**: a mode this wave cannot read is skipped and recorded in `Game.mode_notices` (a `ModeNotice`, the same "unreadable is not the same as no effect" pattern as `TargetingNotice`/`InterveningIfNotice`/`CostModifierNotice`/`LayerNotice`), while every other chosen mode of the same cast still happens - CR 101.3 excuses only "any part of an instruction that's impossible to perform", and CR 700.2/702.42b already treat each mode as its own separable instruction rather than a sub-clause of one. **X is fixed once for the whole spell** (CR 107.3a/107.3c): `Casting.x_value_at_targets` records what X was when targets were announced, and `cast()`'s `_refuse_if_x_changed_since_targets` refuses loudly if `choose_modes`'s and `determine_cost`'s independent setters of `x_value` ever disagree by the time the spell is cast, rather than letting a mode's "up to X target ..." be counted against a stale X. Kozilek's Command's mode 1 (token creation, a variable count and a quoted granted ability) and mode 3 (an X-bounded exile) both resolve correctly now, closing the reported defect. Mystic Confluence's repeatable mode runs once per time it was chosen. Not reached by this: Spree/Tiered/pawprint modal templating (`ModalProfile.understood` is already `False` for those, so `resolve_modal_spell` never runs at all), and any mode whose clause shape none of the existing parsers cover (Mystic Confluence's "unless its controller pays", Cryptic Command's "Tap all creatures your opponents control.", Thraben Charm's dynamic-damage and player's-graveyard-exile modes) - each such mode is simply a `ModeNotice`. | `scenarios/test_modal_spells.py` |
| Mana abilities | CR 605 | `machines/abilities.py` (`ManaAbility`, `ManaCondition`), `Game._controlled_land_types`/`activate_ability` | `test_abilities.py`, `scenarios/test_mana_abilities.py` |
| A conditional "instead" mana ability, evaluated against the live board (Urza's Tower/Mine/Power Plant, Gemstone Caverns) | CR 605.1a (criteria evaluated on printed text), 605.3b (resolves immediately), 305.5 (land subtypes are single words - "Urza's Mine" is read as "Urza's" and "Mine"), 205.3i | `ManaAbility.resolve`, `ManaCondition`, `Game._controlled_land_types` | `scenarios/test_mana_abilities.py` |
| A basic land's, a shockland's, and a Ravnica dual's intrinsic mana ability, unwritten because it is printed as reminder text | CR 305.6, 305.5 | `intrinsic_land_ability`, used as the fallback in `parse_mana_abilities` and `activated_abilities_of` whenever a land prints no activated ability of its own | `test_abilities.py`, `scenarios/test_mana_abilities.py` |
| Choosing a colour for a mana ability that offers one (any colour, or one of several) | CR 605.1a | `ManaAbility.resolve(color=...)`, `Game.activate_ability(..., color=...)` | `test_abilities.py`, `scenarios/test_mana_abilities.py` |
| The activation cost of a mana ability, paid in full before it resolves (a tap, a sacrifice, a life payment) | CR 601.2g ("mana abilities must be activated before costs are paid"), 602.2b | `Game.begin_activating`/`CostPayment.pay`, called before `Game.activate_ability` in both the harness (`Scenario.activate`) and the API (`engine_api.activate_ability`) | `scenarios/test_mana_abilities.py` |
| "Add N mana of any one color" - more than one mana, all of the one colour chosen | CR 106.1b (the six types of mana), CR 106.5 (an undefined type produces nothing, which is why the colour must be chosen) | `machines/abilities.py`'s `_ANY_COLOR`/`ManaAbility.any_color_count`. Previously only "one mana of any color" was read at all, so Shang-Chi, Master of Kung Fu's `{T}: Add two mana of any one color.` was not recognised as a mana ability and produced nothing; it is the only printing in the pool with this shape | `scenarios/test_mana_spend_restrictions.py` |
| "Activate only if [board state]" restrictions on a mana ability (Fanatic of Rhonas's Ferocious, Mox Opal's Metalcraft) | CR 602.5b | `Game._activation_condition_holds`, called from `why_cannot_activate` | `scenarios/test_mana_abilities.py` |
| Mana spend restrictions ("Spend this mana only to ...") | CR 106.6 (the restriction half of it; CR 703.4q / 500.5 for when the mana and the tag are lost; CR 118.3a for paying being the removal of *that* mana) | `models/mana.py` carries the tag on the mana in the pool, never on its source: `ManaRestriction` (the printed sentence plus a tuple of `SpendClause` alternatives), `RestrictedMana` (how much of `ManaPool.floating` carries each), and `ManaSpend` (what a cost is *for* - `casting(card)` against `activating(card)`, which is what tells a creature **spell** apart from an ability of a creature **source**). `ManaPool._spendable_buckets` removes mana the restriction forbids before the payment search runs, so an illegal purpose is **refused** rather than deprioritised; `ManaPool._buckets` then orders restricted mana ahead of unrestricted, so the mana that can do less is the mana spent and a legal play is never stranded. `ManaPool.empty` drops the tags with the mana. `machines/cost.py` reads the sentence (`spend_restriction`), tags what a source produces (`CostPayment.tap_for_mana`, inferring which ability was activated from what it produced when the caller does not say - `restriction_for_production`), and carries the purpose (`CostPayment.spend`, set by `Casting.determine_cost` and `Game.begin_activating`). `auto_tap` offers a restricted ability exactly when the restriction permits the cost being paid. All four printings in the pool are read: Shang-Chi, Master of Kung Fu, Eldrazi Temple, Cavern of Souls (needs CR 614.12a's chosen creature type on the permanent), Delighted Halfling. **Still not modelled**: the *other two* things CR 106.6 lists - an additional effect on the spell the mana is spent on (Cavern of Souls's and Delighted Halfling's "and that spell can't be countered", Arena of Glory's haste grant) and a delayed triggered ability. A payment that cannot name what it is for (`CostPayment.spend` left `None` - a foretell/plot cost, a keyword "unless you pay") gets no restricted mana at all, and a sentence the grammar cannot read produces a restriction with no clauses that permits nothing: both fail closed. Restricted mana added by an *effect* rather than a mana ability (`machines/effects.py`'s mana-adding clauses) is still added untagged. | `scenarios/test_mana_spend_restrictions.py`, `scenarios/test_mana_abilities.py`, `scenarios/test_auto_tap.py` |
| "Imprint" (CR 207.2c: an ability word with no rules meaning of its own) and the "exiled with this permanent" shape it names on Ugin's Labyrinth - "you may exile a `<quality>` card [with mana value N or greater/less] from your hand" on entry, linked back to the permanent so a later ability can find it again | CR 207.2c, CR 608.2d (a cost-free "you may", illegal when no legal card exists in hand), CR 605.1a (the conditional mana clause), CR 406.4 (the exile-pile annotation this reuses) | `machines/effects.py`'s `_parse_imprint_clause` (the ETB choice) and `_parse_return_imprinted_clause` (the "return the exiled card" ability), read off the ability's own text with no registry row; `ExileMarker.IMPRINTED` and `ExileAnnotation.linked_permanent_id` (`models/card_state.py`) carry the link; `ManaCondition.imprinted` and `Game.card_imprinted_on` (read by both `Game.activate_ability` and `cost.py`'s auto-tap solver) resolve the conditional mana clause against it. An unrecognised quality word fails closed with an `ImprintNotice` rather than silently asking nothing (`Game.imprint_notices`) | `scenarios/test_imprint.py` |
| "You may sacrifice `<restriction>`. If you do, `<consequence>`." (CR 118.12) - "this `<type>`" (Sanctum of Ugin, no choice of which) or "another `<type>`" (Disciple of Freyalise, a real CR 608.2d choice among what the player controls), paired with a plain mandatory search or a magnitude-threaded pair of clauses reading "X" as the sacrificed permanent's power | CR 118.12 (the "if you do" checks the *choice*, not the board, "regardless of what events actually occurred"), CR 608.2d (the "you may" itself, illegal with no legal permanent to sacrifice), CR 608.2i (the power is read before the sacrifice moves the permanent to the graveyard), CR 701.21a (sacrifice) | `machines/effects.py`'s `_parse_conditional_sacrifice_clause`, `_sacrifice_restriction`, `_parse_sacrifice_consequence`. An unrecognised restriction or consequence fails closed with a `ConditionalClauseNotice` (`Game.conditional_clause_notices`) rather than silently offering nothing | `scenarios/test_conditional_sacrifice_clauses.py` |
| Solving which untapped sources to tap, and which colour a dual/shockland/any-colour source makes, to pay a known cost - so a player is not asked to hand-pick every land on every cast | CR 601.2g (mana abilities activated before costs are paid), 118.3c (activating them is never mandatory) | `CostPayment.auto_tap`, `free_tap_mana_abilities`, both in `machines/cost.py`. Never chooses a source whose only mana ability has a cost beyond `{T}` (Sunbaked Canyon's life, Tinder Farm's sacrifice, Arena of Glory's exert) - that is a real cost only the player may choose to pay. A CR 106.6 restricted ability (Eldrazi Temple's `{C}{C}`, Cavern of Souls's any-colour ability) **is** offered now, but only when the restriction permits the cost being paid, and is preferred over the same source's unrestricted ability when both would serve - see the spend-restriction row above. Prefers the fewest sources, and among equally-small assignments prefers spending the least flexible ones first | `scenarios/test_auto_tap.py` |
| Triggered abilities | CR 603.2, 603.3, 603.3b, 603.4, 603.6a, 603.10a, 500.6, 700.4 | `machines/triggers.py`, `Game.emit`/`put_triggers_on_stack` | `scenarios/test_triggered_abilities.py` |
| The event side of a trigger: drawing, life, damage, sacrifice, countering, untapping | CR 603.2, 603.2c, 603.2g, 603.10a, 603.10e, 121.2, 119.3, 119.9, 120.1, 120.9, 701.6a, 701.21a, 502.3 | `TriggerEvent` in `machines/abilities.py`, the emitters in `models/game.py` (`draw_cards`, `gain_life`, `deal_damage`/`deal_damage_to_player`, `sacrifice`, `counter`, `untap_step`), and the matcher branches in `machines/triggers.py` | `scenarios/test_trigger_events.py` |
| Activated abilities | CR 602.1a, 602.2, 602.5, 602.5b | `Game.activation_cost`/`begin_activating`/`activate_ability` | `scenarios/test_activated_abilities.py` |
| An ability as an object on the stack | CR 113.1c, 405.1, 113.7, 113.7a, 608.2n | `AbilityOnStack` in `machines/triggers.py` | `scenarios/test_triggered_abilities.py` |
| A mana ability skipping the stack | CR 605.1a, 605.3b, 605.5 | `Game.activate_ability`, with all four CR 605.1a criteria of the 2026-08-19 release: no target, could add mana, not a loyalty ability (enforced now - Ugin, Eye of the Storms' `0: Add {C}{C}{C}.` is a loyalty ability and takes the stack), and - checked by `moves_a_library_card` on the printed text, which is also what the rule's replacement-effect caveat asks - a cost and effect that move no card to or from a library | `scenarios/test_activated_abilities.py`, `scenarios/test_loyalty_abilities.py` |
| Loyalty abilities | CR 113.5, 606 | A loyalty symbol in a cost makes the ability a loyalty ability (CR 606.2, parsed with a signed amount; the X of a `-X` cost is unchosen). Activation is refused outside the controller's main phase with an empty stack, more than once per permanent per turn (CR 606.3 - per permanent, not per ability), and for a negative cost beyond the counters (CR 606.6); paying adds or removes loyalty counters as the cost (CR 606.4, 107.7). A planeswalker at zero loyalty goes to its owner's graveyard inside `Game.check_state_based_actions` (CR 704.5i, 306.9). Loyalty abilities take the stack, not the mana fast path (CR 605.1a's "not a loyalty ability" criterion, 605.5). Not modelled: choosing X, CR 606.5's combining of multiple loyalty costs, damage removing loyalty counters (CR 306.8, 120.3c), and the effect halves of the pool's walkers (no registry entries). | `machines/abilities.py` (`CostKind.LOYALTY`, `LoyaltyCost`), `machines/cost.py`, `Game.why_cannot_activate`/`activate_ability`, `planeswalkers_with_zero_loyalty` | `scenarios/test_loyalty_abilities.py`, `test_abilities.py` |
| Cast triggers, and what is not cast | CR 601.2, 603.2g, 110.2a | `Game.put_on_stack`, `Game.put_onto_battlefield` | `scenarios/test_triggered_abilities.py` |
| The intervening *if* | CR 603.4, 608.2a | `intervening_if_holds`, `Game._resolve_ability`. Unreadable clauses fail closed with an `InterveningIfNotice`. Read now, on top of the shapes listed on the function itself: the werewolves' "no spells were cast last turn" and "a player cast two or more spells last turn" (`_spells_cast_last_turn_holds`, answered from `Game.spells_cast_last_turn` - the snapshot of `spells_cast_this_turn` taken as a turn begins, CR 601.2a) | `scenarios/test_triggered_abilities.py`, `scenarios/test_transformed_characteristics.py` |
| What mana was spent to cast a spell, and whether it was kicked - read by an intervening *if* | CR 601.2h, 702.33d, 608.2a | `Game.note_cast` records `CostPayment.mana_payment.spend` and `Casting.kicked` onto `CastRecord` (`mana_spent`, `kicked`) as the spell goes on the stack; `intervening_if_holds` reads them back for "it was kicked" (Sowing Mycospawn), "no mana was spent to cast it" (Vexing Bauble), and "[mana symbols] was spent to cast it" (Wistfulness, Drowner of Truth). **CR 608.2a's own second check, on resolution, used to fail this closed for every ETB ability of this shape (W7b)**: `resolve_top` popped `Game.cast_records[spell.id]` immediately after `enter_the_battlefield`, before the triggered ability it had just created ever got a turn to resolve, so `_intervening_if_still_true`'s recheck always read `cast_record`'s empty-record fallback - "nothing was spent" - and Wistfulness's own draw-two-discard-one silently never happened even though the trigger had correctly gone on the stack. Fixed by not popping the record for a permanent's own resolution branch at all (only the non-permanent, straight-to-graveyard branch still pops it immediately, since nothing later needs to recheck a spell that never created a further ability of its own) | `scenarios/test_mana_spent_intervening_if.py`, `scenarios/test_cast_triggers.py` |
| Transforming a permanent, and a transformed permanent's characteristics | CR 701.27a, 701.27g, 712.8d, 712.8e, 712.14a, 712.18, 202.3b, 109.3 | `CardState.transform` flips the flag; `CardState.up_face` is what makes it mean anything - it returns `Card.back_face` while `transformed` is set, so `name`, `types`, `subtypes`, `supertypes`, `colors`, `oracle_text`, `keywords`, `mana_cost`, `power`, `toughness` and `loyalty` are all the back face's (CR 712.8e), and `machines/layers.printed_characteristics` composes them the same way. Mana value deliberately does **not** move: CR 202.3b/712.8e calculate it from the front face's mana cost, which is what `CardState.mana_value` encodes (it is also where an MDFC land face's 0 comes from, CR 712.8f). Abilities move with the face because CR 109.3 counts them as characteristics: `activated_abilities_of(card, face)` and `machines/triggers.triggers_for` both filter on `CardState.up_face_name`, so a transformed Ajani, Nacatl Pariah has Ajani, Nacatl Avenger's three loyalty abilities and none of his front face's, and Duskwatch Recruiter swaps its `{2}{G}` ability for Krallenhorde Howler's cost reducer. `Game.enter_the_battlefield`/`put_onto_battlefield` take `transformed=` for CR 712.14a's "onto the battlefield transformed", set **before** the move so CR 306.5b's loyalty counters are read off the back face - without that a creature face returned transformed as a planeswalker arrived at 0 loyalty and died to CR 704.5i. `"transform this creature."` is read off printed text by `_parse_transform_clause` (no registry row), and the werewolves' two intervening *if* clauses ("if no spells were cast last turn", "if a player cast two or more spells last turn") are answered from the new `Game.spells_cast_last_turn` snapshot. Not modelled: casting a nonmodal DFC transformed (CR 712.8c), double-faced *tokens* (CR 701.27a), meld (CR 712.8g), and convert (CR 701.28) | `scenarios/test_transformed_characteristics.py`, `scenarios/test_mass_counter_placement.py`, `scenarios/test_reflexive_triggered_abilities.py`, `scenarios/test_triggered_abilities.py` |
| Stack resolution | CR 608 | `Game.resolve_top` | `scenarios/test_stack.py` |
| Countering | CR 701.6 | `machines/effects.py` | `scenarios/test_stack.py` |
| Playing a land, and the land-play allowance | CR 116, 305, 305.2, 305.2a, 305.2b, 305.3, 305.4, 611.3d | `Game.play_land`, with the CR 305.2a comparison in `Game.why_cannot_play_land`/`can_play_land`: the allowance (`Game.land_allowance`) is one land (CR 305.2) plus the additional land plays static abilities grant their controller (CR 611.3d), read through `machines/layers.ADDITIONAL_LAND_PLAYS` - a per-card registry, since static ability text is not parsed; Azusa, Lost but Seeking is the entry, and her "on each of your turns" needs no condition because the allowance is only consulted for the active player (CR 305.3). CR 305.4's "put" is honoured by construction: `put_onto_battlefield` never increments `lands_played`. Not checked: priority possession (CR 116.2a's "any time they have priority") | `scenarios/test_special_actions.py`, `scenarios/test_land_drops.py`, `scenarios/test_fetching_a_land.py` |
| Playing a modal double-faced card's land face | CR 712.8a, 712.8f, 712.12 | `Card.land_face` is the mirror of `Casting.base_cost`'s MDFC read - Scryfall leaves an MDFC's front-only `is_land` blind to a back face like Witch-Blessed Meadow, so `Game.play_land` also accepts a card whose *back* face is a land, records the choice on `CardState.land_face_played`, and `types`/`subtypes`/`oracle_text`/`mana_cost`/`name` read that face once it is set (CR 712.8f). `machines/triggers.triggers_for` skips an ability whose `BaseAbility.face` is the other face, so the front creature's "when this creature enters" line does not fire off a land drop. `transformed` (CR 701.27a) is untouched - this is a one-time choice at play, never a later transform | `scenarios/test_mdfc_land_play.py` |
| A double-faced creature's power, toughness, oracle text and colors | CR 712.8a, 712.8d, 712.8f | **Fixed defect:** Scryfall leaves the top-level `power`, `toughness`, `oracle_text` and `colors` null on a `transform` or `modal_dfc` card and puts each face's own values on `card_faces` instead - `machines/layers.py`'s `printed_characteristics` and `CardState.power`/`.toughness`/`.oracle_text` read only the top-level fields, so every double-faced creature (Duskwatch Recruiter, Delver of Secrets, Ajani Nacatl Pariah, The Legend of Roku, Disciple of Freyalise, Drowner of Truth, Witch Enchanter) had base power `None` and toughness `None`, in combat and in state-based actions alike. `combat._power_of`'s `power or 0` then folded that `None` into a real 0, so the creature assigned no combat damage; `Game._dies_to_state_based_action`'s `None`-toughness branch left it alive at any amount of damage (CR 704.5g never fires on a toughness that is not a number). Both machines now read `CardState.up_face` - the land face when `land_face_played` names one (CR 712.8f, mirroring the row above), otherwise `Card.front_face` (CR 712.8a, 712.8d) - before falling back to the top-level fields, which is still correct for every single-faced card. `combat._power_of` no longer collapses a genuinely uncomputable power (a printed `*` with no readable characteristic-defining ability) into 0 either: it returns `None` and the caller records an `UndefinedPowerNotice` (`Game.undefined_power_notices`) and skips the assignment instead of asserting a number. `CardState.name` has since been fixed the same way (see the row below): it now reads `up_face` too, instead of `card.name`'s combined "Front // Back" string. `CardState.transformed` now feeds characteristics too - a transformed Delver of Secrets **is** a 3/2 flier - see the "Transforming a permanent" row above, which supersedes this sentence | `scenarios/test_double_faced_creature_characteristics.py` |
| A double-faced object's name, and a spell's effect and target requirements | CR 201.1, 712.8a, 712.8c, 712.8d, 712.8f, 712.11 | **Fixed defect, third instance of the same family.** `CardState.name` still read `card.name` - Scryfall's combined "Front // Back" string - rather than `up_face`, even though `.oracle_text`/`.power`/`.toughness`/`.mana_cost` had already been fixed to do exactly that; a dozen scenario assertions had keyed lookups off the combined name for a double-faced permanent sitting on its front face and were fixed to name the front face alone rather than left as the reference. Separately, `Game.resolve_top` looked up a resolving spell's effect with `effect_for(spell.card.name, spell.card.oracle_text)` - the raw `Card` fields, null for a `modal_dfc`/`transform` spell - so every modal-DFC spell (Shatterskull Smashing, Valakut Awakening, Sink into Stupor, Turntimber Symbiosis) silently resolved to nothing; `Game.cost_reduction_for`, `Game.static_cost_modifiers_for`, `Game._ability_removed` (an ability-loss check), `machines/combat.py`'s "can't be blocked" reader and evasion-notice text, and `machines/layers.py`'s `effects_for` (every layer-computed static/pump/anthem ability) had the identical bug and are fixed alongside it. `machines/targeting.targeting_profile` and `machines/modes.modal_profile` had a variant of the same defect one level down - they parse a spell's targeting/modal shape off a raw `Card`, before any `CardState` exists, so `spell.oracle_text`'s fallback was not available to them; `Card.front_oracle_text` is the new `Card`-level fallback (mirroring `Casting.base_cost`'s existing one for `mana_cost`), and both now read it instead of `card.oracle_text`. Without it, casting one of these spells and choosing any target raised "too many targets ... at most 0", because the spell's printed target requirement was never read from its (null) text. Of the four MDFC spell fixtures, Sink into Stupor's clause shape ("return target spell or nonland permanent ... to its owner's hand") was already one `machines/effects.py`'s clause parser reads end to end. **W13 closes the other three** (Shatterskull Smashing's X-damage-divided-and-doubled, Valakut Awakening's put-cards-away-then-draw-more, Turntimber Symbiosis's look-seven-put-a-creature-onto-the-battlefield) - see "Reading a division off the card..." above for the first and their own rows in "Cards from the metagame" below for the other two. All six scenarios in `scenarios/test_mdfc_spell_side.py` pass with no `xfail` left | `scenarios/test_mdfc_spell_side.py`, and the corrected assertions in `scenarios/test_double_faced_creature_characteristics.py`, `scenarios/test_dies_trigger_scope.py`, `scenarios/test_mana_spent_intervening_if.py`, `scenarios/test_search_as_a_clause.py`, `scenarios/test_triggered_abilities.py`, `scenarios/test_tokens.py` |
| Damage and lethal damage | CR 120, 704.5g | `models/card_state.py` | `scenarios/test_removal.py` |
| Targeting a permanent or a player | CR 115.1 | `TargetRef` in `models/card_state.py` | `scenarios/test_damage_to_players.py` |
| Damage to a player, life gain and loss | CR 118, 119.2, 120.3a | `Game.deal_damage_to_player`, `Player.gain_life`/`lose_life` | `scenarios/test_damage_to_players.py` |
| Losing the game at zero life | CR 104.2a, 704.5a | `Game.check_state_based_actions` | `scenarios/test_damage_to_players.py` |
| Turn-based actions: untap, draw, cleanup | CR 703.3, 703.4c, 703.4d, 703.4n, 703.4p | `Game.turn_based_actions` | `scenarios/test_turn_based_actions.py` |
| Mana pools emptying as each step and phase ends | CR 703.4q, 500.5, 106.4 | `Game.empty_mana_pools`, run at every step boundary `Game.advance` and `Game.advance_to` cross - a step-end action, so upkeep mana never reaches the main phase, while mana floated during a step stays spendable until that step ends. The player is said to lose it (CR 106.4); replacement effects that keep mana from being lost (Horizon Stone and friends) are not modelled. | `scenarios/test_mana_pool_emptying.py` |
| Turn-based actions: the combat declarations | CR 703.4i, 703.4j, 703.4k, 508.1, 508.1f, 508.8, 500.11, 614.10a, 509.1, 509.2a, 802.4, 701.26a, 702.20b, 506.4 | `Game.declare_attackers_step`/`declare_blockers_step`, dispatched by `Game.turn_based_actions` on the automatic path: each step asks its player through the decision machinery (`DECLARE_ATTACKERS`, `DECLARE_BLOCKERS`) and performs through the existing `declare_attackers`/`declare_blockers`. CR 508.8's skip of the declare blockers and combat damage steps when nobody was declared is in `advance`. Attack-declaration tapping fires `BECOMES_TAPPED` (CR 508.1f, not a cost) except under vigilance (CR 702.20b) | `scenarios/test_combat_turn_based_actions.py` |
| Maximum hand size and the cleanup discard | CR 402.2, 514.1, 701.9b, 608.2d | `Player.discard_to_maximum_hand_size` asks through `Game.ask_cleanup_discard`, a `DecisionKind.CHOOSE_CARDS` question: a scripted answer, then `Game.decisions.provider` (a live player outside the engine), then the back of the hand as the unscripted, unprovided default - the same fallback this used before the decision routed through `Game.ask`, so no existing scenario moved | `scenarios/test_turn_based_actions.py` |
| Wiping marked damage in cleanup | CR 514.2, 703.4p | `Game.remove_all_damage` | `scenarios/test_turn_based_actions.py` |
| Losing to an empty library | CR 104.3c, 121.4, 704.5b | `Player.draw_up_to`, `Game.check_state_based_actions` | `scenarios/test_state_based_actions.py` |
| Toughness 0 or less, counters included | CR 704.5f | `Game.check_state_based_actions`, `CardState.toughness` | `scenarios/test_state_based_actions.py`, `scenarios/test_counters.py` |
| Counters on permanents and players | CR 122.1, 122.1a, 122.1f, 122.2 | `Counter`/`Counters` and `CardState.counters` in `models/card_state.py`, `Player.counters` | `scenarios/test_counters.py` |
| +1/+1 and -1/-1 annihilating | CR 122.3, 704.5q | `CardState.annihilate_counters`, `counter_state_based_actions` | `scenarios/test_counters.py` |
| The layer system | CR 613 | `machines/layers.py` | `test_layers.py` |
| Counters in layer 7c | CR 613.4c | `machines/layers.py` reads `CardState.counters` | `test_layers.py`, `scenarios/test_counters.py` |
| Counters as a cost | CR 118.3, 122.1, 122.6, 602.2b | `ComponentKind.PLACE_COUNTERS`/`REMOVE_COUNTERS` in `machines/cost.py`, built by `place_counters_cost`/`remove_counters_cost`. The cost shape is parsed off the ability's own text, not keyed by card name: `cost_component_for_phrase` reads the self-referential "Put N \<kind> counter(s) on this \<type>" and "Remove N \<kind> counter(s) from this \<type>" templates (Devoted Druid's -1/-1, Walking Ballista's +1/+1) into an empty-cards component that `Game.activation_cost`'s existing self-reference fill-in (the same one `exert_cost`/`exile_cost` already use) completes with the ability's own permanent. `_why_not_remove_counters` refuses the cost outright, before anything is spent, when the permanent does not have that many counters (CR 118.3, mirroring the already-tapped-permanent case the rule states); `_why_not_place_counters` only needs the permanent to still be there to receive one. Both place and remove happen at cost-payment time - during activation (CR 602.2b), before the ability that carries them ever resolves - so a -1/-1 counter's toughness drop, or a pairwise annihilation against an existing +1/+1 counter (CR 704.5q), is visible immediately, and CR 704.5f's zero-toughness state-based action can end the permanent before its own ability resolves (the classic Devoted Druid line: two activations, no Vizier of Remedies, and the second cost's counter is the one that kills it). The rewind (CR 733.1) reuses the loyalty cost's `_remember_counters`/deep-copy pattern rather than `CostComponent._remember`'s by-reference snapshot, which would otherwise record the mutation as already having happened. Not covered: a printed cost naming a *chosen* target rather than "this \<type>" (no printing in the pool needs it, and this builder has no target-resolution hook at cost-build time), and a cost that spreads a total across several permanents at once - The Filigree Sylex's "Remove ten oil counters from among permanents you control" - which is a distribution problem this builder does not attempt; both shapes fall through `cost_component_for_phrase` to `None`, and `Game.activation_cost` turns that into a raised refusal rather than a silent free activation | `scenarios/test_counters_as_a_cost.py`, `test_cost.py` |
| Characteristic-defining abilities that define P/T, in sublayer 7a | CR 604.3, 604.3a, 208.2a, 208.5, 613.4a | `define_power_toughness` (both halves) and `define_power` (power only - Nighthawk Scavenger's toughness is a plain printed number), `LayerContext`, `Characteristics.numeric_power_toughness` in `machines/layers.py`. `Game.computed_board()` builds the `LayerContext` (every graveyard, plus a per-controller mapping) fresh on every call and hands it to `ContinuousEffects.board`, so `Game.power_of`/`toughness_of`/`characteristics_of` - and everything that reads them: combat, state-based actions, targeting - see a graveyard-counting CDA's real answer rather than an empty world. Three graveyard-reading shapes are covered: every graveyard (Tarmogoyf), only the controller's own (Boneyard Wurm, via `LayerContext.graveyard_of`), and every graveyard except the controller's own (Nighthawk Scavenger, via `LayerContext.opponents_graveyard_of`) | `test_layers.py`, `scenarios/test_characteristic_defining_abilities.py` |
| Continuous effects from static abilities, for the cards in the registry | CR 604.2, 113.3d, 611, 613 | `LAYER_EFFECTS` in `machines/layers.py` | `scenarios/test_static_abilities.py`, `scenarios/judge/test_judge_layers.py` |
| Continuous effects created by a resolving spell or ability, with a duration | CR 611.2, 611.2a, 611.2b, 611.2c, 613.7a, 613.7b, 514.2, 703.4p, 500.5b | `Duration`, `ContinuousEffects` in `machines/layers.py`; `create_continuous_effect` in `machines/effects.py`. **Fixed defect:** "Target creature gets +N/+N and gains \<keyword> until end of turn." (Give In to Violence) used to reach `machines/effects.py` and do nothing at all, with no `LayerNotice` recorded - `split_effect_clauses` cuts the sentence into a pump clause and a keyword clause on its own "and" separator before any clause parser ever saw it whole, and neither half alone matched `_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s pure-pump-or-pure-keyword shape, so the card fell through `effect_for` to no effect and no record. `_merge_continuous_pump_keyword_clauses` now undoes that cut (forward order and, defensively, the unattested reverse "gains \<keyword> and gets +N/+N") generically off oracle text and hands the whole spell to `create_continuous_effect`, so it reaches `parsed_layer_effects`'s existing four-shape parser exactly like a plain "gets +N/+N until end of turn." already did - a keyword this engine does not model (Adamant Will's indestructible) or more than one granted keyword (Aerial Maneuver) still reaches that parser and comes back as a `LayerNotice` rather than silence. | `test_layers.py`, `scenarios/test_continuous_effects_with_a_duration.py`, `scenarios/test_continuous_pump_and_keyword_grant.py` |
| Putting N counters on *each member of a group* ("each creature you control", "each Cat you control"), as opposed to something targeted | CR 122.1, 205.2a, 205.3, 613.4, 613.5 | `_parse_put_counters_on_group_clause` in `machines/effects.py`, the group-wide twin of `put_counters_on_ability_targets`'s "on target X". Reads the *computed* board (CR 613.5), not the printed type line, so a permanent that gained a subtype only through a continuous effect still counts. A card-type qualifier ("creature") and a creature-subtype qualifier ("Cat") are both read off the same `[a-z]+` group - Leyline of Abundance's fixed-amount `{6}{G}{G}` activation and Ouroboroid's own "where X is this creature's power" variable-magnitude trigger. **Now proven against Ajani, Nacatl Pariah's own printed "+2: Put a +1/+1 counter on each Cat you control."**, driven through a live game: his back face's abilities are reachable since `CardState.transformed` feeds characteristics (see the "Transforming a permanent" row above), so the former xfail in `scenarios/test_mass_counter_placement.py` is a passing test that transforms him, activates the `+2` and checks the counter lands on Ocelot Pride and not on Ajani himself, who is no longer a Cat (CR 205.3). The clause shape is still also proven directly against Ocelot Pride, a real single-faced Cat creature. | `scenarios/test_mass_counter_placement.py` |
| W7a: the long tail of activated abilities - nine cards whose effect clause was previously unread | CR 122.1, 700.7, 201.5, 701.26b, 700.6, 603.12, 400.2, 702.189a, 107.3a | Nine self-contained parsers in `machines/effects.py`, none of them table rows: **Walking Ballista**'s `{4}: Put a +1/+1 counter on this creature.` and **The Filigree Sylex**'s `{T}: Put an oil counter on ...` - `_parse_put_counters_on_self_clause`, the self-referential twin of the group-wide shape above, reading `ability.source(game)` rather than a target. **Devoted Druid**'s "Put a -1/-1 counter on this creature: Untap this creature." - `_parse_untap_self_clause`; the cost side already worked (see "Counters as a cost" above), only the untap effect was missing, and the Vizier-less loop it enables terminates correctly on CR 704.5f once toughness reaches 0. Both self-referential shapes now also read a card's own **printed name** standing in for CR 700.7's "this \<type>" (CR 201.5) - `Game._self_normalized_effect_text`/`_cost_refers_to_self` - which is what The Filigree Sylex ("... on The Filigree Sylex") and Grist, the Hunger Tide ("... on Grist") both print instead; a sibling wave's own `_exiles_itself_by_name` covers the same CR 201.5 self-reference for an `Exile <name>` cost (Abstergo Entertainment's own "Exile Abstergo Entertainment"), so the two coexist rather than duplicate. The Filigree Sylex's second ability, "Destroy each nonland permanent with mana value equal to the number of oil counters on ...", reuses Engineered Explosives's existing mass-destruction-by-own-counters shape once normalised; its third ability's "Remove ten oil counters from among permanents you control" stays the distribution refusal the "Counters as a cost" row above already documents - unchanged, still correctly a raised `ValueError`, never a free activation. **The Legend of Roku // Avatar Roku**'s `{8}: Create a 4/4 red Dragon creature token with flying and firebending 4.` needed two fixes: CR 702.189a's "Firebending N" as a leveled token keyword (`_LEVELED_TOKEN_KEYWORDS`), and a whole-text token-clause parser (`_parse_whole_text_token_clause`) that reads the clause without going through `split_effect_clauses` first, whose bare-"and" cut otherwise slices "with flying and firebending 4" into two clauses neither of which parses alone - proven end to end through a real `.transform()` and `activate_ability`, now that "Transforming a permanent" (above) makes the back face's abilities reachable. **Abstergo Entertainment**'s "Return up to one target historic card from your graveyard to your hand, then exile all graveyards." needed CR 700.6's "historic" qualifier - `TargetRequirement.historic`, checked as a disjunction across card type, supertype, *and* subtype at once, a shape none of the existing per-field AND-only restrictions could express. **Agatha's Soul Cauldron**'s "Exile target card from a graveyard. When a creature card is exiled this way, put a +1/+1 counter on target creature you control." is CR 603.12's reflexive-trigger shape again, but conditioned on the *type* of what the first sentence exiled rather than on a player's choice - `_parse_exile_target_card_reflexive_creature_counter`, reusing `Game.create_reflexive_trigger` rather than a second reflexive primitive; `profile_for_text`'s reflexive-tail cut (see "Trigger conditions the matcher cannot read" below) was widened from "when you do," to also match "when \<event\> this way," so the outer ability still announces only its own target. **Grist, the Hunger Tide**'s `+1` ("... then mill a card. If an Insect card was milled this way, put a loyalty counter on Grist and repeat this process.") is a self-terminating loop reading the specific card `_mill` (now returning what it moved) just milled, not the graveyard generally - `_parse_create_token_mill_repeat_clause`. **Tyvar, Jubilant Brawler**'s `-2` ("Mill three cards, then you may return a creature card with mana value 2 or less from your graveyard to the battlefield.") is a resolution-time `MAY`/`CHOOSE_CARDS` choice among the whole graveyard after the mill (CR 400.2: no "just arrived" exception) rather than a target - `_parse_mill_then_may_return_creature_clause`. **Fiend Artisan**'s `{X}{B/G}, {T}, Sacrifice another creature: Search your library for a creature card with mana value X or less, ...` needed CR 107.3a's X extended from spells onto activated abilities for the first time: `AbilityOnStack.x_value`, threaded through `Game.activation_cost`/`begin_activating`/`activate_ability`'s new `x_value` parameter (`ManaCost.with_x` folds it into the paid cost) and read back by `activated_effect_for`'s own `substitute_x` fallback, mirroring `effect_for`'s existing spell-side handling exactly. | `scenarios/test_activated_ability_effects.py` |
| A duration-bearing team-wide pump with no target, its magnitude computed at resolution ("Creatures you control get +N/+N until end of turn", optionally "where X is the number of \<type> you control") | CR 611.2, 611.2a, 611.2c, 613.1d, 613.4c | `_MASS_PUMP_UNTIL_EOT_RE`/`_mass_pump_until_eot_builder` in `machines/layers.py` build the continuous effect (per-target `ContinuousEffect`s exactly like `_pump_and_keyword_builder`'s own single-subject shape, not a live `Selector` the way the anthem's CR 611.3 shape needs); `_mass_pump_ability_effect`/`_mass_pump_spell_effect`/`_run_mass_pump` in `machines/effects.py` compute the concrete, fixed-now group of creatures (CR 611.2c: "any objects that come under [that] control later aren't affected") and, when the card prints one, resolve the "where X is ..." magnitude through `count_expression` **once**, substituting a literal number for "X" before handing the sentence to the layers parser - never a live re-read, which is what would let a creature entering later retroactively grow the pump. Closes the row this file used to carry for "a team-wide temporary pump with no target": Violent Outburst's own "+1/+0" and Craterhoof Behemoth's "+X/+X and trample, where X is the number of creatures you control" both resolve for real now. The `Duration.UNTIL_END_OF_TURN`-only gate in `_parse_mass_pump_clause` matters: without it, this shape would misfire on Glorious Anthem's own durationless CR 611.3 anthem (which every resolving *spell* passes through `effect_for` too, permanents included) and double the bonus by storing a second, redundant copy of the same static effect. | `scenarios/test_cascade.py::test_violent_outbursts_own_pump_actually_pumps`, `scenarios/test_computed_magnitude_team_pump.py` |
| A shared count expression - "the number of \<type>\[s] you control" / "\<type> cards in your graveyard" - fixed once at the moment a caller evaluates it (CR 611.2c) | CR 205.2a, 613.4, 613.5 | `count_expression(phrase: str) -> Callable[[Game, str], int] \| None` in `machines/effects.py`, returning a function of `(game, controller)` rather than a value, so the caller decides exactly when CR 611.2c's magnitude is fixed. Reads only a single CR 300.1 card type as the qualifier ("creature[s]") - a coloured, named, or compound qualifier ("green creatures", "Human creatures", "artifact or enchantment permanents") is not read and returns `None` rather than being guessed at; no card in the pool needs one of those shapes yet. "You control" reads the computed board (CR 613.5); "in your graveyard" reads `CardState.types` directly, since a graveyard card has no continuous effects to compute. Consumed by Craterhoof Behemoth's own pump magnitude and by Grist, the Hunger Tide's -5 ("Each opponent loses life equal to the number of creature cards in your graveyard", read by `_parse_each_opponent_loses_life_equal_to`). | `scenarios/test_computed_magnitude_team_pump.py`, `scenarios/test_count_expression_life_loss.py` |
| "Target permanent becomes \<type> in addition to its other types until end of turn." - an *additive* layer 4 type change, as opposed to Karn, the Great Creator's replacing "becomes a[n] \<type> creature ..." | CR 613.1d, 611.2 | `_BECOMES_TYPE_IN_ADDITION_RE`/`_becomes_type_in_addition_builder` in `machines/layers.py`, reusing `add_type` (already load-bearing for earthbend's creature-type grant) rather than a `set`-style replacement. Liquimetal Coating is the card. | `scenarios/test_type_changing_in_addition_to.py` |
| Loyalty, and a planeswalker at zero | CR 122.1e, 209.1, 306.5, 306.9, 704.5i | `CardState.loyalty`, `planeswalkers_with_zero_loyalty` | `scenarios/test_counters.py` |
| The legend rule | CR 205.4d, 704.5j | `Game.check_state_based_actions` | `scenarios/test_state_based_actions.py` |
| Countering an ability | CR 113.9, 115.2, 608.2b, 611.2b, 613.1f | `Game.counter`, `Game.find_ability_by_id`/`resolve_target`, Tishana's Tidebinder in `machines/effects.py`, `Game._still_has_ability` for the layer 6 half | `scenarios/test_countering_an_ability.py`, `scenarios/test_targeting_an_ability.py`, `scenarios/test_continuous_effects_with_a_duration.py` |
| Fizzling | CR 608.2b | `Game.spell_fizzles`, `Game.resolve_top` | `scenarios/test_stack.py` |
| Multiplayer: turn order, priority, leaving the game | CR 104.2a, 800.4, 800.7, 103.8a | `machines/turn.py`, `machines/priority.py`, `Game._player_left` | `scenarios/test_multiplayer.py` |
| Declaring attackers | CR 508 | `machines/combat.py` | `scenarios/test_declaring_attackers.py` |
| Summoning sickness | CR 302.6, 508.1a, 602.5a, 702.10c | `CardState.summoning_sick` (the raw entered-this-turn fact, on every permanent - a land that becomes a creature is restricted from when it entered), `CardState.is_summoning_sick` (the rule's answer: sick AND creature), `Game.begin_turn_for`, `Game.can_activate_tap_ability`, consulted by `CostPayment.tap_for_mana` | `scenarios/test_summoning_sickness.py` |
| Declaring blockers | CR 509 | `machines/combat.py` | `scenarios/test_declaring_blockers.py` |
| Combat damage | CR 510 | `Game.combat_damage` | `scenarios/test_combat_damage.py` |
| First strike, double strike | CR 702.7, 702.4, 510.4 | `machines/combat.py` | `scenarios/test_first_strike.py` |
| Flying, reach, menace, trample, vigilance, haste | CR 702.9, 702.17, 702.111, 702.19, 702.20, 702.10 | `machines/combat.py` (read off Scryfall `keywords`) | `scenarios/test_evasion.py` |
| Defender | CR 702.3a-b | `attack_refusal` in `machines/combat.py` | `scenarios/test_defender.py` |
| Deathtouch: lethal assignment and the state-based action | CR 702.2a-c, 704.5h | `lethal_for` in `machines/combat.py`, `CardState.dealt_deathtouch_damage`/`has_lethal_damage` | `scenarios/test_deathtouch.py` |
| Lifelink | CR 702.15b, 120.3f, 702.15e | `_deal_combat_damage` in `machines/combat.py` | `scenarios/test_lifelink.py` |
| Basic landwalk | CR 702.14a-c, 305.6 | `landwalk_refusal` in `machines/combat.py` | `scenarios/test_landwalk.py` |
| Combat reading the computed board | CR 510.1a, 613.5 | `_power_of`/`_toughness_of`/`has_keyword` in `machines/combat.py`, through `Game.power_of` | `scenarios/test_delirium.py` |
| Casting timing, and flash | CR 117.1a, 304.1, 307.1, 302.1, 505.6a, 702.8a | `why_cannot_cast_now` in `machines/casting.py`, checked as a `Casting` is created (CR 601.3) | `scenarios/test_flash.py` |
| Hexproof, at announcement | CR 702.11a-b, 601.2c | `Casting._hexproof_refusal` | `scenarios/test_hexproof.py` |
| Kicker, as an optional additional cost | CR 702.33a, 702.33c-d, 118.8a | `Casting.pay_kicker`, `Casting.kicked` (carried onto `Game.cast_record(spell).kicked` by `Game.note_cast`, which the linked "if it was kicked" ability reads - see the mana-spent row above) | `scenarios/test_kicker.py` |
| An activated ability that functions outside the battlefield | CR 602.1a, 602.2, 602.5 | `KeywordActivation` in `machines/keywords.py` | `scenarios/test_cycling.py` |
| Cycling and typecycling | CR 702.29a-b, 702.29e-f | `cycling_activation`/`cycle` in `machines/keywords.py` | `scenarios/test_cycling.py` |
| Equip, attachment, and CR 704.5n | CR 702.6a, 301.5a-b, 701.3a, 701.3d, 704.5n, 307.5 | `equip_activation`/`equipment_state_based_actions` in `machines/keywords.py`, `CardState.attached_to` | `scenarios/test_equip.py` |
| A keyword line that *is* a triggered ability | CR 702.1, 603.1, 603.2, 603.3 | `keyword_triggered_abilities` in `machines/keywords.py` writes each rule's own expansion out as a `TriggeredAbility`; `triggers.triggered_abilities_of` returns it beside the printed ones | `scenarios/test_ward.py`, `test_prowess.py`, `test_cascade.py`, `test_persist.py`, `test_mobilize.py`, `test_madness.py` |
| Ward, as a trigger that really fires | CR 702.21a, 701.6a-b | `TriggerEvent.BECOMES_TARGET`, emitted by `Casting._emit_becomes_target` (CR 601.2c); `ward_triggers`/`WardTrigger` is the optional payment | `scenarios/test_ward.py` |
| Prowess, as far as its trigger | CR 702.108a, 702.108b | `_prowess_ability` in `machines/keywords.py`, matched by `condition_matches` on the cast event | `scenarios/test_prowess.py` |
| Cascade | CR 702.85a, 702.85c | `_cascade_ability` and `cascade` in `machines/keywords.py`; the source is the *spell*, which `Game.emit` asks because CR 702.85a functions on the stack | `scenarios/test_cascade.py` |
| Persist, and last known counters | CR 702.79a, 704.8, 603.10a, 122.2 | `_persist_ability` (intervening *if* included) and `persist_return` in `machines/keywords.py`, `CardState.last_known_counters` | `scenarios/test_persist.py` |
| Persist's intervening *if*, read by the trigger machinery | CR 603.4, 608.2a, 702.79a | `intervening_if_holds` reads "it had no -1/-1 counters on it" off `last_known_counters` | `scenarios/test_persist.py` |
| Mobilize, as far as its trigger | CR 702.181a | `_mobilize_ability` in `machines/keywords.py`, off the CR 508.1 attack declaration | `scenarios/test_mobilize.py` |
| Morph: casting a card face down, and turning it back up | CR 702.37a, 702.37c-e, 708.2, 708.2a-b, 708.4, 708.8, 708.9, 303.4a | `FaceDownCharacteristics` and `CardState.face_down_characteristics`; `Casting._turn_face_down_if_cast_that_way`; `face_down_characteristics`/`why_cannot_turn_face_up`/`turn_face_up_cost` in `machines/keywords.py` | `scenarios/test_morph.py` |
| Madness: the discard replacement, and casting from its pile of exile | CR 702.35a-b, 406.4, 701.9a | `madness_replaces_discard`/`discard`/`madness_annotation` in `machines/keywords.py`, `ExileMarker.MADNESS`, a `KeywordCastOption` in `machines/casting.py` | `scenarios/test_madness.py` |
| Dash, as an alternative cost | CR 702.109a, 118.9, 601.2b | `_option_from_keyword` in `machines/casting.py`; `Game.was_cast_with(spell, "Dash")` records it | `scenarios/test_dash.py` |
| Entwine, charged as well as opened | CR 702.42a, 118.8a, 601.2b | `Casting._charge_entwine`, called by `choose_modes(entwined=True)` | `scenarios/test_entwine.py` |
| Enchant: what an Aura may target and be attached to | CR 702.5a, 702.5c-d, 303.4, 303.4a | `enchant_restrictions`/`why_cannot_enchant` in `machines/keywords.py`, `Casting._enchant_refusal`, `targeting._with_aura_target` | `scenarios/test_enchant.py` |
| Indestructible, as a question the engine can answer | CR 702.12a-c | `is_indestructible`/`indestructible_survives_lethal_damage` in `machines/keywords.py`, off the computed board (CR 613.5) | `scenarios/test_indestructible.py` |
| Exert | CR 701.43a-c, 118.3, 733.1 | `exert` in `machines/keywords.py`, `CardState.exerted`/`untap`, `ComponentKind.EXERT`/`exert_cost` in `machines/cost.py` | `scenarios/test_exert.py` |
| Combat damage that knows its source | CR 120.1, 120.7, 609.7b, 615.8, 702.16e | `_deal_combat_damage` passes `source=` to `Game.deal_damage` and reads the amount actually dealt back | `scenarios/test_lifelink.py`, `test_deathtouch.py` |
| Dredge | CR 702.52a-b, 701.17a | `dredge`/`why_cannot_dredge` in `machines/keywords.py` | `scenarios/test_dredge.py` |
| Owner, separately from controller | CR 108.3, 108.4, 108.4a, 109.4 | `CardState.owner`/`controller_or_owner`, read by `machines/targeting.py` | `scenarios/test_targeting_adjectives.py` |
| Removing a permanent from combat | CR 506.4, 511.3 | `CombatMachine.remove`, `Game.advance` | `scenarios/test_declaring_blockers.py` |
| Exile | CR 406 | `Game.exile_permanent` | `scenarios/test_exile.py` |
| Applying replacement and prevention effects | CR 614.1, 614.5, 614.6, 614.7, 615.1a | `ReplaceableEvent`/`apply_replacements` in `machines/replacement.py` | `scenarios/test_replacement_effects.py` |
| A choice made while an effect resolves | CR 608.2d | `machines/decisions.py`, `Game.ask`/`may`/`may_pay_life`. `Game.ask` tries a scripted `DecisionScript` answer, then `Game.decisions.provider` (a `DecisionProvider` - a live player standing outside the engine, e.g. a server thread), then `default_answer`, and validates whichever of the first two answered against `legal_options` before returning it. Wired to a live provider so far only for the cleanup discard's `CHOOSE_CARDS` kind (see the maximum-hand-size row); every other kind above still only takes scripted or default answers | `scenarios/test_decisions_during_resolution.py`, `scenarios/test_turn_based_actions.py` |
| Energy ({E}) as a payable cost | CR 107.14, CR 118.3, CR 608.2d | `DecisionKind.PAY_ENERGY` (a fixed amount, `Game.may_pay_energy` - the same `affirmative_is_legal`-gated shape `may_pay_life` already uses for CR 119.4, turned to CR 118.3's energy floor instead) and `DecisionKind.PAY_ENERGY_AMOUNT` (a real variable amount from 0 up to however much energy the player has when asked, `Game.pay_any_amount_of_energy`, validated by `Game.ask` the same way `CHOOSE_CARDS`'s count is - the "choose an amount" primitive noted as missing below, now built). Read off a card's own printed text with no per-card row: `_parse_sacrifice_unless_pay_energy` (Static Prison's "unless you pay {E}"), `_parse_target_get_energy_pay_damage` (Galvanic Discharge's "you may pay any amount of {E}", threaded into the damage it deals), `_parse_x_energy_pay_destroy_by_mana_value` (Wrath of the Skies's same variable-amount shape, threaded into a mana-value-ceiling mass destruction). Guide of Souls's own "you may pay {E}{E}{E}. When you do, ..." is CR 603.12's reflexive trigger, and is now wired to this same `may_pay_energy` call too (`_parse_reflexive_pay_energy_clause`, W4) - see its own row below | `scenarios/test_energy_payment.py`, `scenarios/test_counters.py`, `scenarios/test_reflexive_triggered_abilities.py` |
| Scry | CR 701.22a, 701.22b | `Game.scry` | `scenarios/test_scry.py` |
| Surveil | CR 701.25a, 701.25c | `Game.surveil` | `scenarios/test_surveil.py` |
| Shuffling a library | CR 701.24a, 701.24b, 701.24d, 701.24e | `Game.shuffle_library`, `Game.shuffle_seed` | `scenarios/test_shuffling.py` |
| Searching a zone, and the shuffle after it | CR 701.23a, 701.23b, 701.23d, 701.23e, 701.23h, 400.2 | `Game.search_library` | `scenarios/test_shuffling.py` |
| An enters replacement carrying a choice | CR 614.1c, 614.12, 614.12a, 119.4 | `_self_enters_modifiers`/`_pay_life_or_tapped` (the shockland's pay-life-or-tapped choice) and `_choose_a_quality` (the "as [this] enters, choose a color/card name/creature type" shape - Utopia Sprawl, Voice of All, Forsaken Crossroads, Runed Halo, Pithing Needle, Disruptor Flute, Cavern of Souls) in `machines/replacement.py`. The chosen value is recorded generically on `CardState.choice` (`ChoiceKind.COLOR`/`CARD_NAME`/`CREATURE_TYPE`), asked through `DecisionKind.CHOOSE_A_QUALITY`. Only one consumer of "the chosen ..." is wired end to end - the mana-adding trigger clause above; Voice of All's permanent-targeted protection grant already gets a `LayerNotice` for free from the static-ability sweep, and Runed Halo's player-targeted grant, Pithing Needle's and Disruptor Flute's activation/cost restrictions by name, and Cavern of Souls' restricted-mana grant each fail closed with an `UnwiredChoiceNotice` instead of silently doing nothing - see that model's docstring in `machines/replacement.py`. | `scenarios/test_decisions_during_resolution.py`, `scenarios/test_chosen_quality_on_entering.py`, `scenarios/test_mana_adding_triggers.py` |
| The source of a damage event | CR 120.1, 120.7, 120.2b | `Game.deal_damage(..., source=...)`, `ReplaceableEvent.source` | `scenarios/test_prevention_effects.py` |
| Prevention effects with a duration | CR 615.1, 615.3, 615.4, 615.6, 615.7, 615.8, 615.9, 609.7b, 514.2 | `PreventionShield`/`ShieldKind`, `Game.create_prevention_shield`, gathered by `machines/replacement.applicable_effects` | `scenarios/test_prevention_effects.py` |
| Protection, the damage half | CR 702.16e, 702.16a | `Game.protection_from_damage`, `Game.source_has_quality` | `scenarios/test_prevention_effects.py` |
| Protection *granted* by another static ability | CR 613.1f, 702.16a, 702.16g | `machines/layers._INDEFINITE_KEYWORD_AND_PROTECTION_GRANT_RE` reads "[keyword(s), and] protection from A [and from B]" (Akroma's Memorial) as a layer-6 grant, one "Protection from X" ability string per quality, alongside `_indefinite_keyword_grant_builder`'s existing plain-keyword grants. `Game._effective_protection_qualities` is what both `protection_refusal` and `protection_from_damage` now call instead of `protection_qualities(target.card)` directly - it reads the target's own printed protection plus any granted line off its computed `Characteristics.abilities`, so a permanent standing next to Akroma's Memorial is protected the same way Emrakul is protected by its own printed text. Only this one indefinite-grant shape is read; a targeted "gains protection from the color of your choice" (Mother of Runes, Voice of All) needs a colour-choice mechanism this engine does not have yet and is not attempted | `scenarios/test_protection_grants.py` |
| Who owns a card | CR 108.3, 108.3b | `Player.add` stamps `CardState.owner`, so `load_deck` and a scenario board agree | `scenarios/test_starting_a_game.py` |
| Equipment unattaching from an illegal permanent | CR 704.5n | `keywords.equipment_state_based_actions`, dispatched by `Game.check_state_based_actions` | `scenarios/test_equip.py` |
| "Activate only as a sorcery" | CR 602.5d, 307.5 | `Game.why_cannot_activate` | `scenarios/test_activated_abilities.py` |
| Ordering two effects on one event | CR 616.1, 616.1f, 616.1g, 616.2 | `order_effects`, `apply_replacements` | `scenarios/test_replacement_effects.py`, `scenarios/judge/test_judge_replacement_effects.py` |
| A permanent entering tapped or with counters | CR 614.1c, 614.12, 122.6 | `Game.enter_the_battlefield`, `_self_enters_modifiers` | `scenarios/test_replacement_effects.py` |
| Replacing a move to a graveyard | CR 400.6, 700.4 | `Game.put_into_graveyard` | `scenarios/judge/test_judge_dies_triggers.py` |
| Draws and life gain as replaceable events | CR 121.1, 121.2, 121.6, 119.3 | `Game.draw_cards`, `Game.gain_life` | `scenarios/test_replacement_effects.py` |
| Delayed triggered abilities | CR 603.7, 603.7a, 603.7b, 603.7c, 603.7d, 603.7e, 608.3g, 610.2 | `machines/delayed.py`, `Game.create_delayed_trigger`/`delayed_triggers` | `scenarios/test_delayed_triggered_abilities.py` |
| A game that holds its own continuous effects | CR 611.2, 613.7a, 613.7b, 514.2 | `Game.continuous_effects`, `Game.cleanup_step`, `Game.enter_the_battlefield` | `scenarios/test_continuous_effects_with_a_duration.py` |
| The layer engine reaching the state-based actions | CR 613.5, 704.5f, 704.5g | `Game.computed_board`/`power_of`/`toughness_of`, `_dies_to_state_based_action` | `scenarios/judge/test_judge_state_based_actions.py` |
| An ability on the stack as a *resolvable* target | CR 115.2, 608.2b | `Game.find_ability_by_id`, `Game.resolve_target` | `scenarios/test_targeting_an_ability.py`, `scenarios/test_countering_an_ability.py` |
| Losing to ten poison counters | CR 704.5c | `Game._losing_players`, `Player.loses_to_poison` | `scenarios/test_counters.py` |
| Skipping the first draw step, once | CR 103.8a, 103.8c | `TurnMachine.skips_draw`, keyed on `turns_taken` | `test_turn.py`, `scenarios/test_turn_based_actions.py` |
| Extra turns | CR 500.7 | `TurnMachine.grant_extra_turn`, `Game.grant_extra_turn` | `scenarios/test_extra_turns.py` |
| Controlling another player | CR 723.1, 723.1a, 723.1b, 723.3, 723.5, 723.5a, 723.6, 723.8, 723.9 | `TurnMachine.gain_control_of_player`/`controller_of_player`, `PriorityMachine.decider`, `Game.gain_control_of_player`/`why_cannot_decide_for`/`why_cannot_pay_with`/`concede(by=...)` | `scenarios/test_controlling_another_player.py` |
| A cost reduction read off the board, and locking the total cost in | CR 601.2f, 205.2b | `Game.cost_reduction_for`, `Game.determine_total_cost` | `scenarios/test_dynamic_cost_reduction.py` |
| Static cost increases printed on *other* permanents, and Trinisphere's floor | CR 601.2f, 611.3 | `Game.static_cost_modifiers_for` (increases before reductions in `apply_modifications`, the floor applied last), parsed off oracle text by `cost_modifier_effect`/`looks_like_unparsed_cost_modifier` in `machines/cost.py` - unconditional ("Spells cost {N} more to cast"), type-qualified ("Noncreature"/"Nonartifact" spells), per-prior-spell-this-turn (Damping Sphere), and the Trinisphere floor shape. A shape none of these read (Grand Arbiter Augustin IV's controller-relative "Spells your opponents cast cost {1} more to cast") is not applied and is recorded in `Game.cost_modifier_notices` rather than silently skipped | `scenarios/test_costs.py` |
| Protection, the targeting half | CR 702.16a, 702.16b, 702.16g | `protection_qualities`, `Game.protection_refusal`, consulted by `Game.legal_target`. `Game._effective_protection_qualities` folds in a *granted* protection quality too (see the row above), so this reads a permanent's own printing plus whatever another static ability has given it | `scenarios/test_protection.py`, `scenarios/test_protection_grants.py` |
| A plain "can't be blocked" restriction | CR 509.1a | `combat.evasion_restriction_refusal`, read straight off the attacker's own oracle text rather than off `Keyword` - unlike flying, menace, or landwalk, this restriction has no keyword name of its own. Two shapes: unconditional (The Mindskinner) and "can't be blocked by creatures with power N or less" (Questing Beast). A subject is only read self-referentially ("this creature" or the card's own short name before a comma, CR 201.4-style); nothing in the pool grants "can't be blocked" to *another* creature, so that shape is not read. A sentence that opens the same way but is not one of the two - "power N or **greater**" (April O'Neil, Kunoichi Trainee), a colour, or any other qualifier - is not guessed at: `combat.looks_like_unparsed_evasion_restriction` catches it and `block_refusal` records an `EvasionNotice` (dedup'd per attacker) instead of the block silently going through unrestricted *or* silently being refused | `scenarios/test_evasion_restrictions.py` |
| Rechecking a **modal** spell's targets on resolution | CR 608.2b, 700.2c | `Game._resolution_profile` reads the chosen modes and X off `Game.cast_records` - filled by `Casting.cast` through `Game.note_cast` - and asks `profile_for_modes`, so a modal spell's targets are rechecked against the same profile it was announced with | `scenarios/test_variable_target_counts.py` |
| Morph in the layer system | CR 613.2, 708.2 | `machines/layers.printed_characteristics` consults `state.face_down_characteristics`, so `Game.computed_board` reports the nameless 2/2 (CR 702.37c) rather than the printed face - CR 708.2 makes those the copiable values, which is layer 1 | `scenarios/test_morph.py` |
| Match and game containers, and starting a game | CR 100.6, 103.1, 103.2a, 103.3, 103.4, 103.5, 103.5c, 800.6 | `models/match.py` (`Match.start_game`, `register_deck`, `chooser_for_next_game`, `run_mulligans`), `Player.load_deck`/`draw_opening_hand`/`mulligan`/`keep_hand` | `test_match.py`, `scenarios/test_starting_a_game.py`, `scenarios/test_mulligans.py` |
| Drawing the game | CR 104.1, 104.2a, 104.4a, 104.5 | One state-based-action check removing every player still in the game sets `Game.drawn`: `winner` stays None, `is_over` is True, and the losers still leave under CR 104.5. `Match.draws` counts the drawn games, which score for nobody. `Game.end_in_draw` is the staging entry for a draw no check produced | `scenarios/test_drawing_the_game.py` |
| Mass destruction and mass sacrifice: "destroy each `<qualifier>`" / "each player sacrifices all `<qualifier>`" | CR 701.8a, 701.21a, 608.2f, 202.3, 712.8f | `_parse_mass_type_qualifier` reads the qualifier (an optional "nonland " prefix, "permanent[s]" with no restriction, "colored"/"colorless", or a comma/"and"/"or"-joined list of card types with no trailing "permanent" at all - Wrath of the Skies's own template) off the *computed* board (`Game.characteristics_of`); `_parse_mass_mv_rhs`/`_parse_mass_mv_comparison` read the numeric comparison's right-hand side as either a printed constant (Culling Ritual) or a count of counters on the clause's own source (Engineered Explosives's "the number of charge counters on this artifact", via `last_known_counters` once the source has already left as its own activation's cost); `_MASS_WITHOUT_COUNTER_RE` reads an absence-of-a-counter qualifier (Oblivion Stone). `_destroy_matching` snapshots the battlefield once and rechecks each candidate's zone immediately before its own `destroy` call, the same CR 608.2b-shaped recheck `_parse_x_energy_pay_destroy_by_mana_value` already uses for Wrath of the Skies, which shares this grammar but keeps its own dedicated parser above it for its energy-payment right-hand side. `each_player_sacrifices_colored_permanents` is All Is Dust's own dedicated whole-sentence parser (sacrifice, not destroy, so CR 702.12b never applies) rather than reusing the qualifier grammar, since its "permanents ... that are one or more colors" is a relative clause, not an adjective-noun qualifier. `machines/layers.printed_characteristics`'s own `mana_value` also now follows `state.land_face_played` (CR 712.8f) instead of always reading `Card.cmc`, which is Scryfall's *spell*-face mana value for a modal double-faced card even when its land face is up | `scenarios/test_mass_destruction.py` |

| A counterspell's own qualifier, and CR 118.12a's "unless" rider | CR 701.5a, 109.2b, 118.12a, 608.2b | `_COUNTER_TARGET_SPELL_RE` in `machines/effects.py` now accepts an optional qualifier ("noncreature", a colour, a card type) ahead of "spell" - the verb still runs `counter_targets` unconditionally, since CR 115's own qualifier legality is `machines/targeting.py`'s job, not this dispatcher's. "Counter target spell unless its controller pays {N}." (Censor, Mystical Dispute) is `_counter_unless_pays_effect`/`Game.may_pay_mana`, a new `DecisionKind.PAY_MANA` read as CR 118.12a's "may/if not" pair and put to the *targeted* spell's controller, not the counterspell's caster. Only mana already floating in that player's pool can pay it - CR 608.2g's "activate a mana ability right here" is not modelled, so a controller who would need to tap a land to pay is refused as if they had no mana at all | `scenarios/test_counterspells.py` |
| A counterspell's own redirect and rider, read as one paired clause rather than two independent ones | CR 400.7, 608.2c | Force of Negation's "Counter target noncreature spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard." is `_parse_counter_then_exile_instead_of_graveyard_pair`, and `Game.counter` grew a `to_exile` flag for the redirect itself. Access Denied's "Counter target spell. Create X 1/1 ... tokens ..., where X is that spell's mana value." is `_parse_counter_then_create_tokens_by_mana_value_pair`, reading the countered spell's `card.cmc` before it leaves the stack. Both fail the *whole* pair closed (no counter at all) if either sentence does not parse, the same all-or-nothing rule `_parse_anaphoric_clause_pair` already keeps | `scenarios/test_counterspells.py` |
| The CR 118.9 pitch alternative cost, read off inline text rather than a keyword | CR 118.9, 118.9c | `machines/cost.alternative_cost_offers` reads "You may `<cost>` rather than pay this spell's mana cost." (Force of Will) and its "If it's not your turn, you may `<cost>` ..." cousin (Force of Negation, Force of Vigor) off the card's own text; `Casting.use_pitch_cost` builds the `TotalCost` through the existing `total_cost_for_phrase`/`exile_cost`/`CardRequirement` machinery `_option_from_keyword` already used for Evoke and Dash, and refuses the "not your turn" gate when it is the caster's own turn. `_split_cost_phrase` now also splits on a bare "and" (no comma), which Force of Will's "pay 1 life and exile a blue card from your hand" needs and no existing keyword cost had | `scenarios/test_counterspells.py` |
| A compound target this engine cannot fully read fails open rather than wrongly enforced | CR 115.2b | Consign to Memory's "Counter target triggered ability or colorless spell." used to be *actively misread*: `targeting.py`'s `_ABILITY_PHRASE.match` (a bare prefix match) claimed the whole compound was "target activated or triggered ability" and silently dropped "or colorless spell" - `understood=True` with a wrong, enforced restriction, which is worse than not checking at all. It now requires the ability phrase to consume the entire noun phrase (`.end() == len(noun_phrase.rstrip())`), so the compound correctly falls through to `understood=False` (unchecked, per this file's usual convention) while Tishana's Tidebinder's plain "target activated or triggered ability" is untouched. The counter verb itself (`counter_targets`) never cared which half of the "or" was targeted, so a colorless spell is still countered correctly either way; a spell targeting an *ability* still has no announcement-side path to choose one (`docs/engine-coverage.md`'s existing ability-targeting gap, unchanged by this wave) | `scenarios/test_counterspells.py` |
| An activated ability that functions from a hand or a graveyard, printed like any other `[Cost]: [Effect.]` line rather than a CR 702 keyword | CR 113.6j, 113.6m, 113.7a | `abilities.py` reads a `zone`/`zone_rule` off any activated ability whose own cost discards itself (Boseiju's and Otawara's Channel, Waker of Waves' plain ability - CR 113.6j) or whose effect returns itself from its own graveyard (World Breaker - CR 113.6m), off the words alone, no card names. `machines/keywords.off_battlefield_activation` is the general form of `KeywordActivation` cycling and equip already used, built from the printed ability rather than a keyword's fixed expansion; its `generic_effect=True` leaves the ability's resolution to the ordinary per-card path (`Game._effect_of`'s `ActivatedAbility` branch) rather than a `KEYWORD_EFFECTS` row, so the same clause parsers a battlefield ability reaches apply here too. A trailing "This ability costs `[N]` less to activate for each `[quality]` you control" sentence (Boseiju, Otawara) is a **separate static ability** sharing the printed line, not a third clause of the one before it (CR 604.1, and CR 702.41a's Affinity / CR 702.125a's Undaunted are the CR's own precedent for this exact shape) - `_split_off_trailing_cost_reduction` peels it off before `ActivatedAbility.effect` is built, and `Game.activation_cost_reduction_for` reads the quality generically (a CR 205.4a supertype and/or CR 205.2a card type) and applies it through the ordinary `ManaCost.minus` (CR 118.7). World Breaker's own self-return ("Return this card from your graveyard to your hand") is `_parse_self_return_clause`, a plain zone-change of the ability's own source rather than a target. Boseiju's search clause ("search their library for a land card with a basic land type") needed one more fix: `_has_a_basic_land_type` reads CR 305.6's *subtype* question, distinct from `_quality_matcher`'s "basic land" branch which checks the "basic" *supertype* (CR 305.8) - a shockland has a basic land type without being a basic land, so folding the two together would have been narrower than the card actually reads. Waker of Waves' split needed `Game.look_at_top_and_split` (a different wave's primitive); `_merge_look_top_split_hand_graveyard_clauses` is its own consumer of that primitive, alongside `_merge_look_top_reveal_to_hand_clauses`'s Duskwatch Recruiter | `scenarios/test_off_battlefield_activation.py` |
| Chalice of the Void's "mana value equal to charge counters" trigger, and "counter that spell" read generically | CR 202.3e, 107.3g, 107.3i, 607.1, 701.6a | `condition_matches`'s `_MANA_VALUE_EQUALS_COUNTERS` shape already recognised the cast-trigger condition, but compared the charge-counter count against the spell's printed `Card.cmc` - always the off-stack, X-as-0 reading (CR 107.3g), never the real on-stack value CR 202.3e asks for. `Game.put_on_stack` now computes that value itself - the printed cmc plus `x_value` once per `{X}` in the mana cost (CR 107.3i: every `{X}` on one object shares the one chosen value, so Walking Ballista's `{X}{X}` cast for X=1 is mana value 2, not 1) - and carries it on `GameEvent.amount`, which the condition reads in preference to `subject_card.cmc`. The effect side had no entry at all, and is not a `TRIGGER_EFFECTS` row: `_parse_counter_that_spell_clause` in `machines/effects.py` reads "counter that spell" by shape, through `trigger_effect_for`'s ordinary `parse_mixed_effect` fallback - CR 607.1 linked-ability anaphora back to the trigger's own event subject, not a target, so it reads `ability.event.subject_id` and counters with `Game.counter` (CR 701.6a) regardless of who cast it, Chalice's own controller included. Vexing Bauble's identical clause needed the exact same read, so its old hand-written `vexing_bauble_counter`/`TRIGGER_EFFECTS` row is deleted too - `test_mana_spent_intervening_if.py`'s Vexing Bauble test now runs entirely off this parser | `scenarios/test_chalice_of_the_void.py`, `scenarios/test_mana_spent_intervening_if.py` |

## Can you actually play a game?

A game starts and runs now: `Match.start_game` loads each registered deck
(`Player.load_deck`, with the sideboard set aside for games two and three -
CR 103.2a), shuffles it seeded (CR 103.3), sets life to 20 (CR 103.4), deals
opening hands of seven (CR 103.5), and `Match.run_mulligans` settles them
through the London mulligan. Who goes first is decided by CR 103.1 - randomly,
by name, or by the loser of the previous game through `Match.chooser_for_next_game`.
`scenarios/test_starting_a_game.py` and `scenarios/test_mulligans.py` play it
through with real tournament decklists. From there, `Game(automatic_turn_based_actions=True)`
drives the whole turn: untap, draw, the combat declarations through the decision
machinery, cleanup - a creature attack declared by its player, blocked by the
defender, and dealt damage, all from `advance()` (`scenarios/test_combat_turn_based_actions.py`).

What still separates this from a game two people could actually play:

1. **The card effects registry is the bottleneck.** `machines/effects.py` is a
   hand-written registry keyed by card name; every card without an entry
   resolves as a no-op, which is most of them. Casting, targeting, paying, and
   the stack all work - it is the resolution that does nothing. **A slice of
   this is now closed**: `parse_player_effect`/`parse_player_effect_for_spell`
   read a single-clause, no-target, no-choice player effect - life gain and
   loss, energy, drawing, milling, surveil, scry, and any straight-line
   combination of those joined by "and"/"then"/a sentence boundary (CR
   608.2c) - straight off a card's own printed text, tried on a registry miss
   in all three resolution paths (`effect_for`, `trigger_effect_for`,
   `activated_effect_for`). It fails **closed**: one clause it cannot read
   (a target, a modal choice) throws the whole effect away rather than
   running the part it understood. **"You may `<clause>`." is now read
   too** (CR 608.2d), for both the player-effect wave above and the
   targeted wave (destroy/exile/return/tap/untap/counters/damage-target,
   `parse_targeted_effect`/`parse_targeted_effect_for_spell`) - wrapping is
   only ever applied over a clause the parser already understands, so "you
   may `<something unread>`" still throws the whole effect away rather than
   asking a question it could not carry out. "`<A>`. If you do, `<B>`." (CR
   118.12) is now read for the **sacrifice** shape: "you may sacrifice this
   `<type>`" (Sanctum of Ugin - the permanent bearing the ability itself,
   never a choice among several) and "you may sacrifice another `<type>`"
   (Disciple of Freyalise - a real CR 608.2d choice among whatever the
   player controls of that type), each paired with its own "if you do"
   consequence - a plain mandatory search (`_search_and_place_for`, run with
   `optional=False` since CR 118.12's own "you may" already gated it) or a
   magnitude-threaded pair of clauses reading "X" as the sacrificed
   permanent's power, captured before `Game.sacrifice` moves it to the
   graveyard the same CR 608.2i way `_parse_anaphoric_clause_pair` already
   does. CR 118.12's own text is the reason the consequence never re-checks
   the board afterward: "the 'If \[a player\] does' clause checks whether
   the player chose to pay ... regardless of what events actually
   occurred" - CR 701.21a's sacrifice has no failure mode for a permanent
   the player controls, so "did you do it" is only ever "did you say yes".
   `machines/effects._parse_conditional_sacrifice_clause`,
   `ConditionalClauseNotice`; `scenarios/test_conditional_sacrifice_clauses.py`.
   Still not implemented: the **pay-life** cousin of the same CR 118.12 shape -
   Necrodominance's "you may pay any amount of life. If you do, draw that many
   cards." It once needed a decision primitive this engine did not have -
   "choose an amount of life to pay" is not `PAY_LIFE`'s fixed `amount`, and
   no `DecisionKind` read a variable answer back as an integer. That primitive
   exists now: `DecisionKind.PAY_ENERGY_AMOUNT` and `Game.pay_any_amount_of_
   energy` (see the energy row above), built for Galvanic Discharge's and
   Wrath of the Skies's own "you may pay any amount of {E}" rather than for
   Necrodominance - its own clause is still unwired, but the missing piece was
   the shape of the question (an integer, not a boolean), which is no longer
   a gap in the machinery, only in which cards call it. **Turntimber
   Symbiosis's own clause is fixed (W13)** - see its own row below in "Cards
   from the metagame" - and turned out not to need this primitive at all: "you
   may put a creature card ... onto the battlefield. If that card has mana
   value 3 or less, ..." is a plain CR 608.2d `MAY`/`CHOOSE_CARDS` choice with
   a check on the chosen card's own mana value read inline, not an amount
   fed back as an integer. Targeted effects with a restriction the
   parser cannot enforce, other choices, and token creation are still the
   registry's job.
2. **Opening-hand actions are not modelled.** CR 103.6's opening-hand actions
   (Leyline-style begins-on-the-battlefield effects) are a separate sequence
   after the mulligan process and are not modelled.
3. **Decisions default rather than ask.** Unscripted questions - a mulligan,
   an attack declaration - take the documented default answer rather than
   waiting for a player, because there is no player agent: a human at the API
   or a scenario script is the only source of answers. For the mulligan
   (`ask_mulligan`) and the two combat declarations (`ask_attackers`,
   `ask_blockers`) this is not merely unwired but structural: all three read
   `DecisionScript.take` directly and never call `Game.ask`, so
   `Game.decisions.provider` - the hook a live caller such as the API's
   per-game mailbox attaches to - is never consulted for them at all, unlike
   `MAY`/`PAY_LIFE`/`SCRY`/`SURVEIL`/`CHOOSE_CARDS`/`CHOOSE_TARGETS`, which do
   flow through `Game.ask` and so can be answered live without any engine
   change. Routing a live answer to a mulligan or a combat declaration would
   need `Game.ask` itself extended to cover them, not just a caller wiring a
   provider in.

Scenario tests that need the manual path still call the combat moves by hand;
`automatic_turn_based_actions` off leaves every turn-based action to the caller.

### A harness convenience, not a rule: auto-passing after an action (magic-cards-model-api)

The self-test API's player-facing tools (`magic-cards-model-api`'s `mcp.py`
and `seat_cli.py`) make every action tool - `cast`, `play_land`, `activate`,
`declare_attackers`, `declare_blockers`, `resolve_top`, `advance`, `decide`,
`pass` - do the action, then release priority, then block until that seat next
has something to do, all in one call. The engine's own rule underneath this is
correct and unchanged: **CR 117.3c** - "If a player has priority when they
cast a spell, activate an ability, or take a special action, that player
receives priority afterward" - which is exactly what `Game.retain_priority`
already gives back to the actor. What the harness adds on top is a
convenience, not part of the rule: it auto-passes that regained priority away
on the caller's behalf unless the caller asks to keep it, because two
AI agents playing through a seat found "act, then separately remember to
pass, then wait" chatty and easy to forget a step of. The escape hatch back to
the real rule is the `hold_priority` parameter every one of those tools takes:
set true, the action still runs and the actor still keeps priority exactly as
CR 117.3c says, but the tool returns immediately without auto-passing or
blocking - for casting into one's own trick, activating twice before passing,
or any other sequence a human player would do without giving priority up
first. See `magic-cards-model-api/src/magic_cards_model_api/seatkit.py` for
the implementation (`run_action`) shared by both transports.

## Not modelled

Roughly in the order they block other work.

| Area | Rules | Note |
|---|---|---|
| Combat turn-based actions, on the manual path | CR 703.4i, 703.4j, 703.4k | The automatic path drives all three combat steps now - see the Modelled table. With `automatic_turn_based_actions` off, declaring, blocking, and damage remain moves a caller makes. An illegal scripted declaration raises rather than being silently dropped: with no player agent there is nobody to pick a replacement. |
| The 508.8 skip versus "put onto the battlefield attacking" | CR 508.8, 508.4 | `advance` reads the declaration flag only, so a creature put onto the battlefield attacking by an effect (CR 508.4, modelled for tokens) does not defeat the skip of the declare blockers and combat damage steps. |
| The extra first-strike damage step as a *step* | CR 510.4 | The two damage assignments happen, with state-based actions between them, but both inside `Step.COMBAT_DAMAGE`. There is no second entry in `TURN_ORDER`, so no priority round between them. |
| Attacking a planeswalker or a battle | CR 508.1a, 306.6, 310.5 | `declare_attacker` accepts and validates a planeswalker or battle as the defender, but nothing redirects damage, removes loyalty, or checks CR 506.4c. Untested. |
| Combat keywords the pool does not carry | CR 702 | Flying, reach, trample, menace, vigilance, haste, first strike, double strike, defender, deathtouch, lifelink and the five basic landwalks are enforced. Banding, shadow, fear, intimidate, skulk, "can't block" and the nonbasic/snow landwalk shapes of CR 702.14a are not - no printing in the pool has one. |
| Keyword *grants* the layer registry does not produce | CR 611, 613, 613.1f | `combat.has_keyword(state, keyword, game)` reads the computed board when it is given a game (CR 613.5), through `abilities.keywords_in_lines`, so a keyword removed in layer 6 is gone from combat and a granted one is there - Violent Urge's first strike now causes CR 510.4's extra damage step. What a card *generates* is still the hand-written `LAYER_EFFECTS` registry, so Cori-Steel Cutter's "has trample and haste" grants nothing. |
| Attack and block requirements | CR 508.1c, 508.1d, 509.1b, 509.1c | Only the restrictions the engine knows about are checked. "Attacks if able", "must block if able", "can't attack unless", and the maximum-requirements search those imply are not modelled. |
| Removed from combat, other causes | CR 506.4 | Only leaving the battlefield removes a permanent from combat. Control change, phasing out, and effects that say so do not. |
| Draws without a check | CR 104.4b, 104.4c, 104.4i | The simultaneous-loss draw is modelled (see the Modelled table). The loop draw of CR 104.4b, an effect that states the game is a draw (CR 104.4c), and CR 104.4i's intentional draw have no mechanics behind them - `Game.end_in_draw` is the staging entry a scenario calls. |
| Starting a game | CR 100-103 | `Match.start_game` does the work now - decklists registered by username with the sideboard set aside (CR 103.2a), seeded shuffles (CR 103.3), life 20 (CR 103.4), opening hands of seven (CR 103.5), and CR 103.1's first-player decision, with the loser of the previous game choosing after game one. Covered in the Modelled table. The London mulligan is orchestrated now: `Match.run_mulligans` collects each player's declaration in turn order (CR 103.5), takes every mulligan at once once all declarations are in, repeats until nobody mulligans, pays the bottoming cost at the keep, honours CR 103.5c and CR 800.6's free first mulligan in multiplayer games (CR 800.1), and enforces CR 103.5's zero-hand ceiling. What is left: CR 103.6's opening-hand actions are a separate sequence that begins once the process completes and are not modelled, nor are CR 103.5b's "any time [that player] could mulligan" effects. |
| Turn-based actions outside untap, draw, and cleanup | CR 703.4 | The rest of the CR 703.4 list needs mechanics that do not exist: phasing (703.4a), day/night (703.4b), Saga and Attraction steps, and the combat entries above. Mana pools emptying (703.4q) is modelled - see the Modelled table. |
| Trigger conditions the matcher cannot read | CR 603.1 | `machines/triggers.py` matches a fixed set of condition shapes and returns False for anything else, so an unreadable trigger silently never fires. **Now read**: a non-self-referential dies condition, singular or plural, optionally narrowed by "you control" and by a creature subtype ("Whenever another creature you control dies", "... one or more other Cats you control die" - Ajani, Nacatl Pariah); the spelled-out CR 700.4 form of dies ("is put into a graveyard from the battlefield" - Flagstones of Trokair); "Whenever you attack" (CR 508.3d, once per attacking player per combat, not once per attacker - `Game.declare_attackers` emits a second, subjectless event for it); "is tapped for mana" (CR 106.12a), both "you tap a creature for mana" (Badgermole Cub, Leyline of Abundance) and "enchanted [land] is tapped for mana" (Utopia Sprawl, read off the Aura's own `attached_to`); and "a player casts a spell with mana value equal to the number of `<kind>` counters on this `<permanent>`" (Chalice of the Void), now compared against the spell's real on-stack mana value (CR 202.3e) rather than its printed `Card.cmc` - see the Chalice of the Void row above. Still not read: leaves-the-battlefield (CR 603.6c - broader than dies, and nothing in the pool's other examples justifies a new emit site yet), a permanent turning face up, a +1/+1 counter being put on a permanent, a Class leveling up (no Class mechanic exists at all), and state triggers (CR 603.8). Delayed triggers (CR 603.7) are modelled - see `machines/delayed.py` - but they are *created* by an effect rather than parsed, so a card whose printed text creates one still needs an entry in `machines/effects.py`. **Reflexive triggers (CR 603.12) are now modelled for three shapes**, not just one: `_parse_reflexive_sacrifice_clause` in `machines/effects.py` reads "You may sacrifice `<restriction>`. When you do, `<consequence>`." (Grist, the Hunger Tide), `_parse_reflexive_pay_energy_clause` reads the same "you may" shape for a fixed-amount energy cost instead of a sacrifice (Guide of Souls' "you may pay {E}{E}{E}", built on `Game.may_pay_energy`), and `_parse_reflexive_mandatory_token_clause` reads CR 603.12's "allow **or instruct**" the mandatory way - no `MAY` decision at all - for a token-creation action, with a nested intervening *if* (CR 603.4) checked once, immediately after the action happens (Ajani, Nacatl Avenger's `0`). `DelayedTriggers.create_reflexive` in `machines/delayed.py` is shared by all three: each creates a genuinely separate triggered ability that goes on the stack the next time a player would receive priority (CR 603.3), so an opponent gets a real object to respond to (CR 405.6a) and the consequence's own target is chosen when *it* is put on the stack (CR 603.3d), not earlier. See `tests/scenarios/test_reflexive_triggered_abilities.py`. Any other action shape ("choose a mode", a discard, a life payment as the reflected action) is still unread and records a `ReflexiveClauseNotice` instead of resolving silently. Caretaker's Talent's "Whenever one or more tokens you control enter, draw a card. This ability triggers only once each turn." is deliberately left unread even though ENTERS_THE_BATTLEFIELD plus a token-type check would be cheap: the engine has no "only once each turn" debounce for a *triggered* ability (only for activated abilities, CR 602.5b), and firing it without that limiter would draw extra cards, which is worse than never firing. **Delayed triggers with a stated duration (CR 603.7b, "such as 'this turn'") are now bounded**: `DelayedTrigger.expires_end_of_turn` plus `DelayedTriggers.expire_this_turn` (called from `Game.cleanup_step`, CR 514.2) is what stops Dalkovan Encampment's "whenever you attack this turn" from also firing on a later turn's attack; `DelayedTrigger.subjectless_only` is the companion fix for a duration-bounded trigger that watches an event `Game.emit`s twice per occurrence (once per creature, once subjectless per player) - without it the trigger double-fires. |
| Events nothing emits | CR 603.2 | Seventeen events now reach `Game.emit`: entering the battlefield, dying, attacking, blocking, a step beginning, casting a spell, a card being exiled, becoming a target, drawing a card (one event per card, CR 121.2), gaining life, losing life, dealing damage (combat and noncombat told apart by `GameEvent.combat`), being sacrificed, a spell being countered, becoming untapped, becoming tapped, and being tapped for mana (CR 106.12a) (`scenarios/test_trigger_events.py`). The tap sites are wired: the TAP cost component in `machines/cost.py`, attack declaration in `machines/combat.py` (not under vigilance), and cost sacrifices route through `Game.sacrifice`, so they fire the sacrifice event and the dies event both; spell-effect draws route through `Game.draw_cards`. `CostPayment.tap_for_mana` (tapping a permanent to pay a cost) and the mana-ability fast path in `Game.activate_ability` (CR 605.3b, a permanent tapping itself) both emit `TAPPED_FOR_MANA` through the shared `machines/triggers.tapped_for_mana_event` builder, so the two cannot drift apart on what the event looks like. One registry effect (`Seasoned Pyromancer`'s discard-then-draw) still calls `Player.draw` directly rather than through the emitting path. Sheoldred, Ragavan, Questing Beast, and Dragon Appeasement now trigger. Sheoldred's own "you gain 2 life" half now runs too, through `parse_player_effect`'s fallback (no `TRIGGER_EFFECTS` row needed); her other half - "an opponent draws a card, they lose 2 life" - still does nothing, because "they" is a pronoun this wave does not resolve to a player. Ragavan's, Nashi's, and Questing Beast's resolutions are all read generically off their own printed clauses now and all three fail closed on purpose with an `UnmodeledTriggerEffectNotice` - see the table rows below for why each. **Dragon Appeasement's now runs**: "you may draw a card" is read by `parse_player_effect`'s "you may" wrapper (CR 608.2d), asked through `Game.may` with the documented take-it default. **Utopia Sprawl's, Leyline of Abundance's, and Badgermole Cub's "add an additional" bonus now resolves for real** - `_parse_mana_adding_trigger` in `machines/effects.py` reads "[its controller ]add[s] an additional <mana>" off the ability's own printed text (no `TRIGGER_EFFECTS` row, so the fix is one text template, not three per-card rows), and Utopia Sprawl's "As this Aura enters, choose a color" (CR 614.12a, 614.1c) is now a real choice too - see the next paragraph. "Its controller" is read as the *enchanted permanent's* controller (`attached_to`), not the ability's own, so an Aura enchanting an opponent's land credits the right player (CR 303.4e; `scenarios/test_mana_adding_triggers.py`). **What is still a known simplification**: a triggered mana ability (CR 605.1b) is treated like an ordinary triggered ability and goes on the stack; CR 605.4a says it "doesn't go on the stack" and resolves immediately after the mana ability that triggered it. Because of that, mana from tapping a permanent to help pay a spell's own cost cannot land in time to pay for that same cast - `CostPayment.tap_for_mana`'s payment pool is already settled before the trigger, sitting above the spell on the stack, gets a turn - so the bonus mana instead floats in `player.mana_pool` once the trigger resolves, available to a *later* payment that opens by copying the player's floating mana. Not attempted here; see `scenarios/test_mana_adding_triggers.py`'s docstrings. |
| Ordering triggers a player controls | CR 603.3b | APNAP order between players is honoured; within one player's set the order they triggered in is used, because the rules leave the choice to the player and nothing here can ask. |
| Missing a trigger, and optional triggers | CR 603.3, 603.5 | A trigger is never missed. Solemn Simulacrum's two "you may" clauses, Malevolent Rumble's, the fetch/search family (`_search_library`, `parse_search_and_put_effect`, `Game.search_library`), and now every "you may `<clause>`." the wave-1/wave-2 parsers otherwise read (`parse_player_effect`, `parse_targeted_effect`, and their spell twins - `tests/scenarios/test_optional_effect_clauses.py`) are wired through `Game.ask`. Measured against the fixture pool as it stood before that file's cards were added, this closes exactly **one** previously-broken card (Dragon Appeasement); the rest of the original ~47-clause survey needs a clause type neither parser reads yet - discard, pay-life, a variable X - and is still an `if True:` or simply absent. "`<A>`. If you do, `<B>`." (CR 118.12) is now implemented for the sacrifice shape - see the wave-1 note above and `_parse_conditional_sacrifice_clause`; the pay-life and variable-X cousins are still absent, needing a decision primitive this engine does not have. Its documented default is still to take it, so nothing wired here moves an existing test's behaviour. |
| A trigger in the cleanup step | CR 514.3a | `Game.advance` does not put triggers on the stack in the untap or cleanup steps, where no player receives priority; a cleanup trigger should give players priority and repeat the step, and does not. |
| Rewinding a cost that already emitted an event | CR 733.1 | `CostComponent.unpay` restores the sacrificed permanent, but the dies event it caused has already been emitted and the trigger stays pending. Only reachable through an explicit `rewind`, since `CostPayment.pay` checks the whole cost before paying any of it. |
| Timing restrictions on an activated ability | CR 602.1b, 602.5 | "Activate only once each turn" (CR 602.5b) and "activate only as a sorcery" (CR 602.5d, CR 307.5) are enforced by `Game.why_cannot_activate`. Every other timing sentence is parsed into `ActivatedAbility.instructions` and read by nobody. |
| A land type granted by an effect is invisible to activation | CR 305.6, 613 | `Game.activated_abilities` reads the static printed `Card` (`activated_abilities_of(permanent.card)`), not the layer-computed `Characteristics`, so a land that gains a basic land type from Urborg, Dryad of the Ilysian Grove, or Blood Moon does not gain the matching activatable mana ability - the intrinsic-land fallback in `machines/abilities.py` never sees the grant. Pre-existing, not a regression from the self-referential cost fix. |
| Static abilities as *text* | CR 611, 613 | The layer engine in `machines/layers.py` applies continuous effects in layer and sublayer order, dependency included, reads counters off the permanents (CR 613.4c) and applies characteristic-defining abilities in 7a (CR 613.4a). As of W5, four shapes are read straight off a card's own oracle text by `parsed_layer_effects`, tried on a `LAYER_EFFECTS` registry miss: "target/this creature gets +N/+N [and gains \<keyword>] until end of turn" (CR 613.4c, 613.1f), "target/this creature gains \<keyword> until end of turn" (CR 613.1f, CR 113.10), and "\[other] creatures \[you control\|your opponents control] get +N/+N" (CR 613.4c, static). **W6 adds two more**: "\<subject> has base power and toughness N/N until end of turn" (sublayer 7b, CR 613.4b - a *set*, not W5's 7c modifier; Flexible Waterbender) and "Until your next turn, up to \<n> target ... becomes a\[n] \<type> creature with power and toughness each equal to its mana value" (layer 4 + sublayer 7b, CR 613.1d/613.4b/613.6; Karn, the Great Creator's +1). The mana-value P/T reuses `set_power_toughness_to_mana_value`, which reads the target's mana value fresh every board computation (CR 613.5) rather than freezing it at resolution - the same choice Opalescence's identical clause already made. A new `Duration.UNTIL_YOUR_NEXT_TURN` (CR 800.4m) outlives the turn it was created in and the opponent's turn(s) after it, ending only when `Game.begin_turn_for` fires for its own controller. A sentence that opens like one of the six shapes but does not fully match - Violent Outburst's temporary team-wide one, a "becomes a Human Soldier creature" two-word type, "has base power and toughness N/N *until your next turn*" - is not silently dropped: `looks_like_unparsed_layer_effect` catches it and `ContinuousEffects.layer_notices` records a `LayerNotice` instead. Teferi, Time Raveler's own "Until your next turn, you may cast sorcery spells as though they had flash." is real pool text that opens the same way as Karn's duration and is correctly *not* flagged - it grants a permission, not a type change, and is outside every shape's territory. **W5** gives that permission (and Teferi's static half) somewhere to live: see the rules-modifying casting-restriction row above, in `machines/casting_restrictions.py` rather than here - a permission over *casting* writes no layer at all, so it was never going to be this module's business. What is left in the hand-written `LAYER_EFFECTS` registry (13 rows, unchanged by W6 - none of its existing rows turned out reachable through the two new shapes) is what does not generalise: Humility, Opalescence, Blood Moon, Urborg, Twisted Image, Dryad of the Ilysian Grove, Dress Down, Relentless Rats, Tarmogoyf, Allosaurus Rider, Tishana's Tidebinder, Violent Urge (its pump and first strike are the generalised shapes, reused via `_pump_and_keyword_builder`; only its *Delirium* clause is hand-built), and the Monster Role token (subject "Enchanted creature", which needs the board's `attached_to` link rather than a resolved target - not read by any shape yet). `test_layer_effects_registry_is_minimal.py` guards against a re-added row for a shape the parser already covers, the same way `test_registry_is_minimal.py` does for `machines/effects.py`. **Every other card with a static ability this parser does not reach generates nothing**, silently - Doran, Fog Bank, Hyena Umbra ("Enchanted creature" again), Cori-Steel Cutter and the rest. Earthbend/waterbend-style custom keyword costs ("Waterbend {3}:", Badgermole Cub's "earthbend 1" reminder) are not modelled as activation costs, so Flexible Waterbender's own ability cannot actually be activated in a game yet even though its effect text now parses; `scenarios/test_type_changing_and_pt_setting_effects.py` exercises the clause in isolation and says so. **W7**: `parsed_layer_effects` no longer re-derives its sentences from raw oracle text with its own reminder-stripping and cost-prefix regexes - `layer_readable_sentences` (`machines/abilities.py`) hands it every `StaticAbility.text` and `ActivatedAbility.effect` the real ability parser found, so `StaticAbility` (previously parsed by `parse_abilities` and never read by anything) is now load-bearing. A seventh shape was added on the same pass: "\[other] creatures \[you control\|your opponents control] have \<keyword>\[, \<keyword> and \<keyword>]" (CR 613.1f, static; True Conviction), the keyword-granting twin of the anthem shape - one or more keywords off `_KNOWN_KEYWORDS`'s whitelist, each producing its own grant, none reachable via `_KEYWORD_GRANT_RE` because that shape requires "until end of turn" and this one is indefinite (CR 611.3b: a static ability's effect lasts exactly as long as its source does, with nothing to expire). A keyword outside the whitelist - Asceticism's hexproof, which `machines/combat.py`'s `Keyword` does not model - fails closed with a `LayerNotice` rather than granting nothing silently; `scenarios/test_indefinite_keyword_grant.py` covers both the grant (functional in combat: double strike's extra damage step, lifelink's life gain) and the switch-off the moment the source leaves the battlefield, and the fail-closed case. None of the 15 `LAYER_EFFECTS` rows turned out reachable through this new shape or the sentence-source refactor (`test_layer_effects_registry_is_minimal.py` still passes unchanged) - this wave only widened coverage to cards not previously in the registry at all, and did not shrink it. **W8 adds protection grants**: `_INDEFINITE_KEYWORD_AND_PROTECTION_GRANT_RE` reads the same indefinite shape with a trailing "protection from A [and from B]" clause (Akroma's Memorial), producing a "Protection from \<quality>" ability string per quality through the same `_indefinite_keyword_grant_builder` the plain-keyword shape already uses - see "Protection *granted* by another static ability" above. Only the fixed-quality, un-chosen form is read; a targeted "gains protection from the color of your choice" needs a colour-choice mechanism this wave did not build, and is left for a future one along with cost-modifying static text and characteristic-defining abilities beyond the four already in the registry. **W13 adds an eighth shape**: "this creature gets +N/+N for each \<type> card in your graveyard" (sublayer 7c, CR 613.4c - a *modifier* added to the printed base, not Tarmogoyf's/Boneyard Wurm's sublayer 7a characteristic-defining "power and toughness are equal to" *set*), which is what Fiend Artisan's own pump turned out to be - `_self_pump_per_graveyard_card_builder`, no duration (CR 611.3), magnitude read off `LayerContext.graveyard_of` fresh every board computation the same live-recompute trick Boneyard Wurm's row already used. `is_resolution_layer_effect_text` excludes it from the *resolution*-effect routing the same way the anthem shape is excluded, since it opens like `_PUMP_RE`'s one-shot pump but carries no duration and is CR 611.3's own static effect. |
| An activated ability's effect reaching the layer engine with its own resolved targets, not just its source | CR 611.2, 602.2, 606 | `machines/effects.py`'s `create_continuous_effect_of_ability` used to always hand the layer engine `targets=[source]`, which is right for a pump that targets nothing beyond itself (Basking Rootwalla) but silently did nothing for an ability that targets something else (Karn, the Great Creator's +1, targeting a noncreature artifact) - the reported defect. It now calls `game.resolve_card_targets(ability)` when the ability actually has targets, the same CR 608.2b recheck a spell's targets already get, and falls back to `[source]` only when it has none. A legally-chosen "up to one" targeting nothing resolves doing nothing rather than fizzling. | `scenarios/test_type_changing_and_pt_setting_effects.py` |
| Combat, state-based actions, and targeting reading a permanent's *computed* type, not its printed one | CR 613.5, 508.1a, 509.1a, 704.5f-g, 601.2c | `machines/combat.py`'s `attack_refusal`/`block_refusal`, `Game._state_based_actions_once`'s death check, and `machines/targeting.py`'s card-type/excluded-card-type check all used to read `CardState.is_creature`/`target.card.types` - the **printed** type line - so a permanent a continuous effect turned into a creature (Karn's animated Trinisphere) could not attack, block, be dealt lethal combat damage, or even be legally targeted by a spell that requires "target creature" once animated. All three now ask `Game.characteristics_of`/`.is_creature` when a `Game` is available, the same pattern `combat.has_keyword` already established for keyword grants and `TargetRequirement._rejects_comparison` already established for power/toughness/mana-value comparisons; without a `Game`, or off the battlefield, the printed values are still what is read, since layers never apply anywhere else. **Note this row is about combat/SBA/targeting only - trigger matching is a separate reader and is covered by the row below.** | `scenarios/test_type_changing_and_pt_setting_effects.py` |
| Trigger matching reading a permanent's *up-face* type, not its front-face-only printed one | CR 712.8a, 712.8f, 712.12, 603.10, 205.3a | **Fixed defect, real-game report:** `Game._enters_event` and six other `GameEvent` construction sites (`put_on_stack`'s cast event, `deal_damage`, `sacrifice`, `put_into_graveyard`'s dies event, `declare_attacker`, `tapped_for_mana_event`) handed `machines/triggers.py`'s `_types_match`/`_subtype_matches`/`_category_matches` the raw printing (`permanent.card.types`, which is `Card.front_type_line` - structurally the front face, CR 712.8a) instead of the object as it actually exists. A modal double-faced permanent played for its *land* back face (Witch Enchanter // Witch-Blessed Meadow, and the other 6 MDFC-with-land-face fixtures) was judged a Creature by every one of those checks: Guide of Souls ("Whenever another creature you control enters...") fired on a land drop that was not a creature entering, and the mirror bug went unnoticed in the other direction - "Landfall - Whenever a land you control enters" (an ordinary CR 603.6a trigger) could never fire off any of those same 7 fixtures, because their front faces are Creature/Instant/Sorcery. `GameEvent` now carries `subject_types`/`subject_subtypes`, populated from `CardState.types`/`.subtypes` (already up-face aware via `land_face_played`/`up_face`) at the moment each event is built, and every type/subtype-reading branch in `condition_matches` reads those instead. `subject_card` (the raw `Card`) is unchanged and still used where CR 712.8a's front face is the *correct* answer - the mana-value-equals-counters cast check's `.cmc` read - since a card is never cast as its MDFC land face. **Since finished for transformers too:** `CardState.types`/`.subtypes` now read the back face while `transformed` is set (CR 712.8e), so these same `subject_types`/`subject_subtypes` are correct for a flipped Delver of Secrets, and `triggers_for`'s per-face filter was generalised from `land_face_played` to `CardState.up_face_name` - a transformed permanent has its back face's triggers and not its front's (CR 109.3). See the "Transforming a permanent" row above. Layer-computed types (an animated land judged by a trigger condition) are also not read here - only up-face awareness, not the full `Game.characteristics_of` layer stack - matching the same boundary the combat/SBA/targeting row above crossed for continuous effects but this one does not. | `scenarios/test_mdfc_land_play.py` |
| Which replacement effects exist at all | CR 614.1 | The application path is general; *which* effect a card generates comes from `machines/replacement.py`'s hand-written `REPLACEMENTS` registry (one row - Kalitas, Traitor of Ghet, whose "exile that card and create a 2/2 black Zombie creature token" mixes an exile this module can do with a token creation it cannot, so a generic parser would have to silently drop half the sentence) plus a set of generic compilers tried on a registry miss: "if \[quality] would be put into \[whose] graveyard, exile it instead" (Rest in Peace, Leyline of the Void, Necrodominance, Sanctifier en-Vec), "if a nontoken creature would enter and it wasn't cast, exile it instead" (Containment Priest), "if a source would deal damage ..., it deals double/triple that damage ... instead" (Furnace of Rath, CR 701.10g), "if \[a damage event], prevent that damage and \[someone] mill\[s] \[N] that many cards" (The Mindskinner, Angel of Suffering), "prevent all combat damage that would be dealt to and dealt by this creature" (Fog Bank), "if you would gain life, you gain twice that much life instead" and its draw-doubling sibling (Alhammarret's Archive), and the token/counter doublers (Doubling Season). `test_replacement_registry_is_minimal.py` guards against a re-added row for a shape a compiler already covers. A card whose wording does not match any compiled shape and has no `REPLACEMENTS` row generates no replacement effect however plainly its text reads - Stridehangar Automaton's token-plus-an-extra-Thopter clause (DDR#901) and The Darkness Crystal's "exile it and you gain 2 life" (mixing exile with a life gain, the same shape gap Kalitas has) both still fall through here. The two enters-the-battlefield exceptions remain generic and unconditional: "[this] enters tapped" and "[this] enters with N counters" are executed straight off the parse (CR 614.1c, 614.12). |
| An enters replacement with an unreadable *condition* | CR 614.1c | The **choice** case is modelled now: CR 614.12a's "if a replacement effect that modifies how a permanent enters the battlefield requires a choice, that choice is made before the permanent enters the battlefield", and the shocklands' "you may pay 2 life. If you don't, it enters tapped" is joined back into one choice by `_self_enters_modifiers` and answered through `Game.may_pay_life` (CR 119.4 decides whether paying is even legal). What is still skipped is a condition about the *board* - Arena of Glory's "unless you control a Mountain". An amount that is X is now read too when the entering object has its own cast record: CR 107.3m defines X for an enters-the-battlefield replacement effect off the value chosen for the spell that became that object, so Hangarback Walker and Walking Ballista both scale (`scenarios/test_enters_with_x_counters.py`) - an object with no cast record at all (put onto the battlefield by something other than its own resolution) still leaves the amount undefined and the replacement still skipped. Slumbering Trudge's "three minus X" is a different, still-unread shape - `_read_counters` only recognises a bare count, not an expression, so it never reaches this fallback. |
| Entering as a copy, or under another player's control | CR 614.1c, 616.1b, 616.1c | Parsed as `ENTERS_AS_COPY` and given its own forced step in `order_effects`, but nothing can produce one: copying needs copiable values `CardState` does not have. Clone and Vesuva enter as themselves. `scenarios/test_replacement_effects.py` has the xfail. |
| Self-replacement effects, CR 614.15 | CR 614.15, 616.1a | The rule's forced first choice is implemented as a hook in `order_effects` and never fires, because a self-replacement effect is an effect of a *resolving spell* replacing its own effect and `machines/effects.py` has no way to express one. Not to be confused with `ReplacementEffect.self_replacement`, which is CR 614.12's narrower "affects only that permanent". |
| Who chooses when several effects apply | CR 616.1 | The affected object's controller is meant to choose one at a time. There is nobody to ask, so `order_effects` stands in with a deterministic rule - that player's own effects first, then everyone else's, each in battlefield order. Same gap as CR 603.3b for triggers. |
| Skip effects, and replacing a step | CR 614.1b, 614.10 | Parsed as `SKIP` and never applied. `TurnMachine.skips_draw` is the one hand-rolled case - now keyed on `turns_taken` so CR 103.8a's "their first turn" is spent after exactly one turn, rather than firing again on a first-turn extra turn; Necrodominance's "Skip your draw step" still does not feed it. |
| Replacing a draw with something other than a draw | CR 121.6b, 121.6c, 614.11a, 614.11b | The draw event carries only how many cards. An effect that replaces the draw with milling, revealing, or a search (dredge, Abundance) cannot be expressed. |
| Effects that say something *can't* happen | CR 614.17, 614.17c, 614.17d | "Can't" effects are not replacement effects but follow similar rules, and none of them are modelled. Notably CR 614.17c's "if an event can't happen, it can only be replaced by a self-replacement effect" is not enforced. |
| Targeting text the parser cannot read | CR 115 | `machines/targeting.py` reads the common WOTC templates. Anything else leaves `understood=False` and is not checked at all. **A sweep of every card in `tests/fixtures/cards` over both spell text and ability text (`profile_for_text`) leaves no line unread.** **Fixed this wave:** "target creature with mana value 2 or less" (Abrupt Decay, Fatal Push), "target creature with power 3 or greater" (Abzan Charm), and "target creature with power or toughness 1 or less" (Warping Wail) used to read *past* the comparison - `understood=True` with no restriction at all, so the whole battlefield was a legal target. `TargetRequirement` now carries `comparison_attribute`/`comparison_operator`/`comparison_value` and `_rejects_comparison` judges them off `Game.characteristics_of` (CR 613.5, layers included - a creature pumped or shrunk by a continuous effect is judged on its current power, not the printed one). An unbound X (CR 107.3) or a count the parser cannot read at all (Prismatic Ending's own Converge condition, below) fails the whole phrase closed rather than being dropped - `comparison_value` stays `None` and every target is refused, per the project's rule that a falsely-permissive restriction is worse than an unimplemented one. **W6 fixes two more:** `Casting.targeting`/`Game._resolution_profile` now substitute a non-modal card's own announced X into its printed text before reading the restriction (`"{X}" in spell.mana_cost`), so March of Otherworldly Light, Tamiyo, Compleated Sage, and Postmortem Lunge's "target creature card with mana value X" are real, evaluated restrictions now, not a permanent `comparison_value=None` fail-closed - this was the row's own "still open" item, closed by touching `casting.py` and `Game._resolution_profile` as flagged. And a colour restriction ("target black or red permanent", Celestial Purge) is read for the first time: `TargetRequirement.required_colors` is a disjunction over CR 105's five colours, parsed as a leading adjective the same way a card type already is, and enforced off `Game.characteristics_of(...).colors` (CR 613.1e's layer 5) the same way the mana-value comparison already is. A modal card's X *is* substituted before parsing (`profile_for_modes`/`mode_rules_text`), so Kozilek's Command's "exile target creature with mana value X or less" resolves correctly once its X is announced. "target permanent card" is still read as any card rather than the six card types a permanent can have, unrelated to this fix. The controller and combat-state restrictions are answered - `targeting.py` falls back from controller to owner (CR 109.3), and `Casting.choose_targets` and `Game.legal_target` both pass the game down, so "target attacking creature" is enforced in play, not just in tests. A modal card is `understood=False` as a whole on purpose - `Game._resolution_profile` asks `profile_for_modes` for the modes that were chosen (CR 700.2c). |
| Revolt, and Fatal Push's own "instead" clause | CR 207.2c (ability word; no further numbered rule found for Revolt itself) | `Game.permanents_left_battlefield_this_turn`/`Game.revolt_active_for` track, per controller, whether a permanent they controlled left the battlefield this turn - fed by `Game._note_left_battlefield`, called from every route off the battlefield (`put_into_graveyard`, `exile_permanent`, `return_to_hand`), and cleared on the same turn-advance reset `spells_cast_this_turn` already gets. Fatal Push's own two-paragraph shape ("Destroy target creature if it has mana value 2 or less. Revolt — Destroy that creature if it has mana value 4 or less instead if a permanent left the battlefield under your control this turn.") is read generically, off the text template rather than the card's name (`machines/targeting.py`'s `_read_revolt_mana_value_override`, `TargetRequirement.comparison_value_if_revolt`) - the wider number is substituted in at both announcement and `Game.legal_target`'s CR 608.2b recheck whenever Revolt is live for the caster right then, not fixed once at parse time. `machines/effects.py`'s `_parse_revolt_destroy_or_exile_clause` only has to recognise the two-paragraph shape and hand back the ordinary unconditional destroy/exile verb - the conditional half lives entirely in the targeting layer. | `scenarios/test_fatal_push_revolt.py` |
| Converge | An ability word (CR 207.2c); `knowledge_search` found no further numbered rule for Converge itself | Prismatic Ending's "Exile target nonland permanent if its mana value is less than or equal to the number of colors of mana spent to cast this spell" names a count that is not fixed until the cost is fully paid (CR 601.2g-i), which is *after* targets are announced (CR 601.2c) - unlike Fatal Push's own mana-value condition above, there is no moment before resolution at which this could restrict what may legally be targeted, so `machines/targeting.py` correctly leaves "target nonland permanent" unrestricted (see the row above) and `_parse_converge_exile_by_colors_spent` in `machines/effects.py` judges the condition once, at resolution, off `CastRecord.mana_spent` (`Color.COLORLESS` excluded - generic mana is not one of CR 105.1's five colours). | `scenarios/test_prismatic_ending.py` |
| An additional cost of "pay X life" feeding a resolution magnitude | CR 118.8a, 107.3f, 119.4, 611.2, 611.2c | Toxic Deluge's "As an additional cost to cast this spell, pay X life. All creatures get -X/-X until end of turn." needed two things: the announced X to reach a life-payment cost with no fixed number (`modes.substitute_x` already turns "pay X life" into the ordinary "pay N life" `machines/cost.py` already reads, once the caller announces X the same way any other X-cost spell does), and a mass debuff with no controller restriction at all - `machines/layers.py`'s `_MASS_PUMP_UNTIL_EOT_RE` and `machines/effects.py`'s `_mass_creature_group_targets` both gained an "all creatures" branch (`every_creature`) alongside the existing "creatures you control"/"creatures your opponents control" ones, reusing `_run_mass_pump` unchanged with a negative magnitude read off `Game.cast_record(spell).x_value` at resolution (`_parse_x_life_mass_debuff`, matched ahead of the generic mass-pump parser so the still-literal "X" is never mistaken for Craterhoof's own "where X is ..." shape). The state-based action that kills a 0-toughness creature is unchanged - it is a consequence of the pump, not part of the effect. | `scenarios/test_toxic_deluge.py` |
| "Destroy all `<qualifier>`", and non-targeted damage to a card-type group | CR 701.8a, 205.2a, 119.1 | `_DESTROY_EACH_RE` now reads "destroy all" as well as "destroy each" (Brotherhood's End's "Destroy all artifacts with mana value 3 or less" - the same grammar Culling Ritual's "destroy each" already used, and `_parse_mass_type_qualifier` now singularises a bare plural type word the same way `_singular_card_type` already did elsewhere, so "artifacts" reads as `Type.ARTIFACT`). A new, non-targeted damage shape was added alongside it for a card naming itself as the source: "`<Source>` deals N damage to each `<type>`[ and each `<type>`]*" (Brotherhood's End's other mode, "deals 3 damage to each creature and each planeswalker") - `_parse_damage_each_group_clause`, tried on the whole text ahead of the ordinary clause split (the generic "and" splitter would otherwise cut "each creature and each planeswalker" into two fragments), OR-ing the named CR 300.1 types together so a permanent that is more than one of them is hit once. Neither shape is targeted, so CR 608.2b's legality recheck never applies to either - each judges the board as it stands the moment it runs. | `scenarios/test_brotherhoods_end.py` |
| A reanimation target named by a variable mana value, with a granted haste and a delayed exile | CR 107.3a, 603.7, 603.7c, 611.2a, 701.13a | Postmortem Lunge's "Return target creature card with mana value X from your graveyard to the battlefield. It gains haste. Exile it at the beginning of the next end step." used to leave a `DelayedClauseNotice` (the timing was recognised, the antecedent was not) - `_parse_delayed_reanimate_haste_exile_clauses` in `machines/effects.py` now reads all three clauses as one CR 608.2c instruction: the target's own mana-value comparison is the ordinary "targeting text the parser cannot read" fix above (a real, evaluated X once `Casting.targeting` substitutes it), haste is granted with `Duration.INDEFINITE` scoped to `only_this_incarnation` of the specific object that just entered (CR 611.2a: no duration stated), and the delayed exile is built fresh with `machines/delayed.py`'s new `exile_subject_at_next_end_step` callback rather than a name-keyed table row - CR 603.7c's zone/stamp check means a creature destroyed before the end step is simply not there for the trigger to affect. | `scenarios/test_postmortem_lunge.py` |
| Choosing a split card's own half | CR 709.2, 709.3, 709.3a, 709.3b | `Casting.cast_as_split_half` is CR 709.3's actual choice, alongside the pre-existing Adventure-only `cast_as_adventure` - it records the choice both on `Casting.face` (already used for `base_cost`, unchanged) and, once the spell is cast, onto a new `CardState.face_played` field, scoped to `Layout.SPLIT` alone so Adventure's own still-open gap below is untouched. `CardState.up_face` reads that face while (and only while) the object is on the stack (CR 709.3b: "while on the stack, only the characteristics of the half being cast exist"; CR 709.2: off the stack it is "only one card" again, so a resolved Wear // Tear in the graveyard reads as Wear, its front face, the same as before it was ever cast). `Casting.targeting` reads the chosen half's own printed text instead of `targeting_profile(card)`'s combined-text fallback, so Tear's "target enchantment" is enforced correctly rather than Wear's "target artifact" (or the reverse) regardless of which half was actually chosen. The front half already worked with no changes at all - `Casting.base_cost` already special-cased a split card's `"{1}{R} // {W}"` combined `mana_cost` to the first face's own cost, and `up_face` already fell back to `Card.front_face`. Fuse (CR 702.102, casting both halves as one spell) is not modelled - only its reminder line is stripped (`_FUSE_LINE_RE`), not read. | `scenarios/test_split_cards.py` |
| Modal templating other than bullets | CR 700.2h, 700.2i, 700.2e, 601.7 | A mode with its own cost printed in front of it (Spree, CR 702.172a; Tiered, CR 702.183a), pawprint modes (CR 700.2i), and a mode chosen by a player other than the controller (CR 700.2e, 601.7) all leave `ModalProfile.understood` False. |
| Keyword abilities with no execution path | CR 702 | `scripts/sweep_pool.py --keywords` is the list, and it is down to **6** from 31 (14 before this pass). Still inert: compleated, hideaway, role token, sunburst, suspend. "Imprint" moved to `ABILITY_WORDS` (CR 207.2c: it has no rules meaning of its own) once Ugin's Labyrinth's shape - "you may exile a `<quality>` card ... from your hand" - was read as a plain clause; see the imprint row in the Modelled table. |
| Morph's variants | CR 702.37b, 702.168 | Morph itself is in the Modelled table. Megamorph's turn-face-up is meant to add a +1/+1 counter (CR 702.37b) and is not modelled - `turn_face_up_cost` in `machines/keywords.py` knows the morph cost only, and there is no megamorph printing in the pool to test against. No printing has disguise either, so the ward {2} set `FaceDownCharacteristics` builds for it (CR 702.168) is untested against a real card. |
| State-based actions the model cannot express | CR 704.5 | Copies (704.5e) and battles (704.5v-704.5x). CR 704.5d (a token outside the battlefield ceases to exist), CR 704.5m (an Aura on an illegal object), CR 704.5z (Roles beyond the newest), CR 704.5h (deathtouch) and CR 704.5n (an Equipment on an illegal permanent) are all dispatched now. |
| Dispatching the counter state-based actions | CR 704.5c, 704.5i, 704.5q | Losing to ten poison counters (704.5c) is dispatched in `Game._losing_players`, and a planeswalker at zero loyalty (704.5i) is dispatched in `Game._state_based_actions_once` now. Annihilation (704.5q) lives in `counter_state_based_actions` in `models/card_state.py` and is still driven by `PlayedScenario.state_based_actions` in the scenario harness, not by `Game`. A creature killed by its -1/-1 counters (704.5f) does fire inside `Game`, because `CardState.toughness` counts them. |
| Reducing a cost *by* a hybrid symbol | CR 118.7e | The payer chooses a half when the reduction is applied and there is nobody to ask, so `ManaCost.minus` raises. Reducing by a Phyrexian symbol (118.7f) and by snow symbols (118.7g) is modelled, and a cost containing hybrid, Phyrexian, or snow symbols survives any increase or reduction intact. |
| Whether a hybrid symbol "requires" its colours | CR 118.7b-c | `{G/W}` is treated as requiring neither green nor white, so a `{G}` reduction against Kitchen Finks takes generic. The rules do not say this in so many words; it follows from CR 107.4e leaving the choice until the cost is paid. |
| Counters that do more than count | CR 122.1b, 122.4, 613.1f | A keyword counter should grant its keyword in layer 6 (CR 613.1f), and CR 704.5r caps a kind at N where a card says so. Both are storable - the counters are there - but neither is applied. |
| The second half of a delayed-cast keyword | CR 702.34a, 702.74a, 702.185a, 715.3d | The *casting* side of flashback, evoke, plot, foretell, warp, and Adventure works, and **the announcement record is filled**: `Casting.cast` calls `Game.note_cast` (keyword, face, modes, `x_value`) as the spell goes on the stack, so `Game.cast_record` and `Game.was_cast_with` have answers. Flashback's "then exile it" replacement in `machines/replacement.py` reads the record and works - its test passes. Warp's delayed exile trigger reads `Game.was_cast_with` and works too. What still does not: Adventure, because the card on the stack is still the front face (CR 715.3b's alternative characteristics) - `casting.exile_adventured` performs the exile by hand and `scenarios/test_adventure.py` xfails on resolution - and evoke's sacrifice, which is a triggered ability nothing creates (`scenarios/test_evoke.py` has the xfail). |
| Suspend | CR 702.62a-d, 116.2f | `Suspend 3—{2}{B}{B}` is parsed, count and all, and is not executed. Suspend is **three** abilities (CR 702.62a): a static one in hand that exiles the card with N time counters by the special action of CR 116.2f, an upkeep trigger that removes a time counter, and a trigger on the last one coming off that lets the card be played without paying its mana cost, with haste if it is a creature. The annotated-exile machinery would carry the first, `ExileMarker` needs a `SUSPENDED` entry and `CardState.counters` already holds time counters; the two triggers would fit `keyword_triggered_abilities` once `TriggerEvent` can say 'a counter was removed'. Delay's own "counter target spell... exile it with three time counters... it gains suspend" is the same gap wearing a counterspell's clothes: `_COUNTER_THEN_SUSPEND_REDIRECT_RE` in `machines/effects.py` recognises the whole shape (so it is not silent) but deliberately does nothing at all - countering the spell while dropping "it gains suspend" would leave it exiled with no way back, a board that looks right and is not, so the entire paragraph fails closed with a `SuspendRedirectNotice` (`Game.suspend_redirect_notices`) instead. `scenarios/test_counterspells.py::test_delay_fails_closed_with_a_notice_instead_of_half_applying` is the proof. |
| A self-referential cost reduction based on the spell's own chosen target | CR 601.2f | Mystical Dispute's "This spell costs {2} less to cast if it targets a blue spell." is a different shape from `Game.cost_reduction_for`'s board-static reductions (Emrakul's graveyard-card-types row above): the condition depends on *this spell's own announced target*, which is chosen after the cost would need to already be known. `_SELF_COST_REDUCTION_LINE_RE` in `machines/effects.py` only strips the sentence so it does not break the card's separate "Counter target spell unless its controller pays {3}." resolution clause - the reduction itself is not computed anywhere, so Mystical Dispute always costs its full printed {2}{U} regardless of target. |
| A team-wide temporary pump with no target ("Creatures you control get +N/+N until end of turn.") | CR 611.2 | Now correctly told apart from CR 611.3's anthem (see the Modelled row above) and reaches a `LayerNotice` instead of silence, but no shape in `machines/layers.py` actually builds the continuous effect yet - Violent Outburst's own "+1/+0" from this deck's other cascade card never applies. Its cascade half is unaffected: the exile/hit/free-cast pipeline does not touch this line at all. |
| Dash's other two abilities | CR 702.109a, 603.7, 608.3g, 613.1f | The alternative cost works and `Game.was_cast_with(spell, "Dash")` records it. The return-to-hand is a delayed triggered ability with warp's exact shape - `Game._create_resolution_delayed_triggers` builds warp's and not dash's - and the haste is a layer 6 grant the hand-written `LAYER_EFFECTS` registry has no entry for. `scenarios/test_dash.py` has both xfails. |
| CR 704.5n applied to things that are not Equipment | CR 704.5n, 704.5p | `machines/keywords.equipment_state_based_actions` is subtype-aware now: it consults `_ATTACHES_TO` and unattaches only an Equipment or Fortification on an illegal host (CR 704.5n), leaving Auras to CR 704.5m. **CR 704.5p's action is written** - `attachment_state_based_actions`, unattaching unconditionally everything that is neither Aura, Equipment, Fortification, nor battle - but nothing dispatches it and no test covers it. Not currently reachable: the only attached permanents in the pool are Equipment and one Aura reading `Enchant creature`. |
| An Aura on an object CR 704.5m cannot judge | CR 704.5m, 303.4c, 702.16c | `machines/keywords.aura_state_based_actions` **is** dispatched now. What it cannot judge is CR 303.4c's "other applicable effects": CR 702.16c's "a permanent with protection can't be enchanted by Auras that have the stated quality" is not checked (no pairing in the pool can reach it - the only Aura printing is white and the only creature with printed protection has it from black and red), and CR 303.4d's Aura that is also a creature is not either. Both fail open. CR 704.5m's "or player" branch **is now reachable** - `CardState.attach_to` reads a target through `TargetRef.coerce`, which accepts a `Player` as readily as a `CardState`, and `aura_state_based_actions` checks a player attachment's legality (still in the game) directly off `attachment` - `scenarios/test_aura_attachment.py`'s former xfail now passes for real, with Curse of Exhaustion (`Enchant player`) rather than Hyena Umbra. |
| Mobilize's tokens | CR 702.181a, 111.1 | The trigger fires off a real attack and resolves creating nothing, because the effect is entirely token creation. `scenarios/test_mobilize.py` asserts that honestly rather than xfailing it - the gap is tokens, not mobilize. |
| Alternative characteristics on the stack | CR 715.3b, 715.4 | `Casting.cast_as_adventure` charges the Adventure face's mana cost, but `Card` reports the front face's types, power, and text everywhere, so an Adventure on the stack is still a Creature and resolves onto the battlefield. **A split card's own version of this gap is fixed (W6, CR 709.3b)** - see "Choosing a split card's own half" above; scoped to `Layout.SPLIT` deliberately, so this row's Adventure gap is unchanged. |
| Multiplayer options beyond Free-for-All defaults | CR 801-811 | Free-for-All (CR 806) with its defaults works at three or more players. Not modelled: limited range of influence (CR 801), the attack-left/right and attack-multiple-players options (CR 802, 803) - `declare_attacker` will let any opponent be attacked - and every team variant (CR 805, 808-811). CR 800.4a moves a departed player's objects off the shared zones by *controller* - `Game._player_left` still selects by `state.controller == username`, even though ownership is modelled separately now (`CardState.owner`, stamped by `Player.add`). |
| Drawing, in team and limited-range-of-influence multiplayer | CR 104.4d, 104.4e, 104.4g | Free-for-all draws are modelled (`scenarios/test_drawing_the_game.py`), including the case where a player left earlier. The teams (CR 104.4d, 104.4g) and LROI (104.4e) draw variants are not - same scope as the multiplayer row. |
| Protection beyond targeting and damage | CR 702.16c, 702.16d, 702.16f, 702.16j, 702.16k | Only CR 702.16b is enforced, and only at the CR 608.2b recheck: `machines/targeting.py` reads the *caster's* text and has nothing to say about the target's, so `Casting.choose_targets` still lets a protected target be announced. `Game.why_cannot_target` is the check it needs, and it exists with no callers. CR 702.16c/d need attachments. **CR 702.16e is enforced end to end now**: `machines/combat._deal_combat_damage` and the damage entries in `machines/effects.py` name their source, so `Game.protection_from_damage` prevents spell and combat damage alike (`scenarios/test_prevention_effects.py`), and this holds for *granted* protection too (`scenarios/test_protection_grants.py`), not only a permanent's own printed text. CR 702.16f would live in `machines/combat.py`, which does not read protection at all - a *different* blocking restriction now does (see "A plain 'can't be blocked' restriction" above), but it is read off the attacker's own text, not off protection's stated quality, so a card whose only "can't be blocked" comes from CR 702.16f itself is still unenforced; no printing in the pool has protection *and* attacks with a quality that matters against a real blocker, so this has not been exercised either way. A quality that names a card type is read everywhere, and a **colour** is read on the damage side (`Game.source_has_quality`) and now also merged in for a granted quality (`Game._effective_protection_qualities`), though still not on the targeting side; "everything" and a player-as-quality are parsed out and then ignored. Protection on a *player* is not modelled: `Player` has no text. |
| Where the CR 601.2f self-reduction hook lives | CR 601.2f | `Casting.determine_cost` does not consult the game, so a spell that reduces its own cost off the board only gets its discount through `Game.determine_total_cost`. A scenario that calls `casting.determine_cost()` directly pays full price. The reader itself is narrow on purpose: it matches "costs {N} less to cast for each card type among cards in your graveyard" and nothing else. |
| Making a controlled player act, beyond priority | CR 723.4, 723.5, 723.7 | CR 723.5 is enforced where the engine can ask the question - `PriorityMachine.require` gives the pass to the controller and refuses it to the controlled player - but casting, activating, attacking, and blocking take no "who decided this" argument, so nothing checks that it was the controller who chose. `Game.why_cannot_decide_for` and `Game.why_cannot_pay_with` (CR 723.5a) answer the question; no caller asks them. CR 723.4's information rules and CR 723.7's restrict/require clauses are not modelled at all. |
| Emrakul, the Promised End's control duration | CR 723.1 | The cast trigger is fully registered: the control half through `Game.gain_control_of_player`, and the extra turn as a delayed triggered ability (CR 603.7, CR 603.7e) that fires at the end step of the controlled player's turn - `effect="grant_extra_turn"`, `step=Step.END_STEP`, `subject_player=<victim>`, `only_when_active=<victim>`. That ordering is the rule: CR 500.7 adds an extra turn "directly after the specified turn", so granting it at resolution would put it before the turn being stolen. What is still missing is the **duration** - "during that player's next turn" - because `Game.gain_control_of_player` takes no duration, so control is handed over and never returned. Savor the Moment now has its `EFFECTS` entry; only its "skip the untap step" half is an xfail. |
| Skipping a turn, step, or phase | CR 500.7, 614.10 | Extra turns are inserted correctly, but nothing can *skip* one. CR 723.1b's "if a turn is skipped" is tested through an extra turn deferring the controlled player's turn instead, which reaches the same state by a different road, and Savor the Moment's "Skip the untap step of that turn" has an xfail in `scenarios/test_extra_turns.py` - the extra turn itself is granted now. |
| `count_expression`'s qualifier is a single CR 300.1 card type only | CR 205.2a | `machines/effects.py`'s shared "the number of \<type>[s] you control" / "\<type> cards in your graveyard" evaluator (consumed by Craterhoof Behemoth's pump magnitude and Grist, the Hunger Tide's -5) reads "creature[s]" and the other fourteen card types, and nothing else: a coloured qualifier ("green creatures"), a named-subtype qualifier ("Elves", "Human creatures"), or a compound one ("artifact or enchantment permanents") returns `None` and the caller falls through to its own ordinary fail-closed path rather than a guess. No card in the pool needs one of those shapes yet, so this is a known scope boundary, not a bug found and left. |

## Finding the gaps: `scripts/sweep_pool.py`

Two holes look identical from a passing test, and the script reports both:

```sh
uv run python scripts/sweep_pool.py --keywords   # keywords nothing acts on
uv run python scripts/sweep_pool.py --effects    # cards with text and no effect entry
uv run python scripts/sweep_pool.py --targeting  # targeting text the parser cannot read
uv run python scripts/sweep_pool.py --card "Grief"
```

The targeting report is at **zero** and is there to keep it there: a phrase
`machines/targeting.py` cannot read comes back `understood=False` and CR 115
legality is then not checked at all, which looks exactly like a card that
targets nothing.

The keyword report is the one that used to be missing. A card can have its
keyword parsed, printed, and returned by `parse_abilities`, and still have
nothing anywhere that acts on it - which is how evoke sat in the pool on five
cards doing nothing while every card-level sweep called them fine. A keyword
counts as executed only if `machines/combat.py`, `machines/casting.py`, or the
mana-ability path reads it; everything else is listed, with the cards carrying
it. Keep the two exception lists in the script honest, because anything on them
is a keyword the report will never mention again.

## Card effects

`machines/effects.py` is a scripted registry keyed by card name, not a rules
engine. There are three tables in it.

**`EFFECTS`, what a spell does.** Counterspell,
Swords to Plowshares, Twisted Image, Giant Growth, Dismember,
Unholy Heat, Mutagenic Growth, Assault Strobe, Violent Urge,
Malevolent Rumble, Monstrous Rage, Savor the Moment,
Preordain. Lightning Bolt no longer has a
row - see "Targeted single-object effects (wave 2)" below - and neither does
Lightning Helix any more: "deals 3 damage to any target and you gain 3 life"
mixes a targeted clause and a player clause, which `parse_mixed_effect_for_spell`
now reads clause by clause, trying the targeted parser and then the player
parser on each one (see "Mixed targeted/player effects" below). Spectral
Procession is gone too (W4): "Create three 1/1 white Spirit creature tokens
with flying" is one clause of `_parse_token_clause`'s shape - see "Token
creation (wave 4)" below. **W8 removes six more rows**: Electrolyze
("deals N damage divided as you choose among one or two targets", read by
`_DIVIDED_DAMAGE_RE`), Lava Dart and Violent Urge were tried too but Lava
Dart's flashback line still refuses the whole text (its row stays, see below)
while Violent Urge's own second-sentence *delirium* shape already reached
`create_continuous_effect` through `_is_layer_effect_text`, so its row was
dead weight the same way Preordain's used to be; Fog/Angelsong ("prevent all
combat damage that would be dealt this turn", `_PREVENT_ALL_COMBAT_DAMAGE_RE`),
Bandage ("prevent the next N damage that would be dealt to \<target> this
turn", `_PREVENT_NEXT_DAMAGE_TO_TARGET_RE`), and Awe Strike ("the next time
target creature would deal damage this turn, prevent that damage[, You gain
life equal to the damage prevented this way.]", read as one CR 608.2c
instruction by `_merge_prevent_damage_from_target_clauses`). Every other card
without a row either resolves and does nothing or is reached by one of the
effect parsers off its own printed text.

The remaining three are the earlier token wave:

| Card | What executes | What does not |
|---|---|---|
| Malevolent Rumble | Reveals four, puts a permanent card into hand, the rest into the graveyard, then creates the Eldrazi Spawn, in printed order (CR 608.2c) | *Which* permanent card, and whether to take one at all, are real `Game.may` / `CHOOSE_CARDS` questions (CR 608.2d) now; the unscripted default still takes the first permanent in library order |
| Monstrous Rage | The +2/+0 in sublayer 7c (CR 613.4c) and the Monster Role token created attached to the target (CR 111.10k, CR 701.3a). The Role's own +1/+1 and trample are `LAYER_EFFECTS["Monster"]`, CR 704.5m/CR 704.5z both police it, and combat reads the granted trample off the computed board | Nothing |
| Savor the Moment | "Take an extra turn after this one" (CR 500.7) | "Skip the untap step of that turn" - a rules-modifying continuous effect (CR 611.3) with nowhere to live |

Four more came in with the decision point and the prevention shields:

| Card | What executes | What does not |
|---|---|---|
| Preordain | Scry 2, then draw, in printed order (CR 608.2c). The scry is a real question put to the controller (CR 608.2d, CR 701.22a), and CR 701.22b's "scry 0 is not a scry" falls out of `Game.scry`. Has no `EFFECTS` row: `parse_player_effect_for_spell` reads both clauses straight off the printed text | Nothing |
| Fog, Angelsong | A combat-only `ShieldKind.ALL` prevention shield over the whole board (CR 615.1, CR 615.1a), expiring in the cleanup step (CR 514.2). No `EFFECTS` row any more (W8): `_PREVENT_ALL_COMBAT_DAMAGE_RE` reads the sentence off the printed text | Nothing. Angelsong's cycling is a way to discard it rather than cast it (CR 702.29a) and never reaches the parser |
| Bandage | A `ShieldKind.AMOUNT` shield of 1 on the target (CR 615.7), then the draw (CR 608.2c). "Any target" is a permanent or a player and either can be shielded. No `EFFECTS` row any more (W8): `_PREVENT_NEXT_DAMAGE_TO_TARGET_RE` reads the first clause, the ordinary player-clause parser reads the draw | Nothing |
| Awe Strike | A `ShieldKind.NEXT_INSTANCE` shield naming the targeted creature as the *source* (CR 615.8), so its next instance of damage is prevented wherever it was headed. No `EFFECTS` row any more (W8): `_merge_prevent_damage_from_target_clauses` reads both sentences as one CR 608.2c instruction | Nothing. The shield sets `gains_life_when_prevented=True` only because the card's own second sentence says so, so "You gain life equal to the damage prevented this way" (CR 615.5) runs from `Game.apply_prevention_shield` |

The last four came out of the Modern metagame sweep below:

| Card | What executes | What does not |
|---|---|---|
| Lava Dart | 1 damage to any target - exactly `_DAMAGE_TARGET_RE`'s shape, but its row stays (W8 tried deleting it): `Card.oracle_text` is two lines here, the second being "Flashback-Sacrifice a Mountain." (CR 702.34), and `_prepare_effect_clauses` refuses the whole text as one unreadable clause rather than reading the first line alone - see `tests/test_targeted_effects.py::test_a_flashback_line_takes_the_whole_effect_down` | Its flashback (CR 702.34) is a way to cast it, not part of resolution - `machines/casting.py`'s problem, not this table's |
| Unholy Heat | 2 damage, or 6 with *delirium*. The count is card types (CR 205.2a, CR 300.1) among cards in **your** graveyard, taken at resolution | Nothing. *Delirium* is an ability word with no rules meaning of its own (CR 207.2c), so the whole mechanic is that one sentence |
| Mutagenic Growth | +2/+2 until end of turn, sublayer 7c (CR 613.4c) | Needs a `ContinuousEffects` on the `Game`; without one it resolves and does nothing |
| Assault Strobe | Grants double strike (CR 702.4) in layer 6 (CR 613.1f, CR 113.10) | Nothing. Combat reads the granted double strike off the computed board, so CR 510.4's extra damage step follows |
| Violent Urge | +1/+0 in 7c and first strike in layer 6, plus double strike when *delirium* holds. One resolution across two layers (CR 613.6), and the granted first strike causes the extra damage step. No `EFFECTS` row any more (W8): the whole text - including its ability-word-prefixed *Delirium* second sentence - is read whole by `_is_layer_effect_text`'s fallback to `create_continuous_effect`, the row having been dead weight since that fallback existed | Nothing |

Two of those are half-effects, and the half that is missing is a continuous
effect in both cases:

| Card | What executes | What does not |
|---|---|---|
| Electrolyze | Two damage divided among the targets, then the draw (CR 121.1). The targets *are* announced now - `machines/targeting.py` reads "one or two targets" as one CR 115.4 target with a floor of one and a ceiling of two. No `EFFECTS` row any more (W8): `_DIVIDED_DAMAGE_RE` reads the first clause off the printed text, the ordinary player-clause parser reads the draw | **Fixed (W13):** the division is the caster's own announcement when `Casting.announce_division` is called (`CardState.division`, read by `_deal_divided_damage_shares`); a caster who never calls it still gets the old even-split fallback, so every pre-W13 Electrolyze scenario is unchanged |
| Twisted Image | The switch (sublayer 7d, CR 613.4d, until end of turn) and then the draw, in printed order (CR 608.2c) | Nothing. `Game` holds the `ContinuousEffects` store now, so the switch reaches the board and CR 704.5g judges lethal damage against it |

**`TRIGGER_EFFECTS`, what a triggered ability does**, keyed by
`(card name, TriggerEvent, marker)`. The third part is a lowercase fragment of
the trigger's own printed text, and it is what lets a card with two triggers on
one event have two entries: `trigger_effect_for` still takes `(name, event)`,
because `Game._effect_of` has only those, and returns a dispatcher that reads the
resolving ability's text when a card has more than one. An empty marker means
"every trigger this card has on this event", which is what most entries carry.

| Card | Trigger | What actually executes |
|---|---|---|
| Solemn Simulacrum | enters | Searches the library for the first basic land and puts it onto the battlefield tapped, **then shuffles** (CR 701.24a, CR 701.24b). The "you may" is a real question now (CR 608.2d) whose default is to take it. Has no `TRIGGER_EFFECTS` row: `parse_search_and_put_effect` reads it straight off the printed text. |
| White Orchid Phantom | enters | Destroys the targeted nonbasic land (CR 701.8a), then its **controller** - not the Phantom's controller - searches their library for a basic land and puts it onto the battlefield **tapped**, then shuffles, in printed order (CR 608.2c). Has no `TRIGGER_EFFECTS` row (W3): the destroy is `_parse_targeted_clause`'s shape, the search is `_parse_search_clause`'s "its controller may" shape (`_build_search_clause`), and `parse_mixed_effect` reads both clauses off the printed text with no table row - the same two-clause shape as Ghost Quarter's activated ability below. |
| Solemn Simulacrum | dies | Draws a card. The "you may" is a real `Game.may` question now (CR 608.2d); the default is still to take it. Has no `TRIGGER_EFFECTS` row: `parse_player_effect`'s "you may draw a card" clause reads it. |
| Guttersnipe | cast | Two damage to each opponent. Whole ability. No `TRIGGER_EFFECTS` row any more (W8): `_DAMAGE_EACH_OPPONENT_RE` reads "\<source> deals N damage to each opponent" straight off the printed text, and covers Impact Tremors (no row, ever) the same way - `tests/scenarios/test_triggered_abilities.py::test_a_card_with_no_registry_row_gets_the_each_opponent_damage_shape_too`. |
| Hellrider | attacks | One damage to the attacked player. Damage to a planeswalker does nothing, because loyalty is not modelled. |
| Ashmouth Hound | blocks | One damage to the other creature in the pair. Whole ability. |
| Delver of Secrets | beginning of upkeep | Looks at the top card and transforms on an instant or sorcery (CR 701.27a). The flip now **changes characteristics**: `CardState.up_face` returns the back face while `transformed` is set (CR 712.8e), so a flipped Delver is Insectile Aberration, a 3/2 Human Insect with flying - it attacks for 3, cannot be blocked by a ground creature, and keeps mana value 1 off its front face (CR 202.3b). See the "Transforming a permanent" row above and `scenarios/test_transformed_characteristics.py`. Previously this table understated the bug in the other direction: before the fix that made `layers.py`/`CardState` fall back to `card_faces[0]` for power, toughness and oracle text, `Card` reported *neither* face for a `transform` or `modal_dfc` creature - Scryfall leaves the top-level fields null - so every double-faced creature was a powerless, textless 0/0 rather than its printed front face, in combat and in state-based actions alike. |
| Thopter Assembly | beginning of upkeep | Returns itself to its owner's hand **and now creates the five Thopter tokens too** (W8: `create_tokens`/`THOPTER` were already in this file for Hangarback Walker, so the docstring claiming tokens were unmodelled was stale - a row-masked bug found while auditing this entry for deletion, fixed without deleting the row). Its intervening *if* ("if you control no Thopters other than this creature", CR 603.4) is still not modelled, so it fires - and returns/recreates - every upkeep rather than only the first. |
| Devourer of Destiny | cast | Exiles the targeted permanent. The "that's one or more colors" restriction is not checked. Has no `TRIGGER_EFFECTS` row: `parse_targeted_effect` reads its single "exile target permanent" clause straight off the printed text. |
| Tishana's Tidebinder | enters | Counters the targeted activated or triggered ability (CR 113.9), then records the layer 6 "for as long as this creature remains on the battlefield" effect on the countered ability's source (CR 611.2b, 613.1f). Both halves run: `Game.find_ability_by_id` resolves the target, and `Game.why_cannot_activate` asks the computed board whether the ability survived (CR 613.5). |
| Ulamog, the Ceaseless Hunger | cast, attacks | No `TRIGGER_EFFECTS` row for either ability. "exile two target permanents" is `parse_targeted_effect`'s count-agnostic exile shape (`_targets_understood`), so it exiles both targeted permanents (CR 701.13a) before the 10/10 resolves off the ability's own printed text. **Its attack trigger now works too (W7b)**: "defending player exiles the top twenty cards of their library" reads "defending player" as CR 508.5/508.6 anaphora off the attack event's own `GameEvent.defender` (`_parse_defending_player_exiles_top_n_clause`), resolved to a username by `machines.combat.defending_player` - generalised from taking a live `Attack` to taking a bare `TargetRef`, so a resolving trigger can ask the same question long after the attack itself has left `game.combat`. See `scenarios/test_attack_trigger_defending_player.py`. |
| Ugin, Eye of the Storms | cast (two triggers) | No `TRIGGER_EFFECTS` rows any more either: both `CAST_SPELL` triggers - "When you cast this spell" and "Whenever you cast a colorless spell" - print "exile up to one target permanent that's one or more colors", which is the same count-agnostic exile shape, so `trigger_effect_for`'s fallback reaches both (told apart because `Game._effect_of` always hands it the *resolving* ability's own text, not a hardcoded one - see `tests/scenarios/test_cast_triggers.py::test_ugins_second_trigger_fires_off_a_later_colorless_spell`). The "that's one or more colors" restriction is still not checked. **His loyalty abilities resolve too**, with no `ACTIVATED_EFFECTS` rows: `+2: You gain 3 life and draw a card.` is two ordinary player clauses; `0: Add {C}{C}{C}.` reaches `_parse_add_mana_clause` (CR 106.4) because CR 605.1a's "it's not a loyalty ability" keeps it off the mana-ability fast path; and `−11: Search your library for any number of colorless nonland cards, exile them, then shuffle. Until end of turn, you may cast those cards without paying their mana costs.` is one CR 608.2c instruction read by `_parse_exile_then_play_permission_pair`, granting a `PlayPermission` per exiled card. See `tests/scenarios/test_loyalty_abilities.py` and `tests/scenarios/test_play_from_exile.py`. |
| Ranger-Captain of Eos | enters | Searches for a creature card with mana value 1 or less and puts it into hand, then shuffles. The printed "you may search" is CR 701.23g and is asked; CR 701.23b's "isn't required to find" is asked inside the search; the reveal is information only. Has no `TRIGGER_EFFECTS` row (W3): `_SEARCH_AND_PUT_RE`'s `max_mv` group reads the "with mana value 1 or less" bound straight off the printed text, so `_parse_search_clause` covers the whole sentence with no table row. **W5**: its sacrifice ability now runs too - "Your opponents can't cast noncreature spells this turn" is `machines.casting_restrictions.parse_casting_rule_clause`'s shape, reached by `_parse_mixed_clause`'s fallback with no `ACTIVATED_EFFECTS` row - see the rules-modifying casting-restriction row in the Modelled table above. |
| Sowing Mycospawn | cast | Searches for a land and puts it onto the battlefield untapped. Neither of its two `CAST_SPELL` triggers has a `TRIGGER_EFFECTS` row any more: this one is `parse_search_and_put_effect`'s shape and reaches it through the fallback, told apart from the card's other trigger because `Game._effect_of` always hands `trigger_effect_for` the resolving ability's own printed text. The kicked trigger's text parses to nothing and is deliberately left that way: it is an intervening *if* (CR 603.4) that should not trigger at all when the spell was not kicked, and kicker (CR 702.33a) is not tracked, so `intervening_if_holds` reads it as true. |
| Emrakul, the Promised End | cast | Gains control of the target opponent, then creates a delayed triggered ability (CR 603.7, CR 603.7e) that grants that player an extra turn at the beginning of the end step of *their* turn. That ordering is CR 500.7: an extra turn is added "directly after the specified turn", so granting it during this resolution would slot it in before the turn being stolen. **The control duration is still wrong**: the card gives control "during that player's next turn" and `Game.gain_control_of_player` has no duration, so control is handed over now and never returned. |
| Ajani, Nacatl Pariah | enters | Creates a 2/1 white Cat Warrior token (CR 701.7a). No `TRIGGER_EFFECTS` row any more (W4): `_parse_token_clause`'s shape, read off the trigger's own printed text. Its other trigger - "whenever one or more other Cats you control die" - **now fires**: `machines/triggers.py` reads a non-self `DIES` condition narrowed by subtype, so a Cat token dying puts it on the stack. Its effect now runs too: `_parse_may_exile_self_then_return_clause` reads "you may exile Ajani, then return him to the battlefield transformed under his owner's control" off the trigger's own printed text (CR 201.5's name self-reference; no registry row), exiles him and returns him through `put_onto_battlefield(transformed=True)` (CR 712.14a), so he comes back as the planeswalker Ajani, Nacatl Avenger with CR 306.5b's 3 loyalty counters. `scenarios/test_tokens.py`'s test is no longer an xfail. |
| Ocelot Pride | beginning of end step | **Both sentences run.** Creates a 1/1 white Cat token. **The intervening *if* is judged for real** - `Game.gain_life` records who gained life this turn (CR 119.9), so CR 603.4's "if you gained life this turn" is a genuine check, not an unconditional pass. Then, if the controller has the city's blessing, creates a copy (CR 707.2, `token_copy_of`) of every token they control that entered the battlefield this turn (`CardState.turn_entered`, stamped once in `Game.enter_the_battlefield`). *Ascend* (CR 702.131b) is a real per-player designation, `Player.has_citys_blessing`, granted once a player controls ten or more permanents and never lost, checked in `ascend_state_based_actions` alongside the other background state-based checks. No `TRIGGER_EFFECTS` row: both sentences are `_parse_token_clause` and `_parse_city_blessing_token_copy_clause`'s shapes, read off the trigger's own printed text, so `trigger_effect_for`'s fallback reaches the whole ability. This card used to keep a name-keyed row specifically so the second sentence could be dropped while the first still ran unconditionally - a real game hit exactly that: a player with 11+ permanents got one Cat a turn instead of the doubling, silently. That is no longer how a half-readable paragraph is handled anywhere in this codebase: an ability is read as a whole or not at all (CR 608.2c). Not modelled: CR 702.131a (ascend on a spell) and CR 702.131d's continuous-effect reapplication timing - see `machines/keywords.ascend_state_based_actions`'s docstring. |
| Seasoned Pyromancer | enters | Discards two, draws two, then creates one 1/1 red Elemental per nonland discarded *this way* (CR 608.2c order). **Which two cards are discarded is the discarding player's own `CHOOSE_CARDS` question (CR 701.9b)** through `Game.ask`; the unscripted default still discards the front of hand. |
| Drowner of Truth | cast | No `TRIGGER_EFFECTS` row any more (W4): "create two 0/1 colorless Eldrazi Spawn creature tokens with 'Sacrifice this token: Add {C}.'" is `_parse_token_clause`'s shape, quoted rules text included. **It still never actually triggers in a real game**: "if {C} was spent to cast it" is not one of the four shapes `intervening_if_holds` reads, so CR 603.4 fails it closed and the ability never reaches the stack at all - true before this wave and true after, since the old hand-written row was equally unreachable. |
| Wurmcoil Engine | dies | No `TRIGGER_EFFECTS` row any more (W4): CR 608.2c's clause split cuts "create a 3/3 ... token with deathtouch and a 3/3 ... token with lifelink" into two independent noun phrases at "and", and `_parse_token_clause` reads each - the second has no "create" of its own, which is why the verb is optional in the regex. This is the entry that makes a *token copy* of Wurmcoil work, since CR 707.2 copies the printed text and CR 111.7 lets the dying token fire it before it ceases to exist. |
| Hangarback Walker | dies | Creates one 1/1 flying Thopter per +1/+1 counter it had, read off `last_known_counters` because CR 122.2 has already destroyed them and CR 603.10a lets the trigger look back. Keeps its `TRIGGER_EFFECTS` row: "for each +1/+1 counter on this creature" is not a fixed `_COUNT` word, so `_parse_token_clause` refuses the clause rather than guess a count of one. |
| Soul Warden | enters | Gains 1 life whenever another creature enters, tokens included (CR 110.1). Whole ability. |

**Ability-side routing to `create_continuous_effect_of_ability` is text-driven
now, not a per-card row.** Basking Rootwalla's and Karn, the Great Creator's
`ACTIVATED_EFFECTS` rows existed only to route the ability there - the actual
pump/type-change/P-T-set was always `machines/layers.py`'s
`parsed_layer_effects` reading the ability's own text - so
`machines/effects.py`'s `_is_layer_effect_text` (tried after the ordinary
clause parser fails) recognises the shape and reaches the same function with
no row, and `ACTIVATED_EFFECTS` is now empty. The same recognition reaches a
**triggered** ability of the same shape, which never had a row-based path at
all: Oliphaunt's "Whenever this creature attacks, another target creature you
control gets +2/+0 and gains trample until end of turn." used to fire and
resolve to nothing; it now actually pumps and grants trample, proven in
`scenarios/test_parsed_layer_effects.py` by a trampler dealing damage through
a blocker it could not have without both halves applying. Getting a
*triggered* ability's own effect text this far also exposed a shape
`parsed_layer_effects` had never had to read before: its trigger condition
("Whenever this creature attacks, ") shares the line with the effect and
`_effect_sentences` did not strip it the way it already stripped an
activated ability's cost - `_TRIGGER_CONDITION_PREFIX_RE` is the fix.
`Tower Above`'s "Until end of turn, target creature gets +4/+4 and gains
trample, wither, and \"...\"" is the spell-side twin of the same gap:
duration-first phrasing failed even the loose "does this look like our
territory" check (`_LOOKS_LIKE_LAYER_EFFECT_RE` anchored on the subject
coming first) and did nothing with no `LayerNotice`.
`_normalize_duration_first` reads the duration wherever it sits (CR 611.2a
states it "as stated by the spell or ability", not pinned to one end of the
sentence); Tower Above's granted keywords are still not one this wave reads
(a bare word list, not a quoted extra ability), so it now fails closed with a
notice instead of silently doing nothing. The anthem shape (CR 611.3) is
deliberately excluded from this routing decision
(`is_resolution_layer_effect_text`): a permanent spell whose only text is a
"Creatures you control get +N/+N." (Glorious Anthem) must not also create a
one-shot copy of its own static ability on cast, which is what a first,
too-eager version of this routing did - the anthem is CR 611.3's own
`effects_for` battlefield sweep and never a CR 611.2 resolution effect.

**`ACTIVATED_EFFECTS`, what an activated ability does**, keyed by
`(card name, index)`:

| Card | Ability | What actually executes |
|---|---|---|
| Vampiric Rites | `{1}{B}, Sacrifice a creature:` | Gains 1 life and draws a card. Whole ability. |
| Skirk Prospector | `Sacrifice a Goblin: Add {R}.` | No entry needed - it is a mana ability, so `Game.activate_ability` resolves it without the stack and puts `{R}` in the pool. |
| Basking Rootwalla | `{1}{G}:` | Creates the +2/+2 until-end-of-turn continuous effect on itself (CR 611.2, 613.4c), and the once-each-turn restriction is enforced (CR 602.5b). Needs the game to hold a `ContinuousEffects`; without one it resolves and does nothing. Has no `ACTIVATED_EFFECTS` row any more, nor does Karn, the Great Creator's `+1` (see the row-count note above the table). |
| Arid Mesa, Bloodstained Mire, Flooded Strand, Marsh Flats, Misty Rainforest, Scalding Tarn, Verdant Catacombs, Windswept Heath, Wooded Foothills | `{T}, Pay 1 life, Sacrifice this land:` | No per-card entry: `activated_effect_for` falls back to `parse_search_and_put_effect`, which reads "Search your library for a `<type>` or `<type>` card, put it onto the battlefield, then shuffle." straight off each card's own text. Searches for a card with one of the two printed **land types** (CR 305.6), puts it onto the battlefield untapped, **then shuffles** (CR 701.24a). The whole three-part cost is paid on activation (CR 602.1a). It is not a land drop (CR 305.1, CR 701.18a), so the land drop stays available. Misty Rainforest and Verdant Catacombs used to have no registry entry at all and silently did nothing; they now work for the same reason every fetchland does. |
| Expedition Map | `{2}, {T}, Sacrifice this artifact:` | Same fallback, reading "Search your library for a land card, reveal it, put it into your hand, then shuffle." - any land (a broader quality than a land type), into hand instead of onto the battlefield. |
| Fiery Islet, Sunbaked Canyon | `{1}, {T}, Sacrifice this land:` | Draws a card. Whole ability. |
| Goblin Bombardment | `Sacrifice a creature:` | 1 damage to any target - no longer a table row, reached by the wave-2 targeted-effect parser. Whole ability - the sacrifice is a cost (CR 602.1a) and is paid before the ability is on the stack. |
| Ghost Quarter | `{T}, Sacrifice this land:` | Destroys the target land (CR 701.8a), then its **controller** searches for a basic land (a supertype, CR 205.4c) and puts it onto the battlefield, in printed order (CR 608.2c), then shuffles. Both questions - CR 701.23g's printed "may search" and CR 701.23b's "isn't required to find" - are put to the *victim*, not to the activator. Has no `ACTIVATED_EFFECTS` row (W3): `parse_mixed_effect` reads the destroy clause and the "its controller may search" clause together off the printed text - see `scenarios/test_search_as_a_clause.py`. |

An ability with no entry still triggers or activates, still goes on the stack,
can still be responded to, and is still removed by CR 608.2n. It simply has no
effect when it gets there.

This is the single biggest gap between the model and a real engine, and it is
deliberate: a general effect system needs targeting, triggers, and continuous
effects first. Until then, a scenario relying on a card's text must add that
card's effect to the registry.

## Targeted single-object effects (wave 2)

Wave 1 (above) taught the model untargeted player effects - gain life, draw,
mill, scry, surveil - off a card's own printed text, with no table row. Wave 2
does the same for the largest remaining block: a **single** targeted verb -
`Destroy target X.`, `Exile target X.`, `<Source> deals N damage to target X.`
(and "to any target"), `Return target X to its owner's hand.`,
`Tap`/`Untap target X.`, and `Put N +1/+1 (or -1/-1) counters on target X.`
Each is one clause naming exactly one target (CR 115.6's "up to" and "one or
two" are excluded on purpose). `parse_targeted_effect_for_spell` and
`parse_targeted_effect` in `machines/effects.py` are the parsers. `effect_for`
wires them into `parse_mixed_effect_for_spell`'s per-clause dispatch; since W3,
`trigger_effect_for` and `activated_effect_for` do the same through
`parse_mixed_effect`, which tries a targeted clause, then a search clause
(`_parse_search_clause`), then the wave-1 player-effect parser on each clause
in turn, rather than trying three whole-effect parsers in sequence.

The restriction is never re-parsed by this wave's own regex: each verb
function calls `machines/targeting.py`'s `profile_for_text` on the captured
"target ..." phrase (count words included, since "up to two" and "another"
both sit *before* the word "target") and refuses to build an effect unless
`understood` is true, the phrase is exactly one requirement, and that
requirement takes exactly one target. A phrase mentioning mana value, power,
or toughness, or an "if" clause, is refused outright even when `understood`
says otherwise - see the false-confidence gap below.

**Measured result**: sweeping `tests/fixtures/cards` for every spell and
ability text not already covered by an `EFFECTS`/`TRIGGER_EFFECTS`/
`ACTIVATED_EFFECTS` row, 23 distinct pool cards go from "resolves and does
nothing" to actually executing (Lightning Bolt and Goblin Bombardment already
worked before this wave via a now-deleted registry row, so the net-new count
is 21): Aether Adept, Anafenza, the Foremost, Bojuka Bog, Bone Splinters,
Colossal Skyturtle, Footlight Fiend, Formidable Speaker, Goblin Bombardment,
Guerrilla Gorilla, High Noon, Icy Manipulator, Keen-Eyed Curator, Kiora's
Follower, Lava Spike, Lightning Bolt, Nahiri, the Harbinger, Ravenous
Chupacabra, The Filigree Sylex, Tormod's Crypt, Utter End, Walking Ballista,
Wistfulness, World Breaker.

### Two registry rows deleted because the parser fully subsumes them

- **`EFFECTS["Lightning Bolt"]`** - "Lightning Bolt deals 3 damage to any
  target." is one clause of exactly this wave's shape.
- **`ACTIVATED_EFFECTS[("Goblin Bombardment", 0)]`** - the sacrifice is a cost
  (CR 602.1a), paid before the ability is on the stack; the effect half on its
  own, "This enchantment deals 1 damage to any target.", is the same shape.

`Lava Dart` deliberately **keeps** its row: its full oracle text carries a
second line for flashback, so `split_effect_clauses` produces a second clause
this wave does not cover and the whole effect fails closed - exactly the
point of failing closed, not a bug to route around.

### Known gaps, found and verified while writing this wave

- **`machines/targeting.py`'s Oxford-comma noun list, and negated
  supertypes, are now read correctly (fixed in the wave documented just
  below this section).** `profile_for_text("target artifact, creature, or
  land")` used to come back `understood=True` with `card_types={ARTIFACT}`
  alone; it now reads all three. `tests/scenarios/test_targeted_effect_parser.py`'s
  Icy Manipulator test still only targets an artifact - narrowing it further
  is this file's job, not this wave's, and left as a follow-up rather than
  reshaping a passing test to prove a fix that belongs elsewhere.
- **A restriction can be `understood=True` and still silently drop a
  comparison.** "target nonland permanent with mana value 3 or less" (Abrupt
  Decay) and "target creature if it has mana value 2 or less" (Fatal Push)
  both used to read as `understood=True`, with the mana-value clause simply
  never reaching the `TargetRequirement`. **Fixed in `machines/targeting.py`**
  (see the "Targeting text the parser cannot read" row above): `TargetRequirement`
  now reads and enforces the comparison for real
  (`comparison_attribute`/`comparison_operator`/`comparison_value`,
  `_rejects_comparison`), consulted by `Game.legal_target` on resolution
  (CR 608.2b) for both a spell and, as of this wave, an ability on the stack
  too (see the zones/abilities row below).
  **`machines/effects.py`'s guard is loosened to match, this wave**: the old
  `_UNENFORCED_RESTRICTION_RE` blanket-refused any clause mentioning mana
  value, converted mana cost, power, toughness, *or* "if"; the first four are
  retired now that the comparison is real (Abrupt Decay measured working end
  to end - `tests/scenarios/test_targeted_effect_parser.py`). "if" is kept as
  its own `_UNENFORCED_CONDITIONAL_RE`, but only refuses when the phrase's
  parsed requirement carries no `comparison_attribute` - so Fatal Push's "if
  it has mana value 2 or less" is trusted (the "if" *is* the comparison) while
  a hypothetical unrelated conditional stays refused. **Fatal Push's own Revolt
  clause is read too, as of W6** - `_parse_revolt_destroy_or_exile_clause` in
  `machines/effects.py` recognises the two-paragraph shape and hands back the
  ordinary destroy verb, while `TargetRequirement.comparison_value_if_revolt`
  (`machines/targeting.py`) is what actually widens the threshold to 4 when
  Revolt is live - see the "Revolt" row above. Prismatic Ending's "if its mana
  value is less than or equal to the number of colors of mana spent to cast
  this spell" still names a count `_extract_comparison` cannot pin down at
  all - no digit, no X - so `profile_for_text` still, correctly, reports
  `understood=False` for the *targeting* restriction (nothing changed here:
  the count genuinely is not known until after targets are announced, CR
  601.2g-i). **W6 reads the condition anyway, at resolution** - see the
  "Converge" row above - which is the difference between an unrestricted
  target and an unresolved one.
- **The same wave relaxes the zones half of that guard for exile and return.**
  `_targets_understood` used to force every verb's `TargetRequirement.zones`
  to be exactly `{Zone.BATTLEFIELD}`, because `exile_ability_targets` and
  `return_ability_targets_to_hand` used to hard-filter to
  `Zone.BATTLEFIELD` too - a graveyard-targeting exile or return silently did
  nothing even once it parsed. CR 406.2/701.13a exile "from whatever zone
  it's currently in" and CR 701.19a's "return" names no particular origin
  zone, so both now take a `battlefield_only` flag (`True` still for destroy,
  tap, untap, and put-counters, which CR 701.8a/701.26a/701.26b/122.6 define
  only for a permanent on the battlefield) and the two execution functions no
  longer filter by zone at all, trusting `Game.legal_target`'s recheck
  instead (CR 608.2b). That recheck used to be a no-op for an **ability** on
  the stack ("An ability is only checked for 'is it still there'"", this
  file's own words until this wave) - closing that gap was necessary for the
  zones relaxation to be safe at all: `Game.legal_target` now reads an
  ability's own printed text with `profile_for_text` the same way
  `activate_ability`/`why_cannot_target_with_trigger` already do at
  announcement, so a target that leaves the zone its ability's restriction
  requires is caught on resolution just as a spell's is.
  **Measured, not estimated** (an earlier survey on this project claimed
  "~47 you-may clauses"; the real number was 1): across the whole fixture
  pool, exactly two cards are unlocked end to end by the zones relaxation -
  Faerie Macabre ("Exile up to two target cards from graveyards") and
  Keen-Eyed Curator ("Exile target card from a graveyard").
  Kozilek's Command's "Exile up to X target cards from graveyards" was one
  mode of a modal spell, and `effect_for` did not dispatch modes at all at the
  time this paragraph was written - it now does (`resolve_modal_spell`, see
  the Modelled table's "What a mode does on resolution" row), and this mode
  reaches `exile_ability_targets` through it like any other card's.
  **A later wave closed the two remaining look-alikes.** Tormod's Crypt and
  Bojuka Bog's "exile target player's graveyard" targets the *player*
  (`allows_cards=False`), which `exile_ability_targets`'s
  `isinstance(target, CardState)` check can never reach - `exile_target_
  players_graveyard` is a separate clause `_parse_targeted_clause` now routes
  "target player's graveyard" phrases to instead, ahead of the generic
  exile-target regex, and empties every card in the targeted player's own
  graveyard (own included) into exile. Raise Dead and Eternal Witness's
  "return ... to **your** hand" (rather than "to its owner's hand") used to
  fail `_RETURN_TARGET_RE` outright; `_RETURN_FROM_YOUR_GRAVEYARD_TO_HAND_RE`
  is the sibling pattern that reads it. Rest in Peace's "exile all
  graveyards" and Sanctifier en-Vec's "exile all cards that are `<quality>`
  from all graveyards" (no target at all) and Endurance's "up to one target
  player puts all the cards from their graveyard on the bottom of their
  library in a random order" (CR 115.6) are new shapes entirely - see
  `tests/scenarios/test_graveyard_zone_effects.py`. Rest in Peace's and
  Sanctifier en-Vec's own second sentences ("If a card ... would be put into
  a graveyard ..., exile it instead") are static replacement effects, a
  different ability from the one this closes, and remain unattempted - there
  is no home in `machines/effects.py` for a graveyard-redirecting
  replacement the way `machines/replacement.py` already has for "enters
  tapped".
- **A triggered ability's targets, chosen before its source exists, are not
  checked.** `Game.why_cannot_target_with_trigger` looks for the source card
  on the battlefield or the stack (CR 603.6a); an enters-the-battlefield
  trigger queued with `choose_trigger_targets` while its source is still in
  hand finds nothing and is not checked at all - `Game.choose_trigger_targets`
  will accept an illegal target for Ravenous Chupacabra ("target creature an
  opponent controls") if it is queued before the creature is cast. Once the
  source is already on the battlefield (Anafenza, the Foremost's attack
  trigger, tested this wave) the restriction is read correctly. Pre-existing
  behaviour of `Game.choose_trigger_targets`, not introduced by this wave.
- **A triggered ability requiring a target, with none chosen, still goes on
  the stack.** `Game._ask_trigger_targets` asks for up to
  `TargetingProfile.max_targets` (CR 115.6's "up to N") but never enforces
  `min_targets`; an empty `CHOOSE_TARGETS` answer is accepted regardless of
  whether the ability's text made a target mandatory, exactly as an empty
  answer always was before this kind existed. Deliberately not fixed this
  wave: the clause that would decide it (CR 603.3d's continuation past "if a
  choice is required when the triggered ability is put onto the stack ...")
  truncated in `knowledge_search(type="rules")` across four differently
  phrased queries in the session that wrote `CHOOSE_TARGETS`, so the rule was
  never read in full and nothing here asserts it.
- **`+N/+N until end of turn` was deliberately not attempted.** Every pump
  card the sweep found (Giant Growth, Mutagenic Growth, Dismember, Monstrous
  Rage) already has an explicit `LAYER_EFFECTS` row, and the one new
  candidate (Collective Brutality) is modal. Building the generic
  `ContinuousEffects.add` path for zero measured new cards was not worth the
  risk this wave.
- **Mixed targeted-and-untargeted multi-clause effects are now merged** - see
  "Mixed targeted/player effects" below. `parse_mixed_effect_for_spell` is the
  clause-level parser this bullet asked for; Lightning Helix and Vraska's
  Contempt are the pool cards that turned up with exactly this shape.
- **A destroy/exile/tap/etc. clause naming two direct objects joined by
  "and"** ("Destroy target creature and target land." - Fumarole) is split by
  `split_effect_clauses` into two clauses, the second missing its verb, and
  fails closed. Not attempted this wave.

## Mixed targeted/player effects

`parse_targeted_effect_for_spell` and `parse_player_effect_for_spell` are each
whole-effect parsers: every clause has to be their one shape or the card is
refused. A card mixing the two kinds of clause - Lightning Helix's "deals 3
damage to any target and you gain 3 life" - parsed under neither and needed a
table row for exactly that reason. `parse_mixed_effect_for_spell` in
`machines/effects.py` is a per-clause dispatcher: it splits the text the same
way both waves already did, then tries the targeted parser and then the player
parser on *each clause independently*, so a wholly-targeted or
wholly-player-clause card still parses (each clause just succeeds on the first
of the two it is tried against) and a genuinely mixed one now does too. It
replaces both whole-effect calls in `effect_for`'s fallback.

Fail-closed stays **per clause, not per parser**: one clause that matches
neither parser still throws the whole effect away, exactly as each
whole-effect parser already refused on its own (Fatal Push, Assassin's Trophy
are unaffected and still resolve to nothing).

**`EFFECTS["Lightning Helix"]` deleted.** Vraska's Contempt ("Exile target
creature or planeswalker. You gain 2 life.") is the second real card proving
the shape, added to the fixture pool for this wave and never given a row.

**The preamble strip and modal bail are now shared.** Before this wave, only
`_parse_targeted_clauses` stripped a spell's non-effect preamble (CR 118.8a's
additional-cost line, "This spell can't be countered") and refused a modal
card (CR 700.2) before splitting into clauses; `_parse_player_clauses` did
neither. Both are now one shared step, `_prepare_effect_clauses`, used by the
targeted parser, the player parser, and the mixed dispatcher alike. Two
consequences:

- **Cathartic Reunion now runs.** "As an additional cost to cast this spell,
  discard two cards. Draw three cards." used to have its cost line read as an
  unparseable effect clause, which failed the whole card closed even though
  "Draw three cards" alone is `parse_clause_effect`'s plain shape. This was a
  missed win, not a wrong one, but it is fixed now.
- **A modal card whose every mode happens to be player-parseable can no
  longer run all of them.** This would have been a fails-open bug - CR 700.2c
  says only the chosen mode's targets and effect apply, and a linear reading
  across every bullet point runs every mode instead. Verified this session: no
  card in the fixture pool actually exercises the difference, because a real
  "Choose one —" line is itself unparseable by every clause regex today (it
  contains "choose", which none of them recognise) and so already failed
  closed on its own, for an unrelated reason, before this fix existed. The
  shared modal bail is defense in depth against a future clause regex (a
  "you may", an "or") that could otherwise let such a card through -
  `tests/test_mixed_effects.py::test_a_modal_card_whose_every_mode_is_player_parseable_does_not_run_them_all`
  pins the behaviour with a synthetic string for exactly that reason.

### Anaphoric "controller" clauses: "\<destroy/exile\> target X. Its/that X's controller ..."

Solitude's own defect, found in a playtest: its enters trigger ("exile up to
one other target creature. That creature's controller gains life equal to its
power.") resolved with a legal target and did nothing at all - no exile, no
life gain, and no record anywhere that the second sentence had gone unread.
`_parse_mixed_clauses` correctly refused the whole effect per clause
(CR 608.2c has no notion of running half an instruction), but silently.

`_parse_anaphoric_clause_pair` in `machines/effects.py` reads both sentences as
one instruction: the first names a target (CR 608.2b legality applies only
here), the second is CR 400.7's plain anaphora back to whatever the first
found - never a fresh target of its own. The referent's controller and power
are snapshotted from the battlefield **before** the first sentence's verb runs
(CR 608.2i) - reading them afterward would see `CardState.move_to`'s empty
husk (counters cleared, layers no longer computed for an off-battlefield
permanent) and silently return the bare printed power instead of the real one.
An unreadable second sentence now leaves an `AnaphoricClauseNotice` on
`Game.anaphoric_clause_notices` instead of failing silently.

Six real cards in the fixture pool now resolve in full through this, with no
registry row: **Solitude**, **Swords to Plowshares** (`EFFECTS` row deleted -
the old `exile_targets` exiled and never gained the life, a live fail-open
this fix corrects), **Assassin's Trophy**, **Ghost Quarter**, **White Orchid
Phantom**, **Cityscape Leveler**. **Boseiju, Who Endures'** Channel ability
joined them in a later wave, once its two separate reasons were fixed: its
search sentence's "a land card with a basic land type" phrasing (`_has_a_
basic_land_type`, distinct from `_quality_matcher`'s "basic land" supertype
check - see the off-battlefield-activation row in the Modelled table above),
and its own trailing "This ability costs {1} less to activate for each
legendary creature you control." sentence, which turned out not to be a third
clause of the destroy-then-search ability at all but a separate static ability
(`_split_off_trailing_cost_reduction`) sharing its printed line. One still
fails closed, for a reason this wave does not extend to:

- **Craterous Stomp's** "Craterous Stomp deals 3 damage to target creature an
  opponent controls. Each other creature that player controls becomes a
  Coward..." is a different shape entirely: the first clause is damage, not
  destroy/exile (so the object never moves and there is no LKI question), and
  the second clause acts on a *group* of permanents the referent controls
  rather than reading a value or searching - a group continuous type-changing
  effect this wave does not build.

Also out of scope, and left failing closed exactly as before: stack-object
anaphora (Access Denied, Force of Negation, Delay, Transcendent Dragon -
"that spell" refers to an object on the stack, not a permanent). Subtlety's
own stack-object shape ("choose up to one target creature spell or
planeswalker spell. Its owner puts it on their choice of the top or bottom
of their library.") is now built, but as a dedicated targeted-clause merge
(`_parse_choose_up_to_one_target_spell_clauses`) rather than through this
anaphoric-referent machinery - see "Exile 'until this leaves the
battlefield'" below, where it is documented alongside Static Prison.
Phelia's own delayed-trigger anaphora is fixed - see "Delayed-trigger clauses"
below; Ephemerate's "exile target creature you control, then return it" is a
different shape (one resolution, CR 400.7's new object, not a delayed
trigger) and is fixed too - see "Exile-then-return clauses" further down;
Postmortem Lunge's antecedent (a reanimation target named by a variable mana
value) is fixed too, as of W6 - see "A reanimation target named by a
variable mana value..." in the Not-modelled table above (moved there since
it is now modelled, not a gap).

Scenario coverage: `tests/scenarios/test_anaphoric_referent_clauses.py`. Unit
coverage for the parser and the notice: `tests/test_mixed_effects.py`.

## Token creation (wave 4)

`_parse_token_clause` in `machines/effects.py` reads CR 701.7a's "create ...
token(s)" off a card's own printed text and joins the same per-clause
dispatcher (`_parse_mixed_clause`) the targeted, search, and player clauses
already go through - tried after the targeted shape and before a search, so a
card mixing a token clause with either kind (none in the pool do yet, but
nothing stops one) still parses clause by clause.

Two noun-phrase shapes are read: "[create] [N] [P/T] [color(s)] [subtype(s)]
[artifact] creature token[s] [with <keywords or a quoted ability>]", and
CR 111.10's predefined tokens by name ("create a Food token"), now a small
table in `models/token.py` (`PREDEFINED`) rather than one keyed by the card
that creates them - **Food** (CR 111.10b) and **Powerstone** (CR 111.10h)
joined **Treasure** (CR 111.10a) and the **Monster Role** (CR 111.10k) this
wave, because Generous Ent and Cityscape Leveler are the pool's other two
predefined-token cards. Cityscape Leveler's "Its controller creates a tapped
Powerstone token" still does not parse - the subject is the ability's target's
controller, not "you", the same distinction `_build_search_clause` already
draws for a search but this wave's token clause does not - so it is text this
parser recognises the shape of but does not yet read end to end.

**Two shapes are refused on purpose, both fail-closed:**

- **"a token that's a copy of ..."** (CR 707.2) is checked for and refused
  before the noun-phrase regex is even tried - a copy needs the original's
  copiable values, which this parser does not read off anything. Repudiate //
  Replicate, Fanatic of Rhonas's eternalize, Caretaker's Talent, and Tamiyo,
  Compleated Sage's -X all hit this and all still resolve to nothing. Ocelot
  Pride's own second sentence used to as well; it is now read by a dedicated
  parser instead (`_parse_city_blessing_token_copy_clause`, see the ascend
  entry below and the Ocelot Pride row above) rather than by this one.
- **A count this parser cannot read as a fixed `_COUNT` word** - Hangarback
  Walker's "for each +1/+1 counter on this creature", Seasoned Pyromancer's
  "for each nonland card discarded this way" - simply does not match
  `_TOKEN_CLAUSE_RE`, so nothing silently substitutes a count of one. A tail
  after "with" that mixes a real keyword with unread text - Hangarback
  Walker's "with flying for each +1/+1 counter on this creature" - fails the
  same way: `_parse_token_tail` only accepts a single quoted ability or a
  comma/"and" list drawn entirely from a small keyword whitelist, and anything
  else takes the whole clause down with it (CR 608.2c has no notion of running
  half an instruction).

**Four rows deleted**, all reachable through the fallback with no table entry:
`EFFECTS["Spectral Procession"]`, and `TRIGGER_EFFECTS` for Ajani, Nacatl
Pariah's enters trigger, Drowner of Truth's cast trigger (quoted rules text on
the token, read verbatim into `TokenDefinition.rules_text`), and Wurmcoil
Engine's dies trigger (two tokens joined by "and", which CR 608.2c's clause
split already cuts into two independent noun phrases - the second has no
"create" of its own, which is why `_TOKEN_CLAUSE_RE` treats "create" as
optional).

**Hangarback Walker keeps its row** - its variable count depends on the
permanent's own counters at the moment it dies, which `_TOKEN_CLAUSE_RE` has
no notion of reading, so `hangarback_dies` still computes it directly.
`tests/scenarios/test_token_effect_parser.py` proves the reason with a direct
parser check rather than assuming it: `parse_mixed_effect` on the card's whole
printed trigger text comes back `None`, so if the row were ever removed the
fallback would create nothing rather than one Thopter regardless of counters.

**Ocelot Pride's row is gone.** A later ruling in this project forbids a
card-name row that exists to let one paragraph half-execute (see the Ocelot
Pride row above, and `docs/engine-coverage.md`'s ascend entry): `ascend`, the
city's blessing, and "tokens that entered this turn" are all built now, so
both of Ocelot Pride's sentences are read off its own printed text with no
row at all.

**One new card works that never had a row at all**: Generous Ent's "When this
creature enters, create a Food token." was not reachable before this wave
because tokens were not parsed off any text yet; it is `_parse_token_clause`'s
predefined-token shape now, no row needed.

**A token entering fires another permanent's own enters trigger** the same way
a card would (CR 110.1, CR 603.6a) - verified directly for Guide of Souls
against Spectral Procession's three Spirits, since this is the interaction most
likely to be missed if token creation and "enters" were wired up
independently.

**Not measured as "working end to end" even though their text matches the
shape**: Basking Broodscale's "you may create ... Eldrazi Spawn" (the counter-placed trigger
condition is not one `machines/triggers.py` reads), and Seasoned Pyromancer's
graveyard-activated "Create two 1/1 red Elemental creature tokens" (nothing
can activate an ability from a graveyard yet). Dalkovan Encampment's own
*mobilize* tokens **are now fixed end to end (W4)** - see its own row in the
per-card table below and "Trigger conditions the matcher cannot read" above;
Voice of Victory's identical second half is presumably reachable the same way
but has not been proven directly.

## Count-agnostic targeting (wave 2 continued)

`_targets_understood` required `minimum == maximum == 1`, so CR 115.6's "up to
N" and "N or M target ..." refused outright even for a verb whose meaning does
not change with the count. It now accepts a count-agnostic requirement
(`count_agnostic=True`) for **destroy, exile, tap, untap, return, and
put-counters-on** - each simply repeats itself once per legal target,
including "up to one" resolving to zero (CR 608.2b already skips an illegal
target the same way a chosen-zero target is just never iterated).

**Damage is deliberately excluded and stays strict.** Multiple damage targets
divide a total at announcement (CR 601.2d - Electrolyze's "divided as you
choose among one or two targets"), a different mechanism `deal_damage`/
`damage_ability_targets` do not model; `deal_divided_damage` is the real thing
and is not reached by this parser. "Deals N damage to two targets" and "deals
N damage to up to one target" both still refuse.

**`_targets_understood` also now checks the requirement's `zones` field**,
refusing anything but exactly `{Zone.BATTLEFIELD}`. This was found while
relaxing the count check: Faerie Macabre's "Discard this card: Exile up to two
target cards from graveyards." matches the count-agnostic exile shape by count
alone, but `exile_ability_targets` (and every sibling verb function) only ever
acts on `Zone.BATTLEFIELD` targets - resolving it would have silently exiled
nothing, a fails-open trap the inventory flagged in advance. It stays
unscripted instead. Raise Dead has the same graveyard-targeting shape but
already failed for an unrelated reason (`_RETURN_TARGET_RE` requires "to its
owner's hand", and Raise Dead prints "to your hand"), so Faerie Macabre is the
card that actually exercises the new zones check -
`tests/scenarios/test_targeted_effect_parser.py::test_faerie_macabre_resolves_without_exiling_a_graveyard_card`
proves it end to end: the ability still resolves (CR 608.2n) and the discard
cost is still paid, it just exiles nothing.

**Two `TRIGGER_EFFECTS` rows deleted.** Ulamog, the Ceaseless Hunger's "exile
two target permanents" and both of Ugin, Eye of the Storms' "exile up to one
target permanent that's one or more colors" triggers are all
`parse_targeted_effect`'s count-agnostic exile shape now, off the ability's
own printed text - see the card-by-card table above. Ugin's two triggers are
still told apart correctly with no marker at all, because
`Game._effect_of` always hands `trigger_effect_for` the *resolving* ability's
own text.

## Delayed-trigger clauses parsed off printed text

Phelia, Exuberant Shepherd's attack trigger used to resolve and do nothing:
"exile up to one other target nonland permanent" parsed and ran, but "At the
beginning of the next end step, return that card to the battlefield under its
owner's control. If it entered under your control, put a +1/+1 counter on
Phelia." had no reader, so `_parse_mixed_clauses` correctly refused the whole
ability (CR 608.2c has no notion of running half an instruction) - silently.
`machines/delayed.py` already had every piece of CR 603.7's machinery
(`DelayedTrigger`, creation timing, one-shot spend, the CR 603.7c zone check,
CR 603.7d/e source and controller capture) for warp and Emrakul's extra turn;
the gap was purely that nothing read a printed "at the beginning of the next
\<step\>, \<verb\> it" off a card and called `DelayedTriggers.create`.

`_parse_delayed_blink_clauses` in `machines/effects.py` is the fix for
Phelia's own shape: it runs the exile clause itself (rather than delegating to
`exile_ability_targets`, which throws the moved object away), then closes over
the exiled `CardState` when it builds the `DelayedTrigger` - the same
clause-linking idea `_parse_anaphoric_clause_pair` already uses for "destroy/
exile target X. Its controller ...". A third, optional rider clause ("if it
entered under your control, put a +1/+1 counter on \<name\>") reads the
recipient's name generically against the resolving source's own name at run
time, so it is not one more name-keyed table row. `_parse_delayed_single_clause`
covers the shape with no antecedent of its own: no object at all ("draw a
card", Mishra's Bauble) or the trigger's own event subject (Aether Membrane's
"return that creature ..." off `ability.event.related_id`, CR 509.1a's other
half of a blocking pair). `DelayedTrigger.callback` now carries a parsed
clause's own closure directly, ahead of `DELAYED_EFFECTS`'s string key, for
the same reason that registry's "no printed text to read" justification never
applied here.

**CR 603.7c's identity gap, fixed and already latent for warp.** A delayed
trigger names its subject by `id` plus an expected zone, but this engine
mutates a `CardState` in place across a zone change rather than replacing it
(CR 400.7's "new object" is otherwise unrepresented) - so an object that left
its expected zone and came back to it by some *other* route still matched,
which CR 603.7c's parenthetical explicitly forbids ("if that object left that
zone and then returned, it's a new object and thus won't be affected").
`CardState.zone_change_stamp` is a fresh id stamped on every `move_to` call;
`DelayedTrigger.expected_stamp` captures it at creation and `still_affects`
now requires a match. This was already reachable through warp's own delayed
exile before this fix (a warped permanent blinked and returned to the
battlefield before the end step would have been wrongly exiled as if it were
the original) - `_create_resolution_delayed_triggers` now stamps it too.

Fixed: Phelia, Exuberant Shepherd; Aether Membrane ("return that creature to
its owner's hand at end of combat", CR 511.2's own `BEGINNING_OF_STEP` timing);
Mishra's Bauble (plus a no-op reader for "look at the top card of target
player's library", CR 701.20e); Ragavan, Nimble Pilferer's dash (the identical
return-to-hand executor `_create_resolution_delayed_triggers` already needed
for warp).

**Left failing closed, on purpose, with a `DelayedClauseNotice` instead of
silence:** Nahiri, the Harbinger's -8 (the antecedent is a search result). A
half-run blink is worse than the pre-existing no-op - an opponent's permanent
exiled forever is a strictly worse board than the card doing nothing - so it
executes no part of its instruction. **Postmortem Lunge's own reanimation
antecedent is fixed, as of W6** - see "A reanimation target named by a
variable mana value..." in the Not-modelled table above; a dedicated
reanimate/haste/delayed-exile parser (`_parse_delayed_reanimate_haste_exile_
clauses`) reads it as three clauses of one instruction rather than leaving it
here. **Deliberately excluded:** Dalkovan
Encampment and Voice of Victory take a *plural* token subject ("Sacrifice
them"), a different shape this wave does not read.

Scenario coverage: `tests/scenarios/test_delayed_trigger_clause_parsing.py`.
The pre-existing `tests/scenarios/test_delayed_triggered_abilities.py` and
`tests/scenarios/test_dash.py` cover the generic `machines/delayed.py`
mechanism this wave builds on.

## Exile-then-return clauses: Ephemerate's own blink, and Rebound

Two defects, fixed together because the same card exposed both. Every CR
number below was looked up with `knowledge_search(type="rules")` in the
session that fixed this.

**Defect 1 - no reader for "return it to the battlefield".** Ephemerate's
"Exile target creature you control, then return it to the battlefield under
its owner's control." used to resolve and do nothing: clause 1 parsed alone
as an ordinary exile (`_EXILE_TARGET_RE`), clause 2 had no reader anywhere -
only `_RETURN_TARGET_RE`'s "return it to its owner's hand" existed - so
`_parse_mixed_clauses`'s all-or-nothing fold correctly discarded the whole
effect (CR 608.2c has no notion of running half an instruction), but
*silently*: the sweeper listed Ephemerate as `silent`, not as a recorded
notice. `_parse_exile_then_return_clause_pair` in `machines/effects.py` is the
fix, wired into the same clause-pair dispatch `_parse_anaphoric_clause_pair`
already uses: a parameterised reader for "exile target X, then return it to
the battlefield[ tapped][ transformed][ under its owner's/your control]", not
a card-name row. `_RETURN_TO_BATTLEFIELD_RE` reads the three optional groups;
a card whose wording falls outside them (recognised by the looser
`_LOOKS_LIKE_RETURN_TO_BATTLEFIELD_RE` prefix match) still takes the whole
effect down through `_unreadable_anaphoric_clause`'s now-shared notice path,
rather than silently keeping only the exile half - an exile with nothing to
return it is a strictly worse board than doing nothing at all, so fail-closed
had to stay fail-closed.

Three rules this reader has to get right, none of them free from the existing
`exile_ability_targets`/`Game.exile_permanent`/`Game.put_onto_battlefield`
primitives it composes:

- **CR 400.7** - the returned object is a new one. `CardState.move_to`
  already implements this (fresh `zone_change_stamp`, `id` unchanged), so
  reusing `Game.exile_permanent` then `Game.put_onto_battlefield` - the same
  two calls `each_player_exiles_sacrifices_and_returns_creatures` already uses
  for Living End - was enough; no parallel path was written.
- **CR 110.2 / 110.2a** - the controller of the returned permanent is read off
  the card's own words ("its owner's control" vs "your control"), never
  defaulted to whoever controls the resolving spell. Owner and controller are
  never collapsed into one question: a creature blinked out from under an
  opponent's control returns to the *opponent* when the card says "its
  owner's control".
- **CR 122.2 / CR 302.6 / CR 508.1a** - counters and summoning sickness follow
  automatically from `move_to`'s battlefield branch; this reader never
  "restores" either.

**A latent bug this reader's own test (`test_ephemerate_drops_an_aura_
attached_to_the_blink_target`) surfaced and `Game._detach_dependents` fixes:**
`CardState.move_to` already clears the *moved* card's own `attachment` as it
leaves (CR 400.7), but nothing cleared an Aura or Equipment's `attached_to`
pointing *at* it - stored by id, and this engine mutates a `CardState` in
place rather than minting a fresh id on return, so a permanent exiled and
returned **within one resolution** (no state-based-action check runs in
between; CR 704.3 only checks before a player would next receive priority)
had the same id both times and an Aura would silently "follow" the blink with
nothing ever catching it. `Game.exile_permanent` now calls `_detach_dependents`
the moment a permanent actually leaves the battlefield, `unattach()`-ing
anything pointing at it; the ordinary `aura_state_based_actions`/`equipment_
state_based_actions` sweep that runs once the whole spell finishes resolving
then does its real CR 704.5m/704.5n job (an Aura pointing at nothing goes to
its owner's graveyard, an Equipment pointing at nothing stays on the
battlefield unattached) exactly as if a live check had run in between.

**Defect 2 - Rebound was not implemented at all** (`grep -rn "rebound"` used
to return zero hits). CR 702.88a: "If this spell was cast from your hand,
instead of putting it into your graveyard as it resolves, exile it and, at
the beginning of your next upkeep, you may cast this card from exile without
paying its mana cost." Built as a keyword, in `machines/keywords.has_rebound`
plus `machines/delayed.rebound_recast`, never a name row, even though
Ephemerate is the only rebound card in the pool:

- The exile-instead-of-graveyard half hangs off the same hook flashback and
  Adventure already use - `Game.put_into_graveyard`'s own
  `ReplaceableEvent(kind=ZONE_CHANGE, destination=GRAVEYARD)`, applied in
  `machines/replacement._stack_replacements`. Unlike flashback (CR 702.34a's
  "any time it would leave the stack", which deliberately also catches a
  countered or fizzled spell), rebound's own CR 702.88a wording is narrower -
  "as it resolves" - so a new `ReplaceableEvent.resolving` flag, set only by
  `resolve_top`'s genuine CR 608 resolution path, gates it: a countered spell
  (CR 701.6, never resolves) or a fizzled one (CR 608.2b, "doesn't resolve"
  either) goes to the graveyard the ordinary way instead.
- "If this spell was cast from your hand" is read off `Game.cast_records`
  (`CastRecord.origin_zone`, new, copied from `Casting.origin_zone` as the
  spell goes on the stack) - read *before* `resolve_top` pops the record, not
  from the card's own printed text, which is what stops an Ephemerate cast
  from a graveyard or from its own previous rebound recast rebounding again
  (an infinite exile-and-recast loop otherwise).
- The delayed trigger for "at the beginning of your next upkeep" is a
  `DelayedTrigger` with `expected_zone=Zone.EXILE` plus `expected_stamp` (CR
  603.7c) and, since CR 702.88a says "**your** next upkeep" and not "the next
  upkeep", `only_when_active` set to the caster - the same scoping Emrakul,
  the Promised End's extra-turn trigger already needed, and for the same
  reason: without it, a one-shot trigger (CR 603.7b) created during erin's
  turn would spend itself on the opponent's upkeep if that happens to come
  first, and erin's own upkeep would never see it.
- The recast itself (CR 702.88b: "follows the rules for paying alternative
  costs") is `Game.cast_free_from_exile` - not the interactive `Casting`
  state machine (there is no live announcement to drive from inside a
  resolving ability's effect function), but the same "ask the controller"
  pattern `Game._ask_trigger_targets` already uses for a triggered ability's
  own CR 603.3d target announcement, then `Game.put_on_stack` plus
  `Game.note_cast(..., origin_zone=Zone.EXILE)`.

Scenario coverage: `tests/scenarios/test_ephemerate.py` (the blink, the Aura
trap, owner vs. controller, counters, Guide of Souls not firing off itself)
and `tests/scenarios/test_rebound.py` (exile instead of graveyard, the
next-upkeep recast, declining it, and the countered/fizzled spells that must
not be exiled at all).

## The Modern metagame sweep

The card pool was swept card by card against six real Modern tournament
decklists (Videre, 2026-08-24 and 2026-08-25; pilots Arianne, YungDingo,
nahuel10, Anemu, yunk3r, justFeather). Every card in all six was checked for
Modern legality with `resolve_cards(format="modern", fields="legality")` and all
68 distinct cards came back legal. This section is what that sweep found.

### Engine-wide gaps, in the order they cost the most

**1. ~~`Game` has no `ContinuousEffects`.~~ Fixed.** `Game` holds the store and
ends its "until end of turn" effects in `cleanup_step` (CR 514.2 ends those and
wipes marked damage in the same turn-based action, CR 703.4p). Every spell whose
whole effect is a continuous one - Mutagenic Growth, Assault Strobe, Violent
Urge, Giant Growth, Dismember, Twisted Image, Monstrous Rage - now changes the
board, and `Game.check_state_based_actions` judges CR 704.5f and CR 704.5g
against the computed board (CR 613.5). The defensive `getattr` in
`machines/effects.continuous_effects` is gone with it.

**2. ~~The layer engine and combat are disconnected.~~ Fixed.**
`machines/combat.has_keyword` reads the computed board through `Game.power_of`
and friends, so a keyword granted in layer 6 reaches combat: Violent Urge's
granted first strike now causes CR 510.4's extra damage step, and the
`tests/scenarios/test_delirium.py` xfail is gone. What a card *generates* is
still the hand-written `LAYER_EFFECTS` registry, so Cori-Steel Cutter's "has
trample and haste" grants nothing - that is the Not-modelled row about keyword
grants, not this one.

**3. ~~`TRIGGER_EFFECTS` is keyed by `(card name, TriggerEvent)`.~~ Fixed.** The
key is `(card name, TriggerEvent, marker)` now, where the marker is a lowercase
fragment of the trigger's own printed text. `trigger_effect_for` still takes
`(name, event)` - `Game._effect_of` has nothing else to give it - and returns a
dispatcher when a card has more than one entry for an event; the dispatcher reads
the resolving ability's text and picks, matching the longest marker first. Ugin,
Eye of the Storms has an entry per trigger. Sowing Mycospawn's two triggers now
have no entry at all - `Game._effect_of` always hands `trigger_effect_for` the
resolving ability's own printed text, so the search trigger reaches
`parse_search_and_put_effect` through the fallback and the kicked trigger's
unrelated text still parses to nothing.

**4. ~~Tokens are not modelled.~~ Fixed.**
`models/token.py` holds `TokenDefinition` (the characteristics a creating effect
states, CR 111.3), `TokenState` (a `CardState` over a `Card` synthesised from
them), `create_tokens` (CR 701.7a, CR 111.2), `token_copy_of` (CR 707.2),
`create_predefined_tokens` (CR 111.10), and `tokens_that_cease_to_exist`
(CR 111.7, CR 704.5d). A token is a permanent (CR 110.1) and needs no special
case anywhere else: it enters through `Game.put_onto_battlefield`, fires and sees
enters- and dies-triggers, is summoning sick (CR 302.6), takes counters, and can
be put onto the battlefield attacking (CR 508.4).

The four halves that live outside `models/token.py` are all in place:

- **CR 704.5d** - `Game._state_based_actions_once` calls
  `tokens_that_cease_to_exist`, so a dead token is gone by the time anybody
  next holds priority.
- **CR 111.8** - `TokenState.move_to` declines the move and every caller that
  relists a card asks `move_refused` first, so the token's `zone` and the list
  it sits in cannot disagree.
- **CR 701.7b** - `create_tokens` and `token_copy_of` raise a `CREATE_TOKENS`
  replaceable event, which is what Doubling Season's token half watches.
- **CR 704.5m and CR 704.5z** - the state-based actions that police Auras and
  Roles are dispatched.

What is left is per-card and is in the table below: Cori-Steel Cutter needs a
per-turn cast count and Kozilek's Command needs modal dispatch. Ragavan
(a combat-damage `TriggerEvent`), Dalkovan Encampment (a duration-bounded
delayed trigger, W4), and Ajani (a non-self-referential `DIES` shape) are all
now fixed - see their own rows below.

**5. No decision point. FIXED.** `machines/decisions.py` and `Game.ask`
implement CR 608.2d, including its second sentence - "the player can't choose an
option that's illegal or impossible" - so a question with one legal option is
answered by the rules rather than by a guess. `Game.scry` (CR 701.22a) and
`Game.surveil` (CR 701.25a) are built on it, scry 0 and surveil 0 correctly
being no event at all (CR 701.22b, CR 701.25c). A scenario answers in advance
through the harness: `scry_bottoming`, `scry_keeping_everything_on_top`,
`surveil_to_graveyard`, `will_take_the_may`, `will_pay_the_life`. Unanswered
questions fall through to a documented default table, not to improvisation.
**The registry work is done too**: `EFFECTS["Preordain"]` is
`sequence(scry(2), draw_cards(1))`, and Elegant Parlor, Thundering Falls and
Dragon's Rage Channeler no longer need a `TRIGGER_EFFECTS` row at all -
`parse_player_effect` reads "surveil 1" straight off each one's own text (see
item 1 above), the same fallback that also now covers Commercial District,
Hedge Maze, Meticulous Archive and Underground Mortuary, none of which ever had
a row. `DecisionKind.CHOOSE_CARDS` is now the choose-among-revealed-cards kind
(and doubles as the discard kind, CR 701.9b), and Malevolent Rumble and
Seasoned Pyromancer are wired through it via `Game.ask` - see the "silent
choices" table below. Expressive Iteration and Turntimber Symbiosis have no
registry entry at all yet, so they are not reached by this fix either way.

**6. ~~Shuffling is not modelled.~~ Fixed, registry included.**
`Game.shuffle_library` implements CR 701.24a, seeded from `Game.shuffle_seed`
and the shuffle count so a game is reproducible - CR 701.24a asks that "no
player knows their order", which is a statement about the players and not about
the program. CR 701.24b's "the found cards aren't included in the shuffle" is
the `keep=` argument. `Game.search_library` implements CR 701.23a's look at the
whole hidden zone, CR 701.23b's right to decline to find, CR 701.23d's forced
quantity, and CR 701.23h's hold-the-shuffle-until-the-end. The registry side is
fixed too: `machines/effects.py`'s `_search_library` helper calls
`game.search_library(...)` now, so every registered search effect shuffles, and
the xfails in `scenarios/test_shuffling.py` and `scenarios/test_fetching_a_land.py`
are cleared.

**7. Modal spells cannot dispatch by mode.** `machines/modes.py` parses and
validates the modes and `machines/casting.py` chooses them, but `CardState` does
not record which were chosen and `EFFECTS` is keyed by card name alone, so a
modal card's effect cannot know what it is meant to do (CR 700.2a). Blocks
Kozilek's Command and Thraben Charm.

**8. `X` is recorded, and more of what reads it is now wired. PARTIALLY
FIXED.** The value chosen for `{X}` lands on the cast record - `Casting.cast`
calls `Game.note_cast(x_value=...)` - and `game.cast_record(spell).x_value`
reads it back at resolution; Wrath of the Skies and Kozilek's Command's modal
dispatch already consumed it. Two more consumers now do, closing a live-game
report that turned out to be one root cause behind two symptoms:

- **Green Sun's Zenith.** `effect_for` substitutes the resolved X into a
  plain (non-modal) spell's own resolution text - but only once its own
  *unsubstituted* text has already been tried and found nothing, so Wrath of
  the Skies's own literal-"X" reader keeps working unchanged (see
  `effect_for`'s docstring). That alone was not enough: Green Sun's Zenith's
  second sentence, "Shuffle Green Sun's Zenith into its owner's library.",
  matched no clause shape and took the whole effect down with it (CR 608.2c
  has no half-effect) even after X was readable. `_strip_self_shuffle_clause`
  removes that sentence by the resolving card's own name before dispatch, and
  `machines/replacement.py`'s `_stack_replacements` reads the *same* sentence
  off the same oracle text to redirect the spell's own final zone (CR
  304.2/307.2, CR 715.3d's "instead of graveyard, elsewhere" shape) from the
  graveyard to its owner's library, shuffled in (CR 701.24a/c). Gated on
  `event.resolving`, so a countered Green Sun's Zenith still goes to the
  graveyard the ordinary way (CR 701.6a). See
  `scenarios/test_x_valued_search_and_self_shuffle.py`.
- **"[This] enters with X `<kind>` counters"** (Walking Ballista, Hangarback
  Walker, and by the same generic reading Chalice of the Void, Engineered
  Explosives). `machines/replacement.py`'s `_self_enters_modifiers` used to
  skip a variable counter amount outright, unconditionally, silently - CR
  107.3m ("the spell that became that object as it resolved had a value of X
  chosen for any of its costs" defines X for the entering object's own
  replacement effect) is now read off `Game.cast_records` at the moment the
  permanent enters, before the record is popped. An object with **no** cast
  record at all - found by a search effect rather than cast - still leaves X
  undefined and the replacement still skipped, unchanged; a genuinely cast
  X=0 still correctly places zero counters and CR 704.5f still kills the
  resulting 0/0 on the spot. See `scenarios/test_enters_with_x_counters.py`.

Slumbering Trudge ("enters with a number of stun counters equal to **three
minus X**") is a different, unread shape - not a bare "X counters", so
`_read_counters` never even reaches CR 107.3m's new fallback - and still
cannot scale.

**Nature's Rhythm - fixed (W7b).** `Search your library for a creature card
with mana value X or less ...` is a second X-valued search of the exact
shape Green Sun's Zenith's own fix targets, and the X-substitution half
(`effect_for`'s retry with `substitute_x`) already read it correctly - the
remaining gap was that the card's own text carries a second ability,
`Harmonize {X}{G}{G}{G}{G} (...)`, on its own line below the search
sentence; that line was not one of `_strip_non_effect_preamble`'s recognised
keyword lines, so `split_effect_clauses` read it as a second, unparseable
clause and poisoned the whole resolution the same way Green Sun's Zenith's
self-shuffle sentence used to, for an unrelated reason. `_HARMONIZE_LINE_RE`
strips the line the same way `_REPLICATE_LINE_RE`/`_CYCLING_LINE_RE` already
strip theirs - **Harmonize the keyword itself (CR 702.180/702.180a: casting
from the graveyard, tapping a creature to discount the cost) is still not
built anywhere**, only the line's poisoning effect on the unrelated search
sentence is fixed. Because this file's own static pool sweeper
(`scripts/sweep_pool.py`) never substitutes a real X value, it still reports
Nature's Rhythm (and Green Sun's Zenith) as "silent" - a pre-existing,
unrelated blind spot in the sweeper's own methodology, not a sign either
card is actually unhandled; both are proven working with a real cast X in
`scenarios/test_x_valued_search_and_self_shuffle.py`.

**9. Shockland "as this land enters, you may pay 2 life" does neither branch.
FIXED.** The two printed sentences are one CR 614.12a choice, not two effects,
and `_self_enters_modifiers` now joins them back together and puts the question
to the controller before the land enters. CR 119.4 decides whether paying is
legal at all, so a shockland fetched at 1 life enters tapped without anybody
deciding to tap it, and a scenario that scripts the illegal branch is refused
under CR 608.2d rather than being quietly given the other one. Both xfails are
cleared; the branches are pinned down one at a time in
`scenarios/test_decisions_during_resolution.py`. Covers Steam Vents, Sacred
Foundry, Stomping Ground, Breeding Pool and the rest of the cycle.

## Hidden-zone choices (wave W1)

Three primitives, each reused generally rather than built narrowly for one
card:

- **A player other than a revealed hand's owner choosing from it** (CR
  701.20a, CR 701.9b's "some effects ... allow another player to choose which
  card is discarded"). Thoughtseize's own paragraph - reveal, an overridden
  choice, the discard, an unconditional life loss - is read as one anaphoric
  run of clauses by `_merge_reveal_hand_choose_discard_clauses` in
  `machines/effects.py`, since "it"/"that card" thread through all four
  sentences and none can be parsed alone.
- **"Target player discards N cards"** (CR 701.9a), CR 701.9b's *default*
  chooser left alone - `_parse_target_player_discards_clause`. Go Blank's own
  second clause ("Then exile that player's graveyard") reuses the existing
  `exile_target_players_graveyard` outright rather than a copy of it, since
  both clauses resolve the same single target off `game.resolve_targets`.
  This also closes a pre-existing gap for Mind Rot ("Target player discards
  two cards.", `test_judge_triggers.py`'s DDR#886 scenario) - its own half now
  runs; Captain Howler's "whenever you discard" trigger still parses with no
  event, so that scenario still (and correctly) `xfail`s.
- **Look at the top N cards and split them into two destinations**, general
  past `Game.scry`/`Game.surveil`'s own fixed pair - `Game.look_at_top_and_
  split` in `models/game.py`, reusing `DecisionKind.SCRY`'s question rather
  than adding a kind. Duskwatch Recruiter's `{2}{G}` ability ("look at the top
  three... reveal a creature card... put the rest on the bottom in any
  order") sends its taken half to hand and its rest half to the bottom -
  neither of scry's own destinations - which is exactly why the primitive
  takes both groups off the library and leaves placement to the caller.
  `_merge_look_top_reveal_to_hand_clauses` enforces the card's own
  restriction (creature, at most one) on top of the generic split, since
  `CardSplit` itself has no notion of either.

"You may discard a card. If you do, `<consequence>`." (CR 118.12's discard
cousin of the existing sacrifice shape) is also now read,
`_merge_may_discard_if_you_do_clauses`, reusing `_parse_sacrifice_consequence`
outright for the "if you do" half. Formidable Speaker's ETB is the vehicle.

`Game.search_library` is widened to take a `zone: Zone = Zone.LIBRARY`
parameter (P7) - the same predicate-and-count search, run against a player's
hand or graveyard instead of their library, with the CR 701.24b shuffle only
firing for the library. **Wired up**: `_search_and_exile_matching_name` in
`machines/effects.py` calls it once per zone (graveyard, hand, library, in
printed order) for both **The Stone Brain** and **Surgical Extraction** -
"choose a card name"/"the same name as that card", then search all three
zones for matches and exile them, capped at "up to four" (Stone Brain) or
uncapped ("any number", Surgical Extraction), with the CR 701.24b/e shuffle
only ever touching the library. Both cards' own "graveyard, hand, and
library" and "with that name and exile them" wording carries a bare "and"
`_CLAUSE_SEPARATOR` would otherwise fragment, so both are read whole - a new
early check inside `_parse_mixed_clauses` tries the unsplit `text` before
any splitting happens, ahead of the ordinary per-clause dispatch.

The Stone Brain's own "choose a card name" reuses `DecisionKind.CHOOSE_A_
QUALITY` (no new kind) - the same question CR 614.12a's "as this enters,
choose a card name" already asks through for Pithing Needle and Disruptor
Flute, here asked mid-resolution instead of as an entering-the-battlefield
replacement effect, with the answer used locally rather than stored on
`CardState.choice` (nothing in either card's own text reads it back
anaphorically the way "the chosen name" does). Surgical Extraction needs no
such question at all - its name comes directly off the card its own
"target card in a graveyard other than a basic land card" found, a new
`machines/targeting.py` shape (`_read_other_than_exclusion`) that excludes
`Supertype.BASIC` alone rather than also excluding `Type.LAND` - CR 205.4a
closes "basic" to lands only, so the supertype alone already reads "basic
land card" correctly, and adding the type on top would wrongly refuse a
perfectly legal nonbasic dual too.

The Stone Brain's own cost, "Exile The Stone Brain", turned up two
pre-existing gaps in getting *there*, both fixed alongside this wave's own
work since neither card could be activated at all otherwise: `machines/
abilities.py`'s cost classifier and `_SELF_REFERENCE` (`models/game.py`) only
ever read a self-reference spelled "this `<type>`" (CR 700.7), not CR 201.5's
other form - a cost sentence repeating the permanent's own printed name -
so `_exiles_itself_by_name` reads that form too; and `CostComponent.pay`'s
own `ComponentKind.EXILE` branch assumed the exiled card always sat in one of
the *payer's* own per-player zones (true for every pre-existing example -
Force of Will's hand, Seasoned Pyromancer's graveyard) and broke the first
time a cost exiled a permanent straight off the shared battlefield instead;
it now delegates to `Game.exile_permanent` outright rather than mutating a
zone list by hand.

### Cards from the metagame that still do nothing, and what each needs

| Card | Missing mechanic | Rule |
|---|---|---|
| Ajani, Nacatl Pariah | **Fully working, `−4` included (W13).** Its enters trigger needs no `TRIGGER_EFFECTS` row (W4); "Whenever one or more other Cats you control die" now fires *and* resolves - exile-and-return-transformed is read off its own text, he returns as Ajani, Nacatl Avenger with 3 loyalty (CR 306.5b, CR 712.14a), and his back face's loyalty abilities are activatable (CR 712.8e, CR 109.3). The Avenger's `0` still records a `ReflexiveClauseNotice` - see its own row. His `−4` - "Each opponent chooses an artifact, a creature, an enchantment, and a planeswalker from among the nonland permanents they control, then sacrifices the rest" - is `_parse_each_opponent_choose_one_of_each_type_then_sacrifice` (`machines/effects.py`), generalised on the list of types rather than keyed to this card: one `CHOOSE_CARDS` question per type per opponent (each opponent's own choice, over that opponent's own board, CR 601.7a/602.3a), skipped entirely for a type the opponent controls none of (CR 107.1a), with everything left unclaimed sacrificed (CR 701.21a) | CR 111.1, CR 701.7a, CR 603.10a, CR 712.8e, CR 712.14a, CR 701.21a, CR 107.1a |
| Arena of Glory | Exert as a cost; mana with a spend restriction that also grants haste | CR 701.43a, CR 701.43d |
| Blood Moon | Registered in `LAYER_EFFECTS` already (layer 4). No `EFFECTS` entry is needed or wanted | CR 613.1d |
| Cavern of Souls | Both mana abilities parse and produce (the any-colour one takes a chosen colour). "As this enters, choose a creature type" is recorded on the permanent (CR 614.12a) and the spend restriction tied to that choice **is** enforced - the mana casts a creature spell of the chosen type and refuses anything else. With no type recorded the restriction is unreadable and the mana pays for nothing. Still not modelled: "can't be countered" | CR 106.6, CR 614.12a |
| Cori-Steel Cutter | Tokens work; the *trigger* does not. "Whenever you cast your second spell each turn" needs a per-turn cast count nothing keeps, so it would fire on the first spell too - deliberately left out of `TRIGGER_EFFECTS` rather than registered wrong. Equip and attachment are also missing | CR 702.6a, CR 301.5b, CR 111.1 |
| Dalkovan Encampment | **Fixed end to end (W4).** `_parse_attack_this_turn_create_tapped_attacking_tokens` in `machines/effects.py` creates a delayed trigger (CR 603.7a) watching the subjectless "you attack" event, with `remaining=None` (fires every attack this turn, CR 603.7b's stated duration) and `expires_end_of_turn=True` (swept by `DelayedTriggers.expire_this_turn`, called from `Game.cleanup_step`, CR 514.2). Each firing creates its own two tokens tapped and attacking (CR 508.4) and gives each its own one-shot "sacrifice at the next end step" delayed trigger, reusing the existing `"sacrifice"` `DELAYED_EFFECTS` entry rather than a new plural-subject field. `DelayedTrigger.subjectless_only` is the guard that stops a per-creature `ATTACKS` event double-firing this trigger alongside the subjectless summary event | CR 111.1, CR 508.4, CR 603.7a, CR 603.7b, CR 514.2 |
| Devourer of Destiny | Its cast trigger works. The opening-hand reveal (a static ability that functions in hand) does not | rule not looked up this session - the next agent must verify it before citing one |
| Disciple of Freyalise | "You may sacrifice another creature. If you do, gain X life and draw X" - X from the sacrificed creature's power, a decision, and a modal DFC land back | CR 111 not involved; needs a decision point |
| Dragon's Rage Channeler | **Its cast trigger surveils 1** (CR 701.25a). The *delirium* static pump - +2/+2, flying, and attacks each combat if able - is a layer 6 + 7c effect and is still unregistered | CR 701.25a, CR 613.1f, CR 613.4c |
| Drowner of Truth | Token creation reads correctly off the printed text now (W4, `_parse_token_clause`, no row needed), but the trigger **never actually reaches the stack**: "if {C} was spent to cast it" is not one of the shapes `intervening_if_holds` reads, so CR 603.4 fails it closed for lack of spent-mana tracking | CR 111.1, CR 603.4 |
| Eldrazi Temple | Both mana abilities parse and produce, and the spend restriction ("only to cast colorless Eldrazi spells or activate abilities of colorless Eldrazi") is enforced on both halves - see the spend-restriction row above | CR 106.6 |
| Elegant Parlor / Thundering Falls | **Registered in full**: enters tapped (CR 614.1c), then the enters trigger surveils 1 (CR 701.25a) | CR 614.1c, CR 701.25a |
| Emrakul, the Promised End | Its cast trigger works but the control duration does not; the cost reduction per card type in your graveyard is unread | CR 205.2a |
| Expressive Iteration | Three decisions plus "you may play the exiled card this turn" | CR 701.22a-adjacent; needs a decision point and a play-from-exile permission |
| Fanatic of Rhonas | **Fixed**: both mana abilities parse and produce, and the *ferocious* restriction ("only if you control a creature with power 4 or greater") is now enforced by `Game._activation_condition_holds` | CR 602.5b |
| Fight Rigging | Hideaway; a combat trigger; "play the exiled card without paying its mana cost" | CR 702.75a |
| Flagstones of Trokair | **Fixed and firing end to end.** `_trigger_event` now reads the spelled-out CR 700.4 form of "dies" ("is put into a graveyard from the battlefield"), so the trigger reaches the stack, and `parse_search_and_put_effect` already read its effect - "you may search your library for a Plains card, put it onto the battlefield tapped, then shuffle." - straight off the card | CR 700.4 |
| Flashback (the card) | Granting flashback to a card in a graveyard until end of turn - a layer 6 grant on a non-battlefield object | CR 613.1f, CR 113.10 |
| Galvanic Discharge | **Registered in full.** "Choose target creature or planeswalker" is CR 601.2c's ordinary announcement-time target; "you get {E}{E}{E}, then you may pay any amount of {E}" is a real `DecisionKind.PAY_ENERGY_AMOUNT` question (`_parse_target_get_energy_pay_damage`), and the amount paid is dealt as damage to the target | CR 107.14, CR 118.3 |
| Gemstone Caverns | **The conditional mana ability is fixed** - `{T}: Add {C}`, or any colour instead once it carries a luck counter (`ManaCondition`, checked against `CardState.counters`). Not modelled: the static ability that lets it start the game on the battlefield with a luck counter from the opening hand | CR 122.1 |
| Grand Arbiter Augustin IV | None of its three static abilities are read: "White/Blue spells you cast cost {1} less to cast" are colour-and-controller-conditional reductions no reader in `machines/cost.py` recognises, and "Spells your opponents cast cost {1} more to cast" is controller-relative, a shape `cost_modifier_effect` deliberately does not parse (see `Game.static_cost_modifiers_for`) - `looks_like_unparsed_cost_modifier` catches the increase line and records a `CostModifierNotice` instead of guessing which caster it means | CR 601.2f |
| Green Sun's Zenith | **Fixed.** The recorded `{X}` now scales the search's own "mana value X or less" bound, and the card's own "Shuffle Green Sun's Zenith into its owner's library" sentence - previously unparseable and taking the whole effect down with it - is read generically (by the resolving card's own name, not a table row) to redirect its final zone away from the graveyard. See the numbered gap-8 note above and `scenarios/test_x_valued_search_and_self_shuffle.py` | CR 107.3a, CR 701.23a/b, CR 701.24a/c, CR 304.2/307.2 |
| Guide of Souls | **Fixed end to end (W4).** Its "Whenever you attack" trigger fires (once per combat, CR 508.3d); `_parse_reflexive_pay_energy_clause` in `machines/effects.py` wires `Game.may_pay_energy` (built for Static Prison) into CR 603.12's reflexive-trigger machinery (built for Grist, the Hunger Tide) - a fixed-amount paid cost rather than a sacrifice. Its consequence - "put two +1/+1 counters and a flying counter on target attacking creature. It becomes an Angel in addition to its other types." - is `_parse_counters_and_becomes_type_clause`: the flying counter is a real CR 122.1b keyword counter now (`machines/layers.py::_keyword_counter_lines` feeds it into `Characteristics.abilities`, so `has_keyword` sees it), and the type change is layer 4 (CR 613.1d) with `Duration.INDEFINITE` since the card states no "until end of turn" | CR 107.14, CR 603.12, CR 122.1b, CR 613.1d |
| Ajani, Nacatl Avenger | **Fixed end to end, through a real activation (W4, converging with the CR 712 transform wave).** `_parse_reflexive_mandatory_token_clause` reads CR 603.12's "instruct" half (no `MAY` decision) for "Create a 2/1 ... token. When you do, ...", and the nested intervening *if* - "if you control a red permanent other than Ajani, he deals damage equal to the number of creatures you control to any target" - is checked once, immediately after the token exists (`_parse_if_control_colored_permanent_damage_clause`, reusing `count_expression`). Reaching the ability was the other half of the gap: `Game.activated_abilities` now reads `CardState.up_face_name`, so a transformed Ajani has this `0` and an untransformed one does not (CR 712.8d, CR 712.8e) - `test_reflexive_triggered_abilities.py`'s tests transform him for real and activate through the ordinary path, no hand-built `AbilityOnStack` any more | CR 603.4, CR 603.12, CR 712.8d, CR 712.8e |
| Kraul Harpooner | **Fixed end to end (W4); a false `LayerNotice` closed on top (W13).** "Undergrowth — When this creature enters, choose up to one target creature you don't control with flying. This creature gets +X/+0 until end of turn, where X is the number of creature cards in your graveyard, then you may have this creature fight that creature." is `_parse_undergrowth_pump_and_fight_clause`, read whole (the pump always applies; the fight only if a target was actually chosen, CR 115.6). Fight itself (CR 701.14) did not exist anywhere in the engine before this wave - see `_fight` in `machines/effects.py`. Getting here also needed a real fix in `machines/targeting.py`: "with `<keyword>`" (a trailing evasion-ability clause) was parsed as far as the controller restriction and then silently dropped, so "you don't control with flying" was enforcing "you don't control" only - `TargetRequirement.required_keyword`/`_extract_required_keyword` closes that for a small, explicit keyword vocabulary, without changing behaviour for any "with ..." clause outside it. **W13:** despite the trigger resolving correctly, `machines/layers.effects_for`'s battlefield sweep (called for every permanent every board computation, CR 613.5) used to record a spurious `LayerNotice` on this card - it read this triggered ability's own effect sentence ("This creature gets +X/+0 ... where X is the number of creature cards in your graveyard") as if it were an unreadable *static* pump, because `layer_readable_sentences` deliberately includes a triggered/activated ability's own body so a *different* caller (`create_continuous_effect_of_ability`, resolving the ability itself) can read a rowless pump like Oliphaunt's. `effects_for`'s own two calls now pass `static_only=True`, restricting the sweep to `StaticAbility` text alone; the ability-resolution call sites keep the unrestricted default | CR 701.14, CR 115.6, CR 702.9, CR 611.3 |
| Extinguisher Battleship | **Fixed end to end (W4).** "When this Spacecraft enters, destroy target noncreature permanent. Then this Spacecraft deals 4 damage to each creature." needed no new combined-clause parser - `_CLAUSE_SEPARATOR` already splits on a bare "then", so this is two ordinary clauses of one ability: the existing `_DESTROY_TARGET_RE` and a new `_DAMAGE_EACH_CREATURE_RE`/`damage_each_creature`, the "each creature" (not "each opponent") sibling of Guttersnipe's own reader. CR 608.2b: since the whole ability names exactly one target (the destroy clause's), that target dying in response fizzles the *entire* ability, mass damage included - not a per-clause fizzle | CR 608.2c, CR 701.8a, CR 119.3, CR 608.2b |
| Kozilek's Command | Tokens and scry both work; `EFFECTS` is keyed by card name, so there is no modal dispatch and no mode can be executed. The `{X}` value is recorded on the cast record but unread | CR 700.2a, CR 601.2b |
| Malevolent Rumble | **Registered in full.** The decision over the four revealed cards is a real `Game.may` / `CHOOSE_CARDS` question now (CR 608.2d); the unscripted default takes the first permanent card in library order | CR 111.1, CR 608.2c |
| Mishra's Bauble | **Fixed.** "Look at the top card of target player's library" is a no-op (CR 701.20e, purely informational) and "draw a card at the beginning of the next turn's upkeep" is a parsed delayed trigger - see "Delayed-trigger clauses" below | CR 603.7, CR 701.20e |
| Monstrous Rage | **Registered in full.** +2/+0 in sublayer 7c, and the Monster Role token created attached to the target, granting +1/+1 in 7c and trample in layer 6. CR 704.5m and CR 704.5z are both dispatched, and combat reads the granted trample off the computed board | CR 111.10k, CR 303.7, CR 704.5m, CR 704.5z |
| Mosswort Bridge | Hideaway; "play the exiled card without paying its mana cost" if total power 10 or greater | CR 702.75a |
| Ocelot Pride | **Registered in full, no `TRIGGER_EFFECTS` row.** The end-step Cat token is created, its intervening *if* ("if you gained life this turn") is judged for real, and the second sentence now runs too: *ascend* is `Player.has_citys_blessing`, a real per-player designation granted once and never lost by `ascend_state_based_actions` (CR 702.131b) when a player controls ten or more permanents; "for each token you control that entered this turn" reads `CardState.turn_entered`, stamped once in `Game.enter_the_battlefield`; the copy itself is `token_copy_of` (CR 707.2). Both sentences are read off the ability's own printed text - `_parse_token_clause` and the new `_parse_city_blessing_token_copy_clause` - so `trigger_effect_for`'s fallback covers the whole paragraph with no card-name row. Previously this card kept a row specifically so the first sentence could run unconditionally while the second silently never did; that is the half-execution the project's paragraph-based-ability ruling now forbids everywhere | CR 111.1, CR 702.131b, CR 702.131c, CR 603.4, CR 608.2c, CR 707.2 |
| Preordain | **Registered in full**: scry 2, then draw, in printed order (CR 608.2c), with the scry a real question (CR 608.2d). No `EFFECTS` row any more - `parse_player_effect_for_spell` reads it | CR 701.22a, CR 608.2c |
| Ragavan, Nimble Pilferer | **Whole paragraph runs.** `TriggerEvent.DEALS_DAMAGE` plus `GameEvent.combat`/`GameEvent.player` reads "whenever [this creature] deals combat damage to a player"/"to an opponent" generically off any card's own text (see "Events nothing emits" above) - Ragavan, Nashi, and Questing Beast all trigger through it with no per-card code. All three of Ragavan's clauses now resolve: "create a Treasure token" (`_parse_token_clause`'s predefined-token shape), "exile the top card of that player's library" (`ability.event.player`, CR 607.1's within-one-ability anaphora) and "Until end of turn, you may cast that card", which is read as one CR 608.2c instruction *with* the exiling clause it points back at by `_parse_exile_then_play_permission_pair` and grants a `machines/casting.PlayPermission` over exactly the card just exiled - see the play-from-exile row above. The permission goes to the Ragavan controller while CR 108.3 leaves the card owned by the damaged player, and it ends in the cleanup step (CR 514.2). No `UnmodeledTriggerEffectNotice` any more. **Dash's own delayed return is fixed** - `Game._create_resolution_delayed_triggers` now builds it the same way it builds warp's | CR 108.3, CR 111.10a, CR 120.2a, CR 514.2, CR 601.3, CR 607.1, CR 608.2c, CR 702.109a |
| Nashi, Searcher in the Dark | Triggers on combat damage to a player (see Ragavan above); "you may put any number of ... into your hand" has no `DecisionKind.CHOOSE_CARDS` shape for an unbounded choice (that kind only ever asks for an exact count), read generically by `_unreadable_unbounded_hand_choice_clause`, so the whole resolution is left with an `UnmodeledTriggerEffectNotice` rather than milling and then silently declining the choice | CR 120.2a |
| Questing Beast | Triggers on combat damage to an opponent (see Ragavan above); "target planeswalker **that player** controls" needs a target restricted by the trigger's own event rather than by the ability's static printed text, which `machines/targeting.profile_for_text` cannot express - read generically by `_unreadable_event_player_target_clause`'s "target X that player controls" shape - so it is left with an `UnmodeledTriggerEffectNotice` | CR 120.2a |
| Seasoned Pyromancer | **Its enters trigger is registered in full**, Elemental tokens included; which two cards are discarded is a real `CHOOSE_CARDS` question (CR 701.9b) through `Game.ask`, defaulting to the front of hand when unscripted. Its graveyard-activated ability still needs abilities that function from a graveyard | CR 111.1, CR 608.2c |
| Slickshot Show-Off | Its prowess-like trigger is a layer 7c pump per noncreature spell. Plot is modelled now (see the Modelled table), so the trigger is all that is missing | CR 613.4c, CR 116.2k |
| Slumbering Trudge | Stun counters; `X` read at resolution; "enters tapped if X is 2 or less" | CR 614.1c |
| Static Prison | **Both abilities are registered in full (W7b closes the second).** "At the beginning of your first main phase, sacrifice this enchantment unless you pay {E}" is `_parse_sacrifice_unless_pay_energy`, using `Game.may_pay_energy` the same fixed-amount question `may_pay_life` already asks for CR 119.4, turned the other way round: paying is what averts the sacrifice. Its ETB - "exile target nonland permanent an opponent controls until this enchantment leaves the battlefield. You get {E}{E}" - now runs whole: `_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE` is read *ahead* of the general `_EXILE_TARGET_RE` (whose own phrase would otherwise swallow the "until ..." tail and be refused by `_TRAILING_DURATION_RE`'s still-active blanket guard - every *other* trailing duration is still refused exactly as before), and the exile itself creates three sibling `DelayedTrigger`s (CR 610.2, CR 603.7) - one per departure route this engine can raise (`DIES` covers both destroy and sacrifice; `LEAVES_BATTLEFIELD_TO_EXILE`; and the newly-added `LEAVES_BATTLEFIELD_TO_HAND`, since `Game.return_to_hand` emitted nothing at all before this wave) - so the exiled card returns under its owner's control whenever Static Prison leaves the battlefield by any of them, and only once (`_dismiss_other_static_prison_triggers`). `tests/test_effects.py::test_static_prisons_enters_trigger_does_not_parse_as_a_whole` still correctly asserts `None` from `parse_player_effect` alone - that function only ever reads plain player clauses and was never going to read a target, whichever way the target clause parses - so it is not stale, only no longer the whole story; `trigger_effect_for`'s real dispatch (`parse_mixed_effect`, which tries the targeted reader first) is what changed. See `scenarios/test_exile_until_leaves_the_battlefield.py` | CR 107.14, CR 118.3, CR 406.2, CR 610.2, CR 603.7a/b/c |
| Surgical Extraction | Targeting a card in a graveyard *other than a basic land card* - `machines/targeting.py` has no "other than a basic land" exclusion - then searching three zones of the *owner* for cards with the same name. `Game.search_library`'s `zone` parameter (W1) can now run that search once wired to a real target and name | CR 701.23a, CR 701.13a |
| The Stone Brain | "Choose a card name" as a genuine mid-resolution instruction (not tied to an ETB the way `DecisionKind.CHOOSE_A_QUALITY` has been used so far, though its own docstring already documents the general reuse), feeding a capped ("up to four"), three-zone search of a targeted opponent (`Game.search_library`'s `zone` parameter, W1) and a replacement draw for each card exiled specifically from hand | CR 701.23a, CR 701.13a |
| Thraben Charm | Modal dispatch; "damage equal to twice the number of creatures you control" | CR 700.2a |
| Turntimber Symbiosis | **Fixed (W13).** `_parse_look_top_n_may_battlefield_creature_bonus_clause` (`machines/effects.py`) reads the whole clause: look at the top seven, a `CHOOSE_CARDS`/`MAY` decision for which creature (if any) goes onto the battlefield, the "mana value 3 or less" bonus counters, and the rest to the bottom of the library in a random order | CR 122.1, CR 614.1c, CR 107.1c |
| Voice of Victory | Mobilize; "your opponents can't cast spells during your turn" - a rules-modifying static ability | CR 702.181, CR 611.3 |
| Wrath of the Skies | **Registered in full.** "You get X {E}, then you may pay any amount of {E}" is the same `DecisionKind.PAY_ENERGY_AMOUNT` question Galvanic Discharge asks, with `X` read off `Game.cast_record(spell).x_value`; "Destroy each artifact, creature, and enchantment with mana value less than or equal to the amount of {E} paid this way" reads the amount paid as a mana-value ceiling over a snapshot of `game.battlefield`, rechecking each candidate's zone immediately before destroying it (`_parse_x_energy_pay_destroy_by_mana_value`) | CR 107.14, CR 118.3 |

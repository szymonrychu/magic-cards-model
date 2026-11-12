# trk not_working cards - implementation plan (2026-11-12)

Engine: `~/play-magic/magic-cards-model` @ `339a6b4c2` (main, clean). Research was read-only.
Logs: `~/play-magic/logs/`
- `survey.log` - `scripts/survey_cards.py` re-run on all 29 cards
- `clauses.log` - `support.classify_clauses` for each card
- `probe.log` - each sentence run through `parse_mixed_effect` / `parse_mixed_effect_for_spell`
- `scryfall-*.log`, `survey-proofs-*.log` - candidate proof printings, with their oracle text, Modern legality and status today
- `rulings.log` - Scryfall rulings (none are published yet: the set releases 2026-11-13)

## 0. Re-verification

- **All 29 are still not working, so none was dropped.** 24 are silent and 5 fail closed with a notice (Antagonist Incorporator, Dominion Infiltration, Dominion Saboteur, Hive Mind Coprocessor, Mirror Universe Intrusion). Salt Vampire hit a Scryfall 429 at first; the re-run shows it as a notice.
- **The Wrath of Khan has two failing chapters.** Chapter I is a notice and chapter II is silent; the status table names only chapter II.
- **No metagame card is among them.** `docs/card_coverage/000-metagame/status.md` lists no card, and none of the 29 names appears in `docs/card_coverage/metagame.json`. Batches are therefore ordered by how many cards they unlock.
- **The card texts are current.** The survey cache (`.survey-cache/cards/`, gitignored) was fetched today. Those Old Scientists' preview oracle has a literal newline inside its Saga reminder text; that line becomes two `UnparsedAbility` lines that nothing reads, so it is harmless.

## 1. Per-card findings

Difficulty scale: S = template or reader gap, M = new reader on existing machinery, H = new subsystem or state.

Paths below are relative to `src/magic_cards_model/machines/` unless they say `models/`.

| Card | Failing clause(s) | Root cause | Existing machinery to extend | Diff |
|---|---|---|---|---|
| Replicator | "{2},{T}: Create a tapped token that's a copy of target token you control." | `effects/tokens.py` `_CREATE_TOKEN_COPY_OF_TARGET_RE` has no "tapped" slot; the untapped form already parses (Esika's Chariot). | `token_copy_of(..., tapped=True)` (models/token.py); Kambal's `(?P<tapped>tapped )?` in `copy_effects._FOR_EACH_OF_THEM_COPY_RE` | S |
| Dominion Infiltration | "...create a token that's a copy of that creature, except it has changeling." | The `ep02_r3_token_counts._sequence` chain reads every step except this one. `tokens._read_token_copy_except` and `control_copy._read_copy_exception_list` take only layer-6 combat keywords, so changeling is refused (`delayed_notice_only`). | `replacement/parse.py` `_COPY_EXCEPTION_CDA_KEYWORDS` (Omni-Changeling's clone already reads "except it has changeling"); `layers/apply._changeling_effects` | S |
| Gwyndala, the Progeny | "{2}: Each Equipment token you control becomes a copy of target Equipment you control until end of turn." | `copy_effects._EACH_BECOMES_A_COPY_RE` and `_each_group_member` accept only a card type or "token", with no subtype qualifier. "Each token you control becomes a copy of target Equipment..." already parses. | `copy_effects._parse_each_becomes_a_copy_clause` (Mirrorweave, Mirrorform) | S |
| Mirror Universe Intrusion | "If this spell was kicked, instead for each creature target opponent controls, create a token that's a copy of that creature, except it has menace." (notice `anaphoric_notice_only`) | Three gaps: (a) `modal._instead_branch_effect` composes through `parse_mixed_effect_for_spell` and never reaches the SPELL_TEXT-only `control_copy._parse_for_each_creature_target_player_copy_clause`; (b) that reader hardcodes "target player"; (c) `targeting.kicked_instead_target_text` needs "<verb> target" in both halves, so casting would announce both targets. | Those three functions; `casting/casting.py` already consumes the kicked-instead targets | M |
| Dominion Saboteur | "...enter as a copy ..., except it isn't legendary. If you do, it enters with additional counters ... equal to the same number and kinds of counters the copied permanent has on it." | `replacement/parse._parse_copy_exception("it isn't legendary")` returns None, so the text lands in `copy_exception_unparsed`. `CopyException` (replacement/model.py) cannot remove a supertype. The counters sentence parses as an ENTERS_WITH that no counter reader reads. | `replacement/enters._try_enters_as_copy`; its clone path already adds `exception.enters_with_counters`; the "If you do" pairing (`_IF_YOU_DO`, Devouring Hellion); the token side's `not_legendary` | M (field on persisted model, so a schema bump) |
| Antagonist Incorporator, Hive Mind Coprocessor | 'Artifact creatures you control have "Whenever this creature deals combat damage to a player, you may pay {1} / 1 life. If you do, ..."' | `layers/quoted_grants.group_quoted_grant_of`'s qualifier loop accepts only colours and subtypes. The card-type word "artifact" fails, and `looks_like_unparsed_layer_effect` turns that into the notice. The trigger bodies already resolve (`life._parse_may_pay_life_if_you_do_clause`, the may-pay-mana rung). | Same loop: add `_TYPE_NOUNS` words (and "nontoken") to `required` | S |
| De-evolve | "Enchanted creature gets -4/-0, can't block, and is a Salamander." | `attached_restrictions.parse_attached_compound_grant` splits only on a single " and ". `_RESTRICTION_RE` takes only "gets P/T and can't ...", so the can't-block part would not be enforced either. | `_compound_half`, `layers/attached_grants._read_is_clause` (giving SetCreatureTypes); Dub and Call to Serve already read their three-part "gets, has, and is" list | S/M |
| I'm a Doctor, Not a . . . | "Until end of turn, it gets +1/+1 and becomes a Doctor." | This rewrites to "Target creature gets +1/+1 and becomes a Doctor until end of turn", which `parsed_layer_effects` refuses: no layer sentence combines a pump with a creature-type set. "becomes a Doctor" alone parses. | `layers/parse._BECOMES_CREATURE_TYPE_RE` (~2693) and its builder `_becomes_subtype_in_addition_builder(replaces=True)`; add an optional "gets +P/+T and " prefix. Check also: `_spell_effect_or_notice` returns a `create_continuous_effect` placeholder for this unreadable sentence, which may be a hidden silent. | S |
| Conquest Mission, Support Mission | "...put a quest counter on this enchantment. <base>. If this enchantment has N or more quest counters on it, <alt> instead / instead <alt>." | `modal._CONDITION_INSTEAD_RE`'s `base` group cannot hold a period, so the leading independent sentence stops the match. The last two sentences alone already parse through `_parse_condition_instead_clause_for_ability` (Conquest's "two of those tokens" is rewritten there). | A MIXED_CLAUSES rung that pairs sentence i with its if/instead sentence i+1 (model: `_parse_gated_pair_clauses`, `text._parse_leading_then_if_otherwise_clause`) | S/M |
| Jett Reno, Problem Solver | "Whenever Jett Reno becomes tapped, surveil 1. If her power is 4 or greater, instead draw a card." (not covered by the research agents; I probed it myself) | `abilities.legendary_self_pronoun_normalized` rewrites the possessive "her power" to "it power" (`_LEGENDARY_SELF_OBJECT_PRONOUN_RE` treats every "her" as an object). "If Jett Reno's power is 4 or greater, instead draw a card." already parses. | The same function: read a possessive his/her before a noun as "its"/"this permanent's" | S |
| Those Old Scientists | III: "Choose up to two target cards in graveyards. The owners of those cards shuffle them into their libraries." | `modal._CHOOSE_TARGET_OWNER_SHUFFLES_IT_RE` reads only the singular "Its owner shuffles it into their library" (Deglamer). `library._SHUFFLE_TARGET_CARDS_INTO_LIBRARY_RE` takes only "from your/a graveyard". The targets themselves are understood. | `modal._parse_choose_target_owner_shuffles_it_clause`; `library._shuffle_targets_into_owners_libraries` | S |
| Brazen Bluff | "Choose target noncreature spell an opponent controls. That player may exile it. If they don't, you may cast a noncreature spell from your hand without paying its mana cost." | Each half reads on its own (exile target spell; `library._parse_may_cast_from_hand_free_clause`). The joining "that player may X it; if they don't, Y" shape is missing. The B2 punisher (`modal._parse_opponent_may_have_you_else_clause`) is ability-only and needs "target opponent may have you". | A modal.py SPELL_TEXT/ABILITY_TEXT rung; the asker is the controller of the target, using the punisher's MAY / `_THEY_SUBJECT_RE` approach | M |
| Peace in Our Time | "At the beginning of combat on each player's turn, that player may draw a card. If they do, they can't attack this turn and you put a peace counter on this enchantment." | Three parts are unread: "that player may draw" (the plain "that player draws" reads); a player's "can't attack this turn"; and "you put a ... counter on this enchantment" (it reads without the leading "you"). The " and " also needs to stay inside the if-they-do consequence. | Cheering Crowd's per-card reader `ep02_r2_counter_amounts._parse_that_player_may_put_counter_then_add_mana`; `Game.creatures_cant_attack_until_turns_taken` (a blanket restriction, Orim's Chant), read in `combat.attack_refusal` | M (needs a per-player can't-attack-this-turn field, so a schema bump) |
| Hit It! | "Put a land card from among them onto the battlefield tapped and the rest into your graveyard." | `merges._merge_look_top_put_onto_battlefield_clauses` (~236) accepts only "put the rest on the bottom". | `merges._THE_OTHER_INTO_A_DESTINATION_RE` (already used by `_merge_look_top_split_hand_graveyard_clauses`) | S |
| Deep Space 9 | "Put all permanent cards exiled this way onto the battlefield." | `removal._EXILE_TOP_N_PUT_FROM_AMONG_RE` (~2548, Tezzeret/Xenagos) takes only "from among them". The compound "enters and at the beginning of your upkeep" trigger is already split by `triggers/collect._expand_enters_and_upkeep`. | Widen to `(?:from among them\|exiled this way)` plus "all" | S |
| Temporal Conqueror | "If you can't, create a Treasure token." | No general "if you can't" fallback reader exists; the only one is Borg Cube's (`returns._ASSIMILATE_EXILED_WITH_RE`). `library._MILL_THEN_RETURN_TO_HAND_RE` (~6035) also wants ", then", not ". Then". | `library._parse_mill_then_return_to_hand_clause`; fallback compiled with `_ability_effect_or_notice` | M |
| First Contact | "If this spell is the first spell you've cast this game, you gain 2 life." | "Mill four. You may put a permanent card from among them into your hand." already reads (`library._mill_then_may_take_from_milled_runner`, ~6209), but its tail allows only an unconditional life gain. `Game` tracks only spells cast this turn and last turn, nothing for the whole game. | A new per-player count of spells cast this game on `Game` (`models/game/__init__.py`, filled where `spells_cast_this_turn` is appended); a condition in `models/game/_conditions.py`; the runner tail through `modal._parse_condition_clause` | H (new game-history state, so a schema bump) |
| Andromedan Automatons | "you may search your library for any number of cards named Andromedan Automatons, reveal them, put them into your hand, then shuffle." | `search._YOU_SEARCH_NAMED_CARD_RE` (~1672, Tempest Hawk) reads only the singular "a card named X, reveal it, put it". | Add a count slot ("any number of" / "up to N") and the plural "reveal them, put them"; `game.search_and_put` count | S/M |
| Captain Jean-Luc Picard | "Search your library for a Spacecraft card, put it onto the battlefield with seven charge counters on it, then shuffle." The cost "Tap seven untapped Officers" already reads. | `effects/_common._SEARCH_AND_PUT_RE` (~337) has no counters tail. `Game.search_and_put` (models/game/_zones ~1718) takes no counters argument. | The counters tail of `dispatch._RETURN_FROM_YOUR_GRAVEYARD_TO_BATTLEFIELD_WITH_COUNTER_RE`; `put_onto_battlefield(counters=...)`; `search._search_and_place_for` (~297) | M |
| The Inner Light | II: "Choose target creature. Whenever it deals combat damage to a player this turn, you draw that many cards." | `delayed._THAT_OBJECT_TURN_TRIGGER_RE` accepts only "whenever that <noun>", not "whenever it". The ability rung `text._parse_that_object_turn_trigger_ability_text` does not strip a leading "Choose target X.". Side issue: on the spell side, "it" currently falls through to `tokens._parse_created_trigger_spell_text`, which looks like a misread. | `delayed.ChosenObjectTriggeredAbility`, `create_chosen_object_turn_trigger` ("that many" via `_THAT_MUCH_RE`; Hunter's Insight); `ep02_r2_devotion_domain_party.CHOOSE_TARGET_RE` | S |
| Will Riker, First in the Field | "Sacrifice those lands at the beginning of your next end step." The reveal-until-two-lands part already reads (`merges._merge_reveal_until_n_kind_put_onto_battlefield_clauses`, Skyserpent Seeker). | `delayed.parse_anaphoric_delayed_clause`: "those lands" is not in `_ANAPHOR_AGREEMENT`/`_PLURAL_ANAPHORS`, which accept only them / those tokens / those creatures. | Generalise to "those <type>s"; extend the merge to take a fourth clause, then `triggers_for_all` + `game.create_delayed_trigger` (as in `tokens.py` ~1999) | M |
| The Wrath of Khan | I (notice): "At the beginning of the next combat this turn, gain control of that creature until end of turn. Untap it. It gains haste until end of turn." II (silent): "You may exile a card from your hand. If you do, draw a card." | I: `delayed.ANAPHORIC_TIMING_STEPS` has no next-combat timing, `_ANAPHORIC_VERBS` has no gain-control verb, and the delayed body is three sentences. II: nothing reads "exile a card from your hand" as a player clause in a mixed or may-if-you-do chain; `removal._parse_exile_cards_from_your_hand_clause` is ABILITY_TEXT-only. | I: a new `DelayedEffectSpec` kind holding the body text plus the subject id and stamp, resolved like `ChosenObjectTriggeredAbility`; Threaten's body reader `continuous._parse_untap_and_gain_control_ability`; existing `Step.BEGINNING_OF_COMBAT` delayed triggers. II: copy `merges._merge_may_exile_from_graveyard_if_you_do_clauses` for the hand (empty hand gives no question and no draw) | I: M (new union kind, so a schema bump); II: S |
| All Good Things... | I-III: "Draw two cards, then exile a card from your hand." IV: "If all cards exiled with this Saga share a card type, you gain 10 life." | I-III: the same missing player-clause exile-from-hand reader as Wrath II. The link to the Saga already exists (`removal.link_cards_exiled_during`, `_LINKED_EXILE_READER_RE`). IV: no "all cards exiled with X share a card type" condition exists, and `conditions/objects._SELF_NOUN` lacks "saga". | `conditions/objects._cards_exiled_with`, `_exiled_with`, `_shares_a_card_type_with_exiled` | M |
| The Measure of a Man | III: "Return the exiled card to the battlefield under its owner's control." | The reader exists: Champion's `legacy_keywords.champion_returns` reads `cards_exiled_with(source)`. Its wrapper `removal._parse_champion_clause` is ABILITY_TEXT-only, so it fails once "You gain 2 life." follows. The single-sentence version works (The Princess Takes Flight is handled). | Add a MIXED_CLAUSE rung in `effects/returns.py` reusing that body (optionally move the body to `linked_exile.py`) | S |
| Salt Vampire | "look at target opponent's hand. You may choose a nonland card from it. If you do, that player exiles that card, then draws a card." | `anaphoric_notice_only` on "You may choose a nonland card from it". `merges._merge_reveal_hand_choose_discard_clauses` (~3481; Thoughtseize, Thought-Knot Seer) is too narrow: it lacks the "look at" opener, an optional "may", "if you do", the "that player exiles that card" subject and the "then draws" tail. | That merge; `hand_reveal_exile._HAND_EXILE_UNTIL_LEAVES_RE` already reads both "look at" and "reveals" | M |
| Dal R'El, Augment Orphan | "Landfall - Whenever a land you control enters, add {R} or {G}." | `abilities._parse_add_mana_sentence` accepts only literal symbols, and `TriggeredManaShape` has no one-of-colours choice. Lotus Cobra's "one mana of any color" already reads. | `effects/mana._parse_mana_adding_trigger`, `modal._choose_mana_color`; `amount_sentences._ADD_MANA_FOR_EACH_RE` already reads "{R} or {G}" behind a "for each" | S (confirm `TriggeredManaShape` is never persisted) |
| Dathon, His Heart Open | "{2}: Choose a counter on target enchantment you control. Put another counter of that kind on it." | No reader for choosing one counter and adding one more of the same kind. | Readers that act on every kind of counter: `ep02_r2_counter_amounts._parse_kind_put_or_remove` (`kinds_on`, `_ask_option`), `counter_effects._EACH_KIND_ANOTHER_COUNTER_RE`; the CHOOSE_A_MODE prompt for a counter kind | M |

## 2. PR batches

There are 8 batches, each meant to run in its own `~/play-magic/<n>/` clone pair. No metagame card is involved, so they are ordered by cards unlocked. All of them can start at once.

The Wrath of Khan is split across two batches: chapter I is in B6 and chapter II in B5. The card counts as unlocked when the later of the two merges; neither batch counts it on its own.

### B1 `feat/conditional-instead-and-player-choices` - 6 cards - medium
- **Cards:** Conquest Mission, Support Mission, Jett Reno, Those Old Scientists, Brazen Bluff, Peace in Our Time.
- **Clauses:**
  - leading sentence + "If ~ has N or more <kind> counters on it, ... instead"
  - possessive legend pronoun in a condition
  - plural "owners of those cards shuffle them"
  - "That player may <verb> it. If they don't, <else>"
  - "that player may draw. If they do, they can't attack this turn and you put a counter"
- **Modules:** `effects/modal.py` (main), `abilities.py` (only `legendary_self_pronoun_normalized`), `models/game/__init__.py` (per-player can't-attack field; schema bump), `combat.py` (`attack_refusal`), possibly `player_action_prohibitions.py`.
- **Second printings (Scryfall-verified, Modern legal):**
  - Instead after a leading sentence: none exists (Scryfall finds no non-trk "if ~ has N or more ... counters on it, instead"). The two Missions differ from each other (a token count vs a +1/+1 count, and the position of "instead"), so use both.
  - Possessive pronoun: Viv Vision, Teen Synthezoid ("draw a card if her power is 4 or greater"). It is already handled, so it serves as a regression proof only.
  - Plural graveyard shuffle: **Turn the Earth** (mid; "Choose up to three target cards in graveyards. The owners of those cards shuffle them into their libraries. You gain 2 life."). Silent today.
  - "may <verb> it. If they don't": none exists.
  - "that player may draw; if they do, can't attack": none exists. Cheering Crowd (in the pool) has the nearest "that player may" shape.

### B2 `feat/copy-variants` - 5 cards - medium
- **Cards:** Replicator, Dominion Infiltration, Gwyndala, Mirror Universe Intrusion, Dominion Saboteur.
- **Clauses:**
  - "create a tapped token that's a copy of target ..."
  - token copy "except it has changeling"
  - "Each <subtype> token you control becomes a copy of target ..."
  - kicked "instead for each creature target opponent controls, create a copy"
  - clone "except it isn't legendary" + "additional counters equal to ... the copied permanent has"
- **Modules:** `effects/tokens.py`, `effects/control_copy.py`, `copy_effects.py`, `targeting.py`, `effects/modal.py` (only `_instead_branch_effect`), `replacement/{parse,model,enters}.py` + layer-1 copiable values (schema bump for the `CopyException` field).
- **Second printings:**
  - Kicked-instead copy: **Rite of Replication** (soc; "Create a token that's a copy of target creature. If this spell was kicked, create five of those tokens instead."). Silent today. Also widen the spell-side "those tokens" alternative.
  - Clone that isn't legendary: **Spark Double** (rvr; "... enter as a copy of a creature or planeswalker you control, except it enters with an additional +1/+1 counter ... and it isn't legendary."). Notice today.
  - Group becomes a copy: **Masterful Replication** (moc; "Choose target artifact you control. Each other artifact you control becomes a copy of that artifact until end of turn."; notice today), or Echoing Equation (silent). Mirrorweave is already handled.
  - Tapped token copy: none exists (Scryfall finds no non-trk "create a tapped token that's a copy of target"). Esika's Chariot and Kambal are handled regression proofs.
  - Changeling token copy: none exists for a token. Omni-Changeling (clone) and Twinflame (for-each frame) are handled.
  - Copying the copied permanent's counters: none exists.

### B3 `feat/library-onto-battlefield-fallbacks` - 4 cards - medium/hard
- **Cards:** Hit It!, Deep Space 9, Temporal Conqueror, First Contact.
- **Clauses:**
  - "put a land card from among them onto the battlefield tapped and the rest into your graveyard"
  - "Put all permanent cards exiled this way onto the battlefield"
  - "If you can't, <fallback>"
  - "If this spell is the first spell you've cast this game, ..." (new per-game spell history)
- **Modules:** `effects/merges.py` (look-top region only), `effects/removal.py` (`_EXILE_TOP_N_PUT_FROM_AMONG_RE` only), `effects/library.py`, `models/game/__init__.py` (spells cast this game; schema bump), `models/game/_conditions.py`, `effects/modal.py` (calls `_parse_condition_clause` only).
- **Second printings:**
  - Land onto battlefield tapped, rest to graveyard: **Shigeki, Jukai Visionary** (tdc; "Reveal the top four cards ... You may put a land card from among them onto the battlefield tapped. Put the rest into your graveyard."). Silent today.
  - If-you-can't fallback: **Patient Naturalist** (otj; "mill three cards. Put a land card from among the milled cards into your hand. If you can't, create a Treasure token."). Silent today.
  - Exiled-this-way onto battlefield: none exists. Living End and Anzrag's Rampage have a different shape.
  - First spell this game: none exists (Scryfall finds 0 for "cast this game").

### B4 `feat/layer-static-grants` - 4 cards - simple
- **Cards:** Antagonist Incorporator, Hive Mind Coprocessor, De-evolve, I'm a Doctor, Not a . . .
- **Clauses:**
  - card-type- or nontoken-qualified group quoted grant
  - three-part Aura list "gets, can't block, and is a <type>"
  - "gets +P/+T and becomes a <type>" (loses other types)
- **Modules:** `layers/quoted_grants.py`, `attached_restrictions.py`, `layers/parse.py`.
- **Second printings:**
  - Qualified quoted grant: **Ghired, Mirror of the Wilds** (otj; 'Nontoken creatures you control have "{T}: Create a token that's a copy of target token you control that entered this turn."'). Notice today.
  - Pump plus type change: **Nameless Inversion** (ecl; "Target creature gets +3/-3 and loses all creature types until end of turn."). Notice today.
  - Aura with a can't-block list: none exists. Dub and Call to Serve (gets/has/is) are handled regression proofs.

### B5 `feat/hand-exile-and-linked-returns` - 3 cards (+ Wrath of Khan II) - medium
- **Cards:** All Good Things..., Salt Vampire, The Measure of a Man; The Wrath of Khan chapter II.
- **Clauses:**
  - "exile a card from your hand" as a player clause, after "then" and in may/if-you-do
  - "If all cards exiled with this Saga share a card type"
  - "look at target opponent's hand. You may choose ... If you do, that player exiles that card, then draws"
  - "Return the exiled card ..." followed by another sentence
- **Modules:** `effects/removal.py` (exile-from-hand rung only), `effects/merges.py` (reveal-hand merge + may-exile-hand merge), `conditions/objects.py`, `effects/returns.py` (+ optionally `linked_exile.py`, `legacy_keywords.py`).
- **Second printings:**
  - Look at hand, choose, move, draw: **Vendilion Clique** (a25; "look at target player's hand. You may choose a nonland card from it. If you do, that player reveals the chosen card, puts it on the bottom of their library, then draws a card."). Notice today. Also **Specter's Shriek** (eld; "...If you do, that player exiles that card. ..."), notice today.
  - Saga returns the exiled card: The Princess Takes Flight (woe). It is handled as a single sentence, so it is a regression proof only.
  - Draw then exile from hand: Azor's Gateway and Bane Alley Broker have their own readers, so they are regression only.
  - "may exile a card from your hand. If you do, draw": none exists.
  - Exiled cards share a card type: none exists.

### B6 `feat/turn-scoped-delayed-triggers` - 2 cards (+ Wrath of Khan I) - medium
- **Cards:** The Inner Light, Will Riker; The Wrath of Khan chapter I.
- **Clauses:**
  - "Choose target creature. Whenever it deals combat damage to a player this turn, ... that many"
  - "Sacrifice those lands at the beginning of your next end step"
  - "At the beginning of the next combat this turn, gain control of that creature until end of turn. Untap it. It gains haste ..."
- **Modules:** `delayed.py` (main; a new `DelayedEffectSpec` kind, so a schema bump), `effects/text.py`, `effects/merges.py` (reveal-until merge only), `effects/continuous.py` (reuse only).
- **Second printings:**
  - This-turn combat-damage trigger: **Fire Giant's Fury** (khm; "Whenever it deals combat damage to a player this turn, exile that many cards ..."). Silent today.
  - Delayed sacrifice of "those lands": none exists. Skyserpent Seeker covers the reveal half and is handled.
  - Next-combat delayed gain control: none exists.

### B7 `feat/search-variants` - 2 cards - medium
- **Cards:** Andromedan Automatons, Captain Jean-Luc Picard.
- **Clauses:**
  - "search for any number of / up to N cards named X, reveal them, put them"
  - "search ..., put it onto the battlefield with N <kind> counters on it"
- **Modules:** `effects/search.py`, `effects/_common.py` (`_SEARCH_AND_PUT_RE`), `models/game/_zones.py` (`search_and_put` counters).
- **Second printings:**
  - Named cards: **Battalion Foot Soldier** (m20; "any number of cards named ..."), silent today, and **Squadron Hawk** (a25; "up to three cards named Squadron Hawk"), silent today.
  - Search with counters: none exists as a clean case. Neoform ("put that card onto the battlefield with an additional +1/+1 counter on it") is handled by its own reader; fold it onto the generic tail as the differently worded proof.

### B8 `feat/mana-choice-and-counter-kind` - 2 cards - simple/medium
- **Cards:** Dal R'El, Dathon.
- **Clauses:**
  - triggered "add {X} or {Y}"
  - "Choose a counter on target <noun>. Put another counter of that kind on it."
- **Modules:** `abilities.py` (add-mana sentence / `TriggeredManaShape` only), `effects/mana.py`, `effects/counters.py`.
- **Second printings:**
  - Triggered one-of-colours mana: **Kessig Naturalist** (mid; "Whenever this creature attacks, add {R} or {G}."). Silent today.
  - Chosen counter kind: **Ichormoon Gauntlet** (one; "choose a counter on target permanent. Put an additional counter of that kind on that permanent."), silent today. Also Animation Module (kld; "Give that permanent or player another counter of that kind"), silent today.

**Totals:** 6+5+4+4+3+2+2+2 = 28 cards, plus The Wrath of Khan split across B5 and B6, which makes 29.

## 3. Parallel-run hazards

- **Schema version.** B1 (Peace), B2 (`CopyException`), B3 (spells-this-game) and B6 (`DelayedEffectSpec` kind) each bump `Game.CURRENT_SCHEMA_VERSION`. This is a guaranteed rebase conflict. Each later merger takes the next number when it rebases; never reuse one.
- **Shared big modules, different regions:**
  - `effects/merges.py`: B3 look-top, B5 reveal-hand and may-exile-hand, B6 reveal-until.
  - `effects/modal.py`: B1 main; B2 `_instead_branch_effect`; B3 a call only.
  - `effects/removal.py`: B3 regex; B5 rung.
  - `abilities.py`: B1 pronoun; B8 mana.
  - `models/game/__init__.py`: B1 and B3, new fields.
- **Append-only shared files** conflict trivially: `tests/test_dispatch_order.py` edges, goldens (`mise run golden:update` after rebase), `MEMORY.md`, `docs/engine-coverage.md`, `docs/card_coverage/297-trk/status.md`, the coverage baseline. Regenerate generated files after the rebase rather than hand-merging them.
- **Same-family rungs.** B1's new instead-pair rung and B2's widened `_instead_branch_effect` both touch the if/instead path. Merge B1 first, or have B2 rebase onto it and re-run `test_dispatch_order`.
- **Rule lookups.** Every CR number written in code, tests or MEMORY must be looked up in-session (`rules:find`, `knowledge_search`). This plan states none.

## 4. Open questions (not settled by code, CR or the decisions file)

1. **All Good Things IV.** "If all cards exiled with this Saga share a card type": what happens when fewer than two cards were exiled (empty hand on some chapters)? There are no rulings yet (pre-release), and the CR has no "share a card type" definition; only 201.2's name analogues exist. **Recommended:**
   - zero cards exiled means no life (fail-safe, not vacuous truth);
   - one card means true;
   - two or more means true when their card-type sets intersect.
   - Record the choice in MEMORY and revisit when rulings publish.
2. **Mechanics with no non-trk Modern printing.** Proof follows the B3/B4 precedent in MEMORY: prove inside trk, vary the board, and record the Scryfall check in MEMORY. This is already settled by precedent, so it is not asked; listed only for visibility.

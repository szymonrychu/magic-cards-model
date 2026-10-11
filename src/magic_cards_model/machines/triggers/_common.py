import re

from ...numbers import COUNT

#: Basking Broodscale's and Emperor of Bones' condition: "one or more +1/+1
#: counters are put on this creature" (CR 122.6). The kind is captured so a
#: condition naming +1/+1 is not fired by a charge counter.
_COUNTERS_PUT_CONDITION = re.compile(
    r"^one or more (?:(?P<kind>\S+) )?counters are put on (?P<subject>.+)$"
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

#: Party Dude's own level-3 ability: "Whenever one or more of your opponents
#: are attacked, ..." - "attacked" (no "s", past participle) never matches
#: `machines/abilities._trigger_event`'s own `\battacks?\b` word-boundary
#: read (the "k" and the "ed" that follows share no boundary), so this
#: reaches `condition_matches` with `ability.event` still `None` - the same
#: `_unread_trigger_events`/`_unread_condition_matches` fallback pair every
#: other condition in this section goes through, watching the identical
#: `TriggerEvent.ATTACKS` event "you attack" above already fires once per
#: declaration (CR 603.2c), never once per attacker. CR 506.4: a planeswalker
#: or a battle can itself "be attacked", so "your opponents are attacked" is
#: read the same defending-player normalisation `_attacks_you_holds` already
#: gives "attacks you or a planeswalker you control" - an opponent is
#: attacked whether the declared defender is that opponent directly or a
#: planeswalker/battle they control.
_OPPONENTS_ARE_ATTACKED_CONDITION = re.compile(
    r"^one or more of your opponents (?:are|is) attacked$"
)

#: The Great Goblin's own "Whenever you put one or more counters on a
#: Goblin, Orc, or Army you control, ..." - `_LOYALTY_COUNTERS_PUT_ON_
#: PLANESWALKER_CONDITION`'s own active-voice shape widened from one fixed
#: subject ("a planeswalker") to any subtype or subtype list a "target
#: `<description>`" phrase's own grammar could name, read by `_parse_subtype_
#: list` the identical way `_DYING_SUBTYPE`'s own widened subject is.
#: Matched against `ability.condition` **unlowercased** (unlike every other
#: condition in this family, matched against a `.lower()`'d copy) because
#: `_parse_subtype_list` needs Oracle's own subtype capitalisation to tell a
#: subtype from a card-type word - the reason `_DYING_SUBTYPE`/`_ENTERING_
#: SUBTYPE` are both matched the same unlowered way from `condition_matches`
#: itself, just above this module's `ability.event is None` fallback.
_COUNTERS_PUT_ON_DESCRIPTION_CONDITION = re.compile(
    r"^you put one or more counters on an? "
    r"(?P<subtypes>[A-Z][A-Za-z]*(?:,\s*[A-Z][A-Za-z]*)*(?:,?\s+or\s+[A-Z][A-Za-z]*)?)"
    r" you control$"
)

#: "Whenever you put a counter on a creature you control, ..." (Mikey & Leo,
#: Chaos & Order) / "Whenever you put a +1/+1 counter on a creature, ..."
#: (Ant-Man, Colony Commander, verified Modern/Pioneer/Standard legal) - CR
#: 122.6's active voice, singular ("a counter", not "one or more"), on any
#: object matching a plain quality (`models.game._permanent_quality`) rather
#: than `_COUNTERS_PUT_ON_DESCRIPTION_CONDITION`'s own capitalised subtype
#: list just above. "you control" is optional: Ant-Man's own bare "a
#: creature" names any creature at all, not only the controller's own, so it
#: is read the same loose "you put" convention `_LOYALTY_COUNTERS_PUT_ON_
#: PLANESWALKER_CONDITION` above already uses for the identical active-voice
#: shape - "you put" is read off *whose* permanent the counter landed on
#: (`event.subject_controller`) when the clause names one, never off a
#: separate "who actually moved it" record this engine does not keep for a
#: plain counter placement. The kind group's negative lookahead keeps it from
#: swallowing the literal word "counter(s)" itself when the printed text
#: carries no kind at all ("a counter", not "a +1/+1 counter").
_YOU_PUT_A_COUNTER_ON_QUALITY_CONDITION = re.compile(
    r"^you put an? (?:(?!counters?\b)(?P<kind>[a-z0-9+/-]+) )?counters? on "
    r"(?P<article>another|an?) (?P<quality>[a-z][a-z -]*?)(?P<yours> you control)?$"
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

#: Tamiyo, Inquisitive Student's "you draw your third card in a turn",
#: Faerie Vandal's "you draw your second card each turn", and Gleaming
#: Splendor's own "an opponent draws their second card each turn" - an
#: ordinal over CR 121.2's individual card draws, which are one event each.
#: Both trailing suffixes mean the same turn-scoped count; "each turn" is how
#: most printings say it. "You"/"your" is the ability's own controller;
#: "an opponent"/"their" is any player who is not.
#: King T'Challa's "a player draws their second card each turn" is the
#: third subject: any player at all, the ability's controller included.
_NTH_DRAW_CONDITION = re.compile(
    r"^(?P<who>you|an opponent|a player) draws? (?:your|their) (?P<ordinal>[a-z]+) card"
    r" (?:in a|each) turn$"
)

#: "one or more `<description>` become tapped" - Rewrite History's
#: "creatures you control", Deeproot Pilgrimage's "nontoken Merfolk you
#: control". The plural verb is the batch (CR 603.2c).
_ONE_OR_MORE_BECOME_TAPPED_CONDITION = re.compile(
    r"^one or more (?P<description>.+?) become tapped$", re.IGNORECASE
)

#: "one or more `<type>` cards are put into your graveyard from anywhere[
#: during your turn]" (Robot Domination; Crawling Infestation) and the
#: narrower origin "from your library" (CR 400.6). A card, so never a token
#: (CR 108.2). The plural "into graveyards" (Dennick, Pious Apparition) is
#: any player's graveyard, not only the controller's.
_ONE_OR_MORE_CARDS_INTO_YOUR_GRAVEYARD_CONDITION = re.compile(
    r"^one or more (?P<types>[a-z]+(?: or [a-z]+)*) cards are put into "
    r"(?P<whose>your graveyard|graveyards)"
    r" from (?P<origin>anywhere|your library)(?P<your_turn> during your turn)?$"
)

#: The Plans' "the fourth plan counter is put on this enchantment" (Claim the
#: Kingdom, Political Triumph; Robot Domination's "third", Doom Reigns
#: Supreme's "fifth", Construct a Cosmic Cube's "seventh") - CR 122.6's
#: counters being put on an object, read as a threshold: the one event that
#: takes this object's count of that kind from below N to N or more, the
#: reading CR 714.2b spells out for a Saga's lore counters. Self-referential
#: only, which is how every printing names its object.
_NTH_COUNTER_PUT_CONDITION = re.compile(
    r"^the (?P<ordinal>[a-z]+) (?P<kind>\S+) counter is put on (?:this [a-z]+|it)$"
)

#: CR 702.62a's third ability, as `machines/keywords._suspend_abilities`
#: writes it out: "the last time counter is removed from this card". Never
#: printed as a line of condition text on any card - suspend prints it as one
#: word, and the only text on Lotus Bloom that resembles it is reminder text.
#: CR 702.63a's own third ability writes the identical condition over "this
#: permanent" instead of "this card" (`machines/keywords._vanishing_abilities`)
#: - the same fact asked about a battlefield permanent rather than an exiled
#: card - so this accepts both nouns rather than becoming two near-duplicate
#: patterns.
_LAST_TIME_COUNTER_CONDITION = re.compile(
    r"^the last time counter is removed from this (?:card|permanent)$"
)

#: "When the last `<kind>` counter is removed from this permanent" for every
#: kind but time (read above) - CR 310.12b's Siege defeat trigger, "When the
#: last defense counter is removed from this permanent".
_LAST_COUNTER_CONDITION = re.compile(
    r"^the last (?P<kind>(?!time )[a-z0-9+/-]+) counter is removed from this permanent$"
)

#: CR 702.94a's second ability, as `machines/keywords._miracle_ability` writes
#: it out: "you reveal this card this way". Miracle prints it as one word, so
#: this condition only ever arrives from that expansion.
_REVEALED_THIS_WAY_CONDITION = re.compile(r"^you reveal this card this way$")

#: God-Eternal Kefnet's linked trigger: "Whenever you reveal an instant or
#: sorcery card this way" - the card a player revealed through the static
#: "You may reveal the first card you draw each turn as you draw it" (the same
#: CR 607.2h link miracle has), never any other reveal.
_REVEALED_FIRST_DRAW_CONDITION = re.compile(r"^you reveal an instant or sorcery card this way$")

#: Voltaic Visionary's "When you play a card exiled with this creature" - CR
#: 601.1a's "play" (a land played or a spell cast) of a card out of this
#: object's own CR 607.2a pile.
_PLAY_A_CARD_EXILED_WITH_CONDITION = re.compile(r"^you play a card exiled with this \w+$")

#: The Master of Lake-town's own "Whenever a player loses life" (CR 119.3's
#: own life-loss event, `Game.deal_damage_to_player`/`.exchange_life_totals`)
#: - "a player" is anyone, "you"/"an opponent" the narrower forms other
#: printings of the same shape could use (`GAINS_LIFE`'s identical split).
_LOSES_LIFE_CONDITION = re.compile(r"^(?P<who>you|an opponent|a player) loses? life$")

#: CR 601.1a's "play" spelled out as its two halves: "you play a land or
#: cast a spell [from anywhere other than your hand]" (Shadow of the Goblin) -
#: a land played (CR 116.2a) or a spell cast (CR 601.2), by the named player,
#: from the named origin if there is one.
_PLAY_A_LAND_OR_CAST_CONDITION = re.compile(
    r"^(?P<who>you|an opponent|a player) plays? a land or casts? a spell(?P<origin> from .+)?$"
)

#: The Millennium Calendar's "you untap one or more permanents during your
#: untap step" - `ExtraTriggerEvent.UNTAPPED_DURING_UNTAP_STEP`.
_UNTAPPED_DURING_UNTAP_STEP_CONDITION = re.compile(
    r"^you untap one or more permanents during your untap step$"
)


#: CR 716.2a: "[Cost]: Level N - [Abilities]" means "[Cost]: This Class's
#: level becomes N ..." - Caretaker's Talent's, Stormchaser's Talent's and
#: Wizard Class's "When this Class becomes level 2". Self-referential: the
#: level is the Class's own (CR 716.2b).
_CLASS_BECOMES_LEVEL_CONDITION = re.compile(r"^(?P<subject>.+?) becomes level (?P<level>\d+)$")
#: CR 701.54d: "Whenever the Ring tempts you" / "When the Ring tempts you".
_RING_TEMPTS_YOU_CONDITION = re.compile(r"^the ring tempts you$", re.IGNORECASE)
#: CR 702.154b's own linked condition, self-referential only in the pool -
#: Guardian of New Benalia's "this creature enlists a creature".
_ENLISTS_A_CREATURE_CONDITION = re.compile(r"^(?:this creature|it) enlists? a creature$")


#: CR 700.13: "you commit a crime" - Magda, the Hoardmaster's and Forsaken
#: Miner's identical condition, always "you" (CR 700.13 is a self-designation
#: - a player commits a crime, never "an opponent commits a crime").
_CRIME_COMMITTED_CONDITION = re.compile(r"^you(?:'ve| have)? commits? a crime$", re.IGNORECASE)
#: CR 701.23a: "an opponent searches their library" - Wan Shi Tong,
#: Librarian's and Ob Nixilis, Unshackled's identical condition. "You search
#: your library" is the same event from the controller's own side, kept for
#: generality even though nothing in the pool prints it yet.
_SEARCHES_LIBRARY_CONDITION = re.compile(
    r"^(?P<who>you|an opponent|a player) search(?:es)? (?:your|their) library$", re.IGNORECASE
)
#: CR 706.2: "you roll one or more dice" (Barbarian Class's level 2).
_ROLLS_DICE_CONDITION = re.compile(
    r"^(?P<who>you|an opponent|a player) rolls? one or more dice$", re.IGNORECASE
)
#: CR 603.6c: "an ability that triggers when a card is put into a certain
#: zone 'from anywhere' is never treated as a leaves-the-battlefield
#: ability" - so, unlike `DIES`'s battlefield-only CR 700.4 move, this is not
#: one of CR 603.10a's own enumerated look-back exceptions either; CR
#: 603.10's own intro answers it instead ("objects that exist immediately
#: after an event are checked" by default), which is exactly the graveyard
#: card as it now sits. Emrakul, the Aeons Torn's and Purity's identical
#: condition, self-referential to the ability's own source, from *any*
#: origin zone.
_SELF_PUT_INTO_GRAVEYARD_FROM_ANYWHERE_CONDITION = re.compile(
    r"^(?P<subject>.+?) is put into a graveyard from anywhere$", re.IGNORECASE
)
#: CR 709.5h/709.5j: "you unlock this door" - Ritual Chamber's and Central
#: Elevator // Promising Stairs' identical condition, self-referential to
#: the ability's own printed face (`BaseAbility.face`), never to the
#: permanent's other door.
_DOOR_UNLOCKED_CONDITION = re.compile(r"^you unlock this door$", re.IGNORECASE)
_SOLVE_A_CASE_CONDITION = re.compile(r"^you solve a case$", re.IGNORECASE)

#: CR 702.29c's "When you cycle this card" (Vizier of Tumbling Sands,
#: Windcaller Aven, Choking Tethers), and the non-self "you cycle a card" /
#: "another card" forms of the same verb. CR 702.29d's "cycles or discards"
#: is a different, discard-shaped condition `machines/abilities.
#: _trigger_event` already files under `TriggerEvent.DISCARDS_A_CARD`.
_CYCLE_CONDITION = re.compile(
    r"^(?P<who>you|a player|an opponent) cycles? (?P<what>this card|another card|a card)$"
)

#: CR 602.2's activation, restricted by CR 605.1a's mana-ability test:
#: "`<who>` activates an ability [of `<type list>`] that isn't a mana
#: ability" - Flamescroll Celebrant's "an opponent", Burning-Tree Shaman's
#: "a player", Immolation Shaman's "of an artifact, creature, or land", and
#: Harsh Mentor's "... or land on the battlefield" (CR 109.2's "a type named
#: without 'card', 'spell' or 'source'" already means one on the
#: battlefield, which the branch reading it checks either way).
_ABILITY_ACTIVATED_CONDITION = re.compile(
    r"^(?P<who>you|a player|an opponent) activates? an ability"
    r"(?: of (?P<types>an? [a-z]+(?:(?:,\s*(?:or\s+)?|\s+or\s+)(?:an? )?[a-z]+)*)"
    r"(?: on the battlefield)?)?"
    r"(?P<not_mana> that isn't a mana ability)?$"
)


_ONE_OR_MORE_ATTACK_YOURS = re.compile(r"\byou control\b", re.IGNORECASE)


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


#: The gate half of `_ADDITIONAL_TRIGGER_RE`: "an artifact or creature
#: entering" (Panharmonicon), "a permanent entering the battlefield" (Elesh
#: Norn, Mother of Machines; Starfield Vocalist - WOTC's 2024 "enters" and the
#: older "enters the battlefield" both print), "a land entering" (Ancient
#: Greenwarden), "a Wizard you control entering" (Naban, Dean of Iteration).
#: Each alternative is a card type, "permanent" (any of them), or a subtype;
#: "you control" narrows the entering permanent to the multiplier's own
#: controller's.
_ENTERING_CAUSE_RE = re.compile(
    r"^an? (?P<types>[a-z][a-z ]*?)(?P<yours> you control)? entering(?: the battlefield)?$",
    re.IGNORECASE,
)


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

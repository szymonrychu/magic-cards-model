# Modern Horizons 3 (mh3)

- Expansion: 250
- Set code: `mh3`
- Release date: 2024-06-14
- Cards in scope (Modern/Pioneer/Standard-legal): 256

## Legality

| Format | Legal cards |
|---|---|
| Modern | 256 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 52 | 20.3% |
| Partial (unaudited) | 20 | 7.8% |
| Not tested (handled, untested) | 81 | 31.6% |
| Not working (silent / notice / error) | 103 | 40.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Aerie Auxiliary | silent | When this creature enters, support 2. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Aether Spike | silent | Choose target spell. You get {E}{E} (two energy counters), then you may pay any amount of {E}. Counter that spell unless its controller pays {1} for each {E} pa | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ajani Fells the Godsire | silent | II — Create a 2/1 white Cat Warrior creature token, then put a vigilance counter on a creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Amped Raptor | silent | When this creature enters, you get {E}{E} . Then if you cast it from your hand, exile cards from the top of your library until you exile a nonland card. You may | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Arcbound Condor | silent | Modular | no machine in the engine executes this keyword | Y/-/- | not_working |
| Archway of Innovation | silent | {U}, {T}: The next spell you cast this turn has improvise. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Arna Kennerüd, Skycaptain | silent | Whenever a modified creature you control attacks, double the number of each kind of counter on it. Then for each nontoken permanent attached to it, create a tok | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bespoke Battlewagon | silent | Pay {E}{E}{E}{E}: This Vehicle becomes an artifact creature until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bloodsoaked Insight // Sanguine Morass | silent | This spell costs {1} less to cast for each 1 life your opponents have lost this turn. Target opponent exiles the top three cards of their library. Until the end | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Breaker of Creation | silent | When you cast this spell, you gain 1 life for each colorless permanent you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Breathe Your Last | silent | Destroy target creature or planeswalker. You gain 1 life for each of its colors. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Colossal Dreadmask | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Conduit Goblin | error |  | card_support raised: unsupported mana symbol: {E} | Y/-/- | not_working |
| Copycrook | silent | Connive | no machine in the engine executes this keyword | Y/-/- | not_working |
| Crabomination | silent | When this creature enters, target opponent exiles the top card of their library, a card at random from their graveyard, and a card at random from their hand. Yo | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cranial Ram | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Cyclops Superconductor | error |  | card_support raised: unsupported mana symbol: {E} | Y/-/- | not_working |
| Dreamtide Whale | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Drossclaw | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Eladamri, Korvecdal | silent | {G}, {T}, Tap two untapped creatures you control: Reveal a card from your hand or the top card of your library. If you reveal a creature card this way, put it o | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Electrozoa | silent | At the beginning of your first main phase, tap this creature unless you pay {E}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Emrakul, the World Anew | silent | When you cast this spell, gain control of all creatures target player controls. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Envoy of the Ancestors | silent | Modified creatures you control have lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Essence Reliquary | silent | {T}: Return another target permanent you control and all Auras you control attached to it to their owner's hand. Activate only during your turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Expanding Ooze | silent | Whenever this creature attacks, put a +1/+1 counter on target modified creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Expel the Unworthy | silent | Kicker {2}{W} (You may pay an additional {2}{W} as you cast this spell.) Choose target creature with mana value 3 or less. If this spell was kicked, instead cho | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fangs of Kalonia | silent | Overload | no machine in the engine executes this keyword | Y/-/- | not_working |
| Flare of Cultivation | silent | You may sacrifice a nontoken green creature rather than pay this spell's mana cost. Search your library for up to two basic land cards, reveal those cards, put  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Flare of Fortitude | silent | You may sacrifice a nontoken white creature rather than pay this spell's mana cost. Until end of turn, your life total can't change, and permanents you control  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Flare of Malice | silent | You may sacrifice a nontoken black creature rather than pay this spell's mana cost. Each opponent sacrifices a creature or planeswalker with the greatest mana v | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fowl Strike | silent | Reinforce | no machine in the engine executes this keyword | Y/-/- | not_working |
| Frogmyr Enforcer | silent | Prototype | no machine in the engine executes this keyword | Y/-/- | not_working |
| Genku, Future Shaper | silent | Whenever another nontoken permanent you control leaves the battlefield, choose one that hasn't been chosen this turn. Create a creature token with those charact | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gift of the Viper | silent | Put a +1/+1 counter, a reach counter, and a deathtouch counter on target creature. Untap it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Glyph Elemental | silent | Enchanted creature gets +1/+1 for each +1/+1 counter on this Aura. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Golden-Tail Trainer | silent | Whenever this creature attacks, other modified creatures you control get +X/+X until end of turn, where X is this creature's power. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grim Servant | silent | When this creature enters, search your library for a card with mana value less than or equal to your devotion to black, reveal it, put it into your hand, then s | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grist, Voracious Larva // Grist, the Plague Swarm | silent | Whenever Grist or another creature you control enters, if it entered from your graveyard or you cast it from your graveyard, you may pay {G}. If you do, exile G | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Herigast, Erupting Nullkite | silent | When you cast this spell, you may exile your hand. If you do, draw three cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hexgold Slith | error |  | card_support raised: unsupported mana symbol: {E} | Y/-/- | not_working |
| Hope-Ender Coatl | silent | When you cast this spell, counter target spell an opponent controls unless they pay {1}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Horrid Shadowspinner | silent | Whenever this creature attacks, you may draw cards equal to its power. If you do, discard that many cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Imskir Iron-Eater | silent | When Imskir enters, you draw X cards and you lose X life, where X is half the number of artifacts you control, rounded down. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Indebted Spirit | silent | Enchanted creature gets +1/+1 and has afterlife 1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Infernal Captor | silent | When this creature exploits a creature, gain control of target artifact or creature until end of turn. Untap that permanent. It gains haste until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Invert Polarity | silent | Choose target spell, then flip a coin. If you win the flip, gain control of that spell and you may choose new targets for it. If you lose the flip, counter that | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| It That Heralds the End | silent | Other colorless creatures you control get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jolted Awake | silent | Choose up to one target artifact or creature card in your graveyard. You get {E}{E} (two energy counters). Then you may pay an amount of {E} equal to that card' | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Kami of Jealous Thirst | silent | {4}{B}: Each opponent loses 2 life and you gain 2 life. This ability costs {4}{B} less to activate if you've drawn three or more cards this turn. Activate only  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Kozilek's Unsealing | silent | Whenever you cast a creature spell with mana value 4, 5, or 6, create two 0/1 colorless Eldrazi Spawn creature tokens with "Sacrifice this token: Add {C}." | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Kozilek, the Broken Reality | silent | When you cast this spell, up to two target players each manifest two cards from their hands. For each card manifested this way, you draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Kudo, King Among Bears | silent | Other creatures have base power and toughness 2/2 and are Bears in addition to their other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Legion Leadership // Legion Stronghold | silent | Until end of turn, double target creature's power and it gains first strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lethal Throwdown | silent | As an additional cost to cast this spell, sacrifice a creature or sacrifice a modified creature. (Equipment, Auras you control, and counters are modifications.) | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mandibular Kite | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Marionette Apprentice | silent | Fabricate | no machine in the engine executes this keyword | Y/-/- | not_working |
| Monstrous Vortex | silent | Whenever you cast a creature spell with power 5 or greater, discover X, where X is that spell's mana value. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Muster the Departed | silent | Morbid — At the beginning of your end step, if a creature died this turn, populate. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Nyxborn Hydra | silent | Enchanted creature gets +1/+1 for each +1/+1 counter on this Aura and has reach and trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Nyxborn Unicorn | silent | Enchanted creature gets +2/+2 and has mentor. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Powerbalance | silent | Whenever an opponent casts a spell, you may reveal the top card of your library. If you do, you may cast that card without paying its mana cost if the two spell | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Quest for the Necropolis | silent | {5}{B}, Sacrifice this enchantment: Put target creature card from a graveyard onto the battlefield under your control. This ability costs {1} less to activate f | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ral and the Implicit Maze | silent | III — Create a Spellgorger Weird token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reckless Pyrosurfer | silent | Landfall — Whenever a land you control enters, this creature gains battle cry until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ripples of Undeath | silent | At the beginning of your first main phase, mill three cards. Then you may pay {1} and 3 life. If you do, put a card from among those cards into your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rosecot Knight | silent | When this creature enters, look at the top six cards of your library. You may reveal an artifact or enchantment card from among them and put it into your hand.  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rosheen, Roaring Prophet | silent | When Rosheen enters, mill six cards. You may put a card with {X} in its mana cost from among them into your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rush of Inspiration // Crackling Falls | silent | Draw two cards. Then discard a card at random unless you pay {E}{E} (two energy counters). | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scurrilous Sentry | silent | Whenever this creature enters or attacks, it connives. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scurry of Gremlins | silent | When this enchantment enters, create two 1/1 red Gremlin creature tokens. Then you get an amount of {E} equal to the number of creatures you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shadow of the Second Sun | silent | At the beginning of each of enchanted player's postcombat main phases, there is an additional beginning phase after this phase. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shilgengar, Sire of Famine | silent | Sacrifice another creature: Create a Blood token. If you sacrificed an Angel this way, create a number of Blood tokens equal to its toughness instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Signature Slam | silent | Put a +1/+1 counter on target creature you control, then each modified creature you control deals damage equal to its power to target creature you don't control | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Smelted Chargebug | error |  | card_support raised: unsupported mana symbol: {E} | Y/-/- | not_working |
| Sorin of House Markov // Sorin, Ravenous Neonate | silent | −6: Gain control of target creature. It becomes a Vampire in addition to its other types. Put a lifelink counter on it if you control a white permanent other th | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Springheart Nantuko | silent | Landfall — Whenever a land you control enters, you may pay {1}{G} if this permanent is attached to a creature you control. If you do, create a token that's a co | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spymaster's Vault | silent | {B}, {T}: Target creature you control connives X, where X is the number of creatures that died this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Strength of the Harvest // Haven of the Harvest | silent | Enchanted creature gets +1/+1 for each creature and/or enchantment you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sundering Eruption // Volcanic Fissure | silent | Destroy target land. Its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle. Creatures without flying c | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Temperamental Oozewagg | silent | Modified creatures you control have trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Territory Culler | silent | Landfall — Whenever a land you control enters, look at the top card of your library. If it's a creature card, you may reveal it and put it into your hand. If yo | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| The Creation of Avacyn | silent | I — Search your library for a card, exile it face down, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| The Hunger Tide Rises | silent | IV — Sacrifice any number of creatures. Search your library and/or graveyard for a creature card with mana value less than or equal to the number of creatures s | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Triton Wavebreaker | silent | As long as this permanent is a creature, it has prowess. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Twisted Riddlekeeper | silent | Emerge | no machine in the engine executes this keyword | Y/-/- | not_working |
| Ugin's Binding | silent | Devoid (This card has no color.) Return target nonland permanent you don't control to its owner's hand. Whenever you cast a colorless spell with mana value 7 or | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Unfathomable Truths | silent | Devoid (This card has no color.) Draw three cards and create a 0/1 colorless Eldrazi Spawn creature token with "Sacrifice this token: Add {C}." | the engine's reading came from quoted text, not this clause's own words | Y/-/- | not_working |
| Unstable Amulet | silent | {T}, Pay {E}{E}: Exile the top card of your library. You may play it until you exile another card with this artifact. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Utter Insignificance | silent | {2}{C}: Exile enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Volatile Stormdrake | silent | When this creature enters, exchange control of this creature and target creature an opponent controls. If you do, you get {E}{E}{E}{E}, then sacrifice that crea | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Voltstorm Angel | error |  | card_support raised: unsupported mana symbol: {E} | Y/-/- | not_working |
| Wheel of Potential | silent | You get {E}{E}{E} (three energy counters), then you may pay any amount of {E}. Each player may exile their hand and draw a number of cards equal to the amount o | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wumpus Aberration | silent | When you cast this spell, if {C} wasn't spent to cast it, target opponent may put a creature card from their hand onto the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Abstruse Appropriation | notice | Devoid (This card has no color.) Exile target nonland permanent. You may cast that card for as long as it remains exiled, and you may spend colorless mana as th | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Charitable Levy | notice | Whenever a player casts a noncreature spell, put a collection counter on this enchantment. Then if there are three or more collection counters on it, sacrifice  | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Etched Slith | notice | Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. When you do, you may remove a counter from another target permanent or oppone | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Fanged Flames | notice | Devoid (This card has no color.) Fanged Flames deals 4 damage to target creature or planeswalker. If that creature or planeswalker would die this turn, exile it | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Glimpse the Impossible | notice | Exile the top three cards of your library. You may play those cards this turn. At the beginning of the next end step, if any of those cards remain exiled, put t | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Nadu, Winged Wisdom | notice | Creatures you control have "Whenever this creature becomes the target of a spell or ability, reveal the top card of your library. If it's a land card, put it on | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Obstinate Gargoyle | notice | This creature has flying as long as it's modified. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Propagator Drone | notice | Creature tokens you control have evolve. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Pyretic Rebirth | notice | Return target artifact or creature card from your graveyard to your hand. Pyretic Rebirth deals damage equal to that card's mana value to up to one target creat | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Wither and Bloom | notice | Target creature gets -3/-3 until end of turn. {1}{B}, Exile this card from your graveyard: Put a +1/+1 counter on target creature you control. Activate only as  | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Aether Revolt | unaudited | Revolt — As long as a permanent left the battlefield under your control this turn, if a source you control would deal noncombat damage to an opponent or a perma | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Amphibian Downpour | unaudited | Enchanted creature loses all abilities and is a blue Frog creature with base power and toughness 1/1. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Ashling, Flame Dancer | unaudited | You don't lose unspent red mana as steps and phases end. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Corrupted Shapeshifter | unaudited | As this creature enters, it becomes your choice of a 3/3 creature with flying, a 2/5 creature with vigilance, or a 0/12 creature with defender. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Cursed Wombat | unaudited | Permanents you control have "Whenever one or more +1/+1 counters are put on this permanent, put an additional +1/+1 counter on it. This ability triggers only on | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Dog Umbra | unaudited | As long as another player controls enchanted creature, it can't attack or block. Otherwise, this Aura has umbra armor. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Echoes of Eternity | unaudited | If a triggered ability of a colorless spell you control or another colorless permanent you control triggers, that ability triggers an additional time. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Etherium Pteramander | unaudited | This creature can block only creatures with flying. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Hydra Trainer | unaudited | You may exert this creature as it attacks. When you do, target creature gets +X/+X until end of turn, where X is the number of counters on permanents you contro | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Necrodominance | unaudited | Skip your draw step. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Nethergoyf | unaudited | Nethergoyf's power is equal to the number of card types among cards in your graveyard and its toughness is equal to that number plus 1. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Party Thrasher | unaudited | Noncreature spells you cast from exile have convoke. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Path of Annihilation | unaudited | Eldrazi you control have "{T}: Add one mana of any color." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Pearl-Ear, Imperial Advisor | unaudited | Enchantment spells you cast have affinity for Auras. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Primal Prayers | unaudited | You may cast creature spells with mana value 3 or less by paying {E} rather than paying their mana costs. If you cast a spell this way, you may cast it as thoug | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Six | unaudited | During your turn, nonland permanent cards in your graveyard have retrace. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| The Necrobloom | unaudited | Land cards in your graveyard have dredge 2. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Trickster's Elk | unaudited | Enchanted creature loses all abilities and is a green Elk creature with base power and toughness 3/3. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Voidpouncer | unaudited | If this creature was kicked, it enters with two +1/+1 counters and a trample counter on it and with haste. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Winter Moon | unaudited | Players can't untap more than one nonbasic land during their untap steps. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Accursed Marauder | handled | When this creature enters, each player sacrifices a nontoken creature of their choice. | the engine reads this text and performs it | Y/-/- | not_tested |
| Argent Dais | handled | This artifact enters with two oil counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bountiful Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Forest, Island, or Mountain card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Brainsurge | handled | Draw four cards, then put two cards from your hand on top of your library in any order. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chthonian Nightmare | handled | When this enchantment enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Collective Resistance | handled | Escalate {G} (Pay this cost for each mode chosen beyond the first.) Choose one or more — • Destroy target artifact. • Destroy target enchantment. • Target creat | the engine reads this text and performs it | Y/-/- | not_tested |
| Consuming Corruption | handled | Consuming Corruption deals X damage to target creature or planeswalker and you gain X life, where X is the number of Swamps you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Contaminated Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Plains, Island, or Swamp card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deceptive Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Plains, Swamp, or Forest card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Depth Defiler | handled | When you cast this spell, choose one. If it was kicked, choose both instead. • Return target creature to its owner's hand. • Target player draws two cards, then | the engine reads this text and performs it | Y/-/- | not_tested |
| Dreadmobile | handled | {1}, Sacrifice another artifact or creature: Put a +1/+1 counter on this Vehicle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dreamdrinker Vampire | handled | {1}{B}: Adapt 1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drownyard Lurker | handled | When you cast or cycle Drownyard Lurker, create a 0/1 colorless Eldrazi Spawn creature token with "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Eldrazi Linebreaker | handled | At the beginning of combat on your turn, target creature you control gains haste and gets +X/+0 until end of turn, where X is the number of Eldrazi you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eldrazi Ravager | handled | Sacrifice two Eldrazi: Return this card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Emissary of Soulfire | handled | When this creature enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Emrakul's Messenger | handled | Whenever you draw your second card each turn, create a 0/1 colorless Eldrazi Spawn creature token with "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Eviscerator's Insight | handled | As an additional cost to cast this spell, sacrifice an artifact or creature. Draw two cards. Flashback {4}{B} (You may cast this card from your graveyard for it | the engine reads this text and performs it | Y/-/- | not_tested |
| Evolution Witness | handled | {1}{G}: Adapt 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Faithful Watchdog | handled | This creature enters with three +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fell the Profane // Fell Mire | handled | Destroy target creature or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fetid Gargantua | handled | {2}{B}: Adapt 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flare of Denial | handled | You may sacrifice a nontoken blue creature rather than pay this spell's mana cost. Counter target spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flare of Duplication | handled | You may sacrifice a nontoken red creature rather than pay this spell's mana cost. Copy target instant or sorcery spell. You may choose new targets for the copy. | the engine reads this text and performs it | Y/-/- | not_tested |
| Foreboding Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Swamp, Forest, or Island card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Furnace Hellkite | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghostfire Slice | handled | Devoid (This card has no color.) This spell costs {2} less to cast if an opponent controls a multicolored permanent. Ghostfire Slice deals 4 damage to any targe | the engine reads this text and performs it | Y/-/- | not_tested |
| Glasswing Grace // Age-Graced Chapel | handled | Enchanted creature gets +2/+2 and has flying and lifelink. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gravedig | handled | Choose one — • Target player creates a 2/2 black Zombie creature token. • Return target creature card from your graveyard to your hand. Entwine {2} (Choose both | the engine reads this text and performs it | Y/-/- | not_tested |
| Guardian of the Forgotten | handled | Whenever a modified creature you control dies, manifest the top card of your library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Horrific Assault | handled | Target creature you control deals damage equal to its power to target creature or planeswalker you don't control. If you control an Eldrazi, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Inspired Inventor | handled | When this creature enters, choose one — • You get {E}{E}{E} . • Put a +1/+1 counter on target creature. • Create a 1/1 colorless Servo artifact creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Inventor's Axe | handled | When this Equipment enters, you get {E}{E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Izzet Generatorium | handled | If you would get one or more {E} , you get that many plus one {E} instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lion Umbra | handled | Enchanted creature gets +3/+3 and has reach and vigilance. | the engine reads this text and performs it | Y/-/- | not_tested |
| Metastatic Evangel | handled | Whenever another nontoken creature you control enters, proliferate. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mindless Conscription | handled | When this enchantment enters and whenever you draw your third card each turn, amass Zombies 3. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mogg Mob | handled | Sacrifice this creature: It deals 3 damage divided as you choose among one, two, or three targets. | the engine reads this text and performs it | Y/-/- | not_tested |
| Molten Gatekeeper | handled | Whenever another creature you control enters, this creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nightshade Dryad | handled | Deathtouch | machines/combat.py | Y/-/- | not_tested |
| Nulldrifter | handled | When you cast this spell, draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ondu Knotmaster // Throw a Line | handled | Distribute two +1/+1 counters among one or two target creatures. (Then exile this card. You may cast the creature later from exile.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Perilous Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Island, Mountain, or Plains card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phlage, Titan of Fire's Fury | handled | When Phlage enters, sacrifice it unless it escaped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Ironworks | handled | Whenever you attack, you get {E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Pinnacle Monk // Mystic Peak | handled | When this creature enters, return target instant or sorcery card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Proud Pack-Rhino | handled | When this creature enters, choose one — • Put a shield counter on target permanent. • Proliferate. | the engine reads this text and performs it | Y/-/- | not_tested |
| Razorgrass Ambush // Razorgrass Field | handled | Razorgrass Ambush deals 3 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Reiterating Bolt | handled | Replicate—Pay {E}{E}{E}. (When you cast this spell, copy it for each time you paid its replicate cost. You may choose new targets for the copies.) Reiterating B | the engine reads this text and performs it | Y/-/- | not_tested |
| Retrofitted Transmogrant | handled | {3}{B}: Return this card from your graveyard to the battlefield tapped with two +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Revitalizing Repast // Old-Growth Grove | handled | Put a +1/+1 counter on target creature. It gains indestructible until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Riddle Gate Gargoyle | handled | When this creature enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Roil Cartographer | handled | Landfall — Whenever a land you control enters, you get {E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Sage of the Unknowable | handled |  |  | Y/-/- | not_tested |
| Sarpadian Simulacrum | handled | {3}{R}, Sacrifice this creature: It deals 4 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seething Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Island, Swamp, or Mountain card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serum Visionary | handled | When this creature enters, draw a card, then scry 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shattered Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Mountain, Plains, or Swamp card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sheltering Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Mountain, Forest, or Plains card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Siege Smash | handled | Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.) Choose one — • Destroy target  | the engine reads this text and performs it | Y/-/- | not_tested |
| Skittering Precursor | handled | Whenever you sacrifice a nontoken permanent, create a 0/1 colorless Eldrazi Spawn creature token with "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Skoa, Embermage | handled | When Skoa enters, it deals 4 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Snapping Voidcraw | handled | {3}{C}, {T}: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sneaky Snacker | handled | When you draw your third card in a turn, return this card from your graveyard to the battlefield tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Snow-Covered Wastes | handled |  |  | Y/-/- | not_tested |
| Solar Transformer | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Solstice Zealot | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Spawn-Gang Commander | handled | When you cast this spell, create three 0/1 colorless Eldrazi Spawn creature tokens with "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Stump Stomp // Burnwillow Clearing | handled | Target creature you control deals damage equal to its power to target creature or planeswalker you don't control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tempest Harvester | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Thriving Skyclaw | handled | When this creature enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/-/- | not_tested |
| Tranquil Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Forest, Plains, or Island card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Twisted Landscape | handled | {T}, Sacrifice this land: Search your library for a basic Swamp, Mountain, or Forest card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Urza's Cave | handled | {3}, {T}, Sacrifice this land: Search your library for a land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Warped Tusker | handled | When you cast or cycle Warped Tusker, create a 0/1 colorless Eldrazi Spawn creature token with "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Warren Soultrader | handled | Pay 1 life, Sacrifice another creature: Create a Treasure token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wastescape Battlemage | handled | When you cast this spell, if it was kicked with its {G} kicker, exile target artifact or enchantment an opponent controls. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wight of the Reliquary | handled | This creature gets +1/+1 for each creature card in your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wing It | handled | Target creature gets +2/+2 until end of turn. Put a flying counter on it. Scry 1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Writhing Chrysalis | handled | When you cast this spell, create two 0/1 colorless Eldrazi Spawn creature tokens with "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Wurmcoil Larva | handled | When this creature dies, create a 1/2 black Phyrexian Wurm artifact creature token with deathtouch and a 2/1 black Phyrexian Wurm artifact creature token with l | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>52 cards</summary>

- Ajani, Nacatl Pariah // Ajani, Nacatl Avenger
- Arena of Glory
- Basking Broodscale
- Birthing Ritual
- Boggart Trawler // Boggart Bog
- Bridgeworks Battle // Tanglespan Bridgeworks
- Consign to Memory
- Deem Inferior
- Detective's Phoenix
- Devourer of Destiny
- Disciple of Freyalise // Garden of Freyalise
- Disruptor Flute
- Drowner of Truth // Drowned Jungle
- Eldrazi Repurposer
- Emperor of Bones
- Fanatic of Rhonas
- Galvanic Discharge
- Glaring Fleshraker
- Guide of Souls
- Harbinger of the Seas
- Hydroelectric Specimen // Hydroelectric Laboratory
- Idol of False Gods
- Kozilek's Command
- Malevolent Rumble
- Monumental Henge
- Null Elemental Blast
- Ocelot Pride
- Petrifying Meddler
- Phelia, Exuberant Shepherd
- Planar Genesis
- Psychic Frog
- Ral, Monsoon Mage // Ral, Leyline Prodigy
- Refurbished Familiar
- Shifting Woodland
- Sink into Stupor // Soporific Springs
- Sowing Mycospawn
- Static Prison
- Strix Serenade
- Suppression Ray // Orderly Plaza
- Tamiyo Meets the Story Circle
- Tamiyo, Inquisitive Student // Tamiyo, Seasoned Scholar
- Thief of Existence
- Thraben Charm
- Titans' Vanguard
- Tune the Narrative
- Ugin's Labyrinth
- Ulamog, the Defiler
- Vexing Bauble
- Waterlogged Teachings // Inundated Archive
- White Orchid Phantom
- Witch Enchanter // Witch-Blessed Meadow
- Wrath of the Skies

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| When you cast this spell, up to two target players each manifest two cards from their hands. For each card manifested this way, you draw a card. | Breaker of Creation, Emrakul, the World Anew, Herigast, Erupting Nullkite, Hope-Ender Coatl, Kozilek, the Broken Reality, Wumpus Aberration | 6 |
| Devoid (This card has no color.) Return target nonland permanent you don't control to its owner's hand. Whenever you cast a colorless spell with mana value 7 or | Abstruse Appropriation, Fanged Flames, Ugin's Binding, Unfathomable Truths | 4 |
| Living weapon | Colossal Dreadmask, Cranial Ram, Drossclaw, Mandibular Kite | 4 |
| Enchanted creature gets +1/+1 for each +1/+1 counter on this Aura and has reach and trample. | Glyph Elemental, Nyxborn Hydra, Strength of the Harvest // Haven of the Harvest | 3 |
| Landfall — Whenever a land you control enters, you may pay {1}{G} if this permanent is attached to a creature you control. If you do, create a token that's a co | Reckless Pyrosurfer, Springheart Nantuko, Territory Culler | 3 |
| You may sacrifice a nontoken green creature rather than pay this spell's mana cost. Search your library for up to two basic land cards, reveal those cards, put  | Flare of Cultivation, Flare of Fortitude, Flare of Malice | 3 |
| At the beginning of your first main phase, mill three cards. Then you may pay {1} and 3 life. If you do, put a card from among those cards into your hand. | Electrozoa, Ripples of Undeath | 2 |
| Enchanted creature gets +1/+1 and has afterlife 1. | Indebted Spirit, Nyxborn Unicorn | 2 |
| Enchanted creature loses all abilities and is a blue Frog creature with base power and toughness 1/1. | Amphibian Downpour, Trickster's Elk | 2 |
| Modified creatures you control have lifelink. | Envoy of the Ancestors, Temperamental Oozewagg | 2 |
| Whenever you cast a creature spell with mana value 4, 5, or 6, create two 0/1 colorless Eldrazi Spawn creature tokens with "Sacrifice this token: Add {C}." | Kozilek's Unsealing, Monstrous Vortex | 2 |
| As an additional cost to cast this spell, sacrifice a creature or sacrifice a modified creature. (Equipment, Auras you control, and counters are modifications.) | Lethal Throwdown | 1 |
| As long as another player controls enchanted creature, it can't attack or block. Otherwise, this Aura has umbra armor. | Dog Umbra | 1 |
| As long as this permanent is a creature, it has prowess. | Triton Wavebreaker | 1 |
| As this creature enters, it becomes your choice of a 3/3 creature with flying, a 2/5 creature with vigilance, or a 0/12 creature with defender. | Corrupted Shapeshifter | 1 |
| At the beginning of each of enchanted player's postcombat main phases, there is an additional beginning phase after this phase. | Shadow of the Second Sun | 1 |
| Choose target spell, then flip a coin. If you win the flip, gain control of that spell and you may choose new targets for it. If you lose the flip, counter that | Invert Polarity | 1 |
| Choose target spell. You get {E}{E} (two energy counters), then you may pay any amount of {E}. Counter that spell unless its controller pays {1} for each {E} pa | Aether Spike | 1 |
| Choose up to one target artifact or creature card in your graveyard. You get {E}{E} (two energy counters). Then you may pay an amount of {E} equal to that card' | Jolted Awake | 1 |
| Connive | Copycrook | 1 |
| Creature tokens you control have evolve. | Propagator Drone | 1 |
| Creatures you control have "Whenever this creature becomes the target of a spell or ability, reveal the top card of your library. If it's a land card, put it on | Nadu, Winged Wisdom | 1 |
| Destroy target creature or planeswalker. You gain 1 life for each of its colors. | Breathe Your Last | 1 |
| Destroy target land. Its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle. Creatures without flying c | Sundering Eruption // Volcanic Fissure | 1 |
| Draw two cards. Then discard a card at random unless you pay {E}{E} (two energy counters). | Rush of Inspiration // Crackling Falls | 1 |
| During your turn, nonland permanent cards in your graveyard have retrace. | Six | 1 |
| {4}{B}: Each opponent loses 2 life and you gain 2 life. This ability costs {4}{B} less to activate if you've drawn three or more cards this turn. Activate only  | Kami of Jealous Thirst | 1 |
| Eldrazi you control have "{T}: Add one mana of any color." | Path of Annihilation | 1 |
| Emerge | Twisted Riddlekeeper | 1 |
| Enchantment spells you cast have affinity for Auras. | Pearl-Ear, Imperial Advisor | 1 |
| {2}{C}: Exile enchanted creature. | Utter Insignificance | 1 |
| Exile the top three cards of your library. You may play those cards this turn. At the beginning of the next end step, if any of those cards remain exiled, put t | Glimpse the Impossible | 1 |
| Fabricate | Marionette Apprentice | 1 |
| −6: Gain control of target creature. It becomes a Vampire in addition to its other types. Put a lifelink counter on it if you control a white permanent other th | Sorin of House Markov // Sorin, Ravenous Neonate | 1 |
| I — Search your library for a card, exile it face down, then shuffle. | The Creation of Avacyn | 1 |
| If a triggered ability of a colorless spell you control or another colorless permanent you control triggers, that ability triggers an additional time. | Echoes of Eternity | 1 |
| If this creature was kicked, it enters with two +1/+1 counters and a trample counter on it and with haste. | Voidpouncer | 1 |
| II — Create a 2/1 white Cat Warrior creature token, then put a vigilance counter on a creature you control. | Ajani Fells the Godsire | 1 |
| III — Create a Spellgorger Weird token. | Ral and the Implicit Maze | 1 |
| IV — Sacrifice any number of creatures. Search your library and/or graveyard for a creature card with mana value less than or equal to the number of creatures s | The Hunger Tide Rises | 1 |
| Kicker {2}{W} (You may pay an additional {2}{W} as you cast this spell.) Choose target creature with mana value 3 or less. If this spell was kicked, instead cho | Expel the Unworthy | 1 |
| Land cards in your graveyard have dredge 2. | The Necrobloom | 1 |
| Modular | Arcbound Condor | 1 |
| Morbid — At the beginning of your end step, if a creature died this turn, populate. | Muster the Departed | 1 |
| Nethergoyf's power is equal to the number of card types among cards in your graveyard and its toughness is equal to that number plus 1. | Nethergoyf | 1 |
| Noncreature spells you cast from exile have convoke. | Party Thrasher | 1 |
| Other colorless creatures you control get +1/+1. | It That Heralds the End | 1 |
| Other creatures have base power and toughness 2/2 and are Bears in addition to their other types. | Kudo, King Among Bears | 1 |
| Overload | Fangs of Kalonia | 1 |
| {T}, Pay {E}{E}: Exile the top card of your library. You may play it until you exile another card with this artifact. | Unstable Amulet | 1 |
| Pay {E}{E}{E}{E}: This Vehicle becomes an artifact creature until end of turn. | Bespoke Battlewagon | 1 |
| Permanents you control have "Whenever one or more +1/+1 counters are put on this permanent, put an additional +1/+1 counter on it. This ability triggers only on | Cursed Wombat | 1 |
| Players can't untap more than one nonbasic land during their untap steps. | Winter Moon | 1 |
| Prototype | Frogmyr Enforcer | 1 |
| Put a +1/+1 counter, a reach counter, and a deathtouch counter on target creature. Untap it. | Gift of the Viper | 1 |
| Put a +1/+1 counter on target creature you control, then each modified creature you control deals damage equal to its power to target creature you don't control | Signature Slam | 1 |
| Reinforce | Fowl Strike | 1 |
| {T}: Return another target permanent you control and all Auras you control attached to it to their owner's hand. Activate only during your turn. | Essence Reliquary | 1 |
| Return target artifact or creature card from your graveyard to your hand. Pyretic Rebirth deals damage equal to that card's mana value to up to one target creat | Pyretic Rebirth | 1 |
| Revolt — As long as a permanent left the battlefield under your control this turn, if a source you control would deal noncombat damage to an opponent or a perma | Aether Revolt | 1 |
| Sacrifice another creature: Create a Blood token. If you sacrificed an Angel this way, create a number of Blood tokens equal to its toughness instead. | Shilgengar, Sire of Famine | 1 |
| {5}{B}, Sacrifice this enchantment: Put target creature card from a graveyard onto the battlefield under your control. This ability costs {1} less to activate f | Quest for the Necropolis | 1 |
| Skip your draw step. | Necrodominance | 1 |
| {G}, {T}, Tap two untapped creatures you control: Reveal a card from your hand or the top card of your library. If you reveal a creature card this way, put it o | Eladamri, Korvecdal | 1 |
| Target creature gets -3/-3 until end of turn. {1}{B}, Exile this card from your graveyard: Put a +1/+1 counter on target creature you control. Activate only as  | Wither and Bloom | 1 |
| {B}, {T}: Target creature you control connives X, where X is the number of creatures that died this turn. | Spymaster's Vault | 1 |
| {U}, {T}: The next spell you cast this turn has improvise. | Archway of Innovation | 1 |
| This creature can block only creatures with flying. | Etherium Pteramander | 1 |
| This creature has flying as long as it's modified. | Obstinate Gargoyle | 1 |
| This spell costs {1} less to cast for each 1 life your opponents have lost this turn. Target opponent exiles the top three cards of their library. Until the end | Bloodsoaked Insight // Sanguine Morass | 1 |
| Until end of turn, double target creature's power and it gains first strike. | Legion Leadership // Legion Stronghold | 1 |
| Vanishing | Dreamtide Whale | 1 |
| When Imskir enters, you draw X cards and you lose X life, where X is half the number of artifacts you control, rounded down. | Imskir Iron-Eater | 1 |
| When Rosheen enters, mill six cards. You may put a card with {X} in its mana cost from among them into your hand. | Rosheen, Roaring Prophet | 1 |
| When this creature enters, exchange control of this creature and target creature an opponent controls. If you do, you get {E}{E}{E}{E}, then sacrifice that crea | Volatile Stormdrake | 1 |
| When this creature enters, look at the top six cards of your library. You may reveal an artifact or enchantment card from among them and put it into your hand.  | Rosecot Knight | 1 |
| When this creature enters, search your library for a card with mana value less than or equal to your devotion to black, reveal it, put it into your hand, then s | Grim Servant | 1 |
| When this creature enters, support 2. | Aerie Auxiliary | 1 |
| When this creature enters, target opponent exiles the top card of their library, a card at random from their graveyard, and a card at random from their hand. Yo | Crabomination | 1 |
| When this creature enters, you get {E}{E} . Then if you cast it from your hand, exile cards from the top of your library until you exile a nonland card. You may | Amped Raptor | 1 |
| When this creature exploits a creature, gain control of target artifact or creature until end of turn. Untap that permanent. It gains haste until end of turn. | Infernal Captor | 1 |
| When this enchantment enters, create two 1/1 red Gremlin creature tokens. Then you get an amount of {E} equal to the number of creatures you control. | Scurry of Gremlins | 1 |
| Whenever a modified creature you control attacks, double the number of each kind of counter on it. Then for each nontoken permanent attached to it, create a tok | Arna Kennerüd, Skycaptain | 1 |
| Whenever a player casts a noncreature spell, put a collection counter on this enchantment. Then if there are three or more collection counters on it, sacrifice  | Charitable Levy | 1 |
| Whenever an opponent casts a spell, you may reveal the top card of your library. If you do, you may cast that card without paying its mana cost if the two spell | Powerbalance | 1 |
| Whenever another nontoken permanent you control leaves the battlefield, choose one that hasn't been chosen this turn. Create a creature token with those charact | Genku, Future Shaper | 1 |
| Whenever Grist or another creature you control enters, if it entered from your graveyard or you cast it from your graveyard, you may pay {G}. If you do, exile G | Grist, Voracious Larva // Grist, the Plague Swarm | 1 |
| Whenever this creature attacks, other modified creatures you control get +X/+X until end of turn, where X is this creature's power. | Golden-Tail Trainer | 1 |
| Whenever this creature attacks, put a +1/+1 counter on target modified creature you control. | Expanding Ooze | 1 |
| Whenever this creature attacks, you may draw cards equal to its power. If you do, discard that many cards. | Horrid Shadowspinner | 1 |
| Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. When you do, you may remove a counter from another target permanent or oppone | Etched Slith | 1 |
| Whenever this creature enters or attacks, it connives. | Scurrilous Sentry | 1 |
| You don't lose unspent red mana as steps and phases end. | Ashling, Flame Dancer | 1 |
| You get {E}{E}{E} (three energy counters), then you may pay any amount of {E}. Each player may exile their hand and draw a number of cards equal to the amount o | Wheel of Potential | 1 |
| You may cast creature spells with mana value 3 or less by paying {E} rather than paying their mana costs. If you cast a spell this way, you may cast it as thoug | Primal Prayers | 1 |
| You may exert this creature as it attacks. When you do, target creature gets +X/+X until end of turn, where X is the number of counters on permanents you contro | Hydra Trainer | 1 |

## Notes



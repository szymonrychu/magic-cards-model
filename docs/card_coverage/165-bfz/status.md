# Battle for Zendikar (bfz)

- Expansion: 165
- Set code: `bfz`
- Release date: 2015-10-02
- Cards in scope (Modern/Pioneer/Standard-legal): 226

## Legality

| Format | Legal cards |
|---|---|
| Modern | 226 |
| Pioneer | 226 |
| Standard | 5 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 27 | 11.9% |
| Works (untested) | 157 | 69.5% |
| Partial (unaudited) | 6 | 2.7% |
| Not working | 36 | 15.9% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Bane of Bala Ged | silent | Whenever this creature attacks, defending player exiles two permanents they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Benthic Infiltrator | silent | Ingest | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Brilliant Spectrum | silent | Converge — Draw X cards, where X is the number of colors of mana spent to cast this spell. Then discard two cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Bring to Light | silent | Converge — Search your library for a creature, instant, or sorcery card with mana value less than or equal to the number of colors of mana spent to cast this sp | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Call the Scions | silent | Devoid (This card has no color.) Create two 1/1 colorless Eldrazi Scion creature tokens. They have "Sacrifice this token: Add {C}." | the engine's reading came from quoted text, not this clause's own words | Y/Y/- | not_working |
| Crumble to Dust | silent | Devoid (This card has no color.) Exile target nonbasic land. Search its controller's graveyard, hand, and library for any number of cards with the same name as  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Culling Drone | silent | Ingest | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Drana, Liberator of Malakir | silent | Whenever Drana deals combat damage to a player, put a +1/+1 counter on each attacking creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Exert Influence | silent | Converge — Gain control of target creature if its power is less than or equal to the number of colors of mana spent to cast this spell. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fathom Feeder | silent | {3}{U}{B}: Draw a card. Each opponent exiles the top card of their library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fertile Thicket | silent | When this land enters, you may look at the top five cards of your library. If you do, reveal up to one basic land card from among them, then put that card on to | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gideon, Ally of Zendikar | silent | +1: Until end of turn, Gideon becomes a 5/5 Human Soldier Ally creature with indestructible that's still a planeswalker. Prevent all damage that would be dealt  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Grip of Desolation | silent | Devoid (This card has no color.) Exile target creature and target land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gruesome Slaughter | silent | Until end of turn, colorless creatures you control gain "{T}: This creature deals damage equal to its power to target creature." | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hedron Blade | silent | Whenever equipped creature becomes blocked by one or more colorless creatures, it gains deathtouch until end of turn. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Infuse with the Elements | silent | Converge — Put X +1/+1 counters on target creature, where X is the number of colors of mana spent to cast this spell. That creature gains trample until end of t | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mist Intruder | silent | Ingest | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Munda, Ambush Leader | silent | Rally — Whenever Munda or another Ally you control enters, you may look at the top four cards of your library. If you do, reveal any number of Ally cards from a | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Quarantine Field | silent | When this enchantment enters, for each isolation counter on it, exile up to one target nonland permanent an opponent controls until this enchantment leaves the  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ruination Guide | silent | Ingest | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Salvage Drone | silent | Ingest | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Silent Skimmer | silent | Whenever this creature attacks, defending player loses 2 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sire of Stagnation | silent | Whenever a land an opponent controls enters, that player exiles the top two cards of their library and you draw two cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Skyline Cascade | silent | When this land enters, target creature an opponent controls doesn't untap during its controller's next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Slab Hammer | silent | Whenever equipped creature attacks, you may return a land you control to its owner's hand. If you do, the creature gets +2/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sludge Crawler | silent | Ingest | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Smothering Abomination | silent | At the beginning of your upkeep, sacrifice a creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tightening Coils | silent | Enchanted creature gets -6/-0 and loses flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Titan's Presence | silent | As an additional cost to cast this spell, reveal a colorless creature card from your hand. Exile target creature if its power is less than or equal to the revea | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Transgress the Mind | silent | Devoid (This card has no color.) Target player reveals their hand. You choose a card from it with mana value 3 or greater and exile that card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Vile Aggregate | silent | Ingest | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Zada, Hedron Grinder | silent | Whenever you cast an instant or sorcery spell that targets only Zada, copy that spell for each other creature you control that the spell could target. Each copy | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Barrage Tyrant | notice | {2}{R}, Sacrifice another colorless creature: This creature deals damage equal to the sacrificed creature's power to any target. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Emeria Shepherd | notice | Landfall — Whenever a land you control enters, you may return target nonland permanent card from your graveyard to your hand. If that land is a Plains, you may  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Herald of Kozilek | notice | Colorless spells you cast cost {1} less to cast. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Unnatural Aggression | notice | Devoid (This card has no color.) Target creature you control fights target creature an opponent controls. If the creature an opponent controls would die this tu | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Breaker of Armies | unaudited | All creatures able to block this creature do so. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Kor Castigator | unaudited | This creature can't be blocked by Eldrazi Scions. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Reckless Cohort | unaudited | This creature attacks each combat if able unless you control another Ally. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ulamog's Despoiler | unaudited | As this creature enters, you may put two cards your opponents own from exile into their owners' graveyards. If you do, this creature enters with four +1/+1 coun | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Undergrowth Champion | unaudited | If damage would be dealt to this creature while it has a +1/+1 counter on it, prevent that damage and remove a +1/+1 counter from this creature. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Void Winnower | unaudited | Your opponents can't cast spells with even mana values. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Adverse Conditions | handled | Devoid (This card has no color.) Tap up to two target creatures. Those creatures don't untap during their controller's next untap step. Create a 1/1 colorless E | the engine reads this text and performs it | Y/Y/- | not_tested |
| Akoum Firebird | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Akoum Stonewaker | handled | Landfall — Whenever a land you control enters, you may pay {2}{R}. If you do, create a 3/1 red Elemental creature token with trample and haste. Exile that token | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ally Encampment | handled | {1}, {T}, Sacrifice this land: Return target Ally you control to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Angel of Renewal | handled | When this creature enters, you gain 1 life for each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Angelic Captain | handled | Whenever this creature attacks, it gets +1/+1 until end of turn for each other attacking Ally. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Angelic Gift | handled | When this Aura enters, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Beastcaller Savant | handled | Haste | machines/combat.py | Y/Y/- | not_tested |
| Belligerent Whiptail | handled | Landfall — Whenever a land you control enters, this creature gains first strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blight Herder | handled | When you cast this spell, you may put two cards your opponents own from exile into their owners' graveyards. If you do, create three 1/1 colorless Eldrazi Scion | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blighted Cataract | handled | {5}{U}, {T}, Sacrifice this land: Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blighted Fen | handled | {4}{B}, {T}, Sacrifice this land: Target opponent sacrifices a creature of their choice. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blighted Gorge | handled | {4}{R}, {T}, Sacrifice this land: It deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blighted Steppe | handled | {3}{W}, {T}, Sacrifice this land: You gain 2 life for each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blighted Woodland | handled | {3}{G}, {T}, Sacrifice this land: Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bloodbond Vampire | handled | Whenever you gain life, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Boiling Earth | handled | Boiling Earth deals 1 damage to each creature your opponents control. Awaken 4—{6}{R} (If you cast this spell for {6}{R}, also put four +1/+1 counters on target | the engine reads this text and performs it | Y/Y/- | not_tested |
| Brood Butcher | handled | When this creature enters, create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Brood Monitor | handled | When this creature enters, create three 1/1 colorless Eldrazi Scion creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Broodhunter Wurm | handled |  |  | Y/Y/- | not_tested |
| Brutal Expulsion | handled | Devoid (This card has no color.) Choose one or both — • Return target spell or creature to its owner's hand. • Brutal Expulsion deals 2 damage to target creatur | the engine reads this text and performs it | Y/Y/- | not_tested |
| Carrier Thrall | handled | When this creature dies, create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Catacomb Sifter | handled | When this creature enters, create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chasm Guide | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control gain haste until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cinder Glade | handled | This land enters tapped unless you control two or more basic lands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cliffside Lookout | handled | {4}{W}: Creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cloud Manta | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Coastal Discovery | handled | Draw two cards. Awaken 4—{5}{U} (If you cast this spell for {5}{U}, also put four +1/+1 counters on target land you control and it becomes a 0/0 Elemental creat | the engine reads this text and performs it | Y/Y/- | not_tested |
| Complete Disregard | handled | Devoid (This card has no color.) Exile target creature with power 3 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Coralhelm Guide | handled | {4}{U}: Target creature can't be blocked this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Courier Griffin | handled | When this creature enters, you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cryptic Cruiser | handled | {2}{U}, Put a card an opponent owns from exile into that player's graveyard: Tap target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dampening Pulse | handled | Creatures your opponents control get -1/-0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deathless Behemoth | handled | Sacrifice two Eldrazi Scions: Return this card from your graveyard to your hand. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Defiant Bloodlord | handled | Whenever you gain life, target opponent loses that much life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Demon's Grasp | handled | Target creature gets -5/-5 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Desolation Twin | handled | When you cast this spell, create a 10/10 colorless Eldrazi creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drana's Emissary | handled | At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drowner of Hope | handled | When this creature enters, create two 1/1 colorless Eldrazi Scion creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Earthen Arms | handled | Put two +1/+1 counters on target permanent. Awaken 4—{6}{G} (If you cast this spell for {6}{G}, also put four +1/+1 counters on target land you control and it b | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eldrazi Devastator | handled | Trample | machines/combat.py | Y/Y/- | not_tested |
| Eldrazi Skyspawner | handled | When this creature enters, create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Expedition Envoy | handled |  |  | Y/Y/- | not_tested |
| Eyeless Watcher | handled | When this creature enters, create two 1/1 colorless Eldrazi Scion creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Felidar Cub | handled | Sacrifice this creature: Destroy target enchantment. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Firemantle Mage | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control gain menace until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fortified Rampart | handled | Defender | machines/combat.py | Y/Y/- | not_tested |
| From Beyond | handled | At the beginning of your upkeep, create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Geyserfield Stalker | handled | Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ghostly Sentinel | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Gideon's Reproach | handled | Gideon's Reproach deals 4 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grave Birthing | handled | Devoid (This card has no color.) Target opponent exiles a card from their graveyard. You create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Greenwarden of Murasa | handled | When this creature enters, you may return target card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grove Rumbler | handled | Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grovetender Druids | handled | Rally — Whenever this creature or another Ally you control enters, you may pay {1}. If you do, create a 1/1 green Plant creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Guardian of Tazeem | handled | Landfall — Whenever a land you control enters, tap target creature an opponent controls. If that land is an Island, that creature doesn't untap during its contr | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hagra Sharpshooter | handled | {4}{B}: Target creature gets -1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Halimar Tidecaller | handled | When this creature enters, you may return target card with awaken from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hedron Archive | handled | {2}, {T}, Sacrifice this artifact: Draw two cards. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Hero of Goma Fada | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control gain indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Horribly Awry | handled | Devoid (This card has no color.) Counter target creature spell with mana value 4 or less. If that spell is countered this way, exile it instead of putting it in | the engine reads this text and performs it | Y/Y/- | not_tested |
| Incubator Drone | handled | When this creature enters, create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jaddi Offshoot | handled | Landfall — Whenever a land you control enters, you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kalastria Healer | handled | Rally — Whenever this creature or another Ally you control enters, each opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kalastria Nightwatch | handled | Whenever you gain life, this creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kitesail Scout | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Kor Bladewhirl | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control gain first strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kor Entanglers | handled | Rally — Whenever this creature or another Ally you control enters, tap target creature an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kozilek's Channeler | handled |  |  | Y/Y/- | not_tested |
| Kozilek's Sentinel | handled | Whenever you cast a colorless spell, this creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lantern Scout | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control gain lifelink until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lavastep Raider | handled | {2}{R}: This creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lifespring Druid | handled |  |  | Y/Y/- | not_tested |
| Looming Spires | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lumbering Falls | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Makindi Patrol | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control gain vigilance until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Makindi Sliderunner | handled | Landfall — Whenever a land you control enters, this creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Malakir Familiar | handled | Whenever you gain life, this creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| March from the Tomb | handled | Return any number of target Ally creature cards with total mana value 8 or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mind Raker | handled | When this creature enters, you may put a card an opponent owns from exile into that player's graveyard. If you do, each opponent discards a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mire's Malice | handled | Target opponent discards two cards. Awaken 3—{5}{B} (If you cast this spell for {5}{B}, also put three +1/+1 counters on target land you control and it becomes  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Molten Nursery | handled | Whenever you cast a colorless spell, this enchantment deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mortuary Mire | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Murasa Ranger | handled | Landfall — Whenever a land you control enters, you may pay {3}{G}. If you do, put two +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Natural Connection | handled | Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nettle Drone | handled | {T}: This creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nirkana Assassin | handled | Whenever you gain life, this creature gains deathtouch until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nissa's Renewal | handled | Search your library for up to three basic land cards, put them onto the battlefield tapped, then shuffle. You gain 7 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Noyan Dar, Roil Shaper | handled | Whenever you cast an instant or sorcery spell, you may put three +1/+1 counters on target land you control. If you do, that land becomes a 0/0 Elemental creatur | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ob Nixilis Reignited | handled | +1: You draw a card and you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Omnath, Locus of Rage | handled | Landfall — Whenever a land you control enters, create a 5/5 red and green Elemental creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ondu Champion | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control gain trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ondu Greathorn | handled | Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ondu Rising | handled | Whenever a creature attacks this turn, it gains lifelink until end of turn. Awaken 4—{4}{W} (If you cast this spell for {4}{W}, also put four +1/+1 counters on  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Oracle of Dust | handled | {2}, Put a card an opponent owns from exile into that player's graveyard: Draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Oran-Rief Hydra | handled | Landfall — Whenever a land you control enters, put a +1/+1 counter on this creature. If that land is a Forest, put two +1/+1 counters on this creature instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Oran-Rief Invoker | handled | {8}: This creature gets +5/+5 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Outnumber | handled | Outnumber deals damage to target creature equal to the number of creatures you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Part the Waterveil | handled | Take an extra turn after this one. Exile Part the Waterveil. Awaken 6—{6}{U}{U}{U} (If you cast this spell for {6}{U}{U}{U}, also put six +1/+1 counters on targ | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pathway Arrows | handled | Equipped creature has "{2}, {T}: This creature deals 1 damage to target creature. If a colorless creature is dealt damage this way, tap it." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Planar Outburst | handled | Destroy all nonland creatures. Awaken 4—{5}{W}{W}{W} (If you cast this spell for {5}{W}{W}{W}, also put four +1/+1 counters on target land you control and it be | the engine reads this text and performs it | Y/Y/- | not_tested |
| Plated Crusher | handled | Hexproof | machines/casting.py (target legality) | Y/Y/- | not_tested |
| Prairie Stream | handled | This land enters tapped unless you control two or more basic lands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prism Array | handled | Converge — This enchantment enters with a crystal counter on it for each color of mana spent to cast it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Processor Assault | handled | Devoid (This card has no color.) As an additional cost to cast this spell, put a card an opponent owns from exile into that player's graveyard. Processor Assaul | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reclaiming Vines | handled | Destroy target artifact, enchantment, or land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Resolute Blademaster | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control gain double strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Retreat to Coralhelm | handled | Landfall — Whenever a land you control enters, choose one — • You may tap or untap target creature. • Scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Retreat to Emeria | handled | Landfall — Whenever a land you control enters, choose one — • Create a 1/1 white Kor Ally creature token. • Creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Retreat to Hagra | handled | Landfall — Whenever a land you control enters, choose one — • Target creature gets +1/+0 and gains deathtouch until end of turn. • Each opponent loses 1 life an | the engine reads this text and performs it | Y/Y/- | not_tested |
| Retreat to Valakut | handled | Landfall — Whenever a land you control enters, choose one — • Target creature gets +2/+0 until end of turn. • Target creature can't block this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rising Miasma | handled | All creatures get -2/-2 until end of turn. Awaken 3—{5}{B}{B} (If you cast this spell for {5}{B}{B}, also put three +1/+1 counters on target land you control an | the engine reads this text and performs it | Y/Y/- | not_tested |
| Roil Spout | handled | Put target creature on top of its owner's library. Awaken 4—{4}{W}{U} (If you cast this spell for {4}{W}{U}, also put four +1/+1 counters on target land you con | the engine reads this text and performs it | Y/Y/- | not_tested |
| Roil's Retribution | handled | Roil's Retribution deals 5 damage divided as you choose among any number of target attacking or blocking creatures. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rot Shambler | handled | Whenever another creature you control dies, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ruin Processor | handled | When you cast this spell, you may put a card an opponent owns from exile into that player's graveyard. If you do, you gain 5 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ruinous Path | handled | Destroy target creature or planeswalker. Awaken 4—{5}{B}{B} (If you cast this spell for {5}{B}{B}, also put four +1/+1 counters on target land you control and i | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rush of Ice | handled | Tap target creature. It doesn't untap during its controller's next untap step. Awaken 3—{4}{U} (If you cast this spell for {4}{U}, also put three +1/+1 counters | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sandstone Bridge | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Scatter to the Winds | handled | Counter target spell. Awaken 3—{4}{U}{U} (If you cast this spell for {4}{U}{U}, also put three +1/+1 counters on target land you control and it becomes a 0/0 El | the engine reads this text and performs it | Y/Y/- | not_tested |
| Scour from Existence | handled | Exile target permanent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Scythe Leopard | handled | Landfall — Whenever a land you control enters, this creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Seek the Wilds | handled | Look at the top four cards of your library. You may reveal a creature or land card from among them and put it into your hand. Put the rest on the bottom of your | the engine reads this text and performs it | Y/Y/- | not_tested |
| Serene Steward | handled | Whenever you gain life, you may pay {W}. If you do, put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shadow Glider | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Shambling Vent | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shatterskull Recruit | handled | Menace | machines/combat.py | Y/Y/- | not_tested |
| Skitterskin | handled | This creature can't block. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Smoldering Marsh | handled | This land enters tapped unless you control two or more basic lands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Snapping Gnarlid | handled | Landfall — Whenever a land you control enters, this creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spawning Bed | handled | {6}, {T}, Sacrifice this land: Create three 1/1 colorless Eldrazi Scion creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spell Shrivel | handled | Devoid (This card has no color.) Counter target spell unless its controller pays {4}. If that spell is countered this way, exile it instead of putting it into i | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stasis Snare | handled | When this enchantment enters, exile target creature an opponent controls until this enchantment leaves the battlefield. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Stone Haven Medic | handled | {W}, {T}: You gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stonefury | handled | Stonefury deals damage to target creature equal to the number of lands you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sure Strike | handled | Target creature gets +3/+0 and gains first strike until end of turn. (It deals combat damage before creatures without first strike.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Swell of Growth | handled | Target creature gets +2/+2 until end of turn. You may put a land card from your hand onto the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tajuru Beastmaster | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tajuru Stalwart | handled | Converge — This creature enters with a +1/+1 counter on it for each color of mana spent to cast it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tajuru Warcaller | handled | Rally — Whenever this creature or another Ally you control enters, creatures you control get +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tandem Tactics | handled | Up to two target creatures each get +1/+2 until end of turn. You gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Touch of the Void | handled | Devoid (This card has no color.) Touch of the Void deals 3 damage to any target. If a creature dealt damage this way would die this turn, exile it instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tunneling Geopede | handled | Landfall — Whenever a land you control enters, this creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Turn Against | handled | Devoid (This card has no color.) Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ugin's Insight | handled | Scry | no code needed | Y/Y/- | not_tested |
| Ulamog's Nullifier | handled | When this creature enters, you may put two cards your opponents own from exile into their owners' graveyards. If you do, counter target spell. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ulamog's Reclaimer | handled | When this creature enters, you may put a card an opponent owns from exile into that player's graveyard. If you do, return target instant or sorcery card from yo | the engine reads this text and performs it | Y/Y/- | not_tested |
| Valakut Invoker | handled | {8}: This creature deals 3 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Valakut Predator | handled | Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vestige of Emrakul | handled | Devoid | no code needed | Y/Y/- | not_tested |
| Void Attendant | handled | {1}{G}, Put a card an opponent owns from exile into that player's graveyard: Create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this token:  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Volcanic Upheaval | handled | Destroy target land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Voracious Null | handled | {1}{B}, Sacrifice another creature: Put two +1/+1 counters on this creature. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wave-Wing Elemental | handled | Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Windrider Patrol | handled | Whenever this creature deals combat damage to a player, scry 2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Woodland Wanderer | handled | Converge — This creature enters with a +1/+1 counter on it for each color of mana spent to cast it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Zulaport Cutthroat | handled | Whenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>27 cards</summary>

- Akoum Hellkite
- Aligned Hedron Network
- Blisterpod
- Canopy Vista
- Clutch of Currents
- Conduit of Ruin
- Dust Stalker
- Encircling Fissure
- Endless One
- Guul Draz Overseer
- Kiora, Master of the Depths
- Lithomancer's Focus
- Murk Strider
- Painful Truths
- Radiant Flames
- Roilmage's Trick
- Sanctum of Ugin
- Serpentine Spike
- Shrine of the Forsaken Gods
- Skyrider Elf
- Sunken Hollow
- Swarm Surge
- Tide Drifter
- Ulamog, the Ceaseless Hunger
- Unified Front
- Vampiric Rites
- Wasteland Strangler

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| ingest | 7 | Benthic Infiltrator, Culling Drone, Mist Intruder, Ruination Guide, Salvage Drone | bfz |
| Converge | 4 | Brilliant Spectrum, Bring to Light, Exert Influence, Infuse with the Elements | bfz |
| Landfall | 1 | Emeria Shepherd | bfz |
| Rally | 1 | Munda, Ambush Leader | bfz |
| +N: until end of turn, gideon becomes a N/N human soldier ally creature with indestructible that's still a planeswalker. prevent all damage that would be dealt  | 1 | Gideon, Ally of Zendikar | bfz |
| all creatures able to block ~ do so. | 1 | Breaker of Armies | bfz |
| as an additional cost to cast ~, reveal a colorless creature card from your hand. exile target creature if its power is less than or equal to the revealed card' | 1 | Titan's Presence | bfz |
| as ~ enters, you may put two cards your opponents own from exile into their owners' graveyards. if you do, ~ enters with four +N/+N counters on it. | 1 | Ulamog's Despoiler | bfz |
| at the beginning of your upkeep, sacrifice a creature. | 1 | Smothering Abomination | bfz |
| colorless spells you cast cost {M} less to cast. | 1 | Herald of Kozilek | bfz |
| devoid (~ has no color.) create two N/N colorless eldrazi scion creature tokens. they have "..." | 1 | Call the Scions | bfz |
| devoid (~ has no color.) exile target creature and target land. | 1 | Grip of Desolation | bfz |
| devoid (~ has no color.) exile target nonbasic land. search its controller's graveyard, hand, and library for any number of cards with the same name as that lan | 1 | Crumble to Dust | bfz |
| devoid (~ has no color.) target creature you control fights target creature an opponent controls. if the creature an opponent controls would die ~, exile it ins | 1 | Unnatural Aggression | bfz |
| devoid (~ has no color.) target player reveals their hand. you choose a card from it with mana value N or greater and exile that card. | 1 | Transgress the Mind | bfz |
| enchanted creature gets -N/-N and loses flying. | 1 | Tightening Coils | bfz |
| if damage would be dealt to ~ while it has a +N/+N counter on it, prevent that damage and remove a +N/+N counter from ~. | 1 | Undergrowth Champion | bfz |
| until end of turn, colorless creatures you control gain "..." | 1 | Gruesome Slaughter | bfz |
| when ~ enters, for each isolation counter on it, exile up to one target nonland permanent an opponent controls until ~ leaves the battlefield. | 1 | Quarantine Field | bfz |
| when ~ enters, target creature an opponent controls doesn"..."s next untap step. | 1 | Skyline Cascade | bfz |
| when ~ enters, you may look at the top five cards of your library. if you do, reveal up to one basic land card from among them, then put that card on top of you | 1 | Fertile Thicket | bfz |
| whenever a land an opponent controls enters, that player exiles the top two cards of their library and you draw two cards. | 1 | Sire of Stagnation | bfz |
| whenever drana deals combat damage to a player, put a +N/+N counter on each attacking creature you control. | 1 | Drana, Liberator of Malakir | bfz |
| whenever equipped creature attacks, you may return a land you control to its owner's hand. if you do, the creature gets +N/+N until end of turn. | 1 | Slab Hammer | bfz |
| whenever equipped creature becomes blocked by one or more colorless creatures, it gains deathtouch until end of turn. | 1 | Hedron Blade | bfz |
| whenever you cast an instant or sorcery spell that targets only zada, copy that spell for each other creature you control that the spell could target. each copy | 1 | Zada, Hedron Grinder | bfz |
| whenever ~ attacks, defending player exiles two permanents they control. | 1 | Bane of Bala Ged | bfz |
| whenever ~ attacks, defending player loses N life. | 1 | Silent Skimmer | bfz |
| your opponents can't cast spells with even mana values. | 1 | Void Winnower | bfz |
| {M}{M}, sacrifice another colorless creature: ~ deals damage equal to the sacrificed creature's power to any target. | 1 | Barrage Tyrant | bfz |
| {M}{M}{M}: draw a card. each opponent exiles the top card of their library. | 1 | Fathom Feeder | bfz |
| ~ attacks each combat if able unless you control another ally. | 1 | Reckless Cohort | bfz |
| ~ can't be blocked by eldrazi scions. | 1 | Kor Castigator | bfz |

## Notes



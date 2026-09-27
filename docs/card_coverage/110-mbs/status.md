# Mirrodin Besieged (mbs)

- Expansion: 110
- Set code: `mbs`
- Release date: 2011-02-04
- Cards in scope (Modern/Pioneer/Standard-legal): 142

## Legality

| Format | Legal cards |
|---|---|
| Modern | 142 |
| Pioneer | 7 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 11 | 7.7% |
| Works (untested) | 88 | 62.0% |
| Partial (unaudited) | 7 | 4.9% |
| Not working | 36 | 25.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ardent Recruit | silent | Metalcraft — This creature gets +2/+2 as long as you control three or more artifacts. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Banishment Decree | silent | Put target artifact, creature, or enchantment on top of its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bonehoard | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Choking Fumes | silent | Put a -1/-1 counter on each attacking creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Concussive Bolt | silent | Concussive Bolt deals 4 damage to target player or planeswalker. Metalcraft — If you control three or more artifacts, creatures controlled by that player or by  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Contested War Zone | silent | Whenever a creature deals combat damage to you, that creature's controller gains control of this land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Copper Carapace | silent | Equipped creature gets +2/+2 and can't block. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cryptoplasm | silent | At the beginning of your upkeep, you may have this creature become a copy of another target creature, except it has this ability. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Decimator Web | silent | {4}, {T}: Target opponent loses 2 life, gets a poison counter, then mills six cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Distant Memories | silent | Search your library for a card, exile it, then shuffle. Any opponent may have you put that card into your hand. If no player does, you draw three cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Flayer Husk | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Galvanoth | silent | At the beginning of your upkeep, you may look at the top card of your library. You may cast it without paying its mana cost if it's an instant or sorcery spell. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hero of Oxid Ridge | silent | Whenever this creature attacks, creatures with power 1 or less can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Leonin Relic-Warder | silent | When this creature leaves the battlefield, return the exiled card to the battlefield under its owner's control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Magnetic Mine | silent | Whenever another artifact is put into a graveyard from the battlefield, this artifact deals 2 damage to that artifact's controller. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mirrorworks | silent | Whenever another nontoken artifact you control enters, you may pay {2}. If you do, create a token that's a copy of that artifact. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mitotic Manipulation | silent | Look at the top seven cards of your library. You may put one of those cards onto the battlefield if it has the same name as a permanent. Put the rest on the bot | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mortarpod | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Phyrexian Rebirth | silent | Destroy all creatures, then create an X/X colorless Phyrexian Horror artifact creature token, where X is the number of creatures destroyed this way. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Praetor's Counsel | silent | Return all cards from your graveyard to your hand. Exile Praetor's Counsel. You have no maximum hand size for the rest of the game. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Psychosis Crawler | silent | Psychosis Crawler's power and toughness are each equal to the number of cards in your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rally the Forces | silent | Attacking creatures get +1/+0 and gain first strike until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Razorfield Rhino | silent | Metalcraft — This creature gets +2/+2 as long as you control three or more artifacts. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Silverskin Armor | silent | Equipped creature gets +1/+1 and is an artifact in addition to its other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Skinwing | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Spin Engine | silent | {R}: Target creature can't block this creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spire Serpent | silent | Metalcraft — As long as you control three or more artifacts, this creature gets +2/+2 and can attack as though it didn't have defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Strandwalker | silent | Living weapon | no machine in the engine executes this keyword | Y/-/- | not_working |
| Tezzeret, Agent of Bolas | silent | −1: Target artifact becomes an artifact creature with base power and toughness 5/5. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Victory's Herald | silent | Whenever this creature attacks, attacking creatures gain flying and lifelink until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Burn the Impure | notice | Burn the Impure deals 3 damage to target creature. If that creature has infect, Burn the Impure deals 3 damage to that creature's controller. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Gore Vassal | notice | Sacrifice this creature: Put a -1/-1 counter on target creature. Then if that creature's toughness is 1 or greater, regenerate it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Gruesome Encore | notice | Put target creature card from an opponent's graveyard onto the battlefield under your control. It gains haste. Exile it at the beginning of the next end step. I | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Pistus Strike | notice | Destroy target creature with flying. Its controller gets a poison counter. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Vedalken Anatomist | notice | {2}{U}, {T}: Put a -1/-1 counter on target creature. You may tap or untap that creature. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Virulent Wound | notice | Put a -1/-1 counter on target creature. When that creature dies this turn, its controller gets a poison counter. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Blightsteel Colossus | unaudited | If Blightsteel Colossus would be put into a graveyard from anywhere, reveal Blightsteel Colossus and shuffle it into its owner's library instead. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Kemba's Legion | unaudited | This creature can block an additional creature each combat for each Equipment attached to this creature. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Phyrexian Hydra | unaudited | If damage would be dealt to this creature, prevent that damage. Put a -1/-1 counter on this creature for each 1 damage prevented this way. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Shimmer Myr | unaudited | You may cast artifact spells as though they had flash. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Signal Pest | unaudited | This creature can't be blocked except by creatures with flying or reach. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Sphere of the Suns | unaudited | This artifact enters tapped and with three charge counters on it. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Training Drone | unaudited | This creature can't attack or block unless it's equipped. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Black Sun's Zenith | handled | Put X -1/-1 counters on each creature. Shuffle Black Sun's Zenith into its owner's library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bladed Sentinel | handled | {W}: This creature gains vigilance until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blightwidow | handled | Reach | machines/combat.py | Y/-/- | not_tested |
| Blisterstick Shaman | handled | When this creature enters, it deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blue Sun's Zenith | handled | Target player draws X cards. Shuffle Blue Sun's Zenith into its owner's library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Brass Squire | handled | {T}: Attach target Equipment you control to target creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Caustic Hound | handled | When this creature dies, each player loses 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Consecrated Sphinx | handled | Whenever an opponent draws a card, you may draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Core Prowler | handled | When this creature dies, proliferate. | the engine reads this text and performs it | Y/-/- | not_tested |
| Corrupted Conscience | handled | You control enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Creeping Corrosion | handled | Destroy all artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crush | handled | Destroy target noncreature artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Darksteel Plate | handled | Equipped creature has indestructible. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dross Ripper | handled | {2}{B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fangren Marauder | handled | Whenever an artifact is put into a graveyard from the battlefield, you may gain 5 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flensermite | handled | Lifelink | machines/combat.py | Y/-/- | not_tested |
| Flesh-Eater Imp | handled | Sacrifice a creature: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Frantic Salvage | handled | Put any number of target artifact cards from your graveyard on top of your library. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Glissa's Courier | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Glissa, the Traitor | handled | Whenever a creature an opponent controls dies, you may return target artifact card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gnathosaur | handled | Sacrifice an artifact: This creature gains trample until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Go for the Throat | handled | Destroy target nonartifact creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Goblin Wardriver | handled | Battle Cry | machines/keywords.py | Y/-/- | not_tested |
| Gust-Skimmer | handled | {U}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hellkite Igniter | handled | {1}{R}: This creature gets +X/+0 until end of turn, where X is the number of artifacts you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hero of Bladehold | handled | Whenever this creature attacks, create two 1/1 white Soldier creature tokens that are tapped and attacking. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hexplate Golem | handled |  |  | Y/-/- | not_tested |
| Horrifying Revelation | handled | Target player discards a card, then mills a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Inkmoth Nexus | handled | {1}: This land becomes a 1/1 Phyrexian Blinkmoth artifact creature with flying and infect until end of turn. It's still a land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Into the Core | handled | Exile two target artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Koth's Courier | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Kuldotha Flamefiend | handled | When this creature enters, you may sacrifice an artifact. If you do, this creature deals 4 damage divided as you choose among any number of targets. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kuldotha Ringleader | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Loxodon Partisan | handled | Battle Cry | machines/keywords.py | Y/-/- | not_tested |
| Lumengrid Gargoyle | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Massacre Wurm | handled | When this creature enters, creatures your opponents control get -2/-2 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Master's Call | handled | Create two 1/1 colorless Myr artifact creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Metallic Mastery | handled | Gain control of target artifact until end of turn. Untap that artifact. It gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mirran Crusader | handled | Protection | models/game.py | Y/-/- | not_tested |
| Mirran Mettle | handled | Target creature gets +2/+2 until end of turn. Metalcraft — That creature gets +4/+4 until end of turn instead if you control three or more artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mirran Spy | handled | Whenever you cast an artifact spell, you may untap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Morbid Plunder | handled | Return up to two target creature cards from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Myr Sire | handled | When this creature dies, create a 1/1 colorless Phyrexian Myr artifact creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Myr Turbine | handled | {T}: Create a 1/1 colorless Myr artifact creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Myr Welder | handled | Imprint — {T}: Exile target artifact card from a graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nested Ghoul | handled | Whenever a source deals damage to this creature, create a 2/2 black Phyrexian Zombie creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Neurok Commando | handled | Whenever this creature deals combat damage to a player, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Oculus | handled | When this creature dies, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ogre Resister | handled |  |  | Y/-/- | not_tested |
| Peace Strider | handled | When this creature enters, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyresis | handled | Enchanted creature has infect. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Crusader | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Phyrexian Digester | handled | Infect | machines/combat.py | Y/-/- | not_tested |
| Phyrexian Juggernaut | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Vatmother | handled | At the beginning of your upkeep, you get a poison counter. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pierce Strider | handled | When this creature enters, target opponent loses 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Piston Sledge | handled | When this Equipment enters, attach it to target creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Plague Myr | handled | Infect | machines/combat.py | Y/-/- | not_tested |
| Plaguemaw Beast | handled | {T}, Sacrifice a creature: Proliferate. | the engine reads this text and performs it | Y/-/- | not_tested |
| Priests of Norn | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Quicksilver Geyser | handled | Return up to two target nonland permanents to their owners' hands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Quilled Slagwurm | handled |  |  | Y/-/- | not_tested |
| Red Sun's Zenith | handled | Red Sun's Zenith deals X damage to any target. If a creature dealt damage this way would die this turn, exile it instead. Shuffle Red Sun's Zenith into its owne | the engine reads this text and performs it | Y/-/- | not_tested |
| Rot Wolf | handled | Whenever a creature dealt damage by Rot Wolf this turn dies, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rusted Slasher | handled | Sacrifice an artifact: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sangromancer | handled | Whenever a creature an opponent controls dies, you may gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scourge Servant | handled | Infect | machines/combat.py | Y/-/- | not_tested |
| Serum Raker | handled | When this creature dies, each player discards a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shriekhorn | handled | This artifact enters with three charge counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Slagstorm | handled | Choose one — • Slagstorm deals 3 damage to each creature. • Slagstorm deals 3 damage to each player. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Spine of Ish Sah | handled | When this artifact enters, destroy target permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spiraling Duelist | handled | Metalcraft — This creature has double strike as long as you control three or more artifacts. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spread the Sickness | handled | Destroy target creature, then proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Steel Sabotage | handled | Choose one — • Counter target artifact spell. • Return target artifact to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tangle Hulk | handled | {2}{G}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tangle Mantis | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Thrun, the Last Troll | handled | This spell can't be countered. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tine Shrike | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Titan Forge | handled | {3}, {T}: Put a charge counter on this artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Treasure Mage | handled | When this creature enters, you may search your library for an artifact card with mana value 6 or greater, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Turn the Tide | handled | Creatures your opponents control get -2/-0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Unnatural Predation | handled | Target creature gets +1/+1 and gains trample until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vedalken Infuser | handled | At the beginning of your upkeep, you may put a charge counter on target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viridian Claw | handled | Equipped creature gets +1/+0 and has first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viridian Corrupter | handled | When this creature enters, destroy target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viridian Emissary | handled | When this creature dies, you may search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vivisection | handled | As an additional cost to cast this spell, sacrifice a creature. Draw three cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| White Sun's Zenith | handled | Create X 2/2 white Cat creature tokens. Shuffle White Sun's Zenith into its owner's library. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>11 cards</summary>

- Accorder Paladin
- Fuel for the Cause
- Green Sun's Zenith
- Ichor Wellspring
- Knowledge Pool
- Lead the Stampede
- Melira's Keepers
- Phyrexian Revoker
- Septic Rats
- Sword of Feast and Famine
- Thopter Assembly

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| living weapon | 5 | Bonehoard, Flayer Husk, Mortarpod, Skinwing, Strandwalker | mbs |
| Metalcraft | 3 | Ardent Recruit, Razorfield Rhino, Spire Serpent | mbs |
| at the beginning of your upkeep, you may have ~ become a copy of another target creature, except it has ~. | 1 | Cryptoplasm | mbs |
| at the beginning of your upkeep, you may look at the top card of your library. you may cast it without paying its mana cost if it's an instant or sorcery spell. | 1 | Galvanoth | mbs |
| attacking creatures get +N/+N and gain first strike until end of turn. | 1 | Rally the Forces | mbs |
| destroy all creatures, then create an N/N colorless phyrexian horror artifact creature token, where N is the number of creatures destroyed ~. | 1 | Phyrexian Rebirth | mbs |
| destroy target creature with flying. its controller gets a poison counter. | 1 | Pistus Strike | mbs |
| equipped creature gets +N/+N and can't block. | 1 | Copper Carapace | mbs |
| equipped creature gets +N/+N and is an artifact in addition to its other types. | 1 | Silverskin Armor | mbs |
| if damage would be dealt to ~, prevent that damage. put a -N/-N counter on ~ for each N damage prevented ~. | 1 | Phyrexian Hydra | mbs |
| if ~ would be put into a graveyard from anywhere, reveal ~ and shuffle it into its owner's library instead. | 1 | Blightsteel Colossus | mbs |
| look at the top seven cards of your library. you may put one of those cards onto the battlefield if it has the same name as a permanent. put the rest on the bot | 1 | Mitotic Manipulation | mbs |
| put a -N/-N counter on each attacking creature. | 1 | Choking Fumes | mbs |
| put a -N/-N counter on target creature. when that creature dies ~, its controller gets a poison counter. | 1 | Virulent Wound | mbs |
| put target artifact, creature, or enchantment on top of its owner's library. | 1 | Banishment Decree | mbs |
| put target creature card from an opponent's graveyard onto the battlefield under your control. it gains haste. exile it at the beginning of the next end step. i | 1 | Gruesome Encore | mbs |
| return all cards from your graveyard to your hand. exile ~. you have no maximum hand size for the rest of the game. | 1 | Praetor's Counsel | mbs |
| sacrifice ~: put a -N/-N counter on target creature. then if that creature's toughness is N or greater, regenerate it. | 1 | Gore Vassal | mbs |
| search your library for a card, exile it, then shuffle. any opponent may have you put that card into your hand. if no player does, you draw three cards. | 1 | Distant Memories | mbs |
| when ~ leaves the battlefield, return the exiled card to the battlefield under its owner's control. | 1 | Leonin Relic-Warder | mbs |
| whenever a creature deals combat damage to you, that creature's controller gains control of ~. | 1 | Contested War Zone | mbs |
| whenever another artifact is put into a graveyard from the battlefield, ~ deals N damage to that artifact's controller. | 1 | Magnetic Mine | mbs |
| whenever another nontoken artifact you control enters, you may pay {M}. if you do, create a token that's a copy of that artifact. | 1 | Mirrorworks | mbs |
| whenever ~ attacks, attacking creatures gain flying and lifelink until end of turn. | 1 | Victory's Herald | mbs |
| whenever ~ attacks, creatures with power N or less can't block ~. | 1 | Hero of Oxid Ridge | mbs |
| you may cast artifact spells as though they had flash. | 1 | Shimmer Myr | mbs |
| {M}, {M}: target opponent loses N life, gets a poison counter, then mills six cards. | 1 | Decimator Web | mbs |
| {M}: target creature can't block ~ ~. | 1 | Spin Engine | mbs |
| {M}{M}, {M}: put a -N/-N counter on target creature. you may tap or untap that creature. | 1 | Vedalken Anatomist | mbs |
| ~ can block an additional creature each combat for each equipment attached to ~. | 1 | Kemba's Legion | mbs |
| ~ can"..."s equipped. | 1 | Training Drone | mbs |
| ~ can't be blocked except by creatures with flying or reach. | 1 | Signal Pest | mbs |
| ~ deals N damage to target creature. if that creature has infect, ~ deals N damage to that creature's controller. | 1 | Burn the Impure | mbs |
| ~ deals N damage to target player or planeswalker. metalcraft — if you control three or more artifacts, creatures controlled by that player or by that planeswal | 1 | Concussive Bolt | mbs |
| ~ enters tapped and with three charge counters on it. | 1 | Sphere of the Suns | mbs |
| ~'s power and toughness are each equal to the number of cards in your hand. | 1 | Psychosis Crawler | mbs |
| −N: target artifact becomes an artifact creature with base power and toughness N/N. | 1 | Tezzeret, Agent of Bolas | mbs |

## Notes



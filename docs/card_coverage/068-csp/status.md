# Coldsnap (csp)

- Expansion: 068
- Set code: `csp`
- Release date: 2006-07-21
- Cards in scope (Modern/Pioneer/Standard-legal): 143

## Legality

| Format | Legal cards |
|---|---|
| Modern | 143 |
| Pioneer | 2 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 38 | 26.6% |
| Works (untested) | 69 | 48.3% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 36 | 25.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Adarkar Valkyrie | silent | {T}: When target creature other than this creature dies this turn, return that card to the battlefield under your control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Arcum Dagsson | silent | {T}: Target artifact creature's controller sacrifices it. That player may search their library for a noncreature artifact card, put it onto the battlefield, the | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Balduvian Fallen | silent | Whenever this creature's cumulative upkeep is paid, it gets +1/+0 until end of turn for each {B} or {R} spent this way. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Brooding Saurian | silent | At the beginning of each end step, each player gains control of all nontoken permanents they own. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Commandeer | silent | You may exile two blue cards from your hand rather than pay this spell's mana cost. Gain control of target noncreature spell. You may choose new targets for it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Controvert | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Counterbalance | silent | Whenever an opponent casts a spell, you may reveal the top card of your library. If you do, counter that spell if it has the same mana value as the revealed car | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Darien, King of Kjeldor | silent | Whenever you're dealt damage, you may create that many 1/1 white Soldier creature tokens. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Dark Depths | silent | When Dark Depths has no ice counters on it, sacrifice it. If you do, create Marit Lage, a legendary 20/20 black Avatar creature token with flying and indestruct | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Fury of the Horde | silent | You may exile two red cards from your hand rather than pay this spell's mana cost. Untap all creatures that attacked this turn. After this main phase, there is  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Garza's Assassin | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Grim Harvest | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Hibernation's End | silent | Whenever you pay this enchantment's cumulative upkeep, you may search your library for a creature card with mana value equal to the number of age counters on th | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Icefall | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Jester's Scepter | silent | {2}, {T}, Put a card exiled with this artifact into its owner's graveyard: Counter target spell if it has the same name as that card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jokulmorder | silent | When this creature enters, sacrifice it unless you sacrifice five lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Karplusan Minotaur | silent | Whenever you win a coin flip, this creature deals 1 damage to any target. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Kjeldoran Gargoyle | silent | Whenever this creature deals damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Krovikan Rot | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Resize | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Rimehorn Aurochs | silent | {2}{S}: Target creature blocks target creature this turn if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rune Snag | silent | Counter target spell unless its controller pays {2} plus an additional {2} for each card named Rune Snag in each graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scrying Sheets | silent | {1}{S}, {T}: Look at the top card of your library. If that card is snow, you may reveal it and put it into your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shape of the Wiitigo | silent | At the beginning of your upkeep, put a +1/+1 counter on enchanted creature if it attacked or blocked since your last upkeep. Otherwise, remove a +1/+1 counter f | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sun's Bounty | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Surging Aether | silent | Ripple | no machine in the engine executes this keyword | Y/-/- | not_working |
| Surging Dementia | silent | Ripple | no machine in the engine executes this keyword | Y/-/- | not_working |
| Surging Flame | silent | Ripple | no machine in the engine executes this keyword | Y/-/- | not_working |
| Surging Might | silent | Ripple | no machine in the engine executes this keyword | Y/-/- | not_working |
| Surging Sentinels | silent | Ripple | no machine in the engine executes this keyword | Y/-/- | not_working |
| Tamanoa | silent | Whenever a noncreature source you control deals damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ursine Fylgja | silent | Remove a healing counter from this creature: Prevent the next 1 damage that would be dealt to this creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Woolly Razorback | silent | As long as this creature has an ice counter on it, prevent all combat damage it would deal and it has defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blizzard Specter | notice | Whenever this creature deals combat damage to a player, choose one — • That player returns a permanent they control to its owner's hand. • That player discards  | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Ohran Viper | notice | Whenever this creature deals combat damage to a creature, destroy that creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Thermal Flux | notice | Choose one — • Target nonsnow permanent becomes snow until end of turn. • Target snow permanent isn't snow until end of turn. Draw a card at the beginning of th | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Arctic Flats | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Aurochs Herd | handled | When this creature enters, you may search your library for an Aurochs card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Balduvian Frostwaker | handled | {U}, {T}: Target snow land becomes a 2/2 blue Elemental creature with flying. It's still a land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boreal Centaur | handled | {S}: This creature gets +1/+1 until end of turn. Activate only once each turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boreal Druid | handled |  |  | Y/-/- | not_tested |
| Boreal Griffin | handled | {S}: This creature gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boreal Shelf | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bull Aurochs | handled | Whenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Aurochs. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chill to the Bone | handled | Destroy target nonsnow creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chilling Shade | handled | {S}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Coldsteel Heart | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cryoclasm | handled | Destroy target Plains or Island. Cryoclasm deals 3 damage to that land's controller. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deathmark | handled | Destroy target green or white creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Deepfire Elemental | handled | {X}{X}{1}: Destroy target artifact or creature with mana value X. | the engine reads this text and performs it | Y/-/- | not_tested |
| Disciple of Tevesh Szat | handled | {T}: Target creature gets -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drelnoch | handled | Whenever this creature becomes blocked, you may draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Earthen Goo | handled | This creature gets +1/+1 for each age counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Field Marshal | handled | Other Soldier creatures get +1/+1 and have first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flashfreeze | handled | Counter target red or green spell. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Frost Marsh | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Frost Raptor | handled | {S}{S}: This creature gains shroud until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Frostweb Spider | handled | Whenever this creature blocks a creature with flying, put a +1/+1 counter on this creature at end of combat. | the engine reads this text and performs it | Y/-/- | not_tested |
| Garza Zol, Plague Queen | handled | Whenever a creature dealt damage by Garza Zol this turn dies, put a +1/+1 counter on Garza Zol. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gelid Shackles | handled | Enchanted creature can't block, and its activated abilities can't be activated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Glacial Plating | handled | Enchanted creature gets +3/+3 for each age counter on this Aura. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Rimerunner | handled | {T}: Target creature can't block this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Greater Stone Spirit | handled | This creature can't be blocked by creatures with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gristle Grinner | handled | Whenever a creature dies, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gutless Ghoul | handled | {1}, Sacrifice a creature: You gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Heidar, Rimewind Master | handled | {2}, {T}: Return target permanent to its owner's hand. Activate only if you control four or more snow permanents. | the engine reads this text and performs it | Y/-/- | not_tested |
| Highland Weald | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Into the North | handled | Search your library for a snow land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jötun Grunt | handled | Cumulative upkeep | machines/keywords.py | Y/-/- | not_tested |
| Jötun Owl Keeper | handled | When this creature dies, create a 1/1 white Bird creature token with flying for each age counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kjeldoran Outrider | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Krovikan Mist | handled | Krovikan Mist's power and toughness are each equal to the number of Illusions on the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Krovikan Whispers | handled | You control enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lightning Serpent | handled | This creature enters with X +1/+0 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magmatic Core | handled | At the beginning of your end step, this enchantment deals X damage divided as you choose among any number of target creatures, where X is the number of age coun | the engine reads this text and performs it | Y/-/- | not_tested |
| Martyr of Bones | handled | {1}, Reveal X black cards from your hand, Sacrifice this creature: Exile up to X target cards from a single graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Martyr of Spores | handled | {1}, Reveal X green cards from your hand, Sacrifice this creature: Target creature gets +X/+X until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mouth of Ronom | handled | {4}{S}, {T}, Sacrifice this land: It deals 4 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ohran Yeti | handled | {2}{S}: Target snow creature gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Orcish Bloodpainter | handled | {T}, Sacrifice a creature: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Perilous Research | handled | Draw two cards, then sacrifice a permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phobian Phantasm | handled | Cumulative upkeep | machines/keywords.py | Y/-/- | not_tested |
| Phyrexian Etchings | handled | At the beginning of your end step, draw a card for each age counter on this enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Ironfoot | handled | This creature doesn't untap during your untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Snowcrusher | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Soulgorger | handled | Cumulative upkeep | machines/keywords.py | Y/-/- | not_tested |
| Rime Transfusion | handled | Enchanted creature gets +2/+1 and has "{S}: This creature can't be blocked this turn except by snow creatures." | the engine reads this text and performs it | Y/-/- | not_tested |
| Rimebound Dead | handled | {S}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rimewind Taskmage | handled | {1}, {T}: You may tap or untap target permanent. Activate only if you control four or more snow permanents. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ronom Unicorn | handled | Sacrifice this creature: Destroy target enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sek'Kuar, Deathkeeper | handled | Whenever another nontoken creature you control dies, create a 3/1 black and red Graveborn creature token with haste. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sheltering Ancient | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Simian Brawler | handled | Discard a land card: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sound the Call | handled | Create a 1/1 green Wolf creature token. It has "This token gets +1/+1 for each card named Sound the Call in each graveyard." | the engine reads this text and performs it | Y/-/- | not_tested |
| Squall Drifter | handled | {W}, {T}: Tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Steam Spitter | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stromgald Crusader | handled | {B}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sunscour | handled | You may exile two white cards from your hand rather than pay this spell's mana cost. Destroy all creatures. | the engine reads this text and performs it | Y/-/- | not_tested |
| Survivor of the Unseen | handled | {T}: Draw two cards, then put a card from your hand on top of your library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thermopod | handled | {S}: This creature gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tresserhorn Sinks | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Shards | handled | Cumulative upkeep | machines/keywords.py | Y/-/- | not_tested |
| White Shield Crusader | handled | {W}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zombie Musher | handled | {S}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zur the Enchanter | handled | Whenever Zur attacks, you may search your library for an enchantment card with mana value 3 or less, put it onto the battlefield, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>38 cards</summary>

- Adarkar Windform
- Allosaurus Rider
- Balduvian Warlord
- Braid of Fire
- Cover of Winter
- Diamond Faerie
- Feast of Flesh
- Freyalise's Radiance
- Goblin Furrier
- Haakon, Stromgald Scourge
- Herald of Leshrac
- Karplusan Strider
- Kjeldoran Javelineer
- Kjeldoran War Cry
- Krovikan Scoundrel
- Lightning Storm
- Luminesce
- Martyr of Ashes
- Martyr of Sands
- Mishra's Bauble
- Mystic Melting
- Panglacial Wurm
- Rimefeather Owl
- Rimescale Dragon
- Rimewind Cryomancer
- Rite of Flame
- Ronom Hulk
- Ronom Serpent
- Skred
- Soul Spike
- Stalking Yeti
- Swift Maneuver
- Thrumming Stone
- Tresserhorn Skyknight
- Vanish into Memory
- Vexing Sphinx
- Void Maw
- Wilderness Elemental

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| recover | 7 | Controvert, Garza's Assassin, Grim Harvest, Icefall, Krovikan Rot | csp |
| ripple | 5 | Surging Aether, Surging Dementia, Surging Flame, Surging Might, Surging Sentinels | csp |
| Choose one | 1 | Thermal Flux | csp |
| as long as ~ has an ice counter on it, prevent all combat damage it would deal and it has defender. | 1 | Woolly Razorback | csp |
| at the beginning of each end step, each player gains control of all nontoken permanents they own. | 1 | Brooding Saurian | csp |
| at the beginning of your upkeep, put a +N/+N counter on enchanted creature if it attacked or blocked since your last upkeep. otherwise, remove a +N/+N counter f | 1 | Shape of the Wiitigo | csp |
| counter target spell unless its controller pays {M} plus an additional {M} for each card named ~ in each graveyard. | 1 | Rune Snag | csp |
| remove a healing counter from ~: prevent the next N damage that would be dealt to ~ ~. | 1 | Ursine Fylgja | csp |
| when ~ enters, sacrifice it unless you sacrifice five lands. | 1 | Jokulmorder | csp |
| when ~ has no ice counters on it, sacrifice it. if you do, create marit lage, a legendary N/N black avatar creature token with flying and indestructible. | 1 | Dark Depths | csp |
| whenever a noncreature source you control deals damage, you gain that much life. | 1 | Tamanoa | csp |
| whenever an opponent casts a spell, you may reveal the top card of your library. if you do, counter that spell if it has the same mana value as the revealed car | 1 | Counterbalance | csp |
| whenever you pay ~ cumulative upkeep, you may search your library for a creature card with mana value equal to the number of age counters on ~, put it onto the  | 1 | Hibernation's End | csp |
| whenever you win a coin flip, ~ deals N damage to any target. | 1 | Karplusan Minotaur | csp |
| whenever you're dealt damage, you may create that many N/N white soldier creature tokens. | 1 | Darien, King of Kjeldor | csp |
| whenever ~ cumulative upkeep is paid, it gets +N/+N until end of turn for each {M} or {M} spent ~. | 1 | Balduvian Fallen | csp |
| whenever ~ deals combat damage to a creature, destroy that creature at end of combat. | 1 | Ohran Viper | csp |
| whenever ~ deals combat damage to a player, choose one — • that player returns a permanent they control to its owner's hand. • that player discards a card. | 1 | Blizzard Specter | csp |
| whenever ~ deals damage, you gain that much life. | 1 | Kjeldoran Gargoyle | csp |
| you may exile two blue cards from your hand rather than pay ~ mana cost. gain control of target noncreature spell. you may choose new targets for it. (if that s | 1 | Commandeer | csp |
| you may exile two red cards from your hand rather than pay ~ mana cost. untap all creatures that attacked ~. after ~ phase, there is an additional combat phase  | 1 | Fury of the Horde | csp |
| {M}, {M}, put a card exiled with ~ into its owner's graveyard: counter target spell if it has the same name as that card. | 1 | Jester's Scepter | csp |
| {M}: target artifact creature's controller sacrifices it. that player may search their library for a noncreature artifact card, put it onto the battlefield, the | 1 | Arcum Dagsson | csp |
| {M}: when target creature other than ~ dies ~, return that card to the battlefield under your control. | 1 | Adarkar Valkyrie | csp |
| {M}{M}, {M}: look at the top card of your library. if that card is snow, you may reveal it and put it into your hand. | 1 | Scrying Sheets | csp |
| {M}{M}: target creature blocks target creature ~ if able. | 1 | Rimehorn Aurochs | csp |

## Notes



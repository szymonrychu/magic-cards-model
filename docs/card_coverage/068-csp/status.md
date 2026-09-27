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
| Tested | 8 | 5.6% |
| Works (untested) | 58 | 40.6% |
| Partial (unaudited) | 13 | 9.1% |
| Not working | 64 | 44.8% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Adarkar Valkyrie | silent | {T}: When target creature other than this creature dies this turn, return that card to the battlefield under your control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Adarkar Windform | silent | {1}{S}: Target creature loses flying until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Arcum Dagsson | silent | {T}: Target artifact creature's controller sacrifices it. That player may search their library for a noncreature artifact card, put it onto the battlefield, the | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Aurochs Herd | silent | Whenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Aurochs. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Balduvian Fallen | silent | Whenever this creature's cumulative upkeep is paid, it gets +1/+0 until end of turn for each {B} or {R} spent this way. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Balduvian Frostwaker | silent | {U}, {T}: Target snow land becomes a 2/2 blue Elemental creature with flying. It's still a land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Balduvian Warlord | silent | {T}: Remove target blocking creature from combat. Creatures it was blocking that hadn't become blocked by another creature this combat become unblocked, then it | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Brooding Saurian | silent | At the beginning of each end step, each player gains control of all nontoken permanents they own. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bull Aurochs | silent | Whenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Aurochs. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Commandeer | silent | You may exile two blue cards from your hand rather than pay this spell's mana cost. Gain control of target noncreature spell. You may choose new targets for it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Controvert | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Counterbalance | silent | Whenever an opponent casts a spell, you may reveal the top card of your library. If you do, counter that spell if it has the same mana value as the revealed car | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Darien, King of Kjeldor | silent | Whenever you're dealt damage, you may create that many 1/1 white Soldier creature tokens. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Dark Depths | silent | When Dark Depths has no ice counters on it, sacrifice it. If you do, create Marit Lage, a legendary 20/20 black Avatar creature token with flying and indestruct | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Diamond Faerie | silent | {1}{S}: Snow creatures you control get +1/+1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Feast of Flesh | silent | Feast of Flesh deals X damage to target creature and you gain X life, where X is 1 plus the number of cards named Feast of Flesh in all graveyards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Field Marshal | silent | Other Soldier creatures get +1/+1 and have first strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fury of the Horde | silent | You may exile two red cards from your hand rather than pay this spell's mana cost. Untap all creatures that attacked this turn. After this main phase, there is  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Garza's Assassin | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Glacial Plating | silent | Enchanted creature gets +3/+3 for each age counter on this Aura. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grim Harvest | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Herald of Leshrac | silent | When this creature leaves the battlefield, each player gains control of each land they own that you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hibernation's End | silent | Whenever you pay this enchantment's cumulative upkeep, you may search your library for a creature card with mana value equal to the number of age counters on th | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Icefall | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Jester's Scepter | silent | When this artifact enters, exile the top five cards of target player's library face down. You may look at those cards for as long as they remain exiled. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jokulmorder | silent | When this creature enters, sacrifice it unless you sacrifice five lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Karplusan Minotaur | silent | Whenever you win a coin flip, this creature deals 1 damage to any target. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Kjeldoran Gargoyle | silent | Whenever this creature deals damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Krovikan Mist | silent | Krovikan Mist's power and toughness are each equal to the number of Illusions on the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Krovikan Rot | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Lightning Storm | silent | Lightning Storm deals X damage to any target, where X is 3 plus the number of charge counters on Lightning Storm. Discard a land card: Put two charge counters o | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Luminesce | silent | Prevent all damage that black sources and red sources would deal this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Magmatic Core | silent | At the beginning of your end step, this enchantment deals X damage divided as you choose among any number of target creatures, where X is the number of age coun | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Martyr of Bones | silent | {1}, Reveal X black cards from your hand, Sacrifice this creature: Exile up to X target cards from a single graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Perilous Research | silent | Draw two cards, then sacrifice a permanent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Phobian Phantasm | silent | Fear | no machine in the engine executes this keyword | Y/-/- | not_working |
| Resize | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Rimefeather Owl | silent | Rimefeather Owl's power and toughness are each equal to the number of snow permanents on the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rimehorn Aurochs | silent | Whenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Aurochs. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rite of Flame | silent | Add {R}{R}, then add {R} for each card named Rite of Flame in each graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ronom Serpent | silent | When you control no snow lands, sacrifice this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Rune Snag | silent | Counter target spell unless its controller pays {2} plus an additional {2} for each card named Rune Snag in each graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scrying Sheets | silent | {1}{S}, {T}: Look at the top card of your library. If that card is snow, you may reveal it and put it into your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shape of the Wiitigo | silent | When this Aura enters, put six +1/+1 counters on enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Skred | silent | Skred deals damage to target creature equal to the number of snow permanents you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stalking Yeti | silent | When this creature enters, if it's on the battlefield, it deals damage equal to its power to target creature an opponent controls and that creature deals damage | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
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
| Earthen Goo | notice | This creature gets +1/+1 for each age counter on it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Frostweb Spider | notice | Whenever this creature blocks a creature with flying, put a +1/+1 counter on this creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Kjeldoran War Cry | notice | Creatures you control get +X/+X until end of turn, where X is 1 plus the number of cards named Kjeldoran War Cry in all graveyards. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Mystic Melting | notice | Destroy target artifact or enchantment. Draw a card at the beginning of the next turn's upkeep. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Ohran Viper | notice | Whenever this creature deals combat damage to a creature, destroy that creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Swift Maneuver | notice | Prevent the next 2 damage that would be dealt to any target this turn. Draw a card at the beginning of the next turn's upkeep. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Thermal Flux | notice | Choose one — • Target nonsnow permanent becomes snow until end of turn. • Target snow permanent isn't snow until end of turn. Draw a card at the beginning of th | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Vanish into Memory | notice | Exile target creature. You draw cards equal to that creature's power. At the beginning of your next upkeep, return that card to the battlefield under its owner' | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Cover of Winter | unaudited | If a creature would deal combat damage to you and/or one or more creatures you control, prevent X of that damage, where X is the number of age counters on this  | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Freyalise's Radiance | unaudited | Snow permanents don't untap during their controllers' untap steps. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Gelid Shackles | unaudited | Enchanted creature can't block, and its activated abilities can't be activated. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Goblin Furrier | unaudited | Prevent all damage that this creature would deal to snow creatures. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Greater Stone Spirit | unaudited | This creature can't be blocked by creatures with flying. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Haakon, Stromgald Scourge | unaudited | You may cast this card from your graveyard, but not from anywhere else. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Karplusan Strider | unaudited | This creature can't be the target of blue or black spells. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Panglacial Wurm | unaudited | While you're searching your library, you may cast this card from your library. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Rimescale Dragon | unaudited | Creatures with ice counters on them don't untap during their controllers' untap steps. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Thrumming Stone | unaudited | Spells you cast have ripple 4. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Tresserhorn Skyknight | unaudited | Prevent all damage that would be dealt to this creature by creatures with first strike. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Void Maw | unaudited | If another creature would die, exile it instead. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Wilderness Elemental | unaudited | Wilderness Elemental's power is equal to the number of nonbasic lands your opponents control. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Arctic Flats | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boreal Centaur | handled | {S}: This creature gets +1/+1 until end of turn. Activate only once each turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boreal Druid | handled |  |  | Y/-/- | not_tested |
| Boreal Griffin | handled | {S}: This creature gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boreal Shelf | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chill to the Bone | handled | Destroy target nonsnow creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chilling Shade | handled | {S}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Coldsteel Heart | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cryoclasm | handled | Destroy target Plains or Island. Cryoclasm deals 3 damage to that land's controller. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deathmark | handled | Destroy target green or white creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Deepfire Elemental | handled | {X}{X}{1}: Destroy target artifact or creature with mana value X. | the engine reads this text and performs it | Y/-/- | not_tested |
| Disciple of Tevesh Szat | handled | {T}: Target creature gets -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drelnoch | handled | Whenever this creature becomes blocked, you may draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flashfreeze | handled | Counter target red or green spell. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Frost Marsh | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Frost Raptor | handled | {S}{S}: This creature gains shroud until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Garza Zol, Plague Queen | handled | Whenever a creature dealt damage by Garza Zol this turn dies, put a +1/+1 counter on Garza Zol. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Rimerunner | handled | {T}: Target creature can't block this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gristle Grinner | handled | Whenever a creature dies, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gutless Ghoul | handled | {1}, Sacrifice a creature: You gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Heidar, Rimewind Master | handled | {2}, {T}: Return target permanent to its owner's hand. Activate only if you control four or more snow permanents. | the engine reads this text and performs it | Y/-/- | not_tested |
| Highland Weald | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Into the North | handled | Search your library for a snow land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jötun Grunt | handled | Cumulative upkeep | machines/keywords.py | Y/-/- | not_tested |
| Jötun Owl Keeper | handled | When this creature dies, create a 1/1 white Bird creature token with flying for each age counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kjeldoran Outrider | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Krovikan Scoundrel | handled |  |  | Y/-/- | not_tested |
| Krovikan Whispers | handled | You control enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lightning Serpent | handled | This creature enters with X +1/+0 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Martyr of Spores | handled | {1}, Reveal X green cards from your hand, Sacrifice this creature: Target creature gets +X/+X until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mouth of Ronom | handled | {4}{S}, {T}, Sacrifice this land: It deals 4 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ohran Yeti | handled | {2}{S}: Target snow creature gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Orcish Bloodpainter | handled | {T}, Sacrifice a creature: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Etchings | handled | At the beginning of your end step, draw a card for each age counter on this enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Ironfoot | handled | This creature doesn't untap during your untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Snowcrusher | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Soulgorger | handled | Cumulative upkeep | machines/keywords.py | Y/-/- | not_tested |
| Rime Transfusion | handled | Enchanted creature gets +2/+1 and has "{S}: This creature can't be blocked this turn except by snow creatures." | the engine reads this text and performs it | Y/-/- | not_tested |
| Rimebound Dead | handled | {S}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rimewind Taskmage | handled | {1}, {T}: You may tap or untap target permanent. Activate only if you control four or more snow permanents. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ronom Hulk | handled | Protection | models/game.py | Y/-/- | not_tested |
| Ronom Unicorn | handled | Sacrifice this creature: Destroy target enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sek'Kuar, Deathkeeper | handled | Whenever another nontoken creature you control dies, create a 3/1 black and red Graveborn creature token with haste. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sheltering Ancient | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Simian Brawler | handled | Discard a land card: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Soul Spike | handled | You may exile two black cards from your hand rather than pay this spell's mana cost. Soul Spike deals 4 damage to any target and you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
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
<summary>8 cards</summary>

- Allosaurus Rider
- Braid of Fire
- Kjeldoran Javelineer
- Martyr of Ashes
- Martyr of Sands
- Mishra's Bauble
- Rimewind Cryomancer
- Vexing Sphinx

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| recover | 7 | Controvert, Garza's Assassin, Grim Harvest, Icefall, Krovikan Rot | csp |
| ripple | 5 | Surging Aether, Surging Dementia, Surging Flame, Surging Might, Surging Sentinels | csp |
| whenever ~ attacks, it gets +N/+N until end of turn for each other attacking aurochs. | 3 | Aurochs Herd, Bull Aurochs, Rimehorn Aurochs | csp |
| Choose one | 1 | Thermal Flux | csp |
| add {M}{M}, then add {M} for each card named ~ in each graveyard. | 1 | Rite of Flame | csp |
| as long as ~ has an ice counter on it, prevent all combat damage it would deal and it has defender. | 1 | Woolly Razorback | csp |
| at the beginning of each end step, each player gains control of all nontoken permanents they own. | 1 | Brooding Saurian | csp |
| at the beginning of your end step, ~ deals N damage divided as you choose among any number of target creatures, where N is the number of age counters on it. | 1 | Magmatic Core | csp |
| counter target spell unless its controller pays {M} plus an additional {M} for each card named ~ in each graveyard. | 1 | Rune Snag | csp |
| creatures with ice counters on them don"..." untap steps. | 1 | Rimescale Dragon | csp |
| creatures you control get +N/+N until end of turn, where N is N plus the number of cards named ~ in all graveyards. | 1 | Kjeldoran War Cry | csp |
| destroy target artifact or enchantment. draw a card at the beginning of the next turn's upkeep. | 1 | Mystic Melting | csp |
| draw two cards, then sacrifice a permanent. | 1 | Perilous Research | csp |
| enchanted creature can"..."t be activated. | 1 | Gelid Shackles | csp |
| enchanted creature gets +N/+N for each age counter on ~. | 1 | Glacial Plating | csp |
| exile target creature. you draw cards equal to that creature"..."s control. if you do, discard cards equal to that creature's toughness. | 1 | Vanish into Memory | csp |
| fear | 1 | Phobian Phantasm | csp |
| if a creature would deal combat damage to you and/or one or more creatures you control, prevent N of that damage, where N is the number of age counters on ~. | 1 | Cover of Winter | csp |
| if another creature would die, exile it instead. | 1 | Void Maw | csp |
| other soldier creatures get +N/+N and have first strike. | 1 | Field Marshal | csp |
| prevent all damage that black sources and red sources would deal ~. | 1 | Luminesce | csp |
| prevent all damage that would be dealt to ~ by creatures with first strike. | 1 | Tresserhorn Skyknight | csp |
| prevent all damage that ~ would deal to snow creatures. | 1 | Goblin Furrier | csp |
| prevent the next N damage that would be dealt to any target ~. draw a card at the beginning of the next turn's upkeep. | 1 | Swift Maneuver | csp |
| remove a healing counter from ~: prevent the next N damage that would be dealt to ~ ~. | 1 | Ursine Fylgja | csp |
| snow permanents don"..." untap steps. | 1 | Freyalise's Radiance | csp |
| spells you cast have ripple N. | 1 | Thrumming Stone | csp |
| when you control no snow lands, sacrifice ~. | 1 | Ronom Serpent | csp |
| when ~ enters, exile the top five cards of target player's library face down. you may look at those cards for as long as they remain exiled. | 1 | Jester's Scepter | csp |
| when ~ enters, if it's on the battlefield, it deals damage equal to its power to target creature an opponent controls and that creature deals damage equal to it | 1 | Stalking Yeti | csp |
| when ~ enters, put six +N/+N counters on enchanted creature. | 1 | Shape of the Wiitigo | csp |
| when ~ enters, sacrifice it unless you sacrifice five lands. | 1 | Jokulmorder | csp |
| when ~ has no ice counters on it, sacrifice it. if you do, create marit lage, a legendary N/N black avatar creature token with flying and indestructible. | 1 | Dark Depths | csp |
| when ~ leaves the battlefield, each player gains control of each land they own that you control. | 1 | Herald of Leshrac | csp |
| whenever a noncreature source you control deals damage, you gain that much life. | 1 | Tamanoa | csp |
| whenever an opponent casts a spell, you may reveal the top card of your library. if you do, counter that spell if it has the same mana value as the revealed car | 1 | Counterbalance | csp |
| whenever you pay ~ cumulative upkeep, you may search your library for a creature card with mana value equal to the number of age counters on ~, put it onto the  | 1 | Hibernation's End | csp |
| whenever you win a coin flip, ~ deals N damage to any target. | 1 | Karplusan Minotaur | csp |
| whenever you're dealt damage, you may create that many N/N white soldier creature tokens. | 1 | Darien, King of Kjeldor | csp |
| whenever ~ blocks a creature with flying, put a +N/+N counter on ~ at end of combat. | 1 | Frostweb Spider | csp |
| whenever ~ cumulative upkeep is paid, it gets +N/+N until end of turn for each {M} or {M} spent ~. | 1 | Balduvian Fallen | csp |
| whenever ~ deals combat damage to a creature, destroy that creature at end of combat. | 1 | Ohran Viper | csp |
| whenever ~ deals combat damage to a player, choose one — • that player returns a permanent they control to its owner's hand. • that player discards a card. | 1 | Blizzard Specter | csp |
| whenever ~ deals damage, you gain that much life. | 1 | Kjeldoran Gargoyle | csp |
| while you're searching your library, you may cast ~ from your library. | 1 | Panglacial Wurm | csp |
| you may cast ~ from your graveyard, but not from anywhere else. | 1 | Haakon, Stromgald Scourge | csp |
| you may exile two blue cards from your hand rather than pay ~ mana cost. gain control of target noncreature spell. you may choose new targets for it. (if that s | 1 | Commandeer | csp |
| you may exile two red cards from your hand rather than pay ~ mana cost. untap all creatures that attacked ~. after ~ phase, there is an additional combat phase  | 1 | Fury of the Horde | csp |
| {M}, reveal N black cards from your hand, sacrifice ~: exile up to N target cards from a single graveyard. | 1 | Martyr of Bones | csp |
| {M}, {M}: target snow land becomes a N/N blue elemental creature with flying. it's still a land. | 1 | Balduvian Frostwaker | csp |
| {M}: remove target blocking creature from combat. creatures it was blocking that hadn't become blocked by another creature ~ become unblocked, then it blocks an | 1 | Balduvian Warlord | csp |
| {M}: target artifact creature's controller sacrifices it. that player may search their library for a noncreature artifact card, put it onto the battlefield, the | 1 | Arcum Dagsson | csp |
| {M}: when target creature other than ~ dies ~, return that card to the battlefield under your control. | 1 | Adarkar Valkyrie | csp |
| {M}{M}, {M}: look at the top card of your library. if that card is snow, you may reveal it and put it into your hand. | 1 | Scrying Sheets | csp |
| {M}{M}: snow creatures you control get +N/+N until end of turn. | 1 | Diamond Faerie | csp |
| {M}{M}: target creature loses flying until end of turn. | 1 | Adarkar Windform | csp |
| ~ can't be blocked by creatures with flying. | 1 | Greater Stone Spirit | csp |
| ~ can't be the target of blue or black spells. | 1 | Karplusan Strider | csp |
| ~ deals N damage to any target, where N is N plus the number of charge counters on ~. discard a land card: put two charge counters on ~. you may choose a new ta | 1 | Lightning Storm | csp |
| ~ deals N damage to target creature and you gain N life, where N is N plus the number of cards named ~ in all graveyards. | 1 | Feast of Flesh | csp |
| ~ deals damage to target creature equal to the number of snow permanents you control. | 1 | Skred | csp |
| ~ gets +N/+N for each age counter on it. | 1 | Earthen Goo | csp |
| ~'s power and toughness are each equal to the number of illusions on the battlefield. | 1 | Krovikan Mist | csp |
| ~'s power and toughness are each equal to the number of snow permanents on the battlefield. | 1 | Rimefeather Owl | csp |
| ~'s power is equal to the number of nonbasic lands your opponents control. | 1 | Wilderness Elemental | csp |

## Notes



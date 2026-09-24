# Coldsnap (csp)

- Expansion: 068
- Set code: `csp`
- Release date: 2006-07-21
- Cards in scope (Modern/Pioneer/Standard-legal): 141

## Legality

| Format | Legal cards |
|---|---|
| Modern | 141 |
| Pioneer | 2 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 7 | 5.0% |
| Partial (unaudited) | 12 | 8.5% |
| Not tested (handled, untested) | 56 | 39.7% |
| Not working (silent / notice / error) | 66 | 46.8% |

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
| Dark Depths | silent | {3}: Remove an ice counter from Dark Depths. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Diamond Faerie | silent | {1}{S}: Snow creatures you control get +1/+1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Feast of Flesh | silent | Feast of Flesh deals X damage to target creature and you gain X life, where X is 1 plus the number of cards named Feast of Flesh in all graveyards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Field Marshal | silent | Other Soldier creatures get +1/+1 and have first strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fury of the Horde | silent | You may exile two red cards from your hand rather than pay this spell's mana cost. Untap all creatures that attacked this turn. After this main phase, there is  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Garza's Assassin | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Gelid Shackles | silent | {S}: Enchanted creature gains defender until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Glacial Plating | silent | Enchanted creature gets +3/+3 for each age counter on this Aura. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Goblin Rimerunner | silent | {T}: Target creature can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grim Harvest | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Herald of Leshrac | silent | When this creature leaves the battlefield, each player gains control of each land they own that you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hibernation's End | silent | Whenever you pay this enchantment's cumulative upkeep, you may search your library for a creature card with mana value equal to the number of age counters on th | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Icefall | silent | Recover | no machine in the engine executes this keyword | Y/-/- | not_working |
| Jester's Scepter | silent | When this artifact enters, exile the top five cards of target player's library face down. You may look at those cards for as long as they remain exiled. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jokulmorder | silent | When this creature enters, sacrifice it unless you sacrifice five lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jötun Owl Keeper | silent | When this creature dies, create a 1/1 white Bird creature token with flying for each age counter on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
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
| Gristle Grinner | handled | Whenever a creature dies, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gutless Ghoul | handled | {1}, Sacrifice a creature: You gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Heidar, Rimewind Master | handled | {2}, {T}: Return target permanent to its owner's hand. Activate only if you control four or more snow permanents. | the engine reads this text and performs it | Y/-/- | not_tested |
| Highland Weald | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Into the North | handled | Search your library for a snow land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jötun Grunt | handled | Cumulative upkeep | machines/keywords.py | Y/-/- | not_tested |
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
<summary>7 cards</summary>

- Braid of Fire
- Kjeldoran Javelineer
- Martyr of Ashes
- Martyr of Sands
- Mishra's Bauble
- Rimewind Cryomancer
- Vexing Sphinx

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Recover | Controvert, Garza's Assassin, Grim Harvest, Icefall, Krovikan Rot, Resize, Sun's Bounty | 7 |
| Ripple | Surging Aether, Surging Dementia, Surging Might, Surging Sentinels | 4 |
| Whenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Aurochs. | Aurochs Herd, Bull Aurochs, Rimehorn Aurochs | 3 |
| This creature can't be the target of blue or black spells. | Greater Stone Spirit, Karplusan Strider | 2 |
| Whenever this creature deals combat damage to a player, choose one — • That player returns a permanent they control to its owner's hand. • That player discards  | Blizzard Specter, Ohran Viper | 2 |
| Add {R}{R}, then add {R} for each card named Rite of Flame in each graveyard. | Rite of Flame | 1 |
| As long as this creature has an ice counter on it, prevent all combat damage it would deal and it has defender. | Woolly Razorback | 1 |
| At the beginning of each end step, each player gains control of all nontoken permanents they own. | Brooding Saurian | 1 |
| At the beginning of your end step, this enchantment deals X damage divided as you choose among any number of target creatures, where X is the number of age coun | Magmatic Core | 1 |
| Choose one — • Target nonsnow permanent becomes snow until end of turn. • Target snow permanent isn't snow until end of turn. Draw a card at the beginning of th | Thermal Flux | 1 |
| Counter target spell unless its controller pays {2} plus an additional {2} for each card named Rune Snag in each graveyard. | Rune Snag | 1 |
| Creatures with ice counters on them don't untap during their controllers' untap steps. | Rimescale Dragon | 1 |
| Creatures you control get +X/+X until end of turn, where X is 1 plus the number of cards named Kjeldoran War Cry in all graveyards. | Kjeldoran War Cry | 1 |
| Destroy target artifact or enchantment. Draw a card at the beginning of the next turn's upkeep. | Mystic Melting | 1 |
| Draw two cards, then sacrifice a permanent. | Perilous Research | 1 |
| {S}: Enchanted creature gains defender until end of turn. | Gelid Shackles | 1 |
| Enchanted creature gets +3/+3 for each age counter on this Aura. | Glacial Plating | 1 |
| Exile target creature. You draw cards equal to that creature's power. At the beginning of your next upkeep, return that card to the battlefield under its owner' | Vanish into Memory | 1 |
| Fear | Phobian Phantasm | 1 |
| Feast of Flesh deals X damage to target creature and you gain X life, where X is 1 plus the number of cards named Feast of Flesh in all graveyards. | Feast of Flesh | 1 |
| If a creature would deal combat damage to you and/or one or more creatures you control, prevent X of that damage, where X is the number of age counters on this  | Cover of Winter | 1 |
| If another creature would die, exile it instead. | Void Maw | 1 |
| Krovikan Mist's power and toughness are each equal to the number of Illusions on the battlefield. | Krovikan Mist | 1 |
| Lightning Storm deals X damage to any target, where X is 3 plus the number of charge counters on Lightning Storm. Discard a land card: Put two charge counters o | Lightning Storm | 1 |
| {1}{S}, {T}: Look at the top card of your library. If that card is snow, you may reveal it and put it into your hand. | Scrying Sheets | 1 |
| Other Soldier creatures get +1/+1 and have first strike. | Field Marshal | 1 |
| Prevent all damage that black sources and red sources would deal this turn. | Luminesce | 1 |
| Prevent all damage that this creature would deal to snow creatures. | Goblin Furrier | 1 |
| Prevent all damage that would be dealt to this creature by creatures with first strike. | Tresserhorn Skyknight | 1 |
| Prevent the next 2 damage that would be dealt to any target this turn. Draw a card at the beginning of the next turn's upkeep. | Swift Maneuver | 1 |
| Remove a healing counter from this creature: Prevent the next 1 damage that would be dealt to this creature this turn. | Ursine Fylgja | 1 |
| {3}: Remove an ice counter from Dark Depths. | Dark Depths | 1 |
| {T}: Remove target blocking creature from combat. Creatures it was blocking that hadn't become blocked by another creature this combat become unblocked, then it | Balduvian Warlord | 1 |
| {1}, Reveal X black cards from your hand, Sacrifice this creature: Exile up to X target cards from a single graveyard. | Martyr of Bones | 1 |
| Rimefeather Owl's power and toughness are each equal to the number of snow permanents on the battlefield. | Rimefeather Owl | 1 |
| Skred deals damage to target creature equal to the number of snow permanents you control. | Skred | 1 |
| {1}{S}: Snow creatures you control get +1/+1 until end of turn. | Diamond Faerie | 1 |
| Snow permanents don't untap during their controllers' untap steps. | Freyalise's Radiance | 1 |
| Spells you cast have ripple 4. | Thrumming Stone | 1 |
| {T}: Target artifact creature's controller sacrifices it. That player may search their library for a noncreature artifact card, put it onto the battlefield, the | Arcum Dagsson | 1 |
| {T}: Target creature can't block this turn. | Goblin Rimerunner | 1 |
| {1}{S}: Target creature loses flying until end of turn. | Adarkar Windform | 1 |
| {U}, {T}: Target snow land becomes a 2/2 blue Elemental creature with flying. It's still a land. | Balduvian Frostwaker | 1 |
| This creature gets +1/+1 for each age counter on it. | Earthen Goo | 1 |
| {T}: When target creature other than this creature dies this turn, return that card to the battlefield under your control. | Adarkar Valkyrie | 1 |
| When this artifact enters, exile the top five cards of target player's library face down. You may look at those cards for as long as they remain exiled. | Jester's Scepter | 1 |
| When this Aura enters, put six +1/+1 counters on enchanted creature. | Shape of the Wiitigo | 1 |
| When this creature dies, create a 1/1 white Bird creature token with flying for each age counter on it. | Jötun Owl Keeper | 1 |
| When this creature enters, if it's on the battlefield, it deals damage equal to its power to target creature an opponent controls and that creature deals damage | Stalking Yeti | 1 |
| When this creature enters, sacrifice it unless you sacrifice five lands. | Jokulmorder | 1 |
| When this creature leaves the battlefield, each player gains control of each land they own that you control. | Herald of Leshrac | 1 |
| When you control no snow lands, sacrifice this creature. | Ronom Serpent | 1 |
| Whenever a noncreature source you control deals damage, you gain that much life. | Tamanoa | 1 |
| Whenever an opponent casts a spell, you may reveal the top card of your library. If you do, counter that spell if it has the same mana value as the revealed car | Counterbalance | 1 |
| Whenever this creature blocks a creature with flying, put a +1/+1 counter on this creature at end of combat. | Frostweb Spider | 1 |
| Whenever this creature deals damage, you gain that much life. | Kjeldoran Gargoyle | 1 |
| Whenever this creature's cumulative upkeep is paid, it gets +1/+0 until end of turn for each {B} or {R} spent this way. | Balduvian Fallen | 1 |
| Whenever you pay this enchantment's cumulative upkeep, you may search your library for a creature card with mana value equal to the number of age counters on th | Hibernation's End | 1 |
| Whenever you're dealt damage, you may create that many 1/1 white Soldier creature tokens. | Darien, King of Kjeldor | 1 |
| Whenever you win a coin flip, this creature deals 1 damage to any target. | Karplusan Minotaur | 1 |
| While you're searching your library, you may cast this card from your library. | Panglacial Wurm | 1 |
| Wilderness Elemental's power is equal to the number of nonbasic lands your opponents control. | Wilderness Elemental | 1 |
| You may cast this card from your graveyard, but not from anywhere else. | Haakon, Stromgald Scourge | 1 |
| You may exile two blue cards from your hand rather than pay this spell's mana cost. Gain control of target noncreature spell. You may choose new targets for it. | Commandeer | 1 |
| You may exile two red cards from your hand rather than pay this spell's mana cost. Untap all creatures that attacked this turn. After this main phase, there is  | Fury of the Horde | 1 |

## Notes



# Magic 2013 (m13)

- Expansion: 128
- Set code: `m13`
- Release date: 2012-07-13
- Cards in scope (Modern/Pioneer/Standard-legal): 107

## Legality

| Format | Legal cards |
|---|---|
| Modern | 107 |
| Pioneer | 31 |
| Standard | 5 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 13 | 12.1% |
| Works (untested) | 63 | 58.9% |
| Partial (unaudited) | 1 | 0.9% |
| Not working | 30 | 28.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Blood Reckoning | silent | Whenever a creature attacks you or a planeswalker you control, that creature's controller loses 1 life. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Cathedral of War | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Crippling Blight | silent | Enchanted creature gets -1/-1 and can't block. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Disciple of Bolas | silent | When this creature enters, sacrifice another creature. You gain X life and draw X cards, where X is that creature's power. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Duskmantle Prowler | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Duty-Bound Dead | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Gem of Becoming | silent | {3}, {T}, Sacrifice this artifact: Search your library for an Island card, a Swamp card, and a Mountain card. Reveal those cards, put them into your hand, then  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Knight of Glory | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Knight of Infamy | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Liliana of the Dark Realms | silent | −3: Target creature gets +X/+X or -X/-X until end of turn, where X is the number of Swamps you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Master of the Pearl Trident | silent | Other Merfolk creatures you control get +1/+1 and have islandwalk. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mindclaw Shaman | silent | When this creature enters, target opponent reveals their hand. You may cast an instant or sorcery spell from among those cards without paying its mana cost. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mwonvuli Beast Tracker | silent | When this creature enters, search your library for a creature card with deathtouch, hexproof, reach, or trample and reveal it. Shuffle and put that card on top. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Nefarox, Overlord of Grixis | silent | Whenever Nefarox attacks alone, defending player sacrifices a creature of their choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Odric, Master Tactician | silent | Whenever Odric and at least three other creatures attack, you choose which creatures block this combat and how those creatures block. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Public Execution | silent | Destroy target creature an opponent controls. Each other creature that player controls gets -2/-0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ring of Evos Isle | silent | At the beginning of your upkeep, put a +1/+1 counter on equipped creature if it's blue. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ring of Kalonia | silent | At the beginning of your upkeep, put a +1/+1 counter on equipped creature if it's green. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ring of Thune | silent | At the beginning of your upkeep, put a +1/+1 counter on equipped creature if it's white. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ring of Valkas | silent | At the beginning of your upkeep, put a +1/+1 counter on equipped creature if it's red. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ring of Xathrid | silent | {2}: Regenerate equipped creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Roaring Primadox | silent | At the beginning of your upkeep, return a creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Servant of Nefarox | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Slumbering Dragon | silent | Whenever a creature attacks you or a planeswalker you control, put a +1/+1 counter on this creature. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Spelltwine | silent | Exile target instant or sorcery card from your graveyard and target instant or sorcery card from an opponent's graveyard. Copy those cards. Cast the copies if a | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sublime Archangel | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Tricks of the Trade | silent | Enchanted creature gets +2/+0 and can't be blocked. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Void Stalker | silent | {2}{U}, {T}: Put this creature and target creature on top of their owners' libraries, then those players shuffle their libraries. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Timberpack Wolf | notice | This creature gets +1/+1 for each other creature you control named Timberpack Wolf. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Xathrid Gorgon | notice | {2}{B}, {T}: Put a petrification counter on target creature. It gains defender and becomes a colorless artifact in addition to its other types. Its activated ab | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Encrust | unaudited | Enchanted permanent doesn't untap during its controller's untap step and its activated abilities can't be activated. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ajani's Sunstriker | handled | Lifelink | machines/combat.py | Y/-/- | not_tested |
| Ajani, Caller of the Pride | handled | +1: Put a +1/+1 counter on up to one target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Archaeomancer | handled | When this creature enters, return target instant or sorcery card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Arctic Aven | handled | This creature gets +1/+1 as long as you control a Plains. | the engine reads this text and performs it | Y/-/- | not_tested |
| Attended Knight | handled | When this creature enters, create a 1/1 white Soldier creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Battleflight Eagle | handled | When this creature enters, target creature gets +2/+2 and gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bloodhunter Bat | handled | When this creature enters, target player loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bond Beetle | handled | When this creature enters, put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boundless Realms | handled | Search your library for up to X basic land cards, where X is the number of lands you control, put them onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Captain's Call | handled | Create three 1/1 white Soldier creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chronomaton | handled | {1}, {T}: Put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cleaver Riot | handled | Creatures you control gain double strike until end of turn. (They deal both first-strike and regular combat damage.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Courtly Provocateur | handled | {T}: Target creature attacks this turn if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cower in Fear | handled | Creatures your opponents control get -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Craterize | handled | Destroy target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crimson Muckwader | handled | This creature gets +1/+1 as long as you control a Swamp. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crusader of Odric | handled | Crusader of Odric's power and toughness are each equal to the number of creatures you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Diabolic Revelation | handled | Search your library for up to X cards, put those cards into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Downpour | handled | Tap up to three target creatures. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dragon Hatchling | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Faerie Invaders | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Firewing Phoenix | handled | {1}{R}{R}{R}: Return this card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flames of the Firebrand | handled | Flames of the Firebrand deals 3 damage divided as you choose among one, two, or three targets. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Flinthoof Boar | handled | This creature gets +1/+1 as long as you control a Mountain. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fungal Sprouting | handled | Create X 1/1 green Saproling creature tokens, where X is the greatest power among creatures you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Battle Jester | handled | Whenever you cast a red spell, target creature can't block this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Griffin Protector | handled | Whenever another creature you control enters, this creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Guardian Lions | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Harbor Bandit | handled | This creature gets +1/+1 as long as you control an Island. | the engine reads this text and performs it | Y/-/- | not_tested |
| Healer of the Pride | handled | Whenever another creature you control enters, you gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hellion Crucible | handled | {1}{R}, {T}: Put a pressure counter on this land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hydrosurge | handled | Target creature gets -5/-0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Krenko's Command | handled | Create two 1/1 red Goblin creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Krenko, Mob Boss | handled | {T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Liliana's Shade | handled | When this creature enters, you may search your library for a Swamp card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magmaquake | handled | Magmaquake deals X damage to each creature without flying and each planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mark of the Vampire | handled | Enchanted creature gets +2/+2 and has lifelink. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Murder | handled | Destroy target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Primal Huntbeast | handled | Hexproof | machines/casting.py (target legality) | Y/-/- | not_tested |
| Prized Elephant | handled | This creature gets +1/+1 as long as you control a Forest. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ranger's Path | handled | Search your library for up to two Forest cards, put them onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Reckless Brute | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rhox Faithmender | handled | If you would gain life, you gain twice that much life instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rummaging Goblin | handled | {T}, Discard a card: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sands of Delirium | handled | {X}, {T}: Target player mills X cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Searing Spear | handled | Searing Spear deals 3 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sentinel Spider | handled | Reach | machines/combat.py | Y/-/- | not_tested |
| Serpent's Gift | handled | Target creature gains deathtouch until end of turn. (Any amount of damage it deals to a creature is enough to destroy it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Show of Valor | handled | Target creature gets +2/+4 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Smelt | handled | Destroy target artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spiked Baloth | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Staff of Nin | handled | At the beginning of your upkeep, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Talrand's Invocation | handled | Create two 2/2 blue Drake creature tokens with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Talrand, Sky Summoner | handled | Whenever you cast an instant or sorcery spell, create a 2/2 blue Drake creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thragtusk | handled | When this creature enters, you gain 5 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trading Post | handled | {1}, {T}, Discard a card: You gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Veilborn Ghoul | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vile Rebirth | handled | Exile target creature card from a graveyard. Create a 2/2 black Zombie creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| War Falcon | handled | This creature can't attack unless you control a Knight or a Soldier. | the engine reads this text and performs it | Y/-/- | not_tested |
| Warclamp Mastiff | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Watercourser | handled | {U}: This creature gets +1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wild Guess | handled | As an additional cost to cast this spell, discard a card. Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Yeva's Forcemage | handled | When this creature enters, target creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>13 cards</summary>

- Augur of Bolas
- Chandra's Fury
- Elderscale Wurm
- Faith's Reward
- Jace's Phantasm
- Mind Sculpt
- Omniscience
- Predatory Rampage
- Switcheroo
- Thundermaw Hellkite
- Touch of the Eternal
- Worldfire
- Yeva, Nature's Herald

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| exalted | 7 | Cathedral of War, Duskmantle Prowler, Duty-Bound Dead, Knight of Glory, Knight of Infamy | m13 |
| at the beginning of your upkeep, put a +N/+N counter on equipped creature if it's blue. | 1 | Ring of Evos Isle | m13 |
| at the beginning of your upkeep, put a +N/+N counter on equipped creature if it's green. | 1 | Ring of Kalonia | m13 |
| at the beginning of your upkeep, put a +N/+N counter on equipped creature if it's red. | 1 | Ring of Valkas | m13 |
| at the beginning of your upkeep, put a +N/+N counter on equipped creature if it's white. | 1 | Ring of Thune | m13 |
| at the beginning of your upkeep, return a creature you control to its owner's hand. | 1 | Roaring Primadox | m13 |
| destroy target creature an opponent controls. each other creature that player controls gets -N/-N until end of turn. | 1 | Public Execution | m13 |
| enchanted creature gets +N/+N and can't be blocked. | 1 | Tricks of the Trade | m13 |
| enchanted creature gets -N/-N and can't block. | 1 | Crippling Blight | m13 |
| enchanted permanent doesn"..."s untap step and its activated abilities can't be activated. | 1 | Encrust | m13 |
| exile target instant or sorcery card from your graveyard and target instant or sorcery card from an opponent's graveyard. copy those cards. cast the copies if a | 1 | Spelltwine | m13 |
| other merfolk creatures you control get +N/+N and have islandwalk. | 1 | Master of the Pearl Trident | m13 |
| when ~ enters, sacrifice another creature. you gain N life and draw N cards, where N is that creature's power. | 1 | Disciple of Bolas | m13 |
| when ~ enters, search your library for a creature card with deathtouch, hexproof, reach, or trample and reveal it. shuffle and put that card on top. | 1 | Mwonvuli Beast Tracker | m13 |
| when ~ enters, target opponent reveals their hand. you may cast an instant or sorcery spell from among those cards without paying its mana cost. | 1 | Mindclaw Shaman | m13 |
| whenever a creature attacks you or a planeswalker you control, put a +N/+N counter on ~. | 1 | Slumbering Dragon | m13 |
| whenever a creature attacks you or a planeswalker you control, that creature's controller loses N life. | 1 | Blood Reckoning | m13 |
| whenever nefarox attacks alone, defending player sacrifices a creature of their choice. | 1 | Nefarox, Overlord of Grixis | m13 |
| whenever odric and at least three other creatures attack, you choose which creatures block ~ and how those creatures block. | 1 | Odric, Master Tactician | m13 |
| {M}, {M}, sacrifice ~: search your library for an island card, a swamp card, and a mountain card. reveal those cards, put them into your hand, then shuffle. | 1 | Gem of Becoming | m13 |
| {M}: regenerate equipped creature. | 1 | Ring of Xathrid | m13 |
| {M}{M}, {M}: put a petrification counter on target creature. it gains defender and becomes a colorless artifact in addition to its other types. its activated ab | 1 | Xathrid Gorgon | m13 |
| {M}{M}, {M}: put ~ and target creature on top of their owners' libraries, then those players shuffle their libraries. | 1 | Void Stalker | m13 |
| ~ gets +N/+N for each other creature you control named ~. | 1 | Timberpack Wolf | m13 |
| −N: target creature gets +N/+N or -N/-N until end of turn, where N is the number of swamps you control. | 1 | Liliana of the Dark Realms | m13 |

## Notes



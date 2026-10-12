# Tempest (tmp)

- Expansion: 018
- Set code: `tmp`
- Release date: 1997-10-14
- Cards in scope (Modern/Pioneer/Standard-legal): 57

## Legality

| Format | Legal cards |
|---|---|
| Modern | 57 |
| Pioneer | 5 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 14 | 24.6% |
| Works (untested) | 33 | 57.9% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 10 | 17.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Boil | silent | Destroy all Islands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Death Pits of Rath | silent | Whenever a creature is dealt damage, destroy it. It can't be regenerated. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Elvish Fury | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Jinxed Idol | silent | Sacrifice a creature: Target opponent gains control of this artifact. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rathi Dragon | silent | When this creature enters, sacrifice it unless you sacrifice two Mountains. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rootwater Matriarch | silent | {T}: Gain control of target creature for as long as that creature is enchanted. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Time Warp | silent | Target player takes an extra turn after this one. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vhati il-Dal | silent | {T}: Until end of turn, target creature has base power 1 or base toughness 1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Whispers of the Muse | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Altar of Dementia | notice | Sacrifice a creature: Target player mills cards equal to the sacrificed creature's power. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Auratog | handled | Sacrifice an enchantment: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bottle Gnomes | handled | Sacrifice this creature: You gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Canopy Spider | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Canyon Wildcat | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Elite Javelineer | handled | Whenever this creature blocks, it deals 1 damage to target attacking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Emerald Medallion | handled | Green spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fighting Drake | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Harrow | handled | As an additional cost to cast this spell, sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jet Medallion | handled | Black spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lightning Blast | handled | Lightning Blast deals 4 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lightning Elemental | handled | Haste | machines/combat.py | Y/-/- | not_tested |
| Master Decoy | handled | {W}, {T}: Tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Overrun | handled | Creatures you control get +3/+3 and gain trample until end of turn. (Each of those creatures can deal excess combat damage to the player or planeswalker it's at | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Patchwork Gnomes | handled | Discard a card: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pearl Medallion | handled | White spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Hulk | handled |  |  | Y/-/- | not_tested |
| Pincher Beetles | handled | Shroud | models/game.py (Game.shroud_refusal), machines/targeting.py (TargetingProfile._check_shroud, CR 702.18a) | Y/-/- | not_tested |
| Propaganda | handled | Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rolling Thunder | handled | Rolling Thunder deals X damage divided as you choose among any number of targets. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rootbreaker Wurm | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Rootwalla | handled | {1}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sandstone Warrior | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sapphire Medallion | handled | Blue spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scragnoth | handled | This spell can't be countered. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sea Monster | handled | This creature can't attack unless defending player controls an Island. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shimmering Wings | handled | Enchanted creature has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skyshroud Ranger | handled | {T}: You may put a land card from your hand onto the battlefield. Activate only as a sorcery. | the engine reads this text and performs it | Y/-/- | not_tested |
| Soltari Priest | handled | Shadow | machines/combat.py | Y/-/- | not_tested |
| Staunch Defenders | handled | When this creature enters, you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stun | handled | Target creature can't block this turn. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trained Armodon | handled |  |  | Y/-/- | not_tested |
| Twitch | handled | You may tap or untap target artifact, creature, or land. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Verdant Force | handled | At the beginning of each upkeep, create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>14 cards</summary>

- Booby Trap
- Choke
- Dauthi Slayer
- Diabolic Edict
- Furnace of Rath
- Goblin Bombardment
- Knight of Dusk
- Marble Titan
- Mogg Fanatic
- Reflecting Pool
- Root Maze
- Ruby Medallion
- Stalking Stones
- Sudden Impact

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| buyback | 2 | Elvish Fury, Whispers of the Muse | tmp |
| destroy all islands. | 1 | Boil | tmp |
| sacrifice a creature: target opponent gains control of ~. | 1 | Jinxed Idol | tmp |
| sacrifice a creature: target player mills cards equal to the sacrificed creature's power. | 1 | Altar of Dementia | tmp |
| target player takes an extra turn after ~. | 1 | Time Warp | tmp |
| when ~ enters, sacrifice it unless you sacrifice two mountains. | 1 | Rathi Dragon | tmp |
| whenever a creature is dealt damage, destroy it. it can't be regenerated. | 1 | Death Pits of Rath | tmp |
| {M}: gain control of target creature for as long as that creature is enchanted. | 1 | Rootwater Matriarch | tmp |
| {M}: until end of turn, target creature has base power N or base toughness N. | 1 | Vhati il-Dal | tmp |

## Notes



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
| Full (handled + tested) | 7 | 12.3% |
| Partial (unaudited) | 5 | 8.8% |
| Not tested (handled, untested) | 30 | 52.6% |
| Not working (silent / notice / error) | 15 | 26.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Boil | silent | Destroy all Islands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dauthi Slayer | silent | Shadow | no machine in the engine executes this keyword | Y/-/- | not_working |
| Death Pits of Rath | silent | Whenever a creature is dealt damage, destroy it. It can't be regenerated. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Elvish Fury | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Jinxed Idol | silent | Sacrifice a creature: Target opponent gains control of this artifact. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rathi Dragon | silent | When this creature enters, sacrifice it unless you sacrifice two Mountains. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rootwater Matriarch | silent | {T}: Gain control of target creature for as long as that creature is enchanted. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shimmering Wings | silent | {U}: Return this Aura to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Soltari Priest | silent | Shadow | no machine in the engine executes this keyword | Y/-/- | not_working |
| Stun | silent | Target creature can't block this turn. Draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sudden Impact | silent | Sudden Impact deals damage to target player equal to the number of cards in that player's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Time Warp | silent | Target player takes an extra turn after this one. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vhati il-Dal | silent | {T}: Until end of turn, target creature has base power 1 or base toughness 1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Whispers of the Muse | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Altar of Dementia | notice | Sacrifice a creature: Target player mills cards equal to the sacrificed creature's power. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Booby Trap | unaudited | As this artifact enters, choose an opponent and a card name other than a basic land card name. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Choke | unaudited | Islands don't untap during their controllers' untap steps. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Marble Titan | unaudited | Creatures with power 3 or greater don't untap during their controllers' untap steps. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Root Maze | unaudited | Artifacts and lands enter tapped. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Sea Monster | unaudited | This creature can't attack unless defending player controls an Island. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Auratog | handled | Sacrifice an enchantment: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bottle Gnomes | handled | Sacrifice this creature: You gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Canopy Spider | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Canyon Wildcat | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Elite Javelineer | handled | Whenever this creature blocks, it deals 1 damage to target attacking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Emerald Medallion | handled | Green spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fighting Drake | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Harrow | handled | As an additional cost to cast this spell, sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jet Medallion | handled | Black spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Knight of Dusk | handled | {B}{B}: Destroy target creature blocking this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
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
| Skyshroud Ranger | handled | {T}: You may put a land card from your hand onto the battlefield. Activate only as a sorcery. | the engine reads this text and performs it | Y/-/- | not_tested |
| Staunch Defenders | handled | When this creature enters, you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trained Armodon | handled |  |  | Y/-/- | not_tested |
| Twitch | handled | You may tap or untap target artifact, creature, or land. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Verdant Force | handled | At the beginning of each upkeep, create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>7 cards</summary>

- Diabolic Edict
- Furnace of Rath
- Goblin Bombardment
- Mogg Fanatic
- Reflecting Pool
- Ruby Medallion
- Stalking Stones

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Buyback | Elvish Fury, Whispers of the Muse | 2 |
| Shadow | Dauthi Slayer, Soltari Priest | 2 |
| Artifacts and lands enter tapped. | Root Maze | 1 |
| As this artifact enters, choose an opponent and a card name other than a basic land card name. | Booby Trap | 1 |
| Creatures with power 3 or greater don't untap during their controllers' untap steps. | Marble Titan | 1 |
| Destroy all Islands. | Boil | 1 |
| {T}: Gain control of target creature for as long as that creature is enchanted. | Rootwater Matriarch | 1 |
| Islands don't untap during their controllers' untap steps. | Choke | 1 |
| {U}: Return this Aura to its owner's hand. | Shimmering Wings | 1 |
| Sacrifice a creature: Target opponent gains control of this artifact. | Jinxed Idol | 1 |
| Sacrifice a creature: Target player mills cards equal to the sacrificed creature's power. | Altar of Dementia | 1 |
| Sudden Impact deals damage to target player equal to the number of cards in that player's hand. | Sudden Impact | 1 |
| Target creature can't block this turn. Draw a card. | Stun | 1 |
| Target player takes an extra turn after this one. | Time Warp | 1 |
| This creature can't attack unless defending player controls an Island. | Sea Monster | 1 |
| {T}: Until end of turn, target creature has base power 1 or base toughness 1. | Vhati il-Dal | 1 |
| When this creature enters, sacrifice it unless you sacrifice two Mountains. | Rathi Dragon | 1 |
| Whenever a creature is dealt damage, destroy it. It can't be regenerated. | Death Pits of Rath | 1 |

## Notes



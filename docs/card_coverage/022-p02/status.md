# Portal Second Age (p02)

- Expansion: 022
- Set code: `p02`
- Release date: 1998-06-24
- Cards in scope (Modern/Pioneer/Standard-legal): 26

## Legality

| Format | Legal cards |
|---|---|
| Modern | 26 |
| Pioneer | 4 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 3.8% |
| Partial (unaudited) | 1 | 3.8% |
| Not tested (handled, untested) | 19 | 73.1% |
| Not working (silent / notice / error) | 5 | 19.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Denizen of the Deep | silent | When this creature enters, return each other creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Goblin Lore | silent | Draw four cards, then discard three cards at random. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Magma Giant | silent | When this creature enters, it deals 2 damage to each creature and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sea Drake | silent | When this creature enters, return two target lands you control to their owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sylvan Basilisk | silent | Whenever this creature becomes blocked by a creature, destroy that creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lone Wolf | unaudited | You may have this creature assign its combat damage as though it weren't blocked. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Angel of Mercy | handled | When this creature enters, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Angelic Wall | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Bear Cub | handled |  |  | Y/Y/Y | not_tested |
| Cruel Edict | handled | Target opponent sacrifices a creature of their choice. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Glider | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Matron | handled | When this creature enters, you may search your library for a Goblin card, reveal that card, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Mountaineer | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Goblin Piker | handled |  |  | Y/-/- | not_tested |
| Goblin Raider | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Norwood Ranger | handled |  |  | Y/-/- | not_tested |
| Ogre Taskmaster | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ravenous Rats | handled | When this creature enters, target opponent discards a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Righteous Charge | handled | Creatures you control get +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| River Bear | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Swarm of Rats | handled | Swarm of Rats's power is equal to the number of Rats you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tree Monkey | handled | Reach | machines/combat.py | Y/-/- | not_tested |
| Vampiric Spirit | handled | When this creature enters, you lose 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wild Griffin | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Wildfire | handled | Each player sacrifices four lands of their choice. Wildfire deals 4 damage to each creature. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Sleight of Hand

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| draw four cards, then discard three cards at random. | 1 | Goblin Lore | p02 |
| when ~ enters, it deals N damage to each creature and each player. | 1 | Magma Giant | p02 |
| when ~ enters, return each other creature you control to its owner's hand. | 1 | Denizen of the Deep | p02 |
| when ~ enters, return two target lands you control to their owner's hand. | 1 | Sea Drake | p02 |
| whenever ~ becomes blocked by a creature, destroy that creature. | 1 | Sylvan Basilisk | p02 |
| you may have ~ assign its combat damage as though it weren't blocked. | 1 | Lone Wolf | p02 |

## Notes



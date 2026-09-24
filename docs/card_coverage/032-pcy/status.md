# Prophecy (pcy)

- Expansion: 032
- Set code: `pcy`
- Release date: 2000-06-05
- Cards in scope (Modern/Pioneer/Standard-legal): 18

## Legality

| Format | Legal cards |
|---|---|
| Modern | 18 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 2 | 11.1% |
| Not tested (handled, untested) | 10 | 55.6% |
| Not working (silent / notice / error) | 6 | 33.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Avatar of Woe | silent | Fear | no machine in the engine executes this keyword | Y/-/- | not_working |
| Inflame | silent | Inflame deals 2 damage to each creature dealt damage this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jolrael, Empress of Beasts | silent | {2}{G}, {T}, Discard two cards: All lands target player controls become 3/3 creatures until end of turn. They're still lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lesser Gargadon | silent | Whenever this creature attacks or blocks, sacrifice a land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Panic Attack | silent | Up to three target creatures can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spiketail Hatchling | silent | Sacrifice this creature: Counter target spell unless its controller pays {1}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Avatar of Might | unaudited | If an opponent controls at least four more creatures than you, this spell costs {6} less to cast. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Living Terrain | unaudited | Enchanted land is a 5/6 green Treefolk creature that's still a land. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Coastal Hornclaw | handled | Sacrifice a land: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Diving Griffin | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Plague Wind | handled | Destroy all creatures you don't control. They can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ridgeline Rager | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Searing Wind | handled | Searing Wind deals 10 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spitting Spider | handled | Sacrifice a land: This creature deals 1 damage to each creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spore Frog | handled | Sacrifice this creature: Prevent all combat damage that would be dealt this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sword Dancer | handled | {W}{W}: Target attacking creature gets -1/-0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thrive | handled | Put a +1/+1 counter on each of X target creatures. | the engine reads this text and performs it | Y/-/- | not_tested |
| Whip Sergeant | handled | {R}: Target creature gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| {2}{G}, {T}, Discard two cards: All lands target player controls become 3/3 creatures until end of turn. They're still lands. | Jolrael, Empress of Beasts | 1 |
| Enchanted land is a 5/6 green Treefolk creature that's still a land. | Living Terrain | 1 |
| Fear | Avatar of Woe | 1 |
| If an opponent controls at least four more creatures than you, this spell costs {6} less to cast. | Avatar of Might | 1 |
| Inflame deals 2 damage to each creature dealt damage this turn. | Inflame | 1 |
| Sacrifice this creature: Counter target spell unless its controller pays {1}. | Spiketail Hatchling | 1 |
| Up to three target creatures can't block this turn. | Panic Attack | 1 |
| Whenever this creature attacks or blocks, sacrifice a land. | Lesser Gargadon | 1 |

## Notes



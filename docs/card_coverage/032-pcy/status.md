# Prophecy (pcy)

- Expansion: 032
- Set code: `pcy`
- Release date: 2000-06-05
- Cards in scope (Modern/Pioneer/Standard-legal): 19

## Legality

| Format | Legal cards |
|---|---|
| Modern | 19 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 1 | 5.3% |
| Works (untested) | 10 | 52.6% |
| Partial (unaudited) | 4 | 21.1% |
| Not working | 4 | 21.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Jolrael, Empress of Beasts | silent | {2}{G}, {T}, Discard two cards: All lands target player controls become 3/3 creatures until end of turn. They're still lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lesser Gargadon | silent | Whenever this creature attacks or blocks, sacrifice a land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Panic Attack | silent | Up to three target creatures can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spiketail Hatchling | silent | Sacrifice this creature: Counter target spell unless its controller pays {1}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Avatar of Hope | unaudited | If you have 3 or less life, this spell costs {6} less to cast. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Avatar of Might | unaudited | If an opponent controls at least four more creatures than you, this spell costs {6} less to cast. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Avatar of Woe | unaudited | If there are ten or more creature cards total in all graveyards, this spell costs {6} less to cast. | a static ability no support check audits - not verified either way | Y/-/- | partial |
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
<summary>1 cards</summary>

- Inflame

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| enchanted land is a N/N green treefolk creature that's still a land. | 1 | Living Terrain | pcy |
| if an opponent controls at least four more creatures than you, ~ costs {M} less to cast. | 1 | Avatar of Might | pcy |
| if there are ten or more creature cards total in all graveyards, ~ costs {M} less to cast. | 1 | Avatar of Woe | pcy |
| if you have N or less life, ~ costs {M} less to cast. | 1 | Avatar of Hope | pcy |
| sacrifice ~: counter target spell unless its controller pays {M}. | 1 | Spiketail Hatchling | pcy |
| up to three target creatures can't block ~. | 1 | Panic Attack | pcy |
| whenever ~ attacks or blocks, sacrifice a land. | 1 | Lesser Gargadon | pcy |
| {M}{M}, {M}, discard two cards: all lands target player controls become N/N creatures until end of turn. they're still lands. | 1 | Jolrael, Empress of Beasts | pcy |

## Notes



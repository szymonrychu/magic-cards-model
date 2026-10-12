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
| Tested | 5 | 26.3% |
| Works (untested) | 12 | 63.2% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 2 | 10.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Jolrael, Empress of Beasts | silent | {2}{G}, {T}, Discard two cards: All lands target player controls become 3/3 creatures until end of turn. They're still lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Panic Attack | silent | Up to three target creatures can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Coastal Hornclaw | handled | Sacrifice a land: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Diving Griffin | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Lesser Gargadon | handled | Whenever this creature attacks or blocks, sacrifice a land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Plague Wind | handled | Destroy all creatures you don't control. They can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ridgeline Rager | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Searing Wind | handled | Searing Wind deals 10 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spiketail Hatchling | handled | Sacrifice this creature: Counter target spell unless its controller pays {1}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spitting Spider | handled | Sacrifice a land: This creature deals 1 damage to each creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spore Frog | handled | Sacrifice this creature: Prevent all combat damage that would be dealt this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sword Dancer | handled | {W}{W}: Target attacking creature gets -1/-0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thrive | handled | Put a +1/+1 counter on each of X target creatures. | the engine reads this text and performs it | Y/-/- | not_tested |
| Whip Sergeant | handled | {R}: Target creature gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>5 cards</summary>

- Avatar of Hope
- Avatar of Might
- Avatar of Woe
- Inflame
- Living Terrain

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| up to three target creatures can't block ~. | 1 | Panic Attack | pcy |
| {M}{M}, {M}, discard two cards: all lands target player controls become N/N creatures until end of turn. they're still lands. | 1 | Jolrael, Empress of Beasts | pcy |

## Notes



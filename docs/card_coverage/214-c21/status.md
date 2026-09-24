# Commander 2021 (c21)

- Expansion: 214
- Set code: `c21`
- Release date: 2021-04-23
- Cards in scope (Modern/Pioneer/Standard-legal): 3

## Legality

| Format | Legal cards |
|---|---|
| Modern | 3 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 0 | 0.0% |
| Works (untested) | 1 | 33.3% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 2 | 66.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Cursed Mirror | silent | As this artifact enters, you may have it become a copy of any creature on the battlefield until end of turn, except it has haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Laelia, the Blade Reforged | silent | Whenever one or more cards are put into exile from your library and/or your graveyard, put a +1/+1 counter on Laelia. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Angel of the Ruins | handled | When this creature enters, exile up to two target artifacts and/or enchantments. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| as ~ enters, you may have it become a copy of any creature on the battlefield until end of turn, except it has haste. | 1 | Cursed Mirror | c21 |
| whenever one or more cards are put into exile from your library and/or your graveyard, put a +N/+N counter on laelia. | 1 | Laelia, the Blade Reforged | c21 |

## Notes



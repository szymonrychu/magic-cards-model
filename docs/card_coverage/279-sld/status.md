# Secret Lair Drop (sld)

- Expansion: 279
- Set code: `sld`
- Release date: 2020-10-13
- Cards in scope (Modern/Pioneer/Standard-legal): 4

## Legality

| Format | Legal cards |
|---|---|
| Modern | 4 |
| Pioneer | 4 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 25.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 1 | 25.0% |
| Not working (silent / notice / error) | 2 | 50.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Nexus of Fate | silent | Take an extra turn after this one. If Nexus of Fate would be put into a graveyard from anywhere, reveal Nexus of Fate and shuffle it into its owner's library in | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tezzeret, Master of the Bridge | silent | +2: Tezzeret deals X damage to each opponent, where X is the number of artifacts you control. You gain X life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rin and Seri, Inseparable | handled | Whenever you cast a Dog spell, create a 1/1 green Cat creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Voja, Jaws of the Conclave

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| +N: tezzeret deals N damage to each opponent, where N is the number of artifacts you control. you gain N life. | 1 | Tezzeret, Master of the Bridge | sld |
| take an extra turn after ~. if ~ would be put into a graveyard from anywhere, reveal ~ and shuffle it into its owner's library instead. | 1 | Nexus of Fate | sld |

## Notes



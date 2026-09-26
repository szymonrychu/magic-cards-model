# Secret Lair Drop (sld)

- Expansion: 279
- Set code: `sld`
- Release date: 2019-12-08
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 5 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 1 | 16.7% |
| Works (untested) | 3 | 50.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 2 | 33.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Nexus of Fate | silent | Take an extra turn after this one. If Nexus of Fate would be put into a graveyard from anywhere, reveal Nexus of Fate and shuffle it into its owner's library in | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tezzeret, Master of the Bridge | silent | +2: Tezzeret deals X damage to each opponent, where X is the number of artifacts you control. You gain X life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Angel of Finality | handled | When this creature enters, exile target player's graveyard. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Angel of the Ruins | handled | When this creature enters, exile up to two target artifacts and/or enchantments. | the engine reads this text and performs it | Y/-/- | not_tested |
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



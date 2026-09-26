# Duel Decks: Speed vs. Cunning (ddn)

- Expansion: 154
- Set code: `ddn`
- Release date: 2014-09-05
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 6 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 0 | 0.0% |
| Works (untested) | 5 | 83.3% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 16.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Thousand Winds | silent | When this creature is turned face up, return all other tapped creatures to their owners' hands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Jeskai Elder | handled | Whenever this creature deals combat damage to a player, you may draw a card. If you do, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Heart-Piercer | handled | Raid — When this creature enters, if you attacked this turn, this creature deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mystic Monastery | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Nomad Outpost | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Zurgo Helmsmasher | handled | Zurgo attacks each combat if able. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| when ~ is turned face up, return all other tapped creatures to their owners' hands. | 1 | Thousand Winds | ddn |

## Notes



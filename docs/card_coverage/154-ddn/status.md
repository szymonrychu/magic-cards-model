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
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 16.7% |
| Not tested (handled, untested) | 4 | 66.7% |
| Not working (silent / notice / error) | 1 | 16.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Thousand Winds | silent | When this creature is turned face up, return all other tapped creatures to their owners' hands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Zurgo Helmsmasher | unaudited | Zurgo attacks each combat if able. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Jeskai Elder | handled | Whenever this creature deals combat damage to a player, you may draw a card. If you do, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Heart-Piercer | handled | Raid — When this creature enters, if you attacked this turn, this creature deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mystic Monastery | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Nomad Outpost | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| When this creature is turned face up, return all other tapped creatures to their owners' hands. | Thousand Winds | 1 |
| Zurgo attacks each combat if able. | Zurgo Helmsmasher | 1 |

## Notes



# Magic 2014 Promos (pm14)

- Expansion: 138
- Set code: `pm14`
- Release date: 2013-07-18
- Cards in scope (Modern/Pioneer/Standard-legal): 4

## Legality

| Format | Legal cards |
|---|---|
| Modern | 4 |
| Pioneer | 4 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 50.0% |
| Not working (silent / notice / error) | 2 | 50.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Goblin Diplomats | silent | {T}: Each creature attacks this turn if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Megantic Sliver | silent | Sliver creatures you control get +3/+3. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Colossal Whale | handled | Whenever this creature attacks, you may exile target creature defending player controls until this creature leaves the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hive Stirrings | handled | Create two 1/1 colorless Sliver creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| {T}: Each creature attacks this turn if able. | Goblin Diplomats | 1 |
| Sliver creatures you control get +3/+3. | Megantic Sliver | 1 |

## Notes



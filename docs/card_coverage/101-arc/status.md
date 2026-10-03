# Archenemy (arc)

- Expansion: 101
- Set code: `arc`
- Release date: 2010-06-18
- Cards in scope (Modern/Pioneer/Standard-legal): 4

## Legality

| Format | Legal cards |
|---|---|
| Modern | 4 |
| Pioneer | 3 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 0 | 0.0% |
| Works (untested) | 3 | 75.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 25.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Sorcerer's Strongbox | silent | {2}, {T}: Flip a coin. If you win the flip, sacrifice this artifact and draw three cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Chandra's Outrage | handled | Chandra's Outrage deals 4 damage to target creature and 2 damage to that creature's controller. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Plummet | handled | Destroy target creature with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reassembling Skeleton | handled | {1}{B}: Return this card from your graveyard to the battlefield tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| {M}, {M}: flip a coin. if you win the flip, sacrifice ~ and draw three cards. | 1 | Sorcerer's Strongbox | arc |

## Notes



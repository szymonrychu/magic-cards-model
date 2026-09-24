# Friday Night Magic 2015 (f15)

- Expansion: 157
- Set code: `f15`
- Release date: 2015-01-01
- Cards in scope (Modern/Pioneer/Standard-legal): 5

## Legality

| Format | Legal cards |
|---|---|
| Modern | 5 |
| Pioneer | 5 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 20.0% |
| Partial (unaudited) | 1 | 20.0% |
| Not tested (handled, untested) | 2 | 40.0% |
| Not working (silent / notice / error) | 1 | 20.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Abzan Beastmaster | silent | At the beginning of your upkeep, draw a card if you control the creature with the greatest toughness or tied for the greatest toughness. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Orator of Ojutai | unaudited | As an additional cost to cast this spell, you may reveal a Dragon card from your hand. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Frost Walker | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Roast | handled | Roast deals 5 damage to target creature without flying. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Anticipate

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| As an additional cost to cast this spell, you may reveal a Dragon card from your hand. | Orator of Ojutai | 1 |
| At the beginning of your upkeep, draw a card if you control the creature with the greatest toughness or tied for the greatest toughness. | Abzan Beastmaster | 1 |

## Notes



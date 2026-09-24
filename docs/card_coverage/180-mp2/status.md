# Amonkhet Invocations (mp2)

- Expansion: 180
- Set code: `mp2`
- Release date: 2017-04-28
- Cards in scope (Modern/Pioneer/Standard-legal): 3

## Legality

| Format | Legal cards |
|---|---|
| Modern | 3 |
| Pioneer | 3 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 66.7% |
| Not working (silent / notice / error) | 1 | 33.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| The Scarab God | silent | At the beginning of your upkeep, each opponent loses X life and you scry X, where X is the number of Zombies you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| The Locust God | handled | Whenever you draw a card, create a 1/1 blue and red Insect creature token with flying and haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| The Scorpion God | handled | Whenever a creature with a -1/-1 counter on it dies, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of your upkeep, each opponent loses X life and you scry X, where X is the number of Zombies you control. | The Scarab God | 1 |

## Notes



# Amonkhet Invocations (mp2)

- Expansion: 180
- Set code: `mp2`
- Release date: 2017-04-28
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
| Tested | 1 | 25.0% |
| Works (untested) | 2 | 50.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 25.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| The Scarab God | notice | {2}{U}{B}: Exile target creature card from a graveyard. Create a token that's a copy of it, except it's a 4/4 black Zombie. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| The Locust God | handled | Whenever you draw a card, create a 1/1 blue and red Insect creature token with flying and haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| The Scorpion God | handled | Whenever a creature with a -1/-1 counter on it dies, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Containment Priest

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| {M}{M}{M}: exile target creature card from a graveyard. create a token that"..."s a N/N black zombie. | 1 | The Scarab God | mp2 |

## Notes



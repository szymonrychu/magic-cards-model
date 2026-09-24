# Game Day Promos (gdy)

- Expansion: 228
- Set code: `gdy`
- Release date: 2022-04-08
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
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 1 | 20.0% |
| Not working (silent / notice / error) | 3 | 60.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| All-Seeing Arbiter | silent | Whenever you discard a card, target creature an opponent controls gets -X/-0 until your next turn, where X is the number of different mana values among cards in | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Surge Engine | silent | {U}: This creature loses defender and gains "This creature can't be blocked." | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Workshop Warchief | silent | Blitz | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Shivan Devastator | handled | This creature enters with X +1/+1 counters on it. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Recruitment Officer

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Blitz | Workshop Warchief | 1 |
| {U}: This creature loses defender and gains "This creature can't be blocked." | Surge Engine | 1 |
| Whenever you discard a card, target creature an opponent controls gets -X/-0 until your next turn, where X is the number of different mana values among cards in | All-Seeing Arbiter | 1 |

## Notes



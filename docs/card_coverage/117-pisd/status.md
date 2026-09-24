# Innistrad Promos (pisd)

- Expansion: 117
- Set code: `pisd`
- Release date: 2011-09-24
- Cards in scope (Modern/Pioneer/Standard-legal): 5

## Legality

| Format | Legal cards |
|---|---|
| Modern | 5 |
| Pioneer | 1 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 20.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 40.0% |
| Not working (silent / notice / error) | 2 | 40.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Elite Inquisitor | silent | First strike, vigilance Protection from Vampires, from Werewolves, and from Zombies | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mayor of Avabruck // Howlpack Alpha | silent | Other Human creatures you control get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Devil's Play | handled | Devil's Play deals X damage to any target. Flashback {X}{R}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Diregraf Ghoul | handled | This creature enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Ludevic's Test Subject // Ludevic's Abomination

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| First strike, vigilance Protection from Vampires, from Werewolves, and from Zombies | Elite Inquisitor | 1 |
| Other Human creatures you control get +1/+1. | Mayor of Avabruck // Howlpack Alpha | 1 |

## Notes



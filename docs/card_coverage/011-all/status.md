# Alliances (all)

- Expansion: 011
- Set code: `all`
- Release date: 1996-06-10
- Cards in scope (Modern/Pioneer/Standard-legal): 9

## Legality

| Format | Legal cards |
|---|---|
| Modern | 9 |
| Pioneer | 2 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 11.1% |
| Not tested (handled, untested) | 6 | 66.7% |
| Not working (silent / notice / error) | 2 | 22.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Hail Storm | silent | Hail Storm deals 2 damage to each attacking creature and 1 damage to you and each creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Swamp Mosquito | silent | Whenever this creature attacks and isn't blocked, defending player gets a poison counter. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Elvish Bard | unaudited | All creatures able to block this creature do so. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Aesthir Glider | handled | This creature can't block. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gorilla Shaman | handled | {X}{X}{1}: Destroy target noncreature artifact with mana value X. | the engine reads this text and performs it | Y/-/- | not_tested |
| Guerrilla Tactics | handled | Guerrilla Tactics deals 2 damage to any target. When a spell or ability an opponent controls causes you to discard this card, it deals 4 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pillage | handled | Destroy target artifact or land. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Reprisal | handled | Destroy target creature with power 4 or greater. It can't be regenerated. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Storm Crow | handled | Flying | machines/combat.py | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| All creatures able to block this creature do so. | Elvish Bard | 1 |
| Hail Storm deals 2 damage to each attacking creature and 1 damage to you and each creature you control. | Hail Storm | 1 |
| Whenever this creature attacks and isn't blocked, defending player gets a poison counter. | Swamp Mosquito | 1 |

## Notes



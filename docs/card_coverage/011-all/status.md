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
| Tested | 1 | 11.1% |
| Works (untested) | 6 | 66.7% |
| Partial (unaudited) | 1 | 11.1% |
| Not working | 1 | 11.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
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
<summary>1 cards</summary>

- Hail Storm

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| all creatures able to block ~ do so. | 1 | Elvish Bard | all |
| whenever ~ attacks and isn't blocked, defending player gets a poison counter. | 1 | Swamp Mosquito | all |

## Notes



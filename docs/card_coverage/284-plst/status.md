# The List (plst)

- Expansion: 284
- Set code: `plst`
- Release date: 2019-11-07
- Cards in scope (Modern/Pioneer/Standard-legal): 4

## Legality

| Format | Legal cards |
|---|---|
| Modern | 4 |
| Pioneer | 2 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 1 | 25.0% |
| Works (untested) | 1 | 25.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 2 | 50.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Cursed Mirror | silent | As this artifact enters, you may have it become a copy of any creature on the battlefield until end of turn, except it has haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| The Haunt of Hightower | silent | Whenever The Haunt of Hightower attacks, defending player discards a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Jazal Goldmane | handled | {3}{W}{W}: Attacking creatures you control get +X/+X until end of turn, where X is the number of attacking creatures. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- K'rrik, Son of Yawgmoth

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| as ~ enters, you may have it become a copy of any creature on the battlefield until end of turn, except it has haste. | 1 | Cursed Mirror | plst |
| whenever ~ attacks, defending player discards a card. | 1 | The Haunt of Hightower | plst |

## Notes



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
| Tested | 0 | 0.0% |
| Works (untested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 25.0% |
| Not working | 3 | 75.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Cursed Mirror | silent | As this artifact enters, you may have it become a copy of any creature on the battlefield until end of turn, except it has haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jazal Goldmane | silent | {3}{W}{W}: Attacking creatures you control get +X/+X until end of turn, where X is the number of attacking creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| The Haunt of Hightower | silent | Whenever The Haunt of Hightower attacks, defending player discards a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| K'rrik, Son of Yawgmoth | unaudited | For each {B} in a cost, you may pay 2 life rather than pay that mana. | a static ability no support check audits - not verified either way | Y/-/- | partial |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| as ~ enters, you may have it become a copy of any creature on the battlefield until end of turn, except it has haste. | 1 | Cursed Mirror | plst |
| for each {M} in a cost, you may pay N life rather than pay that mana. | 1 | K'rrik, Son of Yawgmoth | plst |
| whenever ~ attacks, defending player discards a card. | 1 | The Haunt of Hightower | plst |
| {M}{M}{M}: attacking creatures you control get +N/+N until end of turn, where N is the number of attacking creatures. | 1 | Jazal Goldmane | plst |

## Notes



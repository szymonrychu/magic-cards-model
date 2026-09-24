# Commander 2014 (c14)

- Expansion: 156
- Set code: `c14`
- Release date: 2014-11-07
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
| Full (handled + tested) | 1 | 25.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 50.0% |
| Not working (silent / notice / error) | 1 | 25.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Jazal Goldmane | silent | {3}{W}{W}: Attacking creatures you control get +X/+X until end of turn, where X is the number of attacking creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Reef Worm | handled | When this creature dies, create a 3/3 blue Fish creature token with "When this token dies, create a 6/6 blue Whale creature token with 'When this token dies, cr | the engine reads this text and performs it | Y/-/- | not_tested |
| Titania, Protector of Argoth | handled | When Titania enters, return target land card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Containment Priest

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| {M}{M}{M}: attacking creatures you control get +N/+N until end of turn, where N is the number of attacking creatures. | 1 | Jazal Goldmane | c14 |

## Notes



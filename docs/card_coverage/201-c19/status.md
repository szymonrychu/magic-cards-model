# Commander 2019 (c19)

- Expansion: 201
- Set code: `c19`
- Release date: 2019-08-23
- Cards in scope (Modern/Pioneer/Standard-legal): 3

## Legality

| Format | Legal cards |
|---|---|
| Modern | 3 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 33.3% |
| Not tested (handled, untested) | 0 | 0.0% |
| Not working (silent / notice / error) | 2 | 66.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Chainer, Nightmare Adept | silent | Discard a card: You may cast a creature spell from your graveyard this turn. Activate only once each turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sevinne's Reclamation | silent | Return target permanent card with mana value 3 or less from your graveyard to the battlefield. If this spell was cast from a graveyard, you may copy this spell  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| K'rrik, Son of Yawgmoth | unaudited | For each {B} in a cost, you may pay 2 life rather than pay that mana. | a static ability no support check audits - not verified either way | Y/-/- | partial |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| discard a card: you may cast a creature spell from your graveyard ~. activate only once each turn. | 1 | Chainer, Nightmare Adept | c19 |
| for each {M} in a cost, you may pay N life rather than pay that mana. | 1 | K'rrik, Son of Yawgmoth | c19 |
| return target permanent card with mana value N or less from your graveyard to the battlefield. if ~ was cast from a graveyard, you may copy ~ and may choose a n | 1 | Sevinne's Reclamation | c19 |

## Notes



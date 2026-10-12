# Arabian Nights (arn)

- Expansion: 003
- Set code: `arn`
- Release date: 1993-12-17
- Cards in scope (Modern/Pioneer/Standard-legal): 13

## Legality

| Format | Legal cards |
|---|---|
| Modern | 13 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 3 | 23.1% |
| Works (untested) | 8 | 61.5% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 2 | 15.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Sindbad | silent | {T}: Draw a card and reveal it. If it isn't a land card, discard it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rukh Egg | notice | When this creature dies, create a 4/4 red Bird creature token with flying at the beginning of the next end step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Aladdin's Ring | handled | {8}, {T}: This artifact deals 4 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| City of Brass | handled | Whenever this land becomes tapped, it deals 1 damage to you. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dancing Scimitar | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Fishliver Oil | handled | Enchanted creature has islandwalk. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flying Carpet | handled | {2}, {T}: Target creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flying Men | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Moorish Cavalry | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Unstable Mutation | handled | Enchanted creature gets +3/+3. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>3 cards</summary>

- Dandân
- Desert
- Kird Ape

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| when ~ dies, create a N/N red bird creature token with flying at the beginning of the next end step. | 1 | Rukh Egg | arn |
| {M}: draw a card and reveal it. if it isn't a land card, discard it. | 1 | Sindbad | arn |

## Notes



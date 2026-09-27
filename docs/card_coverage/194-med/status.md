# Mythic Edition (med)

- Expansion: 194
- Set code: `med`
- Release date: 2019-01-25
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
| Tested | 0 | 0.0% |
| Works (untested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 25.0% |
| Not working | 3 | 75.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Domri, Chaos Bringer | silent | +1: Add {R} or {G}. If that mana is spent on a creature spell, it gains riot. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kaya, Orzhov Usurper | silent | +1: Exile up to two target cards from a single graveyard. You gain 2 life if at least one creature card was exiled this way. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nicol Bolas, Dragon-God | silent | +1: You draw a card. Each opponent exiles a card from their hand or a permanent they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gideon Blackblade | unaudited | Prevent all damage that would be dealt to Gideon Blackblade during your turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| +N: add {M} or {M}. if that mana is spent on a creature spell, it gains riot. | 1 | Domri, Chaos Bringer | med |
| +N: exile up to two target cards from a single graveyard. you gain N life if at least one creature card was exiled ~. | 1 | Kaya, Orzhov Usurper | med |
| +N: you draw a card. each opponent exiles a card from their hand or a permanent they control. | 1 | Nicol Bolas, Dragon-God | med |
| prevent all damage that would be dealt to ~ during your turn. | 1 | Gideon Blackblade | med |

## Notes



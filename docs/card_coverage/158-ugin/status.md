# Ugin's Fate (ugin)

- Expansion: 158
- Set code: `ugin`
- Release date: 2015-01-17
- Cards in scope (Modern/Pioneer/Standard-legal): 13

## Legality

| Format | Legal cards |
|---|---|
| Modern | 13 |
| Pioneer | 13 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 7.7% |
| Partial (unaudited) | 1 | 7.7% |
| Not tested (handled, untested) | 3 | 23.1% |
| Not working (silent / notice / error) | 8 | 61.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Fierce Invocation | silent | Manifest the top card of your library, then put two +1/+1 counters on it. (To manifest a card, put it onto the battlefield face down as a 2/2 creature. Turn it  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Formless Nurturing | silent | Manifest the top card of your library, then put a +1/+1 counter on it. (To manifest a card, put it onto the battlefield face down as a 2/2 creature. Turn it fac | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Jeskai Infiltrator | silent | When this creature deals combat damage to a player, exile it and the top card of your library in a face-down pile, shuffle that pile, then manifest those cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ugin's Construct | silent | When this creature enters, sacrifice a permanent that's one or more colors. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ugin, the Spirit Dragon | silent | −X: Exile each permanent with mana value X or less that's one or more colors. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Wildcall | silent | Manifest the top card of your library, then put X +1/+1 counters on it. (To manifest a card, put it onto the battlefield face down as a 2/2 creature. Turn it fa | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Write into Being | silent | Look at the top two cards of your library. Manifest one of those cards, then put the other on the top or bottom of your library. (To manifest a card, put it ont | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Reality Shift | notice | Exile target creature. Its controller manifests the top card of their library. (That player puts the top card of their library onto the battlefield face down as | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Hewed Stone Retainers | unaudited | Cast this spell only if you've cast another spell this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Arashin War Beast | handled | Whenever this creature deals combat damage to one or more blocking creatures, manifest the top card of your library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Soul Summons | handled | Manifest the top card of your library. (Put it onto the battlefield face down as a 2/2 creature. Turn it face up any time for its mana cost if it's a creature c | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sultai Emissary | handled | When this creature dies, manifest the top card of your library. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Mastery of the Unseen

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Manifest the top card of your library, then put two +1/+1 counters on it. (To manifest a card, put it onto the battlefield face down as a 2/2 creature. Turn it  | Fierce Invocation, Formless Nurturing, Wildcall | 3 |
| Cast this spell only if you've cast another spell this turn. | Hewed Stone Retainers | 1 |
| Exile target creature. Its controller manifests the top card of their library. (That player puts the top card of their library onto the battlefield face down as | Reality Shift | 1 |
| Look at the top two cards of your library. Manifest one of those cards, then put the other on the top or bottom of your library. (To manifest a card, put it ont | Write into Being | 1 |
| When this creature deals combat damage to a player, exile it and the top card of your library in a face-down pile, shuffle that pile, then manifest those cards. | Jeskai Infiltrator | 1 |
| When this creature enters, sacrifice a permanent that's one or more colors. | Ugin's Construct | 1 |
| −X: Exile each permanent with mana value X or less that's one or more colors. | Ugin, the Spirit Dragon | 1 |

## Notes



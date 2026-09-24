# Born of the Gods Promos (pbng)

- Expansion: 146
- Set code: `pbng`
- Release date: 2014-02-01
- Cards in scope (Modern/Pioneer/Standard-legal): 9

## Legality

| Format | Legal cards |
|---|---|
| Modern | 9 |
| Pioneer | 9 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 2 | 22.2% |
| Partial (unaudited) | 1 | 11.1% |
| Not tested (handled, untested) | 2 | 22.2% |
| Not working (silent / notice / error) | 4 | 44.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Arbiter of the Ideal | silent | Inspired — Whenever this creature becomes untapped, reveal the top card of your library. If it's an artifact, creature, or land card, you may put it onto the ba | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Forgestoker Dragon | silent | {1}{R}: This creature deals 1 damage to target creature. That creature can't block this combat. Activate only if this creature is attacking. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nessian Wilds Ravager | silent | When this creature enters, if tribute wasn't paid, you may have this creature fight another target creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fated Conflagration | notice | Fated Conflagration deals 5 damage to target creature or planeswalker. If it's your turn, scry 2. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Tromokratis | unaudited | Tromokratis can't be blocked unless all creatures defending player controls block it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Eater of Hope | handled | {B}, Sacrifice another creature: Regenerate this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Silent Sentinel | handled | Whenever this creature attacks, you may return target enchantment card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Kiora's Follower
- Pain Seer

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Fated Conflagration deals 5 damage to target creature or planeswalker. If it's your turn, scry 2. | Fated Conflagration | 1 |
| Inspired — Whenever this creature becomes untapped, reveal the top card of your library. If it's an artifact, creature, or land card, you may put it onto the ba | Arbiter of the Ideal | 1 |
| {1}{R}: This creature deals 1 damage to target creature. That creature can't block this combat. Activate only if this creature is attacking. | Forgestoker Dragon | 1 |
| Tromokratis can't be blocked unless all creatures defending player controls block it. | Tromokratis | 1 |
| When this creature enters, if tribute wasn't paid, you may have this creature fight another target creature. | Nessian Wilds Ravager | 1 |

## Notes



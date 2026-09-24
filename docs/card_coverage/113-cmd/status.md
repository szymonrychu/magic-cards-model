# Commander 2011 (cmd)

- Expansion: 113
- Set code: `cmd`
- Release date: 2011-06-17
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 3 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 16.7% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 3 | 50.0% |
| Not working (silent / notice / error) | 2 | 33.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Kaalia of the Vast | silent | Whenever Kaalia attacks an opponent, you may put an Angel, Demon, or Dragon creature card from your hand onto the battlefield tapped and attacking that opponent | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scavenging Ooze | notice | {G}: Exile target card from a graveyard. If it was a creature card, put a +1/+1 counter on this creature and you gain 1 life. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Command Tower | handled |  |  | Y/Y/- | not_tested |
| Hornet Queen | handled | When this creature enters, create four 1/1 green Insect creature tokens with flying and deathtouch. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Soul Snare | handled | {W}, Sacrifice this enchantment: Exile target creature that's attacking you or a planeswalker you control. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Flusterstorm

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| whenever kaalia attacks an opponent, you may put an angel, demon, or dragon creature card from your hand onto the battlefield tapped and attacking that opponent | 1 | Kaalia of the Vast | cmd |
| {M}: exile target card from a graveyard. if it was a creature card, put a +N/+N counter on ~ and you gain N life. | 1 | Scavenging Ooze | cmd |

## Notes



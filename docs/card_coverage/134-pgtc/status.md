# Gatecrash Promos (pgtc)

- Expansion: 134
- Set code: `pgtc`
- Release date: 2013-01-26
- Cards in scope (Modern/Pioneer/Standard-legal): 9

## Legality

| Format | Legal cards |
|---|---|
| Modern | 9 |
| Pioneer | 9 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 4 | 44.4% |
| Not working (silent / notice / error) | 5 | 55.6% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Consuming Aberration | silent | Consuming Aberration's power and toughness are each equal to the number of cards in your opponents' graveyards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Fathom Mage | silent | Whenever a +1/+1 counter is put on this creature, you may draw a card. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Nightveil Specter | silent | Whenever this creature deals combat damage to a player, that player exiles the top card of their library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Treasury Thrull | silent | Extort | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Zameck Guildmage | silent | {G}{U}: This turn, each creature you control enters with an additional +1/+1 counter on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Firemane Avenger | handled | Battalion — Whenever this creature and at least two other creatures attack, this creature deals 3 damage to any target and you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Foundry Champion | handled | When this creature enters, it deals damage to any target equal to the number of creatures you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rubblehulk | handled | Rubblehulk's power and toughness are each equal to the number of lands you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skarrg Goliath | handled | Bloodrush — {5}{G}{G}, Discard this card: Target attacking creature gets +9/+9 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Consuming Aberration's power and toughness are each equal to the number of cards in your opponents' graveyards. | Consuming Aberration | 1 |
| Extort | Treasury Thrull | 1 |
| {G}{U}: This turn, each creature you control enters with an additional +1/+1 counter on it. | Zameck Guildmage | 1 |
| Whenever a +1/+1 counter is put on this creature, you may draw a card. | Fathom Mage | 1 |
| Whenever this creature deals combat damage to a player, that player exiles the top card of their library. | Nightveil Specter | 1 |

## Notes



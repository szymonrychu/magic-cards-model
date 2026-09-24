# Exodus (exo)

- Expansion: 021
- Set code: `exo`
- Release date: 1998-06-15
- Cards in scope (Modern/Pioneer/Standard-legal): 23

## Legality

| Format | Legal cards |
|---|---|
| Modern | 23 |
| Pioneer | 4 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 2 | 8.7% |
| Partial (unaudited) | 2 | 8.7% |
| Not tested (handled, untested) | 12 | 52.2% |
| Not working (silent / notice / error) | 7 | 30.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Coat of Arms | silent | Each creature gets +1/+1 for each other creature on the battlefield that shares at least one creature type with it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Elvish Berserker | silent | Whenever this creature becomes blocked, it gets +1/+1 until end of turn for each creature blocking it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Maniacal Rage | silent | Enchanted creature gets +2/+2 and can't block. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Pandemonium | silent | Whenever a creature enters, that creature's controller may have it deal damage equal to its power to any target of their choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reclaim | silent | Put target card from your graveyard on top of your library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Reconnaissance | silent | {0}: Remove target attacking creature you control from combat and untap it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Thrull Surgeon | notice | {1}{B}, Sacrifice this creature: Look at target player's hand and choose a card from it. That player discards that card. Activate only as a sorcery. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| High Ground | unaudited | Each creature you control can block an additional creature each combat. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Spellbook | unaudited | You have no maximum hand size. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Anarchist | handled | When this creature enters, you may return target sorcery card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Curiosity | handled | Whenever enchanted creature deals damage to an opponent, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mindless Automaton | handled | This creature enters with two +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mirri, Cat Warrior | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Nausea | handled | All creatures get -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Paladin en-Vec | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Peace of Mind | handled | {W}, Discard a card: You gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Robe of Mirrors | handled | Enchanted creature has shroud. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seismic Assault | handled | Discard a land card: This enchantment deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Standing Troops | handled | Vigilance | machines/combat.py | Y/Y/- | not_tested |
| Treasure Hunter | handled | When this creature enters, you may return target artifact card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Treasure Trove | handled | {2}{U}{U}: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Merfolk Looter
- Soul Warden

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Each creature gets +1/+1 for each other creature on the battlefield that shares at least one creature type with it. | Coat of Arms | 1 |
| Each creature you control can block an additional creature each combat. | High Ground | 1 |
| Enchanted creature gets +2/+2 and can't block. | Maniacal Rage | 1 |
| Put target card from your graveyard on top of your library. | Reclaim | 1 |
| {0}: Remove target attacking creature you control from combat and untap it. | Reconnaissance | 1 |
| {1}{B}, Sacrifice this creature: Look at target player's hand and choose a card from it. That player discards that card. Activate only as a sorcery. | Thrull Surgeon | 1 |
| Whenever a creature enters, that creature's controller may have it deal damage equal to its power to any target of their choice. | Pandemonium | 1 |
| Whenever this creature becomes blocked, it gets +1/+1 until end of turn for each creature blocking it. | Elvish Berserker | 1 |
| You have no maximum hand size. | Spellbook | 1 |

## Notes



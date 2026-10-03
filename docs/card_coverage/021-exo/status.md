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
| Tested | 2 | 8.7% |
| Works (untested) | 13 | 56.5% |
| Partial (unaudited) | 1 | 4.3% |
| Not working | 7 | 30.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Coat of Arms | silent | Each creature gets +1/+1 for each other creature on the battlefield that shares at least one creature type with it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Elvish Berserker | silent | Whenever this creature becomes blocked, it gets +1/+1 until end of turn for each creature blocking it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Maniacal Rage | silent | Enchanted creature gets +2/+2 and can't block. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Pandemonium | silent | Whenever a creature enters, that creature's controller may have it deal damage equal to its power to any target of their choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reconnaissance | silent | {0}: Remove target attacking creature you control from combat and untap it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Paladin en-Vec | notice | Protection | protection from a quality the engine does not read: red (This creature deals combat damage before creatures without first strike | Y/-/- | not_working |
| Thrull Surgeon | notice | {1}{B}, Sacrifice this creature: Look at target player's hand and choose a card from it. That player discards that card. Activate only as a sorcery. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| High Ground | unaudited | Each creature you control can block an additional creature each combat. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Anarchist | handled | When this creature enters, you may return target sorcery card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Curiosity | handled | Whenever enchanted creature deals damage to an opponent, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mindless Automaton | handled | This creature enters with two +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mirri, Cat Warrior | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Nausea | handled | All creatures get -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Peace of Mind | handled | {W}, Discard a card: You gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reclaim | handled | Put target card from your graveyard on top of your library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Robe of Mirrors | handled | Enchanted creature has shroud. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seismic Assault | handled | Discard a land card: This enchantment deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spellbook | handled | You have no maximum hand size. | the engine reads this text and performs it | Y/-/- | not_tested |
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

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| each creature gets +N/+N for each other creature on the battlefield that shares at least one creature type with it. | 1 | Coat of Arms | exo |
| each creature you control can block an additional creature each combat. | 1 | High Ground | exo |
| enchanted creature gets +N/+N and can't block. | 1 | Maniacal Rage | exo |
| protection | 1 | Paladin en-Vec | exo |
| whenever a creature enters, that creature's controller may have it deal damage equal to its power to any target of their choice. | 1 | Pandemonium | exo |
| whenever ~ becomes blocked, it gets +N/+N until end of turn for each creature blocking it. | 1 | Elvish Berserker | exo |
| {M}: remove target attacking creature you control from combat and untap it. | 1 | Reconnaissance | exo |
| {M}{M}, sacrifice ~: look at target player's hand and choose a card from it. that player discards that card. activate only as a sorcery. | 1 | Thrull Surgeon | exo |

## Notes



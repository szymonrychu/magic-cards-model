# Urza's Destiny (uds)

- Expansion: 027
- Set code: `uds`
- Release date: 1999-06-07
- Cards in scope (Modern/Pioneer/Standard-legal): 30

## Legality

| Format | Legal cards |
|---|---|
| Modern | 30 |
| Pioneer | 5 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 2 | 6.7% |
| Works (untested) | 13 | 43.3% |
| Partial (unaudited) | 2 | 6.7% |
| Not working | 13 | 43.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Emperor Crocodile | silent | When you control no other creatures, sacrifice this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Eradicate | silent | Exile target nonblack creature. Search its controller's graveyard, hand, and library for all cards with the same name as that creature and exile them. Then that | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Extruder | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Hunting Moa | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Plow Under | silent | Put two target lands on top of their owners' libraries. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Quash | silent | Counter target instant or sorcery spell. Search its controller's graveyard, hand, and library for all cards with the same name as that spell and exile them. The | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scour | silent | Exile target enchantment. Search its controller's graveyard, hand, and library for all cards with the same name as that enchantment and exile them. Then that pl | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sowing Salt | silent | Exile target nonbasic land. Search its controller's graveyard, hand, and library for all cards with the same name as that land and exile them. Then that player  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Splinter | silent | Exile target artifact. Search its controller's graveyard, hand, and library for all cards with the same name as that artifact and exile them. Then that player s | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Thran Golem | silent | As long as this creature is enchanted, it gets +2/+2 and has flying, first strike, and trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Trumpet Blast | silent | Attacking creatures get +2/+0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Bloodshot Cyclops | notice | {T}, Sacrifice a creature: This creature deals damage equal to the sacrificed creature's power to any target. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Yavimaya Enchantress | notice | This creature gets +1/+1 for each enchantment on the battlefield. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Storage Matrix | unaudited | As long as this artifact is untapped, each player chooses artifact, creature, or land during their untap step. That player can untap only permanents of the chos | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Thorn Elemental | unaudited | You may have this creature assign its combat damage as though it weren't blocked. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Capashen Knight | handled | {1}{W}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Elvish Piper | handled | {G}, {T}: You may put a creature card from your hand onto the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fodder Cannon | handled | {4}, {T}, Sacrifice a creature: This artifact deals 4 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Junk Diver | handled | When this creature dies, return another target artifact card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mantis Engine | handled | {2}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Master Healer | handled | {T}: Prevent the next 4 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rescue | handled | Return target permanent you control to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sanctimony | handled | Whenever an opponent taps a Mountain for mana, you may gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Solidarity | handled | Creatures you control get +0/+5 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Soul Feast | handled | Target player loses 4 life and you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Temporal Adept | handled | {U}{U}{U}, {T}: Return target permanent to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thieving Magpie | handled | Whenever this creature deals damage to an opponent, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Yavimaya Elder | handled | When this creature dies, you may search your library for up to two basic land cards, reveal them, put them into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Ancient Silverback
- Urza's Incubator

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| echo | 2 | Extruder, Hunting Moa | uds |
| as long as ~ is enchanted, it gets +N/+N and has flying, first strike, and trample. | 1 | Thran Golem | uds |
| as long as ~ is untapped, each player chooses artifact, creature, or land during their untap step. that player can untap only permanents of the chosen type ~. | 1 | Storage Matrix | uds |
| attacking creatures get +N/+N until end of turn. | 1 | Trumpet Blast | uds |
| counter target instant or sorcery spell. search its controller's graveyard, hand, and library for all cards with the same name as that spell and exile them. the | 1 | Quash | uds |
| exile target artifact. search its controller's graveyard, hand, and library for all cards with the same name as that artifact and exile them. then that player s | 1 | Splinter | uds |
| exile target enchantment. search its controller's graveyard, hand, and library for all cards with the same name as that enchantment and exile them. then that pl | 1 | Scour | uds |
| exile target nonbasic land. search its controller's graveyard, hand, and library for all cards with the same name as that land and exile them. then that player  | 1 | Sowing Salt | uds |
| exile target nonblack creature. search its controller's graveyard, hand, and library for all cards with the same name as that creature and exile them. then that | 1 | Eradicate | uds |
| put two target lands on top of their owners' libraries. | 1 | Plow Under | uds |
| when you control no other creatures, sacrifice ~. | 1 | Emperor Crocodile | uds |
| you may have ~ assign its combat damage as though it weren't blocked. | 1 | Thorn Elemental | uds |
| {M}, sacrifice a creature: ~ deals damage equal to the sacrificed creature's power to any target. | 1 | Bloodshot Cyclops | uds |
| ~ gets +N/+N for each enchantment on the battlefield. | 1 | Yavimaya Enchantress | uds |

## Notes



# Weatherlight (wth)

- Expansion: 017
- Set code: `wth`
- Release date: 1997-06-09
- Cards in scope (Modern/Pioneer/Standard-legal): 25

## Legality

| Format | Legal cards |
|---|---|
| Modern | 25 |
| Pioneer | 2 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 2 | 8.0% |
| Works (untested) | 16 | 64.0% |
| Partial (unaudited) | 1 | 4.0% |
| Not working | 6 | 24.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Gaea's Blessing | silent | Target player shuffles up to three target cards from their graveyard into their library. Draw a card. When this card is put into your graveyard from your librar | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hidden Horror | silent | When this creature enters, sacrifice it unless you discard a creature card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Llanowar Sentinel | silent | When this creature enters, you may pay {1}{G}. If you do, search your library for a card named Llanowar Sentinel, put that card onto the battlefield, then shuff | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Phantom Wings | silent | Sacrifice this Aura: Return enchanted creature to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Agonizing Memories | notice | Look at target player's hand and choose two cards from it. Put them on top of that player's library in any order. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Cinder Wall | notice | When this creature blocks, destroy it at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Steel Golem | unaudited | You can't cast creature spells. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Aura of Silence | handled | Artifact and enchantment spells your opponents cast cost {2} more to cast. | the engine reads this text and performs it | Y/-/- | not_tested |
| Benalish Knight | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Bloodrock Cyclops | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bogardan Firefiend | handled | When this creature dies, it deals 2 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Buried Alive | handled | Search your library for up to three creature cards, put them into your graveyard, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Call of the Wild | handled | {2}{G}{G}: Reveal the top card of your library. If it's a creature card, put it onto the battlefield. Otherwise, put it into your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fervor | handled | Creatures you control have haste. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fire Whip | handled | Enchanted creature has "{T}: This creature deals 1 damage to any target." | the engine reads this text and performs it | Y/-/- | not_tested |
| Fog Elemental | handled | When this creature attacks or blocks, sacrifice it at end of combat. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gemstone Mine | handled | This land enters with three mining counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lava Hounds | handled | When this creature enters, it deals 4 damage to you. | the engine reads this text and performs it | Y/-/- | not_tested |
| Llanowar Behemoth | handled | Tap an untapped creature you control: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Razortooth Rats | handled | Fear | machines/keywords.py | Y/-/- | not_tested |
| Sage Owl | handled | When this creature enters, look at the top four cards of your library, then put them back in any order. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serra's Blessing | handled | Creatures you control have vigilance. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thunderbolt | handled | Choose one — • Thunderbolt deals 3 damage to target player or planeswalker. • Thunderbolt deals 4 damage to target creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Cone of Flame
- Mind Stone

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| look at target player"..."s library in any order. | 1 | Agonizing Memories | wth |
| sacrifice ~: return enchanted creature to its owner's hand. | 1 | Phantom Wings | wth |
| target player shuffles up to three target cards from their graveyard into their library. draw a card. when ~ is put into your graveyard from your library, shuff | 1 | Gaea's Blessing | wth |
| when ~ blocks, destroy it at end of combat. | 1 | Cinder Wall | wth |
| when ~ enters, sacrifice it unless you discard a creature card. | 1 | Hidden Horror | wth |
| when ~ enters, you may pay {M}{M}. if you do, search your library for a card named ~, put that card onto the battlefield, then shuffle. | 1 | Llanowar Sentinel | wth |
| you can't cast creature spells. | 1 | Steel Golem | wth |

## Notes



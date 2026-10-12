# Urza's Saga (usg)

- Expansion: 023
- Set code: `usg`
- Release date: 1998-10-12
- Cards in scope (Modern/Pioneer/Standard-legal): 66

## Legality

| Format | Legal cards |
|---|---|
| Modern | 66 |
| Pioneer | 15 |
| Standard | 5 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 22 | 33.3% |
| Works (untested) | 35 | 53.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 9 | 13.6% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Academy Researchers | silent | When this creature enters, you may put an Aura card from your hand onto the battlefield attached to this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fecundity | silent | Whenever a creature dies, that creature's controller may draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| No Rest for the Wicked | silent | Sacrifice this enchantment: Return to your hand all creature cards in your graveyard that were put there from the battlefield this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Persecute | silent | Choose a color. Target player reveals their hand and discards all cards of that color. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rewind | silent | Counter target spell. Untap up to four lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Shiv's Embrace | silent | {R}: Enchanted creature gets +1/+0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sleeper Agent | silent | When this creature enters, target opponent gains control of it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spreading Algae | silent | When enchanted land becomes tapped, destroy it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Victimize | silent | Choose two target creature cards in your graveyard. Sacrifice a creature. If you do, return the chosen cards to the battlefield tapped. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Angelic Chorus | handled | Whenever a creature you control enters, you gain life equal to its toughness. | the engine reads this text and performs it | Y/-/- | not_tested |
| Angelic Page | handled | {T}: Target attacking or blocking creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Annul | handled | Counter target artifact or enchantment spell. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Befoul | handled | Destroy target land or nonblack creature. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blanchwood Armor | handled | Enchanted creature gets +1/+1 for each Forest you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Catalog | handled | Draw two cards, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cathodion | handled | When this creature dies, add {C}{C}{C}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chimeric Staff | handled | {X}: This artifact becomes an X/X Construct artifact creature until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Citanul Flute | handled | {X}, {T}: Search your library for a creature card with mana value X or less, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Confiscate | handled | You control enchanted permanent. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Congregate | handled | Target player gains 2 life for each creature on the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Coral Merfolk | handled |  |  | Y/Y/- | not_tested |
| Dragon Blood | handled | {3}, {T}: Put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eastern Paladin | handled | {B}{B}, {T}: Destroy target green creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elite Archers | handled | {T}: This creature deals 3 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elvish Lyrist | handled | {G}, {T}, Sacrifice this creature: Destroy target enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Spelunkers | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Heat Ray | handled | Heat Ray deals X damage to target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hibernation | handled | Return all green permanents to their owners' hands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hollow Dogs | handled | Whenever this creature attacks, it gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Horseshoe Crab | handled | {U}: Untap this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Intrepid Hero | handled | {T}: Destroy target creature with power 4 or greater. | the engine reads this text and performs it | Y/-/- | not_tested |
| Looming Shade | handled | {B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pegasus Charger | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Phyrexian Tower | handled |  |  | Y/-/- | not_tested |
| Scoria Wurm | handled | At the beginning of your upkeep, flip a coin. If you lose the flip, return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serra Avatar | handled | Serra Avatar's power and toughness are each equal to your life total. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serra's Embrace | handled | Enchanted creature gets +2/+2 and has flying and vigilance. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shivan Hellkite | handled | {1}{R}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skirge Familiar | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Thundering Giant | handled | Haste | machines/combat.py | Y/Y/- | not_tested |
| Viashino Runner | handled | Menace | machines/combat.py | Y/-/- | not_tested |
| Voltaic Key | handled | {1}, {T}: Untap target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Western Paladin | handled | {B}{B}, {T}: Destroy target white creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Worn Powerstone | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>22 cards</summary>

- Abundance
- Arc Lightning
- Claws of Gix
- Corrupt
- Duress
- Fertile Ground
- Fog Bank
- Glorious Anthem
- Greater Good
- Imaginary Pet
- Meltdown
- Okk
- Pariah
- Phyrexian Colossus
- Priest of Titania
- Redeem
- Reflexes
- Sanctum Guardian
- Telepathy
- Urza's Armor
- Vernal Bloom
- Worship

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| choose a color. target player reveals their hand and discards all cards of that color. | 1 | Persecute | usg |
| choose two target creature cards in your graveyard. sacrifice a creature. if you do, return the chosen cards to the battlefield tapped. | 1 | Victimize | usg |
| counter target spell. untap up to four lands. | 1 | Rewind | usg |
| sacrifice ~: return to your hand all creature cards in your graveyard that were put there from the battlefield ~. | 1 | No Rest for the Wicked | usg |
| when enchanted land becomes tapped, destroy it. | 1 | Spreading Algae | usg |
| when ~ enters, target opponent gains control of it. | 1 | Sleeper Agent | usg |
| when ~ enters, you may put an aura card from your hand onto the battlefield attached to ~. | 1 | Academy Researchers | usg |
| whenever a creature dies, that creature's controller may draw a card. | 1 | Fecundity | usg |
| {M}: enchanted creature gets +N/+N until end of turn. | 1 | Shiv's Embrace | usg |

## Notes



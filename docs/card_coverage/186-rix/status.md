# Rivals of Ixalan (rix)

- Expansion: 186
- Set code: `rix`
- Release date: 2018-01-19
- Cards in scope (Modern/Pioneer/Standard-legal): 117

## Legality

| Format | Legal cards |
|---|---|
| Modern | 117 |
| Pioneer | 117 |
| Standard | 8 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 6 | 5.1% |
| Partial (unaudited) | 10 | 8.5% |
| Not tested (handled, untested) | 71 | 60.7% |
| Not working (silent / notice / error) | 30 | 25.6% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Angrath, Minotaur Pirate | silent | −11: Destroy all creatures target opponent controls. Angrath deals damage to that player equal to their total power. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Baffling End | silent | When this enchantment leaves the battlefield, target opponent creates a 3/3 green Dinosaur creature token with trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Blazing Hope | silent | Exile target creature with power greater than or equal to your life total. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cherished Hatchling | silent | When this creature dies, you may cast Dinosaur spells this turn as though they had flash, and whenever you cast a Dinosaur spell this turn, it gains "When this  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Crashing Tide | silent | This spell has flash as long as you control a Merfolk. Return target creature to its owner's hand. Draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Curious Obsession | silent | At the beginning of your end step, if you didn't attack with a creature this turn, sacrifice this Aura. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dinosaur Hunter | silent | Whenever this creature deals damage to a Dinosaur, destroy that creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dire Fleet Neckbreaker | silent | Attacking Pirates you control get +2/+0. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fathom Fleet Boarder | silent | When this creature enters, you lose 2 life unless you control another Pirate. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gruesome Fate | silent | Each opponent loses 1 life for each creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hardy Veteran | silent | During your turn, this creature gets +0/+2. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Merfolk Mistbinder | silent | Other Merfolk you control get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mutiny | silent | Target creature an opponent controls deals damage equal to its power to another target creature that player controls. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sea Legs | silent | Enchanted creature gets +0/+2 as long as it's a Pirate. Otherwise, it gets -2/-0. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| See Red | silent | At the beginning of your end step, if you didn't attack with a creature this turn, sacrifice this Aura. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tilonalli's Crown | silent | When this Aura enters, it deals 1 damage to enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Voracious Vampire | silent | When this creature enters, target Vampire you control gets +1/+1 and gains menace until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Vraska, Scheming Gorgon | silent | −10: Until end of turn, creatures you control gain deathtouch and "Whenever this creature deals damage to an opponent, that player loses the game." | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Angrath's Ambusher | notice | This creature gets +2/+0 as long as you control an Angrath planeswalker. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Angrath's Fury | notice | Destroy target creature. Angrath's Fury deals 3 damage to target player or planeswalker. You may search your library and/or graveyard for a card named Angrath,  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Buccaneer's Bravado | notice | Choose one — • Target creature gets +1/+1 and gains first strike until end of turn. • Target Pirate gets +1/+1 and gains double strike until end of turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Dusk Charger | notice | This creature gets +2/+2 as long as you have the city's blessing. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Expel from Orazca | notice | Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.) Return target nonland permanent to its owner's hand. If yo | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Grasping Scoundrel | notice | This creature gets +1/+0 as long as it's attacking. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Kitesail Corsair | notice | This creature has flying as long as it's attacking. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Skymarcher Aspirant | notice | This creature has flying as long as you have the city's blessing. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Snubhorn Sentry | notice | This creature gets +3/+0 as long as you have the city's blessing. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Spire Winder | notice | This creature gets +1/+1 as long as you have the city's blessing. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Storm Fleet Swashbuckler | notice | This creature has double strike as long as you have the city's blessing. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Vraska's Scorn | notice | Target opponent loses 4 life. You may search your library and/or graveyard for a card named Vraska, Scheming Gorgon, reveal it, and put it into your hand. If yo | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Charging Tuskodon | unaudited | If this creature would deal combat damage to a player, it deals double that damage to that player instead. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Daring Buccaneer | unaudited | As an additional cost to cast this spell, reveal a Pirate card from your hand or pay {2}. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Everdawn Champion | unaudited | Prevent all combat damage that would be dealt to this creature. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Luminous Bonds | unaudited | Enchanted creature can't attack or block. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Oathsworn Vampire | unaudited | You may cast this card from your graveyard if you gained life this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Relentless Raptor | unaudited | This creature attacks or blocks each combat if able. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| River Darter | unaudited | This creature can't be blocked by Dinosaurs. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Sadistic Skymarcher | unaudited | As an additional cost to cast this spell, reveal a Vampire card from your hand or pay {1}. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Slippery Scoundrel | unaudited | As long as you have the city's blessing, this creature has hexproof and can't be blocked. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Swaggering Corsair | unaudited | Raid — This creature enters with a +1/+1 counter on it if you attacked this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Aquatic Incursion | handled | When this enchantment enters, create two 1/1 blue Merfolk creature tokens with hexproof. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Arterial Flow | handled | Each opponent discards two cards. If you control a Vampire, each opponent loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Atzocan Seer | handled | Sacrifice this creature: Return target Dinosaur card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bombard | handled | Bombard deals 4 damage to target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Brazen Freebooter | handled | When this creature enters, create a Treasure token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cacophodon | handled | Enrage — Whenever this creature is dealt damage, untap target permanent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Canal Monitor | handled |  |  | Y/Y/- | not_tested |
| Cleansing Ray | handled | Choose one — • Destroy target Vampire. • Destroy target enchantment. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crested Herdcaller | handled | When this creature enters, create a 3/3 green Dinosaur creature token with trample. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dark Inquiry | handled | Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deadeye Brawler | handled | Whenever this creature deals combat damage to a player, if you have the city's blessing, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deadeye Rig-Hauler | handled | Raid — When this creature enters, if you attacked this turn, you may return target creature to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dusk Legion Zealot | handled | When this creature enters, you draw a card and you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Exultant Skymarcher | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Famished Paladin | handled | This creature doesn't untap during your untap step. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fanatical Firebrand | handled | {T}, Sacrifice this creature: It deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Forerunner of the Coalition | handled | When this creature enters, you may search your library for a Pirate card, reveal it, then shuffle and put that card on top. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Forerunner of the Empire | handled | When this creature enters, you may search your library for a Dinosaur card, reveal it, then shuffle and put that card on top. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Forerunner of the Heralds | handled | When this creature enters, you may search your library for a Merfolk card, reveal it, then shuffle and put that card on top. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Forerunner of the Legion | handled | When this creature enters, you may search your library for a Vampire card, reveal it, then shuffle and put that card on top. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Frilled Deathspitter | handled | Enrage — Whenever this creature is dealt damage, it deals 2 damage to target opponent or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Giltgrove Stalker | handled | This creature can't be blocked by creatures with power 2 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gleaming Barrier | handled | When this creature dies, create a Treasure token. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Goblin Trailblazer | handled | Menace | machines/combat.py | Y/Y/- | not_tested |
| Golden Demise | handled | Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.) All creatures get -2/-2 until end of turn. If you have the | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hornswoggle | handled | Counter target creature spell. You create a Treasure token. (It's an artifact with "{T}, Sacrifice this token: Add one mana of any color.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Impale | handled | Destroy target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Imperial Ceratops | handled | Enrage — Whenever this creature is dealt damage, you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jade Bearer | handled | When this creature enters, put a +1/+1 counter on another target Merfolk you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jadecraft Artisan | handled | When this creature enters, target creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jungle Creeper | handled | {3}{B}{G}: Return this card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jungleborn Pioneer | handled | When this creature enters, create a 1/1 blue Merfolk creature token with hexproof. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Knight of the Stampede | handled | Dinosaur spells you cast cost {2} less to cast. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Legion Lieutenant | handled | Other Vampires you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Majestic Heliopterus | handled | Whenever this creature attacks, another target Dinosaur you control gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Martyr of Dusk | handled | When this creature dies, create a 1/1 white Vampire creature token with lifelink. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mausoleum Harpy | handled | Whenever another creature you control dies, if you have the city's blessing, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mist-Cloaked Herald | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Moment of Craving | handled | Target creature gets -2/-2 until end of turn. You gain 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Moment of Triumph | handled | Target creature gets +2/+2 until end of turn. You gain 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Orazca Frillback | handled |  |  | Y/Y/- | not_tested |
| Orazca Raptor | handled |  |  | Y/Y/- | not_tested |
| Orazca Relic | handled | {T}, Sacrifice this artifact: You gain 3 life and draw a card. Activate only if you have the city's blessing. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Overgrown Armasaur | handled | Enrage — Whenever this creature is dealt damage, create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pirate's Pillage | handled | As an additional cost to cast this spell, discard a card. Draw two cards and create two Treasure tokens. (They're artifacts with "{T}, Sacrifice this token: Add | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pitiless Plunderer | handled | Whenever another creature you control dies, create a Treasure token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pride of Conquerors | handled | Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.) Creatures you control get +1/+1 until end of turn. If you  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Raging Regisaur | handled | Whenever this creature attacks, it deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reaver Ambush | handled | Exile target creature with power 3 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reckless Rage | handled | Reckless Rage deals 4 damage to target creature you don't control and 2 damage to target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Resplendent Griffin | handled | Whenever this creature attacks, if you have the city's blessing, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Riverwise Augur | handled | When this creature enters, draw three cards, then put two cards from your hand on top of your library in any order. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sanguine Glorifier | handled | When this creature enters, put a +1/+1 counter on another target Vampire you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shake the Foundations | handled | Shake the Foundations deals 1 damage to each creature without flying. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Siren Reaver | handled | Raid — This spell costs {1} less to cast if you attacked this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Soul of the Rapids | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Squire's Devotion | handled | Enchanted creature gets +1/+1 and has lifelink. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Storm Fleet Sprinter | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Strength of the Pack | handled | Put two +1/+1 counters on each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sun Sentinel | handled | Vigilance | machines/combat.py | Y/Y/- | not_tested |
| Sun-Collared Raptor | handled | {2}{R}: This creature gets +3/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sun-Crested Pterodon | handled | This creature has vigilance as long as you control another Dinosaur. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Swab Goblin | handled |  |  | Y/Y/Y | not_tested |
| Swift Warden | handled | When this creature enters, target Merfolk you control gains hexproof until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sworn Guardian | handled |  |  | Y/Y/- | not_tested |
| Thrashing Brontodon | handled | {1}, Sacrifice this creature: Destroy target artifact or enchantment. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Thunderherd Migration | handled | As an additional cost to cast this spell, reveal a Dinosaur card from your hand or pay {1}. Search your library for a basic land card, put it onto the battlefie | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vampire Champion | handled | Deathtouch | machines/combat.py | Y/Y/- | not_tested |
| Vampire Revenant | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Vraska's Conquistador | handled | Whenever this creature attacks or blocks, if you control a Vraska planeswalker, target opponent loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Waterknot | handled | When this Aura enters, tap enchanted creature. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>6 cards</summary>

- Enter the Unknown
- Flood of Recollection
- Needletooth Raptor
- Ravenous Chupacabra
- Secrets of the Golden City
- Stampeding Horncrest

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| This creature gets +2/+0 as long as you control an Angrath planeswalker. | Angrath's Ambusher, Dusk Charger, Grasping Scoundrel, Snubhorn Sentry, Spire Winder | 5 |
| As an additional cost to cast this spell, reveal a Vampire card from your hand or pay {1}. | Daring Buccaneer, Sadistic Skymarcher | 2 |
| At the beginning of your end step, if you didn't attack with a creature this turn, sacrifice this Aura. | Curious Obsession, See Red | 2 |
| This creature has flying as long as you have the city's blessing. | Kitesail Corsair, Skymarcher Aspirant | 2 |
| As long as you have the city's blessing, this creature has hexproof and can't be blocked. | Slippery Scoundrel | 1 |
| Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.) Return target nonland permanent to its owner's hand. If yo | Expel from Orazca | 1 |
| Attacking Pirates you control get +2/+0. | Dire Fleet Neckbreaker | 1 |
| Choose one — • Target creature gets +1/+1 and gains first strike until end of turn. • Target Pirate gets +1/+1 and gains double strike until end of turn. | Buccaneer's Bravado | 1 |
| −11: Destroy all creatures target opponent controls. Angrath deals damage to that player equal to their total power. | Angrath, Minotaur Pirate | 1 |
| Destroy target creature. Angrath's Fury deals 3 damage to target player or planeswalker. You may search your library and/or graveyard for a card named Angrath,  | Angrath's Fury | 1 |
| During your turn, this creature gets +0/+2. | Hardy Veteran | 1 |
| Each opponent loses 1 life for each creature you control. | Gruesome Fate | 1 |
| Enchanted creature can't attack or block. | Luminous Bonds | 1 |
| Enchanted creature gets +0/+2 as long as it's a Pirate. Otherwise, it gets -2/-0. | Sea Legs | 1 |
| Exile target creature with power greater than or equal to your life total. | Blazing Hope | 1 |
| If this creature would deal combat damage to a player, it deals double that damage to that player instead. | Charging Tuskodon | 1 |
| Other Merfolk you control get +1/+1. | Merfolk Mistbinder | 1 |
| Prevent all combat damage that would be dealt to this creature. | Everdawn Champion | 1 |
| Raid — This creature enters with a +1/+1 counter on it if you attacked this turn. | Swaggering Corsair | 1 |
| Target creature an opponent controls deals damage equal to its power to another target creature that player controls. | Mutiny | 1 |
| Target opponent loses 4 life. You may search your library and/or graveyard for a card named Vraska, Scheming Gorgon, reveal it, and put it into your hand. If yo | Vraska's Scorn | 1 |
| This creature attacks or blocks each combat if able. | Relentless Raptor | 1 |
| This creature can't be blocked by Dinosaurs. | River Darter | 1 |
| This creature has double strike as long as you have the city's blessing. | Storm Fleet Swashbuckler | 1 |
| This spell has flash as long as you control a Merfolk. Return target creature to its owner's hand. Draw a card. | Crashing Tide | 1 |
| −10: Until end of turn, creatures you control gain deathtouch and "Whenever this creature deals damage to an opponent, that player loses the game." | Vraska, Scheming Gorgon | 1 |
| When this Aura enters, it deals 1 damage to enchanted creature. | Tilonalli's Crown | 1 |
| When this creature dies, you may cast Dinosaur spells this turn as though they had flash, and whenever you cast a Dinosaur spell this turn, it gains "When this  | Cherished Hatchling | 1 |
| When this creature enters, target Vampire you control gets +1/+1 and gains menace until end of turn. | Voracious Vampire | 1 |
| When this creature enters, you lose 2 life unless you control another Pirate. | Fathom Fleet Boarder | 1 |
| When this enchantment leaves the battlefield, target opponent creates a 3/3 green Dinosaur creature token with trample. | Baffling End | 1 |
| Whenever this creature deals damage to a Dinosaur, destroy that creature. | Dinosaur Hunter | 1 |
| You may cast this card from your graveyard if you gained life this turn. | Oathsworn Vampire | 1 |

## Notes



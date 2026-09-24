# Aether Revolt (aer)

- Expansion: 178
- Set code: `aer`
- Release date: 2017-01-20
- Cards in scope (Modern/Pioneer/Standard-legal): 182

## Legality

| Format | Legal cards |
|---|---|
| Modern | 182 |
| Pioneer | 182 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 11 | 6.0% |
| Partial (unaudited) | 12 | 6.6% |
| Not tested (handled, untested) | 103 | 56.6% |
| Not working (silent / notice / error) | 56 | 30.8% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Aerial Modification | silent | As long as enchanted permanent is a Vehicle, it's a creature in addition to its other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Aethersphere Harvester | silent | Pay {E}: This Vehicle gains lifelink until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Aetherstream Leopard | error |  | card_support raised: unsupported mana symbol: {E} | Y/Y/- | not_working |
| Aethertide Whale | silent | When this creature enters, you get six {E} . | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Aetherwind Basker | silent | Whenever this creature enters or attacks, you get {E} for each creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ajani Unyielding | silent | +2: Reveal the top three cards of your library. Put all nonland permanent cards revealed this way into your hand and the rest on the bottom of your library in a | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ajani's Aid | silent | When this enchantment enters, you may search your library and/or graveyard for a card named Ajani, Valiant Protector, reveal it, and put it into your hand. If y | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ajani, Valiant Protector | silent | −11: Put X +1/+1 counters on target creature, where X is your life total. That creature gains trample until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Baral's Expertise | silent | Return up to three target artifacts and/or creatures to their owners' hands. You may cast a spell with mana value 4 or less from your hand without paying its ma | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Baral, Chief of Compliance | silent | Whenever a spell or ability you control counters a spell, you may draw a card. If you do, discard a card. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Caught in the Brights | silent | When a Vehicle you control attacks, exile enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Consulate Crackdown | silent | When this enchantment enters, exile all artifacts your opponents control until this enchantment leaves the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Daredevil Dragster | silent | At end of combat, if this Vehicle attacked or blocked this combat, put a velocity counter on it. Then if it has two or more velocity counters on it, sacrifice i | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Dark Intimations | silent | Each opponent sacrifices a creature or planeswalker of their choice, then discards a card. You return a creature or planeswalker card from your graveyard to you | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Decommission | silent | Destroy target artifact or enchantment. Revolt — If a permanent left the battlefield under your control this turn, you gain 3 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Disallow | silent | Counter target spell, activated ability, or triggered ability. (Mana abilities can't be targeted.) | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fourth Bridge Prowler | silent | When this creature enters, you may have target creature get -1/-1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gonti's Machinations | silent | Pay {E}{E}, Sacrifice this enchantment: Each opponent loses 3 life. You gain life equal to the life lost this way. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Greenbelt Rampager | silent | When this creature enters, pay {E}{E} . If you can't, return this creature to its owner's hand and you get {E}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gremlin Infestation | silent | At the beginning of your end step, this Aura deals 2 damage to enchanted artifact's controller. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hope of Ghirapur | silent | Sacrifice Hope of Ghirapur: Until your next turn, target player who was dealt combat damage by Hope of Ghirapur this turn can't cast noncreature spells. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Indomitable Creativity | silent | Destroy X target artifacts and/or creatures. For each permanent destroyed this way, its controller reveals cards from the top of their library until an artifact | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kari Zev's Expertise | silent | Gain control of target creature or Vehicle until end of turn. Untap it. It gains haste until end of turn. You may cast a spell with mana value 2 or less from yo | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Lightning Runner | silent | Whenever this creature attacks, you get {E}{E} , then you may pay eight {E}. If you pay, untap all creatures you control, and after this phase, there is an addi | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Maulfist Revolutionary | silent | When this creature enters or dies, for each kind of counter on target permanent or player, give that permanent or player another counter of that kind. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mechanized Production | silent | At the beginning of your upkeep, create a token that's a copy of enchanted artifact. Then if you control eight or more artifacts with the same name as one anoth | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Metallic Mimic | silent | This creature is the chosen type in addition to its other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Monstrous Onslaught | silent | Monstrous Onslaught deals X damage divided as you choose among any number of target creatures, where X is the greatest power among creatures you control as you  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Natural Obsolescence | silent | Put target artifact on the bottom of its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Peacewalker Colossus | silent | {1}{W}: Another target Vehicle you control becomes an artifact creature until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Peema Aether-Seer | silent | When this creature enters, you get an amount of {E} equal to the greatest power among creatures you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Perilous Predicament | silent | Each opponent sacrifices an artifact creature and a nonartifact creature of their choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Pia's Revolution | silent | Whenever a nontoken artifact is put into your graveyard from the battlefield, return that card to your hand unless target opponent has this enchantment deal 3 d | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Quicksmith Rebel | silent | When this creature enters, target artifact you control gains "{T}: This artifact deals 2 damage to any target" for as long as you control this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Quicksmith Spy | silent | When this creature enters, target artifact you control gains "{T}: Draw a card" for as long as you control this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Renegade Wheelsmith | silent | Whenever this creature becomes tapped, target creature can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Restoration Specialist | silent | {W}, Sacrifice this creature: Return up to one target artifact card and up to one target enchantment card from your graveyard to your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rishkar's Expertise | silent | Draw cards equal to the greatest power among creatures you control. You may cast a spell with mana value 5 or less from your hand without paying its mana cost. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Salvage Scuttler | silent | Whenever this creature attacks, return an artifact you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Scrap Trawler | silent | Whenever this creature dies or another artifact you control is put into a graveyard from the battlefield, return to your hand target artifact card in your grave | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Scrounging Bandar | silent | At the beginning of your upkeep, you may move any number of +1/+1 counters from this creature onto another target creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Siege Modification | silent | As long as enchanted permanent is a Vehicle, it's a creature in addition to its other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Skyship Plunderer | silent | Whenever this creature deals combat damage to a player, for each kind of counter on target permanent or player, give that permanent or player another counter of | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sram's Expertise | silent | Create three 1/1 colorless Servo artifact creature tokens. You may cast a spell with mana value 3 or less from your hand without paying its mana cost. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tezzeret's Touch | silent | When enchanted artifact is put into a graveyard, return that card to its owner's hand. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Tezzeret, Master of Metal | silent | −3: Target opponent loses life equal to the number of artifacts you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Trophy Mage | silent | When this creature enters, you may search your library for an artifact card with mana value 3, reveal it, put it into your hand, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Battle at the Bridge | notice | Improvise (Your artifacts can help cast this spell. Each artifact you tap after you're done activating mana abilities pays for {1}.) Target creature gets -X/-X  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Call for Unity | notice | Creatures you control get +1/+1 for each unity counter on this enchantment. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Chandra's Revolution | notice | Chandra's Revolution deals 4 damage to target creature. Tap target land. That land doesn't untap during its controller's next untap step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Destructive Tampering | notice | Choose one — • Destroy target artifact. • Creatures without flying can't block this turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Kari Zev, Skyship Raider | notice | Whenever Kari Zev attacks, create Ragavan, a legendary 2/1 red Monkey creature token. Ragavan enters tapped and attacking. Exile that token at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Lifecraft Awakening | notice | Put X +1/+1 counters on target artifact you control. If it isn't a creature or Vehicle, it becomes a 0/0 Construct artifact creature. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Secret Salvage | notice | Exile target nonland card from your graveyard. Search your library for any number of cards with the same name as that card, reveal them, put them into your hand | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Tezzeret's Betrayal | notice | Destroy target creature. You may search your library and/or graveyard for a card named Tezzeret, Master of Metal, reveal it, and put it into your hand. If you s | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Treasure Keeper | notice | When this creature dies, reveal cards from the top of your library until you reveal a nonland card with mana value 3 or less. You may cast that card without pay | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Audacious Infiltrator | unaudited | This creature can't be blocked by artifact creatures. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Exquisite Archangel | unaudited | If you would lose the game, instead exile this creature and your life total becomes equal to your starting life total. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Fen Hauler | unaudited | This creature can't be blocked by artifact creatures. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Greenwheel Liberator | unaudited | Revolt — This creature enters with two +1/+1 counters on it if a permanent left the battlefield under your control this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Heart of Kiran | unaudited | You may remove a loyalty counter from a planeswalker you control rather than pay Heart of Kiran's crew cost. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Inspiring Statuary | unaudited | Nonartifact spells you cast have improvise. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Lifecraft Cavalry | unaudited | Revolt — This creature enters with two +1/+1 counters on it if a permanent left the battlefield under your control this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Narnam Renegade | unaudited | Revolt — This creature enters with a +1/+1 counter on it if a permanent left the battlefield under your control this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Night Market Aeronaut | unaudited | Revolt — This creature enters with a +1/+1 counter on it if a permanent left the battlefield under your control this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Night Market Guard | unaudited | This creature can block an additional creature each combat. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Rishkar, Peema Renegade | unaudited | Each creature you control with a counter on it has "{T}: Add {G}." | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Unbridled Growth | unaudited | Enchanted land has "{T}: Add one mana of any color." | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Aegis Automaton | handled | {4}{W}: Return another target creature you control to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aeronaut Admiral | handled | Vehicles you control have flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aether Herder | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aether Inspector | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aether Poisoner | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aether Swooper | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aethergeode Miner | handled | Whenever this creature attacks, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Airdrop Aeronauts | handled | Revolt — When this creature enters, if a permanent left the battlefield under your control this turn, you gain 5 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ajani's Comrade | handled | At the beginning of combat on your turn, if you control an Ajani planeswalker, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Alley Evasion | handled | Choose one — • Target creature you control gets +1/+2 until end of turn. • Return target creature you control to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Alley Strangler | handled | Menace | machines/combat.py | Y/Y/- | not_tested |
| Augmenting Automaton | handled | {1}{B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Barricade Breaker | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bastion Inventor | handled | Improvise | machines/objects_as_costs.py (improvise) | Y/Y/- | not_tested |
| Cogwork Assembler | handled | {7}: Create a token that's a copy of target artifact. That token gains haste. Exile it at the beginning of the next end step. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Consulate Turret | handled | {T}: You get {E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Countless Gears Renegade | handled | Revolt — When this creature enters, if a permanent left the battlefield under your control this turn, create a 1/1 colorless Servo artifact creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crackdown Construct | handled | Whenever you activate an ability of an artifact or creature that isn't a mana ability, this creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cruel Finality | handled | Target creature gets -2/-2 until end of turn. Scry 1. (Look at the top card of your library. You may put that card on the bottom.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Daring Demolition | handled | Destroy target creature or Vehicle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dawnfeather Eagle | handled | When this creature enters, creatures you control get +1/+1 and gain vigilance until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deadeye Harpooner | handled | Revolt — When this creature enters, if a permanent left the battlefield under your control this turn, destroy target tapped creature an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Defiant Salvager | handled | Sacrifice an artifact or creature: Put a +1/+1 counter on this creature. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deft Dismissal | handled | Deft Dismissal deals 3 damage divided as you choose among one, two, or three target attacking or blocking creatures. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dispersal Technician | handled | When this creature enters, you may return target artifact to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Druid of the Cowl | handled |  |  | Y/Y/Y | not_tested |
| Efficient Construction | handled | Whenever you cast an artifact spell, create a 1/1 colorless Thopter artifact creature token with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Embraal Gear-Smasher | handled | {T}, Sacrifice an artifact: This creature deals 2 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Enraged Giant | handled | Improvise | machines/objects_as_costs.py (improvise) | Y/Y/- | not_tested |
| Felidar Guardian | handled | When this creature enters, you may exile another target permanent you control, then return that card to the battlefield under its owner's control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Filigree Crawler | handled | When this creature dies, create a 1/1 colorless Thopter artifact creature token with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Foundry Assembler | handled | Improvise | machines/objects_as_costs.py (improvise) | Y/Y/- | not_tested |
| Foundry Hornet | handled | When this creature enters, if you control a creature with a +1/+1 counter on it, creatures your opponents control get -1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Freejam Regent | handled | {1}{R}: This creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Frontline Rebel | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ghirapur Osprey | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Gifted Aetherborn | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Glint-Sleeve Siphoner | handled | Whenever this creature enters or attacks, you get {E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gonti's Aether Heart | handled | Whenever Gonti's Aether Heart or another artifact you control enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Herald of Anguish | handled | At the beginning of your end step, each opponent discards a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Heroic Intervention | handled | Permanents you control gain hexproof and indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hidden Herbalists | handled | Revolt — When this creature enters, if a permanent left the battlefield under your control this turn, add {G}{G}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hidden Stockpile | handled | Revolt — At the beginning of your end step, if a permanent left the battlefield under your control this turn, create a 1/1 colorless Servo artifact creature tok | the engine reads this text and performs it | Y/Y/- | not_tested |
| Highspire Infusion | handled | Target creature gets +3/+3 until end of turn. You get {E}{E} (two energy counters). | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ice Over | handled | Enchanted permanent doesn't untap during its controller's untap step. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Illusionist's Stratagem | handled | Exile up to two target creatures you control, then return those cards to the battlefield under their owner's control. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Implement of Combustion | handled | {R}, Sacrifice this artifact: It deals 1 damage to target player or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Implement of Examination | handled | {U}, Sacrifice this artifact: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Implement of Ferocity | handled | {G}, Sacrifice this artifact: Put a +1/+1 counter on target creature. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Implement of Improvement | handled | {W}, Sacrifice this artifact: You gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Implement of Malice | handled | {B}, Sacrifice this artifact: Target player discards a card. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inspiring Roar | handled | Put a +1/+1 counter on each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Invigorated Rampage | handled | Choose one — • Target creature gets +4/+0 and gains trample until end of turn. • Two target creatures each get +2/+0 and gain trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ironclad Revolutionary | handled | When this creature enters, you may sacrifice an artifact. If you do, put two +1/+1 counters on this creature and each opponent loses 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Irontread Crusher | handled | Crew | machines/keywords.py | Y/Y/- | not_tested |
| Lathnu Sailback | handled |  |  | Y/Y/- | not_tested |
| Leave in the Dust | handled | Return target nonland permanent to its owner's hand. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lifecrafter's Bestiary | handled | At the beginning of your upkeep, scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lifecrafter's Gift | handled | Put a +1/+1 counter on target creature, then put a +1/+1 counter on each creature you control with a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Maverick Thopterist | handled | When this creature enters, create two 1/1 colorless Thopter artifact creature tokens with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Midnight Entourage | handled | Other Aetherborn you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mobile Garrison | handled | Whenever this Vehicle attacks, untap another target artifact or creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Oath of Ajani | handled | When Oath of Ajani enters, put a +1/+1 counter on each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Outland Boar | handled | This creature can't be blocked by creatures with power 2 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pacification Array | handled | {2}, {T}: Tap target artifact or creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pendulum of Patterns | handled | When this artifact enters, you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Precise Strike | handled | Target creature gets +1/+0 and gains first strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prizefighter Construct | handled |  |  | Y/Y/- | not_tested |
| Ravenous Intruder | handled | Sacrifice an artifact: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reckless Racer | handled | Whenever this creature becomes tapped, you may discard a card. If you do, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Release the Gremlins | handled | Destroy X target artifacts. Create X 2/2 red Gremlin creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Renegade Map | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Renegade's Getaway | handled | Target permanent gains indestructible until end of turn. Create a 1/1 colorless Servo artifact creature token. (Effects that say "destroy" don't destroy a perma | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reservoir Walker | handled | When this creature enters, you gain 3 life and get {E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Resourceful Return | handled | Return target creature card from your graveyard to your hand. If you control an artifact, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ridgescale Tusker | handled | When this creature enters, put a +1/+1 counter on each other creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rogue Refiner | handled | When this creature enters, draw a card and you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Scrapper Champion | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Servo Schematic | handled | When this artifact enters or is put into a graveyard from the battlefield, create a 1/1 colorless Servo artifact creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shielded Aether Thief | handled | Whenever this creature blocks, you get {E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shipwreck Moray | handled | When this creature enters, you get {E}{E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Silkweaver Elite | handled | Revolt — When this creature enters, if a permanent left the battlefield under your control this turn, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sly Requisitioner | handled | Whenever a nontoken artifact you control is put into a graveyard from the battlefield, create a 1/1 colorless Servo artifact creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Solemn Recruit | handled | Revolt — At the beginning of your end step, if a permanent left the battlefield under your control this turn, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spire Patrol | handled | When this creature enters, tap target creature an opponent controls. That creature doesn't untap during its controller's next untap step. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spire of Industry | handled |  |  | Y/Y/- | not_tested |
| Sram, Senior Edificer | handled | Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sweatworks Brawler | handled | Improvise | machines/objects_as_costs.py (improvise) | Y/Y/- | not_tested |
| Take into Custody | handled | Tap target creature. It doesn't untap during its controller's next untap step. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tezzeret the Schemer | handled | +1: Create a colorless artifact token named Etherium Cell with "{T}, Sacrifice this token: Add one mana of any color." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tezzeret's Simulacrum | handled | {T}: Target opponent loses 1 life. If you control a Tezzeret planeswalker, that player loses 3 life instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thopter Arrest | handled | When this enchantment enters, exile target artifact or creature an opponent controls until this enchantment leaves the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Universal Solvent | handled | {7}, {T}, Sacrifice this artifact: Destroy target permanent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Untethered Express | handled | Whenever this Vehicle attacks, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vengeful Rebel | handled | Revolt — When this creature enters, if a permanent left the battlefield under your control this turn, target creature an opponent controls gets -3/-3 until end  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Verdant Automaton | handled | {3}{G}: Put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Watchful Automaton | handled | {2}{U}: Scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Welder Automaton | handled | {3}{R}: This creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Weldfast Engineer | handled | At the beginning of combat on your turn, target artifact creature you control gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wind-Kin Raiders | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Wrangle | handled | Gain control of target creature with power 4 or less until end of turn. Untap that creature. It gains haste until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Yahenni's Expertise | handled | All creatures get -3/-3 until end of turn. You may cast a spell with mana value 3 or less from your hand without paying its mana cost. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Yahenni, Undying Partisan | handled | Whenever a creature an opponent controls dies, put a +1/+1 counter on Yahenni. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>11 cards</summary>

- Aether Chaser
- Aid from the Cowl
- Bastion Enforcer
- Consulate Dreadnought
- Hinterland Drake
- Hungry Flames
- Merchant's Dockhand
- Metallic Rebuke
- Walking Ballista
- Whir of Invention
- Winding Constrictor

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Revolt — This creature enters with two +1/+1 counters on it if a permanent left the battlefield under your control this turn. | Greenwheel Liberator, Lifecraft Cavalry, Narnam Renegade, Night Market Aeronaut | 4 |
| When this creature enters, you may search your library for an artifact card with mana value 3, reveal it, put it into your hand, then shuffle. | Aethertide Whale, Fourth Bridge Prowler, Peema Aether-Seer, Trophy Mage | 4 |
| At the beginning of your upkeep, create a token that's a copy of enchanted artifact. Then if you control eight or more artifacts with the same name as one anoth | Gremlin Infestation, Mechanized Production, Scrounging Bandar | 3 |
| As long as enchanted permanent is a Vehicle, it's a creature in addition to its other types. | Aerial Modification, Siege Modification | 2 |
| Put X +1/+1 counters on target artifact you control. If it isn't a creature or Vehicle, it becomes a 0/0 Construct artifact creature. | Ajani, Valiant Protector, Lifecraft Awakening | 2 |
| This creature can't be blocked by artifact creatures. | Audacious Infiltrator, Fen Hauler | 2 |
| When this creature enters, target artifact you control gains "{T}: This artifact deals 2 damage to any target" for as long as you control this creature. | Quicksmith Rebel, Quicksmith Spy | 2 |
| {1}{W}: Another target Vehicle you control becomes an artifact creature until end of turn. | Peacewalker Colossus | 1 |
| At end of combat, if this Vehicle attacked or blocked this combat, put a velocity counter on it. Then if it has two or more velocity counters on it, sacrifice i | Daredevil Dragster | 1 |
| Chandra's Revolution deals 4 damage to target creature. Tap target land. That land doesn't untap during its controller's next untap step. | Chandra's Revolution | 1 |
| Choose one — • Destroy target artifact. • Creatures without flying can't block this turn. | Destructive Tampering | 1 |
| Counter target spell, activated ability, or triggered ability. (Mana abilities can't be targeted.) | Disallow | 1 |
| Create three 1/1 colorless Servo artifact creature tokens. You may cast a spell with mana value 3 or less from your hand without paying its mana cost. | Sram's Expertise | 1 |
| Creatures you control get +1/+1 for each unity counter on this enchantment. | Call for Unity | 1 |
| Destroy target artifact or enchantment. Revolt — If a permanent left the battlefield under your control this turn, you gain 3 life. | Decommission | 1 |
| Destroy target creature. You may search your library and/or graveyard for a card named Tezzeret, Master of Metal, reveal it, and put it into your hand. If you s | Tezzeret's Betrayal | 1 |
| Destroy X target artifacts and/or creatures. For each permanent destroyed this way, its controller reveals cards from the top of their library until an artifact | Indomitable Creativity | 1 |
| Draw cards equal to the greatest power among creatures you control. You may cast a spell with mana value 5 or less from your hand without paying its mana cost. | Rishkar's Expertise | 1 |
| Each creature you control with a counter on it has "{T}: Add {G}." | Rishkar, Peema Renegade | 1 |
| Each opponent sacrifices a creature or planeswalker of their choice, then discards a card. You return a creature or planeswalker card from your graveyard to you | Dark Intimations | 1 |
| Each opponent sacrifices an artifact creature and a nonartifact creature of their choice. | Perilous Predicament | 1 |
| Enchanted land has "{T}: Add one mana of any color." | Unbridled Growth | 1 |
| Exile target nonland card from your graveyard. Search your library for any number of cards with the same name as that card, reveal them, put them into your hand | Secret Salvage | 1 |
| Gain control of target creature or Vehicle until end of turn. Untap it. It gains haste until end of turn. You may cast a spell with mana value 2 or less from yo | Kari Zev's Expertise | 1 |
| If you would lose the game, instead exile this creature and your life total becomes equal to your starting life total. | Exquisite Archangel | 1 |
| Improvise (Your artifacts can help cast this spell. Each artifact you tap after you're done activating mana abilities pays for {1}.) Target creature gets -X/-X  | Battle at the Bridge | 1 |
| Monstrous Onslaught deals X damage divided as you choose among any number of target creatures, where X is the greatest power among creatures you control as you  | Monstrous Onslaught | 1 |
| Nonartifact spells you cast have improvise. | Inspiring Statuary | 1 |
| Pay {E}{E}, Sacrifice this enchantment: Each opponent loses 3 life. You gain life equal to the life lost this way. | Gonti's Machinations | 1 |
| Pay {E}: This Vehicle gains lifelink until end of turn. | Aethersphere Harvester | 1 |
| Put target artifact on the bottom of its owner's library. | Natural Obsolescence | 1 |
| Return up to three target artifacts and/or creatures to their owners' hands. You may cast a spell with mana value 4 or less from your hand without paying its ma | Baral's Expertise | 1 |
| +2: Reveal the top three cards of your library. Put all nonland permanent cards revealed this way into your hand and the rest on the bottom of your library in a | Ajani Unyielding | 1 |
| Sacrifice Hope of Ghirapur: Until your next turn, target player who was dealt combat damage by Hope of Ghirapur this turn can't cast noncreature spells. | Hope of Ghirapur | 1 |
| {W}, Sacrifice this creature: Return up to one target artifact card and up to one target enchantment card from your graveyard to your hand. | Restoration Specialist | 1 |
| −3: Target opponent loses life equal to the number of artifacts you control. | Tezzeret, Master of Metal | 1 |
| This creature can block an additional creature each combat. | Night Market Guard | 1 |
| This creature is the chosen type in addition to its other types. | Metallic Mimic | 1 |
| When a Vehicle you control attacks, exile enchanted creature. | Caught in the Brights | 1 |
| When enchanted artifact is put into a graveyard, return that card to its owner's hand. | Tezzeret's Touch | 1 |
| When this creature dies, reveal cards from the top of your library until you reveal a nonland card with mana value 3 or less. You may cast that card without pay | Treasure Keeper | 1 |
| When this creature enters or dies, for each kind of counter on target permanent or player, give that permanent or player another counter of that kind. | Maulfist Revolutionary | 1 |
| When this creature enters, pay {E}{E} . If you can't, return this creature to its owner's hand and you get {E}. | Greenbelt Rampager | 1 |
| When this enchantment enters, exile all artifacts your opponents control until this enchantment leaves the battlefield. | Consulate Crackdown | 1 |
| When this enchantment enters, you may search your library and/or graveyard for a card named Ajani, Valiant Protector, reveal it, and put it into your hand. If y | Ajani's Aid | 1 |
| Whenever a nontoken artifact is put into your graveyard from the battlefield, return that card to your hand unless target opponent has this enchantment deal 3 d | Pia's Revolution | 1 |
| Whenever a spell or ability you control counters a spell, you may draw a card. If you do, discard a card. | Baral, Chief of Compliance | 1 |
| Whenever Kari Zev attacks, create Ragavan, a legendary 2/1 red Monkey creature token. Ragavan enters tapped and attacking. Exile that token at end of combat. | Kari Zev, Skyship Raider | 1 |
| Whenever this creature attacks, return an artifact you control to its owner's hand. | Salvage Scuttler | 1 |
| Whenever this creature attacks, you get {E}{E} , then you may pay eight {E}. If you pay, untap all creatures you control, and after this phase, there is an addi | Lightning Runner | 1 |
| Whenever this creature becomes tapped, target creature can't block this turn. | Renegade Wheelsmith | 1 |
| Whenever this creature deals combat damage to a player, for each kind of counter on target permanent or player, give that permanent or player another counter of | Skyship Plunderer | 1 |
| Whenever this creature dies or another artifact you control is put into a graveyard from the battlefield, return to your hand target artifact card in your grave | Scrap Trawler | 1 |
| Whenever this creature enters or attacks, you get {E} for each creature you control. | Aetherwind Basker | 1 |
| You may remove a loyalty counter from a planeswalker you control rather than pay Heart of Kiran's crew cost. | Heart of Kiran | 1 |

## Notes



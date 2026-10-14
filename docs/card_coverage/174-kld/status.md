# Kaladesh (kld)

- Expansion: 174
- Set code: `kld`
- Release date: 2016-09-30
- Cards in scope (Modern/Pioneer/Standard-legal): 246

## Legality

| Format | Legal cards |
|---|---|
| Modern | 246 |
| Pioneer | 246 |
| Standard | 14 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 52 | 21.1% |
| Works (untested) | 166 | 67.5% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 28 | 11.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Aetherborn Marauder | silent | When this creature enters, move any number of +1/+1 counters from other permanents you control onto this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Aethersquall Ancient | silent | Pay eight {E}: Return all other creatures to their owners' hands. Activate only as a sorcery. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Aetherworks Marvel | silent | Whenever a permanent you control is put into a graveyard, you get {E} . | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Animation Module | silent | {3}, {T}: Choose a counter on target permanent or player. Give that permanent or player another counter of that kind. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Aviary Mechanic | silent | When this creature enters, you may return another permanent you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cataclysmic Gearhulk | silent | When this creature enters, each player chooses an artifact, a creature, an enchantment, and a planeswalker from among the nonland permanents they control, then  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Confiscation Coup | silent | Choose target artifact or creature. You get {E}{E}{E}{E} (four energy counters), then you may pay an amount of {E} equal to that permanent's mana value. If you  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Consulate Surveillance | silent | Pay {E}{E}: Prevent all damage that would be dealt to you this turn by a source of your choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Deadlock Trap | silent | {T}, Pay {E}: Tap target creature or planeswalker. Its activated abilities can't be activated this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Depala, Pilot Exemplar | silent | Each Vehicle you control gets +1/+1 as long as it's a creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dovin Baan | silent | +1: Until your next turn, up to one target creature gets -3/-0 and its activated abilities can't be activated. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dubious Challenge | silent | Look at the top ten cards of your library, exile up to two creature cards from among them, then shuffle. Target opponent may choose one of the exiled cards and  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Eager Construct | silent | When this creature enters, each player may scry 1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Empyreal Voyager | silent | Whenever this creature deals combat damage to a player, you get that many {E} . | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gearshift Ace | silent | Whenever this creature crews a Vehicle, that Vehicle gains first strike until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Ghirapur Guide | silent | {2}{G}: Target creature you control can't be blocked by creatures with power 2 or less this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hazardous Conditions | silent | Creatures with no counters on them get -2/-2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hightide Hermit | silent | Pay {E}{E}: This creature can attack this turn as though it didn't have defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Multiform Wonder | silent | Pay {E}: This creature gets +2/-2 or -2/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nissa, Nature's Artisan | silent | −4: Reveal the top two cards of your library. Put all land cards from among them onto the battlefield and the rest into your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rashmi, Eternities Crafter | silent | Whenever you cast your first spell each turn, reveal the top card of your library. You may cast it without paying its mana cost if it's a spell with lesser mana | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Shrewd Negotiation | silent | Exchange control of target artifact you control and target artifact or creature you don't control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Speedway Fanatic | silent | Whenever this creature crews a Vehicle, that Vehicle gains haste until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Verdant Crescendo | silent | Search your library for a basic land card and put it onto the battlefield tapped. Search your library and graveyard for a card named Nissa, Nature's Artisan, re | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Veteran Motorist | silent | Whenever this creature crews a Vehicle, that Vehicle gets +1/+1 until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Built to Last | notice | Target creature gets +2/+2 until end of turn. If it's an artifact creature, it gains indestructible until end of turn. (Damage and effects that say "destroy" do | unparsed remainder: If it's an artifact creature, it gains indestructible until end of turn. | Y/Y/- | not_working |
| Built to Smash | notice | Target attacking creature gets +3/+3 until end of turn. If it's an artifact creature, it gains trample until end of turn. | unparsed remainder: If it's an artifact creature, it gains trample until end of turn. | Y/Y/- | not_working |
| Insidious Will | notice | Choose one — • Counter target spell. • You may choose new targets for target spell. • Copy target instant or sorcery spell. You may choose new targets for the c | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Accomplished Automaton | handled | Fabricate | machines/keywords.py | Y/Y/- | not_tested |
| Acrobatic Maneuver | handled | Exile target creature you control, then return that card to the battlefield under its owner's control. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aerial Responder | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Aether Hub | handled | When this land enters, you get {E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aether Meltdown | handled | When this Aura enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aether Theorist | handled | When this creature enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aetherflux Reservoir | handled | Whenever you cast a spell, you gain 1 life for each spell you've cast this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aethertorch Renegade | handled | When this creature enters, you get {E}{E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ambitious Aetherborn | handled | Fabricate | machines/keywords.py | Y/Y/- | not_tested |
| Appetite for the Unnatural | handled | Destroy target artifact or enchantment. You gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aradara Express | handled | Crew | machines/keywords.py | Y/Y/- | not_tested |
| Arborback Stomper | handled | When this creature enters, you gain 5 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Architect of the Untamed | handled | Landfall — Whenever a land you control enters, you get {E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Attune with Aether | handled | Search your library for a basic land card, reveal it, put it into your hand, then shuffle. You get {E}{E} (two energy counters). | the engine reads this text and performs it | Y/Y/- | not_tested |
| Authority of the Consuls | handled | Creatures your opponents control enter tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Ballista Charger | handled | Whenever this Vehicle attacks, it deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bastion Mastodon | handled | {W}: This creature gains vigilance until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bomat Bazaar Barge | handled | When this Vehicle enters, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Botanical Sanctum | handled | This land enters tapped unless you control two or fewer other lands. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Brazen Scourge | handled | Haste | machines/combat.py | Y/Y/Y | not_tested |
| Bristling Hydra | handled | When this creature enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ceremonious Rejection | handled | Counter target colorless spell. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chandra's Pyrohelix | handled | Chandra's Pyrohelix deals 2 damage divided as you choose among one or two targets. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chandra, Pyrogenius | handled | +2: Chandra deals 2 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cloudblazer | handled | When this creature enters, you gain 2 life and draw two cards. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Cogworker's Puzzleknot | handled | When this artifact enters, create a 1/1 colorless Servo artifact creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Consulate Skygate | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Contraband Kingpin | handled | Whenever an artifact you control enters, scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cowl Prowler | handled |  |  | Y/Y/- | not_tested |
| Curio Vendor | handled |  |  | Y/Y/- | not_tested |
| Decoction Module | handled | Whenever a creature you control enters, you get {E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Demon of Dark Schemes | handled | When this creature enters, all other creatures get -2/-2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dhund Operative | handled | As long as you control an artifact, this creature gets +1/+0 and has deathtouch. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Disappearing Act | handled | As an additional cost to cast this spell, return a permanent you control to its owner's hand. Counter target spell. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dukhara Peafowl | handled | {U}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dukhara Scavenger | handled | When this creature enters, you may put target artifact or creature card from your graveyard on top of your library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Durable Handicraft | handled | Whenever a creature you control enters, you may pay {1}. If you do, put a +1/+1 counter on that creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dynavolt Tower | handled | Whenever you cast an instant or sorcery spell, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Electrostatic Pummeler | handled | When this creature enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Elegant Edgecrafters | handled | This creature can't be blocked by creatures with power 2 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eliminate the Competition | handled | As an additional cost to cast this spell, sacrifice X creatures. Destroy X target creatures. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Embraal Bruiser | handled | This creature enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Engineered Might | handled | Choose one — • Target creature gets +5/+5 and gains trample until end of turn. • Creatures you control get +2/+2 and gain vigilance until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Era of Innovation | handled | Whenever an artifact or Artificer you control enters, you may pay {1}. If you do, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Essence Extraction | handled | Essence Extraction deals 3 damage to target creature and you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Experimental Aviator | handled | When this creature enters, create two 1/1 colorless Thopter artifact creature tokens with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Failed Inspection | handled | Counter target spell. Draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fairgrounds Warden | handled | When this creature enters, exile target creature an opponent controls until this creature leaves the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Filigree Familiar | handled | When this creature enters, you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fireforger's Puzzleknot | handled | When this artifact enters, it deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Flame Lash | handled | Flame Lash deals 4 damage to any target. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Fleetwheel Cruiser | handled | When this Vehicle enters, it becomes an artifact creature until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fortuitous Find | handled | Choose one or both — • Return target artifact card from your graveyard to your hand. • Return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Foundry Inspector | handled | Artifact spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Foundry Screecher | handled | This creature gets +1/+0 as long as you control an artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fragmentize | handled | Destroy target artifact or enchantment with mana value 4 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fretwork Colony | handled | This creature can't block. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Furious Reprisal | handled | Furious Reprisal deals 2 damage to each of two targets. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gearseeker Serpent | handled | {5}{U}: This creature can't be blocked this turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Giant Spectacle | handled | Enchanted creature gets +2/+1 and has menace. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Glassblower's Puzzleknot | handled | When this artifact enters, scry 2, then you get {E}{E}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Glimmer of Genius | handled | Scry 2, then draw two cards. You get {E}{E} (two energy counters). | the engine reads this text and performs it | Y/Y/- | not_tested |
| Glint-Nest Crane | handled | When this creature enters, look at the top four cards of your library. You may reveal an artifact card from among them and put it into your hand. Put the rest o | the engine reads this text and performs it | Y/Y/- | not_tested |
| Glint-Sleeve Artisan | handled | Fabricate | machines/keywords.py | Y/Y/- | not_tested |
| Guardian of the Great Conduit | handled | As long as you control a Nissa planeswalker, this creature gets +2/+0 and has vigilance. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Harsh Scrutiny | handled | Target opponent reveals their hand. You choose a creature card from it. That player discards that card. Scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Herald of the Fair | handled | When this creature enters, target creature you control gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Highspire Artisan | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Impeccable Timing | handled | Impeccable Timing deals 3 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Incendiary Sabotage | handled | As an additional cost to cast this spell, sacrifice an artifact. Incendiary Sabotage deals 3 damage to each creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inventor's Apprentice | handled | This creature gets +1/+1 as long as you control an artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inventor's Goggles | handled | Equipped creature gets +1/+2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inventors' Fair | handled | At the beginning of your upkeep, if you control three or more artifacts, you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Iron League Steed | handled | Haste | machines/combat.py | Y/Y/- | not_tested |
| Janjeet Sentry | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kambal, Consul of Allocation | handled | Whenever an opponent casts a noncreature spell, that player loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Key to the City | handled | {T}, Discard a card: Up to one target creature can't be blocked this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kujar Seedsculptor | handled | When this creature enters, put a +1/+1 counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Larger Than Life | handled | Target creature gets +4/+4 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lathnu Hellion | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lawless Broker | handled | When this creature dies, put a +1/+1 counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Liberating Combustion | handled | Liberating Combustion deals 6 damage to target creature. You may search your library and/or graveyard for a card named Chandra, Pyrogenius, reveal it, and put i | the engine reads this text and performs it | Y/Y/- | not_tested |
| Live Fast | handled | You draw two cards, lose 2 life, and get {E}{E} (two energy counters). | the engine reads this text and performs it | Y/Y/- | not_tested |
| Longtusk Cub | handled | Whenever this creature deals combat damage to a player, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Make Obsolete | handled | Creatures your opponents control get -1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Malfunction | handled | When this Aura enters, tap enchanted permanent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Marionette Master | handled | Whenever an artifact you control is put into a graveyard from the battlefield, target opponent loses life equal to this creature's power. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Master Trinketeer | handled | Servos and Thopters you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Metalspinner's Puzzleknot | handled | When this artifact enters, you draw a card and you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Minister of Inquiries | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Morbid Curiosity | handled | As an additional cost to cast this spell, sacrifice an artifact or creature. Draw cards equal to the mana value of the sacrificed permanent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Narnam Cobra | handled | {G}: This creature gains deathtouch until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nature's Way | handled | Target creature you control gains vigilance and trample until end of turn. It deals damage equal to its power to target creature you don't control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Night Market Lookout | handled | Whenever this creature becomes tapped, each opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nimble Innovator | handled | When this creature enters, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ninth Bridge Patrol | handled | Whenever another creature you control leaves the battlefield, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nissa, Vital Force | handled | +1: Untap target land you control. Until your next turn, it becomes a 5/5 Elemental creature with haste. It's still a land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ornamental Courage | handled | Untap target creature. It gets +1/+3 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ovalchase Daredevil | handled | Whenever an artifact you control enters, you may return this card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ovalchase Dragster | handled | Haste | machines/combat.py | Y/Y/- | not_tested |
| Oviya Pashiri, Sage Lifecrafter | handled | {2}{G}, {T}: Create a 1/1 colorless Servo artifact creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Peema Outrider | handled | Trample | machines/combat.py | Y/Y/- | not_tested |
| Perpetual Timepiece | handled | {T}: Mill two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pia Nalaar | handled | When Pia Nalaar enters, create a 1/1 colorless Thopter artifact creature token with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prakhata Club Security | handled |  |  | Y/Y/- | not_tested |
| Prakhata Pillar-Bug | handled | {B}: This creature gains lifelink until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Propeller Pioneer | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Quicksmith Genius | handled | Whenever an artifact you control enters, you may discard a card. If you do, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reckless Fireweaver | handled | Whenever an artifact you control enters, this creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Refurbish | handled | Return target artifact card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Renegade Firebrand | handled | As long as you control a Chandra planeswalker, this creature gets +1/+0 and has first strike. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Renegade Freighter | handled | Whenever this Vehicle attacks, it gets +1/+1 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Renegade Tactics | handled | Target creature can't block this turn. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Restoration Gearsmith | handled | When this creature enters, return target artifact or creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Revolutionary Rebuff | handled | Counter target nonartifact spell unless its controller pays {2}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ruinous Gremlin | handled | {2}{R}, Sacrifice this creature: Destroy target artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rush of Vitality | handled | Target creature gets +1/+0 and gains lifelink and indestructible until end of turn. (Damage dealt by that creature also causes its controller to gain that much  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sage of Shaila's Claim | handled | When this creature enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Saheeli Rai | handled | +1: Scry 1. Saheeli Rai deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Saheeli's Artistry | handled | Choose one or both — • Create a token that's a copy of target artifact. • Create a token that's a copy of target creature, except it's an artifact in addition t | the engine reads this text and performs it | Y/Y/- | not_tested |
| Salivating Gremlins | handled | Whenever an artifact you control enters, this creature gets +2/+0 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Select for Inspection | handled | Return target tapped creature to its owner's hand. Scry 1. (Look at the top card of your library. You may put that card on the bottom.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Self-Assembler | handled | When this creature enters, you may search your library for an Assembly-Worker creature card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Servo Exhibition | handled | Create two 1/1 colorless Servo artifact creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sky Skiff | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Skyship Stalker | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skysovereign, Consul Flagship | handled | Whenever Skysovereign enters or attacks, it deals 3 damage to target creature or planeswalker an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skyswirl Harrier | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Skywhaler's Shot | handled | Destroy target creature with power 3 or greater. Scry 1. (Look at the top card of your library. You may put that card on the bottom.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Snare Thopter | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Spireside Infiltrator | handled | Whenever this creature becomes tapped, it deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spontaneous Artist | handled | When this creature enters, you get {E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Start Your Engines | handled | Vehicles you control become artifact creatures until end of turn. Creatures you control get +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Subtle Strike | handled | Choose one or both — • Target creature gets -1/-1 until end of turn. • Put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Syndicate Trafficker | handled | {1}, Sacrifice an artifact: Put a +1/+1 counter on this creature. It gains indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Take Down | handled | Choose one — • Take Down deals 4 damage to target creature with flying. • Take Down deals 1 damage to each creature with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tasseled Dromedary | handled |  |  | Y/Y/- | not_tested |
| Terrain Elemental | handled |  |  | Y/Y/- | not_tested |
| Terror of the Fairgrounds | handled |  |  | Y/Y/- | not_tested |
| Tezzeret's Ambition | handled | Draw three cards. If you control no artifacts, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thriving Grubs | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thriving Ibex | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thriving Rats | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thriving Rhino | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thriving Turtle | handled | When this creature enters, you get {E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tidy Conclusion | handled | Destroy target creature. You gain 1 life for each artifact you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Toolcraft Exemplar | handled | At the beginning of combat on your turn, if you control an artifact, this creature gets +2/+1 until end of turn. If you control three or more artifacts, it also | the engine reads this text and performs it | Y/Y/- | not_tested |
| Torch Gauntlet | handled | Equipped creature gets +2/+0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Underhanded Designs | handled | Whenever an artifact you control enters, you may pay {1}. If you do, each opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Unlicensed Disintegration | handled | Destroy target creature. If you control an artifact, Unlicensed Disintegration deals 3 damage to that creature's controller. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vedalken Blademaster | handled | Prowess | machines/keywords.py | Y/Y/- | not_tested |
| Verdurous Gearhulk | handled | When this creature enters, distribute four +1/+1 counters among any number of target creatures you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Visionary Augmenter | handled | Fabricate | machines/keywords.py | Y/Y/- | not_tested |
| Wayward Giant | handled | Menace | machines/combat.py | Y/Y/- | not_tested |
| Weaponcraft Enthusiast | handled | Fabricate | machines/keywords.py | Y/Y/- | not_tested |
| Weldfast Monitor | handled | {R}: This creature gains menace until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Weldfast Wingsmith | handled | Whenever an artifact you control enters, this creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Welding Sparks | handled | Welding Sparks deals X damage to target creature, where X is 3 plus the number of artifacts you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Whirler Virtuoso | handled | When this creature enters, you get {E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Whirlermaker | handled | {4}, {T}: Create a 1/1 colorless Thopter artifact creature token with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wild Wanderer | handled | When this creature enters, you may search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wildest Dreams | handled | Return X target cards from your graveyard to your hand. Exile Wildest Dreams. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wily Bandar | handled | {2}{G}: This creature gains indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wispweaver Angel | handled | When this creature enters, you may exile another target creature you control, then return that card to the battlefield under its owner's control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Woodweaver's Puzzleknot | handled | When this artifact enters, you gain 3 life and get {E}{E}{E} . | the engine reads this text and performs it | Y/Y/- | not_tested |
| Workshop Assistant | handled | When this creature dies, return another target artifact card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>52 cards</summary>

- Aetherstorm Roc
- Angel of Invention
- Armorcraft Judge
- Blooming Marsh
- Blossoming Defense
- Bomat Courier
- Captured by the Consulate
- Cathartic Reunion
- Chandra, Torch of Defiance
- Combustible Gearhulk
- Commencement of Festivities
- Concealed Courtyard
- Consul's Shieldguard
- Cultivator of Blades
- Cultivator's Caravan
- Demolition Stomper
- Die Young
- Dramatic Reversal
- Eddytrail Hawk
- Fabrication Module
- Fairgrounds Trumpeter
- Fateful Showdown
- Fumigate
- Ghirapur Orrery
- Gonti, Lord of Luxury
- Harnessed Lightning
- Hijack
- Inspiring Vantage
- Long-Finned Skywhale
- Lost Legacy
- Madcap Experiment
- Maulfist Doorbuster
- Maulfist Squad
- Metallurgic Summonings
- Metalwork Colossus
- Midnight Oil
- Noxious Gearhulk
- Padeem, Consul of Innovation
- Panharmonicon
- Paradoxical Outcome
- Revoke Privileges
- Riparian Tiger
- Scrapheap Scrounger
- Sequestered Stash
- Servant of the Conduit
- Smuggler's Copter
- Spark of Creativity
- Spirebluff Canal
- Territorial Gorger
- Torrential Gearhulk
- Trusty Companion
- Voltaic Brawler

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Choose one | 1 | Insidious Will | kld |
| +N: until your next turn, up to one target creature gets -N/-N and its activated abilities can't be activated. | 1 | Dovin Baan | kld |
| choose target artifact or creature. you get {M}{M}{M}{M} (four energy counters), then you may pay an amount of {M} equal to that permanent's mana value. if you  | 1 | Confiscation Coup | kld |
| creatures with no counters on them get -N/-N until end of turn. | 1 | Hazardous Conditions | kld |
| each vehicle you control gets +N/+N as long as it's a creature. | 1 | Depala, Pilot Exemplar | kld |
| exchange control of target artifact you control and target artifact or creature you don't control. | 1 | Shrewd Negotiation | kld |
| look at the top ten cards of your library, exile up to two creature cards from among them, then shuffle. target opponent may choose one of the exiled cards and  | 1 | Dubious Challenge | kld |
| pay eight {M}: return all other creatures to their owners' hands. activate only as a sorcery. | 1 | Aethersquall Ancient | kld |
| pay {M}: ~ gets +N/-N or -N/+N until end of turn. | 1 | Multiform Wonder | kld |
| pay {M}{M}: prevent all damage that would be dealt to you ~ by a source of your choice. | 1 | Consulate Surveillance | kld |
| pay {M}{M}: ~ can attack ~ as though it didn't have defender. | 1 | Hightide Hermit | kld |
| search your library for a basic land card and put it onto the battlefield tapped. search your library and graveyard for a card named nissa, nature's artisan, re | 1 | Verdant Crescendo | kld |
| target attacking creature gets +N/+N until end of turn. if it's an artifact creature, it gains trample until end of turn. | 1 | Built to Smash | kld |
| target creature gets +N/+N until end of turn. if it"..."t destroy it.) | 1 | Built to Last | kld |
| when ~ enters, each player chooses an artifact, a creature, an enchantment, and a planeswalker from among the nonland permanents they control, then sacrifices t | 1 | Cataclysmic Gearhulk | kld |
| when ~ enters, each player may scry N. | 1 | Eager Construct | kld |
| when ~ enters, move any number of +N/+N counters from other permanents you control onto ~. | 1 | Aetherborn Marauder | kld |
| when ~ enters, you may return another permanent you control to its owner's hand. | 1 | Aviary Mechanic | kld |
| whenever a permanent you control is put into a graveyard, you get {M} . | 1 | Aetherworks Marvel | kld |
| whenever you cast your first spell each turn, reveal the top card of your library. you may cast it without paying its mana cost if it"..."t cast it, put it into | 1 | Rashmi, Eternities Crafter | kld |
| whenever ~ crews a vehicle, that vehicle gains first strike until end of turn. | 1 | Gearshift Ace | kld |
| whenever ~ crews a vehicle, that vehicle gains haste until end of turn. | 1 | Speedway Fanatic | kld |
| whenever ~ crews a vehicle, that vehicle gets +N/+N until end of turn. | 1 | Veteran Motorist | kld |
| whenever ~ deals combat damage to a player, you get that many {M} . | 1 | Empyreal Voyager | kld |
| {M}, pay {M}: tap target creature or planeswalker. its activated abilities can't be activated ~. | 1 | Deadlock Trap | kld |
| {M}, {M}: choose a counter on target permanent or player. give that permanent or player another counter of that kind. | 1 | Animation Module | kld |
| {M}{M}: target creature you control can't be blocked by creatures with power N or less ~. | 1 | Ghirapur Guide | kld |
| −N: reveal the top two cards of your library. put all land cards from among them onto the battlefield and the rest into your hand. | 1 | Nissa, Nature's Artisan | kld |

## Notes



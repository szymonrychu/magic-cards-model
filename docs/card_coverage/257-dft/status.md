# Aetherdrift (dft)

- Expansion: 257
- Set code: `dft`
- Release date: 2025-02-14
- Cards in scope (Modern/Pioneer/Standard-legal): 256

## Legality

| Format | Legal cards |
|---|---|
| Modern | 256 |
| Pioneer | 256 |
| Standard | 256 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 8 | 3.1% |
| Partial (unaudited) | 18 | 7.0% |
| Not tested (handled, untested) | 95 | 37.1% |
| Not working (silent / notice / error) | 135 | 52.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Aatchik, Emerald Radian | silent | When Aatchik enters, create a 1/1 green Insect creature token for each artifact and/or creature card in your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Adrenaline Jockey | silent | Whenever you activate an exhaust ability, put a +1/+1 counter on this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/Y | not_working |
| Aether Syphon | silent | Max speed — Whenever you draw a card, each opponent mills two cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Afterburner Expert | silent | Whenever you activate an exhaust ability, return this card from your graveyard to the battlefield. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/Y | not_working |
| Alacrian Armory | silent | At the beginning of combat on your turn, choose up to one target Mount or Vehicle you control. Until end of turn, that permanent becomes saddled if it's a Mount | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Alacrian Jaguar | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Amonkhet Raceway | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Ancient Vendetta | silent | Choose a card name. Search target opponent's graveyard, hand, and library for up to four cards with that name and exile them. Then that player shuffles. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Apocalypse Runner | silent | {T}: Target creature you control with power 2 or less gains lifelink until end of turn and can't be blocked this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Autarch Mammoth | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Avishkar Raceway | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Back on Track | silent | Return target creature or Vehicle card from your graveyard to the battlefield. Create a 1/1 colorless Pilot creature token with "This token saddles Mounts and c | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Boom Scholar | silent | Exhaust — {4}{R}{G}: Creatures and Vehicles you control gain trample until end of turn. Put two +1/+1 counters on this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Brightfield Glider | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Brightfield Mustang | silent | Whenever this creature attacks while saddled, untap it and put a +1/+1 counter on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Bulwark Ox | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Burnout Bashtronaut | silent | Max speed — This creature has double strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Canyon Vaulter | silent | Whenever this creature saddles a Mount or crews a Vehicle during your main phase, that Mount or Vehicle gains flying until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/Y | not_working |
| Carrion Cruiser | silent | When this Vehicle enters, mill two cards. Then return a creature or Vehicle card from your graveyard to your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Chandra, Spark Hunter | silent | At the beginning of combat on your turn, choose up to one target Vehicle you control. Until end of turn, it becomes an artifact creature and gains haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Cloudspire Coordinator | silent | {T}: Create X 1/1 colorless Pilot creature tokens, where X is the number of Mounts and/or Vehicles that entered the battlefield under your control this turn. Th | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Coalstoke Gearhulk | silent | When this creature enters, put target creature card with mana value 4 or less from a graveyard onto the battlefield under your control with a finality counter o | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Cryptcaller Chariot | silent | Whenever you discard one or more cards, create that many tapped 2/2 black Zombie creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Cursecloth Wrappings | silent | {T}: Target creature card in your graveyard gains embalm until end of turn. The embalm cost is equal to its mana cost. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Daretti, Rocketeer Engineer | silent | Whenever Daretti enters or attacks, choose target artifact card in your graveyard. You may sacrifice an artifact. If you do, return the chosen card to the battl | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Detention Chariot | silent | When this Vehicle enters, exile target artifact or creature an opponent controls until this Vehicle leaves the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| District Mascot | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Diversion Unit | silent | {U}, Sacrifice this creature: Counter target instant or sorcery spell unless its controller pays {3}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Dracosaur Auxiliary | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Dredger's Insight | silent | Whenever one or more artifact and/or creature cards leave your graveyard, you gain 1 life. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/Y | not_working |
| Earthrumbler | silent | Exile an artifact or creature card from your graveyard: This Vehicle becomes an artifact creature until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Embalmed Ascendant | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Endrider Catalyzer | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Endrider Spikespitter | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Fang Guardian | silent | When this creature enters, another target creature or Vehicle you control gets +2/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Fang-Druid Summoner | silent | When this creature enters, you may search your library and/or graveyard for a creature card with no abilities, reveal it, and put it into your hand. If you sear | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Far Fortune, End Boss | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Full Throttle | silent | After this main phase, there are two additional combat phases. At the beginning of each combat this turn, untap all creatures that attacked this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Gas Guzzler | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Gastal Raider | silent | Max speed — This creature gets +1/+1 and has menace. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Gastal Thrillroller | silent | When this Vehicle enters, it becomes an artifact creature until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Gastal Thrillseeker | silent | Max speed — This creature has deathtouch and haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Gilded Ghoda | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Glitch Ghost Surveyor | silent | Start your engines! | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Gloryheath Lynx | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Goblin Surveyor | silent | Start your engines! | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Gonti, Night Minister | silent | Whenever a player casts a spell they don't own, that player creates a Treasure token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Guardian Sunmare | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Guidelight Matrix | silent | {2}, {T}: Target Mount you control becomes saddled until end of turn. Activate only as a sorcery. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Guidelight Pathmaker | silent | When this Vehicle enters, you may search your library for an artifact card and reveal it. Put it onto the battlefield if its mana value is 2 or less. Otherwise, | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Haunt the Network | silent | Choose target opponent. Create two 1/1 colorless Thopter artifact creature tokens with flying. Then the chosen player loses X life and you gain X life, where X  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Hazoret, Godseeker | silent | Start your engines! | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Hellish Sideswipe | silent | As an additional cost to cast this spell, sacrifice an artifact or creature. Destroy target creature or Vehicle. If the sacrificed permanent was a Vehicle, draw | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Hour of Victory | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Howler's Heavy | silent | When you cycle this card, target creature or Vehicle an opponent controls gets -3/-0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Howlsquad Heavy | silent | At the beginning of combat on your turn, create a 1/1 red Goblin creature token. That token attacks this combat if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Kickoff Celebrations | silent | Max speed — Sacrifice this enchantment: Creatures and Vehicles you control gain haste until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Kolodin, Triumph Caster | silent | Mounts and Vehicles you control have haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Lagorin, Soul of Alacria | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Leonin Surveyor | silent | Start your engines! | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Lifecraft Engine | silent | Vehicle creatures you control are the chosen creature type in addition to their other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Lightwheel Enhancements | silent | Enchanted permanent gets +1/+1 and has vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Lotusguard Disciple | silent | When this creature enters, target creature or Vehicle gains lifelink and indestructible until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Loxodon Surveyor | silent | Start your engines! | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Magmakin Artillerist | silent | Whenever you discard one or more cards, this creature deals that much damage to each opponent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Marshals' Pathcruiser | silent | Exhaust — {W}{U}{B}{R}{G}: This Vehicle becomes an artifact creature. Put two +1/+1 counters on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Mendicant Core, Guidelight | silent | Max speed — Whenever you cast an artifact spell, you may pay {1}. If you do, copy it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Midnight Mangler | silent | During turns other than yours, this Vehicle is an artifact creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Mindspring Merfolk | silent | Exhaust — {X}{U}{U}, {T}: Draw X cards. Put a +1/+1 counter on each Merfolk creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Momentum Breaker | silent | When this enchantment enters, each opponent sacrifices a creature or Vehicle of their choice. Each opponent who can't discards a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Mu Yanling, Wind Rider | silent | When Mu Yanling enters, create a 3/2 colorless Vehicle artifact token with crew 1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Muraganda Raceway | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Mutant Surveyor | silent | Start your engines! | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Nesting Bot | silent | Max speed — This creature gets +1/+0. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Ooze Patrol | silent | When this creature enters, mill two cards, then put a +1/+1 counter on this creature for each artifact and/or creature card in your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Outpace Oblivion | silent | {2}, Sacrifice this enchantment: It deals 2 damage to each player who doesn't have max speed. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Oviya, Automech Artisan | silent | Each creature that's attacking one of your opponents has trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Perilous Snare | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Pit Automaton | silent | {2}, {T}: When you next activate an exhaust ability that isn't a mana ability this turn, copy it. You may choose new targets for the copy. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Point the Way | silent | {3}{G}, Sacrifice this enchantment: Search your library for up to X basic land cards, where X is your speed. Put those cards onto the battlefield tapped, then s | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Possession Engine | silent | When this Vehicle enters, gain control of target creature an opponent controls for as long as you control this Vehicle. That creature can't attack or block for  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Pride of the Road | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Quag Feast | silent | Choose target creature, planeswalker, or Vehicle. Mill two cards, then destroy the chosen permanent if its mana value is less than or equal to the number of car | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Racers' Scoreboard | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Rangers' Aetherhive | silent | Whenever you activate an exhaust ability, create a 1/1 colorless Thopter artifact creature token with flying. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/Y | not_working |
| Rangers' Refueler | silent | Whenever you activate an exhaust ability, draw a card. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/Y | not_working |
| Reckless Velocitaur | silent | Whenever this creature saddles a Mount or crews a Vehicle during your main phase, that Mount or Vehicle gets +2/+0 and gains trample until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/Y | not_working |
| Redshift, Rocketeer Chief | silent | {T}: Add X mana of any one color, where X is Redshift's power. Spend this mana only to activate abilities. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Rise from the Wreck | silent | Return up to one target creature card, up to one target Mount card, up to one target Vehicle card, and up to one target creature card with no abilities from you | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Risen Necroregent | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Risky Shortcut | silent | Draw two cards. Each player loses 2 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Riverchurn Monument | silent | {1}, {T}: Any number of target players each mill two cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Road Rage | silent | Road Rage deals X damage to target creature or planeswalker, where X is 2 plus the number of Mounts and Vehicles you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Roadside Assistance | silent | Enchanted permanent gets +1/+1 and has lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Rocketeer Boostbuggy | silent | Exhaust — {3}: This Vehicle becomes an artifact creature. Put a +1/+1 counter on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Samut, the Driving Force | silent | Start your engines! | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Shefet Archfiend | silent | When this creature enters, all other creatures get -2/-2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Silken Strength | silent | When this Aura enters, untap enchanted permanent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Sita Varma, Masked Racer | silent | Exhaust — {X}{G}{G}{U}: Put X +1/+1 counters on Sita Varma. Then you may have the base power and toughness of each other creature you control become equal to Si | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Skyserpent Seeker | silent | Exhaust — {4}: Reveal cards from the top of your library until you reveal two land cards. Put those land cards onto the battlefield tapped and the rest on the b | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Slick Imitator | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Spectacular Pileup | silent | All creatures and Vehicles lose indestructible until end of turn, then destroy all creatures and Vehicles. Cycling {2} ({2}, Discard this card: Draw a card.) | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Spikeshell Harrier | silent | When this creature enters, return target creature or Vehicle an opponent controls to its owner's hand. If that opponent's speed is greater than each other playe | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Spire Mechcycle | silent | Exhaust — Tap another untapped Mount or Vehicle you control: This Vehicle becomes an artifact creature. Put a +1/+1 counter on it for each Mount and/or Vehicle  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Starting Column | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Streaking Oilgorger | silent | Max speed — This creature has lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Swiftwing Assailant | silent | Max speed — This creature gets +0/+1 and has vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| The Aetherspark | silent | +1: Attach The Aetherspark to up to one target creature you control. Put a +1/+1 counter on that creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| The Speed Demon | silent | At the beginning of your end step, you draw X cards and lose X life, where X is your speed. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Trade the Helm | silent | Exchange control of target artifact or creature you control and target artifact or creature an opponent controls. Cycling {2} ({2}, Discard this card: Draw a ca | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Transit Mage | silent | When this creature enters, you may search your library for an artifact card with mana value 4 or 5, reveal it, put it into your hand, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Unswerving Sloth | silent | Whenever this creature attacks while saddled, it gains indestructible until end of turn. Untap all creatures you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Valor's Flagship | silent | When you cycle this card, create X 1/1 colorless Pilot creature tokens with "This token saddles Mounts and crews Vehicles as though its power were 2 greater." | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Venomsac Lagac | silent | Saddle | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Veteran Beastrider | silent | At the beginning of your end step, untap each creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Vnwxt, Verbose Host | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Voyager Glidecar | silent | Tap three other untapped creatures you control: Until end of turn, this Vehicle becomes an artifact creature and gains flying. Put a +1/+1 counter on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Walking Sarcophagus | silent | Max speed — This creature gets +1/+2. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Waxen Shapethief | silent | You may have this creature enter as a copy of an artifact or creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Winter, Cursed Rider | silent | Exhaust — {2}{U}{B}, {T}, Exile X artifact cards from your graveyard: Each other nonartifact creature gets -X/-X until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Zahur, Glory's Past | silent | Max speed | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Brightglass Gearhulk | notice | When this creature enters, you may search your library for up to two artifact, creature, and/or enchantment cards with mana value 1 or less, reveal them, put th | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Collision Course | notice | Choose one — • Collision Course deals X damage to target creature, where X is the number of permanents you control that are creatures and/or Vehicles. • Destroy | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Crash and Burn | notice | Choose one — • Destroy target Vehicle. • Crash and Burn deals 6 damage to target creature or planeswalker. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Defend the Rider | notice | Choose one — • Target permanent you control gains hexproof and indestructible until end of turn. • Create a 1/1 colorless Pilot creature token with "This token  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Demonic Junker | notice | When this Vehicle enters, for each player, destroy up to one target creature that player controls. If a creature you controlled was destroyed this way, put two  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Gastal Blockbuster | notice | When this creature enters, you may sacrifice a creature or Vehicle. When you do, destroy target artifact an opponent controls. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Grim Javelineer | notice | Whenever you attack, target attacking creature gets +1/+0 until end of turn. When that creature dies this turn, surveil 1. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| March of the World Ooze | notice | Creatures you control have base power and toughness 6/6 and are Oozes in addition to their other types. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Oildeep Gearhulk | notice | When this creature enters, look at target player's hand. You may choose a card from it. If you do, that player discards that card, then draws a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Pedal to the Metal | notice | Target creature gets +X/+0 and gains first strike until end of turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Push the Limit | notice | Return all Mount and Vehicle cards from your graveyard to the battlefield. Sacrifice them at the beginning of the next end step. Vehicles you control become art | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Riptide Gearhulk | notice | When this creature enters, for each opponent, put up to one target nonland permanent that player controls into its owner's library third from the top. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| The Last Ride | notice | The Last Ride gets -X/-X, where X is your life total. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Tune Up | notice | Return target artifact card from your graveyard to the battlefield. If it's a Vehicle, it becomes an artifact creature. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Caradora, Heart of Alacria | unaudited | If one or more +1/+1 counters would be put on a creature or Vehicle you control, that many plus one +1/+1 counters are put on it instead. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Chitin Gravestalker | unaudited | This spell costs {1} less to cast for each artifact and/or creature card in your graveyard. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Cloudspire Captain | unaudited | This creature saddles Mounts and crews Vehicles as though its power were 2 greater. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Country Roads | unaudited | This land enters tapped unless you control a Mount or Vehicle. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Deathless Pilot | unaudited | This creature saddles Mounts and crews Vehicles as though its power were 2 greater. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Dynamite Diver | unaudited | This creature saddles Mounts and crews Vehicles as though its power were 2 greater. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Elvish Refueler | unaudited | During your turn, as long as you haven't activated an exhaust ability this turn, you may activate exhaust abilities as though they haven't been activated. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Foul Roads | unaudited | This land enters tapped unless you control a Mount or Vehicle. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Interface Ace | unaudited | This creature saddles Mounts and crews Vehicles using its toughness rather than its power. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Lumbering Worldwagon | unaudited | This Vehicle's power is equal to the number of lands you control. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Mimeoplasm, Revered One | unaudited | As Mimeoplasm enters, exile up to X creature cards from your graveyard. It enters with three +1/+1 counters on it for each creature card exiled this way. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Reef Roads | unaudited | This land enters tapped unless you control a Mount or Vehicle. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Rocky Roads | unaudited | This land enters tapped unless you control a Mount or Vehicle. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Sab-Sunen, Luxa Embodied | unaudited | Sab-Sunen can't attack or block unless it has an even number of counters on it. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Skyseer's Chariot | unaudited | Activated abilities of sources with the chosen name cost {2} more to activate. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Thunderous Velocipede | unaudited | Each other Vehicle and creature you control enters with an additional +1/+1 counter on it if its mana value is 4 or less. Otherwise, it enters with three additi | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Wickerfolk Indomitable | unaudited | You may cast this card from your graveyard by paying 2 life and sacrificing an artifact or creature in addition to paying its other costs. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Wild Roads | unaudited | This land enters tapped unless you control a Mount or Vehicle. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Aetherjacket | handled | {2}, {T}, Sacrifice this creature: Destroy another target artifact. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Agonasaur Rex | handled | When you cycle this card, put two +1/+1 counters on up to one target creature or Vehicle. It gains trample and indestructible until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Air Response Unit | handled | Flying | machines/combat.py | Y/Y/Y | not_tested |
| Basri, Tomorrow's Champion | handled | {W}, {T}, Exert Basri: Create a 1/1 white Cat creature token with lifelink. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Beastrider Vanguard | handled | {4}{G}: Look at the top three cards of your library. You may reveal a permanent card from among them and put it into your hand. Put the rest on the bottom of yo | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bestow Greatness | handled | Target creature gets +4/+4 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bleachbone Verge | handled |  |  | Y/Y/Y | not_tested |
| Boosted Sloop | handled | Whenever you attack, draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bounce Off | handled | Return target creature or Vehicle to its owner's hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Broadcast Rambler | handled | When this Vehicle enters, create a 1/1 colorless Thopter artifact creature token with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Broadside Barrage | handled | Broadside Barrage deals 5 damage to target creature or planeswalker. Draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Broodheart Engine | handled | At the beginning of your upkeep, surveil 1. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Burner Rocket | handled | When this Vehicle enters, target creature you control gets +2/+0 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Caelorna, Coral Tyrant | handled |  |  | Y/Y/Y | not_tested |
| Camera Launcher | handled | Exhaust — {3}: Put a +1/+1 counter on this creature. Create a 1/1 colorless Thopter artifact creature token with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Clamorous Ironclad | handled | Crew | machines/keywords.py | Y/Y/Y | not_tested |
| Cloudspire Skycycle | handled | When this Vehicle enters, distribute two +1/+1 counters among one or two other target Vehicles and/or creatures you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Count on Luck | handled | At the beginning of your upkeep, exile the top card of your library. You may play that card this turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Daring Mechanic | handled | {3}{W}: Put a +1/+1 counter on target Mount or Vehicle. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Debris Beetle | handled | When this Vehicle enters, each opponent loses 3 life and you gain 3 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Draconautics Engineer | handled | Exhaust — {R}: Other creatures you control gain haste until end of turn. Put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dune Drifter | handled | When this Vehicle enters, return target artifact or creature card with mana value X or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Engine Rat | handled | {5}{B}: Each opponent loses 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Explosive Getaway | handled | Exile up to one target artifact or creature. Return it to the battlefield under its owner's control at the beginning of the next end step. Explosive Getaway dea | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Fearless Swashbuckler | handled | Vehicles you control have haste. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Flood the Engine | handled | When this Aura enters, tap enchanted permanent. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Fuel the Flames | handled | Fuel the Flames deals 2 damage to each creature. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Gallant Strike | handled | Destroy target creature with toughness 4 or greater. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Greasewrench Goblin | handled | Exhaust — {2}{R}: Discard up to two cards, then draw that many cards. Put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Grim Bauble | handled | When this artifact enters, target creature an opponent controls gets -2/-2 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Guidelight Optimizer | handled |  |  | Y/Y/Y | not_tested |
| Guidelight Synergist | handled | This creature gets +1/+0 for each artifact you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Haunted Hellride | handled | Whenever you attack, target creature you control gets +1/+0 and gains deathtouch until end of turn. Untap it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Hazard of the Dunes | handled | Exhaust — {6}{G}: Put three +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Hulldrifter | handled | When this Vehicle enters, draw two cards. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Intimidation Tactics | handled | Target opponent reveals their hand. You choose an artifact or creature card from it. Exile that card. Cycling {3} ({3}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Jibbirik Omnivore | handled |  |  | Y/Y/Y | not_tested |
| Kalakscion, Hunger Tyrant | handled |  |  | Y/Y/Y | not_tested |
| Keen Buccaneer | handled | Exhaust — {1}{U}: Draw a card, then discard a card. Put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Lightshield Parry | handled | Target creature gets +2/+2 until end of turn. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Locust Spray | handled | Target creature gets -1/-1 until end of turn. Cycling {B} ({B}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Loot, the Pathfinder | handled | Exhaust — {U}, {T}: Draw three cards. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Marketback Walker | handled | This creature enters with X +1/+1 counters on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Maximum Overdrive | handled | Put a +1/+1 counter on target creature. It gains deathtouch and indestructible until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Memory Guardian | handled | Flying | machines/combat.py | Y/Y/Y | not_tested |
| Migrating Ketradon | handled | When this creature enters, you gain 4 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Molt Tender | handled | {T}: Mill a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Monument to Endurance | handled | Whenever you discard a card, choose one that hasn't been chosen this turn — • Draw a card. • Create a Treasure token. • Each opponent loses 3 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Night Market | handled | This land enters tapped. As it enters, choose a color. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Nimble Thopterist | handled | When this creature enters, create a 1/1 colorless Thopter artifact creature token with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pacesetter Paragon | handled | Exhaust — {2}{R}: Put a +1/+1 counter on this creature. It gains double strike until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pactdoll Terror | handled | Whenever this creature or another artifact you control enters, each opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Plow Through | handled | Choose one — • Target creature you control fights target creature an opponent controls. (Each deals damage equal to its power to the other.) • Destroy target Ve | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pothole Mole | handled | When this creature enters, mill three cards, then you may return a land card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Prowcatcher Specialist | handled | Exhaust — {3}{R}: Put two +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pyrewood Gearhulk | handled | When this creature enters, other creatures you control get +2/+2 and gain vigilance and menace until end of turn. Damage can't be prevented this turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Regal Imperiosaur | handled | Other Dinosaurs you control get +1/+1. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Repurposing Bay | handled | {2}, {T}, Sacrifice another artifact: Search your library for an artifact card with mana value equal to 1 plus the sacrificed artifact's mana value, put that ca | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Ride's End | handled | This spell costs {3} less to cast if it targets a tapped permanent. Exile target creature or Vehicle. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Ripclaw Wrangler | handled | When this Vehicle enters, each opponent discards a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Riverpyre Verge | handled |  |  | Y/Y/Y | not_tested |
| Roadside Blowout | handled | This spell costs {2} less to cast if it targets a permanent with mana value 1. Return target creature or Vehicle an opponent controls to its owner's hand. Draw  | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Rover Blades | handled | Equipped creature has double strike. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Run Over | handled | This spell costs {1} less to cast if it targets a Mount or Vehicle you control. Target creature you control deals damage equal to its power to target creature a | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sabotage Strategist | handled | Whenever one or more creatures attack you, those creatures get -1/-0 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Salvation Engine | handled | Other artifact creatures you control get +2/+2. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Scrap Compactor | handled | {3}, {T}, Sacrifice this artifact: It deals 3 damage to target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Scrounging Skyray | handled | Whenever you discard one or more cards, put that many +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Skybox Ferry | handled | Flying | machines/combat.py | Y/Y/Y | not_tested |
| Skycrash | handled | Destroy target artifact. Cycling {R} ({R}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Skystreak Engineer | handled | Exhaust — {4}{U}: Put two +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Spectral Interference | handled | Counter target artifact or creature spell unless its controller pays {4}. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Spin Out | handled | Destroy target creature or Vehicle. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Spotcycle Scouter | handled | When this Vehicle enters, scry 2. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Stall Out | handled | Tap target creature or Vehicle, then put three stun counters on it. (If a permanent with a stun counter would become untapped, remove one from it instead.) Cycl | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Stampeding Scurryfoot | handled | Exhaust — {3}{G}: Put a +1/+1 counter on this creature. Create a 3/3 green Elephant creature token. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sunbillow Verge | handled |  |  | Y/Y/Y | not_tested |
| Sundial, Dawn Tyrant | handled |  |  | Y/Y/Y | not_tested |
| Syphon Fuel | handled | Target creature gets -6/-6 until end of turn. You gain 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Terrian, World Tyrant | handled |  |  | Y/Y/Y | not_tested |
| Thopter Fabricator | handled | Whenever you draw your second card each turn, create a 1/1 colorless Thopter artifact creature token with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Thunderhead Gunner | handled | Discard a card: Draw a card. Activate only as a sorcery and only once each turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Thundering Broodwagon | handled | When this Vehicle enters, destroy target nonland permanent an opponent controls with mana value 4 or less. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Trip Up | handled | Target nonland permanent's owner puts it on their choice of the top or bottom of their library. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Tyrox, Saurid Tyrant | handled |  |  | Y/Y/Y | not_tested |
| Unstoppable Plan | handled | At the beginning of your end step, untap all nonland permanents you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Veloheart Bike | handled | When this Vehicle enters, you gain 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Voyage Home | handled | Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.) You draw three cards and gain 3 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Voyager Quickwelder | handled | Artifact spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Wastewood Verge | handled |  |  | Y/Y/Y | not_tested |
| Webstrike Elite | handled | When you cycle this card, destroy up to one target artifact or enchantment with mana value X. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Willowrush Verge | handled |  |  | Y/Y/Y | not_tested |
| Wreck Remover | handled | Whenever this creature enters or attacks, exile up to one target card from a graveyard. You gain 1 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Wreckage Wickerfolk | handled | When this creature enters, surveil 2. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Wretched Doll | handled | {B}, {T}: Surveil 1. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>8 cards</summary>

- Boommobile
- Captain Howler, Sea Scourge
- Greenbelt Guardian
- Ketramose, the New Dawn
- Marauding Mako
- Radiant Lotus
- Stock Up
- Ticket Tortoise

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Max speed | Amonkhet Raceway, Avishkar Raceway, Embalmed Ascendant, Endrider Catalyzer, Endrider Spikespitter, Far Fortune, End Boss, Gas Guzzler, Hour of Victory, Muraganda Raceway, Perilous Snare, Pride of the Road, Racers' Scoreboard, Risen Necroregent, Slick Imitator, Starting Column, Vnwxt, Verbose Host, Zahur, Glory's Past | 17 |
| Saddle | Alacrian Jaguar, Autarch Mammoth, Brightfield Glider, Bulwark Ox, District Mascot, Dracosaur Auxiliary, Gilded Ghoda, Gloryheath Lynx, Guardian Sunmare, Lagorin, Soul of Alacria, Venomsac Lagac | 11 |
| Start your engines! | Glitch Ghost Surveyor, Goblin Surveyor, Hazoret, Godseeker, Leonin Surveyor, Loxodon Surveyor, Mutant Surveyor, Samut, the Driving Force | 7 |
| This land enters tapped unless you control a Mount or Vehicle. | Country Roads, Foul Roads, Reef Roads, Rocky Roads, Wild Roads | 5 |
| Max speed — This creature gets +0/+1 and has vigilance. | Gastal Raider, Nesting Bot, Swiftwing Assailant, Walking Sarcophagus | 4 |
| This creature saddles Mounts and crews Vehicles using its toughness rather than its power. | Cloudspire Captain, Deathless Pilot, Dynamite Diver, Interface Ace | 4 |
| When this creature enters, you may search your library and/or graveyard for a creature card with no abilities, reveal it, and put it into your hand. If you sear | Brightglass Gearhulk, Fang-Druid Summoner, Gastal Blockbuster, Transit Mage | 4 |
| Whenever you activate an exhaust ability, create a 1/1 colorless Thopter artifact creature token with flying. | Adrenaline Jockey, Afterburner Expert, Rangers' Aetherhive, Rangers' Refueler | 4 |
| At the beginning of combat on your turn, choose up to one target Mount or Vehicle you control. Until end of turn, that permanent becomes saddled if it's a Mount | Alacrian Armory, Chandra, Spark Hunter, Howlsquad Heavy | 3 |
| Max speed — This creature has deathtouch and haste. | Burnout Bashtronaut, Gastal Thrillseeker, Streaking Oilgorger | 3 |
| At the beginning of your end step, you draw X cards and lose X life, where X is your speed. | The Speed Demon, Veteran Beastrider | 2 |
| Enchanted permanent gets +1/+1 and has vigilance. | Lightwheel Enhancements, Roadside Assistance | 2 |
| Exhaust — {W}{U}{B}{R}{G}: This Vehicle becomes an artifact creature. Put two +1/+1 counters on it. | Marshals' Pathcruiser, Rocketeer Boostbuggy | 2 |
| When you cycle this card, create X 1/1 colorless Pilot creature tokens with "This token saddles Mounts and crews Vehicles as though its power were 2 greater." | Howler's Heavy, Valor's Flagship | 2 |
| Whenever this creature attacks while saddled, it gains indestructible until end of turn. Untap all creatures you control. | Brightfield Mustang, Unswerving Sloth | 2 |
| Whenever this creature saddles a Mount or crews a Vehicle during your main phase, that Mount or Vehicle gets +2/+0 and gains trample until end of turn. | Canyon Vaulter, Reckless Velocitaur | 2 |
| Whenever you discard one or more cards, create that many tapped 2/2 black Zombie creature tokens. | Cryptcaller Chariot, Magmakin Artillerist | 2 |
| Activated abilities of sources with the chosen name cost {2} more to activate. | Skyseer's Chariot | 1 |
| {T}: Add X mana of any one color, where X is Redshift's power. Spend this mana only to activate abilities. | Redshift, Rocketeer Chief | 1 |
| After this main phase, there are two additional combat phases. At the beginning of each combat this turn, untap all creatures that attacked this turn. | Full Throttle | 1 |
| All creatures and Vehicles lose indestructible until end of turn, then destroy all creatures and Vehicles. Cycling {2} ({2}, Discard this card: Draw a card.) | Spectacular Pileup | 1 |
| {1}, {T}: Any number of target players each mill two cards. | Riverchurn Monument | 1 |
| As an additional cost to cast this spell, sacrifice an artifact or creature. Destroy target creature or Vehicle. If the sacrificed permanent was a Vehicle, draw | Hellish Sideswipe | 1 |
| As Mimeoplasm enters, exile up to X creature cards from your graveyard. It enters with three +1/+1 counters on it for each creature card exiled this way. | Mimeoplasm, Revered One | 1 |
| +1: Attach The Aetherspark to up to one target creature you control. Put a +1/+1 counter on that creature. | The Aetherspark | 1 |
| Choose a card name. Search target opponent's graveyard, hand, and library for up to four cards with that name and exile them. Then that player shuffles. | Ancient Vendetta | 1 |
| Choose one — • Collision Course deals X damage to target creature, where X is the number of permanents you control that are creatures and/or Vehicles. • Destroy | Collision Course | 1 |
| Choose one — • Destroy target Vehicle. • Crash and Burn deals 6 damage to target creature or planeswalker. | Crash and Burn | 1 |
| Choose one — • Target permanent you control gains hexproof and indestructible until end of turn. • Create a 1/1 colorless Pilot creature token with "This token  | Defend the Rider | 1 |
| Choose target creature, planeswalker, or Vehicle. Mill two cards, then destroy the chosen permanent if its mana value is less than or equal to the number of car | Quag Feast | 1 |
| Choose target opponent. Create two 1/1 colorless Thopter artifact creature tokens with flying. Then the chosen player loses X life and you gain X life, where X  | Haunt the Network | 1 |
| {T}: Create X 1/1 colorless Pilot creature tokens, where X is the number of Mounts and/or Vehicles that entered the battlefield under your control this turn. Th | Cloudspire Coordinator | 1 |
| Creatures you control have base power and toughness 6/6 and are Oozes in addition to their other types. | March of the World Ooze | 1 |
| Draw two cards. Each player loses 2 life. | Risky Shortcut | 1 |
| During turns other than yours, this Vehicle is an artifact creature. | Midnight Mangler | 1 |
| During your turn, as long as you haven't activated an exhaust ability this turn, you may activate exhaust abilities as though they haven't been activated. | Elvish Refueler | 1 |
| Each creature that's attacking one of your opponents has trample. | Oviya, Automech Artisan | 1 |
| Each other Vehicle and creature you control enters with an additional +1/+1 counter on it if its mana value is 4 or less. Otherwise, it enters with three additi | Thunderous Velocipede | 1 |
| Exchange control of target artifact or creature you control and target artifact or creature an opponent controls. Cycling {2} ({2}, Discard this card: Draw a ca | Trade the Helm | 1 |
| Exhaust — {4}{R}{G}: Creatures and Vehicles you control gain trample until end of turn. Put two +1/+1 counters on this creature. | Boom Scholar | 1 |
| Exhaust — {X}{U}{U}, {T}: Draw X cards. Put a +1/+1 counter on each Merfolk creature you control. | Mindspring Merfolk | 1 |
| Exhaust — {2}{U}{B}, {T}, Exile X artifact cards from your graveyard: Each other nonartifact creature gets -X/-X until end of turn. | Winter, Cursed Rider | 1 |
| Exhaust — {X}{G}{G}{U}: Put X +1/+1 counters on Sita Varma. Then you may have the base power and toughness of each other creature you control become equal to Si | Sita Varma, Masked Racer | 1 |
| Exhaust — {4}: Reveal cards from the top of your library until you reveal two land cards. Put those land cards onto the battlefield tapped and the rest on the b | Skyserpent Seeker | 1 |
| Exhaust — Tap another untapped Mount or Vehicle you control: This Vehicle becomes an artifact creature. Put a +1/+1 counter on it for each Mount and/or Vehicle  | Spire Mechcycle | 1 |
| Exile an artifact or creature card from your graveyard: This Vehicle becomes an artifact creature until end of turn. | Earthrumbler | 1 |
| If one or more +1/+1 counters would be put on a creature or Vehicle you control, that many plus one +1/+1 counters are put on it instead. | Caradora, Heart of Alacria | 1 |
| Max speed — Sacrifice this enchantment: Creatures and Vehicles you control gain haste until end of turn. | Kickoff Celebrations | 1 |
| Max speed — Whenever you cast an artifact spell, you may pay {1}. If you do, copy it. | Mendicant Core, Guidelight | 1 |
| Max speed — Whenever you draw a card, each opponent mills two cards. | Aether Syphon | 1 |
| Mounts and Vehicles you control have haste. | Kolodin, Triumph Caster | 1 |
| Return all Mount and Vehicle cards from your graveyard to the battlefield. Sacrifice them at the beginning of the next end step. Vehicles you control become art | Push the Limit | 1 |
| Return target artifact card from your graveyard to the battlefield. If it's a Vehicle, it becomes an artifact creature. | Tune Up | 1 |
| Return target creature or Vehicle card from your graveyard to the battlefield. Create a 1/1 colorless Pilot creature token with "This token saddles Mounts and c | Back on Track | 1 |
| Return up to one target creature card, up to one target Mount card, up to one target Vehicle card, and up to one target creature card with no abilities from you | Rise from the Wreck | 1 |
| Road Rage deals X damage to target creature or planeswalker, where X is 2 plus the number of Mounts and Vehicles you control. | Road Rage | 1 |
| Sab-Sunen can't attack or block unless it has an even number of counters on it. | Sab-Sunen, Luxa Embodied | 1 |
| {U}, Sacrifice this creature: Counter target instant or sorcery spell unless its controller pays {3}. | Diversion Unit | 1 |
| {2}, Sacrifice this enchantment: It deals 2 damage to each player who doesn't have max speed. | Outpace Oblivion | 1 |
| {3}{G}, Sacrifice this enchantment: Search your library for up to X basic land cards, where X is your speed. Put those cards onto the battlefield tapped, then s | Point the Way | 1 |
| Tap three other untapped creatures you control: Until end of turn, this Vehicle becomes an artifact creature and gains flying. Put a +1/+1 counter on it. | Voyager Glidecar | 1 |
| {T}: Target creature card in your graveyard gains embalm until end of turn. The embalm cost is equal to its mana cost. | Cursecloth Wrappings | 1 |
| Target creature gets +X/+0 and gains first strike until end of turn. | Pedal to the Metal | 1 |
| {T}: Target creature you control with power 2 or less gains lifelink until end of turn and can't be blocked this turn. | Apocalypse Runner | 1 |
| {2}, {T}: Target Mount you control becomes saddled until end of turn. Activate only as a sorcery. | Guidelight Matrix | 1 |
| The Last Ride gets -X/-X, where X is your life total. | The Last Ride | 1 |
| This spell costs {1} less to cast for each artifact and/or creature card in your graveyard. | Chitin Gravestalker | 1 |
| This Vehicle's power is equal to the number of lands you control. | Lumbering Worldwagon | 1 |
| Vehicle creatures you control are the chosen creature type in addition to their other types. | Lifecraft Engine | 1 |
| When Aatchik enters, create a 1/1 green Insect creature token for each artifact and/or creature card in your graveyard. | Aatchik, Emerald Radian | 1 |
| When Mu Yanling enters, create a 3/2 colorless Vehicle artifact token with crew 1. | Mu Yanling, Wind Rider | 1 |
| When this Aura enters, untap enchanted permanent. | Silken Strength | 1 |
| When this creature enters, all other creatures get -2/-2 until end of turn. | Shefet Archfiend | 1 |
| When this creature enters, another target creature or Vehicle you control gets +2/+2 until end of turn. | Fang Guardian | 1 |
| When this creature enters, for each opponent, put up to one target nonland permanent that player controls into its owner's library third from the top. | Riptide Gearhulk | 1 |
| When this creature enters, look at target player's hand. You may choose a card from it. If you do, that player discards that card, then draws a card. | Oildeep Gearhulk | 1 |
| When this creature enters, mill two cards, then put a +1/+1 counter on this creature for each artifact and/or creature card in your graveyard. | Ooze Patrol | 1 |
| When this creature enters, put target creature card with mana value 4 or less from a graveyard onto the battlefield under your control with a finality counter o | Coalstoke Gearhulk | 1 |
| When this creature enters, return target creature or Vehicle an opponent controls to its owner's hand. If that opponent's speed is greater than each other playe | Spikeshell Harrier | 1 |
| When this creature enters, target creature or Vehicle gains lifelink and indestructible until end of turn. | Lotusguard Disciple | 1 |
| When this enchantment enters, each opponent sacrifices a creature or Vehicle of their choice. Each opponent who can't discards a card. | Momentum Breaker | 1 |
| When this Vehicle enters, exile target artifact or creature an opponent controls until this Vehicle leaves the battlefield. | Detention Chariot | 1 |
| When this Vehicle enters, for each player, destroy up to one target creature that player controls. If a creature you controlled was destroyed this way, put two  | Demonic Junker | 1 |
| When this Vehicle enters, gain control of target creature an opponent controls for as long as you control this Vehicle. That creature can't attack or block for  | Possession Engine | 1 |
| When this Vehicle enters, it becomes an artifact creature until end of turn. | Gastal Thrillroller | 1 |
| When this Vehicle enters, mill two cards. Then return a creature or Vehicle card from your graveyard to your hand. | Carrion Cruiser | 1 |
| When this Vehicle enters, you may search your library for an artifact card and reveal it. Put it onto the battlefield if its mana value is 2 or less. Otherwise, | Guidelight Pathmaker | 1 |
| {2}, {T}: When you next activate an exhaust ability that isn't a mana ability this turn, copy it. You may choose new targets for the copy. | Pit Automaton | 1 |
| Whenever a player casts a spell they don't own, that player creates a Treasure token. | Gonti, Night Minister | 1 |
| Whenever Daretti enters or attacks, choose target artifact card in your graveyard. You may sacrifice an artifact. If you do, return the chosen card to the battl | Daretti, Rocketeer Engineer | 1 |
| Whenever one or more artifact and/or creature cards leave your graveyard, you gain 1 life. | Dredger's Insight | 1 |
| Whenever you attack, target attacking creature gets +1/+0 until end of turn. When that creature dies this turn, surveil 1. | Grim Javelineer | 1 |
| You may cast this card from your graveyard by paying 2 life and sacrificing an artifact or creature in addition to paying its other costs. | Wickerfolk Indomitable | 1 |
| You may have this creature enter as a copy of an artifact or creature you control. | Waxen Shapethief | 1 |

## Notes



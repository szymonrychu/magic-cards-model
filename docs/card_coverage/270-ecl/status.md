# Lorwyn Eclipsed (ecl)

- Expansion: 270
- Set code: `ecl`
- Release date: 2026-01-23
- Cards in scope (Modern/Pioneer/Standard-legal): 252

## Legality

| Format | Legal cards |
|---|---|
| Modern | 252 |
| Pioneer | 252 |
| Standard | 252 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 138 | 54.8% |
| Works (untested) | 113 | 44.8% |
| Partial (unaudited) | 1 | 0.4% |
| Not working | 0 | 0.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Wildvine Pummeler | unaudited | Vivid — This spell costs {1} less to cast for each color among permanents you control. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Aquitect's Defenses | handled | When this Aura enters, enchanted creature gains hexproof until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Assert Perfection | handled | Target creature you control gets +1/+0 until end of turn. It deals damage equal to its power to up to one target creature an opponent controls. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Barbed Bloodletter | handled | When this Equipment enters, attach it to target creature you control. That creature gains wither until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bile-Vial Boggart | handled | When this creature dies, put a -1/-1 counter on up to one target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bitterbloom Bearer | handled | At the beginning of your upkeep, you lose 1 life and create a 1/1 blue and black Faerie creature token with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Blight Rot | handled | Put four -1/-1 counters on target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bogslither's Embrace | handled | As an additional cost to cast this spell, blight 1 or pay {3}. (To blight 1, put a -1/-1 counter on a creature you control.) Exile target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Boneclub Berserker | handled | This creature gets +2/+0 for each other Goblin you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Brambleback Brute | handled | This creature enters with two -1/-1 counters on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Brigid's Command | handled | Choose two — • Create a token that's a copy of target Kithkin you control. • Target player creates a 1/1 green and white Kithkin creature token. • Target creatu | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Burdened Stoneback | handled | This creature enters with two -1/-1 counters on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Catharsis | handled | When this creature enters, if {W}{W} was spent to cast it, create two 1/1 green and white Kithkin creature tokens. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Chitinous Graspling | handled | Reach | machines/combat.py | Y/Y/Y | not_tested |
| Chomping Changeling | handled | When this creature enters, destroy up to one target artifact or enchantment. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Clachan Festival | handled | When this enchantment enters, create two 1/1 green and white Kithkin creature tokens. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Crossroads Watcher | handled | Whenever another creature you control enters, this creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dawn's Light Archer | handled | Reach | machines/combat.py | Y/Y/Y | not_tested |
| Dawnhand Eulogist | handled | When this creature enters, mill three cards. Then if there is an Elf card in your graveyard, each opponent loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Deepchannel Duelist | handled | At the beginning of your end step, untap target Merfolk you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Disruptor of Currents | handled | When this creature enters, return up to one other target nonland permanent to its owner's hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dundoolin Weaver | handled | When this creature enters, if you control three or more creatures, return target permanent card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Eclipsed Elf | handled | When this creature enters, look at the top four cards of your library. You may reveal an Elf, Swamp, or Forest card from among them and put it into your hand. P | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Eclipsed Flamekin | handled | When this creature enters, look at the top four cards of your library. You may reveal an Elemental, Island, or Mountain card from among them and put it into you | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Eclipsed Kithkin | handled | When this creature enters, look at the top four cards of your library. You may reveal a Kithkin, Forest, or Plains card from among them and put it into your han | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Eclipsed Merrow | handled | When this creature enters, look at the top four cards of your library. You may reveal a Merfolk, Plains, or Island card from among them and put it into your han | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Elder Auntie | handled | When this creature enters, create a 1/1 black and red Goblin creature token. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Emptiness | handled | When this creature enters, if {W}{W} was spent to cast it, return target creature card with mana value 3 or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Enraged Flamecaster | handled | Whenever you cast a spell with mana value 4 or greater, this creature deals 2 damage to each opponent. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Evershrike's Gift | handled | Enchanted creature gets +1/+0 and has flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Feed the Flames | handled | Feed the Flames deals 5 damage to target creature. If that creature would die this turn, exile it instead. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Feisty Spikeling | handled | During your turn, this creature has first strike. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Firdoch Core | handled | {4}: This artifact becomes a 4/4 artifact creature until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Flame-Chain Mauler | handled | {1}{R}: This creature gets +1/+0 and gains menace until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Flamebraider | handled |  |  | Y/Y/Y | not_tested |
| Flamekin Gildweaver | handled | When this creature enters, create a Treasure token. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Flaring Cinder | handled | When this creature enters and whenever you cast a spell with mana value 4 or greater, you may discard a card. If you do, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Flitterwing Nuisance | handled | This creature enters with a -1/-1 counter on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Flock Impostor | handled | When this creature enters, return up to one other target creature you control to its owner's hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Foraging Wickermaw | handled | When this creature enters, surveil 1. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Gallant Fowlknight | handled | When this creature enters, creatures you control get +1/+0 until end of turn. Kithkin creatures you control also gain first strike until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Gangly Stompling | handled | Trample | machines/combat.py | Y/Y/Y | not_tested |
| Giantfall | handled | Choose one — • Target creature you control deals damage equal to its power to target creature an opponent controls. • Destroy target artifact. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Gilt-Leaf's Embrace | handled | When this Aura enters, enchanted creature gains trample and indestructible until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Glamermite | handled | When this creature enters, choose one — • Tap target creature. • Untap target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Gnarlbark Elm | handled | This creature enters with two -1/-1 counters on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Goldmeadow Nomad | handled | {W}, Exile this card from your graveyard: Create a 1/1 green and white Kithkin creature token. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Gravelgill Scoundrel | handled | Whenever this creature attacks, you may tap another untapped creature you control. If you do, this creature can't be blocked this turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Great Forest Druid | handled |  |  | Y/Y/Y | not_tested |
| Gristle Glutton | handled | {T}, Blight 1: Discard a card. If you do, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Hovel Hurler | handled | This creature enters with two -1/-1 counters on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Impolite Entrance | handled | Target creature gains trample and haste until end of turn. Draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Iron-Shield Elf | handled | Discard a card: This creature gains indestructible until end of turn. Tap it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Keep Out | handled | Choose one — • Keep Out deals 4 damage to target tapped creature. • Destroy target enchantment. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Kirol, Attentive First-Year | handled | Tap two untapped creatures you control: Copy target triggered ability you control. You may choose new targets for the copy. Activate only once each turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Kulrath Mystic | handled | Whenever you cast a spell with mana value 4 or greater, this creature gets +2/+0 and gains vigilance until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Kulrath Zealot | handled | When this creature enters, exile the top card of your library. Until the end of your next turn, you may play that card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Liminal Hold | handled | When this enchantment enters, exile up to one target nonland permanent an opponent controls until this enchantment leaves the battlefield. You gain 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Loch Mare | handled | This creature enters with three -1/-1 counters on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Lofty Dreams | handled | When this Aura enters, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Lys Alana Informant | handled | When this creature enters or dies, surveil 1. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Merrow Skyswimmer | handled | When this creature enters, create a 1/1 white and blue Merfolk creature token. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Mischievous Sneakling | handled | Flash | machines/casting.py (timing) | Y/Y/Y | not_tested |
| Mistmeadow Council | handled | This spell costs {1} less to cast if you control a Kithkin. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Moonglove Extractor | handled | Whenever this creature attacks, you draw a card and lose 1 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Moonlit Lamenter | handled | This creature enters with a -1/-1 counter on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Morcant's Eyes | handled | At the beginning of your upkeep, surveil 1. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Morcant's Loyalist | handled | Other Elves you control get +1/+1. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Mudbutton Cursetosser | handled | As an additional cost to cast this spell, behold a Goblin or pay {2}. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Nightmare Sower | handled | Whenever you cast a spell during an opponent's turn, put a -1/-1 counter on up to one target creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Noggle Robber | handled | When this creature enters or dies, create a Treasure token. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Personify | handled | Exile target creature you control, then return that card to the battlefield under its owner's control. Create a 1/1 colorless Shapeshifter creature token with c | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pestered Wellguard | handled | Whenever this creature becomes tapped, create a 1/1 blue and black Faerie creature token with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Prideful Feastling | handled | Lifelink | machines/combat.py | Y/Y/Y | not_tested |
| Protective Response | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Destroy tar | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pyrrhic Strike | handled | As an additional cost to cast this spell, you may blight 2. (You may put two -1/-1 counters on a creature you control.) Choose one. If this spell's additional c | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Reaping Willow | handled | This creature enters with two -1/-1 counters on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Reckless Ransacking | handled | Target creature gets +3/+2 until end of turn. Create a Treasure token. (It's an artifact with "{T}, Sacrifice this token: Add one mana of any color.") | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Rimekin Recluse | handled | When this creature enters, return up to one other target creature to its owner's hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Riverguard's Reflexes | handled | Target creature gets +2/+2 and gains first strike until end of turn. Untap it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Rooftop Percher | handled | When this creature enters, exile up to two target cards from graveyards. You gain 3 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sapling Nursery | handled | Landfall — Whenever a land you control enters, create a 3/4 green Treefolk creature token with reach. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Scarblade Scout | handled | When this creature enters, mill two cards. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sear | handled | Sear deals 4 damage to target creature or planeswalker. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Shore Lurker | handled | When this creature enters, surveil 1. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Silvergill Mentor | handled | As an additional cost to cast this spell, behold a Merfolk or pay {2}. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Silvergill Peddler | handled | Whenever this creature becomes tapped, draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sizzling Changeling | handled | When this creature dies, exile the top card of your library. Until the end of your next turn, you may play that card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Spiral into Solitude | handled | Enchanted creature can't attack or block. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Stoic Grove-Guide | handled | {1}{B/G}, Exile this card from your graveyard: Create a 2/2 black and green Elf creature token. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Stratosoarer | handled | When this creature enters, target creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Summit Sentinel | handled | When this creature dies, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sun-Dappled Celebrant | handled | Vigilance | machines/combat.py | Y/Y/Y | not_tested |
| Surly Farrier | handled | {T}: Target creature you control gets +1/+1 and gains vigilance until end of turn. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Swat Away | handled | This spell costs {2} less to cast if a creature is attacking you. The owner of target spell or creature puts it on their choice of the top or bottom of their li | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Tanufel Rimespeaker | handled | Whenever you cast a spell with mana value 4 or greater, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Tend the Sprigs | handled | Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control seven or more lands and/or Treefolk, create a 3 | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Thirst for Identity | handled | Draw three cards. Then discard two cards unless you discard a creature card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Thoughtweft Charge | handled | Target creature gets +3/+3 until end of turn. If a creature entered the battlefield under your control this turn, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Thoughtweft Lieutenant | handled | Whenever this creature or another Kithkin you control enters, target creature you control gets +1/+1 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Timid Shieldbearer | handled | {4}{W}: Creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Trystan's Command | handled | Choose two — • Create a token that's a copy of target Elf you control. • Return one or two target permanent cards from your graveyard to your hand. • Destroy ta | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Tweeze | handled | Tweeze deals 3 damage to any target. You may discard a card. If you do, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Twinflame Travelers | handled | If a triggered ability of another Elemental you control triggers, it triggers an additional time. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Unbury | handled | Choose one — • Return target creature card from your graveyard to your hand. • Return two target creature cards that share a creature type from your graveyard t | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Unexpected Assistance | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Draw three  | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Unforgiving Aim | handled | Choose one — • Destroy target creature with flying. • Destroy target enchantment. • Create a 2/2 black and green Elf creature token. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Unwelcome Sprite | handled | Whenever you cast a spell during an opponent's turn, surveil 2. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Vibrance | handled | When this creature enters, if {R}{R} was spent to cast it, this creature deals 3 damage to any target. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Virulent Emissary | handled | Whenever another creature you control enters, you gain 1 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Wanderbrine Preacher | handled | Whenever this creature becomes tapped, you gain 2 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Wanderbrine Trapper | handled | {1}, {T}, Tap another untapped creature you control: Tap target creature an opponent controls. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Wanderwine Distracter | handled | Whenever this creature becomes tapped, target creature an opponent controls gets -3/-0 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Wary Farmer | handled | At the beginning of your end step, if another creature entered the battlefield under your control this turn, surveil 1. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>138 cards</summary>

- Abigale, Eloquent First-Year
- Adept Watershaper
- Ajani, Outland Chaperone
- Appeal to Eirdu
- Ashling's Command
- Ashling, Rekindled // Ashling, Rimebound
- Auntie's Sentence
- Aurora Awakener
- Bark of Doran
- Blighted Blackthorn
- Bloodline Bidding
- Blossombind
- Boggart Cursecrafter
- Boggart Mischief
- Boggart Prankster
- Boldwyr Aggressor
- Boulder Dash
- Bre of Clan Stoutarm
- Brigid, Clachan's Heart // Brigid, Doun's Mind
- Bristlebane Battler
- Bristlebane Outrider
- Burning Curiosity
- Celestial Reunion
- Champion of the Clachan
- Champion of the Path
- Champion of the Weird
- Champions of the Perfect
- Champions of the Shoal
- Changeling Wayfinder
- Chaos Spewer
- Chronicle of Victory
- Cinder Strike
- Collective Inferno
- Creakwood Safewright
- Curious Colossus
- Darkness Descends
- Dawn-Blessed Pennant
- Dawnhand Dissident
- Deceit
- Deepway Navigator
- Doran, Besieged by Time
- Dose of Dawnglow
- Dream Harvest
- Dream Seizer
- Eclipsed Boggart
- Eclipsed Realms
- Eirdu, Carrier of Dawn // Isilu, Carrier of Twilight
- Encumbered Reejerey
- End-Blaze Epiphany
- Explosive Prodigy
- Figure of Fable
- Formidable Speaker
- Gathering Stone
- Glamer Gifter
- Glen Elendra Guardian
- Glen Elendra's Answer
- Glister Bairn
- Gloom Ripper
- Goliath Daydreamer
- Grub's Command
- Grub, Storied Matriarch // Grub, Notorious Auntie
- Gutsplitter Gang
- Harmonized Crescendo
- Heirloom Auntie
- Hexing Squelcher
- High Perfect Morcant
- Illusion Spinners
- Kinbinding
- Kindle the Inner Flame
- Kinsbaile Aspirant
- Kinscaer Sentry
- Kithkeeper
- Lasting Tarfire
- Lavaleaper
- Lluwen, Imperfect Naturalist
- Luminollusk
- Lys Alana Dignitary
- Maralen, Fae Ascendant
- Meanders Guide
- Meek Attack
- Midnight Tilling
- Mirrorform
- Mirrormind Crown
- Moon-Vigil Adherents
- Moonshadow
- Morningtide's Light
- Mornsong Aria
- Mutable Explorer
- Noggle the Mind
- Oko, Lorwyn Liege // Oko, Shadowmoor Scion
- Omni-Changeling
- Perfect Intimidation
- Pitiless Fists
- Prismabasher
- Prismatic Undercurrents
- Puca's Eye
- Pummeler for Hire
- Raiding Schemes
- Reluctant Dounguard
- Requiting Hex
- Retched Wretch
- Rhys, the Evermore
- Rime Chill
- Rimefire Torque
- Safewright Cavalry
- Sanar, Innovative First-Year
- Scarblade's Malice
- Scuzzback Scrounger
- Selfless Safewright
- Shadow Urchin
- Shimmercreep
- Shimmerwilds Growth
- Shinestriker
- Slumbering Walker
- Soul Immolation
- Soulbright Seeker
- Sourbread Auntie
- Spinerock Tyrant
- Spry and Mighty
- Squawkroaster
- Stalactite Dagger
- Sting-Slinger
- Sunderflock
- Sygg's Command
- Sygg, Wanderwine Wisdom // Sygg, Wanderbrine Shield
- Tam, Mindful First-Year
- Taster of Wares
- Thoughtweft Imbuer
- Tributary Vaulter
- Trystan, Callous Cultivator // Trystan, Penitent Culler
- Twilight Diviner
- Vinebred Brawler
- Voracious Tome-Skimmer
- Wanderwine Farewell
- Warren Torchmaster
- Wild Unraveling
- Winnowing
- Wistfulness

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Vivid | 1 | Wildvine Pummeler | ecl |

## Notes

- 2026-09-27: round landed; Eirdu // Isilu, Sunderflock and Wildvine Pummeler sit in "partial" only because the sweep does not audit their static lines - each is proven by a scenario test (test_persist_grants.py, test_vivid_cost_and_cda.py).

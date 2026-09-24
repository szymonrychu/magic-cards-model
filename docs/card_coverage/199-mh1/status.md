# Modern Horizons (mh1)

- Expansion: 199
- Set code: `mh1`
- Release date: 2019-06-14
- Cards in scope (Modern/Pioneer/Standard-legal): 209

## Legality

| Format | Legal cards |
|---|---|
| Modern | 209 |
| Pioneer | 7 |
| Standard | 6 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 21 | 10.0% |
| Partial (unaudited) | 17 | 8.1% |
| Not tested (handled, untested) | 89 | 42.6% |
| Not working (silent / notice / error) | 82 | 39.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Abominable Treefolk | silent | Abominable Treefolk's power and toughness are each equal to the number of snow permanents you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Alpine Guide | silent | When this creature leaves the battlefield, sacrifice a Mountain. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Amorphous Axe | silent | Equipped creature gets +3/+0 and is every creature type. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Answered Prayers | silent | Whenever a creature you control enters, you gain 1 life. If this enchantment isn't a creature, it becomes a 3/3 Angel creature with flying in addition to its ot | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Aria of Flame | silent | When this enchantment enters, each opponent gains 10 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Astral Drift | silent | Whenever you cycle this card or cycle another card while this enchantment is on the battlefield, you may exile target creature. If you do, return that card to t | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Bellowing Elk | silent | As long as you had another creature enter the battlefield under your control this turn, this creature has trample and indestructible. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bogardan Dragonheart | silent | Sacrifice another creature: Until end of turn, this creature becomes a Dragon with base power and toughness 4/4, flying, and haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cleaving Sliver | silent | Sliver creatures you control get +2/+0. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cloudshredder Sliver | silent | Sliver creatures you control have flying and haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Collected Conjuring | silent | Exile the top six cards of your library. You may cast up to two sorcery spells with mana value 3 or less from among them without paying their mana costs. Put th | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Conifer Wurm | silent | {3}{G}: This creature gets +X/+X until end of turn, where X is the number of snow permanents you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cunning Evasion | silent | Whenever a creature you control becomes blocked, you may return it to its owner's hand. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Dead of Winter | silent | All nonsnow creatures get -X/-X until end of turn, where X is the number of snow permanents you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Deep Forest Hermit | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Excavating Anurid | silent | Threshold — As long as there are seven or more cards in your graveyard, this creature gets +1/+1 and has vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Face of Divinity | silent | As long as another Aura is attached to enchanted creature, it has first strike and lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Feaster of Fools | silent | Devour | no machine in the engine executes this keyword | Y/-/- | not_working |
| Force of Despair | silent | If it's not your turn, you may exile a black card from your hand rather than pay this spell's mana cost. Destroy all creatures that entered this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Frostwalk Bastion | silent | Whenever this land deals combat damage to a creature, tap that creature and it doesn't untap during its controller's next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Giver of Runes | silent | {T}: Another target creature you control gains protection from colorless or from the color of your choice until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gluttonous Slug | silent | Evolve | no machine in the engine executes this keyword | Y/-/- | not_working |
| Goblin Champion | silent | Exalted | no machine in the engine executes this keyword | Y/-/- | not_working |
| Goblin Oriflamme | silent | Attacking creatures you control get +1/+0. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Hall of Heliod's Generosity | silent | {1}{W}, {T}: Put target enchantment card from your graveyard on top of your library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Headless Specter | silent | Hellbent — Whenever this creature deals combat damage to a player, if you have no cards in hand, that player discards a card at random. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hexdrinker | silent | Level up {1} ({1}: Put a level counter on this. Level up only as a sorcery.) LEVEL 3-7 4/4 Protection from instants LEVEL 8+ 6/6 Protection from everything | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Iceberg Cancrix | silent | Whenever another snow permanent you control enters, you may have target player mill two cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Igneous Elemental | silent | This spell costs {2} less to cast if there is a land card in your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lancer Sliver | silent | Sliver creatures you control have first strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Marit Lage's Slumber | silent | At the beginning of your upkeep, if you control ten or more snow permanents, sacrifice Marit Lage's Slumber. If you do, create Marit Lage, a legendary 20/20 bla | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mind Rake | silent | Overload | no machine in the engine executes this keyword | Y/-/- | not_working |
| Morophon, the Boundless | silent | Other creatures you control of the chosen type get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| On Thin Ice | silent | When this Aura enters, exile target creature an opponent controls until this Aura leaves the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Orcish Hellraiser | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Phantasmal Form | silent | Until end of turn, up to two target creatures each have base power and toughness 3/3, gain flying, and become blue Illusions in addition to their other colors a | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Plague Engineer | silent | Creatures of the chosen type your opponents control get -1/-1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pyrophobia | silent | Pyrophobia deals 3 damage to target creature. Cowards can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Quakefoot Cyclops | silent | When this creature enters, up to two target creatures can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rank Officer | silent | When this creature enters, you may discard a card. If you do, create a 2/2 black Zombie creature token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reap the Past | silent | Return X cards at random from your graveyard to your hand. Exile Reap the Past. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Recruit the Worthy | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Rotwidow Pack | silent | {3}{B}{G}, Exile a creature card from your graveyard: Create a 1/2 green Spider creature token with reach, then each opponent loses 1 life for each Spider you c | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scale Up | silent | Until end of turn, target creature you control becomes a green Wurm with base power and toughness 6/4. Overload {4}{G}{G} (You may cast this spell for its overl | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scrapyard Recombiner | silent | Modular | no machine in the engine executes this keyword | Y/-/- | not_working |
| Silumgar Scavenger | silent | Exploit | no machine in the engine executes this keyword | Y/-/- | not_working |
| Smoke Shroud | silent | When a Ninja you control enters, you may return this card from your graveyard to the battlefield attached to that creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Soulherder | silent | Whenever a creature is exiled from the battlefield, put a +1/+1 counter on this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Spell Snuff | silent | Counter target spell. Fateful hour — If you have 5 or less life, draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spinehorn Minotaur | silent | As long as you've drawn two or more cards this turn, this creature has double strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stirring Address | silent | Overload | no machine in the engine executes this keyword | Y/-/- | not_working |
| Stream of Thought | silent | Target player mills four cards. You shuffle up to four cards from your graveyard into your library. Replicate {2}{U}{U} (When you cast this spell, copy it for e | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| String of Disappearances | silent | Return target creature to its owner's hand. Then that creature's controller may pay {U}{U}. If the player does, they may copy this spell and may choose a new ta | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sword of Sinew and Steel | silent | Whenever equipped creature deals combat damage to a player, destroy up to one target planeswalker and up to one target artifact. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sword of Truth and Justice | silent | Whenever equipped creature deals combat damage to a player, put a +1/+1 counter on a creature you control, then proliferate. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Throatseeker | silent | Unblocked attacking Ninjas you control have lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Throes of Chaos | silent | Retrace | no machine in the engine executes this keyword | Y/-/- | not_working |
| Thundering Djinn | silent | Whenever this creature attacks, it deals damage to any target equal to the number of cards you've drawn this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Treefolk Umbra | silent | Enchanted creature gets +0/+2 and assigns combat damage equal to its toughness rather than its power. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Trustworthy Scout | silent | {1}{W}, Exile this card from your graveyard: Search your library for a card named Trustworthy Scout, reveal it, put it into your hand, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Unbound Flourishing | silent | Whenever you cast a permanent spell with a mana cost that contains {X}, double the value of X. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wall of One Thousand Cuts | silent | {W}: This creature can attack this turn as though it didn't have defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Winding Way | silent | Choose creature or land. Reveal the top four cards of your library. Put all cards of the chosen type revealed this way into your hand and the rest into your gra | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Winds of Abandon | silent | Exile target creature you don't control. For each creature exiled this way, its controller searches their library for a basic land card. Those players put those | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Archmage's Charm | notice | Choose one — • Counter target spell. • Target player draws two cards. • Gain control of target nonland permanent with mana value 1 or less. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Cabal Therapist | notice | At the beginning of your first main phase, you may sacrifice a creature. When you do, choose a nonland card name, then target player reveals their hand and disc | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Defile | notice | Target creature gets -1/-1 until end of turn for each Swamp you control. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Eyekite | notice | This creature gets +2/+0 as long as you've drawn two or more cards this turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Fallen Shinobi | notice | Whenever this creature deals combat damage to a player, that player exiles the top two cards of their library. Until end of turn, you may play those cards witho | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Fists of Flame | notice | Draw a card. Until end of turn, target creature gains trample and gets +1/+0 for each card you've drawn this turn. (A creature with trample can deal excess comb | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Force of Rage | notice | If it's not your turn, you may exile a red card from your hand rather than pay this spell's mana cost. Create two 3/1 red Elemental creature tokens with trample | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Goatnap | notice | Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. If that creature is a Goat, it also gets +3/+0 until e | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Ice-Fang Coatl | notice | This creature has deathtouch as long as you control at least three other snow permanents. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Kaya's Guile | notice | Choose two — • Each opponent sacrifices a creature of their choice. • Exile all opponents' graveyards. • Create a 1/1 white and black Spirit creature token with | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Murasa Behemoth | notice | This creature gets +3/+3 as long as there is a land card in your graveyard. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Saddled Rimestag | notice | This creature gets +2/+2 as long as you had another creature enter the battlefield under your control this turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Savage Swipe | notice | Target creature you control gets +2/+2 until end of turn if its power is 2. Then it fights target creature you don't control. (Each deals damage equal to its po | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Shatter Assumptions | notice | Choose one — • Target opponent reveals their hand and discards all colorless nonland cards. • Target opponent reveals their hand and discards all multicolored c | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Tribute Mage | notice | When this creature enters, you may search your library for an artifact card with mana value 2, reveal that card, put it into your hand, then shuffle. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Twisted Reflection | notice | Choose one — • Target creature gets -6/-0 until end of turn. • Switch target creature's power and toughness until end of turn. Entwine {B} (Choose both if you p | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Urza, Lord High Artificer | notice | {5}: Shuffle your library, then exile the top card. Until end of turn, you may play that card without paying its mana cost. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Volatile Claws | notice | Until end of turn, creatures you control get +2/+0 and gain all creature types. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Bladeback Sliver | unaudited | Hellbent — As long as you have no cards in hand, Sliver creatures you control have "{T}: This creature deals 1 damage to target player or planeswalker." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Dregscape Sliver | unaudited | Each Sliver creature card in your graveyard has unearth {2}. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Enduring Sliver | unaudited | Other Sliver creatures you control have outlast {2}. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| First Sliver's Chosen | unaudited | Sliver creatures you control have exalted. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Force of Virtue | unaudited | If it's not your turn, you may exile a white card from your hand rather than pay this spell's mana cost. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Hogaak, Arisen Necropolis | unaudited | You can't spend mana to cast this spell. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Hollowhead Sliver | unaudited | Sliver creatures you control have "{T}, Discard a card: Draw a card." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Lavabelly Sliver | unaudited | Sliver creatures you control have "When this creature enters, it deals 1 damage to target player or planeswalker and you gain 1 life." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Mirrodin Besieged | unaudited | As this enchantment enters, choose Mirran or Phyrexian. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Reprobation | unaudited | Enchanted creature loses all abilities and is a Coward creature with base power and toughness 0/1. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Scuttling Sliver | unaudited | Sliver creatures you control have "{2}: Untap this creature." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Spiteful Sliver | unaudited | Sliver creatures you control have "Whenever this creature is dealt damage, it deals that much damage to target player or planeswalker." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Tectonic Reformation | unaudited | Each land card in your hand has cycling {R}. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Tempered Sliver | unaudited | Sliver creatures you control have "Whenever this creature deals combat damage to a player, put a +1/+1 counter on it." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| The First Sliver | unaudited | Sliver spells you cast have cascade. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Valiant Changeling | unaudited | This spell costs {1} less to cast for each creature type among creatures you control. This effect can't reduce the amount of mana this spell costs by more than  | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Winter's Rest | unaudited | As long as you control another snow permanent, enchanted creature doesn't untap during its controller's untap step. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Arcum's Astrolabe | handled | When this artifact enters, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ayula's Influence | handled | Discard a land card: Create a 2/2 green Bear creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ayula, Queen Among Bears | handled | Whenever another Bear you control enters, choose one — • Put two +1/+1 counters on target Bear. • Target Bear you control fights target creature you don't contr | the engine reads this text and performs it | Y/-/- | not_tested |
| Azra Smokeshaper | handled | When this creature enters, target creature you control gains indestructible until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bazaar Trademage | handled | When this creature enters, draw two cards, then discard three cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Birthing Boughs | handled | {4}, {T}: Create a 2/2 colorless Shapeshifter creature token with changeling. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blizzard Strix | handled | When this creature enters, if you control another snow permanent, exile target permanent other than this creature. Return that card to the battlefield under its | the engine reads this text and performs it | Y/-/- | not_tested |
| Cave of Temptation | handled | {4}, {T}, Sacrifice this land: Put two +1/+1 counters on target creature. Activate only as a sorcery. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chillerpillar | handled | {4}{S}{S}: Monstrosity 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cordial Vampire | handled | Whenever this creature or another creature dies, put a +1/+1 counter on each Vampire you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crashing Footfalls | handled | Suspend 4—{G} (Rather than cast this card from your hand, pay {G} and exile it with four time counters on it. At the beginning of your upkeep, remove a time cou | the engine reads this text and performs it | Y/-/- | not_tested |
| Echo of Eons | handled | Each player shuffles their hand and graveyard into their library, then draws seven cards. Flashback {2}{U} (You may cast this card from your graveyard for its f | the engine reads this text and performs it | Y/-/- | not_tested |
| Endling | handled | {B}: This creature gains menace until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Etchings of the Chosen | handled | As this enchantment enters, choose a creature type. | the engine reads this text and performs it | Y/-/- | not_tested |
| Faerie Seer | handled | When this creature enters, scry 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Farmstead Gleaner | handled | This creature doesn't untap during your untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| First-Sphere Gargantua | handled | When this creature enters, you draw a card and you lose 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fountain of Ichor | handled | {3}: This artifact becomes a 3/3 Dinosaur artifact creature until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Frostwalla | handled | {S}: This creature gets +2/+2 until end of turn. Activate only once each turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Generous Gift | handled | Destroy target permanent. Its controller creates a 3/3 green Elephant creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Geomancer's Gambit | handled | Destroy target land. Its controller may search their library for a basic land card, put it onto the battlefield, then shuffle. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin War Party | handled | Choose one — • Create three 1/1 red Goblin creature tokens. • Creatures you control get +1/+1 and gain haste until end of turn. Entwine {2}{R} (Choose both if y | the engine reads this text and performs it | Y/-/- | not_tested |
| Good-Fortune Unicorn | handled | Whenever another creature you control enters, put a +1/+1 counter on that creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Graveshifter | handled | When this creature enters, you may return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Impostor of the Sixth Pride | handled | Changeling | machines/keywords.py | Y/-/- | not_tested |
| Ingenious Infiltrator | handled | Whenever a Ninja you control deals combat damage to a player, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Irregular Cohort | handled | When this creature enters, create a 2/2 colorless Shapeshifter creature token with changeling. | the engine reads this text and performs it | Y/-/- | not_tested |
| King of the Pride | handled | Other Cats you control get +2/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Knight of Old Benalia | handled | When this creature enters, other creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lesser Masticore | handled | As an additional cost to cast this spell, discard a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lightning Skelemental | handled | Whenever this creature deals combat damage to a player, that player discards two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Llanowar Tribe | handled |  |  | Y/-/- | not_tested |
| Magmatic Sinkhole | handled | Delve (Each card you exile from your graveyard while casting this spell pays for {1}.) Magmatic Sinkhole deals 5 damage to target creature or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Martyr's Soul | handled | When this creature enters, if you control no tapped lands, put two +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mist-Syndicate Naga | handled | Whenever this creature deals combat damage to a player, create a token that's a copy of this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mob | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Destroy tar | the engine reads this text and performs it | Y/-/- | not_tested |
| Moonblade Shinobi | handled | Whenever this creature deals combat damage to a player, create a 1/1 blue Illusion creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mother Bear | handled | {3}{G}{G}, Exile this card from your graveyard: Create two 2/2 green Bear creature tokens. Activate only as a sorcery. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mox Tantalite | handled | Suspend | machines/casting.py (MarkedExile.suspend, finish_suspend) | Y/-/- | not_tested |
| Munitions Expert | handled | When this creature enters, you may have it deal damage to target creature or planeswalker equal to the number of Goblins you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nature's Chant | handled | Destroy target artifact or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ninja of the New Moon | handled | Ninjutsu | machines/keywords.py | Y/-/- | not_tested |
| Oneirophage | handled | Whenever you draw a card, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ore-Scale Guardian | handled | This spell costs {1} less to cast for each land card in your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pashalik Mons | handled | Whenever Pashalik Mons or another Goblin you control dies, Pashalik Mons deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phantom Ninja | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Planebound Accomplice | handled | {R}: You may put a planeswalker card from your hand onto the battlefield. Sacrifice it at the beginning of the next end step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Prismatic Vista | handled | {T}, Pay 1 life, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Putrid Goblin | handled | Persist | machines/keywords.py | Y/-/- | not_tested |
| Rain of Revelation | handled | Draw three cards, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ransack the Lab | handled | Look at the top three cards of your library. Put one of them into your hand and the rest into your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ravenous Giant | handled | At the beginning of your upkeep, this creature deals 1 damage to you. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Return from Extinction | handled | Choose one — • Return target creature card from your graveyard to your hand. • Return two target creature cards that share a creature type from your graveyard t | the engine reads this text and performs it | Y/-/- | not_tested |
| Rhox Veteran | handled | Whenever this creature attacks, tap target creature an opponent controls. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rime Tender | handled | {T}: Untap another target snow permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ruination Rioter | handled | When this creature dies, you may have it deal damage to any target equal to the number of land cards in your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sadistic Obsession | handled | Enchanted creature has "{B}, {T}: Put a -1/-1 counter on target creature." | the engine reads this text and performs it | Y/-/- | not_tested |
| Scour All Possibilities | handled | Scry 2, then draw a card. Flashback {4}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Segovian Angel | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Serra the Benevolent | handled | +2: Creatures you control with flying get +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Settle Beyond Reality | handled | Choose one or both — • Exile target creature you don't control. • Exile target creature you control, then return it to the battlefield under its owner's control | the engine reads this text and performs it | Y/-/- | not_tested |
| Shenanigans | handled | Destroy target artifact. Dredge 1 (If you would draw a card, you may mill a card instead. If you do, return this card from your graveyard to your hand.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Sling-Gang Lieutenant | handled | When this creature enters, create two 1/1 red Goblin creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Smiting Helix | handled | Smiting Helix deals 3 damage to any target and you gain 3 life. Flashback {R}{W} (You may cast this card from your graveyard for its flashback cost. Then exile  | the engine reads this text and performs it | Y/-/- | not_tested |
| Soul-Strike Technique | handled | Enchanted creature gets +1/+1 and has vigilance. | the engine reads this text and performs it | Y/-/- | not_tested |
| Splicer's Skill | handled | Create a 3/3 colorless Phyrexian Golem artifact creature token. Splice onto instant or sorcery {3}{W} (As you cast an instant or sorcery spell, you may reveal t | the engine reads this text and performs it | Y/-/- | not_tested |
| Springbloom Druid | handled | When this creature enters, you may sacrifice a land. If you do, search your library for up to two basic land cards, put them onto the battlefield tapped, then s | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Talisman of Conviction | handled |  |  | Y/-/- | not_tested |
| Talisman of Creativity | handled |  |  | Y/-/- | not_tested |
| Talisman of Curiosity | handled |  |  | Y/-/- | not_tested |
| Talisman of Hierarchy | handled |  |  | Y/-/- | not_tested |
| Thornado | handled | Destroy target creature with flying. Cycling {1}{G} ({1}{G}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Treetop Ambusher | handled | Whenever this creature attacks, target creature you control gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trumpeting Herd | handled | Create a 3/3 green Elephant creature token. Rebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you m | the engine reads this text and performs it | Y/-/- | not_tested |
| Twin-Silk Spider | handled | When this creature enters, create a 1/2 green Spider creature token with reach. | the engine reads this text and performs it | Y/-/- | not_tested |
| Umezawa's Charm | handled | Choose one — • Target creature gets +2/+2 until end of turn. • Target creature gets -1/-1 until end of turn. • You gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Undead Augur | handled | Whenever this creature or another Zombie you control dies, you draw a card and lose 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Universal Automaton | handled | Changeling | machines/keywords.py | Y/-/- | not_tested |
| Unsettled Mariner | handled | Whenever you or a permanent you control becomes the target of a spell or ability an opponent controls, counter that spell or ability unless its controller pays  | the engine reads this text and performs it | Y/-/- | not_tested |
| Vengeful Devil | handled | Morbid — {T}: This creature deals 1 damage to any target. Activate only if a creature died this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Venomous Changeling | handled | Changeling | machines/keywords.py | Y/-/- | not_tested |
| Vesperlark | handled | When this creature leaves the battlefield, return target creature card with power 1 or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viashino Sandsprinter | handled | At the beginning of the end step, return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Warteye Witch | handled | Whenever this creature or another creature you control dies, scry 1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Waterlogged Grove | handled | {1}, {T}, Sacrifice this land: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Weather the Storm | handled | You gain 3 life. Storm (When you cast this spell, copy it for each spell cast before it this turn.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Webweaver Changeling | handled | When this creature enters, if there are three or more creature cards in your graveyard, you gain 5 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Yawgmoth, Thran Physician | handled | Pay 1 life, Sacrifice another creature: Put a -1/-1 counter on up to one target creature and draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zhalfirin Decoy | handled | {T}: Tap target creature. Activate only if you had a creature enter the battlefield under your control this turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>21 cards</summary>

- Changeling Outcast
- Collector Ouphe
- Ephemerate
- Everdream
- Fiery Islet
- Force of Negation
- Force of Vigor
- Glacial Revelation
- Goblin Engineer
- Icehide Golem
- Nurturing Peatland
- Pondering Mage
- Ranger-Captain of Eos
- Seasoned Pyromancer
- Silent Clearing
- Sisay, Weatherlight Captain
- Sunbaked Canyon
- Talisman of Resilience
- Watcher for Tomorrow
- Windcaller Aven
- Wrenn and Six

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Sliver creatures you control have "Whenever this creature is dealt damage, it deals that much damage to target player or planeswalker." | Cloudshredder Sliver, First Sliver's Chosen, Hollowhead Sliver, Lancer Sliver, Lavabelly Sliver, Scuttling Sliver, Spiteful Sliver, Tempered Sliver | 8 |
| If it's not your turn, you may exile a red card from your hand rather than pay this spell's mana cost. Create two 3/1 red Elemental creature tokens with trample | Force of Despair, Force of Rage, Force of Virtue | 3 |
| This creature gets +2/+2 as long as you had another creature enter the battlefield under your control this turn. | Eyekite, Murasa Behemoth, Saddled Rimestag | 3 |
| At the beginning of your upkeep, if you control ten or more snow permanents, sacrifice Marit Lage's Slumber. If you do, create Marit Lage, a legendary 20/20 bla | Cabal Therapist, Marit Lage's Slumber | 2 |
| Overload | Mind Rake, Stirring Address | 2 |
| This spell costs {1} less to cast for each creature type among creatures you control. This effect can't reduce the amount of mana this spell costs by more than  | Igneous Elemental, Valiant Changeling | 2 |
| When this creature enters, you may search your library for an artifact card with mana value 2, reveal that card, put it into your hand, then shuffle. | Rank Officer, Tribute Mage | 2 |
| Whenever a creature you control enters, you gain 1 life. If this enchantment isn't a creature, it becomes a 3/3 Angel creature with flying in addition to its ot | Answered Prayers, Cunning Evasion | 2 |
| Whenever equipped creature deals combat damage to a player, destroy up to one target planeswalker and up to one target artifact. | Sword of Sinew and Steel, Sword of Truth and Justice | 2 |
| Abominable Treefolk's power and toughness are each equal to the number of snow permanents you control. | Abominable Treefolk | 1 |
| All nonsnow creatures get -X/-X until end of turn, where X is the number of snow permanents you control. | Dead of Winter | 1 |
| {T}: Another target creature you control gains protection from colorless or from the color of your choice until end of turn. | Giver of Runes | 1 |
| As long as another Aura is attached to enchanted creature, it has first strike and lifelink. | Face of Divinity | 1 |
| As long as you control another snow permanent, enchanted creature doesn't untap during its controller's untap step. | Winter's Rest | 1 |
| As long as you had another creature enter the battlefield under your control this turn, this creature has trample and indestructible. | Bellowing Elk | 1 |
| As long as you've drawn two or more cards this turn, this creature has double strike. | Spinehorn Minotaur | 1 |
| As this enchantment enters, choose Mirran or Phyrexian. | Mirrodin Besieged | 1 |
| Attacking creatures you control get +1/+0. | Goblin Oriflamme | 1 |
| Buyback | Recruit the Worthy | 1 |
| Choose creature or land. Reveal the top four cards of your library. Put all cards of the chosen type revealed this way into your hand and the rest into your gra | Winding Way | 1 |
| Choose one — • Counter target spell. • Target player draws two cards. • Gain control of target nonland permanent with mana value 1 or less. | Archmage's Charm | 1 |
| Choose one — • Target creature gets -6/-0 until end of turn. • Switch target creature's power and toughness until end of turn. Entwine {B} (Choose both if you p | Twisted Reflection | 1 |
| Choose one — • Target opponent reveals their hand and discards all colorless nonland cards. • Target opponent reveals their hand and discards all multicolored c | Shatter Assumptions | 1 |
| Choose two — • Each opponent sacrifices a creature of their choice. • Exile all opponents' graveyards. • Create a 1/1 white and black Spirit creature token with | Kaya's Guile | 1 |
| Counter target spell. Fateful hour — If you have 5 or less life, draw a card. | Spell Snuff | 1 |
| Creatures of the chosen type your opponents control get -1/-1. | Plague Engineer | 1 |
| Devour | Feaster of Fools | 1 |
| Draw a card. Until end of turn, target creature gains trample and gets +1/+0 for each card you've drawn this turn. (A creature with trample can deal excess comb | Fists of Flame | 1 |
| Each land card in your hand has cycling {R}. | Tectonic Reformation | 1 |
| Each Sliver creature card in your graveyard has unearth {2}. | Dregscape Sliver | 1 |
| Echo | Orcish Hellraiser | 1 |
| Enchanted creature gets +0/+2 and assigns combat damage equal to its toughness rather than its power. | Treefolk Umbra | 1 |
| Enchanted creature loses all abilities and is a Coward creature with base power and toughness 0/1. | Reprobation | 1 |
| Equipped creature gets +3/+0 and is every creature type. | Amorphous Axe | 1 |
| Evolve | Gluttonous Slug | 1 |
| Exalted | Goblin Champion | 1 |
| {3}{B}{G}, Exile a creature card from your graveyard: Create a 1/2 green Spider creature token with reach, then each opponent loses 1 life for each Spider you c | Rotwidow Pack | 1 |
| Exile target creature you don't control. For each creature exiled this way, its controller searches their library for a basic land card. Those players put those | Winds of Abandon | 1 |
| Exile the top six cards of your library. You may cast up to two sorcery spells with mana value 3 or less from among them without paying their mana costs. Put th | Collected Conjuring | 1 |
| {1}{W}, Exile this card from your graveyard: Search your library for a card named Trustworthy Scout, reveal it, put it into your hand, then shuffle. | Trustworthy Scout | 1 |
| Exploit | Silumgar Scavenger | 1 |
| Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. If that creature is a Goat, it also gets +3/+0 until e | Goatnap | 1 |
| Hellbent — As long as you have no cards in hand, Sliver creatures you control have "{T}: This creature deals 1 damage to target player or planeswalker." | Bladeback Sliver | 1 |
| Hellbent — Whenever this creature deals combat damage to a player, if you have no cards in hand, that player discards a card at random. | Headless Specter | 1 |
| Level up {1} ({1}: Put a level counter on this. Level up only as a sorcery.) LEVEL 3-7 4/4 Protection from instants LEVEL 8+ 6/6 Protection from everything | Hexdrinker | 1 |
| Modular | Scrapyard Recombiner | 1 |
| Other creatures you control of the chosen type get +1/+1. | Morophon, the Boundless | 1 |
| Other Sliver creatures you control have outlast {2}. | Enduring Sliver | 1 |
| {1}{W}, {T}: Put target enchantment card from your graveyard on top of your library. | Hall of Heliod's Generosity | 1 |
| Pyrophobia deals 3 damage to target creature. Cowards can't block this turn. | Pyrophobia | 1 |
| Retrace | Throes of Chaos | 1 |
| Return target creature to its owner's hand. Then that creature's controller may pay {U}{U}. If the player does, they may copy this spell and may choose a new ta | String of Disappearances | 1 |
| Return X cards at random from your graveyard to your hand. Exile Reap the Past. | Reap the Past | 1 |
| Sacrifice another creature: Until end of turn, this creature becomes a Dragon with base power and toughness 4/4, flying, and haste. | Bogardan Dragonheart | 1 |
| {5}: Shuffle your library, then exile the top card. Until end of turn, you may play that card without paying its mana cost. | Urza, Lord High Artificer | 1 |
| Sliver creatures you control get +2/+0. | Cleaving Sliver | 1 |
| Sliver spells you cast have cascade. | The First Sliver | 1 |
| Target creature gets -1/-1 until end of turn for each Swamp you control. | Defile | 1 |
| Target creature you control gets +2/+2 until end of turn if its power is 2. Then it fights target creature you don't control. (Each deals damage equal to its po | Savage Swipe | 1 |
| Target player mills four cards. You shuffle up to four cards from your graveyard into your library. Replicate {2}{U}{U} (When you cast this spell, copy it for e | Stream of Thought | 1 |
| {W}: This creature can attack this turn as though it didn't have defender. | Wall of One Thousand Cuts | 1 |
| {3}{G}: This creature gets +X/+X until end of turn, where X is the number of snow permanents you control. | Conifer Wurm | 1 |
| This creature has deathtouch as long as you control at least three other snow permanents. | Ice-Fang Coatl | 1 |
| Threshold — As long as there are seven or more cards in your graveyard, this creature gets +1/+1 and has vigilance. | Excavating Anurid | 1 |
| Unblocked attacking Ninjas you control have lifelink. | Throatseeker | 1 |
| Until end of turn, creatures you control get +2/+0 and gain all creature types. | Volatile Claws | 1 |
| Until end of turn, target creature you control becomes a green Wurm with base power and toughness 6/4. Overload {4}{G}{G} (You may cast this spell for its overl | Scale Up | 1 |
| Until end of turn, up to two target creatures each have base power and toughness 3/3, gain flying, and become blue Illusions in addition to their other colors a | Phantasmal Form | 1 |
| Vanishing | Deep Forest Hermit | 1 |
| When a Ninja you control enters, you may return this card from your graveyard to the battlefield attached to that creature. | Smoke Shroud | 1 |
| When this Aura enters, exile target creature an opponent controls until this Aura leaves the battlefield. | On Thin Ice | 1 |
| When this creature enters, up to two target creatures can't block this turn. | Quakefoot Cyclops | 1 |
| When this creature leaves the battlefield, sacrifice a Mountain. | Alpine Guide | 1 |
| When this enchantment enters, each opponent gains 10 life. | Aria of Flame | 1 |
| Whenever a creature is exiled from the battlefield, put a +1/+1 counter on this creature. | Soulherder | 1 |
| Whenever another snow permanent you control enters, you may have target player mill two cards. | Iceberg Cancrix | 1 |
| Whenever this creature attacks, it deals damage to any target equal to the number of cards you've drawn this turn. | Thundering Djinn | 1 |
| Whenever this creature deals combat damage to a player, that player exiles the top two cards of their library. Until end of turn, you may play those cards witho | Fallen Shinobi | 1 |
| Whenever this land deals combat damage to a creature, tap that creature and it doesn't untap during its controller's next untap step. | Frostwalk Bastion | 1 |
| Whenever you cast a permanent spell with a mana cost that contains {X}, double the value of X. | Unbound Flourishing | 1 |
| Whenever you cycle this card or cycle another card while this enchantment is on the battlefield, you may exile target creature. If you do, return that card to t | Astral Drift | 1 |
| You can't spend mana to cast this spell. | Hogaak, Arisen Necropolis | 1 |

## Notes



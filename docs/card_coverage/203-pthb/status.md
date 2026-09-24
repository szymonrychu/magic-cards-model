# Theros Beyond Death Promos (pthb)

- Expansion: 203
- Set code: `pthb`
- Release date: 2020-01-24
- Cards in scope (Modern/Pioneer/Standard-legal): 62

## Legality

| Format | Legal cards |
|---|---|
| Modern | 62 |
| Pioneer | 62 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 10 | 16.1% |
| Partial (unaudited) | 9 | 14.5% |
| Not tested (handled, untested) | 13 | 21.0% |
| Not working (silent / notice / error) | 30 | 48.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Allure of the Unknown | silent | Reveal the top six cards of your library. An opponent exiles a nonland card from among them, then you put the rest into your hand. That opponent may cast the ex | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Aphemia, the Cacophony | silent | At the beginning of your end step, you may exile an enchantment card from your graveyard. If you do, create a 2/2 black Zombie creature token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Archon of Sun's Grace | silent | Pegasus creatures you control have lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ashiok, Nightmare Muse | silent | −3: Return target nonland permanent to its owner's hand, then that player exiles a card from their hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Atris, Oracle of Half-Truths | silent | When Atris enters, target opponent looks at the top three cards of your library and separates them into a face-down pile and a face-up pile. Put one pile into y | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Bronzehide Lion | silent | When this creature dies, return it to the battlefield. It's an Aura enchantment with enchant creature you control and "{G}{W}: Enchanted creature gains indestru | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Calix, Destiny's Hand | silent | +1: Look at the top four cards of your library. You may reveal an enchantment card from among them and put that card into your hand. Put the rest on the bottom  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dalakos, Crafter of Wonders | silent | Equipped creatures you control have flying and haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Elspeth Conquers Death | silent | II — Noncreature spells your opponents cast cost {2} more to cast until your next turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Elspeth, Sun's Nemesis | silent | −1: Up to two target creatures you control each get +2/+1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Erebos, Bleak-Hearted | silent | Whenever another creature you control dies, you may pay 2 life. If you do, draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gallia of the Endless Dance | silent | Other Satyrs you control get +1/+1 and have haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kiora Bests the Sea God | silent | II — Tap all nonland permanents target opponent controls. They don't untap during their controller's next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Labyrinth of Skophos | silent | {4}, {T}: Remove target attacking or blocking creature from combat. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nessian Boar | silent | Whenever this creature becomes blocked by a creature, that creature's controller draws a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nightmare Shepherd | silent | Whenever another nontoken creature you control dies, you may exile it. If you do, create a token that's a copy of that creature, except it's 1/1 and it's a Nigh | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Protean Thaumaturge | silent | Constellation — Whenever an enchantment you control enters, you may have this creature become a copy of another target creature, except it has this ability. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Shatter the Sky | silent | Each player who controls a creature with power 4 or greater draws a card. Then destroy all creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Storm Herald | silent | When this creature enters, return any number of Aura cards from your graveyard to the battlefield attached to creatures you control. Exile those Auras at the be | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Thassa's Oracle | silent | When this creature enters, look at the top X cards of your library, where X is your devotion to blue. Put up to one of them on top of your library and the rest  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| The Akroan War | silent | I — Gain control of target creature for as long as this Saga remains on the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| The First Iroan Games | silent | IV — Create a Gold token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tymaret Calls the Dead | silent | I, II — Mill three cards. Then you may exile a creature or enchantment card from your graveyard. If you do, create a 2/2 black Zombie creature token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Heliod's Intervention | notice | Choose one — • Destroy X target artifacts and/or enchantments. • Target player gains twice X life. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Nylea's Intervention | notice | Choose one — • Search your library for up to X land cards, reveal them, put them into your hand, then shuffle. • Nylea's Intervention deals twice X damage to ea | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Purphoros's Intervention | notice | Choose one — • Create an X/1 red Elemental creature token with trample and haste. Sacrifice it at the beginning of the next end step. • Purphoros's Intervention | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Purphoros, Bronze-Blooded | notice | {2}{R}: You may put a red creature card or an artifact creature card from your hand onto the battlefield. Sacrifice it at the beginning of the next end step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Taranika, Akroan Veteran | notice | Whenever Taranika attacks, untap another target creature you control. Until end of turn, that creature has base power and toughness 4/4 and gains indestructible | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Tectonic Giant | notice | Whenever this creature attacks or becomes the target of a spell an opponent controls, choose one — • This creature deals 3 damage to each opponent. • Exile the  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Thassa's Intervention | notice | Choose one — • Look at the top X cards of your library. Put up to two of them into your hand and the rest on the bottom of your library in a random order. • Cou | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Ashiok's Erasure | unaudited | Your opponents can't cast spells with the same name as the exiled card. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Eidolon of Obstruction | unaudited | Loyalty abilities of planeswalkers your opponents control cost {1} more to activate. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Haktos the Unscarred | unaudited | Haktos attacks each combat if able. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ox of Agonas | unaudited | This creature escapes with a +1/+1 counter on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Phoenix of Ash | unaudited | This creature escapes with a +1/+1 counter on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Polukranos, Unchained | unaudited | If damage would be dealt to Polukranos while it has a +1/+1 counter on it, prevent that damage and remove that many +1/+1 counters from it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Thryx, the Sudden Storm | unaudited | Spells you cast with mana value 5 or greater cost {1} less to cast and can't be countered. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Underworld Breach | unaudited | Each nonland card in your graveyard has escape. The escape cost is equal to the card's mana cost plus exile three other cards from your graveyard. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Woe Strider | unaudited | This creature escapes with two +1/+1 counters on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Arasta of the Endless Web | handled | Whenever an opponent casts an instant or sorcery spell, create a 1/2 green Spider creature token with reach. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dream Trawler | handled | Whenever you draw a card, this creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eat to Extinction | handled | Exile target creature or planeswalker. Surveil 1. (Look at the top card of your library. You may put that card into your graveyard.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Erebos's Intervention | handled | Choose one — • Target creature gets -X/-X until end of turn. You gain X life. • Exile up to twice X target cards from graveyards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gravebreaker Lamia | handled | When this creature enters, search your library for a card, put it into your graveyard, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Heliod, Sun-Crowned | handled | As long as your devotion to white is less than five, Heliod isn't a creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mantle of the Wolf | handled | Enchanted creature gets +4/+4. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nadir Kraken | handled | Whenever you draw a card, you may pay {1}. If you do, put a +1/+1 counter on this creature and create a 1/1 blue Tentacle creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nyx Lotus | handled | Nyx Lotus enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Setessan Champion | handled | Constellation — Whenever an enchantment you control enters, put a +1/+1 counter on this creature and draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Storm's Wrath | handled | Storm's Wrath deals 4 damage to each creature and each planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Treacherous Blessing | handled | When this enchantment enters, draw three cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wavebreak Hippocamp | handled | Whenever you cast your first spell during each opponent's turn, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>10 cards</summary>

- Dryad of the Ilysian Grove
- Enigmatic Incarnation
- Klothys, God of Destiny
- Kroxa, Titan of Death's Hunger
- Kunoros, Hound of Athreos
- Nylea, Keen-Eyed
- Nyxbloom Ancient
- Shadowspear
- Thassa, Deep-Dwelling
- Uro, Titan of Nature's Wrath

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| This creature escapes with a +1/+1 counter on it. | Ox of Agonas, Phoenix of Ash | 2 |
| At the beginning of your end step, you may exile an enchantment card from your graveyard. If you do, create a 2/2 black Zombie creature token. | Aphemia, the Cacophony | 1 |
| Choose one — • Create an X/1 red Elemental creature token with trample and haste. Sacrifice it at the beginning of the next end step. • Purphoros's Intervention | Purphoros's Intervention | 1 |
| Choose one — • Destroy X target artifacts and/or enchantments. • Target player gains twice X life. | Heliod's Intervention | 1 |
| Choose one — • Look at the top X cards of your library. Put up to two of them into your hand and the rest on the bottom of your library in a random order. • Cou | Thassa's Intervention | 1 |
| Choose one — • Search your library for up to X land cards, reveal them, put them into your hand, then shuffle. • Nylea's Intervention deals twice X damage to ea | Nylea's Intervention | 1 |
| Constellation — Whenever an enchantment you control enters, you may have this creature become a copy of another target creature, except it has this ability. | Protean Thaumaturge | 1 |
| Each nonland card in your graveyard has escape. The escape cost is equal to the card's mana cost plus exile three other cards from your graveyard. | Underworld Breach | 1 |
| Each player who controls a creature with power 4 or greater draws a card. Then destroy all creatures. | Shatter the Sky | 1 |
| Equipped creatures you control have flying and haste. | Dalakos, Crafter of Wonders | 1 |
| Haktos attacks each combat if able. | Haktos the Unscarred | 1 |
| I — Gain control of target creature for as long as this Saga remains on the battlefield. | The Akroan War | 1 |
| I, II — Mill three cards. Then you may exile a creature or enchantment card from your graveyard. If you do, create a 2/2 black Zombie creature token. | Tymaret Calls the Dead | 1 |
| If damage would be dealt to Polukranos while it has a +1/+1 counter on it, prevent that damage and remove that many +1/+1 counters from it. | Polukranos, Unchained | 1 |
| II — Noncreature spells your opponents cast cost {2} more to cast until your next turn. | Elspeth Conquers Death | 1 |
| II — Tap all nonland permanents target opponent controls. They don't untap during their controller's next untap step. | Kiora Bests the Sea God | 1 |
| IV — Create a Gold token. | The First Iroan Games | 1 |
| +1: Look at the top four cards of your library. You may reveal an enchantment card from among them and put that card into your hand. Put the rest on the bottom  | Calix, Destiny's Hand | 1 |
| Loyalty abilities of planeswalkers your opponents control cost {1} more to activate. | Eidolon of Obstruction | 1 |
| Other Satyrs you control get +1/+1 and have haste. | Gallia of the Endless Dance | 1 |
| Pegasus creatures you control have lifelink. | Archon of Sun's Grace | 1 |
| {4}, {T}: Remove target attacking or blocking creature from combat. | Labyrinth of Skophos | 1 |
| −3: Return target nonland permanent to its owner's hand, then that player exiles a card from their hand. | Ashiok, Nightmare Muse | 1 |
| Reveal the top six cards of your library. An opponent exiles a nonland card from among them, then you put the rest into your hand. That opponent may cast the ex | Allure of the Unknown | 1 |
| Spells you cast with mana value 5 or greater cost {1} less to cast and can't be countered. | Thryx, the Sudden Storm | 1 |
| This creature escapes with two +1/+1 counters on it. | Woe Strider | 1 |
| −1: Up to two target creatures you control each get +2/+1 until end of turn. | Elspeth, Sun's Nemesis | 1 |
| When Atris enters, target opponent looks at the top three cards of your library and separates them into a face-down pile and a face-up pile. Put one pile into y | Atris, Oracle of Half-Truths | 1 |
| When this creature dies, return it to the battlefield. It's an Aura enchantment with enchant creature you control and "{G}{W}: Enchanted creature gains indestru | Bronzehide Lion | 1 |
| When this creature enters, look at the top X cards of your library, where X is your devotion to blue. Put up to one of them on top of your library and the rest  | Thassa's Oracle | 1 |
| When this creature enters, return any number of Aura cards from your graveyard to the battlefield attached to creatures you control. Exile those Auras at the be | Storm Herald | 1 |
| Whenever another creature you control dies, you may pay 2 life. If you do, draw a card. | Erebos, Bleak-Hearted | 1 |
| Whenever another nontoken creature you control dies, you may exile it. If you do, create a token that's a copy of that creature, except it's 1/1 and it's a Nigh | Nightmare Shepherd | 1 |
| Whenever Taranika attacks, untap another target creature you control. Until end of turn, that creature has base power and toughness 4/4 and gains indestructible | Taranika, Akroan Veteran | 1 |
| Whenever this creature attacks or becomes the target of a spell an opponent controls, choose one — • This creature deals 3 damage to each opponent. • Exile the  | Tectonic Giant | 1 |
| Whenever this creature becomes blocked by a creature, that creature's controller draws a card. | Nessian Boar | 1 |
| {2}{R}: You may put a red creature card or an artifact creature card from your hand onto the battlefield. Sacrifice it at the beginning of the next end step. | Purphoros, Bronze-Blooded | 1 |
| Your opponents can't cast spells with the same name as the exiled card. | Ashiok's Erasure | 1 |

## Notes



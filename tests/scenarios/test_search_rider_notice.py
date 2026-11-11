"""A search whose description reads ("a basic land card or Town card") must
not leave a "When you search your library this way, ..." rider silently
dropped: the card stays a notice, not silent (Prishe's Wanderings)."""

from magic_cards_model.models.card import Card
from magic_cards_model.support import card_support

PRISHE = (
    "Search your library for a basic land card or Town card, put it onto the "
    "battlefield tapped, then shuffle. When you search your library this way, "
    "put a +1/+1 counter on target creature you control."
)


def test_unread_search_rider_is_a_notice_not_silent():
    card = Card.model_validate(
        {
            "id": "bc92988c-d628-45ea-8606-516a1211cef3",
            "layout": "normal",
            "keywords": [],
            "legalities": {"standard": "legal", "pioneer": "legal", "modern": "legal"},
            "rarity": "common",
            "set": "fin",
            "name": "Prishe's Wanderings",
            "mana_cost": "{3}{G}",
            "cmc": 4.0,
            "type_line": "Sorcery",
            "oracle_text": PRISHE,
            "colors": ["G"],
            "color_identity": ["G"],
        }
    )
    assert card_support(card).status == "notice"

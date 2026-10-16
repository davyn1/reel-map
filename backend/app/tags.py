"""Food type tags, derived from a place's name, its reels' captions and Muse's notes.

Computed on the fly (not stored), so editing the keyword list re-tags every place.
Order matters only for display: tags come back in this order.
"""

import re

from app.models import Place

TAGS: list[tuple[str, str]] = [
    ("Pizza", r"pizza"),
    ("Burgers", r"burgers?|smashburgers?"),
    ("Fried chicken", r"fried chicken|chicken wings?|wings|popcorn chicken|chicken sandwich|hot honey"),
    ("Donuts", r"donuts?|doughnuts?|fritters?"),
    ("Bakery", r"bakery|croissants?|salt bread|pastr(?:y|ies)"),
    ("Desserts", r"cakes?|desserts?|ice cream|milkshakes?|tiramisu|pudding|cobbler|churros?|candy shop|sweet shop|baklava"),
    ("Boba & coffee", r"boba|coffee|roastery|matcha|latte"),
    ("Mexican", r"mexican|tacos?|(?<!rice )burritos?|quesabirria|birria|al pastor|chalupas?|nachos|taqueria"),
    ("Korean", r"korean|bossam"),
    ("Thai", r"thai|tom yum"),
    ("Vietnamese", r"vietnamese|pho|banh mi"),
    ("Chinese", r"chinese|peking duck|sweet (?:&|and) sour|dim sum|dumplings?"),
    ("Taiwanese", r"taiwanese"),
    ("Japanese", r"japanese|sushi|ramen|omakase"),
    ("Hawaiian", r"hawaiian|poke|loco moco"),
    ("Middle Eastern", r"falafels?|shawarma|mediterranean|palestinian"),
    ("Seafood", r"seafood|crab|lobster|shrimp|oysters?|scallops?|salmon|seabass|crawfish"),
    ("BBQ", r"bbq|barbecue|brisket|skewers"),
    ("Sandwiches", r"sandwich(?:es)?|deli\b|delicatessen|chopped cheese"),
    ("Comfort food", r"mac n cheese|mac and cheese|mac n gritz|grits|loaded fries"),
    ("Vegan", r"vegan|plant[- ]based"),
    ("Brunch", r"brunch|breakfast"),
    ("Michelin", r"michelin"),
    ("Late night", r"late[- ]night|open late"),
]

_COMPILED = [(label, re.compile(rf"\b(?:{pattern})\b")) for label, pattern in TAGS]


def text_for(place: Place) -> str:
    reels = [*place.reels, *place.extra_reels]
    parts = [place.name, *(r.venue_raw for r in reels), *(r.dish for r in reels), *(r.muse_note for r in reels)]
    return " ".join(p for p in parts if p).lower().replace("’", "'")


def place_tags(place: Place) -> list[str]:
    text = text_for(place)
    return [label for label, pattern in _COMPILED if pattern.search(text)]

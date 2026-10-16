"""Food type tags, derived from a place's name, its reels' captions and Muse's notes.

Broad on purpose: about a dozen cuisines plus two groups that cut across cuisines
(Seafood, Sweets & bakery), rather than one tag per dish. A place can have several.
Computed on the fly (not stored), so editing these lists re-tags every place.
"""

import re

from app.models import Place

CUISINES: list[tuple[str, str]] = [
    ("Mexican", r"mexican|tacos?|(?<!rice )burritos?|quesabirria|birria|al pastor|chalupas?|taqueria|churros?"),
    ("Korean", r"korean|bossam|bibimbap|bulgogi|kbbq"),
    ("Chinese", r"chinese|taiwanese|popcorn chicken|sweet (?:&|and) sour|dim sum|dumplings?|skewers|szechuan|sichuan|bok ?choy"),
    ("Japanese", r"japanese|sushi|ramen|omakase|izakaya"),
    ("Thai", r"thai|tom yum"),
    ("Vietnamese", r"vietnamese|pho|banh mi"),
    ("Middle Eastern", r"falafels?|shawarma|mediterranean|palestinian|middle eastern"),
    ("Hawaiian", r"hawaiian|poke|loco moco|spam musubi"),
    # Pizza only: "Italian garlic salmon" and "zaza pasta" turned up at soul-food spots.
    ("Pizza & Italian", r"pizza|pizzeria|trattoria|italian restaurant"),
]

# Only when none of the cuisines above match: "fried chicken" at a Korean spot is Korean.
AMERICAN = (
    "American",
    r"american|californian|michelin|burgers?|smashburgers?|fried chicken|chicken wings?|wings|chicken sandwich|hot honey|"
    r"bbq|barbecue|brisket|mac n cheese|mac and cheese|mac n gritz|grits|soul food|chopped cheese|"
    r"sandwich(?:es)?|deli\b|delicatessen|loaded fries|nachos",
)

# Groups that sit alongside a cuisine.
GROUPS: list[tuple[str, str]] = [
    ("Seafood", r"seafood|crab|lobster|shrimp|oysters?|scallops?|crawfish"),
    (
        "Sweets & bakery",
        r"donuts?|doughnuts?|fritters?|bakery|croissants?|salt bread|pastr(?:y|ies)|cakes?|desserts?|ice cream|"
        r"milkshakes?|tiramisu|pudding|cobbler|candy shop|sweet shop|baklava|boba|coffee|roastery|matcha",
    ),
]

TAG_ORDER = [label for label, _ in CUISINES] + [AMERICAN[0]] + [label for label, _ in GROUPS]


def _compile(pairs: list[tuple[str, str]]) -> list[tuple[str, re.Pattern]]:
    return [(label, re.compile(rf"\b(?:{pattern})\b")) for label, pattern in pairs]


_CUISINES = _compile(CUISINES)
_AMERICAN = _compile([AMERICAN])[0]
_GROUPS = _compile(GROUPS)


def text_for(place: Place) -> str:
    reels = [*place.reels, *place.extra_reels]
    parts = [place.name, *(r.venue_raw for r in reels), *(r.dish for r in reels), *(r.muse_note for r in reels)]
    return " ".join(p for p in parts if p).lower().replace("’", "'")


def place_tags(place: Place) -> list[str]:
    """Tags shown for a place: the ones you picked if you edited them, else the automatic ones."""
    if place.tags_override is not None:
        return sort_tags(place.tags_override)
    return auto_tags(place)


def sort_tags(tags: list[str]) -> list[str]:
    return sorted(set(tags), key=TAG_ORDER.index)


def auto_tags(place: Place) -> list[str]:
    text = text_for(place)
    tags = [label for label, pattern in _CUISINES if pattern.search(text)]
    if not tags and _AMERICAN[1].search(text):
        tags.append(_AMERICAN[0])
    tags += [label for label, pattern in _GROUPS if pattern.search(text)]
    return tags

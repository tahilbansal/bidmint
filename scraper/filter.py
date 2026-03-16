FOOD_KEYWORDS = [
    "rice", "chawal", "basmati", "parboiled", "sella", "arwa",
    "wheat", "gehu", "gehun", "atta", "flour", "maida", "chakki",
    "dal", "pulses", "lentil", "moong", "chana", "masoor", "urad",
    "rajma", "arhar", "toor",
    "oil", "tel", "ghee", "vanaspati", "mustard", "sarson",
    "sunflower", "palm", "groundnut",
    "sugar", "cheeni", "gur", "jaggery", "shakkar",
    "milk", "doodh", "paneer", "curd", "butter", "dairy",
    "masala", "spices", "turmeric", "haldi", "mirch", "jeera",
    "dhania", "garam masala",
    "grocery", "ration", "provisions", "foodgrain", "kirana",
    "salt", "namak", "tea", "chai", "biscuit",
    "potato", "aloo", "onion", "pyaz", "tomato",
]

PUNJAB_KEYWORDS = [
    "punjab", "patiala", "ludhiana", "amritsar", "jalandhar",
    "chandigarh", "mohali", "bathinda", "pathankot", "hoshiarpur",
    "gurdaspur", "firozpur", "faridkot", "moga", "ropar", "barnala",
    "mansa", "fatehgarh", "tarn taran", "nawanshahr",
    # Adjacent states — suppliers can fulfil these too
    "haryana", "himachal", "hp", "j&k", "jammu",
]


def is_food_tender(tender: dict) -> bool:
    """Check if tender title or department mentions food-related keywords."""
    text = (tender.get("title", "") + " " + tender.get("department", "")).lower()
    return any(kw in text for kw in FOOD_KEYWORDS)


def is_punjab_tender(tender: dict) -> bool:
    """Check if tender location or department is in Punjab / adjacent states."""
    location = tender.get("location", "").lower()
    department = tender.get("department", "").lower()
    return any(kw in location or kw in department for kw in PUNJAB_KEYWORDS)


def detect_category(tender: dict) -> str:
    """Rule-based category detection from tender title."""
    title = tender.get("title", "").lower()
    if any(k in title for k in ["rice", "chawal", "basmati", "sella"]):
        return "rice"
    elif any(k in title for k in ["wheat", "gehu", "atta", "flour", "maida"]):
        return "wheat"
    elif any(k in title for k in ["dal", "pulse", "lentil", "moong", "chana", "masoor"]):
        return "pulses"
    elif any(k in title for k in ["oil", "tel", "ghee", "vanaspati"]):
        return "oils"
    elif any(k in title for k in ["sugar", "cheeni", "gur", "jaggery"]):
        return "sugar"
    elif any(k in title for k in ["milk", "doodh", "dairy", "paneer"]):
        return "dairy"
    elif any(k in title for k in ["masala", "spice", "turmeric", "haldi"]):
        return "spices"
    else:
        return "other_food"


def filter_tenders(tenders: list) -> list:
    """Filter raw scraped tenders to only Punjab food tenders, with category tagged."""
    filtered = [
        {**t, "category": detect_category(t)}
        for t in tenders
        if is_food_tender(t) and is_punjab_tender(t)
    ]
    print(f"Filter: {len(tenders)} total → {len(filtered)} Punjab food tenders")
    return filtered

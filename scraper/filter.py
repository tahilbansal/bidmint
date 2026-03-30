"""BidMint tender filter — only pass Punjab food-supply tenders.

Design:
- BLOCKLIST checked first on title: rejects construction / maintenance / IT /
  medical tenders that may contain food keywords by coincidence.
- FOOD_KEYWORDS use regex word-boundary matching so "oil" ≠ "soil",
  "rice" ≠ "price", "dal" ≠ "medal".
- Compound oil terms ("edible oil", "mustard oil") are listed explicitly to
  survive the BLOCKLIST even though bare "oil" is excluded.
"""
import logging
import re

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Positive food keywords — title must match at least one (word-boundary).
# ---------------------------------------------------------------------------
FOOD_KEYWORDS = [
    # Grains & cereals
    "basmati", "chawal", "parboiled", "sella", "arwa",
    "gehu", "gehun", "wheat", "atta", "flour", "maida", "chakki",
    "rice",
    # Pulses
    "dal", "pulses", "lentil", "moong", "chana", "masoor", "urad",
    "rajma", "arhar", "toor",
    # Oils & fats — compound phrases beat the BLOCKLIST for bare "oil"
    "edible oil", "cooking oil", "mustard oil", "sunflower oil",
    "palm oil", "groundnut oil", "soybean oil",
    "sarson", "ghee", "vanaspati",
    # Sugar & sweeteners
    "sugar", "cheeni", "gur", "jaggery", "shakkar",
    # Dairy
    "milk", "doodh", "paneer", "curd", "butter", "dairy",
    # Spices & condiments
    "masala", "turmeric", "haldi", "mirch", "jeera", "dhania",
    "garam masala", "spices",
    # Grocery staples
    "grocery", "ration", "provisions", "foodgrain", "kirana",
    "namak", "tea", "chai", "biscuit",
    # Vegetables
    "vegetable", "potato", "aloo", "onion", "pyaz", "tomato",
    "sabzi", "sabji", "carrot", "gajar", "cauliflower", "bhindi",
    "brinjal", "baingan", "palak", "spinach", "gourd", "lauki",
    "pumpkin", "kaddu",
    # Fruits
    "fruit", "apple", "mango", "aam", "banana", "kela", "orange",
    "grapes", "papaya", "guava", "amrood",
]

# ---------------------------------------------------------------------------
# Blocklist — if ANY of these appear in the tender TITLE, reject it
# even when a food keyword is also present.
# ---------------------------------------------------------------------------
BLOCKLIST = [
    # Construction & civil works
    "construction", "civil work", "civil works", "rcc",
    "masonry", "concrete", "boundary wall", "renovation",
    "demolition", "earthwork", "road work", "pavement",
    "drainage", "sewerage", "building work",
    # Maintenance & repair
    "maintenance", "repair", "servicing", "amc",
    "annual maintenance", "overhauling", "upkeep",
    # Electrical & mechanical
    "electrical", "wiring", "transformer", "generator",
    "pump", "motor", "hvac", "air conditioning", "air conditioner",
    "hydraulic", "lubrication", "lubricating",
    # Plumbing
    "plumbing", "pipe fitting", "sanitary fitting",
    # Furniture & interiors
    "furniture", "flooring", "tiles", "tiling",
    "interior", "false ceiling", "partition",
    # IT equipment
    "computer", "laptop", "software", "server",
    "printer", "scanner", "cctv", "networking",
    # Vehicles, transport & two/four-wheelers
    "vehicle", "ambulance", "tyre", "spare part",
    "two wheeler", "two-wheeler", "4 wheeler", "four wheeler", "four-wheeler",
    "wheeler", "motorcycle", "scooter", "bicycle",
    # Civil improvement / upgrade works — not food supply
    "improvement work", "improvement of", "augmentation",
    "upgradation", "bituminous", "asphalting",
    # Uniforms & textiles
    "uniform", "linen", "garment",
    # Medical & pharma
    "medicine", "drug", "pharmaceutical", "surgical",
    "medical equipment", "laboratory",
    # Printing & stationery
    "printing", "stationery",
    # Security & cleaning services
    "security service", "housekeeping", "pest control",
    "fire fighting", "fire safety",
    # Non-food industrial oils / fuels
    "transformer oil", "engine oil", "lubricating oil",
    "hydraulic oil", "diesel", "petrol",
]

# North India geography — Punjab, Haryana, Delhi/NCR, and adjacent hill states
NORTH_INDIA_KEYWORDS = [
    # Punjab districts
    "punjab", "patiala", "ludhiana", "amritsar", "jalandhar",
    "chandigarh", "mohali", "bathinda", "pathankot", "hoshiarpur",
    "gurdaspur", "firozpur", "faridkot", "moga", "ropar", "barnala",
    "mansa", "fatehgarh", "tarn taran", "nawanshahr", "kapurthala",
    "muktsar", "sangrur",
    # Haryana districts
    "haryana",
    "ambala", "kurukshetra", "karnal", "panipat", "sonipat",
    "rohtak", "jhajjar", "hisar", "sirsa", "fatehabad",
    "rewari", "mahendragarh", "yamunanagar", "panchkula",
    "kaithal", "jind", "bhiwani", "palwal", "nuh",
    # Delhi / NCR
    "delhi", "new delhi", "ncr",
    "gurugram", "gurgaon", "faridabad", "noida", "ghaziabad",
    # Hill states — suppliers can fulfil these too
    "himachal", "hp", "j&k", "jammu", "kashmir",
]

# Backward-compat alias used externally
PUNJAB_KEYWORDS = NORTH_INDIA_KEYWORDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match(text: str, phrase: str) -> bool:
    """Case-insensitive word-boundary match for a phrase inside text."""
    return bool(re.search(r'\b' + re.escape(phrase) + r'\b', text, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_food_tender(tender: dict) -> bool:
    """Return True only when the tender is for food/grocery supply.

    Checks in order:
    1. Reject if title contains a BLOCKLIST term (construction, maintenance…).
    2. Accept if title contains a FOOD_KEYWORD (word-boundary matched).
    3. Fallback accept for known food-supply department names.
    """
    title = tender.get("title", "")
    department = tender.get("department", "").lower()
    title_lower = title.lower()

    # Step 1 — blocklist check on title (rejects non-food works/services)
    if any(_match(title_lower, bl) for bl in BLOCKLIST):
        return False

    # Step 2 — food keyword in title (word-boundary)
    if any(_match(title_lower, kw) for kw in FOOD_KEYWORDS):
        return True

    # Step 3 — fallback for food/supply department names
    FOOD_DEPTS = ["food", "supply", "ration", "fci", "nafed", "civil supplies"]
    return any(dep in department for dep in FOOD_DEPTS)


def is_north_india_tender(tender: dict) -> bool:
    """
    Return True when the tender is relevant to North India suppliers.

    Source-specific scrapers (punjab_state, haryana) already guarantee
    geographic relevance, so geography checks are skipped for them.
    CPPP tenders often have no location at all — accept them so the
    AI scorer can evaluate them on other signals.
    """
    source = tender.get("source", "")
    # Scrapers that already constrain to a single state
    if source in ("punjab_state", "haryana"):
        return True
    # CPPP tenders often have blank location — include them for AI scoring
    if source == "cppp" and not tender.get("location"):
        return True
    location = tender.get("location", "").lower()
    department = tender.get("department", "").lower()
    return any(kw in location or kw in department for kw in NORTH_INDIA_KEYWORDS)


# Backward-compat alias
is_punjab_tender = is_north_india_tender


def detect_category(tender: dict) -> str:
    """Rule-based category detection from tender title."""
    title = tender.get("title", "").lower()

    if any(_match(title, k) for k in ["rice", "chawal", "basmati", "sella", "arwa", "parboiled"]):
        return "rice"
    if any(_match(title, k) for k in ["wheat", "gehu", "gehun", "atta", "flour", "maida"]):
        return "wheat"
    if any(_match(title, k) for k in ["dal", "pulse", "lentil", "moong", "chana", "masoor", "urad", "rajma"]):
        return "pulses"
    if any(_match(title, k) for k in ["edible oil", "cooking oil", "mustard oil", "sunflower oil",
                                       "palm oil", "groundnut oil", "ghee", "vanaspati", "sarson"]):
        return "oils"
    if any(_match(title, k) for k in ["sugar", "cheeni", "gur", "jaggery", "shakkar"]):
        return "sugar"
    if any(_match(title, k) for k in ["milk", "doodh", "dairy", "paneer", "curd", "butter"]):
        return "dairy"
    if any(_match(title, k) for k in ["masala", "spice", "turmeric", "haldi", "mirch", "jeera"]):
        return "spices"
    if any(_match(title, k) for k in ["vegetable", "sabzi", "sabji", "aloo", "potato", "onion",
                                       "pyaz", "tomato", "carrot", "cauliflower", "bhindi"]):
        return "vegetables"
    if any(_match(title, k) for k in ["fruit", "apple", "mango", "banana", "orange", "grapes"]):
        return "fruits"
    return "other_food"


def filter_tenders(tenders: list) -> list:
    """Filter raw scraped tenders to only North India food tenders, with category tagged."""
    rejected_food = sum(1 for t in tenders if not is_food_tender(t))
    filtered = [
        {**t, "category": detect_category(t)}
        for t in tenders
        if is_food_tender(t) and is_north_india_tender(t)
    ]
    log.info(
        "Filter: %d total → %d North India food tenders (%d rejected as non-food)",
        len(tenders), len(filtered), rejected_food,
    )
    return filtered

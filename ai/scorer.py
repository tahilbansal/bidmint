from database.models import Supplier, Tender

ADJACENT_DISTRICTS = {
    "patiala":    ["ludhiana", "fatehgarh sahib", "ropar", "ambala", "kurukshetra"],
    "ludhiana":   ["patiala", "jalandhar", "moga", "fatehgarh sahib", "barnala"],
    "amritsar":   ["gurdaspur", "tarn taran", "jalandhar", "pathankot"],
    "jalandhar":  ["ludhiana", "amritsar", "kapurthala", "hoshiarpur", "nawanshahr"],
    "bathinda":   ["mansa", "faridkot", "moga", "barnala", "muktsar"],
    "chandigarh": ["mohali", "patiala", "ropar", "ambala"],
    "mohali":     ["chandigarh", "patiala", "ropar", "fatehgarh sahib"],
}


def calculate_match_score(
    supplier: Supplier,
    tender: Tender,
    ai_result: dict
) -> int:
    """
    Calculate 0–100 match score between a supplier and a tender.

    Scoring weights:
    - Category match:       40 pts
    - Location match:       30 pts
    - AI confidence:        20 pts
    - Quantity feasibility: 10 pts
    - Red flag penalty:    -10 per flag
    """
    score = 0

    # ── 1. Category match (40 pts) ──────────────────────────────
    supplier_cats = [c.strip().lower() for c in supplier.categories.split(",")]
    tender_cat = ai_result.get("food_category", "").lower()

    if tender_cat in supplier_cats:
        score += 40                          # Exact match
    elif "all" in supplier_cats:
        score += 30                          # Supplier handles everything
    elif tender_cat != "other" and len(supplier_cats) > 0:
        score += 15                          # Possible broad match

    # ── 2. Location match (30 pts) ──────────────────────────────
    tender_loc = (tender.location or "").lower()
    supplier_dist = (supplier.district or "").lower()
    adjacent = ADJACENT_DISTRICTS.get(supplier_dist, [])

    if supplier_dist in tender_loc:
        score += 30                          # Same district
    elif any(adj in tender_loc for adj in adjacent):
        score += 20                          # Adjacent district
    elif "punjab" in tender_loc:
        score += 10                          # Same state at least

    # ── 3. AI confidence (20 pts) ───────────────────────────────
    conf_map = {"HIGH": 20, "MEDIUM": 12, "LOW": 5}
    score += conf_map.get(ai_result.get("confidence", "LOW"), 5)

    # ── 4. Quantity feasibility (10 pts) ────────────────────────
    qty_kg = ai_result.get("quantity_kg")
    if qty_kg is not None:
        if qty_kg <= 50_000:                 # < 50 tonnes — MSME feasible
            score += 10
        elif qty_kg <= 200_000:              # < 200 tonnes — possible
            score += 5
        # > 200 tonnes — too large, no points
    else:
        score += 5                           # Unknown — neutral

    # ── 5. Red flag penalty ─────────────────────────────────────
    red_flags = ai_result.get("red_flags", [])
    score -= len(red_flags) * 10

    return max(0, min(100, score))

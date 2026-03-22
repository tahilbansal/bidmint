"""
Manual pipeline test script — run each layer independently.

Usage:
  python scripts/test_pipeline.py --step filter       # Test keyword filter on sample data
  python scripts/test_pipeline.py --step scorer       # Test match scoring
  python scripts/test_pipeline.py --step db           # Test DB connection + read suppliers
  python scripts/test_pipeline.py --step ai           # Test AI matching on sample tender
  python scripts/test_pipeline.py --step scraper      # Test GeM scraper (live, 30-60s)
  python scripts/test_pipeline.py --step prices       # Test AGMARKNET price fetch
  python scripts/test_pipeline.py --step whatsapp     # Test AiSensy WhatsApp send
  python scripts/test_pipeline.py --step full         # Run full pipeline (no WhatsApp)
"""

import sys
import os
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── STEP 1: Filter ──────────────────────────────────────────────────────────

def test_filter():
    print("\n" + "="*60)
    print("STEP 1 — Keyword Filter Test")
    print("="*60)

    from scraper.filter import filter_tenders, detect_category

    sample_tenders = [
        {"id": "T001", "title": "Supply of Basmati Rice 1121 — 2000 kg",
         "department": "District Hospital Patiala", "location": "Patiala, Punjab",
         "quantity": "2000 KG", "deadline": None, "source": "gem"},
        {"id": "T002", "title": "Procurement of Wheat Atta 10kg packs",
         "department": "Civil Supplies Punjab", "location": "Ludhiana, Punjab",
         "quantity": "5000 KG", "deadline": None, "source": "gem"},
        {"id": "T003", "title": "Construction of Boundary Wall",
         "department": "PWD Punjab", "location": "Amritsar, Punjab",
         "quantity": "1 Lot", "deadline": None, "source": "gem"},
        {"id": "T004", "title": "Supply of Mustard Oil 200 litres",
         "department": "Sainik School Kapurthala", "location": "Kapurthala, Punjab",
         "quantity": "200 LTR", "deadline": None, "source": "gem"},
        {"id": "T005", "title": "Moong Dal Whole Grade A",
         "department": "FCI Maharashtra", "location": "Mumbai, Maharashtra",
         "quantity": "10000 KG", "deadline": None, "source": "gem"},
    ]

    filtered = filter_tenders(sample_tenders)

    print(f"\nInput:    {len(sample_tenders)} tenders")
    print(f"Filtered: {len(filtered)} Punjab food tenders\n")

    for t in filtered:
        print(f"  ✅ [{t['id']}] {t['title'][:60]}")
        print(f"      Category: {t['category']} | Location: {t['location']}")

    discarded = [t for t in sample_tenders if t['id'] not in [f['id'] for f in filtered]]
    print(f"\nDiscarded ({len(discarded)}):")
    for t in discarded:
        print(f"  ❌ [{t['id']}] {t['title'][:60]}")

    print("\n✅ Filter test passed!" if len(filtered) == 3 else "\n⚠️  Check filter results")


# ─── STEP 2: AI Matching ─────────────────────────────────────────────────────

async def test_ai():
    print("\n" + "="*60)
    print("STEP 2 — AI Matching Test (Claude API)")
    print("="*60)

    from ai.matcher import parse_tender_with_ai

    sample_tender = {
        "id": "GEM/2026/B/4567890",
        "title": "Supply of Basmati Rice 1121 Premium Quality",
        "department": "District Hospital Patiala, Department of Health Punjab",
        "location": "Patiala, Punjab",
        "quantity": "2000 KG",
    }

    print(f"\nTesting with: {sample_tender['title']}")
    print("Calling Claude API...")

    result = await parse_tender_with_ai(sample_tender)

    print(f"\nAI Result:")
    print(f"  food_category:    {result.get('food_category')}")
    print(f"  item_name_hindi:  {result.get('item_name_hindi')}")
    print(f"  quantity_kg:      {result.get('quantity_kg')}")
    print(f"  fssai_required:   {result.get('fssai_required')}")
    print(f"  confidence:       {result.get('confidence')}")
    print(f"  whatsapp_summary: {result.get('whatsapp_summary')}")
    print(f"  red_flags:        {result.get('red_flags')}")

    if result.get("confidence") in ("HIGH", "MEDIUM", "LOW"):
        print("\n✅ AI matching test passed!")
    else:
        print("\n⚠️  Unexpected result — check ANTHROPIC_API_KEY in .env")


# ─── STEP 3: Scorer ──────────────────────────────────────────────────────────

def test_scorer():
    print("\n" + "="*60)
    print("STEP 3 — Match Scorer Test")
    print("="*60)

    from ai.scorer import calculate_match_score
    from database.models import Supplier, Tender

    test_cases = [
        {
            "label": "Perfect match (same district, exact category, HIGH confidence)",
            "supplier": Supplier(district="patiala", categories="rice,wheat"),
            "tender": Tender(location="Patiala District Hospital", category="rice"),
            "ai": {"food_category": "rice", "confidence": "HIGH", "quantity_kg": 2000, "red_flags": []},
            "expected_min": 90,
        },
        {
            "label": "Adjacent district match",
            "supplier": Supplier(district="patiala", categories="wheat"),
            "tender": Tender(location="Ludhiana Civil Hospital", category="wheat"),
            "ai": {"food_category": "wheat", "confidence": "HIGH", "quantity_kg": 5000, "red_flags": []},
            "expected_min": 80,
        },
        {
            "label": "Wrong category — should be low score",
            "supplier": Supplier(district="patiala", categories="rice"),
            "tender": Tender(location="Patiala", category="construction"),
            "ai": {"food_category": "other", "confidence": "LOW", "quantity_kg": None, "red_flags": []},
            "expected_max": 30,
        },
        {
            "label": "Red flag penalty (2 flags)",
            "supplier": Supplier(district="patiala", categories="rice"),
            "tender": Tender(location="Patiala", category="rice"),
            "ai": {"food_category": "rice", "confidence": "HIGH", "quantity_kg": 2000,
                   "red_flags": ["unrealistic_deadline", "vague_specs"]},
            "expected": 80,
        },
    ]

    all_passed = True
    for tc in test_cases:
        score = calculate_match_score(tc["supplier"], tc["tender"], tc["ai"])
        if "expected_min" in tc:
            passed = score >= tc["expected_min"]
            label = f">= {tc['expected_min']}"
        elif "expected_max" in tc:
            passed = score <= tc["expected_max"]
            label = f"<= {tc['expected_max']}"
        else:
            passed = score == tc["expected"]
            label = f"== {tc['expected']}"

        icon = "✅" if passed else "❌"
        print(f"\n  {icon} {tc['label']}")
        print(f"      Score: {score} (expected {label})")
        if not passed:
            all_passed = False

    print(f"\n{'✅ All scorer tests passed!' if all_passed else '❌ Some scorer tests failed'}")


# ─── STEP 4: DB connection ───────────────────────────────────────────────────

def test_db():
    print("\n" + "="*60)
    print("STEP 4 — Database Connection Test")
    print("="*60)

    from database.connection import SessionLocal
    from database.models import Supplier, Tender, Alert

    db = SessionLocal()
    try:
        supplier_count = db.query(Supplier).count()
        tender_count = db.query(Tender).count()
        alert_count = db.query(Alert).count()

        print(f"\n  ✅ Connected to database!")
        print(f"\n  Suppliers: {supplier_count}")
        print(f"  Tenders:   {tender_count}")
        print(f"  Alerts:    {alert_count}")

        suppliers = db.query(Supplier).filter(Supplier.active == True).all()  # noqa: E712
        if suppliers:
            print(f"\n  Active suppliers:")
            for s in suppliers:
                print(f"    - {s.whatsapp} | {s.name or 'unnamed'} | {s.district} | {s.categories}")
        else:
            print("\n  No active suppliers yet. Run: python scripts/add_supplier.py")

    except Exception as e:
        print(f"\n  ❌ DB error: {e}")
    finally:
        db.close()


# ─── STEP 5: GeM Scraper ─────────────────────────────────────────────────────

async def test_scraper():
    print("\n" + "="*60)
    print("STEP 5 — GeM Scraper Test (live)")
    print("="*60)
    print("Launching Playwright browser... (may take 30–60 seconds)")

    from scraper.gem_scraper import scrape_gem_tenders
    from scraper.filter import filter_tenders

    try:
        tenders = await scrape_gem_tenders()
        print(f"\n  Raw tenders scraped: {len(tenders)}")

        if tenders:
            print(f"\n  Sample (first 5):")
            for t in tenders[:5]:
                print(f"    [{t['id']}] {t['title'][:60]}")

        filtered = filter_tenders(tenders)
        print(f"\n  Punjab food tenders: {len(filtered)}")
        for t in filtered[:5]:
            print(f"    ✅ [{t['id']}] {t['title'][:60]} | {t['category']}")

        print(f"\n✅ Scraper test passed!" if tenders else "\n⚠️  No tenders scraped — GeM portal may be slow")

    except Exception as e:
        print(f"\n  ❌ Scraper error: {e}")


# ─── STEP 6: Mandi Prices ────────────────────────────────────────────────────

async def test_prices():
    print("\n" + "="*60)
    print("STEP 6 — AGMARKNET Mandi Prices Test")
    print("="*60)

    from scraper.agmarknet import fetch_punjab_prices

    try:
        prices = await fetch_punjab_prices()

        if prices:
            print(f"\n  Today's Punjab Mandi Prices:")
            for cat, p in prices.items():
                change = p.get("change", 0)
                arrow = "🔺" if change > 0 else "🔻" if change < 0 else "➡️ "
                print(f"    {arrow} {cat.title():10s}: ₹{p['modal']}/quintal "
                      f"({'+' if change > 0 else ''}{change:.0f}) @ {p['mandi']}")
            print(f"\n✅ Prices fetched successfully!")
        else:
            print("\n  ⚠️  No prices returned — AGMARKNET may have no data for today")

    except Exception as e:
        print(f"\n  ❌ Price fetch error: {e}")


# ─── STEP 7: WhatsApp API ───────────────────────────────────────────────────

async def test_whatsapp():
    print("\n" + "="*60)
    print("STEP 7 — WhatsApp API Test (AiSensy)")
    print("="*60)

    from dotenv import load_dotenv
    load_dotenv()

    from whatsapp.sender import send_help_menu, _send_session_message

    admin = os.getenv("ADMIN_WHATSAPP")
    api_key = os.getenv("AISENSY_API_KEY")

    if not api_key:
        print("\n  ❌ AISENSY_API_KEY not set in .env")
        return
    if not admin:
        print("\n  ❌ ADMIN_WHATSAPP not set in .env")
        return

    print(f"\n  Sending HELP menu to {admin}...")
    success = await send_help_menu(admin)

    if success:
        print(f"  ✅ Message sent! Check WhatsApp on {admin}")
    else:
        print("  ❌ Message failed — check AISENSY_API_KEY and campaign setup")
        print("  Tip: Make sure 'session_reply' campaign exists in AiSensy dashboard")
        print("       OR the number has messaged your business WhatsApp in last 24h")


# ─── STEP 8: Full pipeline (no WhatsApp) ─────────────────────────────────────

async def test_full():
    print("\n" + "="*60)
    print("FULL PIPELINE TEST — No WhatsApp")
    print("="*60)

    from scraper.gem_scraper import scrape_gem_tenders
    from scraper.filter import filter_tenders
    from ai.matcher import parse_tender_with_ai
    from ai.scorer import calculate_match_score
    from database.connection import SessionLocal
    from database.models import Tender, Supplier

    db = SessionLocal()
    stats = {"scraped": 0, "new": 0, "matched": 0, "errors": 0}

    try:
        print("\n[1/4] Scraping GeM tenders...")
        raw = await scrape_gem_tenders()
        food = filter_tenders(raw)
        stats["scraped"] = len(food)
        print(f"      → {len(raw)} raw, {len(food)} Punjab food tenders")

        suppliers = db.query(Supplier).filter(Supplier.active == True).all()  # noqa: E712
        print(f"\n[2/4] Active suppliers: {len(suppliers)}")

        print(f"\n[3/4] Processing tenders with AI (max 5 for test)...")
        for t_raw in food[:5]:
            existing = db.query(Tender).filter(Tender.id == t_raw["id"]).first()
            if existing:
                print(f"      SKIP (already in DB): {t_raw['id']}")
                continue

            try:
                ai_result = await parse_tender_with_ai(t_raw)
                confidence = ai_result.get("confidence")
                category = ai_result.get("food_category")
                print(f"\n      [{t_raw['id']}]")
                print(f"        Title:    {t_raw['title'][:60]}")
                print(f"        AI:       {category} | {confidence} confidence")
                print(f"        Hindi:    {ai_result.get('item_name_hindi', '')}")
                print(f"        Flags:    {ai_result.get('red_flags', [])}")

                stats["new"] += 1

                print(f"\n[4/4] Match scoring against {len(suppliers)} suppliers:")
                for supplier in suppliers:
                    tender_obj = Tender(
                        id=t_raw["id"],
                        location=t_raw.get("location", ""),
                        category=category,
                    )
                    score = calculate_match_score(supplier, tender_obj, ai_result)
                    min_score = int(os.getenv("MIN_MATCH_SCORE", 70))
                    icon = "✅ WOULD ALERT" if score >= min_score else "❌ below threshold"
                    print(f"        {supplier.whatsapp} | score={score} | {icon}")
                    if score >= min_score:
                        stats["matched"] += 1

            except Exception as e:
                print(f"      ERROR on {t_raw.get('id')}: {e}")
                stats["errors"] += 1

    finally:
        db.close()

    print(f"\n{'='*60}")
    print(f"SUMMARY (WhatsApp NOT sent — testing mode)")
    print(f"  Scraped:  {stats['scraped']}")
    print(f"  New:      {stats['new']}")
    print(f"  Matched:  {stats['matched']}")
    print(f"  Errors:   {stats['errors']}")
    print(f"{'='*60}")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BidMint pipeline test")
    parser.add_argument(
        "--step",
        choices=["filter", "ai", "scorer", "db", "scraper", "prices", "whatsapp", "full"],
        required=True,
        help="Which step to test"
    )
    args = parser.parse_args()

    match args.step:
        case "filter":
            test_filter()
        case "ai":
            asyncio.run(test_ai())
        case "scorer":
            test_scorer()
        case "db":
            test_db()
        case "scraper":
            asyncio.run(test_scraper())
        case "prices":
            asyncio.run(test_prices())
        case "whatsapp":
            asyncio.run(test_whatsapp())
        case "full":
            asyncio.run(test_full())

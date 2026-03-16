from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


@scheduler.scheduled_job(CronTrigger(hour=6, minute=30))
async def run_daily_scrape():
    """Main job — 6:30 AM IST daily."""
    from scraper.gem_scraper import scrape_gem_tenders
    from scraper.cppp_scraper import scrape_cppp_tenders
    from scraper.filter import filter_tenders
    from ai.matcher import parse_tender_with_ai
    from ai.scorer import calculate_match_score
    from whatsapp.sender import send_tender_alert, send_admin_report
    from database.connection import SessionLocal
    from database.models import Tender, Supplier, Alert

    db = SessionLocal()
    stats = {"scraped": 0, "new": 0, "alerts_sent": 0, "errors": 0}

    try:
        # Scrape from multiple portals
        raw_tenders = []
        try:
            gem_tenders = await scrape_gem_tenders()
            raw_tenders.extend(gem_tenders)
        except Exception as e:
            print(f"GeM scraper failed: {e}")
            stats["errors"] += 1

        try:
            cppp_tenders = await scrape_cppp_tenders()
            raw_tenders.extend(cppp_tenders)
        except Exception as e:
            print(f"CPPP scraper failed: {e}")
            stats["errors"] += 1

        food_tenders = filter_tenders(raw_tenders)
        stats["scraped"] = len(food_tenders)

        for t_raw in food_tenders:
            # Skip already processed
            if db.query(Tender).filter(Tender.id == t_raw["id"]).first():
                continue

            try:
                ai_result = await parse_tender_with_ai(t_raw)

                # Skip if AI says it's not really food
                if ai_result["food_category"] == "other" \
                        and ai_result["confidence"] == "LOW":
                    continue

                # Save tender
                tender = Tender(
                    id=t_raw["id"],
                    source=t_raw.get("source", "gem"),
                    title=t_raw["title"],
                    title_hindi=ai_result.get("item_name_hindi", ""),
                    department=t_raw["department"],
                    location=t_raw["location"],
                    category=ai_result["food_category"],
                    quantity=t_raw["quantity"],
                    quantity_kg=ai_result.get("quantity_kg"),
                    deadline=t_raw.get("deadline"),
                    whatsapp_summary=ai_result["whatsapp_summary"],
                    ai_confidence=ai_result["confidence"],
                    red_flags=str(ai_result.get("red_flags", [])),
                )
                db.add(tender)
                stats["new"] += 1

                # Match to active suppliers
                suppliers = db.query(Supplier)\
                    .filter(Supplier.active == True).all()  # noqa: E712

                for supplier in suppliers:
                    score = calculate_match_score(supplier, tender, ai_result)
                    if score >= int(os.getenv("MIN_MATCH_SCORE", 70)):
                        sent = await send_tender_alert(supplier.whatsapp, tender)
                        if sent:
                            db.add(Alert(
                                supplier_id=supplier.id,
                                tender_id=tender.id,
                                match_score=score
                            ))
                            tender.alerted_count += 1
                            stats["alerts_sent"] += 1

            except Exception as e:
                print(f"Error processing tender {t_raw.get('id')}: {e}")
                stats["errors"] += 1
                continue

        db.commit()

    except Exception as e:
        print(f"Fatal scrape error: {e}")
        stats["errors"] += 1
    finally:
        # Always send admin report
        admin_wa = os.getenv("ADMIN_WHATSAPP")
        if admin_wa:
            stats["suppliers"] = db.query(Supplier)\
                .filter(Supplier.active == True).count()  # noqa: E712
            await send_admin_report(admin_wa, stats)
        db.close()


@scheduler.scheduled_job(CronTrigger(hour=8, minute=0))
async def send_morning_prices():
    """Send mandi prices digest — 8:00 AM IST daily."""
    from database.connection import SessionLocal
    from database.models import Supplier
    from scraper.agmarknet import fetch_punjab_prices
    from whatsapp.sender import send_mandi_prices

    db = SessionLocal()
    try:
        prices = await fetch_punjab_prices()
        suppliers = db.query(Supplier)\
            .filter(Supplier.active == True).all()  # noqa: E712
        for supplier in suppliers:
            await send_mandi_prices(
                supplier.whatsapp,
                supplier.categories,
                prices
            )
    finally:
        db.close()


@scheduler.scheduled_job(CronTrigger(hour=9, minute=0))
async def send_daily_admin_report():
    """Send admin health report — 9:00 AM IST daily."""
    from api.health import get_daily_stats
    from whatsapp.sender import send_admin_report

    admin_wa = os.getenv("ADMIN_WHATSAPP")
    if admin_wa:
        stats = get_daily_stats()
        await send_admin_report(admin_wa, stats)


if __name__ == "__main__":
    scheduler.start()
    print("BidMint scheduler running (IST timezone)... Ctrl+C to stop")
    asyncio.get_event_loop().run_forever()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# Playwright requires ProactorEventLoop on Windows to spawn subprocesses.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,  # Render captures stdout; stderr may be dropped
)
log = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


@scheduler.scheduled_job(CronTrigger(hour=6, minute=30))
async def run_daily_scrape():
    """Main job — 6:30 AM IST daily."""
    from scraper.runner import scrape_portals
    from scraper.registry import enabled_keys
    from scraper.filter import filter_tenders
    from ai.matcher import parse_tender_with_ai
    from ai.scorer import calculate_match_score
    from whatsapp.sender import send_tender_alert, send_admin_report
    from database.connection import SessionLocal
    from database.models import Tender, Supplier, Alert, RunLog

    db = SessionLocal()
    stats = {"scraped": 0, "new": 0, "alerts_sent": 0, "errors": 0}

    # Create RunLog entry so we can track this run
    run_log = RunLog(job_name="daily_scrape", started_at=datetime.utcnow())
    db.add(run_log)
    db.commit()
    db.refresh(run_log)
    log.info("run_daily_scrape started (run_id=%s)", run_log.id)

    try:
        # Scrape all enabled portals via shared runner (handles playwright routing)
        portals = enabled_keys()
        log.info("Scraping portals: %s", portals)
        raw_tenders, portal_stats = await scrape_portals(portals)
        stats["errors"] += sum(1 for v in portal_stats.values() if isinstance(v, str))
        for portal, result in portal_stats.items():
            log.info("Portal %s: %s", portal, result)
        log.info("Total raw tenders: %d", len(raw_tenders))

        food_tenders = filter_tenders(raw_tenders)
        stats["scraped"] = len(food_tenders)

        for t_raw in food_tenders:
            # Skip already processed
            if db.query(Tender).filter(Tender.id == t_raw["id"]).first():
                continue

            try:
                ai_result = await parse_tender_with_ai(t_raw)

                # Skip if AI (or fallback) can't classify as food
                if ai_result["food_category"] in ("other", "other_food") \
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
                    tender_url=t_raw.get("tender_url", ""),
                    whatsapp_summary=ai_result["whatsapp_summary"],
                    ai_confidence=ai_result["confidence"],
                    red_flags=str(ai_result.get("red_flags", [])),
                )
                db.add(tender)

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

                # Commit each tender independently — a failure on one
                # must not roll back tenders already successfully saved.
                db.commit()
                stats["new"] += 1

            except Exception as e:
                log.error("Error processing tender %s: %s", t_raw.get("id"), e)
                stats["errors"] += 1
                try:
                    db.rollback()
                except Exception:
                    pass
                continue

    except Exception as e:
        log.error("Fatal scrape error: %s", e, exc_info=True)
        stats["errors"] += 1
    finally:
        # Persist run outcome
        try:
            run_log.finished_at = datetime.utcnow()
            run_log.status = "success" if stats["errors"] == 0 else "error"
            run_log.scraped = stats.get("scraped", 0)
            run_log.new_tenders = stats.get("new", 0)
            run_log.alerts_sent = stats.get("alerts_sent", 0)
            run_log.errors = stats.get("errors", 0)
            db.commit()
        except Exception as rl_e:
            log.error("RunLog update failed: %s", rl_e)

        log.info(
            "run_daily_scrape finished — scraped=%d new=%d alerts=%d errors=%d",
            stats["scraped"], stats["new"], stats["alerts_sent"], stats["errors"],
        )

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

    log.info("send_morning_prices started")
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
        log.info("send_morning_prices finished — sent to %d suppliers", len(suppliers))
    except Exception as e:
        log.error("send_morning_prices error: %s", e, exc_info=True)
    finally:
        db.close()


@scheduler.scheduled_job(CronTrigger(hour=9, minute=0))
async def send_daily_admin_report():
    """Send admin health report — 9:00 AM IST daily."""
    from api.health import get_daily_stats
    from whatsapp.sender import send_admin_report

    log.info("send_daily_admin_report started")
    admin_wa = os.getenv("ADMIN_WHATSAPP")
    if admin_wa:
        stats = get_daily_stats()
        await send_admin_report(admin_wa, stats)
        log.info("send_daily_admin_report finished")
    else:
        log.warning("ADMIN_WHATSAPP not set — skipping admin report")


if __name__ == "__main__":
    scheduler.start()
    log.info("BidMint scheduler started (IST timezone)")
    asyncio.get_event_loop().run_forever()


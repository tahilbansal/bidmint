"""
Manual scrape trigger endpoints.

POST /admin/scrape              — kick off a full scrape run in the background
GET  /admin/scrape/{job_id}     — poll status of a running / completed job
GET  /admin/scrape              — list recent jobs (last 20, from DB — survives restart)
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from admin.auth import require_admin_key

router = APIRouter(prefix="/scrape", tags=["Admin – Scrape"])
log = logging.getLogger("admin.scrape")

# In-memory cache for live progress during the current session.
# Keys are job_id (=str(run_log.id)), value is the latest job dict.
_live_jobs: dict[str, dict] = {}


def _job_from_run_log(rl) -> dict:
    """Convert a RunLog ORM row to the API job dict format."""
    debug = {}
    if rl.error_detail:
        try:
            debug = json.loads(rl.error_detail)
        except Exception:
            debug = {"raw_detail": rl.error_detail}
    return {
        "job_id": str(rl.id),
        "status": rl.status,
        "portals": debug.get("portals", []),
        "queued_at": debug.get("queued_at"),
        "started_at": rl.started_at.isoformat() if rl.started_at else None,
        "finished_at": rl.finished_at.isoformat() if rl.finished_at else None,
        "stats": {
            "raw_scraped": debug.get("raw_scraped", 0),
            "food_filtered": rl.scraped,
            "already_in_db": debug.get("already_in_db", 0),
            "ai_rejected": debug.get("ai_rejected", 0),
            "new_saved": rl.new_tenders,
            "alerts_sent": rl.alerts_sent,
            "errors": rl.errors,
        },
        "portal_results": debug.get("portal_results", {}),
        "error": debug.get("fatal_error"),
    }


# ── Background task ──────────────────────────────────────────────────────────

async def _run_scrape_job(job_id: str, portals: list[str]) -> None:
    from database.connection import SessionLocal
    from database.models import RunLog, Alert, Supplier, Tender

    db = SessionLocal()
    debug: dict = {"portals": portals, "portal_results": {}}

    # Mark as running
    try:
        rl = db.query(RunLog).filter(RunLog.id == job_id).first()
        if rl:
            rl.status = "running"
            db.commit()
    except Exception as e:
        log.error("RunLog status update failed: %s", e)

    _live_jobs[job_id]["status"] = "running"
    _live_jobs[job_id]["started_at"] = datetime.utcnow().isoformat()

    raw_scraped = 0
    food_filtered = 0
    already_in_db = 0
    ai_rejected = 0
    new_saved = 0
    alerts_sent = 0
    errors = 0
    error_msgs: list[str] = []

    try:
        from scraper.runner import scrape_portals
        from scraper.filter import filter_tenders
        from ai.matcher import parse_tender_with_ai
        from ai.scorer import calculate_match_score
        from whatsapp.sender import send_tender_alert

        raw_tenders, portal_stats = await scrape_portals(portals)
        for portal, result in portal_stats.items():
            debug["portal_results"][portal] = result
            if isinstance(result, str):
                errors += 1
                error_msgs.append(result)
                log.error("[job %s] %s", job_id, result)
            else:
                log.info("[job %s] %s: %d raw tenders", job_id, portal, result)

        raw_scraped = len(raw_tenders)
        debug["raw_scraped"] = raw_scraped
        log.info("[job %s] raw total: %d — running food filter", job_id, raw_scraped)
        _live_jobs[job_id]["stats"] = {"raw_scraped": raw_scraped, "status": "filtering"}

        food_tenders = filter_tenders(raw_tenders)
        food_filtered = len(food_tenders)
        debug["food_filtered"] = food_filtered
        log.info("[job %s] food filter: %d → %d", job_id, raw_scraped, food_filtered)

        if food_filtered == 0:
            log.warning("[job %s] 0 tenders passed food filter — nothing to save", job_id)

        min_score = int(os.getenv("MIN_MATCH_SCORE", "70"))

        for t_raw in food_tenders:
            if db.query(Tender).filter(Tender.id == t_raw["id"]).first():
                already_in_db += 1
                continue
            try:
                ai_result = await parse_tender_with_ai(t_raw)
                log.info(
                    "[job %s] AI: %s → category=%s confidence=%s",
                    job_id, t_raw.get("id"), ai_result["food_category"], ai_result["confidence"],
                )
                # Reject only when the fallback (or Claude) can't find any food category.
                # "other_food" is the rule-based fallback value for unrecognised items.
                if ai_result["food_category"] in ("other", "other_food") \
                        and ai_result["confidence"] == "LOW":
                    ai_rejected += 1
                    log.info("[job %s] AI rejected %s (category=%s)",
                             job_id, t_raw.get("id"), ai_result["food_category"])
                    continue

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
                db.flush()  # assign PK before adding alerts

                suppliers = db.query(Supplier).filter(Supplier.active == True).all()  # noqa: E712
                for supplier in suppliers:
                    score = calculate_match_score(supplier, tender, ai_result)
                    if score >= min_score:
                        sent = await send_tender_alert(supplier.whatsapp, tender)
                        if sent:
                            db.add(Alert(
                                supplier_id=supplier.id,
                                tender_id=tender.id,
                                match_score=score,
                            ))
                            tender.alerted_count += 1
                            alerts_sent += 1

                # Commit each tender individually so a failure on one never
                # rolls back tenders that were already successfully processed.
                db.commit()
                new_saved += 1
                log.info("[job %s] saved tender %s", job_id, tender.id)

            except Exception as e:
                msg = f"tender {t_raw.get('id')}: {e}"
                error_msgs.append(msg)
                errors += 1
                log.error("[job %s] %s", job_id, msg, exc_info=True)
                try:
                    db.rollback()
                except Exception:
                    pass

        log.info(
            "[job %s] done — raw=%d food=%d skip=%d ai_rej=%d new=%d alerts=%d err=%d",
            job_id, raw_scraped, food_filtered, already_in_db,
            ai_rejected, new_saved, alerts_sent, errors,
        )

    except Exception as e:
        msg = f"fatal: {e}"
        error_msgs.append(msg)
        errors += 1
        debug["fatal_error"] = msg
        log.error("[job %s] fatal error", job_id, exc_info=True)

    finally:
        debug.update({
            "raw_scraped": raw_scraped,
            "already_in_db": already_in_db,
            "ai_rejected": ai_rejected,
            "error_msgs": error_msgs[:20],  # cap stored errors
        })
        final_status = "success" if errors == 0 else ("failed" if new_saved == 0 else "partial")

        # Persist outcome to RunLog
        try:
            rl = db.query(RunLog).filter(RunLog.id == job_id).first()
            if rl:
                rl.status = final_status
                rl.finished_at = datetime.utcnow()
                rl.scraped = food_filtered
                rl.new_tenders = new_saved
                rl.alerts_sent = alerts_sent
                rl.errors = errors
                rl.error_detail = json.dumps(debug)
                db.commit()
        except Exception as e:
            log.error("[job %s] RunLog persist failed: %s", job_id, e)
        finally:
            db.close()

        # Update live cache
        _live_jobs[job_id].update({
            "status": final_status,
            "finished_at": datetime.utcnow().isoformat(),
            "stats": {
                "raw_scraped": raw_scraped,
                "food_filtered": food_filtered,
                "already_in_db": already_in_db,
                "ai_rejected": ai_rejected,
                "new_saved": new_saved,
                "alerts_sent": alerts_sent,
                "errors": errors,
            },
            "portal_results": debug.get("portal_results", {}),
            "error_msgs": error_msgs[:5],
        })


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", dependencies=[Depends(require_admin_key)], status_code=202)
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    portals: Optional[str] = None,
):
    """
    Kick off a manual scrape run in the background.
    Returns immediately with a job_id — poll GET /admin/scrape/{job_id} for status.

    - **portals**: comma-separated list, e.g. `gem,cppp`. Omit to use all active portals.
    """
    from admin.config_store import get_config
    from scraper.registry import enabled_keys
    from database.connection import SessionLocal
    from database.models import RunLog

    active_portals = [p.strip() for p in portals.split(",")] if portals else enabled_keys()

    db = SessionLocal()
    try:
        rl = RunLog(
            job_name="manual_scrape",
            started_at=datetime.utcnow(),
            status="queued",
            error_detail=json.dumps({
                "portals": active_portals,
                "queued_at": datetime.utcnow().isoformat(),
            }),
        )
        db.add(rl)
        db.commit()
        db.refresh(rl)
        job_id = str(rl.id)
    finally:
        db.close()

    _live_jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "portals": active_portals,
        "queued_at": datetime.utcnow().isoformat(),
    }
    background_tasks.add_task(_run_scrape_job, job_id, active_portals)
    log.info("Manual scrape queued — job_id=%s portals=%s", job_id, active_portals)
    return {
        "job_id": job_id,
        "portals": active_portals,
        "poll_url": f"/admin/scrape/{job_id}",
    }


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_jobs(limit: int = 20):
    """Return the last N scrape jobs, newest first. Reads from DB — survives restarts."""
    from database.connection import SessionLocal
    from database.models import RunLog

    db = SessionLocal()
    try:
        rows = (
            db.query(RunLog)
            .filter(RunLog.job_name == "manual_scrape")
            .order_by(RunLog.started_at.desc())
            .limit(limit)
            .all()
        )
        # Merge with live cache so in-progress jobs show real-time stats
        jobs = []
        for row in rows:
            jid = str(row.id)
            if jid in _live_jobs and _live_jobs[jid].get("status") in ("queued", "running"):
                jobs.append(_live_jobs[jid])
            else:
                jobs.append(_job_from_run_log(row))
        return {"jobs": jobs, "count": len(jobs)}
    finally:
        db.close()


@router.get("/{job_id}", dependencies=[Depends(require_admin_key)])
async def scrape_status(job_id: str):
    """Poll the status of a specific scrape job. Live data while running, DB data after restart."""
    # Return live data if available (has real-time progress counters)
    if job_id in _live_jobs:
        return _live_jobs[job_id]

    # Fall back to DB (job from a previous session)
    from database.connection import SessionLocal
    from database.models import RunLog

    db = SessionLocal()
    try:
        rl = db.query(RunLog).filter(RunLog.id == job_id).first()
        if not rl:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_from_run_log(rl)
    finally:
        db.close()


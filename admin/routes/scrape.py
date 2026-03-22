"""
Manual scrape trigger endpoints.

POST /admin/scrape              — kick off a full scrape run in the background
GET  /admin/scrape/{job_id}     — poll status of a running / completed job
GET  /admin/scrape              — list recent jobs (last 20)
"""
import os
import uuid
from collections import deque
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from admin.auth import require_admin_key

router = APIRouter(prefix="/scrape", tags=["Admin – Scrape"])

# In-memory job registry — resets on restart, last 20 jobs kept
_jobs: dict[str, dict] = {}
_job_order: deque = deque(maxlen=20)


# ── Background task ──────────────────────────────────────────────────────────

async def _run_scrape_job(job_id: str, portals: list[str]) -> None:
    _jobs[job_id].update({"status": "running", "started_at": datetime.utcnow().isoformat()})
    stats = {"scraped": 0, "new": 0, "alerts_sent": 0, "errors": 0}
    portal_results: dict = {}

    try:
        from scraper.gem_scraper import scrape_gem_tenders
        from scraper.cppp_scraper import scrape_cppp_tenders
        from scraper.punjab_scraper import scrape_punjab_tenders
        from scraper.filter import filter_tenders
        from ai.matcher import parse_tender_with_ai
        from ai.scorer import calculate_match_score
        from whatsapp.sender import send_tender_alert
        from database.connection import SessionLocal
        from database.models import Alert, Supplier, Tender

        raw_tenders: list = []

        if "gem" in portals:
            try:
                tenders = await scrape_gem_tenders()
                raw_tenders.extend(tenders)
                portal_results["gem"] = len(tenders)
            except Exception as e:
                portal_results["gem"] = f"error: {e}"
                stats["errors"] += 1

        if "cppp" in portals:
            try:
                tenders = await scrape_cppp_tenders()
                raw_tenders.extend(tenders)
                portal_results["cppp"] = len(tenders)
            except Exception as e:
                portal_results["cppp"] = f"error: {e}"
                stats["errors"] += 1

        if "punjab" in portals:
            try:
                tenders = await scrape_punjab_tenders()
                raw_tenders.extend(tenders)
                portal_results["punjab"] = len(tenders)
            except Exception as e:
                portal_results["punjab"] = f"error: {e}"
                stats["errors"] += 1

        food_tenders = filter_tenders(raw_tenders)
        stats["scraped"] = len(food_tenders)
        _jobs[job_id]["portal_results"] = portal_results

        db = SessionLocal()
        min_score = int(os.getenv("MIN_MATCH_SCORE", "70"))
        try:
            for t_raw in food_tenders:
                if db.query(Tender).filter(Tender.id == t_raw["id"]).first():
                    continue
                try:
                    ai_result = await parse_tender_with_ai(t_raw)
                    if ai_result["food_category"] == "other" and ai_result["confidence"] == "LOW":
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
                        whatsapp_summary=ai_result["whatsapp_summary"],
                        ai_confidence=ai_result["confidence"],
                        red_flags=str(ai_result.get("red_flags", [])),
                    )
                    db.add(tender)
                    stats["new"] += 1

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
                                stats["alerts_sent"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    print(f"[scrape job {job_id}] error on tender {t_raw.get('id')}: {e}")

            db.commit()
        finally:
            db.close()

        _jobs[job_id].update({
            "status": "done",
            "finished_at": datetime.utcnow().isoformat(),
            "stats": stats,
        })

    except Exception as e:
        _jobs[job_id].update({
            "status": "failed",
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(e),
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

    - **portals**: comma-separated list to override config, e.g. `gem,cppp`
                   Omit to use all portals from current /admin/config.
    """
    from admin.config_store import get_config
    active_portals = [p.strip() for p in portals.split(",")] if portals else get_config()["portals"]

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "portals": active_portals,
        "queued_at": datetime.utcnow().isoformat(),
    }
    _job_order.append(job_id)
    background_tasks.add_task(_run_scrape_job, job_id, active_portals)
    return {
        "job_id": job_id,
        "portals": active_portals,
        "poll_url": f"/admin/scrape/{job_id}",
    }


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_jobs():
    """Return the last 20 scrape jobs (most recent first)."""
    ordered = [_jobs[jid] for jid in reversed(_job_order) if jid in _jobs]
    return {"jobs": ordered}


@router.get("/{job_id}", dependencies=[Depends(require_admin_key)])
async def scrape_status(job_id: str):
    """Poll the status of a specific scrape job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]

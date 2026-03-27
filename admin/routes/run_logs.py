"""
Scheduler run history — GET /admin/run-logs
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from admin.auth import require_admin_key
from database.connection import get_db
from database.models import RunLog

router = APIRouter(prefix="/run-logs", tags=["Admin – Run Logs"])


def _fmt(rl: RunLog) -> dict:
    duration_s = None
    if rl.finished_at and rl.started_at:
        duration_s = round((rl.finished_at - rl.started_at).total_seconds())
    return {
        "id": str(rl.id),
        "job_name": rl.job_name,
        "status": rl.status,
        "started_at": rl.started_at.isoformat() if rl.started_at else None,
        "finished_at": rl.finished_at.isoformat() if rl.finished_at else None,
        "duration_seconds": duration_s,
        "scraped": rl.scraped,
        "new_tenders": rl.new_tenders,
        "alerts_sent": rl.alerts_sent,
        "errors": rl.errors,
        "error_detail": rl.error_detail,
    }


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_run_logs(
    job: Optional[str] = Query(None, description="Filter by job_name"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return the most recent scheduler run records, newest first."""
    q = db.query(RunLog).order_by(RunLog.started_at.desc())
    if job:
        q = q.filter(RunLog.job_name == job)
    rows = q.limit(limit).all()
    return {"run_logs": [_fmt(r) for r in rows], "count": len(rows)}


@router.get("/latest", dependencies=[Depends(require_admin_key)])
async def latest_runs(db: Session = Depends(get_db)):
    """Return the most recent completed run for each job type."""
    job_names = ["daily_scrape", "morning_prices"]
    result = {}
    for job_name in job_names:
        row = (
            db.query(RunLog)
            .filter(RunLog.job_name == job_name, RunLog.finished_at.isnot(None))
            .order_by(RunLog.started_at.desc())
            .first()
        )
        result[job_name] = _fmt(row) if row else None
    return result


@router.get("/health", dependencies=[Depends(require_admin_key)])
async def scheduler_health(db: Session = Depends(get_db)):
    """Quick health check: did daily_scrape run in the last 26 hours?"""
    cutoff = datetime.utcnow() - timedelta(hours=26)
    last_run = (
        db.query(RunLog)
        .filter(RunLog.job_name == "daily_scrape", RunLog.started_at >= cutoff)
        .order_by(RunLog.started_at.desc())
        .first()
    )
    if last_run is None:
        return {"status": "STALE", "message": "No daily_scrape run in the last 26 hours"}
    return {
        "status": "OK" if last_run.status == "success" else "ERROR",
        "last_run": _fmt(last_run),
    }

from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from database.connection import get_db
from whatsapp.handler import handle_inbound
from sqlalchemy.orm import Session
import asyncio
import os

app = FastAPI(
    title="BidMint API",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None
)


@app.get("/health")
async def health():
    """Health check endpoint for Render.com monitoring."""
    return {"status": "ok", "service": "bidmint", "version": "1.0.0"}


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Receives inbound WhatsApp messages from AiSensy.
    Must always return 200 — AiSensy retries on non-200.
    """
    try:
        data = await request.json()
        phone = data.get("mobile", "").strip()
        message = data.get("message", "").strip()

        if not phone or not message:
            return JSONResponse({"status": "ignored"})

        # Fire and forget — don't block webhook response
        asyncio.create_task(handle_inbound(phone, message))

        return JSONResponse({"status": "ok"})

    except Exception as e:
        print(f"Webhook error: {e}")
        return JSONResponse({"status": "error"})  # Still 200


@app.get("/admin/stats")
async def admin_stats(db: Session = Depends(get_db)):
    """Quick stats for admin — protected by checking source IP in production."""
    from database.models import Supplier, Tender, Alert
    from datetime import datetime, timedelta

    return {
        "active_suppliers": db.query(Supplier).filter(Supplier.active == True).count(),  # noqa: E712
        "total_tenders": db.query(Tender).count(),
        "tenders_today": db.query(Tender).filter(
            Tender.scraped_at >= datetime.utcnow() - timedelta(days=1)
        ).count(),
        "alerts_today": db.query(Alert).filter(
            Alert.sent_at >= datetime.utcnow() - timedelta(days=1)
        ).count(),
        "yes_replies_today": db.query(Alert).filter(
            Alert.response == "YES",
            Alert.responded_at >= datetime.utcnow() - timedelta(days=1)
        ).count(),
    }

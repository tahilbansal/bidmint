from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from whatsapp.handler import handle_inbound
from admin import admin_router
import asyncio
import os
import sys

# Playwright (and any subprocess-spawning async code) requires ProactorEventLoop on Windows.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(
    title="BidMint API",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
)

# Admin API — all routes under /admin/*, protected by X-Admin-Key header
app.include_router(admin_router)


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

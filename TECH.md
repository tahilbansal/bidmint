# Technical Implementation Guide
**BidMint Phase 1 — Developer Reference**
Version 1.0 | March 2026

---

## Table of Contents
1. [Repository Structure](#1-repository-structure)
2. [Setup Guide](#2-setup-guide)
3. [Core Modules](#3-core-modules)
4. [AI Layer](#4-ai-layer)
5. [WhatsApp Layer](#5-whatsapp-layer)
6. [Scheduler](#6-scheduler)
7. [API Server](#7-api-server)
8. [Database Migrations](#8-database-migrations)
9. [Testing](#9-testing)
10. [Deployment](#10-deployment)
11. [Phase 2 Preparation](#11-phase-2-preparation)

---

## 1. Repository Structure

```
bidmint/
├── scraper/
│   ├── __init__.py
│   ├── gem_scraper.py          # GeM portal Playwright scraper
│   ├── cppp_scraper.py         # CPPP portal scraper
│   ├── punjab_scraper.py       # Punjab state portal scraper
│   ├── agmarknet.py            # AGMARKNET mandi price fetcher
│   └── filter.py               # Keyword + location filter
├── ai/
│   ├── __init__.py
│   ├── matcher.py              # Claude API tender classifier
│   ├── scorer.py               # Match scoring engine
│   └── prompts.py              # All Claude prompt templates
├── whatsapp/
│   ├── __init__.py
│   ├── sender.py               # AiSensy outbound messages
│   ├── handler.py              # Inbound message parser + router
│   └── commands.py             # Command action implementations
├── database/
│   ├── __init__.py
│   ├── models.py               # SQLAlchemy ORM models
│   ├── connection.py           # DB connection + session factory
│   └── migrations/             # Alembic migration files
│       └── versions/
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app + webhook endpoint
│   └── health.py               # Health check + admin stats
├── tests/
│   ├── fixtures/               # Saved HTML from portals for offline testing
│   │   └── gem_sample.html
│   ├── test_scraper.py
│   ├── test_matcher.py
│   ├── test_scorer.py
│   └── test_handler.py
├── scripts/
│   └── add_supplier.py         # CLI to manually add pilot suppliers
├── .env.example
├── .gitignore
├── requirements.txt
├── alembic.ini
├── render.yaml
└── README.md
```

---

## 2. Setup Guide

### 2.1 Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | Use pyenv for version management |
| Git | Latest | |
| Supabase account | — | supabase.com — free |
| AiSensy account | — | aisensy.com — 14-day free trial |
| Anthropic API key | — | console.anthropic.com |

### 2.2 Local Development Setup

```bash
# 1. Clone repo
git clone git@github.com:yourusername/bidmint.git
cd bidmint

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# 3. Install all dependencies
pip install -r requirements.txt
playwright install chromium

# 4. Set up environment
cp .env.example .env
# Fill in your values in .env

# 5. Run database migrations
alembic upgrade head

# 6. Add first pilot supplier (your family's store)
python scripts/add_supplier.py

# 7. Test scraper in dry-run mode (no DB writes, no WhatsApp)
python -m scraper.gem_scraper --dry-run

# 8. Start API server
uvicorn api.main:app --reload --port 8000

# 9. Test webhook locally using ngrok
ngrok http 8000
# Copy ngrok URL → paste in AiSensy webhook settings
```

### 2.3 requirements.txt

```
# Web + API
fastapi==0.110.0
uvicorn[standard]==0.27.0
httpx==0.27.0
python-dotenv==1.0.0
pydantic==2.6.3
pydantic-settings==2.2.1

# Scraping
playwright==1.42.0
beautifulsoup4==4.12.3
tenacity==8.2.3

# Database
sqlalchemy==2.0.28
psycopg2-binary==2.9.9
alembic==1.13.1

# AI
anthropic==0.21.0

# Scheduling
apscheduler==3.10.4

# Testing
pytest==8.1.0
pytest-asyncio==0.23.5
pytest-mock==3.14.0
httpx==0.27.0
```

### 2.4 .env.example

```bash
# Database (from Supabase project settings → Database → Connection string)
DATABASE_URL=postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres

# AI (from console.anthropic.com)
ANTHROPIC_API_KEY=sk-ant-api03-...

# WhatsApp (from AiSensy dashboard → API)
AISENSY_API_KEY=...
AISENSY_CAMPAIGN_TENDER=tender_alert_v1
AISENSY_CAMPAIGN_PRICE=price_digest_v1

# App config
SCRAPER_RUN_HOUR=6
SCRAPER_RUN_MINUTE=30
MIN_MATCH_SCORE=70
ADMIN_WHATSAPP=919XXXXXXXXX    # Your WhatsApp for daily reports
ENVIRONMENT=development         # development | production
```

---

## 3. Core Modules

### 3.1 database/models.py

```python
from sqlalchemy import (
    Column, String, DateTime, Boolean,
    Text, Float, Integer, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

Base = declarative_base()


class Supplier(Base):
    __tablename__ = "suppliers"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    whatsapp   = Column(String(15), unique=True, nullable=False)  # 919XXXXXXXXX
    name       = Column(String(100), nullable=True)
    district   = Column(String(50), nullable=False)
    categories = Column(Text, nullable=False)  # "rice,wheat,pulses"
    active     = Column(Boolean, default=True)
    joined_at  = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)


class Tender(Base):
    __tablename__ = "tenders"

    id                = Column(String(50), primary_key=True)  # GeM bid number
    source            = Column(String(20))                    # gem|cppp|punjab_state
    title             = Column(Text)
    title_hindi       = Column(Text)
    department        = Column(String(200))
    location          = Column(String(100))
    category          = Column(String(50))
    quantity          = Column(String(100))
    quantity_kg       = Column(Float, nullable=True)
    deadline          = Column(DateTime, nullable=True)
    whatsapp_summary  = Column(Text)
    ai_confidence     = Column(String(10))                    # HIGH|MEDIUM|LOW
    red_flags         = Column(Text, default="[]")            # JSON array
    scraped_at        = Column(DateTime, default=datetime.utcnow)
    alerted_count     = Column(Integer, default=0)


class Alert(Base):
    __tablename__ = "alerts"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id   = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"))
    tender_id     = Column(String(50), ForeignKey("tenders.id"))
    match_score   = Column(Integer)
    sent_at       = Column(DateTime, default=datetime.utcnow)
    response      = Column(String(10), nullable=True)         # YES|NO|None
    responded_at  = Column(DateTime, nullable=True)


class PriceLog(Base):
    """Populated in Phase 2 — create table now to avoid migration pain."""
    __tablename__ = "price_logs"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commodity     = Column(String(50))
    mandi         = Column(String(100))
    price_modal   = Column(Float)
    price_min     = Column(Float)
    price_max     = Column(Float)
    recorded_date = Column(DateTime)
```

### 3.2 database/connection.py

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # Reconnect if connection dropped
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 3.3 scraper/filter.py

```python
FOOD_KEYWORDS = [
    "rice", "chawal", "basmati", "parboiled", "sella", "arwa",
    "wheat", "gehu", "gehun", "atta", "flour", "maida", "chakki",
    "dal", "pulses", "lentil", "moong", "chana", "masoor", "urad",
    "rajma", "arhar", "toor",
    "oil", "tel", "ghee", "vanaspati", "mustard", "sarson",
    "sunflower", "palm", "groundnut",
    "sugar", "cheeni", "gur", "jaggery", "shakkar",
    "milk", "doodh", "paneer", "curd", "butter", "dairy",
    "masala", "spices", "turmeric", "haldi", "mirch", "jeera",
    "dhania", "garam masala",
    "grocery", "ration", "provisions", "foodgrain", "kirana",
    "salt", "namak", "tea", "chai", "biscuit",
    "potato", "aloo", "onion", "pyaz", "tomato",
]

PUNJAB_KEYWORDS = [
    "punjab", "patiala", "ludhiana", "amritsar", "jalandhar",
    "chandigarh", "mohali", "bathinda", "pathankot", "hoshiarpur",
    "gurdaspur", "firozpur", "faridkot", "moga", "ropar", "barnala",
    "mansa", "fatehgarh", "tarn taran", "nawanshahr",
    # Adjacent states — suppliers can fulfil these too
    "haryana", "himachal", "hp", "j&k", "jammu",
]


def is_food_tender(tender: dict) -> bool:
    text = (tender.get("title", "") + " " + tender.get("department", "")).lower()
    return any(kw in text for kw in FOOD_KEYWORDS)


def is_punjab_tender(tender: dict) -> bool:
    location = tender.get("location", "").lower()
    department = tender.get("department", "").lower()
    return any(kw in location or kw in department for kw in PUNJAB_KEYWORDS)


def detect_category(tender: dict) -> str:
    title = tender.get("title", "").lower()
    if any(k in title for k in ["rice", "chawal", "basmati", "sella"]):
        return "rice"
    elif any(k in title for k in ["wheat", "gehu", "atta", "flour", "maida"]):
        return "wheat"
    elif any(k in title for k in ["dal", "pulse", "lentil", "moong", "chana", "masoor"]):
        return "pulses"
    elif any(k in title for k in ["oil", "tel", "ghee", "vanaspati"]):
        return "oils"
    elif any(k in title for k in ["sugar", "cheeni", "gur", "jaggery"]):
        return "sugar"
    elif any(k in title for k in ["milk", "doodh", "dairy", "paneer"]):
        return "dairy"
    elif any(k in title for k in ["masala", "spice", "turmeric", "haldi"]):
        return "spices"
    else:
        return "other_food"


def filter_tenders(tenders: list) -> list:
    filtered = [
        {**t, "category": detect_category(t)}
        for t in tenders
        if is_food_tender(t) and is_punjab_tender(t)
    ]
    print(f"Filter: {len(tenders)} total → {len(filtered)} Punjab food tenders")
    return filtered
```

---

## 4. AI Layer

### 4.1 ai/prompts.py

```python
TENDER_PARSE_PROMPT = """
You are a government tender analyst for Indian food procurement.
Extract structured data and generate a WhatsApp-ready Hindi summary.
Always respond in valid JSON only. No prose. No markdown fences.

Analyse this GeM tender and return JSON with exactly these keys:
{{
  "food_category": "rice|wheat|pulses|oil|sugar|dairy|spices|other",
  "item_name_hindi": "item name in Hindi/Devanagari script",
  "quantity_kg": <number in kg or null if unclear>,
  "fssai_required": true or false,
  "confidence": "HIGH|MEDIUM|LOW",
  "whatsapp_summary": "3-line Hindi summary, max 100 chars total",
  "red_flags": []
}}

Red flag values (include only if applicable):
- "unrealistic_deadline" — deadline within 3 days of posting
- "abnormal_quantity" — quantity > 500 tonnes for single MSME
- "vague_specs" — item description too vague to bid on

TENDER TITLE: {title}
DEPARTMENT: {department}
LOCATION: {location}
QUANTITY: {quantity}
"""
```

### 4.2 ai/matcher.py

```python
import anthropic
import json
import os
from ai.prompts import TENDER_PARSE_PROMPT
from scraper.filter import detect_category

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


async def parse_tender_with_ai(tender_raw: dict) -> dict:
    """
    Call Claude to extract structured food data from raw tender.
    Falls back to rule-based classification if API fails.
    Cost: ~1 API call = ~Rs 0.08 per tender at Sonnet pricing.
    """
    prompt = TENDER_PARSE_PROMPT.format(
        title=tender_raw.get("title", ""),
        department=tender_raw.get("department", ""),
        location=tender_raw.get("location", ""),
        quantity=tender_raw.get("quantity", "")
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        # Strip accidental markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        return result

    except json.JSONDecodeError as e:
        print(f"Claude returned invalid JSON: {e}. Using fallback.")
        return _rule_based_fallback(tender_raw)

    except anthropic.APIError as e:
        print(f"Anthropic API error: {e}. Using fallback.")
        return _rule_based_fallback(tender_raw)


def _rule_based_fallback(tender_raw: dict) -> dict:
    """Used when Claude API is unavailable. Lower quality but never fails."""
    category = detect_category(tender_raw)
    return {
        "food_category": category,
        "item_name_hindi": tender_raw.get("title", "")[:50],
        "quantity_kg": None,
        "fssai_required": False,
        "confidence": "LOW",
        "whatsapp_summary": tender_raw.get("title", "")[:100],
        "red_flags": []
    }
```

### 4.3 ai/scorer.py

```python
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
```

---

## 5. WhatsApp Layer

### 5.1 whatsapp/sender.py

```python
import httpx
import os
from database.models import Tender

AISENSY_URL = "https://backend.aisensy.com/campaign/t1/api/v2"
AISENSY_API_KEY = os.getenv("AISENSY_API_KEY")


async def send_tender_alert(whatsapp: str, tender: Tender) -> bool:
    """Send HSM template alert for new tender."""
    payload = {
        "apiKey": AISENSY_API_KEY,
        "campaignName": os.getenv("AISENSY_CAMPAIGN_TENDER"),
        "destination": whatsapp,
        "userName": "BidMint",
        "templateParams": [
            tender.location or "Punjab",
            tender.title_hindi or tender.title or "",
            tender.department or "",
            tender.quantity or "",
            str(tender.deadline.strftime("%d %b %Y") if tender.deadline else ""),
        ]
    }
    return await _post(payload)


async def send_tender_details(whatsapp: str, tender: Tender) -> bool:
    """Free-form session message with full tender details (after supplier replies YES)."""
    gem_link = f"https://bidplus.gem.gov.in/bidlists"
    message = (
        f"✅ *टेंडर की पूरी जानकारी*\n\n"
        f"📋 *आइटम:* {tender.title_hindi or tender.title}\n"
        f"🏢 *विभाग:* {tender.department}\n"
        f"📍 *जगह:* {tender.location}\n"
        f"📦 *मात्रा:* {tender.quantity}\n"
        f"⏰ *डेडलाइन:* {tender.deadline.strftime('%d %b %Y %I:%M %p') if tender.deadline else 'N/A'}\n"
        f"🔢 *GeM Bid No:* {tender.id}\n\n"
        f"GeM पर बोली लगाने के लिए:\n{gem_link}\n\n"
        f"कोई सवाल? *HELP* भेजें 🙏"
    )
    return await _send_session_message(whatsapp, message)


async def send_welcome(whatsapp: str, category: str, district: str) -> bool:
    message = (
        f"🙏 *BidMint में आपका स्वागत है!*\n\n"
        f"✅ रजिस्ट्रेशन हो गया\n"
        f"📦 Category: {category.upper()}\n"
        f"📍 District: {district.title()}\n\n"
        f"अब आपको रोज़ सुबह {category} के नए government tenders मिलेंगे।\n\n"
        f"Commands:\n"
        f"*YES* — टेंडर की पूरी जानकारी\n"
        f"*PRICE* — आज के मंडी भाव\n"
        f"*HELP* — सभी commands\n"
        f"*STOP* — बंद करें\n\n"
        f"पूरी तरह मुफ्त। आपका bid price कभी system में नहीं जाता। 🔒"
    )
    return await _send_session_message(whatsapp, message)


async def send_mandi_prices(whatsapp: str, categories: str, prices: dict) -> bool:
    lines = ["📊 *आज के मंडी भाव — Punjab*\n"]
    cats = [c.strip().lower() for c in categories.split(",")]
    for cat in cats:
        if cat in prices:
            p = prices[cat]
            change = p.get("change", 0)
            arrow = "🔺" if change > 0 else "🔻" if change < 0 else "➡️"
            lines.append(
                f"{arrow} *{cat.title()}:* ₹{p['modal']}/quintal "
                f"({'+'if change>0 else ''}{change:.0f} from yesterday)"
            )
    lines.append("\nSource: AGMARKNET (Govt of India)")
    return await _send_session_message(whatsapp, "\n".join(lines))


async def send_help_menu(whatsapp: str) -> bool:
    message = (
        "📋 *BidMint Commands*\n\n"
        "*JOIN <category> <district>*\n  रजिस्टर करें\n  Example: JOIN RICE PATIALA\n\n"
        "*YES* — टेंडर की पूरी जानकारी लें\n"
        "*NO* — इस टेंडर में रुचि नहीं\n"
        "*PRICE* — आज के मंडी भाव\n"
        "*ADD <category>* — नई category जोड़ें\n"
        "*STOP* — alerts बंद करें\n\n"
        "Support: contact@bidmint.in"
    )
    return await _send_session_message(whatsapp, message)


async def send_admin_report(whatsapp: str, stats: dict) -> bool:
    message = (
        f"📊 *BidMint Daily Report*\n\n"
        f"Scraped: {stats.get('scraped', 0)} tenders\n"
        f"New Punjab food: {stats.get('new', 0)}\n"
        f"Alerts sent: {stats.get('alerts_sent', 0)}\n"
        f"YES replies: {stats.get('yes', 0)}\n"
        f"Active suppliers: {stats.get('suppliers', 0)}\n"
        f"API cost: ₹{stats.get('api_cost_inr', 0):.0f}\n"
        f"Errors: {stats.get('errors', 0)}"
    )
    return await _send_session_message(whatsapp, message)


async def _send_session_message(whatsapp: str, message: str) -> bool:
    payload = {
        "apiKey": AISENSY_API_KEY,
        "campaignName": "session_reply",
        "destination": whatsapp,
        "userName": "BidMint",
        "source": "bidmint-backend",
        "message": message,
    }
    return await _post(payload)


async def _post(payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(AISENSY_URL, json=payload)
            success = resp.status_code == 200
            if not success:
                print(f"AiSensy error {resp.status_code}: {resp.text[:200]}")
            return success
    except Exception as e:
        print(f"AiSensy request failed: {e}")
        return False
```

### 5.2 whatsapp/handler.py

```python
from database.connection import SessionLocal
from database.models import Supplier, Alert, Tender
from whatsapp.sender import (
    send_tender_details, send_welcome,
    send_mandi_prices, send_help_menu
)
from scraper.agmarknet import fetch_punjab_prices
import uuid
from datetime import datetime


async def handle_inbound(phone: str, message: str):
    """
    Route inbound WhatsApp message to correct handler.
    phone: 919XXXXXXXXX format
    """
    msg = message.strip().upper()
    db = SessionLocal()

    try:
        if msg.startswith("JOIN"):
            await _handle_join(phone, msg, db)
        elif msg == "YES":
            await _handle_yes(phone, db)
        elif msg == "NO":
            await _handle_no(phone, db)
        elif msg == "PRICE":
            supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
            cats = supplier.categories if supplier else "rice,wheat"
            prices = await fetch_punjab_prices()
            await send_mandi_prices(phone, cats, prices)
        elif msg == "HELP":
            await send_help_menu(phone)
        elif msg == "STOP":
            await _handle_stop(phone, db)
        elif msg.startswith("ADD "):
            await _handle_add_category(phone, msg, db)
        else:
            await send_help_menu(phone)
    finally:
        db.close()


async def _handle_join(phone: str, msg: str, db):
    parts = msg.split()
    category = parts[1].lower() if len(parts) > 1 else "general"
    district = parts[2].lower() if len(parts) > 2 else "punjab"

    existing = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if existing:
        existing.categories = category
        existing.district = district
        existing.active = True
        existing.last_active = datetime.utcnow()
    else:
        db.add(Supplier(
            whatsapp=phone,
            categories=category,
            district=district
        ))
    db.commit()
    await send_welcome(phone, category, district)


async def _handle_yes(phone: str, db):
    # Most recent unanswered alert for this supplier
    alert = (
        db.query(Alert)
        .join(Supplier, Alert.supplier_id == Supplier.id)
        .filter(Supplier.whatsapp == phone)
        .filter(Alert.response == None)
        .order_by(Alert.sent_at.desc())
        .first()
    )
    if alert:
        alert.response = "YES"
        alert.responded_at = datetime.utcnow()
        db.commit()
        tender = db.query(Tender).filter(Tender.id == alert.tender_id).first()
        if tender:
            await send_tender_details(phone, tender)

    # Update last_active
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if supplier:
        supplier.last_active = datetime.utcnow()
        db.commit()


async def _handle_no(phone: str, db):
    alert = (
        db.query(Alert)
        .join(Supplier, Alert.supplier_id == Supplier.id)
        .filter(Supplier.whatsapp == phone)
        .filter(Alert.response == None)
        .order_by(Alert.sent_at.desc())
        .first()
    )
    if alert:
        alert.response = "NO"
        alert.responded_at = datetime.utcnow()
        db.commit()


async def _handle_stop(phone: str, db):
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if supplier:
        supplier.active = False
        db.commit()


async def _handle_add_category(phone: str, msg: str, db):
    parts = msg.split()
    if len(parts) < 2:
        return
    new_cat = parts[1].lower()
    supplier = db.query(Supplier).filter(Supplier.whatsapp == phone).first()
    if supplier:
        existing_cats = [c.strip() for c in supplier.categories.split(",")]
        if new_cat not in existing_cats:
            existing_cats.append(new_cat)
            supplier.categories = ",".join(existing_cats)
            db.commit()
```

---

## 6. Scheduler

### 6.1 scheduler.py

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import os

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


@scheduler.scheduled_job(CronTrigger(hour=6, minute=30))
async def run_daily_scrape():
    """Main job — 6:30 AM IST daily."""
    from scraper.gem_scraper import scrape_gem_tenders
    from scraper.filter import filter_tenders
    from ai.matcher import parse_tender_with_ai
    from ai.scorer import calculate_match_score
    from whatsapp.sender import send_tender_alert, send_admin_report
    from database.connection import SessionLocal
    from database.models import Tender, Supplier, Alert

    db = SessionLocal()
    stats = {"scraped": 0, "new": 0, "alerts_sent": 0, "errors": 0}

    try:
        raw_tenders = await scrape_gem_tenders()
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
                    .filter(Supplier.active == True).all()

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
            .filter(Supplier.active == True).all()
        for supplier in suppliers:
            await send_mandi_prices(
                supplier.whatsapp,
                supplier.categories,
                prices
            )
    finally:
        db.close()


if __name__ == "__main__":
    scheduler.start()
    print("BidMint scheduler running (IST timezone)... Ctrl+C to stop")
    asyncio.get_event_loop().run_forever()
```

---

## 7. API Server

### 7.1 api/main.py

```python
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from database.connection import get_db
from whatsapp.handler import handle_inbound
from sqlalchemy.orm import Session
import os

app = FastAPI(
    title="BidMint API",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None
)


@app.get("/health")
async def health():
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

        # Fire and forget — don't await in webhook
        import asyncio
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
        "active_suppliers": db.query(Supplier).filter(Supplier.active == True).count(),
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
```

---

## 8. Database Migrations

```bash
# Initialise Alembic (first time only)
alembic init database/migrations

# Create initial migration from models
alembic revision --autogenerate -m "initial schema"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# Check current version
alembic current
```

### alembic.ini (key setting)
```ini
sqlalchemy.url = %(DATABASE_URL)s
```

### database/migrations/env.py (add this)
```python
from database.models import Base
target_metadata = Base.metadata
```

---

## 9. Testing

### 9.1 Test Structure

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html

# Run fast tests only (no network)
pytest tests/ -v -m "not integration"

# Run specific file
pytest tests/test_scorer.py -v
```

### 9.2 Key Test: Scorer

```python
# tests/test_scorer.py
from ai.scorer import calculate_match_score
from database.models import Supplier, Tender


def test_exact_match_same_district():
    supplier = Supplier(district="patiala", categories="rice,wheat")
    tender = Tender(location="Patiala District Hospital", category="rice")
    ai = {"food_category": "rice", "confidence": "HIGH", "quantity_kg": 2000, "red_flags": []}
    score = calculate_match_score(supplier, tender, ai)
    assert score >= 80, f"Expected >= 80, got {score}"


def test_wrong_category_low_score():
    supplier = Supplier(district="patiala", categories="rice")
    tender = Tender(location="Patiala", category="construction")
    ai = {"food_category": "other", "confidence": "LOW", "quantity_kg": None, "red_flags": []}
    score = calculate_match_score(supplier, tender, ai)
    assert score < 30, f"Expected < 30, got {score}"


def test_red_flag_penalty():
    supplier = Supplier(district="patiala", categories="rice")
    tender = Tender(location="Patiala", category="rice")
    ai = {"food_category": "rice", "confidence": "HIGH",
          "quantity_kg": 2000, "red_flags": ["unrealistic_deadline", "vague_specs"]}
    score = calculate_match_score(supplier, tender, ai)
    # Should have penalty of 20 (2 flags × 10)
    base = 40 + 30 + 20 + 10  # Perfect score without flags = 100
    assert score == base - 20
```

### 9.3 Key Test: Handler

```python
# tests/test_handler.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_join_registers_new_supplier():
    with patch("whatsapp.handler.send_welcome", new_callable=AsyncMock) as mock_send:
        from whatsapp.handler import handle_inbound
        await handle_inbound("919876543210", "JOIN RICE PATIALA")
        mock_send.assert_called_once_with("919876543210", "rice", "patiala")


@pytest.mark.asyncio
async def test_unknown_command_sends_help():
    with patch("whatsapp.handler.send_help_menu", new_callable=AsyncMock) as mock_help:
        from whatsapp.handler import handle_inbound
        await handle_inbound("919876543210", "RANDOM STUFF")
        mock_help.assert_called_once()
```

---

## 10. Deployment

### 10.1 Post-Deployment Checklist

```
[ ] GET /health returns {"status": "ok"}
[ ] Send "HELP" to business WhatsApp number
[ ] Confirm webhook receives it (check Render logs)
[ ] Confirm HELP menu replies back in Hindi
[ ] Manually trigger scraper:
    python -c "
    import asyncio
    from scheduler import run_daily_scrape
    asyncio.run(run_daily_scrape())
    "
[ ] Check Supabase → tenders table has new rows
[ ] Check Supabase → alerts table has new rows
[ ] Confirm pilot supplier (your family) received WhatsApp alert
[ ] Confirm admin health report received at 9 AM
```

### 10.2 Useful Render CLI Commands

```bash
# Tail live logs
render logs --service bidmint-api --tail

# Trigger manual deploy
render deploy --service bidmint-api

# Check service status
render services list
```

---

## 11. Phase 2 Preparation

These are things to **keep in mind** during Phase 1 development — not to build yet, but to avoid costly refactoring later.

| Phase 2 Feature | Phase 1 Preparation |
|---|---|
| Bid document generation | Store `gem_url` in tenders table (add column now) |
| AGMARKNET price intelligence | `price_logs` table already created — just not populated |
| Web portal for Munim | Keep FastAPI endpoints RESTful and documented at `/docs` |
| Multiple portal sources | `source` column in tenders already distinguishes portals |
| Success fee payments | Add `razorpay_order_id VARCHAR(100) NULL` to alerts table |
| Hindi/Punjabi voice notes | No prep needed — add Whisper as new route in Phase 2 |
| pgvector semantic search | Supabase has pgvector — add `embedding VECTOR(1536)` to tenders later |

> **The Phase 1 principle:** Build it simple, build it correct, build it observable.
> Every line of Phase 1 code should be something you are proud to show a future co-founder or investor.

---

*Document Owner: Tahil | Repo: github.com/yourusername/bidmint | Last Updated: March 2026*

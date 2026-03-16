# System Design Document
**BidMint Phase 1 — Architecture & Design**
Version 1.0 | March 2026

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Component Design](#2-component-design)
3. [Database Design](#3-database-design)
4. [Deployment Architecture](#4-deployment-architecture)
5. [Error Handling & Observability](#5-error-handling--observability)

---

## 1. System Overview

BidMint Phase 1 is a four-component system: a daily scraping engine, an AI matching layer, a WhatsApp delivery layer, and a lightweight data store. All components run asynchronously and are designed to scale independently.

### 1.1 High-Level Architecture

```
[GeM Portal]  [CPPP Portal]  [Punjab eProcure]     [AGMARKNET]
      |              |               |                    |
      └──────────────┴───────────────┘                    |
                     |                                    |
           [Scraper Engine]                    [Price Engine]
           Playwright + httpx                  data.gov.in API
                     |                                    |
                     └──────────────┬─────────────────────┘
                                    |
                         [AI Matching Engine]
                         Claude API + Rule Filter
                                    |
                         [PostgreSQL — Supabase]
                         Single source of truth
                                    |
                         [FastAPI Webhook Server]
                         Render.com free tier
                                    |
                         [AiSensy WhatsApp Layer]
                         Official Meta BSP
                                    |
             [Supplier WhatsApp] ←→ [Reply Handler]
```

### 1.2 Data Flow Summary

```
6:30 AM  →  Scraper runs
6:50 AM  →  AI parses + scores new tenders
7:00 AM  →  WhatsApp alerts sent to matched suppliers
7:05 AM  →  Suppliers start replying YES/NO
8:00 AM  →  Daily mandi price digest sent to all suppliers
9:00 AM  →  Admin health report sent via WhatsApp
Ongoing  →  Webhook handles inbound replies in real time
```

---

## 2. Component Design

### 2.1 Scraper Engine

**Responsibilities:**
- Crawl GeM `bidplus.gem.gov.in` daily at 6:30 AM IST
- Crawl CPPP `eprocure.gov.in` for central government food tenders
- Parse HTML/JSON responses into structured tender objects
- Deduplicate against existing database records
- Write new tenders to PostgreSQL and trigger AI matching

**Technology Choices:**

| Component | Choice | Reason |
|---|---|---|
| Browser automation | Playwright (async) | Handles JS-heavy portals; GeM uses dynamic rendering |
| HTTP requests | httpx (async) | Fast, supports concurrent fetching |
| Scheduling | APScheduler | Lightweight, no Redis needed in Phase 1 |
| HTML parsing | BeautifulSoup4 | Simple, reliable for structured portal HTML |
| Retry logic | tenacity | Exponential backoff on portal timeouts |

**Scraper State Machine:**
```
IDLE → RUNNING → PARSING → FILTERING → SAVING → ALERTING → IDLE
         |
         └─ ERROR → RETRY (max 3x, exp backoff) → ALERT_ADMIN → IDLE
```

**Food Keyword Taxonomy:**

| Category | Primary Keywords | Secondary Keywords |
|---|---|---|
| Rice/Chawal | rice, chawal, basmati, parboiled | paddy, arwa, sella |
| Wheat/Gehu | wheat, gehu, atta, flour, maida | gehun, chakki, roti |
| Pulses/Dal | dal, pulses, lentil, moong, chana | masoor, urad, rajma, arhar |
| Oils/Tel | oil, tel, ghee, vanaspati | mustard, sarson, sunflower, palm |
| Sugar/Cheeni | sugar, cheeni, gur, jaggery | shakkar, mishri |
| Dairy | milk, doodh, paneer, curd, butter | dairy, skimmed, UHT |
| Spices | masala, spices, turmeric, haldi | mirch, jeera, dhania |
| Provisions | grocery, ration, provisions, FMCG | kirana, store items, dry goods |

---

### 2.2 AI Matching Engine

**Design Philosophy:**
Hybrid approach — fast rule-based pre-filtering followed by Claude API for semantic understanding. Keeps API costs low while ensuring high matching quality.

**Matching Pipeline:**
```
New Tender
    ↓
STEP 1: Rule Filter (free, instant)
  — Is it in food keyword list?        → No  → DISCARD
  — Is location Punjab/North India?    → No  → DISCARD
    ↓
STEP 2: Claude AI Parse (1 API call per new tender)
  — Extract: exact item, unit, quantity, FSSAI requirement
  — Classify confidence: HIGH / MEDIUM / LOW
  — Generate 3-line Hindi summary for WhatsApp
    ↓
STEP 3: Supplier Matching (database query)
  — Match category to supplier.categories
  — Match district within 100km radius
  — Calculate final match score (0–100)
    ↓
STEP 4: Alert Decision
  — Score ≥ 80  →  Send immediately
  — Score 60–79 →  Batch with low-priority tag
  — Score < 60  →  Discard silently
```

**Claude API Prompt:**
```
SYSTEM:
You are a government tender analyst for Indian food procurement.
Extract structured data and generate a WhatsApp-ready Hindi summary.
Always respond in valid JSON only. No prose. No markdown fences.

USER:
Analyse this GeM tender and return JSON:
{
  "food_category": "rice|wheat|pulses|oil|sugar|dairy|spices|other",
  "item_name_hindi": "...",
  "quantity_kg": <number or null>,
  "fssai_required": true|false,
  "confidence": "HIGH|MEDIUM|LOW",
  "whatsapp_summary": "3-line Hindi summary max 100 chars total",
  "red_flags": ["unrealistic_deadline"|"abnormal_quantity"] or []
}

TENDER TITLE: {{title}}
DEPARTMENT: {{department}}
LOCATION: {{location}}
QUANTITY: {{quantity}}
```

**Match Scoring Algorithm:**

| Factor | Weight | Scoring Logic |
|---|---|---|
| Category match | 40% | Exact = 40, Broad = 25, None = 0 |
| Location match | 30% | Same district = 30, Adjacent = 20, Same state = 10 |
| AI confidence | 20% | HIGH = 20, MEDIUM = 12, LOW = 5 |
| Quantity feasibility | 10% | Within MSME capacity = 10, Unknown = 5 |
| Red flag penalty | -10 per flag | Deducted from total |

**Final score:** `max(0, min(100, sum_of_above))`

---

### 2.3 WhatsApp Interface Design

**Message Flow:**

| Trigger | Direction | Content | AiSensy Type |
|---|---|---|---|
| New tender matched | Outbound | Template: `tender_alert_v1` | HSM Template |
| Supplier replies YES | Outbound | Full tender details + GeM link | Session message |
| Supplier replies NO | Outbound | Acknowledgement | Session message |
| JOIN received | Outbound | Welcome + categories confirmed | Session message |
| PRICE command | Outbound | Today's mandi prices | Session message |
| HELP command | Outbound | Commands list in Hindi | Session message |
| Daily 8 AM digest | Outbound | Mandi prices + open tender count | HSM Template |

**WhatsApp Template — `tender_alert_v1`:**
```
🌾 *नया फूड टेंडर — {{district}}*

📋 {{item_hindi}}
🏢 {{department}}
📦 मात्रा: {{quantity}}
⏰ अंतिम तारीख: {{deadline}}

रुचि है? *YES* भेजें
नहीं चाहिए? *NO* भेजें
```

**Command Parser:**

| Command Pattern | Action | Example |
|---|---|---|
| `JOIN <category> <district>` | Register new supplier | `JOIN RICE PATIALA` |
| `YES` | Send full tender details | `YES` |
| `NO` | Log decline, suppress 7 days | `NO` |
| `PRICE` | Send mandi prices | `PRICE` |
| `HELP` | Send command list in Hindi | `HELP` |
| `ADD <category>` | Add product category | `ADD WHEAT` |
| `REMOVE <category>` | Remove product category | `REMOVE OIL` |
| `STOP` | Unsubscribe completely | `STOP` |

---

## 3. Database Design

**Platform:** PostgreSQL on Supabase (free tier: 500MB, sufficient for Phase 1 with ~10,000 tenders/month)

### Table: `suppliers`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | Auto-generated |
| `whatsapp` | VARCHAR(15) UNIQUE | Format: `919XXXXXXXXX` |
| `name` | VARCHAR(100) | Optional — added via PROFILE command |
| `district` | VARCHAR(50) | patiala, ludhiana, amritsar, etc. |
| `categories` | TEXT | Comma-separated: `rice,wheat,pulses` |
| `active` | BOOLEAN DEFAULT TRUE | False = STOP received |
| `joined_at` | TIMESTAMP | Auto set on insert |
| `last_active` | TIMESTAMP | Updated on any inbound message |

### Table: `tenders`

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR(50) PRIMARY KEY | GeM bid number |
| `source` | VARCHAR(20) | `gem` \| `cppp` \| `punjab_state` |
| `title` | TEXT | Raw title from portal |
| `title_hindi` | TEXT | AI-generated Hindi title |
| `department` | VARCHAR(200) | Buying organisation |
| `location` | VARCHAR(100) | State / district |
| `category` | VARCHAR(50) | AI-classified food category |
| `quantity` | VARCHAR(100) | Raw quantity string |
| `quantity_kg` | FLOAT | Normalised kg (AI extracted) |
| `deadline` | TIMESTAMP | Bid closing datetime |
| `whatsapp_summary` | TEXT | AI-generated 3-line Hindi summary |
| `ai_confidence` | VARCHAR(10) | `HIGH` \| `MEDIUM` \| `LOW` |
| `red_flags` | TEXT | JSON array of flag strings |
| `scraped_at` | TIMESTAMP | When first scraped |
| `alerted_count` | INTEGER DEFAULT 0 | How many suppliers alerted |

### Table: `alerts`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | |
| `supplier_id` | UUID FK → suppliers | |
| `tender_id` | VARCHAR FK → tenders | |
| `match_score` | INTEGER | 0–100 |
| `sent_at` | TIMESTAMP | |
| `response` | VARCHAR(10) | `YES` \| `NO` \| NULL |
| `responded_at` | TIMESTAMP | NULL until replied |

### Table: `price_logs` *(populate in Phase 2, create now)*

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PRIMARY KEY | |
| `commodity` | VARCHAR(50) | rice, wheat, etc. |
| `mandi` | VARCHAR(100) | Patiala, Ludhiana, etc. |
| `price_modal` | FLOAT | Modal price from AGMARKNET |
| `price_min` | FLOAT | |
| `price_max` | FLOAT | |
| `recorded_date` | DATE | |

### Key Indexes

```sql
-- Speed up supplier matching by district
CREATE INDEX idx_suppliers_district ON suppliers(district);
CREATE INDEX idx_suppliers_active ON suppliers(active);

-- Speed up tender lookups
CREATE INDEX idx_tenders_category ON tenders(category);
CREATE INDEX idx_tenders_deadline ON tenders(deadline);
CREATE INDEX idx_tenders_scraped_at ON tenders(scraped_at);

-- Speed up alert lookups (most frequent query)
CREATE INDEX idx_alerts_supplier_id ON alerts(supplier_id);
CREATE INDEX idx_alerts_response ON alerts(response);
```

---

## 4. Deployment Architecture

### 4.1 Infrastructure (Phase 1 — Minimal Cost)

| Component | Service | Tier | Monthly Cost |
|---|---|---|---|
| Backend API + Webhook | Render.com | Free (512MB RAM) | ₹0 |
| Background Scheduler | Render Worker | Free | ₹0 |
| Database | Supabase | Free (500MB) | ₹0 |
| WhatsApp API | AiSensy | Starter | ₹999 |
| Claude API | Anthropic | Pay per use ~500 calls/day | ~₹800 |
| AGMARKNET Data | data.gov.in | Free API | ₹0 |
| **Total** | | | **~₹1,800/month** |

### 4.2 render.yaml

```yaml
services:
  - type: web
    name: bidmint-api
    runtime: python
    buildCommand: pip install -r requirements.txt && playwright install chromium
    startCommand: uvicorn api.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: AISENSY_API_KEY
        sync: false

  - type: worker
    name: bidmint-scheduler
    runtime: python
    buildCommand: pip install -r requirements.txt && playwright install chromium
    startCommand: python scheduler.py
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: AISENSY_API_KEY
        sync: false
```

### 4.3 Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/bidmint

# AI
ANTHROPIC_API_KEY=sk-ant-...

# WhatsApp
AISENSY_API_KEY=...
AISENSY_CAMPAIGN_TENDER=tender_alert_v1
AISENSY_CAMPAIGN_PRICE=price_digest_v1

# Config
SCRAPER_RUN_HOUR=6
SCRAPER_RUN_MINUTE=30
MIN_MATCH_SCORE=70
ADMIN_WHATSAPP=919XXXXXXXXX
ENVIRONMENT=production
```

---

## 5. Error Handling & Observability

### 5.1 Error Matrix

| Scenario | Handling |
|---|---|
| GeM portal down | Retry 3x with 5-min backoff; log failure; skip day gracefully |
| Claude API timeout | Fall back to rule-based classification; flag for manual review |
| AiSensy rate limit | Queue messages; send in batches of 10 with 1s delay |
| Duplicate tender | Check id uniqueness before insert; upsert on conflict |
| Invalid WhatsApp reply | Log unrecognised input; send HELP message back |
| Database connection fail | Retry 3x; alert admin via WhatsApp; halt job |
| Playwright browser crash | Restart browser context; retry current page |

### 5.2 Daily Admin Health Report

Sent to admin WhatsApp at 9:00 AM IST every day:

```
📊 BidMint Daily Report — 16 March 2026

Scraped:       847 tenders (GeM: 720, CPPP: 127)
Punjab food:   34 new matches
Alerts sent:   89 (34 tenders × avg 2.6 suppliers)
YES replies:   41  (46%)
NO replies:    22  (25%)
No response:   26  (29%)
Active suppliers: 18
API cost today:  ₹42
Errors: None ✅
```

### 5.3 Monitoring Checklist (Manual — Phase 1)

Check these daily until automated monitoring is added:

- [ ] Supabase dashboard — tenders table row count increasing daily
- [ ] Render logs — no ERROR lines in scheduler
- [ ] AiSensy dashboard — messages delivered (not failed)
- [ ] Admin WhatsApp — health report received at 9 AM
- [ ] Test: send `PRICE` to business number — confirm response

---

*Document Owner: Tahil | Last Updated: March 2026 | Repo: github.com/yourusername/bidmint*

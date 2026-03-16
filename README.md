# BidMint 🌾

> AI-powered WhatsApp-first platform for food & agricultural wholesale suppliers in Punjab to discover and win government tenders.

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green)](https://fastapi.tiangolo.com)
[![Claude AI](https://img.shields.io/badge/AI-Claude%20Sonnet-orange)](https://anthropic.com)
[![WhatsApp](https://img.shields.io/badge/WhatsApp-AiSensy-brightgreen)](https://aisensy.com)

---

## What It Does

Punjab wholesale food suppliers miss 60–70% of government tenders because discovery is manual, agents are untrustworthy, and bid preparation takes days.

BidMint solves this on WhatsApp — the one tool every munim (bookkeeper) already uses:

```
Supplier texts: JOIN RICE PATIALA
System:         ✅ Registered. You'll get rice tenders in Patiala daily.

7:05 AM:        🌾 New Tender — Patiala District Hospital
                Rice (Basmati) — 2,000 kg
                Deadline: 24 March 2026
                Reply YES for details

Supplier:       YES

System:         Full details + GeM link sent instantly
```

---

## Documentation

| Document | Description |
|---|---|
| [PRD.md](./PRD.md) | Product Requirements — what we're building and why |
| [DESIGN.md](./DESIGN.md) | System Design — architecture, components, database |
| [TECH.md](./TECH.md) | Technical Guide — setup, all code, deployment |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.11) |
| AI Matching | Claude Sonnet API |
| WhatsApp | AiSensy (Meta BSP) |
| Database | PostgreSQL via Supabase |
| Scraping | Playwright + BeautifulSoup4 |
| Hosting | Render.com |
| Scheduling | APScheduler |

**Monthly infra cost: ~₹1,800 (< $22)**

---

## Quick Start

```bash
git clone git@github.com:yourusername/bidmint.git
cd bidmint
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in your keys
alembic upgrade head
python scripts/add_supplier.py
uvicorn api.main:app --reload
```

See [TECH.md](./TECH.md) for full setup guide.

---

## Phase Roadmap

- **Phase 1** ✅ *(current)* — Tender scraping + AI matching + WhatsApp alerts
- **Phase 2** 🔜 — Bid document generation + price intelligence + Munim portal
- **Phase 3** 📅 — Mobile app + success fee model + Haryana expansion
- **Phase 4** 📅 — Full platform + pharma/FMCG verticals + Series A

---

## License

Private — All rights reserved © 2026 BidMint

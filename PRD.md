# Product Requirements Document
**BidMint — AI Smart Food Procurement Platform**
Version 1.0 | March 2026 | Status: Active Development

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Product Vision & Goals](#2-product-vision--goals)
3. [Target Users](#3-target-users)
4. [User Stories & Acceptance Criteria](#4-user-stories--acceptance-criteria)
5. [Functional Requirements](#5-functional-requirements)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [Success Metrics](#7-success-metrics)
8. [Go-To-Market Plan](#8-go-to-market-plan-punjab)

---

## 1. Executive Summary

BidMint is an AI-powered WhatsApp-first platform that helps food and agricultural wholesale suppliers in Punjab discover government tenders, receive intelligent bid recommendations, and win more contracts — without changing how they already work.

Phase 1 focuses on automated tender discovery, AI-based matching, and WhatsApp delivery. The product is designed around the **Munim** (bookkeeper) as the primary user and the wholesale business owner as the decision-maker.

> **Problem Statement**
>
> Punjab wholesale food suppliers miss 60–70% of government tenders because:
> - Tender discovery is completely manual across 30+ government portals
> - No trusted digital tool exists — existing agents are opaque and potentially fraudulent
> - Bid preparation is time-consuming, often taking 2–3 days per tender

---

## 2. Product Vision & Goals

### 2.1 Vision Statement

> *"Every food supplier in Punjab wins more government contracts — automatically, trustworthily, and in the language they speak."*

### 2.2 Phase 1 Goals

| Goal | Metric | Target (Month 3) |
|---|---|---|
| Tender Discovery | Punjab food tenders scraped daily | 100% of GeM + CPPP listings |
| AI Matching Accuracy | % relevant tenders per supplier | > 85% relevance score |
| WhatsApp Delivery | Alerts sent within hours of posting | < 4 hours lag |
| Supplier Onboarding | Suppliers onboarded | 20 suppliers by Month 2 |
| Engagement Rate | YES replies to alerts | > 40% reply rate |
| Trust Metric | Suppliers retained after 30 days | > 80% retention |

### 2.3 Non-Goals for Phase 1

- Bid document generation *(Phase 2)*
- Price intelligence dashboard *(Phase 2)*
- Mobile app *(Phase 3)*
- Subscription payments *(Phase 2+)*
- Expansion beyond Punjab *(Phase 2+)*

---

## 3. Target Users

### 3.1 Primary User: The Munim (Bookkeeper)

| Attribute | Detail |
|---|---|
| Role | Bookkeeper / accountant in wholesale business |
| Age | 25–45 years |
| Tech comfort | WhatsApp daily, basic Tally, phone calls |
| Language | Punjabi / Hindi primarily, limited English |
| Device | Android smartphone, mid-range |
| Pain point | Tracks tenders manually, misses deadlines, no price guidance |
| Motivation | Make seth (owner) happy, reduce manual work |

### 3.2 Secondary User: The Owner (Seth)

| Attribute | Detail |
|---|---|
| Role | Wholesale business owner, decision-maker |
| Tech comfort | WhatsApp only, skeptical of new tools |
| Language | Punjabi, Hindi |
| Trust concern | Pricing data privacy — key barrier to adoption |
| Motivation | Win more government contracts, grow revenue |

### 3.3 The Munim as Trust Bridge

```
WITHOUT MUNIM:
Startup → Owner: "Share your pricing data"
Owner: "Why should I trust you?" ❌

WITH MUNIM:
Startup → Munim: "Help us help your seth win more tenders"
Munim → Owner: "Seth ji, yeh tool sahi lagta hai"
Owner: "Munim kehta hai toh theek hoga" ✅
```

---

## 4. User Stories & Acceptance Criteria

### US-01 — Supplier Onboarding

**As a Munim**, I want to register on WhatsApp in under 2 minutes so that I can start receiving relevant tender alerts without filling lengthy forms.

**Acceptance Criteria:**
- Munim texts `JOIN RICE PATIALA` to the business number
- System auto-registers supplier with category and district
- Confirmation message sent within 30 seconds in Hindi
- No app download required, no web form to fill

---

### US-02 — Tender Alert

**As a Munim**, I want to receive WhatsApp alerts for relevant food tenders in my district so I never miss a government contract opportunity.

**Acceptance Criteria:**
- Alert received within 4 hours of tender posting on GeM
- Alert contains: item, department, district, quantity, deadline, bid number
- Alert is in Hindi with Punjabi terms where relevant
- Supplier can reply `YES` (want details) or `NO` (not interested)

---

### US-03 — AI Tender Matching

**As a supplier**, I want AI to match tenders to my specific products and location so I only receive tenders I can actually bid on.

**Acceptance Criteria:**
- Match score > 85% precision — irrelevant tenders not sent
- AI considers: product category, quantity feasibility, district proximity
- Supplier can update categories anytime via WhatsApp command

---

### US-04 — Daily Price Alert

**As a Munim**, I want a daily WhatsApp message with mandi prices for my products so I know if market rates have moved.

**Acceptance Criteria:**
- Daily 8 AM message with Punjab mandi prices for subscribed categories
- Shows today vs yesterday price change with up/down indicator
- Data sourced from AGMARKNET (official government mandi data)

---

### US-05 — Trust & Privacy

**As an owner (seth)**, I want to know my pricing data never leaves my device so I can trust the platform with sensitive business information.

**Acceptance Criteria:**
- System never requests or stores bid prices
- Platform only stores: product categories, district, WhatsApp number
- Privacy policy in Hindi available on request
- One-page agreement signed before onboarding large suppliers

---

## 5. Functional Requirements

### 5.1 Tender Scraping Engine

| Req ID | Requirement | Priority |
|---|---|---|
| FR-01 | Scrape GeM bidplus portal daily at 6:30 AM IST | P0 |
| FR-02 | Scrape CPPP eprocure.gov.in for central tenders | P0 |
| FR-03 | Scrape Punjab state e-procurement portal | P1 |
| FR-04 | Filter tenders by 30+ food/agri keywords | P0 |
| FR-05 | Filter tenders by Punjab + adjacent state locations | P0 |
| FR-06 | Deduplicate tenders across portals and runs | P0 |
| FR-07 | Store raw tender data + parsed fields in PostgreSQL | P0 |
| FR-08 | Retry failed scrapes with exponential backoff | P1 |

### 5.2 AI Matching Engine

| Req ID | Requirement | Priority |
|---|---|---|
| FR-09 | Claude API to parse tender title — extract food category, qty, unit | P0 |
| FR-10 | Match tender category to supplier product list | P0 |
| FR-11 | Match tender location to supplier district + 100km radius | P0 |
| FR-12 | Generate match confidence score 0–100 per tender-supplier pair | P0 |
| FR-13 | Only alert if match score > 70 | P0 |
| FR-14 | Claude to generate Hindi summary of tender in 3 lines | P0 |
| FR-15 | AI to flag tenders with unusual quantity or unrealistic deadlines | P1 |

### 5.3 WhatsApp Interface

| Req ID | Requirement | Priority |
|---|---|---|
| FR-16 | Send tender alert via AiSensy template message | P0 |
| FR-17 | Handle YES reply — send full tender details as free-form message | P0 |
| FR-18 | Handle NO reply — log and suppress similar tenders for 7 days | P1 |
| FR-19 | Handle JOIN command for new supplier self-registration | P0 |
| FR-20 | Handle STOP command to unsubscribe immediately | P0 |
| FR-21 | Handle HELP command — send supported commands list in Hindi | P1 |
| FR-22 | Handle PRICE command — send today's mandi prices | P1 |
| FR-23 | Inbound webhook to receive and parse supplier replies | P0 |

### 5.4 Supplier Management

| Req ID | Requirement | Priority |
|---|---|---|
| FR-24 | Store supplier profile: name, WhatsApp, district, categories | P0 |
| FR-25 | Allow category update via WhatsApp: `ADD WHEAT` | P1 |
| FR-26 | Track alert history per supplier | P0 |
| FR-27 | Track YES/NO responses per alert | P0 |
| FR-28 | Auto-deactivate suppliers after 30 days of no response | P2 |

---

## 6. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Performance | Scraper completes full GeM scan in < 30 minutes |
| Performance | WhatsApp alert sent within 10 seconds of job completion |
| Reliability | 99.5% uptime for webhook endpoint |
| Scalability | Architecture supports 1,000 suppliers without code changes |
| Security | No bid prices or sensitive financial data stored anywhere |
| Privacy | Supplier WhatsApp numbers encrypted at rest in database |
| Language | All user-facing messages in Hindi/Punjabi, not English |
| Cost | Total infra cost < ₹3,000/month at 50 suppliers |
| Observability | Daily summary log: tenders scraped, matched, alerts sent, responses |

---

## 7. Success Metrics

| Metric | Week 2 | Month 1 | Month 3 |
|---|---|---|---|
| Suppliers onboarded | 3 (pilot) | 10 | 25 |
| Tenders scraped/day | 50+ | 100+ | 200+ |
| Match accuracy | > 70% | > 80% | > 85% |
| Alert YES reply rate | > 30% | > 40% | > 45% |
| Supplier retention (30 days) | N/A | > 75% | > 80% |
| Infra cost/month | < ₹1,000 | < ₹2,000 | < ₹3,000 |

---

## 8. Go-To-Market Plan (Punjab)

Phase 1 GTM is entirely relationship-driven. No paid marketing. No cold outreach.

### Week 1–2: Patiala Pilot
- Onboard family wholesale business as Supplier #1
- Father introduces to 3–4 trusted mandi contacts personally
- Position: *"Free trial — no payment, no forms, just WhatsApp"*

### Week 3–4: Patiala Anaj Mandi
- Visit grain market in person — talk to 20 suppliers
- Do not pitch technology — ask about tender pain points first
- Offer free WhatsApp registration on the spot

### Month 2: Ludhiana + Amritsar
- One supplier who wins a tender = your case study in Punjabi
- Share the win story at next mandi visit
- Expand using Patiala supplier references

### Trust Messaging (all conversations)

> *"Tumhara bid price system mein kabhi nahi jaata.*
> *Hum sirf tender alert dete hain — baki sab tumhara."*
>
> *(Your bid price never goes into the system.*
> *We only give tender alerts — everything else is yours.)*

---

*Document Owner: Tahil | Last Updated: March 2026 | Next Review: Phase 2 kickoff*

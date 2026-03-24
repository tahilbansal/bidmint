import asyncio
import httpx
import os
from dotenv import load_dotenv
from database.models import Tender

load_dotenv()

AISENSY_CAMPAIGN_URL = "https://backend.aisensy.com/campaign/t1/api/v2"   # Template campaigns
AISENSY_DIRECT_URL   = "https://backend.aisensy.com/campaign/t1/api/v2"   # Session messages (same endpoint, different payload)
AISENSY_API_KEY = os.getenv("AISENSY_API_KEY")


def _p(val: str | None, fallback: str = "—") -> str:
    """Return stripped value or fallback — ensures no empty/whitespace templateParam."""
    return (val or "").strip() or fallback


async def send_tender_alert(whatsapp: str, tender: Tender) -> bool:
    """
    Send a tender recommendation via the tender_alert_v1 HSM template campaign.

    Template params passed to AiSensy:
      {{1}} location      {{2}} item (Hindi)    {{3}} department
      {{4}} quantity      {{5}} deadline

    Retries up to 2 times on failure.
    """
    deadline_str = tender.deadline.strftime("%d %b %Y") if tender.deadline else "जल्द बंद"
    title = _p(tender.title_hindi or tender.title)
    params = [
        _p(tender.location, "Punjab"),
        title,
        _p(tender.department),
        _p(tender.quantity),
        deadline_str,
    ]
    payload = {
        "apiKey": AISENSY_API_KEY,
        "campaignName": os.getenv("AISENSY_CAMPAIGN_TENDER", "tender_alert_v1"),
        "destination": whatsapp,
        "userName": "BidMint",
        "templateParams": params,
    }

    for attempt in range(1, 4):  # up to 3 attempts (2 retries)
        success = await _post(AISENSY_CAMPAIGN_URL, payload)
        if success:
            print(f"          📤 Alert sent → {whatsapp} (attempt {attempt})")
            print(f"             Item    : {title[:60]}")
            print(f"             Location: {_p(tender.location, 'Punjab')}")
            print(f"             Qty     : {_p(tender.quantity)}  Deadline: {deadline_str}")
            return True
        if attempt < 3:
            print(f"          ↩️  Retry {attempt}/2 for {whatsapp}...")
            await asyncio.sleep(2)

    return False


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
    """Send welcome message after supplier registration."""
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
    """Send daily mandi price digest to supplier."""
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
    """Send list of supported commands in Hindi."""
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
    """Send daily health report to admin."""
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
    """
    Send a free-form (session) message via AiSensy.
    Requires the recipient to have messaged your business number in the last 24h.
    Uses the 'session_reply' campaignName — create this in AiSensy as an API campaign
    with a single-variable template body {{1}} so the message text is passed as templateParams[0].
    """
    payload = {
        "apiKey": AISENSY_API_KEY,
        "campaignName": os.getenv("AISENSY_CAMPAIGN_SESSION", "session_reply"),
        "destination": whatsapp,
        "userName": "BidMint",
        "source": "bidmint-backend",
        "templateParams": [message],
    }
    ok = await _post(AISENSY_CAMPAIGN_URL, payload)
    if not ok:
        # session_reply campaign does not exist yet in AiSensy.
        # Go to AiSensy → Campaigns → Create API Campaign → name "session_reply"
        # Template body: {{1}}   (single variable, passes the full message text)
        print(f"          ⚠️  session_reply campaign missing — message NOT sent to {whatsapp}")
        print(f"          📄 Content that would have been delivered:")
        for line in message.splitlines()[:12]:
            print(f"             {line}")
    return ok


async def _post(url: str, payload: dict) -> bool:
    """Post payload to AiSensy API. Returns True on success."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            success = resp.status_code == 200
            if not success:
                print(f"AiSensy error {resp.status_code}: {resp.text[:200]}")
            return success
    except Exception as e:
        print(f"AiSensy request failed: {e}")
        return False

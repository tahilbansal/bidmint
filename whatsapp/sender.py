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
    """Send a free-form session message through AiSensy."""
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
    """Post payload to AiSensy API. Returns True on success."""
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

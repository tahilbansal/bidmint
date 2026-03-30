import anthropic
import json
import logging
import os
from dotenv import load_dotenv
from ai.prompts import TENDER_PARSE_PROMPT
from scraper.filter import detect_category

load_dotenv()
log = logging.getLogger(__name__)

# Set to True once we detect the API quota is exhausted so we stop hitting
# the endpoint on every tender (saves time and log spam).
_api_quota_exhausted = False


def _get_client():
    """Create Anthropic client lazily so load_dotenv() always runs first."""
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


async def parse_tender_with_ai(tender_raw: dict) -> dict:
    """
    Call Claude to extract structured food data from raw tender.
    Falls back to rule-based classification if API fails.
    Cost: ~1 API call = ~Rs 0.08 per tender at Sonnet pricing.
    """
    global _api_quota_exhausted
    if _api_quota_exhausted:
        return _rule_based_fallback(tender_raw)

    prompt = TENDER_PARSE_PROMPT.format(
        title=tender_raw.get("title", ""),
        department=tender_raw.get("department", ""),
        location=tender_raw.get("location", ""),
        quantity=tender_raw.get("quantity", "")
    )

    try:
        client = _get_client()
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
        log.warning("Claude returned invalid JSON: %s — using fallback", e)
        return _rule_based_fallback(tender_raw)

    except Exception as e:
        err_str = str(e).lower()
        if "credit balance is too low" in err_str or "quota" in err_str:
            _api_quota_exhausted = True
            log.warning("Anthropic quota exhausted — switching ALL remaining tenders to rule-based fallback")
        else:
            log.warning("AI unavailable (%s: %s) — using rule-based fallback",
                        type(e).__name__, e)
        return _rule_based_fallback(tender_raw)


def _rule_based_fallback(tender_raw: dict) -> dict:
    """Used when Claude API is unavailable. Lower quality but never fails."""
    category = detect_category(tender_raw)
    # Use MEDIUM confidence when the rule engine recognised a specific food category.
    # Only use LOW (which triggers rejection) for truly unclassifiable tenders.
    confidence = "LOW" if category == "other_food" else "MEDIUM"
    return {
        "food_category": category,
        "item_name_hindi": tender_raw.get("title", "")[:50],
        "quantity_kg": None,
        "fssai_required": False,
        "confidence": confidence,
        "whatsapp_summary": tender_raw.get("title", "")[:100],
        "red_flags": []
    }

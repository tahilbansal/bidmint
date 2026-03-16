import anthropic
import json
import os
from dotenv import load_dotenv
from ai.prompts import TENDER_PARSE_PROMPT
from scraper.filter import detect_category

load_dotenv()


def _get_client():
    """Create Anthropic client lazily so load_dotenv() always runs first."""
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


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

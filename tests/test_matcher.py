"""
Tests for AI matcher module (mocked Claude API).
"""
import pytest
from unittest.mock import patch, MagicMock
from ai.matcher import parse_tender_with_ai, _rule_based_fallback


class TestRuleBasedFallback:
    def test_rice_tender(self):
        tender = {"title": "Basmati Rice 1121 Supply", "department": "Army", "location": "Punjab"}
        result = _rule_based_fallback(tender)
        assert result["food_category"] == "rice"
        assert result["confidence"] == "LOW"
        assert result["fssai_required"] is False

    def test_wheat_tender(self):
        tender = {"title": "Wheat Atta 10kg packs", "department": "FCI", "location": "Punjab"}
        result = _rule_based_fallback(tender)
        assert result["food_category"] == "wheat"

    def test_unknown_category(self):
        tender = {"title": "General Provisions", "department": "Hostel", "location": "Patiala"}
        result = _rule_based_fallback(tender)
        assert result["food_category"] == "other_food"

    def test_returns_all_required_keys(self):
        tender = {"title": "Rice", "department": "", "location": ""}
        result = _rule_based_fallback(tender)
        required_keys = ["food_category", "item_name_hindi", "quantity_kg",
                         "fssai_required", "confidence", "whatsapp_summary", "red_flags"]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"


@pytest.mark.asyncio
async def test_parse_falls_back_on_api_error():
    """Verify that Claude API errors trigger the rule-based fallback."""
    import anthropic
    tender = {"title": "Rice Supply", "department": "Army", "location": "Patiala", "quantity": "500kg"}

    with patch("ai.matcher.client") as mock_client:
        mock_client.messages.create.side_effect = anthropic.APIError(
            message="rate limit", request=MagicMock(), body=None
        )
        result = await parse_tender_with_ai(tender)
        assert result["confidence"] == "LOW"  # Fallback always returns LOW
        assert result["food_category"] == "rice"

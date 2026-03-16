"""
Tests for scraper filter module.
"""
import pytest
from scraper.filter import (
    is_food_tender, is_punjab_tender,
    detect_category, filter_tenders
)


class TestIsFoodTender:
    def test_rice_in_title(self):
        tender = {"title": "Supply of Basmati Rice 50kg bags", "department": "Army"}
        assert is_food_tender(tender) is True

    def test_wheat_in_department(self):
        tender = {"title": "Annual Supply", "department": "Punjab Wheat Board"}
        assert is_food_tender(tender) is True

    def test_not_food(self):
        tender = {"title": "Construction of Bridge", "department": "PWD Punjab"}
        assert is_food_tender(tender) is False

    def test_dal_tender(self):
        tender = {"title": "Procurement of Masoor Dal 1000 quintals", "department": "FCI"}
        assert is_food_tender(tender) is True

    def test_oil_tender(self):
        tender = {"title": "Mustard Oil supply for hostel", "department": "University"}
        assert is_food_tender(tender) is True

    def test_empty_fields(self):
        tender = {"title": "", "department": ""}
        assert is_food_tender(tender) is False


class TestIsPunjabTender:
    def test_patiala_location(self):
        tender = {"location": "Patiala, Punjab", "department": ""}
        assert is_punjab_tender(tender) is True

    def test_punjab_department(self):
        tender = {"location": "", "department": "Punjab State Warehousing Corp"}
        assert is_punjab_tender(tender) is True

    def test_not_punjab(self):
        tender = {"location": "Mumbai, Maharashtra", "department": "BMC"}
        assert is_punjab_tender(tender) is False

    def test_adjacent_state_haryana(self):
        tender = {"location": "Karnal, Haryana", "department": ""}
        assert is_punjab_tender(tender) is True

    def test_chandigarh(self):
        tender = {"location": "Chandigarh", "department": ""}
        assert is_punjab_tender(tender) is True


class TestDetectCategory:
    def test_rice(self):
        assert detect_category({"title": "Basmati Rice 1121"}) == "rice"

    def test_wheat(self):
        assert detect_category({"title": "Wheat Atta 10kg packs"}) == "wheat"

    def test_pulses(self):
        assert detect_category({"title": "Moong Dal Whole"}) == "pulses"

    def test_oil(self):
        assert detect_category({"title": "Refined Sunflower Oil"}) == "oils"

    def test_sugar(self):
        assert detect_category({"title": "White Sugar Grade M"}) == "sugar"

    def test_dairy(self):
        assert detect_category({"title": "Full Cream Milk Packets"}) == "dairy"

    def test_spices(self):
        assert detect_category({"title": "Turmeric Powder 500g"}) == "spices"

    def test_unknown_defaults_to_other(self):
        assert detect_category({"title": "Miscellaneous Provisions"}) == "other_food"


class TestFilterTenders:
    def test_filters_to_punjab_food_only(self):
        tenders = [
            {"title": "Rice Supply", "department": "Punjab Hostel", "location": "Patiala"},
            {"title": "Bridge Construction", "department": "PWD", "location": "Patiala"},
            {"title": "Rice Supply", "department": "Maharashtra FCI", "location": "Mumbai"},
        ]
        result = filter_tenders(tenders)
        assert len(result) == 1
        assert result[0]["category"] == "rice"

    def test_empty_input(self):
        assert filter_tenders([]) == []

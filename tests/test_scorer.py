"""
Tests for AI scorer module.
"""
import pytest
from ai.scorer import calculate_match_score
from database.models import Supplier, Tender


class TestCalculateMatchScore:
    def test_exact_match_same_district(self):
        supplier = Supplier(district="patiala", categories="rice,wheat")
        tender = Tender(location="Patiala District Hospital", category="rice")
        ai = {"food_category": "rice", "confidence": "HIGH", "quantity_kg": 2000, "red_flags": []}
        score = calculate_match_score(supplier, tender, ai)
        assert score >= 80, f"Expected >= 80, got {score}"

    def test_wrong_category_low_score(self):
        supplier = Supplier(district="patiala", categories="rice")
        tender = Tender(location="Patiala", category="construction")
        ai = {"food_category": "other", "confidence": "LOW", "quantity_kg": None, "red_flags": []}
        score = calculate_match_score(supplier, tender, ai)
        assert score < 30, f"Expected < 30, got {score}"

    def test_red_flag_penalty(self):
        supplier = Supplier(district="patiala", categories="rice")
        tender = Tender(location="Patiala", category="rice")
        ai = {
            "food_category": "rice", "confidence": "HIGH",
            "quantity_kg": 2000, "red_flags": ["unrealistic_deadline", "vague_specs"]
        }
        score = calculate_match_score(supplier, tender, ai)
        # Perfect score without flags: 40 + 30 + 20 + 10 = 100
        # With 2 flags: 100 - 20 = 80
        base = 40 + 30 + 20 + 10
        assert score == base - 20

    def test_adjacent_district(self):
        supplier = Supplier(district="patiala", categories="wheat")
        tender = Tender(location="Ludhiana Civil Hospital", category="wheat")
        ai = {"food_category": "wheat", "confidence": "HIGH", "quantity_kg": 5000, "red_flags": []}
        score = calculate_match_score(supplier, tender, ai)
        # Category: 40, Adjacent location: 20, Confidence HIGH: 20, Qty: 10 = 90
        assert score == 90

    def test_same_state_only(self):
        supplier = Supplier(district="patiala", categories="rice")
        tender = Tender(location="Punjab, Bathinda", category="rice")
        ai = {"food_category": "rice", "confidence": "MEDIUM", "quantity_kg": 10000, "red_flags": []}
        score = calculate_match_score(supplier, tender, ai)
        # Category: 40, State only: 10, MEDIUM: 12, qty: 10 = 72
        assert score == 72

    def test_large_quantity_lower_score(self):
        supplier = Supplier(district="patiala", categories="rice")
        tender = Tender(location="Patiala", category="rice")
        ai = {"food_category": "rice", "confidence": "HIGH", "quantity_kg": 300000, "red_flags": []}
        score = calculate_match_score(supplier, tender, ai)
        # Category: 40, Location: 30, HIGH: 20, qty > 200t: 0 = 90
        assert score == 90

    def test_all_categories_supplier(self):
        supplier = Supplier(district="amritsar", categories="all")
        tender = Tender(location="Amritsar", category="spices")
        ai = {"food_category": "spices", "confidence": "MEDIUM", "quantity_kg": None, "red_flags": []}
        score = calculate_match_score(supplier, tender, ai)
        # All categories: 30, Same district: 30, MEDIUM: 12, unknown qty: 5 = 77
        assert score == 77

    def test_score_clamped_at_zero(self):
        supplier = Supplier(district="patiala", categories="rice")
        tender = Tender(location="Mumbai", category="construction")
        ai = {
            "food_category": "other", "confidence": "LOW", "quantity_kg": None,
            "red_flags": ["unrealistic_deadline", "abnormal_quantity", "vague_specs"]
        }
        score = calculate_match_score(supplier, tender, ai)
        assert score >= 0

    def test_score_clamped_at_100(self):
        supplier = Supplier(district="patiala", categories="rice")
        tender = Tender(location="Patiala", category="rice")
        ai = {"food_category": "rice", "confidence": "HIGH", "quantity_kg": 1000, "red_flags": []}
        score = calculate_match_score(supplier, tender, ai)
        assert score <= 100

"""
CLI script to manually add pilot suppliers to the database.
Usage: python scripts/add_supplier.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal
from database.models import Supplier


PILOT_SUPPLIERS = [
    {
        "whatsapp": "919XXXXXXXXX",  # Replace with actual number
        "name": "Pilot Supplier",
        "district": "patiala",
        "categories": "rice,wheat,pulses",
    },
]


def add_suppliers():
    db = SessionLocal()
    try:
        for s in PILOT_SUPPLIERS:
            existing = db.query(Supplier).filter(Supplier.whatsapp == s["whatsapp"]).first()
            if existing:
                print(f"  Already exists: {s['whatsapp']} ({existing.name or 'unnamed'})")
                continue

            supplier = Supplier(
                whatsapp=s["whatsapp"],
                name=s.get("name"),
                district=s["district"],
                categories=s["categories"],
            )
            db.add(supplier)
            print(f"  Added: {s['whatsapp']} — {s['name']} ({s['district']})")

        db.commit()
        print("\nDone. Suppliers in database:")
        for sup in db.query(Supplier).all():
            status = "✅ Active" if sup.active else "❌ Inactive"
            print(f"  {sup.whatsapp} | {sup.name or 'unnamed'} | {sup.district} | {sup.categories} | {status}")
    finally:
        db.close()


if __name__ == "__main__":
    print("Adding pilot suppliers to BidMint...\n")
    add_suppliers()

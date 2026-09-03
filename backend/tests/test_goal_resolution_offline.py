import sys
from backend.main import resolve_goal_based_request, load_catalog

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_goal_resolution_logic():
    print("==================================================")
    print("   PEHRAPAY - GOAL-BASED RESOLVER (OFFLINE TEST)  ")
    print("==================================================")

    catalog = load_catalog()

    # 1. Exact Match Test (Should return exact item unchanged)
    intent_exact = {"item": "Double-Walled Coffee Mug"}
    prod1, notes1 = resolve_goal_based_request("Buy a mug", intent_exact, catalog)
    assert prod1["name"] == "Double-Walled Coffee Mug"
    assert notes1 is None, "Exact match must return None for notes (existing flow unchanged)"
    print("[PASS] 1. Exact Match Test: Returned exact catalog item unchanged.")

    # 2. Goal-Based Selection Test ("buy coffee under Rs. 1000")
    # Catalog contains:
    # - Premium Arabica Coffee Beans (1kg): Rs. 1200, trust 4.8 (category: groceries, exceeds 1000 max_price)
    # - Organic Green Tea (50 bags): Rs. 450, trust 3.5 (category: groceries, within 1000 max_price)
    # - Double-Walled Coffee Mug: Rs. 899, trust 4.0 (category: kitchenware -> MUST BE EXCLUDED by strict category filter!)
    intent_goal = {"item": "coffee"}
    prod2, notes2 = resolve_goal_based_request("buy coffee under 1000", intent_goal, catalog)
    assert prod2 is not None
    assert prod2["category"] == "groceries", f"Expected category 'groceries', got '{prod2['category']}'"
    assert prod2["name"] == "Organic Green Tea (50 bags)", f"Expected 'Organic Green Tea (50 bags)', got '{prod2['name']}'"
    assert "Double-Walled Coffee Mug" not in notes2, "Kitchenware items must NOT be included in groceries category match!"
    print(f"[PASS] 2. Strict Category Constraint Test: Selected '{prod2['name']}' (Rs. {prod2['price']}, trust {prod2['merchant_trust_level']}). Kitchenware items excluded.")

    # 3. Goal-Based Selection Test ("electronics under Rs. 3000")
    # Catalog electronics under 3000:
    # - USB-C Hub (6-in-1): Rs. 2499, trust 4.6
    # - Adjustable Laptop Stand: Rs. 1500, trust 4.6
    # Highest trust 4.6 (tie broken deterministically)
    intent_elec = {"item": "gadgets"}
    prod3, notes3 = resolve_goal_based_request("get tech accessories under 3000", intent_elec, catalog)
    assert prod3 is not None
    assert prod3["price"] <= 3000.0
    print(f"[PASS] 3. Goal-Based High Trust Selection Test: Selected '{prod3['name']}' (Rs. {prod3['price']}, trust {prod3['merchant_trust_level']}).")

    # 4. No Match Test ("buy coffee under Rs. 50")
    intent_none = {"item": "coffee"}
    prod4, err4 = resolve_goal_based_request("buy coffee under 50", intent_none, catalog)
    assert prod4 is None
    assert err4 == "No catalog products found matching your request criteria"
    print(f"[PASS] 4. No Match Test: Correctly returned REJECT reason '{err4}'.")

    print("\n[SUCCESS] Goal-based resolution logic verified 100% offline!")

if __name__ == "__main__":
    test_goal_resolution_logic()

import os
import json
import time
import sys
import sqlite3
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from backend.agent.parser import AgentParser
from backend.razorpay_client.client import RazorpayClientWrapper
from backend.mandates.models import SpendingMandate
from backend.mandates.store import MandateStore, DB_PATH
from backend.policy_engine.engine import PolicyEngine

def load_catalog():
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    catalog_path = os.path.join(current_dir, "data", "catalog.json")
    with open(catalog_path, "r") as f:
        return json.load(f)

def run_day4_integrity_tests():
    print("==================================================")
    print("       PEHRAPAY - DAY 4 INTEGRITY TESTS           ")
    print("==================================================\n")

    # 1. Initialize stores and engine
    store = MandateStore()
    engine = PolicyEngine()
    parser = AgentParser()
    rzp = RazorpayClientWrapper()
    catalog = load_catalog()

    # Setup lookup helper
    catalog_lookup = {item["name"].lower(): item for item in catalog}
    def get_product_details(product_name: str):
        item_details = catalog_lookup.get(product_name.lower())
        if not item_details:
            for name, details in catalog_lookup.items():
                if name in product_name.lower() or product_name.lower() in name:
                    return details
            return {"category": "unknown", "merchant_trust_level": 0.0}
        return item_details

    # Clean tables
    with store._get_connection() as conn:
        conn.execute("DELETE FROM mandates")
        conn.execute("DELETE FROM audit_logs")
        conn.commit()

    now = int(time.time())

    # =========================================================================
    # CASE 1: NORMAL MANDATE (VALID SIGNATURE)
    # =========================================================================
    print("--- [CASE 1] CREATING VALID MANDATE AND TESTING PURCHASE ---")
    mandate_normal = SpendingMandate(
        purpose="Integrity Verification - Normal",
        max_amount=2000.0,
        allowed_category="electronics",
        allowed_merchant_trust_level=3.0,
        max_transactions=5,
        expiry_timestamp=now + 3600
    )
    
    # Store mandate (will generate valid signature)
    store.create_mandate("mandate_valid", mandate_normal)
    mandate_db = store.get_mandate("mandate_valid")
    
    print(f"Mandate Stored signature: {mandate_db['signature']}")
    
    # Run purchase request
    buyer_request = "Buy 1 adjustable laptop stand please." # Rs. 1500, electronics
    print(f"Request: \"{buyer_request}\"")
    
    intent = parser.parse_buyer_request(buyer_request, catalog)
    print(f"Parsed Intent: {json.dumps(intent)}")
    
    prod_meta = get_product_details(intent["item"])
    category = prod_meta["category"]
    trust = prod_meta["merchant_trust_level"]
    
    # Evaluate policy engine
    decision, reason = engine.evaluate(
        intent=intent,
        mandate=mandate_db,
        product_category=category,
        merchant_trust_level=trust
    )
    
    print(f"Policy Engine Decision: {decision}")
    print(f"Reason: {reason}")
    
    razorpay_status = "SKIPPED"
    if decision == "APPROVE":
        total_price = intent["price"] * intent["quantity"]
        order_res = rzp.create_order(amount_in_rupees=total_price)
        payment_link = rzp.generate_payment_link(
            order_id=order_res["order_id"],
            amount_in_rupees=total_price,
            description=f"Purchase: {intent['quantity']}x {intent['item']}"
        )
        razorpay_status = f"SUCCESS (Order: {order_res['order_id']}, Link: {payment_link})"
        store.increment_transaction_count("mandate_valid")
    
    print(f"Razorpay Action: {razorpay_status}\n")
    
    case1_passed = (decision == "APPROVE") and (razorpay_status.startswith("SUCCESS"))

    # =========================================================================
    # CASE 2: TAMPERED MANDATE (SQLITE MODIFIED DIRECTLY)
    # =========================================================================
    print("--- [CASE 2] SIMULATING DIRECT DATABASE TAMPERING ---")
    
    # Setup mandate with small budget (Rs. 500)
    mandate_low_budget = SpendingMandate(
        purpose="Integrity Verification - Tamper Test",
        max_amount=500.0, # Original limit
        allowed_category="electronics",
        allowed_merchant_trust_level=3.0,
        max_transactions=5,
        expiry_timestamp=now + 3600
    )
    store.create_mandate("mandate_tamper", mandate_low_budget)
    
    # Retrieve original mandate to see signature
    original_db = store.get_mandate("mandate_tamper")
    print(f"Original Mandate limit: Rs. {original_db['max_amount']:.2f}")
    print(f"Original Stored signature: {original_db['signature']}")
    
    # Directly tamper SQLite database (modify max_amount from 500 to 50000)
    print("\n[ATTACK] Manipulating SQLite record directly (bypassing store signing)...")
    db_conn = sqlite3.connect(DB_PATH)
    db_conn.execute("UPDATE mandates SET max_amount = 50000.0 WHERE mandate_id = 'mandate_tamper'")
    db_conn.commit()
    db_conn.close()
    print("[ATTACK] Successfully updated 'max_amount' to Rs. 50000.00 directly in SQLite!")
    
    # Retrieve modified record to confirm budget is physically changed
    tampered_db = store.get_mandate("mandate_tamper")
    print(f"Tampered Mandate limit retrieved from DB: Rs. {tampered_db['max_amount']:.2f}")
    print(f"Tampered Mandate signature in DB (remains original): {tampered_db['signature']}\n")
    
    # Run purchase request that exceeds Rs. 500 but is under Rs. 50,000
    # If policy engine is secure, it will detect signature mismatch and REJECT.
    # If insecure, it will evaluate Rs. 1500 <= Rs. 50,000 and APPROVE.
    buyer_request_tamper = "Buy 1 adjustable laptop stand please." # Rs. 1500
    print(f"Request: \"{buyer_request_tamper}\"")
    
    # Wait to avoid Gemini 429 quota (optional, but let's parse using Gemini/mock)
    time.sleep(5)
    
    intent_tamper = parser.parse_buyer_request(buyer_request_tamper, catalog)
    print(f"Parsed Intent: {json.dumps(intent_tamper)}")
    
    prod_meta_tamper = get_product_details(intent_tamper["item"])
    category_tamper = prod_meta_tamper["category"]
    trust_tamper = prod_meta_tamper["merchant_trust_level"]
    
    # Evaluate policy engine on modified mandate
    decision_tamper, reason_tamper = engine.evaluate(
        intent=intent_tamper,
        mandate=tampered_db,
        product_category=category_tamper,
        merchant_trust_level=trust_tamper
    )
    
    print(f"Policy Engine Decision: {decision_tamper}")
    print(f"Reason: {reason_tamper}")
    
    razorpay_status_tamper = "SKIPPED"
    if decision_tamper == "APPROVE":
        total_price = intent_tamper["price"] * intent_tamper["quantity"]
        order_res = rzp.create_order(amount_in_rupees=total_price)
        payment_link = rzp.generate_payment_link(
            order_id=order_res["order_id"],
            amount_in_rupees=total_price,
            description=f"Purchase: {intent_tamper['quantity']}x {intent_tamper['item']}"
        )
        razorpay_status_tamper = f"SUCCESS (Order: {order_res['order_id']}, Link: {payment_link})"
        store.increment_transaction_count("mandate_tamper")
        
    print(f"Razorpay Action: {razorpay_status_tamper}\n")
    
    case2_passed = (decision_tamper == "REJECT") and ("integrity check failed" in reason_tamper) and (razorpay_status_tamper == "SKIPPED")

    # =========================================================================
    # EVALUATION RESULTS SUMMARY
    # =========================================================================
    print("=========================================================================")
    print("                     DAY 4 INTEGRITY TEST SUMMARY                       ")
    print("=========================================================================")
    print(f"Case 1: Normal Valid Flow      | Expected: APPROVE | Actual: {decision:<7} | {'PASS' if case1_passed else 'FAIL'}")
    print(f"Case 2: Direct Database Tamper | Expected: REJECT  | Actual: {decision_tamper:<7} | {'PASS' if case2_passed else 'FAIL'}")
    print("=========================================================================\n")
    
    if case1_passed and case2_passed:
        print("[SUCCESS] DAY 4 CRYPTOGRAPHIC INTEGRITY VERIFICATION SUCCESSFUL!")
    else:
        print("[FAIL] INTEGRITY CHECK FAILURE.")

if __name__ == "__main__":
    run_day4_integrity_tests()

import time
import hmac
import hashlib
import json
import os
from typing import Tuple

class PolicyEngine:
    def __init__(self):
        pass

    def _verify_mandate_signature(self, mandate: dict) -> bool:
        """
        Recomputes the HMAC-SHA256 signature for the mandate's fields and compares it to the stored signature.
        """
        stored_sig = mandate.get("signature")
        if not stored_sig:
            return False

        secret = os.getenv("MANDATE_SIGNING_SECRET", "")
        # Serialize fields deterministically (must match MandateStore.compute_signature)
        payload = {
            "version": int(mandate["version"]),
            "max_amount": float(mandate["max_amount"]),
            "allowed_category": mandate["allowed_category"].lower(),
            "allowed_merchant_trust_level": float(mandate["allowed_merchant_trust_level"]),
            "max_transactions": int(mandate["max_transactions"]),
            "expiry_timestamp": int(mandate["expiry_timestamp"]),
            "human_review_threshold": float(mandate["human_review_threshold"]) if mandate.get("human_review_threshold") is not None else None
        }
        serialized = json.dumps(payload, sort_keys=True)
        recomputed_sig = hmac.new(secret.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(stored_sig, recomputed_sig)

    def evaluate(
        self, 
        intent: dict, 
        mandate: dict, 
        product_category: str, 
        merchant_trust_level: float,
        current_time: int = None,
        store = None
    ) -> Tuple[str, str]:
        """
        Evaluates a structured purchase intent against a spending mandate.
        Returns a tuple: (DECISION, REASON)
        DECISION can be 'APPROVE', 'REJECT', or 'HUMAN_REVIEW'.
        """
        # 0. Signature check
        if not self._verify_mandate_signature(mandate):
            return "REJECT", "Mandate integrity check failed — possible tampering detected"

        curr_time = current_time or int(time.time())

        # 1. Expiry Check
        if curr_time >= mandate["expiry_timestamp"]:
            return "REJECT", f"Mandate has expired (Expiry: {mandate['expiry_timestamp']}, Current: {curr_time})"

        # 2. Transaction Limit Check
        if mandate["current_transactions"] >= mandate["max_transactions"]:
            return "REJECT", f"Mandate transaction limit reached ({mandate['current_transactions']}/{mandate['max_transactions']})"

        # 3. Category Match Check
        if product_category.lower() != mandate["allowed_category"].lower():
            return "REJECT", f"Category '{product_category}' is not allowed by mandate (allowed: '{mandate['allowed_category']}')"

        # 4. Merchant Trust Level Check
        if merchant_trust_level < mandate["allowed_merchant_trust_level"]:
            return "REJECT", f"Merchant trust level {merchant_trust_level} is below required {mandate['allowed_merchant_trust_level']}"

        # 5. Amount Limit Check (Cumulative Remaining Budget)
        remaining_budget = mandate["max_amount"]
        if store is not None:
            spent_so_far = store.get_spent_amount(mandate["mandate_id"], mandate["version"])
            remaining_budget = max(0.0, mandate["max_amount"] - spent_so_far)

        intent_total = intent["price"] * intent["quantity"]
        if intent_total > remaining_budget:
            total_val = int(intent_total) if intent_total.is_integer() else intent_total
            limit_val = int(remaining_budget) if remaining_budget.is_integer() else remaining_budget
            
            total_str = f"{total_val:,}" if isinstance(total_val, int) else f"{total_val:,.2f}"
            limit_str = f"{limit_val:,}" if isinstance(limit_val, int) else f"{limit_val:,.2f}"
            
            return "REJECT", f"Requested transaction total of ₹{total_str} exceeds the remaining mandate budget of ₹{limit_str}."

        # 6. Human Review Check
        hr_threshold = mandate.get("human_review_threshold")
        if hr_threshold is not None and hr_threshold > 0 and intent_total >= hr_threshold:
            return "HUMAN_REVIEW", "Transaction is policy-compliant but exceeds the chosen risk threshold for automated execution."

        return "APPROVE", "Transaction meets all mandate requirements"

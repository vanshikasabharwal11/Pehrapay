"""
PehraPay Python Agent Client SDK
Lightweight integration wrapper for external AI agents (LangChain, AutoGen, CrewAI, LlamaIndex)
to interact with PehraPay Vault APIs.
"""

import requests
from typing import Dict, Any, Optional

class PehraPayAgentClient:
    def __init__(self, api_base: str = "http://127.0.0.1:8000"):
        self.api_base = api_base.rstrip("/")

    def get_catalog(self) -> list:
        """Fetch AI-readable merchant catalog."""
        res = requests.get(f"{self.api_base}/api/catalog")
        res.raise_for_status()
        return res.json()

    def purchase(self, mandate_id: str, buyer_request: str, is_recommendation_accepted: bool = False) -> Dict[str, Any]:
        """
        Submits a natural language purchase request to PehraPay Vault.
        Evaluates intent against mandate policy constraints and returns a signed decision receipt + Razorpay payment link.
        """
        payload = {
            "mandate_id": mandate_id,
            "buyer_request": buyer_request,
            "is_recommendation_accepted": is_recommendation_accepted
        }
        res = requests.post(f"{self.api_base}/api/purchase", json=payload)
        res.raise_for_status()
        return res.json()

    def settle_payment(self, order_id: str, payment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Triggers settlement loop by simulating or passing a Razorpay payment capture webhook.
        Transitions transaction status from AUTHORIZED to PAID_SETTLED.
        """
        payload = {"order_id": order_id, "event": "payment.captured"}
        if payment_id:
            payload["payment_id"] = payment_id
        res = requests.post(f"{self.api_base}/api/webhooks/razorpay", json=payload)
        res.raise_for_status()
        return res.json()

    def get_analytics(self) -> Dict[str, Any]:
        """Fetch live session growth and trust metrics computed directly from SQLite."""
        res = requests.get(f"{self.api_base}/api/analytics/summary")
        res.raise_for_status()
        return res.json()

if __name__ == "__main__":
    # Example usage for autonomous agents:
    client = PehraPayAgentClient()
    print("[SDK TEST] Fetching merchant catalog...")
    catalog = client.get_catalog()
    print(f"[SDK TEST] Loaded {len(catalog)} merchant items.")

    print("\n[SDK TEST] Executing purchase via PehraPay Vault...")
    result = client.purchase(mandate_id="mandate_coffee", buyer_request="buy me coffee under ₹1000")
    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")
    print(f"Order ID: {result.get('order_id')}")
    print(f"Razorpay Link: {result.get('razorpay_url')}")
    
    if result.get("order_id") and result["decision"] == "APPROVE":
        print("\n[SDK TEST] Simulating settlement webhook...")
        settle_res = client.settle_payment(result["order_id"])
        print(f"Settlement Status: {settle_res['transaction_status']}, Payment ID: {settle_res['payment_id']}")

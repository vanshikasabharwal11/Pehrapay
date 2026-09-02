import json
from fastapi.testclient import TestClient
from backend.main import app, store
from backend.mandates.models import SpendingMandate

client = TestClient(app)

def test_emergency_kill_switch():
    print("==================================================")
    print("       PEHRAPAY - EMERGENCY KILL SWITCH TEST      ")
    print("==================================================")
    
    # 1. Setup - Create a valid mandate for the test
    mandate_id = "test_kill_switch_mandate"
    # Clean previous records if any
    with store._get_connection() as conn:
        conn.execute("DELETE FROM mandates WHERE mandate_id = ?", (mandate_id,))
        conn.execute("DELETE FROM audit_logs WHERE mandate_id = ?", (mandate_id,))
        conn.commit()

    # Create the test mandate
    mandate_data = {
        "mandate_id": mandate_id,
        "purpose": "Kill Switch Verification Mandate",
        "max_amount": 5000.0,
        "allowed_category": "electronics",
        "allowed_merchant_trust_level": 3.0,
        "max_transactions": 5,
        "expiry_days": 7
    }
    create_res = client.post("/api/mandates", json=mandate_data)
    assert create_res.status_code == 200
    print("[SETUP] Created test mandate with budget Rs. 5000.")

    # 2. Verify initial status is paused = False
    status_res = client.get("/api/system/status")
    assert status_res.status_code == 200
    assert status_res.json()["paused"] is False
    print("[STEP 1] Confirmed initial system state is ACTIVE.")

    # 3. Trigger Emergency Pause
    pause_res = client.post("/api/system/pause")
    assert pause_res.status_code == 200
    assert pause_res.json()["paused"] is True
    
    # Verify status reflects pause
    status_res = client.get("/api/system/status")
    assert status_res.json()["paused"] is True
    print("[STEP 2] Emergency Kill Switch ACTIVATED.")

    # 4. Attempt purchase while paused
    purchase_data = {
        "buyer_request": "Buy 1 adjustable laptop stand please.",
        "mandate_id": mandate_id
    }
    purchase_res = client.post("/api/purchase", json=purchase_data)
    assert purchase_res.status_code == 200
    
    res_data = purchase_res.json()
    print(f"[STEP 3] Purchase attempt response while paused: {res_data['decision']} ({res_data['reason']})")
    assert res_data["decision"] == "REJECT"
    assert "Emergency Kill Switch Active" in res_data["reason"]
    assert res_data["razorpay_url"] is None

    # 5. Resume Agent
    resume_res = client.post("/api/system/resume")
    assert resume_res.status_code == 200
    assert resume_res.json()["paused"] is False
    
    # Verify status reflects active
    status_res = client.get("/api/system/status")
    assert status_res.json()["paused"] is False
    print("[STEP 4] Emergency Kill Switch DEACTIVATED (System Resumed).")

    # 6. Attempt same purchase after resume (should approve)
    purchase_res2 = client.post("/api/purchase", json=purchase_data)
    assert purchase_res2.status_code == 200
    
    res_data2 = purchase_res2.json()
    print(f"[STEP 5] Purchase attempt response after resume: {res_data2['decision']} ({res_data2['reason']})")
    assert res_data2["decision"] == "APPROVE"
    assert res_data2["razorpay_url"] is not None
    print("[SUCCESS] Emergency Kill Switch behaves exactly as expected!")

if __name__ == "__main__":
    test_emergency_kill_switch()

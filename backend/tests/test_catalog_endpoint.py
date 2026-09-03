import sys
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_get_catalog_endpoint():
    print("==================================================")
    print("      PEHRAPAY - GET /api/catalog ENDPOINT TEST   ")
    print("==================================================")

    res = client.get("/api/catalog")
    assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}"
    
    catalog = res.json()
    assert isinstance(catalog, list), "Catalog response must be a JSON array!"
    assert len(catalog) > 0, "Catalog must contain products!"

    print(f"[SUCCESS] HTTP {res.status_code} OK! Received {len(catalog)} products in catalog.")
    
    first_item = catalog[0]
    required_fields = ["name", "price", "category", "merchant_id", "merchant_trust_level"]
    for field in required_fields:
        assert field in first_item, f"Missing required field '{field}' in catalog item!"

    print(f"\n[SAMPLE PRODUCT]")
    print(f"Name: {first_item['name']}")
    print(f"Price: Rs. {first_item['price']}")
    print(f"Category: {first_item['category']}")
    print(f"Merchant ID: {first_item['merchant_id']}")
    print(f"Merchant Trust Level: {first_item['merchant_trust_level']}")

if __name__ == "__main__":
    test_get_catalog_endpoint()

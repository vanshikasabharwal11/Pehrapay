import os
import json
import re
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load env variables from backend directory or current directory
load_dotenv()
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

class ParsedIntent(BaseModel):
    item: str = Field(..., description="The exact product name matched from the catalog.")
    price: float = Field(..., description="The unit price of the product.")
    quantity: int = Field(..., description="The quantity of the product to purchase.")
    merchant_id: str = Field(..., description="The merchant ID associated with the product.")

# Helper: Goal-Based Product Selection Resolver
def resolve_goal_based_request(buyer_request: str, intent: dict, catalog: list):
    """
    1. Check if intent['item'] has an EXACT match in catalog.json.
       If YES -> Return exact match (EXISTING flow unchanged).
    2. If NO exact match -> Ambiguous / Goal-Based Request.
       Extract category & max_price constraints from buyer_request / intent.
    3. Filter catalog items by category and price <= max_price.
    4. Select product with HIGHEST merchant_trust_level (deterministic selection).
    5. Log clear rationale.
    6. If NO products match -> Return None + error message.
    """
    requested_item = intent.get("item", "").strip()

    # Step 1: Exact Name Match check (case-insensitive)
    for item in catalog:
        if item["name"].strip().lower() == requested_item.lower():
            return item, None

    # Step 2: Goal-based constraint parsing
    text = f"{buyer_request} {requested_item}".lower()

    # Parse max_price constraint (e.g. "under 1000", "below rs. 500", "max 2000", "< 1500")
    max_price = None
    price_match = re.search(r'(?:under|below|max|within|<|less than|budget of|budget)\s*(?:rs\.?|₹)?\s*(\d+(?:\.\d+)?)', text)
    if price_match:
        max_price = float(price_match.group(1))

    # Parse category & keywords
    all_categories = list({item["category"].lower() for item in catalog})
    matched_category = None
    for cat in all_categories:
        if cat in text:
            matched_category = cat
            break

    keyword_map = {
        "coffee": ["groceries", "coffee"],
        "tea": ["groceries", "tea"],
        "drink": ["groceries"],
        "food": ["groceries"],
        "snack": ["groceries"],
        "chair": ["furniture"],
        "desk": ["furniture", "electronics"],
        "lamp": ["electronics"],
        "light": ["electronics"],
        "bottle": ["sports_fitness"],
        "workout": ["sports_fitness"],
        "fitness": ["sports_fitness"],
        "headphone": ["electronics"],
        "audio": ["electronics"],
        "keyboard": ["electronics"],
        "stand": ["electronics"],
        "hub": ["electronics"],
        "tech": ["electronics"],
        "gadget": ["electronics"],
        "electronics": ["electronics"],
        "accessory": ["electronics", "kitchenware"],
        "accessories": ["electronics", "kitchenware"],
        "mug": ["kitchenware"],
        "cup": ["kitchenware"],
        "wallet": ["apparel"]
    }

    keywords = []
    for word, cat_list in keyword_map.items():
        if word in text:
            keywords.append(word)
            if not matched_category:
                matched_category = cat_list[0]

    # Step 3: Search catalog for matching products
    category_products = []
    for item in catalog:
        cat_match = False
        if matched_category:
            # Strict category filter: item's actual category MUST match matched_category
            if item["category"].lower() == matched_category:
                cat_match = True
        else:
            # Keyword fallback ONLY when no category was detected at all
            if any(kw in item["name"].lower() or kw in item["category"].lower() for kw in keywords):
                cat_match = True

        if not cat_match:
            continue

        if max_price is not None and item["price"] > max_price:
            continue

        category_products.append(item)

    # Step 6: No matching products found
    if not category_products:
        return None, "No catalog products found matching your request criteria"

    # Prioritize items matching specific keywords within the category if available
    keyword_matched = [item for item in category_products if any(kw in item["name"].lower() for kw in keywords)]
    matching_products = keyword_matched if keyword_matched else category_products

    # Step 4: Select product with HIGHEST merchant_trust_level
    matching_products.sort(key=lambda x: (x["merchant_trust_level"], -x["price"]), reverse=True)
    selected_product = matching_products[0]

    # Step 5: Log rationale summary
    matched_summary = ", ".join([f"{p['name']} (Rs.{p['price']}, trust {p['merchant_trust_level']})" for p in matching_products])
    constraint_str = f"category '{matched_category or 'general'}'"
    if max_price:
        constraint_str += f" under Rs.{max_price:g}"

    resolution_notes = (
        f"[GOAL RESOLVER] {len(matching_products)} catalog product(s) matched {constraint_str}: "
        f"[{matched_summary}] — selected '{selected_product['name']}' for highest trust score ({selected_product['merchant_trust_level']})."
    )
    try:
        print(resolution_notes)
    except UnicodeEncodeError:
        print(resolution_notes.encode("ascii", "replace").decode("ascii"))

    return selected_product, resolution_notes

class AgentParser:
    def __init__(self):
        self.last_call_fallback = False
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key and "AQ." in self.api_key or len(self.api_key) > 10:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-2.5-flash")
                self.client_enabled = True
                print("Gemini client successfully initialized.")
            except ImportError:
                print("Warning: 'google-generativeai' package not installed. Running in mock mode.")
                self.client_enabled = False
            except Exception as e:
                print(f"Warning: Failed to initialize Gemini Client: {e}")
                self.client_enabled = False
        else:
            print("Warning: GEMINI_API_KEY is missing or invalid. Running in MOCK mode.")
            self.client_enabled = False

    def parse_buyer_request(self, buyer_request: str, catalog: list, force_mock: bool = False) -> dict:
        """
        Parses a natural-language buyer request against a product catalog.
        Returns a structured dictionary matching ParsedIntent schema.
        """
        self.last_call_fallback = not self.client_enabled or force_mock
        if self.client_enabled and not force_mock:
            return self._parse_with_gemini(buyer_request, catalog)
        else:
            return self._parse_mock(buyer_request, catalog)

    def _parse_with_gemini(self, buyer_request: str, catalog: list) -> dict:
        import google.generativeai as genai
        
        system_instruction = (
            "You are an AI Shopping Assistant. Your task is to match the user's natural language request "
            "to exactly one product in the provided catalog and return a structured JSON object. "
            "You must populate all fields in the response schema based on the matched catalog product. "
            "If the request does not specify a quantity, default to 1."
        )

        catalog_str = json.dumps(catalog, indent=2)
        prompt = (
            f"{system_instruction}\n\n"
            f"Catalog:\n{catalog_str}\n\n"
            f"User Request: \"{buyer_request}\"\n\n"
            f"Extract the structured intent matching the schema."
        )

        import time as pytime

        max_retries = 3
        backoff_delay = 5.0

        for attempt in range(max_retries):
            try:
                # Call Gemini using GenerationConfig with response_schema
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        response_schema=ParsedIntent,
                        temperature=0.0
                    )
                )
                
                response_text = response.text.strip()
                intent = json.loads(response_text)
                
                # Authoritative catalog price override (Ignore LLM price output)
                matched_item = None
                for item in catalog:
                    if item["name"].lower() == intent.get("item", "").lower():
                        matched_item = item
                        break
                if not matched_item:
                    for item in catalog:
                        if item["name"].lower() in intent.get("item", "").lower() or intent.get("item", "").lower() in item["name"].lower():
                            matched_item = item
                            break
                if matched_item:
                    intent["price"] = float(matched_item["price"])
                    intent["item"] = matched_item["name"]
                    intent["merchant_id"] = matched_item["merchant_id"]
                
                return intent
            except Exception as e:
                is_429 = "429" in str(e) or "ResourceExhausted" in type(e).__name__ or "quota" in str(e).lower()
                if is_429 and attempt < max_retries - 1:
                    wait_time = backoff_delay * (2 ** attempt)
                    print(f"[RETRY] Gemini API returned 429 (quota exceeded). Retrying in {wait_time:.1f} seconds... (Attempt {attempt+1}/{max_retries})")
                    pytime.sleep(wait_time)
                else:
                    print(f"[WARNING] LLM fallback active - real Gemini call failed. Error: {e}")
                    self.last_call_fallback = True
                    return self._parse_mock(buyer_request, catalog)

    def _parse_mock(self, buyer_request: str, catalog: list) -> dict:
        """
        A rule-based natural language parser that extracts quantity, price constraints,
        and requested item/category, then hands off to the same resolve_goal_based_request
        function used by the main pipeline.
        """
        buyer_request_lower = buyer_request.lower()
        
        # 1. Cleanly extract quantity while ignoring price expressions (e.g. "under 1000", "below rs. 500", "₹1000")
        clean_for_qty = re.sub(r'(?:under|below|max|within|<|less than|budget of|budget)\s*(?:rs\.?|₹|inr)?\s*\d+(?:\.\d+)?', '', buyer_request_lower)
        clean_for_qty = re.sub(r'(?:rs\.?|₹|inr)\s*\d+(?:\.\d+)?', '', clean_for_qty)
        clean_for_qty = re.sub(r'\d+(?:\.\d+)?\s*(?:rs\.?|₹|inr|rupees)', '', clean_for_qty)

        quantity = 1
        qty_match = re.search(r'\b(\d+)\s*(?:x|boxes?|bags?|units?|items?|packs?|pcs?|pieces?)?\b', clean_for_qty)
        if qty_match:
            val = int(qty_match.group(1))
            if 1 <= val <= 100:
                quantity = val
        else:
            word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
            for word, num in word_to_num.items():
                if re.search(rf'\b{word}\b', clean_for_qty):
                    quantity = num
                    break

        # 2. Extract item descriptor (check exact match or strip command keywords)
        exact_match = None
        for product in catalog:
            if product["name"].lower() in buyer_request_lower:
                exact_match = product
                break

        if exact_match:
            extracted_item = exact_match["name"]
        else:
            clean_item = buyer_request_lower
            clean_item = re.sub(r'^(?:please\s+)?(?:buy|purchase|order|get|find|need|want)\s+(?:me\s+)?', '', clean_item)
            clean_item = re.sub(r'^(?:\d+|one|two|three|four|five)\s*(?:x|boxes?|bags?|units?|items?|packs?|pcs?|pieces?|of)?\s*', '', clean_item)
            clean_item = re.sub(r'\s*(?:under|below|max|within|<|less than|budget of|budget|for)\s*(?:rs\.?|₹|inr)?\s*\d+.*$', '', clean_item)
            extracted_item = clean_item.strip() or buyer_request.strip()

        # 3. Hand off to the goal-based resolver (same function as main pipeline)
        temp_intent = {
            "item": extracted_item,
            "quantity": quantity,
            "price": 0.0,
            "merchant_id": ""
        }
        resolved_product, notes = resolve_goal_based_request(buyer_request, temp_intent, catalog)

        if resolved_product:
            try:
                print(f"[MOCK] Goal-based resolved '{buyer_request}' -> '{resolved_product['name']}', qty: {quantity}")
            except Exception:
                safe_req = buyer_request.replace("₹", "Rs.")
                print(f"[MOCK] Goal-based resolved '{safe_req}' -> '{resolved_product['name']}', qty: {quantity}")
            return {
                "item": resolved_product["name"],
                "price": float(resolved_product["price"]),
                "quantity": quantity,
                "merchant_id": resolved_product["merchant_id"],
                "goal_resolution_notes": notes
            }
        else:
            try:
                print(f"[MOCK] No goal-based match for '{buyer_request}' (extracted item: '{extracted_item}'), qty: {quantity}")
            except Exception:
                safe_req = buyer_request.replace("₹", "Rs.")
                print(f"[MOCK] No goal-based match for '{safe_req}' (extracted item: '{extracted_item}'), qty: {quantity}")
            return {
                "item": extracted_item,
                "price": 0.0,
                "quantity": quantity,
                "merchant_id": "",
                "goal_resolution_notes": notes
            }

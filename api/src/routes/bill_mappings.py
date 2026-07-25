import json
import re
from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response
from src.lib.unit_conversion import canonical_unit, UNIT_TO_BASE


def handle_get_bill_mappings(event, _context):
    try:
        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        qs = event.get("queryStringParameters") or {}
        description = (qs.get("description") or "").strip()
        hsn_code = (qs.get("hsnCode") or "").strip()

        db = get_db()

        if description:
            # Exact match first
            mapping = db.bill_item_mappings.find_one({"billItemDescription": description})
            if mapping:
                return json_response(200, {"mappings": [_format_mapping(mapping)]})

            # Fuzzy search fallback
            try:
                from rapidfuzz import fuzz
                all_mappings = list(db.bill_item_mappings.find())
                scored = []
                for m in all_mappings:
                    score = fuzz.token_sort_ratio(description, m["billItemDescription"])
                    if score >= 60:
                        scored.append((score, m))
                scored.sort(key=lambda x: x[0], reverse=True)
                return json_response(200, {
                    "mappings": [
                        {**_format_mapping(m), "confidence": round(s)}
                        for s, m in scored[:5]
                    ]
                })
            except ImportError:
                pass

        if hsn_code:
            mappings = list(db.bill_item_mappings.find({"hsnCode": hsn_code}))
            return json_response(200, {"mappings": [_format_mapping(m) for m in mappings]})

        # Return all mappings if no filters
        mappings = list(db.bill_item_mappings.find().sort("billItemDescription", 1).limit(100))
        return json_response(200, {"mappings": [_format_mapping(m) for m in mappings]})

    except Exception as exc:
        print("get_bill_mappings error", exc)
        return json_response(500, {"message": "Internal server error."})


def handle_create_bill_mapping(event, _context):
    try:
        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            auth = verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        if auth.get("role") != "admin":
            return json_response(403, {"message": "Admin access required."})

        body = json.loads(event.get("body") or "{}")
        bill_desc = (body.get("billItemDescription") or "").strip()
        hsn_code = (body.get("hsnCode") or "").strip() or None
        inventory_item_id = body.get("inventoryItemId")
        conversion_factor = body.get("conversionFactor")
        conversion_from = (body.get("conversionFromUnit") or "").strip() or None
        conversion_to = (body.get("conversionToUnit") or "").strip() or None

        if not bill_desc or not inventory_item_id:
            return json_response(400, {"message": "billItemDescription and inventoryItemId are required."})

        try:
            item_oid = ObjectId(inventory_item_id)
        except Exception:
            return json_response(400, {"message": "Invalid inventoryItemId."})

        db = get_db()

        # Look up inventory item for denormalized fields
        item = db.items.find_one({"_id": item_oid, "isActive": True})
        if not item:
            return json_response(404, {"message": "Inventory item not found."})

        now = datetime.now(timezone.utc)

        doc = {
            "billItemDescription": bill_desc,
            "hsnCode": hsn_code,
            "inventoryItemId": item_oid,
            "inventoryItemName": item["name"],
            "inventoryItemSku": item["sku"],
            "confirmedBy": ObjectId(auth["userId"]),
            "confirmCount": 1,
            "createdAt": now,
            "updatedAt": now,
        }

        if conversion_factor is not None:
            try:
                doc["conversionFactor"] = float(conversion_factor)
            except (TypeError, ValueError):
                return json_response(400, {"message": "conversionFactor must be a number."})
            doc["conversionFromUnit"] = conversion_from
            doc["conversionToUnit"] = conversion_to

        # Upsert: if mapping for this description exists, update it
        existing = db.bill_item_mappings.find_one({"billItemDescription": bill_desc})
        if existing:
            db.bill_item_mappings.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "inventoryItemId": item_oid,
                        "inventoryItemName": item["name"],
                        "inventoryItemSku": item["sku"],
                        "hsnCode": hsn_code,
                        "conversionFactor": doc.get("conversionFactor"),
                        "conversionFromUnit": doc.get("conversionFromUnit"),
                        "conversionToUnit": doc.get("conversionToUnit"),
                        "confirmedBy": ObjectId(auth["userId"]),
                        "updatedAt": now,
                    },
                    "$inc": {"confirmCount": 1},
                },
            )
            return json_response(200, {
                "message": "Mapping updated.",
                "mapping": _format_mapping({**existing, **doc, "confirmCount": existing.get("confirmCount", 0) + 1}),
            })

        try:
            result = db.bill_item_mappings.insert_one(doc)
        except DuplicateKeyError:
            return json_response(409, {"message": "Mapping for this description already exists."})

        doc["_id"] = result.inserted_id
        return json_response(201, {
            "message": "Mapping created.",
            "mapping": _format_mapping(doc),
        })

    except Exception as exc:
        print("create_bill_mapping error", exc)
        return json_response(500, {"message": "Internal server error."})


def handle_suggest_mappings(event, _context):
    """GET /bill-mappings/suggest?description=... — suggest inventory item mapping for a bill description.

    Parses the bill item description to extract:
    - Core product name (stripped of brand, size, packaging info)
    - Pack size (e.g. "Pack of 12" -> 12 pcs)
    - Weight/volume (e.g. "1 Kg" -> 1000 gms)
    - Suggested SKU and conversion factor

    Returns top suggestions ranked by match confidence.
    """
    try:
        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        qs = event.get("queryStringParameters") or {}
        description = (qs.get("description") or "").strip()
        if not description:
            return json_response(400, {"message": "description query param is required."})

        db = get_db()

        # 1. Check existing confirmed mappings first (exact match)
        exact = db.bill_item_mappings.find_one({"billItemDescription": description})
        if exact:
            return json_response(200, {
                "suggestions": [{
                    "inventoryItemId": str(exact["inventoryItemId"]),
                    "inventoryItemName": exact.get("inventoryItemName"),
                    "inventoryItemSku": exact.get("inventoryItemSku"),
                    "confidence": "exact",
                    "score": 100,
                    "suggestedConversion": {
                        "factor": exact.get("conversionFactor"),
                        "fromUnit": exact.get("conversionFromUnit"),
                        "toUnit": exact.get("conversionToUnit"),
                    } if exact.get("conversionFactor") else None,
                    "source": "confirmed_mapping",
                }],
                "parsed": _parse_description(description),
            })

        # 2. Parse the description for product keywords, pack size, weight
        parsed = _parse_description(description)

        # 3. Fuzzy match against inventory items
        try:
            from rapidfuzz import fuzz
        except ImportError:
            return json_response(200, {
                "suggestions": [],
                "parsed": parsed,
                "message": "Fuzzy matching unavailable (rapidfuzz not installed).",
            })

        items = list(db.items.find({"isActive": True}, {"name": 1, "sku": 1, "defaultUnit": 1, "unitConversions": 1}))
        scored = []

        # Use the extracted product name for matching, fall back to full description
        match_text = parsed.get("productName") or description

        for item in items:
            # Score against both name and SKU
            name_score = fuzz.token_sort_ratio(match_text.lower(), item["name"].lower())
            sku_score = fuzz.token_sort_ratio(match_text.lower(), item.get("sku", "").lower()) * 0.9

            # Bonus: check if any keyword from parsed product name appears in item name/sku
            keyword_bonus = 0
            for kw in parsed.get("keywords", []):
                if kw in item["name"].lower() or kw in item.get("sku", "").lower():
                    keyword_bonus += 10

            score = max(name_score, sku_score) + min(keyword_bonus, 20)
            score = min(score, 100)  # cap at 100

            if score >= 40:
                # Build conversion suggestion based on parsed info
                suggested_conv = _suggest_conversion(parsed, item)
                scored.append({
                    "inventoryItemId": str(item["_id"]),
                    "inventoryItemName": item["name"],
                    "inventoryItemSku": item.get("sku"),
                    "confidence": "high" if score >= 75 else "medium" if score >= 55 else "low",
                    "score": round(score),
                    "suggestedConversion": suggested_conv,
                    "source": "smart_match",
                })

        # Sort by score descending, take top 5
        scored.sort(key=lambda x: x["score"], reverse=True)

        return json_response(200, {
            "suggestions": scored[:5],
            "parsed": parsed,
        })

    except Exception as exc:
        print("suggest_mappings error", exc)
        return json_response(500, {"message": "Internal server error."})


def _parse_description(description: str) -> dict:
    """Parse a HyperPure bill item description to extract product info.

    Examples:
        "Fresh 2 Go - Frozen 10\" Plain Tortilla Wrap (RTC), 768 gm (Pack of 12)"
        -> productName: "Tortilla Wrap", packSize: 12, weight: 768, weightUnit: "gm"

        "Frozen Sweet Corn, 1 Kg"
        -> productName: "Sweet Corn", weight: 1, weightUnit: "kg"
    """
    text = description.strip()

    # Extract pack size: "Pack of 12", "pack of 6", "x12", "12 pcs", "12 pieces"
    pack_size = None
    pack_match = re.search(
        r"(?:pack\s*(?:of|-)?\s*(\d+))|"
        r"(?:(\d+)\s*(?:pcs|pieces|piece|pc|nos|units))|"
        r"(?:x\s*(\d+))",
        text, re.IGNORECASE,
    )
    if pack_match:
        pack_size = int(pack_match.group(1) or pack_match.group(2) or pack_match.group(3))

    # Extract weight/volume: "768 gm", "1 Kg", "500 ml", "950 - 1050 gm", "950-1050gm"
    weight = None
    weight_unit = None
    unit_pattern = r"(?:kg|kgs|kilogram|gm|gms|gram|grams|g|lt|ltr|litre|litres|liter|liters|l|ml|mls)"
    # Try range format first: "950 - 1050 gm" or "950-1050gm"
    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(" + unit_pattern + r")\b",
        text, re.IGNORECASE,
    )
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        weight = (low + high) / 2
        weight_unit = range_match.group(3).lower()
    else:
        # Single value: "768 gm", "1 Kg"
        weight_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(" + unit_pattern + r")\b",
            text, re.IGNORECASE,
        )
        if weight_match:
            weight = float(weight_match.group(1))
            weight_unit = weight_match.group(2).lower()

    # Extract product name by removing noise
    product_name = text

    # Remove parenthetical info like (RTC), (Pack of 12), (Ready to Cook), (Big Size)
    product_name = re.sub(r"\([^)]*\)", "", product_name)

    # Remove weight ranges (e.g. "950 - 1050 gm") BEFORE brand split to avoid
    # the " - " in "950 - 1050" being treated as a brand separator
    product_name = re.sub(
        r"\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?\s*(?:kg|kgs|gm|gms|gram|grams|g|lt|ltr|litre|ml|mls|pcs|pieces|pack)\b",
        "", product_name, flags=re.IGNORECASE,
    )

    # Remove brand prefixes (text before " - " or " -- ")
    brand_split = re.split(r"\s*[-]{1,2}\s+", product_name, maxsplit=1)
    if len(brand_split) > 1:
        product_name = brand_split[-1]

    # Remove remaining single weight/quantity strings
    product_name = re.sub(
        r"\d+(?:\.\d+)?\s*(?:kg|kgs|gm|gms|gram|grams|g|lt|ltr|litre|ml|mls|pcs|pieces|pack)\b",
        "", product_name, flags=re.IGNORECASE,
    )

    # Remove size indicators like 10", 12"
    product_name = re.sub(r'\d+["\u201d]\s*', "", product_name)

    # Remove "Frozen", "Fresh", "Premium", "RTC" prefixes
    product_name = re.sub(
        r"\b(?:frozen|fresh|premium|rtc|ready\s+to\s+cook|ready\s+to\s+eat)\b",
        "", product_name, flags=re.IGNORECASE,
    )

    # Clean up: remove commas, extra spaces, leading/trailing junk
    product_name = re.sub(r"[,]+", " ", product_name)
    product_name = re.sub(r"\s+", " ", product_name).strip()
    product_name = product_name.strip(" -,.")

    # Extract keywords (words >= 3 chars, lowercased)
    keywords = [w.lower() for w in re.findall(r"[a-zA-Z]{3,}", product_name)]

    # Suggest a SKU: take the main product words, lowercase, join with space
    suggested_sku = " ".join(keywords[:3]) if keywords else None

    result = {
        "productName": product_name if product_name else None,
        "keywords": keywords,
        "suggestedSku": suggested_sku,
    }

    if pack_size:
        result["packSize"] = pack_size
    if weight is not None:
        result["weight"] = weight
        result["weightUnit"] = weight_unit

    return result


def _suggest_conversion(parsed: dict, inv_item: dict) -> dict | None:
    """Suggest a conversion factor based on parsed description and inventory item."""
    item_unit = canonical_unit(inv_item.get("defaultUnit", ""))

    # Check if item has existing unit conversions we can reuse
    existing_conversions = inv_item.get("unitConversions") or {}

    pack_size = parsed.get("packSize")
    weight = parsed.get("weight")
    weight_unit = parsed.get("weightUnit")

    # Case 1: Pack of N items, inventory tracks in pcs
    # e.g. "Pack of 12" and item unit is "pcs" -> 1 count = 12 pcs
    if pack_size and item_unit in ("pcs", "pkt"):
        return {
            "factor": pack_size,
            "fromUnit": "pcs",
            "toUnit": item_unit,
            "reason": f"Pack of {pack_size}",
        }

    # Case 2: Weight conversion
    # e.g. "1 Kg" and item tracks in gms -> 1 count = 1000 gms
    if weight and weight_unit:
        canon_weight_unit = canonical_unit(weight_unit)
        base_info = UNIT_TO_BASE.get(canon_weight_unit)

        if base_info and item_unit:
            base_unit, multiplier = base_info
            item_base_info = UNIT_TO_BASE.get(item_unit)

            if item_base_info and item_base_info[0] == base_unit:
                # Same base (both weight or both volume)
                # Convert: weight in bill unit -> item's base unit
                weight_in_base = weight * multiplier
                item_multiplier = item_base_info[1]
                factor = weight_in_base / item_multiplier
                return {
                    "factor": factor,
                    "fromUnit": canon_weight_unit,
                    "toUnit": item_unit,
                    "reason": f"{weight} {weight_unit} = {factor} {item_unit}",
                }

    # Case 3: Check existing conversions on the item
    if existing_conversions:
        for from_unit, factor in existing_conversions.items():
            return {
                "factor": factor,
                "fromUnit": from_unit,
                "toUnit": item_unit,
                "reason": "Previously used conversion",
            }

    return None


def _format_mapping(m: dict) -> dict:
    return {
        "id": str(m["_id"]),
        "billItemDescription": m.get("billItemDescription"),
        "hsnCode": m.get("hsnCode"),
        "inventoryItemId": str(m.get("inventoryItemId", "")),
        "inventoryItemName": m.get("inventoryItemName"),
        "inventoryItemSku": m.get("inventoryItemSku"),
        "conversionFactor": m.get("conversionFactor"),
        "conversionFromUnit": m.get("conversionFromUnit"),
        "conversionToUnit": m.get("conversionToUnit"),
        "confirmCount": m.get("confirmCount", 0),
        "createdAt": m.get("createdAt"),
        "updatedAt": m.get("updatedAt"),
    }

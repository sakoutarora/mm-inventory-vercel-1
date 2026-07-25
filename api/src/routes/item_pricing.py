import json
from datetime import datetime, timezone

from bson import ObjectId

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response
from src.lib.unit_conversion import canonical_unit, convert_to_base


def handle_get_item_pricing(event, _context):
    try:
        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        db = get_db()
        items = list(db.items.find({"isActive": True}).sort("name", 1))

        # Look up categories for display
        cat_ids = list({i["categoryId"] for i in items if i.get("categoryId")})
        categories = {str(c["_id"]): c["name"] for c in db.categories.find({"_id": {"$in": cat_ids}})}

        result = []
        for item in items:
            default_unit = canonical_unit(item.get("defaultUnit"))
            _, base_unit = convert_to_base(1, default_unit)

            result.append({
                "id": str(item["_id"]),
                "sku": item.get("sku"),
                "name": item.get("name"),
                "category": categories.get(str(item.get("categoryId")), ""),
                "categoryId": str(item.get("categoryId", "")),
                "defaultUnit": default_unit,
                "baseUnit": base_unit,
                "basePricePerUnit": item.get("basePricePerUnit"),
                "basePriceUpdatedAt": item.get("basePriceUpdatedAt"),
                "unitConversions": item.get("unitConversions") or {},
            })

        return json_response(200, {"items": result})

    except Exception as exc:
        print("get_item_pricing error", exc)
        return json_response(500, {"message": "Internal server error."})


def handle_update_item_base_price(event, _context):
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

        # Get itemId from path parameters
        path_params = event.get("pathParameters") or {}
        item_id = path_params.get("itemId")
        if not item_id:
            return json_response(400, {"message": "itemId is required."})

        try:
            item_oid = ObjectId(item_id)
        except Exception:
            return json_response(400, {"message": "Invalid itemId."})

        body = json.loads(event.get("body") or "{}")
        price = body.get("price")
        unit = (body.get("unit") or "").strip()

        if price is None or not unit:
            return json_response(400, {"message": "price and unit are required."})

        try:
            price = float(price)
            if price < 0:
                return json_response(400, {"message": "price must be non-negative."})
        except (TypeError, ValueError):
            return json_response(400, {"message": "price must be a number."})

        db = get_db()
        item = db.items.find_one({"_id": item_oid, "isActive": True})
        if not item:
            return json_response(404, {"message": "Item not found."})

        # Convert price to base unit
        # e.g., price=308, unit="kg" → factor=1000 → basePricePerUnit = 308/1000 = 0.308/gm
        canon = canonical_unit(unit)
        base_qty, base_unit = convert_to_base(1, canon)
        if base_qty is None:
            return json_response(400, {"message": f"Unsupported unit: {unit}"})

        base_price_per_unit = price / base_qty

        now = datetime.now(timezone.utc)
        db.items.update_one(
            {"_id": item_oid},
            {"$set": {
                "basePricePerUnit": base_price_per_unit,
                "basePriceUpdatedAt": now,
            }},
        )

        return json_response(200, {
            "message": "Base price updated.",
            "itemId": str(item_oid),
            "basePricePerUnit": base_price_per_unit,
            "baseUnit": base_unit,
            "basePriceUpdatedAt": now,
        })

    except Exception as exc:
        print("update_item_base_price error", exc)
        return json_response(500, {"message": "Internal server error."})

from datetime import datetime, timezone

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response
from src.lib.unit_conversion import canonical_unit, normalize_units


def _parse_branch_code(event):
    query = event.get("queryStringParameters") or {}
    return (query.get("branchCode") or "").strip().upper()


def handle_get_inventory_items(event, _context):
    try:
        if event.get("httpMethod") == "OPTIONS":
            return json_response(200, {"ok": True})

        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            auth = verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        branch_code = _parse_branch_code(event)
        if not branch_code:
            return json_response(400, {"message": "branchCode is required."})

        if auth.get("branchCode") != branch_code and auth.get("role") != "admin":
            return json_response(403, {"message": "Branch access denied."})

        db = get_db()
        branch = db.branches.find_one({"code": branch_code, "isActive": True})
        if not branch:
            return json_response(404, {"message": "Branch not found."})

        categories = list(db.categories.find({"isActive": True}).sort([("displayOrder", 1), ("name", 1)]))
        items = list(db.items.find({"isActive": True}).sort("name", 1))
        current_rows = list(db.inventory_current.find({"branchId": branch["_id"]}))

        current_by_item_id = {str(row["itemId"]): row for row in current_rows}
        category_map = {str(cat["_id"]): cat for cat in categories}

        response_items = []
        for item in items:
            current = current_by_item_id.get(str(item["_id"]))
            category = category_map.get(str(item["categoryId"]))
            response_items.append(
                {
                    "id": str(item["_id"]),
                    "sku": item["sku"],
                    "name": item["name"],
                    "category": category["name"] if category else "Uncategorized",
                    "categoryCode": category["code"] if category else None,
                    "required": bool(item.get("isRequired")),
                    "minThreshold": item.get("minThreshold"),
                    "lastQuantity": str(current.get("quantity")) if current else "",
                    "lastUnit": canonical_unit(current.get("unit")) if current else canonical_unit(item.get("defaultUnit")),
                    "lastUpdatedAt": current.get("updatedAt") if current else None,
                    "allowedUnits": normalize_units(item.get("allowedUnits", [])),
                }
            )

        return json_response(
            200,
            {
                "branch": {
                    "id": str(branch["_id"]),
                    "code": branch["code"],
                    "name": branch["name"],
                },
                "items": response_items,
                "generatedAt": datetime.now(timezone.utc),
            },
        )
    except Exception as exc:
        print("get_inventory_items error", exc)
        return json_response(500, {"message": "Internal server error."})

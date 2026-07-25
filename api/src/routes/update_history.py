from datetime import datetime, timedelta, timezone

from bson import ObjectId

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response


IST = timezone(timedelta(hours=5, minutes=30))


def _format_ist(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def handle_get_update_history(event, _context):
    """GET /inventory-updates/history — list inventory updates with changed items."""
    try:
        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            auth = verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        qs = event.get("queryStringParameters") or {}
        branch_code = (qs.get("branchCode") or "").strip().upper()
        limit = min(int(qs.get("limit", 50)), 200)
        offset = int(qs.get("offset", 0))

        if not branch_code:
            return json_response(400, {"message": "branchCode is required."})

        if auth.get("branchCode") != branch_code and auth.get("role") != "admin":
            return json_response(403, {"message": "Branch access denied."})

        db = get_db()
        branch = db.branches.find_one({"code": branch_code, "isActive": True})
        if not branch:
            return json_response(404, {"message": "Branch not found."})

        updates = list(
            db.inventory_updates.find(
                {"branchId": branch["_id"]},
                {
                    "submittedAt": 1,
                    "createdAt": 1,
                    "branchCode": 1,
                    "updatedBy": 1,
                    "itemCount": 1,
                    "items": 1,
                },
            )
            .sort("submittedAt", -1)
            .skip(offset)
            .limit(limit)
        )

        total = db.inventory_updates.count_documents({"branchId": branch["_id"]})

        # Look up category names
        categories = {str(c["_id"]): c["name"] for c in db.categories.find({"isActive": True})}

        result = []
        for u in updates:
            changed_items = []
            for item in u.get("items", []):
                changed_items.append({
                    "itemId": str(item["itemId"]),
                    "sku": item.get("sku", ""),
                    "name": item.get("name", ""),
                    "category": categories.get(str(item.get("categoryId", "")), ""),
                    "previousQuantity": item.get("previousQuantity"),
                    "previousUnit": item.get("previousUnit"),
                    "previousQuantityBase": item.get("previousQuantityBase"),
                    "newQuantity": item.get("newQuantity"),
                    "newUnit": item.get("newUnit"),
                    "newQuantityBase": item.get("newQuantityBase"),
                    "baseUnit": item.get("baseUnit"),
                    "deltaQuantity": item.get("deltaQuantity"),
                    "deltaQuantityBase": item.get("deltaQuantityBase"),
                    "inputQuantity": item.get("inputQuantity"),
                    "inputUnit": item.get("inputUnit"),
                    "crossedBelowThreshold": item.get("crossedBelowThreshold", False),
                    "minThreshold": item.get("minThreshold"),
                })

            result.append({
                "id": str(u["_id"]),
                "submittedAt": u.get("submittedAt"),
                "submittedAtIST": _format_ist(u.get("submittedAt")),
                "createdAtIST": _format_ist(u.get("createdAt")),
                "branchCode": u.get("branchCode"),
                "updatedBy": u.get("updatedBy", {}).get("username", ""),
                "itemCount": u.get("itemCount", 0),
                "items": changed_items,
            })

        return json_response(200, {
            "updates": result,
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    except Exception as exc:
        print("get_update_history error", exc)
        return json_response(500, {"message": "Internal server error."})


def handle_get_update_detail(event, _context):
    """GET /inventory-updates/{updateId} — get full detail of a single update including snapshot."""
    try:
        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            auth = verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        params = event.get("pathParameters") or {}
        update_id = params.get("updateId")
        if not update_id:
            return json_response(400, {"message": "updateId is required."})

        try:
            update_oid = ObjectId(update_id)
        except Exception:
            return json_response(400, {"message": "Invalid updateId."})

        db = get_db()
        update = db.inventory_updates.find_one({"_id": update_oid})
        if not update:
            return json_response(404, {"message": "Update not found."})

        branch = db.branches.find_one({"_id": update["branchId"]})
        if not branch:
            return json_response(404, {"message": "Branch not found."})

        branch_code = branch["code"]
        if auth.get("branchCode") != branch_code and auth.get("role") != "admin":
            return json_response(403, {"message": "Branch access denied."})

        categories = {str(c["_id"]): c["name"] for c in db.categories.find({"isActive": True})}

        changed_items = []
        for item in update.get("items", []):
            changed_items.append({
                "itemId": str(item["itemId"]),
                "sku": item.get("sku", ""),
                "name": item.get("name", ""),
                "category": categories.get(str(item.get("categoryId", "")), ""),
                "previousQuantity": item.get("previousQuantity"),
                "previousUnit": item.get("previousUnit"),
                "previousQuantityBase": item.get("previousQuantityBase"),
                "newQuantity": item.get("newQuantity"),
                "newUnit": item.get("newUnit"),
                "newQuantityBase": item.get("newQuantityBase"),
                "baseUnit": item.get("baseUnit"),
                "deltaQuantity": item.get("deltaQuantity"),
                "deltaQuantityBase": item.get("deltaQuantityBase"),
                "inputQuantity": item.get("inputQuantity"),
                "inputUnit": item.get("inputUnit"),
                "crossedBelowThreshold": item.get("crossedBelowThreshold", False),
                "minThreshold": item.get("minThreshold"),
            })

        snapshot_items = []
        for s in update.get("snapshot", []):
            snapshot_items.append({
                "itemId": str(s["itemId"]),
                "sku": s.get("sku", ""),
                "name": s.get("name", ""),
                "category": categories.get(str(s.get("categoryId", "")), ""),
                "quantity": s.get("quantity"),
                "unit": s.get("unit"),
                "quantityBase": s.get("quantityBase"),
                "baseUnit": s.get("baseUnit"),
                "inputQuantity": s.get("inputQuantity"),
                "inputUnit": s.get("inputUnit"),
            })

        # Find previous update for this branch to enable comparison
        prev_update = db.inventory_updates.find_one(
            {
                "branchId": update["branchId"],
                "submittedAt": {"$lt": update["submittedAt"]},
            },
            {"_id": 1, "submittedAt": 1, "updatedBy": 1, "itemCount": 1},
            sort=[("submittedAt", -1)],
        )

        prev_info = None
        if prev_update:
            prev_info = {
                "id": str(prev_update["_id"]),
                "submittedAtIST": _format_ist(prev_update.get("submittedAt")),
                "updatedBy": prev_update.get("updatedBy", {}).get("username", ""),
                "itemCount": prev_update.get("itemCount", 0),
            }

        return json_response(200, {
            "update": {
                "id": str(update["_id"]),
                "submittedAt": update.get("submittedAt"),
                "submittedAtIST": _format_ist(update.get("submittedAt")),
                "createdAtIST": _format_ist(update.get("createdAt")),
                "branchCode": branch_code,
                "updatedBy": update.get("updatedBy", {}).get("username", ""),
                "itemCount": update.get("itemCount", 0),
                "items": changed_items,
                "snapshot": snapshot_items,
            },
            "previousUpdate": prev_info,
        })

    except Exception as exc:
        print("get_update_detail error", exc)
        return json_response(500, {"message": "Internal server error."})



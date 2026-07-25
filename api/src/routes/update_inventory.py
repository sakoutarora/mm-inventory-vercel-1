import json
from datetime import datetime, timezone

from bson import ObjectId

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response


def _normalize_number(value):
    try:
        num = float(value)
        if num < 0:
            return None
        return num
    except (TypeError, ValueError):
        return None


def handle_update_inventory(event, _context):
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

        body = json.loads(event.get("body") or "{}")
        branch_code = (body.get("branchCode") or body.get("branch") or "").strip().upper()
        items = body.get("items") if isinstance(body.get("items"), list) else []
        submitted_at_raw = body.get("submittedAt")

        if not branch_code or not items:
            return json_response(400, {"message": "branchCode and non-empty items are required."})

        if auth.get("branchCode") != branch_code and auth.get("role") != "admin":
            return json_response(403, {"message": "Branch access denied."})

        db = get_db()
        branch = db.branches.find_one({"code": branch_code, "isActive": True})
        if not branch:
            return json_response(404, {"message": "Branch not found."})

        prepared_item_ids = []
        prepared_rows = []
        for row in items:
            item_id = row.get("itemId") or row.get("id")
            unit = (row.get("unit") or "").strip()
            quantity = _normalize_number(row.get("quantity"))

            if not item_id or not unit:
                return json_response(400, {"message": "Each item must include itemId/id and unit."})
            if quantity is None:
                return json_response(400, {"message": "Item quantity must be a non-negative number."})

            try:
                oid = ObjectId(item_id)
            except Exception:
                return json_response(400, {"message": f"Invalid item id: {item_id}"})

            prepared_item_ids.append(oid)
            prepared_rows.append({"itemId": oid, "unit": unit, "quantity": quantity})

        item_docs = list(db.items.find({"_id": {"$in": prepared_item_ids}, "isActive": True}))
        if len(item_docs) != len(prepared_rows):
            return json_response(400, {"message": "One or more items are invalid or inactive."})

        item_by_id = {str(doc["_id"]): doc for doc in item_docs}
        current_rows = list(
            db.inventory_current.find({"branchId": branch["_id"], "itemId": {"$in": prepared_item_ids}})
        )
        current_by_item_id = {str(row["itemId"]): row for row in current_rows}

        now = datetime.now(timezone.utc)
        batch_items = []

        for row in prepared_rows:
            item_doc = item_by_id[str(row["itemId"])]
            allowed_units = item_doc.get("allowedUnits", [])
            if row["unit"] not in allowed_units:
                return json_response(
                    400,
                    {"message": f"Invalid unit '{row['unit']}' for item {item_doc['name']}"},
                )

            current = current_by_item_id.get(str(row["itemId"]))
            previous_quantity = float(current["quantity"]) if current else None
            previous_unit = current.get("unit") if current else None
            next_version = int(current.get("version", 0)) + 1 if current else 1

            min_threshold = float(item_doc.get("minThreshold", 0))
            qty = float(row["quantity"])

            db.inventory_current.update_one(
                {"branchId": branch["_id"], "itemId": row["itemId"]},
                {
                    "$set": {
                        "quantity": qty,
                        "unit": row["unit"],
                        "minThreshold": min_threshold,
                        "isBelowThreshold": qty < min_threshold,
                        "updatedBy": ObjectId(auth["userId"]),
                        "updatedAt": now,
                        "version": next_version,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                upsert=True,
            )

            batch_items.append(
                {
                    "itemId": row["itemId"],
                    "sku": item_doc["sku"],
                    "name": item_doc["name"],
                    "categoryId": item_doc["categoryId"],
                    "previousQuantity": previous_quantity,
                    "previousUnit": previous_unit,
                    "newQuantity": qty,
                    "newUnit": row["unit"],
                    "deltaQuantity": None if previous_quantity is None else qty - previous_quantity,
                    "minThreshold": min_threshold,
                    "crossedBelowThreshold": (
                        qty < min_threshold
                        if previous_quantity is None
                        else previous_quantity >= min_threshold and qty < min_threshold
                    ),
                }
            )

        submitted_at = now
        if submitted_at_raw:
            try:
                submitted_at = datetime.fromisoformat(submitted_at_raw.replace("Z", "+00:00"))
            except Exception:
                submitted_at = now

        update_doc = {
            "branchId": branch["_id"],
            "branchCode": branch["code"],
            "updatedBy": {
                "userId": ObjectId(auth["userId"]),
                "username": auth.get("username"),
            },
            "submittedAt": submitted_at,
            "createdAt": now,
            "itemCount": len(batch_items),
            "items": batch_items,
        }

        insert_result = db.inventory_updates.insert_one(update_doc)

        return json_response(
            200,
            {
                "message": "Inventory updated successfully.",
                "updateId": str(insert_result.inserted_id),
                "itemCount": len(batch_items),
                "submittedAt": submitted_at,
            },
        )
    except Exception as exc:
        print("update_inventory error", exc)
        return json_response(500, {"message": "Internal server error."})

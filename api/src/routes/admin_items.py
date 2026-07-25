import json
from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response


def _normalize_units(units):
    if not isinstance(units, list):
        return []
    cleaned = []
    for raw in units:
        unit = str(raw or "").strip().lower()
        if unit and unit not in cleaned:
            cleaned.append(unit)
    return cleaned


def _validate_min_threshold(value):
    try:
        parsed = float(value)
        if parsed < 0:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _require_admin(event):
    token = extract_bearer_token(event)
    if not token:
        return None, json_response(401, {"message": "Missing bearer token."})

    try:
        auth = verify_token(token)
    except Exception:
        return None, json_response(401, {"message": "Invalid token."})

    if auth.get("role") != "admin":
        return None, json_response(403, {"message": "Admin access required."})

    return auth, None


def handle_admin_create_item(event, _context):
    try:
        if event.get("httpMethod") == "OPTIONS":
            return json_response(200, {"ok": True})

        _auth, auth_error = _require_admin(event)
        if auth_error:
            return auth_error

        body = json.loads(event.get("body") or "{}")
        sku = (body.get("sku") or "").strip().upper()
        name = (body.get("name") or "").strip()
        category_code = (body.get("categoryCode") or "").strip().upper()
        default_unit = (body.get("defaultUnit") or "").strip().lower()
        allowed_units = _normalize_units(body.get("allowedUnits"))
        min_threshold = _validate_min_threshold(body.get("minThreshold"))
        is_required = bool(body.get("isRequired", False))

        if not sku or not name or not category_code:
            return json_response(400, {"message": "sku, name and categoryCode are required."})
        if min_threshold is None:
            return json_response(400, {"message": "minThreshold must be a non-negative number."})
        if not default_unit:
            return json_response(400, {"message": "defaultUnit is required."})
        if default_unit not in allowed_units:
            allowed_units = [default_unit] + allowed_units

        db = get_db()
        category = db.categories.find_one({"code": category_code, "isActive": True}, {"_id": 1})
        if not category:
            return json_response(404, {"message": "Category not found."})

        now = datetime.now(timezone.utc)
        doc = {
            "sku": sku,
            "name": name,
            "categoryId": category["_id"],
            "defaultUnit": default_unit,
            "allowedUnits": allowed_units,
            "minThreshold": min_threshold,
            "isRequired": is_required,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }

        try:
            result = db.items.insert_one(doc)
        except DuplicateKeyError:
            return json_response(409, {"message": "Item sku already exists."})

        return json_response(
            201,
            {
                "message": "Item created.",
                "item": {
                    "id": str(result.inserted_id),
                    "sku": sku,
                    "name": name,
                    "categoryCode": category_code,
                    "defaultUnit": default_unit,
                    "allowedUnits": allowed_units,
                    "minThreshold": min_threshold,
                    "isRequired": is_required,
                },
            },
        )
    except Exception as exc:
        print("admin_create_item error", exc)
        return json_response(500, {"message": "Internal server error."})


def handle_admin_update_item(event, _context):
    try:
        if event.get("httpMethod") == "OPTIONS":
            return json_response(200, {"ok": True})

        _auth, auth_error = _require_admin(event)
        if auth_error:
            return auth_error

        body = json.loads(event.get("body") or "{}")
        item_id = (body.get("itemId") or body.get("id") or "").strip()
        if not item_id:
            return json_response(400, {"message": "itemId is required."})

        try:
            item_oid = ObjectId(item_id)
        except Exception:
            return json_response(400, {"message": "Invalid itemId."})

        updates = {}

        if "name" in body:
            name = (body.get("name") or "").strip()
            if not name:
                return json_response(400, {"message": "name cannot be empty."})
            updates["name"] = name

        if "categoryCode" in body:
            category_code = (body.get("categoryCode") or "").strip().upper()
            if not category_code:
                return json_response(400, {"message": "categoryCode cannot be empty."})
            db = get_db()
            category = db.categories.find_one({"code": category_code, "isActive": True}, {"_id": 1})
            if not category:
                return json_response(404, {"message": "Category not found."})
            updates["categoryId"] = category["_id"]

        if "minThreshold" in body:
            min_threshold = _validate_min_threshold(body.get("minThreshold"))
            if min_threshold is None:
                return json_response(400, {"message": "minThreshold must be a non-negative number."})
            updates["minThreshold"] = min_threshold

        if "isRequired" in body:
            updates["isRequired"] = bool(body.get("isRequired"))

        if "defaultUnit" in body:
            default_unit = (body.get("defaultUnit") or "").strip().lower()
            if not default_unit:
                return json_response(400, {"message": "defaultUnit cannot be empty."})
            updates["defaultUnit"] = default_unit

        if "allowedUnits" in body:
            allowed_units = _normalize_units(body.get("allowedUnits"))
            if not allowed_units:
                return json_response(400, {"message": "allowedUnits must contain at least one unit."})
            updates["allowedUnits"] = allowed_units

        if not updates:
            return json_response(400, {"message": "No updatable fields provided."})

        if "defaultUnit" in updates and "allowedUnits" in updates:
            if updates["defaultUnit"] not in updates["allowedUnits"]:
                updates["allowedUnits"] = [updates["defaultUnit"]] + updates["allowedUnits"]

        db = get_db()
        item = db.items.find_one({"_id": item_oid, "isActive": True}, {"_id": 1, "defaultUnit": 1, "allowedUnits": 1})
        if not item:
            return json_response(404, {"message": "Item not found."})

        if "allowedUnits" in updates and "defaultUnit" not in updates:
            existing_default = item.get("defaultUnit")
            if existing_default and existing_default not in updates["allowedUnits"]:
                updates["allowedUnits"] = [existing_default] + updates["allowedUnits"]

        if "defaultUnit" in updates and "allowedUnits" not in updates:
            existing_units = item.get("allowedUnits", [])
            if updates["defaultUnit"] not in existing_units:
                updates["allowedUnits"] = [updates["defaultUnit"]] + [u for u in existing_units if u != updates["defaultUnit"]]

        updates["updatedAt"] = datetime.now(timezone.utc)

        db.items.update_one({"_id": item_oid}, {"$set": updates})

        if "minThreshold" in updates:
            db.inventory_current.update_many(
                {"itemId": item_oid},
                [
                    {
                        "$set": {
                            "minThreshold": updates["minThreshold"],
                            "isBelowThreshold": {"$lt": ["$quantity", updates["minThreshold"]]},
                            "updatedAt": updates["updatedAt"],
                        }
                    }
                ],
            )

        return json_response(200, {"message": "Item updated successfully."})
    except Exception as exc:
        print("admin_update_item error", exc)
        return json_response(500, {"message": "Internal server error."})

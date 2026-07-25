import json
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response


def handle_get_suppliers(event, _context):
    try:
        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        db = get_db()
        suppliers = list(db.suppliers.find({"isActive": True}).sort("name", 1))

        return json_response(200, {
            "suppliers": [
                {
                    "id": str(s["_id"]),
                    "name": s["name"],
                    "type": s.get("type", "generic"),
                    "gstin": s.get("gstin"),
                    "createdAt": s.get("createdAt"),
                }
                for s in suppliers
            ]
        })
    except Exception as exc:
        print("get_suppliers error", exc)
        return json_response(500, {"message": "Internal server error."})


def handle_create_supplier(event, _context):
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
        name = (body.get("name") or "").strip()
        supplier_type = (body.get("type") or "generic").strip().lower()
        gstin = (body.get("gstin") or "").strip() or None

        if not name:
            return json_response(400, {"message": "name is required."})

        if supplier_type not in ("hyperpure", "generic"):
            return json_response(400, {"message": "type must be 'hyperpure' or 'generic'."})

        now = datetime.now(timezone.utc)
        db = get_db()

        doc = {
            "name": name,
            "type": supplier_type,
            "gstin": gstin,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }

        try:
            result = db.suppliers.insert_one(doc)
        except DuplicateKeyError:
            return json_response(409, {"message": "Supplier name already exists."})

        return json_response(201, {
            "message": "Supplier created.",
            "supplier": {
                "id": str(result.inserted_id),
                "name": name,
                "type": supplier_type,
                "gstin": gstin,
            },
        })
    except Exception as exc:
        print("create_supplier error", exc)
        return json_response(500, {"message": "Internal server error."})

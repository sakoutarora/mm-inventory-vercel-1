import json
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response


def handle_admin_create_category(event, _context):
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

        if auth.get("role") != "admin":
            return json_response(403, {"message": "Admin access required."})

        body = json.loads(event.get("body") or "{}")
        code = (body.get("code") or "").strip().upper()
        name = (body.get("name") or "").strip()
        display_order = body.get("displayOrder", 999)

        if not code or not name:
            return json_response(400, {"message": "code and name are required."})

        try:
            display_order = int(display_order)
        except (TypeError, ValueError):
            return json_response(400, {"message": "displayOrder must be an integer."})

        now = datetime.now(timezone.utc)
        db = get_db()

        doc = {
            "code": code,
            "name": name,
            "displayOrder": display_order,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }

        try:
            result = db.categories.insert_one(doc)
        except DuplicateKeyError:
            return json_response(409, {"message": "Category code already exists."})

        return json_response(
            201,
            {
                "message": "Category created.",
                "category": {
                    "id": str(result.inserted_id),
                    "code": code,
                    "name": name,
                    "displayOrder": display_order,
                },
            },
        )
    except Exception as exc:
        print("admin_create_category error", exc)
        return json_response(500, {"message": "Internal server error."})

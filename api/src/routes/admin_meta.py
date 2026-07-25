from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response
from src.lib.unit_conversion import canonical_unit, normalize_units


def handle_admin_meta(event, _context):
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

        db = get_db()

        branches = [
            {"id": str(row["_id"]), "code": row["code"], "name": row.get("name")}
            for row in db.branches.find({"isActive": True}, {"code": 1, "name": 1}).sort("code", 1)
        ]

        categories = [
            {
                "id": str(row["_id"]),
                "code": row["code"],
                "name": row.get("name"),
                "displayOrder": row.get("displayOrder", 999),
            }
            for row in db.categories.find({"isActive": True}, {"code": 1, "name": 1, "displayOrder": 1}).sort(
                [("displayOrder", 1), ("name", 1)]
            )
        ]

        items = [
            {
                "id": str(row["_id"]),
                "sku": row.get("sku"),
                "name": row.get("name"),
                "categoryId": str(row.get("categoryId")) if row.get("categoryId") else None,
                "defaultUnit": canonical_unit(row.get("defaultUnit")),
                "allowedUnits": normalize_units(row.get("allowedUnits", [])),
                "minThreshold": row.get("minThreshold", 0),
                "required": bool(row.get("isRequired")),
                "active": bool(row.get("isActive", True)),
            }
            for row in db.items.find(
                {"isActive": True},
                {
                    "sku": 1,
                    "name": 1,
                    "categoryId": 1,
                    "defaultUnit": 1,
                    "allowedUnits": 1,
                    "minThreshold": 1,
                    "isRequired": 1,
                    "isActive": 1,
                },
            ).sort("name", 1)
        ]

        users = [
            {
                "id": str(row["_id"]),
                "username": row.get("username"),
                "fullName": row.get("fullName"),
                "role": row.get("role"),
                "branchIds": [str(bid) for bid in row.get("branchIds", [])],
                "active": bool(row.get("isActive", True)),
            }
            for row in db.users.find(
                {"isActive": True},
                {"username": 1, "fullName": 1, "role": 1, "branchIds": 1, "isActive": 1},
            ).sort("username", 1)
        ]

        return json_response(200, {"branches": branches, "categories": categories, "items": items, "users": users})
    except Exception as exc:
        print("admin_meta error", exc)
        return json_response(500, {"message": "Internal server error."})

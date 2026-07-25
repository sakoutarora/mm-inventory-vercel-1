from datetime import timedelta, timezone

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


def handle_get_snapshots(event, _context):
    """GET /inventory-updates/snapshots — list inventory update snapshots for food cost picker."""
    try:
        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        qs = event.get("queryStringParameters") or {}
        branch_code = (qs.get("branchCode") or "").strip().upper()
        limit = min(int(qs.get("limit", 500)), 1000)

        if not branch_code:
            return json_response(400, {"message": "branchCode is required."})

        db = get_db()
        branch = db.branches.find_one({"code": branch_code, "isActive": True})
        if not branch:
            return json_response(404, {"message": "Branch not found."})

        updates = list(
            db.inventory_updates.find(
                {"branchId": branch["_id"]},
                {
                    "createdAt": 1,
                    "branchCode": 1,
                    "updatedBy": 1,
                    "itemCount": 1,
                },
            )
            .sort("createdAt", -1)
            .limit(limit)
        )

        return json_response(200, {
            "snapshots": [
                {
                    "id": str(u["_id"]),
                    "createdAt": u.get("createdAt"),
                    "createdAtIST": _format_ist(u.get("createdAt")),
                    "branchCode": u.get("branchCode"),
                    "updatedBy": u.get("updatedBy", {}).get("username", ""),
                    "itemCount": u.get("itemCount", 0),
                }
                for u in updates
            ],
        })

    except Exception as exc:
        print("get_snapshots error", exc)
        return json_response(500, {"message": "Internal server error."})

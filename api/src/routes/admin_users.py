import json
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from src.lib.auth import extract_bearer_token, hash_password, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response


ALLOWED_ROLES = {"admin", "staff"}


def handle_admin_create_user(event, _context):
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
        username = (body.get("username") or "").strip().lower()
        password = (body.get("password") or "").strip()
        full_name = (body.get("fullName") or "").strip()
        role = (body.get("role") or "staff").strip().lower()
        branch_codes = body.get("branchCodes") if isinstance(body.get("branchCodes"), list) else []

        if not username or not password or not full_name or not branch_codes:
            return json_response(400, {"message": "username, password, fullName and branchCodes are required."})
        if role not in ALLOWED_ROLES:
            return json_response(400, {"message": "role must be one of: admin, staff."})

        normalized_branch_codes = []
        for code in branch_codes:
            clean = str(code or "").strip().upper()
            if clean and clean not in normalized_branch_codes:
                normalized_branch_codes.append(clean)

        if not normalized_branch_codes:
            return json_response(400, {"message": "branchCodes must include at least one branch."})

        db = get_db()
        branches = list(
            db.branches.find(
                {"code": {"$in": normalized_branch_codes}, "isActive": True},
                {"_id": 1, "code": 1},
            )
        )
        if len(branches) != len(normalized_branch_codes):
            return json_response(400, {"message": "One or more branchCodes are invalid."})

        branch_ids = [row["_id"] for row in branches]

        now = datetime.now(timezone.utc)
        password_hash = hash_password(password)
        user_doc = {
            "username": username,
            "passwordHash": password_hash,
            "fullName": full_name,
            "role": role,
            "branchIds": branch_ids,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }

        try:
            result = db.users.insert_one(user_doc)
        except DuplicateKeyError:
            return json_response(409, {"message": "Username already exists."})

        return json_response(
            201,
            {
                "message": "User created.",
                "user": {
                    "id": str(result.inserted_id),
                    "username": username,
                    "fullName": full_name,
                    "role": role,
                    "branchCodes": normalized_branch_codes,
                },
            },
        )
    except Exception as exc:
        print("admin_create_user error", exc)
        return json_response(500, {"message": "Internal server error."})

import json

from src.lib.auth import compare_password, sign_token
from src.lib.mongo import get_db
from src.lib.response import json_response


def handle_login(event, _context):
    try:
        if event.get("httpMethod") == "OPTIONS":
            return json_response(200, {"ok": True})

        body = json.loads(event.get("body") or "{}")
        username = (body.get("username") or "").strip().lower()
        password = (body.get("password") or "").strip()
        branch_code = (body.get("branchCode") or body.get("branch") or "").strip().upper()

        if not username or not password or not branch_code:
            return json_response(400, {"message": "username, password and branchCode are required."})

        db = get_db()
        user = db.users.find_one({"username": username, "isActive": True})
        if not user:
            return json_response(401, {"message": "Invalid credentials."})

        branch = db.branches.find_one({"code": branch_code, "isActive": True})
        if not branch:
            return json_response(401, {"message": "Invalid branch."})

        if not compare_password(password, user["passwordHash"]):
            return json_response(401, {"message": "Invalid credentials."})

        user_branch_ids = [str(item) for item in user.get("branchIds", [])]
        if str(branch["_id"]) not in user_branch_ids:
            return json_response(403, {"message": "User does not have access to this branch."})

        token = sign_token(
            {
                "userId": str(user["_id"]),
                "username": user["username"],
                "branchId": str(branch["_id"]),
                "branchCode": branch["code"],
                "role": user.get("role", "staff"),
            }
        )

        return json_response(
            200,
            {
                "token": token,
                "user": {
                    "id": str(user["_id"]),
                    "username": user["username"],
                    "fullName": user.get("fullName"),
                    "role": user.get("role"),
                },
                "branch": {
                    "id": str(branch["_id"]),
                    "code": branch["code"],
                    "name": branch["name"],
                },
            },
        )
    except Exception as exc:
        print("login error", exc)
        return json_response(500, {"message": "Internal server error."})

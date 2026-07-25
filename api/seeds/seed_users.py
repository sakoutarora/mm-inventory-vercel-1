from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from src.lib.auth import hash_password
from src.lib.config import MONGODB_URI, MONGODB_DB


def run():
    load_dotenv()
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]

    try:
        branches = [
            {"code": "MM01", "name": "Gurugram Branch 1", "isActive": True},
        ]

        branch_ids = {}
        now = datetime.now(timezone.utc)

        for branch in branches:
            db.branches.update_one(
                {"code": branch["code"]},
                {
                    "$set": {
                        "name": branch["name"],
                        "isActive": branch["isActive"],
                        "updatedAt": now,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                upsert=True,
            )
            branch_doc = db.branches.find_one({"code": branch["code"]})
            branch_ids[branch["code"]] = branch_doc["_id"]

        users = [
            {
                "username": "dev",
                "password": "admin",
                "fullName": "System Admin",
                "role": "admin",
                "branchCodes": ["MM01", "MM02", "MM03"],
            },
            {
                "username": "staff",
                "password": "1234",
                "fullName": "DEL Kitchen Staff",
                "role": "staff",
                "branchCodes": ["MM01"],
            },
        ]

        for user in users:
            password_hash = hash_password(user["password"])
            mapped_branch_ids = [branch_ids[code] for code in user["branchCodes"] if code in branch_ids]
            db.users.update_one(
                {"username": user["username"]},
                {
                    "$set": {
                        "username": user["username"],
                        "passwordHash": password_hash,
                        "fullName": user["fullName"],
                        "role": user["role"],
                        "branchIds": mapped_branch_ids,
                        "isActive": True,
                        "updatedAt": now,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                upsert=True,
            )

        db.users.create_index("username", unique=True)
        db.branches.create_index("code", unique=True)

        print("Seed users completed.")
        for user in users:
            print(f"- {user['username']} / {user['password']} ({user['role']})")
    finally:
        client.close()


if __name__ == "__main__":
    run()

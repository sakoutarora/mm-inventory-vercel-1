from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from src.lib.config import MONGODB_URI, MONGODB_DB


def run():
    load_dotenv()
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]

    now = datetime.now(timezone.utc)

    suppliers = [
        {
            "name": "Zomato Hyperpure",
            "type": "hyperpure",
            "gstin": None,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        },
    ]

    for supplier in suppliers:
        db.suppliers.update_one(
            {"name": supplier["name"]},
            {"$set": supplier, "$setOnInsert": {"createdAt": now}},
            upsert=True,
        )
        print(f"  Upserted supplier: {supplier['name']}")

    print("Supplier seeding complete.")
    client.close()


if __name__ == "__main__":
    run()

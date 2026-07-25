from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from src.lib.config import MONGODB_URI, MONGODB_DB


def run():
    load_dotenv()
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]

    try:
        now = datetime.now(timezone.utc)

        categories = [
            {"code": "DRY", "name": "Dry Goods", "displayOrder": 1},
            {"code": "VEG", "name": "Vegetables", "displayOrder": 2},
            {"code": "DAI", "name": "Dairy", "displayOrder": 3},
            {"code": "PRO", "name": "Protein", "displayOrder": 4},
            {"code": "SPI", "name": "Spices", "displayOrder": 5},
        ]

        category_ids = {}
        for category in categories:
            db.categories.update_one(
                {"code": category["code"]},
                {
                    "$set": {
                        "name": category["name"],
                        "displayOrder": category["displayOrder"],
                        "isActive": True,
                        "updatedAt": now,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                upsert=True,
            )
            doc = db.categories.find_one({"code": category["code"]})
            category_ids[category["code"]] = doc["_id"]

        items = [
            {"sku": "DRY-RICE", "name": "Rice", "categoryCode": "DRY", "defaultUnit": "kg", "allowedUnits": ["kg", "g"], "minThreshold": 10, "isRequired": True},
            {"sku": "DRY-LENTIL", "name": "Lentils", "categoryCode": "DRY", "defaultUnit": "kg", "allowedUnits": ["kg", "g"], "minThreshold": 5, "isRequired": True},
            {"sku": "VEG-TOMATO", "name": "Tomato", "categoryCode": "VEG", "defaultUnit": "kg", "allowedUnits": ["kg", "g", "items"], "minThreshold": 8, "isRequired": True},
            {"sku": "VEG-ONION", "name": "Onion", "categoryCode": "VEG", "defaultUnit": "kg", "allowedUnits": ["kg", "g", "items"], "minThreshold": 8, "isRequired": True},
            {"sku": "DAI-MILK", "name": "Milk", "categoryCode": "DAI", "defaultUnit": "litre", "allowedUnits": ["litre", "ml"], "minThreshold": 6, "isRequired": True},
            {"sku": "DAI-PANEER", "name": "Paneer", "categoryCode": "DAI", "defaultUnit": "kg", "allowedUnits": ["kg", "g"], "minThreshold": 2, "isRequired": False},
            {"sku": "PRO-EGG", "name": "Egg", "categoryCode": "PRO", "defaultUnit": "items", "allowedUnits": ["items", "tray"], "minThreshold": 30, "isRequired": False},
            {"sku": "SPI-CHILI", "name": "Red Chili Powder", "categoryCode": "SPI", "defaultUnit": "kg", "allowedUnits": ["kg", "g"], "minThreshold": 1, "isRequired": False},
            {"sku": "SPI-TURMERIC", "name": "Turmeric Powder", "categoryCode": "SPI", "defaultUnit": "kg", "allowedUnits": ["kg", "g"], "minThreshold": 1, "isRequired": False},
        ]

        for item in items:
            db.items.update_one(
                {"sku": item["sku"]},
                {
                    "$set": {
                        "name": item["name"],
                        "categoryId": category_ids[item["categoryCode"]],
                        "defaultUnit": item["defaultUnit"],
                        "allowedUnits": item["allowedUnits"],
                        "minThreshold": item["minThreshold"],
                        "isRequired": item["isRequired"],
                        "isActive": True,
                        "updatedAt": now,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                upsert=True,
            )

        db.categories.create_index("code", unique=True)
        db.items.create_index("sku", unique=True)
        db.items.create_index([("categoryId", 1), ("isActive", 1)])

        print("Seed master data completed.")
        print(f"Categories upserted: {len(categories)}")
        print(f"Items upserted: {len(items)}")
    finally:
        client.close()


if __name__ == "__main__":
    run()

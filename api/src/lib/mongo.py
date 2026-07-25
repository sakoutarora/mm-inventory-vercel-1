from pymongo import MongoClient
from src.lib.config import MONGODB_URI, MONGODB_DB

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is not None:
        return _db

    _client = MongoClient(MONGODB_URI, maxPoolSize=10)
    _db = _client[MONGODB_DB]
    ensure_indexes(_db)
    return _db


def ensure_indexes(db):
    db.users.create_index("username", unique=True)
    db.users.create_index([("isActive", 1), ("username", 1)])
    db.branches.create_index("code", unique=True)
    db.branches.create_index([("isActive", 1), ("code", 1)])
    db.categories.create_index("code", unique=True)
    db.categories.create_index([("isActive", 1), ("displayOrder", 1), ("name", 1)])
    db.items.create_index("sku", unique=True)
    db.items.create_index([("categoryId", 1), ("isActive", 1)])
    db.items.create_index([("isActive", 1), ("name", 1)])
    db.inventory_current.create_index([("branchId", 1), ("itemId", 1)], unique=True)
    db.inventory_current.create_index([("branchId", 1), ("isBelowThreshold", 1)])
    db.inventory_updates.create_index([("branchId", 1), ("submittedAt", -1)])
    db.inventory_updates.create_index([("items.itemId", 1), ("submittedAt", -1)])

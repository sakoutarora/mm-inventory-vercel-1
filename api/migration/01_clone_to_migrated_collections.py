import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lib.config import MONGODB_DB, MONGODB_URI

SRC_ITEMS = "items"
SRC_CURRENT = "inventory_current"
SRC_UPDATES = "inventory_updates"

DST_ITEMS = "items_migrated"
DST_CURRENT = "inventory_current_migrated"
DST_UPDATES = "inventory_updates_migrated"


BATCH_SIZE = 1000


def _copy_collection(db, source_name: str, target_name: str, transform=None) -> int:
    source = db[source_name]
    target = db[target_name]

    total = 0
    batch = []
    for doc in source.find({}):
        out_doc = transform(doc) if transform else doc
        if out_doc is None:
            continue
        batch.append(out_doc)
        if len(batch) >= BATCH_SIZE:
            target.insert_many(batch, ordered=False)
            total += len(batch)
            batch = []

    if batch:
        target.insert_many(batch, ordered=False)
        total += len(batch)

    return total


def _transform_current(doc: dict) -> dict:
    out = dict(doc)
    out.pop("minThreshold", None)
    out.pop("minThresholdBase", None)
    return out


def _ensure_target_empty(db, target_name: str, reset_targets: bool):
    target = db[target_name]
    if target.estimated_document_count() > 0:
        if not reset_targets:
            raise RuntimeError(
                f"Target collection '{target_name}' is not empty. "
                "Use --reset-targets to drop and recreate migrated collections."
            )
        target.drop()


def run(reset_targets: bool = False):
    load_dotenv()
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]

    try:
        for name in (DST_ITEMS, DST_CURRENT, DST_UPDATES):
            _ensure_target_empty(db, name, reset_targets)

        now = datetime.now(timezone.utc)

        copied_items = _copy_collection(db, SRC_ITEMS, DST_ITEMS)
        copied_current = _copy_collection(db, SRC_CURRENT, DST_CURRENT, transform=_transform_current)
        copied_updates = _copy_collection(db, SRC_UPDATES, DST_UPDATES)

        db[DST_ITEMS].create_index("sku", unique=True)
        db[DST_ITEMS].create_index([("categoryId", 1), ("isActive", 1)])
        db[DST_ITEMS].create_index([("isActive", 1), ("name", 1)])

        db[DST_CURRENT].create_index([("branchId", 1), ("itemId", 1)], unique=True)
        db[DST_CURRENT].create_index([("branchId", 1), ("isBelowThreshold", 1)])

        db[DST_UPDATES].create_index([("branchId", 1), ("submittedAt", -1)])
        db[DST_UPDATES].create_index([("items.itemId", 1), ("submittedAt", -1)])

        print("Migration clone complete")
        print(f"- {SRC_ITEMS} -> {DST_ITEMS}: {copied_items} docs")
        print(f"- {SRC_CURRENT} -> {DST_CURRENT}: {copied_current} docs")
        print(f"- {SRC_UPDATES} -> {DST_UPDATES}: {copied_updates} docs")
        print(f"- Completed at: {now.isoformat()}")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Clone production collections into migrated collections without mutating originals, "
            "and strip minThreshold/minThresholdBase from inventory_current_migrated."
        )
    )
    parser.add_argument(
        "--reset-targets",
        action="store_true",
        help="Drop migrated target collections first if they already exist.",
    )
    args = parser.parse_args()
    run(reset_targets=args.reset_targets)

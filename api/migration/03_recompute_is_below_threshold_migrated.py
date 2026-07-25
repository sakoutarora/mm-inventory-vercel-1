import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lib.config import MONGODB_DB, MONGODB_URI

ITEMS_COLLECTION = "items_migrated"
CURRENT_COLLECTION = "inventory_current_migrated"
BATCH_SIZE = 1000


def run(dry_run: bool = False):
    load_dotenv()
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]

    try:
        items = list(db[ITEMS_COLLECTION].find({}, {"_id": 1, "minThreshold": 1}))
        if not items:
            raise RuntimeError(f"No items found in '{ITEMS_COLLECTION}'.")

        threshold_by_item = {item["_id"]: float(item.get("minThreshold") or 0.0) for item in items}

        now = datetime.now(timezone.utc)
        processed = 0
        flagged_true = 0
        updates_prepared = 0
        updates_applied = 0
        missing_item_refs = 0
        ops = []

        cursor = db[CURRENT_COLLECTION].find({}, {"_id": 1, "itemId": 1, "quantityBase": 1, "quantity": 1})
        for row in cursor:
            processed += 1
            item_id = row.get("itemId")
            if item_id not in threshold_by_item:
                missing_item_refs += 1
                continue

            threshold = threshold_by_item[item_id]
            qty_val = row.get("quantityBase") if row.get("quantityBase") is not None else row.get("quantity")
            qty = float(qty_val or 0.0)
            is_below = qty < threshold
            if is_below:
                flagged_true += 1

            updates_prepared += 1
            if not dry_run:
                ops.append(
                    UpdateOne(
                        {"_id": row["_id"]},
                        {"$set": {"isBelowThreshold": is_below, "updatedAt": now}},
                    )
                )

                if len(ops) >= BATCH_SIZE:
                    result = db[CURRENT_COLLECTION].bulk_write(ops, ordered=False)
                    updates_applied += result.modified_count
                    ops = []

        if not dry_run and ops:
            result = db[CURRENT_COLLECTION].bulk_write(ops, ordered=False)
            updates_applied += result.modified_count

        print("Recompute complete for migrated inventory_current")
        print(f"- Collection: {CURRENT_COLLECTION}")
        print(f"- Processed rows: {processed}")
        print(f"- Rows with valid item threshold: {updates_prepared}")
        print(f"- Rows marked below threshold: {flagged_true}")
        print(f"- Rows missing matching item in {ITEMS_COLLECTION}: {missing_item_refs}")
        print(f"- Rows modified: {updates_applied}")
        print(f"- Dry run: {dry_run}")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Recompute inventory_current_migrated.isBelowThreshold from items_migrated.minThreshold "
            "without touching live collections."
        )
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute counts only; do not write updates.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

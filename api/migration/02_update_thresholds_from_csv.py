import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.lib.config import MONGODB_DB, MONGODB_URI
from src.lib.unit_conversion import canonical_unit, convert_to_base, normalize_units

CSV_PATH = "/Users/sakshamarora/Downloads/Inventory_Rista - inventory items.csv"
ITEMS_COLLECTION = "items_migrated"
CURRENT_COLLECTION = "inventory_current_migrated"


def _parse_min_quantity(raw: str):
    raw = (raw or "").strip()
    if not raw or raw == "0":
        return 0.0, None

    frac_match = re.match(r"(\d+)\s*/\s*(\d+)", raw)
    if frac_match:
        qty = float(frac_match.group(1)) / float(frac_match.group(2))
        remainder = raw[frac_match.end():].strip()
        unit = canonical_unit(remainder.split()[0]) if remainder else None
        return qty, unit

    num_match = re.match(r"([\d.]+)", raw)
    if num_match:
        qty = float(num_match.group(1))
        remainder = raw[num_match.end():].strip()
        unit = canonical_unit(remainder.split()[0]) if remainder else None
        return qty, unit

    return 0.0, None


def _norm_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _infer_unit_for_item(item_doc: dict, parsed_unit: str | None) -> str | None:
    default_unit = canonical_unit(item_doc.get("defaultUnit"))
    allowed_units = normalize_units(item_doc.get("allowedUnits", []))
    if default_unit and default_unit not in allowed_units:
        allowed_units = [default_unit] + allowed_units

    item_base = None
    if default_unit:
        _, item_base = convert_to_base(1.0, default_unit)

    parsed = canonical_unit(parsed_unit) if parsed_unit else None
    if parsed:
        _, parsed_base = convert_to_base(1.0, parsed)
        if parsed_base and item_base and parsed_base == item_base:
            return parsed
        if parsed in allowed_units:
            return parsed

    if default_unit:
        return default_unit
    return allowed_units[0] if allowed_units else None


def _read_csv_rows():
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # CSV headers in the source file include trailing spaces (for example "Min quantity ").
            # Normalize header keys so downstream lookups are stable.
            normalized = {(k.strip() if isinstance(k, str) else k): v for k, v in row.items()}
            rows.append(normalized)
    return rows


def run(dry_run: bool = False):
    load_dotenv()
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]

    try:
        items = list(db[ITEMS_COLLECTION].find({"isActive": True}, {"name": 1, "defaultUnit": 1, "allowedUnits": 1}))
        if not items:
            raise RuntimeError(
                f"No active items found in '{ITEMS_COLLECTION}'. Run migration step 1 first."
            )

        items_by_name = defaultdict(list)
        for item in items:
            items_by_name[_norm_key(item.get("name", ""))].append(item)

        rows = _read_csv_rows()

        now = datetime.now(timezone.utc)
        item_updates = 0
        flag_updates = 0
        skipped = 0
        skipped_no_unique_item_match = 0
        skipped_no_unit = 0
        skipped_bad_conversion = 0

        for row in rows:
            item_name = (row.get("ITEM NAME") or "").strip()
            if not item_name:
                continue

            matched = items_by_name.get(_norm_key(item_name), [])
            if len(matched) != 1:
                skipped += 1
                skipped_no_unique_item_match += 1
                continue

            item_doc = matched[0]
            qty_value, qty_unit = _parse_min_quantity(row.get("Min quantity"))
            source_unit = _infer_unit_for_item(item_doc, qty_unit)
            if not source_unit:
                skipped += 1
                skipped_no_unit += 1
                continue

            threshold_base, threshold_base_unit = convert_to_base(qty_value, source_unit)
            if threshold_base is None or threshold_base_unit is None:
                skipped += 1
                skipped_bad_conversion += 1
                continue

            if not dry_run:
                db[ITEMS_COLLECTION].update_one(
                    {"_id": item_doc["_id"]},
                    {"$set": {"minThreshold": threshold_base, "updatedAt": now}},
                )

                result = db[CURRENT_COLLECTION].update_many(
                    {"itemId": item_doc["_id"]},
                    [
                        {
                            "$set": {
                                "isBelowThreshold": {
                                    "$lt": [{"$ifNull": ["$quantityBase", "$quantity"]}, threshold_base]
                                },
                                "updatedAt": now,
                            }
                        }
                    ],
                )
                flag_updates += result.modified_count

            item_updates += 1

        print("Threshold CSV migration complete")
        print(f"- CSV path: {CSV_PATH}")
        print(f"- Items updated in {ITEMS_COLLECTION}: {item_updates}")
        print(f"- Inventory flags updated in {CURRENT_COLLECTION}: {flag_updates}")
        print(f"- Skipped rows (no unique item match or bad unit): {skipped}")
        print(f"  - no unique item match: {skipped_no_unique_item_match}")
        print(f"  - no usable unit: {skipped_no_unit}")
        print(f"  - conversion failed: {skipped_bad_conversion}")
        print(f"- Dry run: {dry_run}")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Read CSV min quantities and update minThreshold in items_migrated, then recompute "
            "isBelowThreshold in inventory_current_migrated."
        )
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and match only; do not write updates.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

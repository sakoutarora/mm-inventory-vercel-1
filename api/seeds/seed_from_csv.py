import csv
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from src.lib.config import MONGODB_URI, MONGODB_DB
from src.lib.unit_conversion import canonical_unit, convert_to_base, normalize_units

CSV_PATH = "/Users/sakshamarora/Downloads/Inventory_Rista - inventory items.csv"


def _make_code(name):
    """Generate a short uppercase code from a category/item name."""
    words = re.sub(r"[^a-zA-Z0-9 ]", "", name).split()
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(w[0] for w in words).upper()


def _make_sku(category_code, item_name):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", item_name).strip("-").upper()
    return f"{category_code}-{slug}"


def _parse_min_quantity(raw):
    """Extract numeric quantity + optional unit from strings like '1.5 Kg', '500 gms', '1/2 lt'."""
    raw = (raw or "").strip()
    if not raw or raw == "0":
        return 0.0, None

    # Handle fractions like "1/2 Btl"
    frac_match = re.match(r"(\d+)\s*/\s*(\d+)", raw)
    if frac_match:
        qty = float(frac_match.group(1)) / float(frac_match.group(2))
        remainder = raw[frac_match.end():].strip()
        unit = canonical_unit(remainder.split()[0]) if remainder else None
        return qty, unit

    # Handle "As and when" or other non-numeric
    num_match = re.match(r"([\d.]+)", raw)
    if num_match:
        qty = float(num_match.group(1))
        remainder = raw[num_match.end():].strip()
        unit = canonical_unit(remainder.split()[0]) if remainder else None
        return qty, unit

    return 0.0, None


def run():
    load_dotenv()
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]

    try:
        now = datetime.now(timezone.utc)

        # --- Step 1: Clear inventory state and history ---
        del_current = db.inventory_current.delete_many({})
        del_updates = db.inventory_updates.delete_many({})
        print(f"Deleted {del_current.deleted_count} inventory_current docs")
        print(f"Deleted {del_updates.deleted_count} inventory_updates docs")

        # --- Step 2: Deactivate all existing categories & items ---
        db.categories.update_many({}, {"$set": {"isActive": False, "updatedAt": now}})
        db.items.update_many({}, {"$set": {"isActive": False, "updatedAt": now}})
        print("Deactivated all existing categories and items")

        # --- Step 3: Read CSV ---
        rows = []
        with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        # --- Step 4: Extract and upsert categories ---
        category_names = list(dict.fromkeys(
            (row["Category"] or "").strip() for row in rows if (row.get("Category") or "").strip()
        ))

        # Generate unique codes
        used_codes = set()
        category_code_map = {}
        for name in category_names:
            code = _make_code(name)
            # Ensure uniqueness by appending digits if needed
            base_code = code
            counter = 2
            while code in used_codes:
                code = f"{base_code}{counter}"
                counter += 1
            used_codes.add(code)
            category_code_map[name] = code

        category_ids = {}
        for order, name in enumerate(category_names, start=1):
            code = category_code_map[name]
            db.categories.update_one(
                {"code": code},
                {
                    "$set": {
                        "name": name,
                        "displayOrder": order,
                        "isActive": True,
                        "updatedAt": now,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                upsert=True,
            )
            doc = db.categories.find_one({"code": code})
            category_ids[name] = doc["_id"]

        print(f"Upserted {len(category_names)} categories")

        # --- Step 5: Upsert items from CSV ---
        used_skus = set()
        item_count = 0
        for row in rows:
            item_name = (row.get("ITEM NAME") or "").strip()
            cat_name = (row.get("Category") or "").strip()
            if not item_name or not cat_name:
                continue

            cat_code = category_code_map[cat_name]
            cat_id = category_ids[cat_name]

            sku = _make_sku(cat_code, item_name)
            base_sku = sku
            counter = 2
            while sku in used_skus:
                sku = f"{base_sku}-{counter}"
                counter += 1
            used_skus.add(sku)

            raw_unit = (row.get("Consumption Unit") or "").strip()
            # Split entries like "kg/gms" into valid canonical units.
            units = normalize_units([u.strip() for u in raw_unit.split("/") if u.strip()])
            if not units:
                units = ["gms"]
            allowed_units = list(dict.fromkeys(units))

            is_required = (row.get("Flag on ordering") or "").strip().upper() == "TRUE"
            min_quantity_value, min_quantity_unit = _parse_min_quantity(row.get("Min quantity"))
            threshold_source_unit = min_quantity_unit if min_quantity_unit in allowed_units else allowed_units[0]
            min_threshold, base_unit = convert_to_base(min_quantity_value, threshold_source_unit)
            if min_threshold is None or base_unit is None:
                min_threshold = 0.0
                base_unit = allowed_units[0]
            if base_unit not in allowed_units:
                allowed_units = [base_unit] + allowed_units
            price_raw = (row.get("PRICE") or "").strip()
            price = float(price_raw) if price_raw else 0.0

            db.items.update_one(
                {"sku": sku},
                {
                    "$set": {
                        "name": item_name,
                        "categoryId": cat_id,
                        "defaultUnit": base_unit,
                        "allowedUnits": allowed_units,
                        "minThreshold": min_threshold,
                        "isRequired": is_required,
                        "price": price,
                        "isActive": True,
                        "updatedAt": now,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                upsert=True,
            )
            item_count += 1

        print(f"Upserted {item_count} items")
        print("Seed from CSV completed.")

    finally:
        client.close()


if __name__ == "__main__":
    run()

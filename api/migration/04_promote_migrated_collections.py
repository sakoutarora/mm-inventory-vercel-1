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

LIVE_TO_MIGRATED = {
    "items": "items_migrated",
    "inventory_current": "inventory_current_migrated",
    "inventory_updates": "inventory_updates_migrated",
}


def _require_collection(db, name: str):
    if name not in db.list_collection_names():
        raise RuntimeError(f"Required collection '{name}' does not exist.")


def run():
    load_dotenv()
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]

    try:
        for live, migrated in LIVE_TO_MIGRATED.items():
            _require_collection(db, live)
            _require_collection(db, migrated)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        legacy_names = {}

        for live in LIVE_TO_MIGRATED:
            legacy_name = f"{live}_legacy_{ts}"
            if legacy_name in db.list_collection_names():
                raise RuntimeError(
                    f"Legacy collection '{legacy_name}' already exists. Re-run in a new second."
                )
            legacy_names[live] = legacy_name

        for live, legacy in legacy_names.items():
            db[live].rename(legacy)

        for live, migrated in LIVE_TO_MIGRATED.items():
            db[migrated].rename(live)

        print("Promotion complete.")
        print("Live collections now point to migrated data.")
        print("Legacy collections:")
        for live, legacy in legacy_names.items():
            print(f"- {live} -> {legacy}")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Rename current live collections to timestamped legacy collections and promote migrated collections "
            "to live names."
        )
    )
    parser.parse_args()
    run()

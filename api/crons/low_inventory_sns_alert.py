#!/usr/bin/env python3
"""Send a daily inventory alert via AWS SNS.

Shows the top 20 items per branch ranked by estimated days to depletion,
based on consumption data from the last 15 days.

Usage:
  python3 crons/low_inventory_sns_alert.py
  python3 crons/low_inventory_sns_alert.py --dry-run

Required env vars:
  - MONGODB_URI
  - MONGODB_DB
  - SNS_TOPIC_ARN
Optional env vars:
  - AWS_REGION (default: ap-south-1)
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pymongo import MongoClient

try:
    import boto3
except ImportError as exc:  # pragma: no cover
    raise SystemExit("boto3 is required for SNS publishing. Install with: pip install boto3") from exc

LOOKBACK_DAYS = 15
TOP_N = 20
REPORT_TZ = ZoneInfo("Asia/Kolkata")
CRITICAL_DAYS = 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send inventory depletion alert via SNS.")
    parser.add_argument("--dry-run", action="store_true", help="Print the message instead of publishing to SNS.")
    return parser.parse_args()


def _format_number(value: Any) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else "-"


def _format_date(dt: datetime) -> str:
    return dt.astimezone(REPORT_TZ).strftime("%d %b")


def _get_consumption_data(db: Any) -> list[dict]:
    """Run aggregation on inventory_updates to get consumption rates and last 3 updates."""
    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(days=LOOKBACK_DAYS)
    tz_str = str(REPORT_TZ)

    pipeline = [
        {"$match": {"submittedAt": {"$gte": window_start, "$lte": now_utc}}},
        {"$unwind": "$items"},
        {
            "$addFields": {
                "effectiveDelta": {"$ifNull": ["$items.deltaQuantityBase", "$items.deltaQuantity"]},
                "effectiveNewQuantity": {"$ifNull": ["$items.newQuantityBase", "$items.newQuantity"]},
                "effectiveUnit": {"$ifNull": ["$items.baseUnit", "$items.newUnit"]},
            }
        },
        {"$sort": {"submittedAt": 1, "_id": 1}},
        {
            "$group": {
                "_id": {"branchId": "$branchId", "branchCode": "$branchCode", "itemId": "$items.itemId"},
                "itemName": {"$last": "$items.name"},
                "sku": {"$last": "$items.sku"},
                "unit": {"$last": "$effectiveUnit"},
                "firstUpdateDate": {
                    "$first": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$submittedAt", "timezone": tz_str}
                    }
                },
                "lastUpdateDate": {
                    "$last": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$submittedAt", "timezone": tz_str}
                    }
                },
                "totalConsumed": {
                    "$sum": {
                        "$cond": [
                            {"$lt": ["$effectiveDelta", 0]},
                            {"$multiply": [-1, "$effectiveDelta"]},
                            0,
                        ]
                    }
                },
                "updateCount": {"$sum": 1},
                "allUpdates": {
                    "$push": {
                        "submittedAt": "$submittedAt",
                        "quantity": "$effectiveNewQuantity",
                        "unit": "$effectiveUnit",
                    }
                },
            }
        },
        {
            "$project": {
                "branchId": "$_id.branchId",
                "branchCode": "$_id.branchCode",
                "itemId": "$_id.itemId",
                "itemName": 1,
                "sku": 1,
                "unit": 1,
                "totalConsumed": 1,
                "updateCount": 1,
                "elapsedDays": {
                    "$max": [
                        1,
                        {
                            "$dateDiff": {
                                "startDate": {
                                    "$dateFromString": {
                                        "dateString": "$firstUpdateDate",
                                        "format": "%Y-%m-%d",
                                        "timezone": tz_str,
                                    }
                                },
                                "endDate": {
                                    "$dateFromString": {
                                        "dateString": "$lastUpdateDate",
                                        "format": "%Y-%m-%d",
                                        "timezone": tz_str,
                                    }
                                },
                                "unit": "day",
                                "timezone": tz_str,
                            }
                        },
                    ]
                },
                "lastThreeUpdates": {"$slice": ["$allUpdates", -3]},
            }
        },
        {"$match": {"updateCount": {"$gt": 1}}},
        {
            "$addFields": {
                "consumptionRatePerDay": {
                    "$cond": [
                        {"$gt": ["$elapsedDays", 0]},
                        {"$divide": ["$totalConsumed", "$elapsedDays"]},
                        0,
                    ]
                }
            }
        },
        {"$match": {"consumptionRatePerDay": {"$gt": 0}}},
    ]

    return list(db.inventory_updates.aggregate(pipeline, allowDiskUse=False))


def _build_item_block(idx: int, item: dict) -> str:
    """Format a single item block for the email."""
    lines = []

    current_qty = item["current_qty"]
    unit = item["unit"]
    rate = item["rate_per_day"]
    days_left = item["days_left"]
    min_threshold = item.get("min_threshold")

    # Status tag
    try:
        is_out = float(current_qty) == 0
    except (TypeError, ValueError):
        is_out = False

    if is_out:
        tag = "  !! OUT OF STOCK"
    elif days_left is not None and days_left <= CRITICAL_DAYS:
        tag = "  !! CRITICAL"
    else:
        tag = ""

    lines.append(f"  {idx}. {item['name']}  [{item['sku']}]{tag}")

    # Stock line
    stock_str = "OUT OF STOCK" if is_out else f"{_format_number(current_qty)} {unit}"
    min_str = f"Min: {_format_number(min_threshold)} {unit}" if min_threshold is not None else "Min: -"
    lines.append(f"     Stock: {stock_str}  |  {min_str}")

    # Consumption line
    rate_str = f"{_format_number(rate)} {unit}/day"
    if days_left is not None:
        if days_left == 0:
            days_str = "0 days left"
        else:
            days_str = f"~{_format_number(days_left)} days left"
    else:
        days_str = "N/A"
    lines.append(f"     Usage: {rate_str}  |  {days_str}")

    # Last 3 updates
    last_updates = item.get("last_updates", [])
    if last_updates:
        lines.append("     Recent Updates:")
        for upd in last_updates:
            lines.append(f"       - {upd['date']}: {_format_number(upd['quantity'])} {upd['unit']}")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    load_dotenv()
    args = _parse_args()

    mongodb_uri = os.getenv("MONGODB_URI")
    mongodb_db = os.getenv("MONGODB_DB", "inventory")
    sns_topic_arn = os.getenv("SNS_TOPIC_ARN")
    aws_region = os.getenv("AWS_REGION", "ap-south-1")

    if not mongodb_uri:
        raise SystemExit("Missing MONGODB_URI")
    if not args.dry_run and not sns_topic_arn:
        raise SystemExit("Missing SNS_TOPIC_ARN")

    client = MongoClient(mongodb_uri, maxPoolSize=10)
    db = client[mongodb_db]

    # Step 1: Get consumption data from inventory_updates
    consumption_rows = _get_consumption_data(db)
    if not consumption_rows:
        print("No consumption data found in the last 15 days. No alert sent.")
        return

    # Step 2: Get current stock for all items with consumption data
    item_branch_pairs = [
        {"branchId": row["branchId"], "itemId": row["itemId"]}
        for row in consumption_rows
    ]

    # Fetch current inventory for these items
    branch_ids = list({row["branchId"] for row in consumption_rows})
    item_ids = list({row["itemId"] for row in consumption_rows})

    current_stock = {}
    for doc in db.inventory_current.find(
        {"branchId": {"$in": branch_ids}, "itemId": {"$in": item_ids}},
        {"branchId": 1, "itemId": 1, "quantity": 1, "quantityBase": 1, "unit": 1},
    ):
        qty = doc.get("quantityBase") if doc.get("quantityBase") is not None else doc.get("quantity")
        current_stock[(doc["branchId"], doc["itemId"])] = {
            "quantity": qty,
            "unit": doc.get("unit"),
        }

    # Fetch item metadata (minThreshold, defaultUnit)
    items_meta = {}
    for doc in db.items.find(
        {"_id": {"$in": item_ids}},
        {"name": 1, "sku": 1, "minThreshold": 1, "defaultUnit": 1},
    ):
        items_meta[doc["_id"]] = doc

    # Fetch branch metadata
    branches_meta = {}
    for doc in db.branches.find(
        {"_id": {"$in": branch_ids}},
        {"name": 1, "code": 1},
    ):
        branches_meta[doc["_id"]] = doc

    # Step 3: Build enriched items list with days_left
    all_items = []
    for row in consumption_rows:
        branch_id = row["branchId"]
        item_id = row["itemId"]
        rate = float(row.get("consumptionRatePerDay", 0))

        stock = current_stock.get((branch_id, item_id), {})
        current_qty = stock.get("quantity")
        item_meta = items_meta.get(item_id, {})
        branch_meta = branches_meta.get(branch_id, {})

        if current_qty is not None and rate > 0:
            days_left = float(current_qty) / rate
        else:
            days_left = None

        # Format last 3 updates
        last_updates = []
        for upd in row.get("lastThreeUpdates", []):
            submitted = upd.get("submittedAt")
            if submitted:
                last_updates.append({
                    "date": _format_date(submitted),
                    "quantity": upd.get("quantity"),
                    "unit": _safe_str(upd.get("unit") or row.get("unit")),
                })

        all_items.append({
            "branch_id": branch_id,
            "branch_code": _safe_str(branch_meta.get("code") or row.get("branchCode")),
            "branch_name": _safe_str(branch_meta.get("name")),
            "name": _safe_str(row.get("itemName") or item_meta.get("name")),
            "sku": _safe_str(row.get("sku") or item_meta.get("sku")),
            "unit": _safe_str(row.get("unit") or item_meta.get("defaultUnit")),
            "current_qty": current_qty,
            "min_threshold": item_meta.get("minThreshold"),
            "rate_per_day": rate,
            "days_left": days_left,
            "last_updates": last_updates,
        })

    # Step 4: Group by branch, sort by days_left ascending, top 20 per branch
    by_branch: dict[str, list[dict]] = defaultdict(list)
    for item in all_items:
        key = f"{item['branch_code']} ({item['branch_name']})"
        by_branch[key].append(item)

    # Sort each branch's items: items with days_left=None go last, then by days_left ascending
    for key in by_branch:
        by_branch[key].sort(key=lambda x: (x["days_left"] is None, x["days_left"] if x["days_left"] is not None else float("inf")))
        by_branch[key] = by_branch[key][:TOP_N]

    # Step 5: Build the email message
    now = datetime.now(REPORT_TZ)
    separator = "=" * 52
    thin_sep = "-" * 52

    total_shown = sum(len(v) for v in by_branch.values())
    critical_count = sum(
        1 for items in by_branch.values()
        for item in items
        if item["days_left"] is not None and item["days_left"] <= CRITICAL_DAYS
    )
    out_of_stock_count = sum(
        1 for items in by_branch.values()
        for item in items
        if item["current_qty"] is not None and float(item["current_qty"]) == 0
    )

    subject = f"{now.strftime('%Y-%m-%d')} | Mexican Mama Inventory Alert"

    parts = [
        separator,
        "  MEXICAN MAMA - INVENTORY ALERT",
        "  Top Items by Days to Depletion",
        separator,
        "",
        f"  Date:  {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Consumption Window:  Last {LOOKBACK_DAYS} days",
        f"  Showing:  Top {TOP_N} items per branch (lowest days left)",
        "",
    ]

    if critical_count > 0 or out_of_stock_count > 0:
        summary_parts = []
        if out_of_stock_count > 0:
            summary_parts.append(f"{out_of_stock_count} OUT OF STOCK")
        if critical_count > 0:
            summary_parts.append(f"{critical_count} CRITICAL (≤{CRITICAL_DAYS} days)")
        parts.append(f"  !! {' | '.join(summary_parts)}")
        parts.append("")

    for branch_key in sorted(by_branch.keys()):
        items = by_branch[branch_key]
        parts.append(thin_sep)
        parts.append(f"  Branch: {branch_key}  ({len(items)} items)")
        parts.append(thin_sep)
        parts.append("")

        for idx, item in enumerate(items, 1):
            parts.append(_build_item_block(idx, item))

    parts.append(separator)
    parts.append("  Items ranked by urgency (fewest days left first).")
    parts.append("  Please reorder items running low.")
    parts.append(separator)

    message_body = "\n".join(parts).rstrip() + "\n"

    # Step 6: Publish
    if args.dry_run:
        print(f"Subject: {subject}\n")
        print(message_body)
        print(f"\nTotal items shown: {total_shown}")
        return

    sns = boto3.client("sns", region_name=aws_region)
    response = sns.publish(
        TopicArn=sns_topic_arn,
        Subject=subject,
        Message=message_body,
    )
    print("SNS alert published successfully.")
    print(f"SNS MessageId: {response.get('MessageId')}")
    print(f"Items included: {total_shown}")


if __name__ == "__main__":
    main()

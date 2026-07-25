#!/usr/bin/env python3
"""Send a daily low-inventory alert via AWS SNS.

Usage:
  python3 crons/low_inventory_sns_alert.py

Required env vars:
  - MONGODB_URI
  - MONGODB_DB
  - SNS_TOPIC_ARN
Optional env vars:
  - AWS_REGION (default: ap-south-1)
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient

try:
    import boto3
except ImportError as exc:  # pragma: no cover
    raise SystemExit("boto3 is required for SNS publishing. Install with: pip install boto3") from exc


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


def _build_item_list(rows: list[dict[str, str]]) -> str:
    lines = []
    for idx, row in enumerate(rows, 1):
        current = row["current_qty"]
        minimum = row["min_threshold"]
        unit = row["unit"]

        # Calculate deficit
        try:
            deficit = float(minimum) - float(current)
            deficit_str = _format_number(deficit)
        except (TypeError, ValueError):
            deficit_str = "?"

        # Flag out-of-stock items
        try:
            is_out = float(current) == 0
        except (TypeError, ValueError):
            is_out = False

        stock_label = "OUT OF STOCK" if is_out else f"{current} {unit}"

        lines.append(f"  {idx}. {row['item']}  [{row['sku']}]")
        lines.append(f"     Stock: {stock_label}  |  Min Required: {minimum} {unit}  |  Need: {deficit_str} {unit}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    load_dotenv()

    mongodb_uri = os.getenv("MONGODB_URI")
    mongodb_db = os.getenv("MONGODB_DB", "inventory")
    sns_topic_arn = os.getenv("SNS_TOPIC_ARN")
    aws_region = os.getenv("AWS_REGION", "ap-south-1")

    if not mongodb_uri:
        raise SystemExit("Missing MONGODB_URI")
    if not sns_topic_arn:
        raise SystemExit("Missing SNS_TOPIC_ARN")

    client = MongoClient(mongodb_uri, maxPoolSize=10)
    db = client[mongodb_db]

    below_rows = list(
        db.inventory_current.find(
            {"isBelowThreshold": True},
            {
                "_id": 0,
                "branchId": 1,
                "itemId": 1,
                "quantity": 1,
                "unit": 1,
                "quantityBase": 1,
            },
        )
    )

    if not below_rows:
        print("No below-threshold items found. No SNS message published.")
        return

    item_ids = list({row.get("itemId") for row in below_rows if row.get("itemId") is not None})
    branch_ids = list({row.get("branchId") for row in below_rows if row.get("branchId") is not None})

    items = {
        doc["_id"]: doc
        for doc in db.items.find(
            {"_id": {"$in": item_ids}},
            {"name": 1, "sku": 1, "minThreshold": 1, "defaultUnit": 1},
        )
    }
    branches = {
        doc["_id"]: doc
        for doc in db.branches.find(
            {"_id": {"$in": branch_ids}},
            {"name": 1, "code": 1},
        )
    }

    by_branch: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in below_rows:
        item = items.get(row.get("itemId"), {})
        branch = branches.get(row.get("branchId"), {})

        branch_key = f"{_safe_str(branch.get('code'))} ({_safe_str(branch.get('name'))})"
        quantity = row.get("quantityBase") if row.get("quantityBase") is not None else row.get("quantity")

        by_branch[branch_key].append(
            {
                "item": _safe_str(item.get("name")),
                "sku": _safe_str(item.get("sku")),
                "current_qty": _format_number(quantity),
                "min_threshold": _format_number(item.get("minThreshold")),
                "unit": _safe_str(item.get("defaultUnit") or row.get("unit")),
            }
        )

    now = datetime.now()
    separator = "=" * 50
    thin_sep = "-" * 50
    subject = f"{now.strftime('%Y-%m-%d')} | Mexican Mama Inventory Order Alert"

    total_count = sum(len(v) for v in by_branch.values())

    message_parts = [
        separator,
        "  MEXICAN MAMA - INVENTORY REORDER ALERT",
        separator,
        "",
        f"  Date:  {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Total items below threshold:  {total_count}",
        "",
    ]

    for branch_key in sorted(by_branch.keys()):
        rows = sorted(by_branch[branch_key], key=lambda r: (r["item"], r["sku"]))
        message_parts.append(thin_sep)
        message_parts.append(f"  Branch: {branch_key}  ({len(rows)} items)")
        message_parts.append(thin_sep)
        message_parts.append("")
        message_parts.append(_build_item_list(rows))

    message_parts.append(separator)
    message_parts.append("  Please place reorders for the above items.")
    message_parts.append(separator)
    message_body = "\n".join(message_parts).rstrip() + "\n"

    sns = boto3.client("sns", region_name=aws_region)
    response = sns.publish(
        TopicArn=sns_topic_arn,
        Subject=subject,
        Message=message_body,
    )
    print("SNS alert published successfully.")
    print(f"SNS MessageId: {response.get('MessageId')}")
    print("Note: SNS email subscriptions support plain text only (no HTML rendering).")

    print(f"Items included: {len(below_rows)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Print per-day consumption for inventory items updated in the last N days.

Usage:
  python3 crons/weekly_consumption_report.py --days 7
  python3 crons/weekly_consumption_report.py --branch-code BLR01
  python3 crons/weekly_consumption_report.py --days 7 --timezone Asia/Kolkata --limit 50

Required env vars:
  - MONGODB_URI
Optional env vars:
  - MONGODB_DB (default: inventory)
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pymongo import MongoClient

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate per-day consumption for items updated during the last N days."
    )
    parser.add_argument("--branch-code", help="Limit the report to a single branch code, for example BLR01.")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Rolling lookback window in days. Default: 7.",
    )
    parser.add_argument(
        "--timezone",
        default="Asia/Kolkata",
        help="Timezone used to evaluate local calendar dates. Default: Asia/Kolkata.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of rows to print. Default: 100.",
    )
    return parser.parse_args()


def _round_number(value: Any) -> float | int | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number.is_integer():
        return int(number)
    return round(number, 3)


def _window_bounds(report_tz: ZoneInfo, days: int) -> tuple[datetime, datetime, datetime]:
    now_local = datetime.now(report_tz)
    window_start_local = now_local - timedelta(days=days)
    return (
        now_local,
        window_start_local.astimezone(timezone.utc),
        now_local.astimezone(timezone.utc),
    )


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()
    args = _parse_args()

    try:
        report_tz = ZoneInfo(args.timezone)
    except Exception as exc:
        raise SystemExit(f"Invalid timezone '{args.timezone}'.") from exc

    mongodb_uri = os.getenv("MONGODB_URI")
    mongodb_db = os.getenv("MONGODB_DB", "inventory")

    if not mongodb_uri:
        raise SystemExit("Missing MONGODB_URI")

    branch_code = (args.branch_code or "").strip().upper()
    lookback_days = max(1, int(args.days))
    limit = max(1, int(args.limit))

    now_local, window_start_utc, window_end_utc = _window_bounds(report_tz, lookback_days)

    client = MongoClient(mongodb_uri, maxPoolSize=10)
    db = client[mongodb_db]

    match_filter: dict[str, Any] = {
        "submittedAt": {
            "$gte": window_start_utc,
            "$lte": window_end_utc,
        }
    }
    if branch_code:
        match_filter["branchCode"] = branch_code

    pipeline = [
        {"$match": match_filter},
        {"$unwind": "$items"},
        {
            "$addFields": {
                "effectiveDelta": {
                    "$ifNull": ["$items.deltaQuantityBase", "$items.deltaQuantity"]
                },
                "effectivePreviousQuantity": {
                    "$ifNull": ["$items.previousQuantityBase", "$items.previousQuantity"]
                },
                "effectiveNewQuantity": {
                    "$ifNull": ["$items.newQuantityBase", "$items.newQuantity"]
                },
                "effectiveUnit": {
                    "$ifNull": ["$items.baseUnit", "$items.newUnit"]
                },
            }
        },
        {"$sort": {"submittedAt": 1, "_id": 1}},
        {
            "$group": {
                "_id": {
                    "branchCode": "$branchCode",
                    "itemId": "$items.itemId",
                },
                "itemName": {"$last": "$items.name"},
                "sku": {"$last": "$items.sku"},
                "unit": {"$last": "$effectiveUnit"},
                "previousQuantity": {"$first": "$effectivePreviousQuantity"},
                "currentQuantity": {"$last": "$effectiveNewQuantity"},
                "firstUpdateDate": {
                    "$first": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$submittedAt",
                            "timezone": args.timezone,
                        }
                    }
                },
                "lastUpdateDate": {
                    "$last": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$submittedAt",
                            "timezone": args.timezone,
                        }
                    }
                },
                "daysUpdated": {
                    "$addToSet": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$submittedAt",
                            "timezone": args.timezone,
                        }
                    }
                },
                "daysConsumed": {
                    "$addToSet": {
                        "$cond": [
                            {"$lt": ["$effectiveDelta", 0]},
                            {
                                "$dateToString": {
                                    "format": "%Y-%m-%d",
                                    "date": "$submittedAt",
                                    "timezone": args.timezone,
                                }
                            },
                            None,
                        ]
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
                "netDelta": {"$sum": {"$ifNull": ["$effectiveDelta", 0]}},
                "updateCount": {"$sum": 1},
                "debugUpdates": {
                    "$push": {
                        "submittedAt": "$submittedAt",
                        "updateDate": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$submittedAt",
                                "timezone": args.timezone,
                            }
                        },
                        "previousQuantity": "$effectivePreviousQuantity",
                        "currentQuantity": "$effectiveNewQuantity",
                        "deltaQuantity": "$effectiveDelta",
                        "unit": "$effectiveUnit",
                    }
                },
            }
        },
        {
            "$project": {
                "branchCode": "$_id.branchCode",
                "itemId": "$_id.itemId",
                "itemName": 1,
                "sku": 1,
                "unit": 1,
                "previousQuantity": 1,
                "currentQuantity": 1,
                "firstUpdateDate": 1,
                "lastUpdateDate": 1,
                "totalConsumed": 1,
                "netDelta": 1,
                "updateCount": 1,
                "debugUpdates": 1,
                "daysUpdated": {"$size": "$daysUpdated"},
                "daysConsumed": {
                    "$size": {
                        "$filter": {
                            "input": "$daysConsumed",
                            "as": "day",
                            "cond": {"$ne": ["$$day", None]},
                        }
                    }
                },
                "elapsedDays": {
                    "$max": [
                        1,
                        {
                            "$dateDiff": {
                                "startDate": {
                                    "$dateFromString": {
                                        "dateString": "$firstUpdateDate",
                                        "format": "%Y-%m-%d",
                                        "timezone": args.timezone,
                                    }
                                },
                                "endDate": {
                                    "$dateFromString": {
                                        "dateString": "$lastUpdateDate",
                                        "format": "%Y-%m-%d",
                                        "timezone": args.timezone,
                                    }
                                },
                                "unit": "day",
                                "timezone": args.timezone,
                            }
                        },
                    ]
                },
                "avgDailyConsumption": {
                    "$cond": [
                        {
                            "$gt": [
                                {
                                    "$max": [
                                        1,
                                        {
                                            "$dateDiff": {
                                                "startDate": {
                                                    "$dateFromString": {
                                                        "dateString": "$firstUpdateDate",
                                                        "format": "%Y-%m-%d",
                                                        "timezone": args.timezone,
                                                    }
                                                },
                                                "endDate": {
                                                    "$dateFromString": {
                                                        "dateString": "$lastUpdateDate",
                                                        "format": "%Y-%m-%d",
                                                        "timezone": args.timezone,
                                                    }
                                                },
                                                "unit": "day",
                                                "timezone": args.timezone,
                                            }
                                        },
                                    ]
                                },
                                0,
                            ]
                        },
                        {
                            "$divide": [
                                "$totalConsumed",
                                {
                                    "$max": [
                                        1,
                                        {
                                            "$dateDiff": {
                                                "startDate": {
                                                    "$dateFromString": {
                                                        "dateString": "$firstUpdateDate",
                                                        "format": "%Y-%m-%d",
                                                        "timezone": args.timezone,
                                                    }
                                                },
                                                "endDate": {
                                                    "$dateFromString": {
                                                        "dateString": "$lastUpdateDate",
                                                        "format": "%Y-%m-%d",
                                                        "timezone": args.timezone,
                                                    }
                                                },
                                                "unit": "day",
                                                "timezone": args.timezone,
                                            }
                                        },
                                    ]
                                },
                            ]
                        },
                        0,
                    ]
                },
            }
        },
        {"$sort": {"avgDailyConsumption": -1, "totalConsumed": -1, "branchCode": 1, "itemName": 1}},
        {"$limit": limit},
    ]

    rows = list(db.inventory_updates.aggregate(pipeline, allowDiskUse=False))
    results = [
        {
            "itemId": str(row.get("itemId")),
            "name": row.get("itemName"),
            "branchCode": row.get("branchCode"),
            "sku": row.get("sku"),
            "unit": row.get("unit"),
            "previousQuantity": previous_quantity,
            "currentQuantity": current_quantity,
            "totalConsumed": total_consumed,
            "elapsedDays": int(row.get("elapsedDays") or 0),
            "daysUpdated": int(row.get("daysUpdated") or 0),
            "daysConsumed": int(row.get("daysConsumed") or 0),
            "updateCount": int(row.get("updateCount") or 0),
            "consumptionRatePerDay": rate_per_day,
            "netDelta": _round_number(row.get("netDelta")) or 0,
            "estimatedInventoryDaysLeft": round(current_quantity / rate_per_day, 3) if rate_per_day > 0 and current_quantity is not None else None,
            "debug": {
                "firstUpdateDateIncluded": row.get("firstUpdateDate"),
                "lastUpdateDateIncluded": row.get("lastUpdateDate"),
                "windowStart": window_start_utc.astimezone(report_tz).isoformat(),
                "windowEnd": window_end_utc.astimezone(report_tz).isoformat(),
                "updates": [
                    {
                        "submittedAt": update.get("submittedAt").astimezone(report_tz).isoformat() if update.get("submittedAt") else None,
                        "updateDate": update.get("updateDate"),
                        "previousQuantity": _round_number(update.get("previousQuantity")),
                        "currentQuantity": _round_number(update.get("currentQuantity")),
                        "deltaQuantity": _round_number(update.get("deltaQuantity")),
                        "unit": update.get("unit"),
                    }
                    for update in (row.get("debugUpdates") or [])
                ],
            },
        }
        for row in rows
        for previous_quantity in [_round_number(row.get("previousQuantity"))]
        for current_quantity in [_round_number(row.get("currentQuantity"))]
        for total_consumed in [_round_number(row.get("totalConsumed")) or 0]
        for rate_per_day in [_round_number(row.get("avgDailyConsumption")) or 0]
        if int(row.get("updateCount") or 0) > 1
    ]

    payload = {
        "timezone": args.timezone,
        "days": lookback_days,
        "windowStart": window_start_utc.astimezone(report_tz).isoformat(),
        "windowEnd": window_end_utc.astimezone(report_tz).isoformat(),
        "generatedAt": now_local.isoformat(),
        "branchCode": branch_code or None,
        "count": len(results),
        "results": results,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

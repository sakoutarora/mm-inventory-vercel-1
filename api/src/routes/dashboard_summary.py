from collections import defaultdict
from datetime import datetime, timedelta, timezone

from src.lib.auth import extract_bearer_token, verify_token
from src.lib.mongo import get_db
from src.lib.response import json_response


def _parse_branch_code(event):
    query = event.get("queryStringParameters") or {}
    return (query.get("branchCode") or "").strip().upper()


def _safe_days(event, default=14, minimum=3, maximum=30):
    query = event.get("queryStringParameters") or {}
    raw = query.get("days")
    if raw is None:
        return default
    try:
        parsed = int(raw)
        return max(minimum, min(maximum, parsed))
    except (TypeError, ValueError):
        return default


def handle_dashboard_summary(event, _context):
    try:
        if event.get("httpMethod") == "OPTIONS":
            return json_response(200, {"ok": True})

        token = extract_bearer_token(event)
        if not token:
            return json_response(401, {"message": "Missing bearer token."})

        try:
            auth = verify_token(token)
        except Exception:
            return json_response(401, {"message": "Invalid token."})

        branch_code = _parse_branch_code(event)
        if not branch_code:
            return json_response(400, {"message": "branchCode is required."})

        if auth.get("branchCode") != branch_code and auth.get("role") != "admin":
            return json_response(403, {"message": "Branch access denied."})

        db = get_db()
        branch = db.branches.find_one({"code": branch_code, "isActive": True}, {"_id": 1, "name": 1, "code": 1})
        if not branch:
            return json_response(404, {"message": "Branch not found."})

        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        lookback_days = _safe_days(event)
        lookback_start = now - timedelta(days=lookback_days)
        week_start = now - timedelta(days=7)

        current_rows = list(
            db.inventory_current.find(
                {"branchId": branch["_id"]},
                {"_id": 0, "itemId": 1, "quantity": 1, "minThreshold": 1, "isBelowThreshold": 1, "unit": 1},
            )
        )

        item_ids = [row["itemId"] for row in current_rows]
        item_docs = list(
            db.items.find(
                {"_id": {"$in": item_ids}},
                {"_id": 1, "name": 1, "sku": 1, "categoryId": 1, "isActive": 1, "defaultUnit": 1},
            )
        ) if item_ids else []
        item_by_id = {str(doc["_id"]): doc for doc in item_docs}

        category_ids = list({doc.get("categoryId") for doc in item_docs if doc.get("categoryId")})
        categories = list(
            db.categories.find({"_id": {"$in": category_ids}}, {"_id": 1, "name": 1})
        ) if category_ids else []
        category_by_id = {str(cat["_id"]): cat for cat in categories}

        critically_low_items = []
        order_today_count = 0
        category_stats = defaultdict(lambda: {"total": 0, "low": 0})

        for row in current_rows:
            item = item_by_id.get(str(row["itemId"]))
            if not item:
                continue

            category = category_by_id.get(str(item.get("categoryId")))
            category_name = category["name"] if category else "Uncategorized"
            category_stats[category_name]["total"] += 1

            qty = float(row.get("quantity") or 0)
            threshold = float(row.get("minThreshold") or 0)
            is_low = bool(row.get("isBelowThreshold"))

            if threshold > 0 and qty <= (threshold * 1.2):
                order_today_count += 1

            if is_low:
                category_stats[category_name]["low"] += 1
                critically_low_items.append(
                    {
                        "itemId": str(row["itemId"]),
                        "name": item.get("name"),
                        "sku": item.get("sku"),
                        "category": category_name,
                        "quantity": qty,
                        "unit": row.get("unit") or item.get("defaultUnit"),
                        "minThreshold": threshold,
                    }
                )

        critically_low_items.sort(key=lambda x: (x["quantity"] - x["minThreshold"]))

        category_risk = []
        for category_name, stats in category_stats.items():
            total = stats["total"]
            low = stats["low"]
            category_risk.append(
                {
                    "category": category_name,
                    "lowCount": low,
                    "totalCount": total,
                    "lowPct": round((low / total) * 100, 2) if total > 0 else 0,
                }
            )
        category_risk.sort(key=lambda x: x["lowPct"], reverse=True)

        consumed_pipeline = [
            {
                "$match": {
                    "branchId": branch["_id"],
                    "submittedAt": {"$gte": lookback_start},
                }
            },
            {"$unwind": "$items"},
            {"$addFields": {"effectiveDelta": {"$ifNull": ["$items.deltaQuantityBase", "$items.deltaQuantity"]}}},
            {"$match": {"effectiveDelta": {"$lt": 0}}},
            {
                "$group": {
                    "_id": "$items.itemId",
                    "totalConsumed": {"$sum": {"$multiply": [-1, "$effectiveDelta"]}},
                    "daysObserved": {
                        "$addToSet": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$submittedAt",
                                "timezone": "UTC",
                            }
                        }
                    },
                }
            },
            {
                "$project": {
                    "totalConsumed": 1,
                    "daysObserved": {"$size": "$daysObserved"},
                    "avgDailyConsumption": {
                        "$cond": [
                            {"$gt": [{"$size": "$daysObserved"}, 0]},
                            {"$divide": ["$totalConsumed", {"$size": "$daysObserved"}]},
                            0,
                        ]
                    },
                }
            },
            {"$sort": {"avgDailyConsumption": -1}},
            {"$limit": 10},
        ]
        top_consumption_raw = list(db.inventory_updates.aggregate(consumed_pipeline, allowDiskUse=False))

        current_by_item_id = {str(row["itemId"]): row for row in current_rows}
        top_consumption = []
        for row in top_consumption_raw:
            item_id = str(row["_id"])
            item = item_by_id.get(item_id)
            if not item:
                continue
            current = current_by_item_id.get(item_id)
            current_qty = float(current.get("quantityBase") or current.get("quantity") or 0) if current else 0
            avg_daily = float(row.get("avgDailyConsumption") or 0)
            top_consumption.append(
                {
                    "itemId": item_id,
                    "name": item.get("name"),
                    "sku": item.get("sku"),
                    "consumptionUnit": current.get("baseUnit") if current else None,
                    "avgDailyConsumption": round(avg_daily, 3),
                    "totalConsumed": round(float(row.get("totalConsumed") or 0), 3),
                    "daysObserved": int(row.get("daysObserved") or 0),
                    "currentQuantity": current_qty,
                    "daysToDeplete": round(current_qty / avg_daily, 2) if avg_daily > 0 else None,
                }
            )

        daily_consumption_pipeline = [
            {
                "$match": {
                    "branchId": branch["_id"],
                    "submittedAt": {"$gte": week_start},
                }
            },
            {"$unwind": "$items"},
            {"$addFields": {"effectiveDelta": {"$ifNull": ["$items.deltaQuantityBase", "$items.deltaQuantity"]}}},
            {"$match": {"effectiveDelta": {"$lt": 0}}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$submittedAt",
                            "timezone": "UTC",
                        }
                    },
                    "consumed": {"$sum": {"$multiply": [-1, "$effectiveDelta"]}},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        daily_consumption = [
            {"date": row["_id"], "consumed": round(float(row.get("consumed") or 0), 3)}
            for row in db.inventory_updates.aggregate(daily_consumption_pipeline, allowDiskUse=False)
        ]

        updated_today_count = db.inventory_updates.count_documents(
            {"branchId": branch["_id"], "submittedAt": {"$gte": today_start}}
        )
        total_items_tracked = db.items.count_documents({"isActive": True})

        avg_consumption_overall = 0.0
        if top_consumption:
            avg_consumption_overall = round(
                sum(entry["avgDailyConsumption"] for entry in top_consumption) / len(top_consumption), 3
            )

        return json_response(
            200,
            {
                "branch": {"id": str(branch["_id"]), "code": branch["code"], "name": branch["name"]},
                "kpis": {
                    "criticallyLowCount": len(critically_low_items),
                    "orderTodayCount": order_today_count,
                    "totalItemsTracked": total_items_tracked,
                    "updatedTodayCount": updated_today_count,
                    "avgConsumptionPerDay": avg_consumption_overall,
                    "lookbackDays": lookback_days,
                },
                "criticallyLowItems": critically_low_items[:8],
                "topConsumption": top_consumption,
                "dailyConsumption": daily_consumption,
                "categoryRisk": category_risk,
                "generatedAt": now,
            },
        )
    except Exception as exc:
        print("dashboard_summary error", exc)
        return json_response(500, {"message": "Internal server error."})

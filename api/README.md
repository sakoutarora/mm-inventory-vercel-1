# Inventory API (AWS Lambda style, Python)

This folder contains Python Lambda handlers for:
- Login
- Fetch inventory items by branch
- Update inventory and store change history
- Dashboard analytics summary
- Admin APIs for categories, items, and users

## Collections
- `branches`
- `users`
- `categories`
- `items`
- `inventory_current`
- `inventory_updates`

## Database design notes
- `inventory_current` keeps latest stock per `branchId + itemId`.
- `inventory_updates` stores every submitted batch with previous and new values per item for future trend analysis.

## Environment variables
Use `.env.example` values as reference:
- `MONGODB_URI`
- `MONGODB_DB`
- `JWT_SECRET`
- `JWT_EXPIRES_IN_HOURS`

## Lambda handler
- `src/lambda_function.lambda_handler` (single entrypoint that routes by `method + path`)

## Setup
```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Seed scripts
```bash
python run_seed.py users
python run_seed.py master
```

### EC2-friendly seed helpers
```bash
./seeds/ec2_seed_users.sh
./seeds/ec2_seed_master.sh
```

## Suggested API routes
- `POST /api/v1/auth/login`
- `GET /api/v1/inventory/items?branchCode=BLR01`
- `POST /api/v1/inventory/update`
- `GET /api/v1/dashboard/summary?branchCode=BLR01&days=14`
- `GET /api/v1/admin/meta` (admin only)
- `POST /api/v1/admin/categories` (admin only)
- `POST /api/v1/admin/items` (admin only)
- `PATCH /api/v1/admin/items` (admin only)
- `POST /api/v1/admin/users` (admin only)

## Request examples

### 1) Login
```json
POST /auth/login
{
  "username": "blr_staff",
  "password": "staff123",
  "branchCode": "BLR01"
}
```

### 2) Get inventory items
```http
GET /inventory/items?branchCode=BLR01
Authorization: Bearer <token>
```

### 3) Update inventory
```json
POST /inventory/update
Authorization: Bearer <token>
{
  "branchCode": "BLR01",
  "submittedAt": "2026-03-07T10:30:00.000Z",
  "items": [
    { "itemId": "65f0f97e90f2d8c6dd5b2f13", "quantity": 12, "unit": "kg" },
    { "itemId": "65f0f97e90f2d8c6dd5b2f14", "quantity": 20, "unit": "items" }
  ]
}
```

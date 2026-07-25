# Inventory Management System

A multi-platform inventory management system for multi-branch kitchen/restaurant operations. Staff use the Android app for daily stock entry; admins use the web console for analytics, alerts, and master data management.

## Architecture

```
Android App / Web Console
        ↓
  AWS API Gateway
        ↓
  AWS Lambda (Python)
        ↓
     MongoDB
```

| Component | Tech | Location |
|-----------|------|----------|
| Mobile App | Kotlin, Android SDK 34 | `app/` |
| API Backend | Python 3.11, AWS Lambda, Serverless Framework | `api/` |
| Web Console | React 18, Vite | `console/` |
| Database | MongoDB | Hosted (Atlas or self-managed) |

## Features

### Android App (`app/`)
- Login with username, password, and branch code
- Daily inventory entry grouped by category
- Shows previous stock values for reference
- Flags required items that must be filled
- Review screen before submission

### Web Console (`console/`)
- **Inventory** — View and batch-edit stock for a branch, submit changes
- **Dashboard** — KPIs (critically low items, orders, daily consumption), 7-day consumption chart, category risk breakdown, depletion forecasts
- **Admin** (admin-only) — Create/edit categories, items (with units and thresholds), and users with branch assignments

### API (`api/`)
- JWT authentication (12-hour expiry)
- Role-based access (staff / admin)
- Multi-branch support — users only access assigned branches
- Full audit trail of inventory updates with delta tracking
- Consumption analytics over configurable time periods
- Automatic low-stock threshold detection

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/auth/login` | Authenticate user |
| GET | `/inventory/items` | Get items for a branch |
| POST | `/inventory/update` | Submit batch stock update |
| GET | `/dashboard/summary` | KPIs, consumption, risk data |
| GET | `/admin/meta` | All branches, categories, items, users |
| POST | `/admin/categories` | Create category |
| POST | `/admin/items` | Create item |
| PATCH | `/admin/items` | Update item thresholds/units |
| POST | `/admin/users` | Create user |

All routes are prefixed with `/api/v1`.

## Getting Started

### Prerequisites
- Node.js 18+
- Python 3.11+
- MongoDB instance
- Android Studio (for the mobile app)
- AWS account (for deployment)

### Backend

```bash
cd api
cp .env.example .env
# Fill in MONGODB_URI, JWT_SECRET, etc.

pip install -r requirements.txt   # or install pymongo, bcrypt, PyJWT, python-dotenv

# Local testing
python src/lambda_function.py

# Deploy
npx serverless deploy --stage prod
```

### Web Console

```bash
cd console
npm install
npm run dev        # starts on http://localhost:5174
npm run build      # production build → dist/
```

To point at a different API, set `VITE_API_BASE_URL` in a `.env` file.

### Android App

1. Open the project root in Android Studio
2. Update the base URL in `ApiClient.kt` if needed
3. Build and run on a device or emulator (min SDK 24)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGODB_URI` | MongoDB connection string | — |
| `MONGODB_DB` | Database name | `inventory_app` |
| `JWT_SECRET` | Secret for signing tokens | — |
| `JWT_EXPIRES_IN_HOURS` | Token expiry in hours | `12` |

## Database Collections

| Collection | Purpose |
|------------|---------|
| `branches` | Store/branch locations |
| `users` | Staff and admin accounts |
| `categories` | Item groupings |
| `items` | Inventory item definitions |
| `inventory_current` | Latest stock per branch+item |
| `inventory_updates` | Historical change batches |

## Project Structure

```
inventory/
├── app/                    # Android app (Kotlin)
│   └── src/main/java/com/mm/inventory/
│       ├── LoginActivity.kt
│       ├── LandingActivity.kt
│       ├── InventoryActivity.kt
│       ├── ReviewActivity.kt
│       ├── ApiClient.kt
│       └── SessionManager.kt
├── api/                    # Serverless Python backend
│   ├── src/
│   │   ├── lambda_function.py
│   │   ├── routes/         # Route handlers
│   │   └── lib/            # Auth, DB, config utilities
│   └── serverless.yml
├── console/                # React web console
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   └── styles.css
│   └── vite.config.js
└── README.md
```

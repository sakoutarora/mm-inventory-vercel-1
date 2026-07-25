# Threshold Migration (No edits to existing collections)

This migration is designed to **not mutate** existing collections. It writes to new collections only:

- `items_migrated`
- `inventory_current_migrated`
- `inventory_updates_migrated`

## Step 1: Clone and reshape

```bash
python3 migration/01_clone_to_migrated_collections.py
```

If migrated collections already exist and you want to rebuild them:

```bash
python3 migration/01_clone_to_migrated_collections.py --reset-targets
```

What it does:
- Copies `items` -> `items_migrated`
- Copies `inventory_current` -> `inventory_current_migrated`
- Copies `inventory_updates` -> `inventory_updates_migrated`
- While copying `inventory_current`, removes `minThreshold` and `minThresholdBase`

## Step 2: Apply thresholds from CSV

CSV source (from existing seed script path):
- `/Users/sakshamarora/Downloads/Inventory_Rista - inventory items.csv`

Run:

```bash
python3 migration/02_update_thresholds_from_csv.py
```

Dry run:

```bash
python3 migration/02_update_thresholds_from_csv.py --dry-run
```

What it does:
- Reads `Min quantity` from CSV
- Converts threshold to base unit using the same unit conversion library
- Updates `items_migrated.minThreshold`
- Recomputes `inventory_current_migrated.isBelowThreshold` using updated thresholds
- Does not modify original `items`, `inventory_current`, or `inventory_updates`

## Step 3: Recompute `isBelowThreshold` in migrated current

Run this if existing migrated flags are wrong and you want to recalculate from
`items_migrated.minThreshold`:

```bash
python3 migration/03_recompute_is_below_threshold_migrated.py
```

Dry run:

```bash
python3 migration/03_recompute_is_below_threshold_migrated.py --dry-run
```

What it does:
- Reads `items_migrated.minThreshold` by `itemId`
- Recomputes `inventory_current_migrated.isBelowThreshold` as:
  - `effectiveQuantity = quantityBase if present else quantity`
  - `isBelowThreshold = effectiveQuantity < minThreshold`
- Updates only migrated collections

## Step 4: Promote migrated collections to live

```bash
python3 migration/04_promote_migrated_collections.py
```

What it does:
- Renames live collections to timestamped legacy collections:
  - `items` -> `items_legacy_<UTC timestamp>`
  - `inventory_current` -> `inventory_current_legacy_<UTC timestamp>`
  - `inventory_updates` -> `inventory_updates_legacy_<UTC timestamp>`
- Renames migrated collections to live names:
  - `items_migrated` -> `items`
  - `inventory_current_migrated` -> `inventory_current`
  - `inventory_updates_migrated` -> `inventory_updates`

Rollback:
- If needed, reverse the same rename direction using the legacy names printed by the script.

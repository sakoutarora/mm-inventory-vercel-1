# MongoDB Schema

## branches
```json
{
  "_id": "ObjectId",
  "code": "BLR01",
  "name": "Bangalore Branch",
  "isActive": true,
  "createdAt": "Date",
  "updatedAt": "Date"
}
```

## users
```json
{
  "_id": "ObjectId",
  "username": "blr_staff",
  "passwordHash": "bcrypt hash",
  "fullName": "BLR Kitchen Staff",
  "role": "staff|admin",
  "branchIds": ["ObjectId"],
  "isActive": true,
  "createdAt": "Date",
  "updatedAt": "Date"
}
```

## categories
```json
{
  "_id": "ObjectId",
  "code": "VEG",
  "name": "Vegetables",
  "displayOrder": 2,
  "isActive": true,
  "createdAt": "Date",
  "updatedAt": "Date"
}
```

## items
```json
{
  "_id": "ObjectId",
  "sku": "VEG-TOMATO",
  "name": "Tomato",
  "categoryId": "ObjectId",
  "defaultUnit": "kg",
  "allowedUnits": ["kg", "g", "items"],
  "minThreshold": 8,
  "isRequired": true,
  "isActive": true,
  "createdAt": "Date",
  "updatedAt": "Date"
}
```

## inventory_current (latest state)
```json
{
  "_id": "ObjectId",
  "branchId": "ObjectId",
  "itemId": "ObjectId",
  "quantity": 12,
  "unit": "kg",
  "isBelowThreshold": false,
  "updatedBy": "ObjectId",
  "updatedAt": "Date",
  "version": 4,
  "createdAt": "Date"
}
```

## inventory_updates (history batches for analysis)
```json
{
  "_id": "ObjectId",
  "branchId": "ObjectId",
  "branchCode": "BLR01",
  "updatedBy": {
    "userId": "ObjectId",
    "username": "blr_staff"
  },
  "submittedAt": "Date",
  "createdAt": "Date",
  "itemCount": 3,
  "items": [
    {
      "itemId": "ObjectId",
      "sku": "VEG-TOMATO",
      "name": "Tomato",
      "categoryId": "ObjectId",
      "previousQuantity": 15,
      "previousUnit": "kg",
      "newQuantity": 12,
      "newUnit": "kg",
      "deltaQuantity": -3,
      "minThreshold": 8,
      "crossedBelowThreshold": false
    }
  ]
}
```

This split (`inventory_current` + `inventory_updates`) is optimized for both quick current reads and future change-trend analytics.

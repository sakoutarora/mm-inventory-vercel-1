package com.mm.inventory

import org.json.JSONArray
import org.json.JSONObject

object JsonMapper {

    fun parseInventoryItems(json: String): List<InventoryItem> {
        val root = JSONObject(json)
        val itemsArray = root.optJSONArray("items") ?: JSONArray()
        val items = mutableListOf<InventoryItem>()

        for (i in 0 until itemsArray.length()) {
            val item = itemsArray.getJSONObject(i)
            val allowedUnitsJson = item.optJSONArray("allowedUnits") ?: JSONArray()
            val allowedUnits = mutableListOf<String>()
            for (j in 0 until allowedUnitsJson.length()) {
                allowedUnits.add(allowedUnitsJson.getString(j))
            }

            items.add(
                InventoryItem(
                    id = item.optString("id"),
                    sku = item.optString("sku"),
                    name = item.optString("name"),
                    category = item.optString("category", "Other"),
                    required = item.optBoolean("required", false),
                    lastQuantity = item.optString("lastQuantity", ""),
                    lastUnit = item.optString("lastUnit", ""),
                    lastUpdatedAt = item.optString("lastUpdatedAt", ""),
                    allowedUnits = allowedUnits
                )
            )
        }
        return items
    }

    fun updatedItemsToJson(items: List<UpdatedInventoryItem>): String {
        val arr = JSONArray()
        items.forEach { item ->
            arr.put(
                JSONObject()
                    .put("id", item.id)
                    .put("name", item.name)
                    .put("category", item.category)
                    .put("quantity", item.quantity)
                    .put("unit", item.unit)
                    .put("required", item.required)
            )
        }
        return arr.toString()
    }

    fun updatedItemsFromJson(json: String): List<UpdatedInventoryItem> {
        val arr = JSONArray(json)
        val items = mutableListOf<UpdatedInventoryItem>()
        for (i in 0 until arr.length()) {
            val obj = arr.getJSONObject(i)
            items.add(
                UpdatedInventoryItem(
                    id = obj.optString("id"),
                    name = obj.optString("name"),
                    category = obj.optString("category"),
                    quantity = obj.optString("quantity"),
                    unit = obj.optString("unit"),
                    required = obj.optBoolean("required", false)
                )
            )
        }
        return items
    }

    fun submitRequestToJson(request: SubmitInventoryRequest): String {
        val root = JSONObject()
            .put("branchCode", request.branchCode)
            .put("submittedAt", request.submittedAt)

        val itemsArray = JSONArray()
        request.items.forEach { item ->
            itemsArray.put(
                JSONObject()
                    .put("itemId", item.id)
                    .put("quantity", item.quantity)
                    .put("unit", item.unit)
            )
        }
        root.put("items", itemsArray)
        return root.toString()
    }
}

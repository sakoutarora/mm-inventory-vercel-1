package com.mm.inventory

data class InventoryItem(
    val id: String,
    val sku: String,
    val name: String,
    val category: String,
    val required: Boolean,
    val lastQuantity: String,
    val lastUnit: String,
    val lastUpdatedAt: String,
    val allowedUnits: List<String>
)

data class UpdatedInventoryItem(
    val id: String,
    val name: String,
    val category: String,
    val quantity: String,
    val unit: String,
    val required: Boolean
)

data class SubmitInventoryRequest(
    val branchCode: String,
    val submittedAt: String,
    val items: List<UpdatedInventoryItem>
)

data class LoginResult(
    val success: Boolean,
    val message: String,
    val token: String = "",
    val username: String = "",
    val branchCode: String = "",
    val branchName: String = ""
)

data class InventoryFetchResult(
    val success: Boolean,
    val message: String,
    val items: List<InventoryItem> = emptyList()
)

data class ApiResult(
    val success: Boolean,
    val message: String
)

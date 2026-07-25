package com.mm.inventory

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.textfield.MaterialAutoCompleteTextView
import java.time.OffsetDateTime
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.Executors

class InventoryActivity : AppCompatActivity() {

    private lateinit var sessionManager: SessionManager
    private lateinit var dateTimeTextView: TextView
    private lateinit var progressBar: ProgressBar
    private lateinit var contentScrollView: ScrollView
    private lateinit var categoryContainer: LinearLayout
    private lateinit var reviewButton: Button
    private lateinit var searchInput: EditText

    private val ioExecutor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())
    private val dateTimeFormatter = DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm:ss a")
    private val lastUpdatedFormatter = DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm a")

    private val inventoryItems = mutableListOf<InventoryItem>()
    private val inventoryEdits = mutableMapOf<String, InventoryEdit>()
    private val categoryExpandedState = mutableMapOf<String, Boolean>()
    private var searchQuery: String = ""
    private val dateTimeUpdater = object : Runnable {
        override fun run() {
            val now = LocalDateTime.now().format(dateTimeFormatter)
            dateTimeTextView.text = "Updating At: $now"
            mainHandler.postDelayed(this, 1000)
        }
    }

    private val unitAliases = mapOf(
        "kg" to "kg",
        "kgs" to "kg",
        "g" to "gms",
        "gm" to "gms",
        "gms" to "gms",
        "l" to "lt",
        "lt" to "lt",
        "ltr" to "lt",
        "litre" to "lt",
        "liter" to "lt",
        "ml" to "ml",
        "pc" to "pcs",
        "pcs" to "pcs",
        "piece" to "pcs",
        "pieces" to "pcs",
        "item" to "pcs",
        "items" to "pcs",
        "pkt" to "pkt",
        "pkts" to "pkt",
        "packet" to "pkt",
        "packets" to "pkt"
    )

    private fun normalizeUnit(raw: String): String {
        val trimmed = raw.trim().lowercase()
        return unitAliases[trimmed] ?: trimmed
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_inventory)

        sessionManager = SessionManager(this)
        if (!sessionManager.isLoggedIn() || sessionManager.getToken().isBlank()) {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        dateTimeTextView = findViewById(R.id.tvDateTime)
        progressBar = findViewById(R.id.progressBar)
        contentScrollView = findViewById(R.id.scrollContent)
        categoryContainer = findViewById(R.id.categoryContainer)
        reviewButton = findViewById(R.id.btnReview)
        searchInput = findViewById(R.id.etSearch)

        mainHandler.post(dateTimeUpdater)
        fetchAndRenderInventory()

        searchInput.addTextChangedListener(
            object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit

                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                    searchQuery = s?.toString().orEmpty()
                    renderItems()
                }

                override fun afterTextChanged(s: Editable?) = Unit
            }
        )

        reviewButton.setOnClickListener {
            reviewUpdates()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        mainHandler.removeCallbacks(dateTimeUpdater)
        ioExecutor.shutdown()
    }

    private fun fetchAndRenderInventory() {
        showLoading(true)

        val branch = sessionManager.getBranch()
        val token = sessionManager.getToken()
        ioExecutor.execute {
            val result = InventoryApiClient.fetchInventoryItems(branch, token)
            runOnUiThread {
                showLoading(false)
                if (result.success) {
                    inventoryItems.clear()
                    inventoryItems.addAll(result.items)
                    inventoryEdits.clear()
                    renderItems()
                } else {
                    Toast.makeText(this, result.message, Toast.LENGTH_LONG).show()
                    if (result.message.contains("token", ignoreCase = true)
                        || result.message.contains("unauthorized", ignoreCase = true)
                    ) {
                        sessionManager.logout()
                        startActivity(Intent(this, LoginActivity::class.java))
                        finish()
                    }
                }
            }
        }
    }

    private fun renderItems() {
        categoryContainer.removeAllViews()
        val items = filteredInventoryItems()

        if (items.isEmpty()) {
            val emptyView = TextView(this).apply {
                text = if (inventoryItems.isEmpty()) {
                    "No inventory items found."
                } else {
                    "No items match \"$searchQuery\"."
                }
                textSize = 16f
                setPadding(8, 24, 8, 8)
            }
            categoryContainer.addView(emptyView)
            return
        }

        val grouped = items.groupBy { it.category }
        grouped.forEach { (category, categoryItems) ->
            val categoryTitle = TextView(this).apply {
                val expanded = categoryExpandedState[category] ?: false
                text = buildCategoryTitle(category, categoryItems.size, expanded)
                textSize = 20f
                setPadding(8, 24, 8, 8)
            }
            categoryContainer.addView(categoryTitle)

            val sectionContainer = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                visibility = if (categoryExpandedState[category] ?: false) View.VISIBLE else View.GONE
            }

            categoryItems.forEach { item ->
                val row = LayoutInflater.from(this).inflate(R.layout.item_inventory_input, sectionContainer, false)

                val itemName = row.findViewById<TextView>(R.id.tvItemName)
                val lastValue = row.findViewById<TextView>(R.id.tvLastValue)
                val lastUpdatedAt = row.findViewById<TextView>(R.id.tvLastUpdatedAt)
                val requiredTag = row.findViewById<TextView>(R.id.tvRequiredTag)
                val quantityInput = row.findViewById<EditText>(R.id.etQuantity)
                val unitInput = row.findViewById<MaterialAutoCompleteTextView>(R.id.actvUnit)

                itemName.text = item.name
                lastValue.text = "Last recorded: ${item.lastQuantity} ${normalizeUnit(item.lastUnit)}".trim()
                lastUpdatedAt.text = buildLastUpdatedText(item.lastUpdatedAt)
                requiredTag.visibility = if (item.required) View.VISIBLE else View.GONE

                val currentEdit = inventoryEdits[item.id] ?: InventoryEdit(item.lastQuantity, normalizeUnit(item.lastUnit))
                quantityInput.setText(currentEdit.quantity)
                unitInput.setText(currentEdit.unit, false)

                val unitOptions = (item.allowedUnits + item.lastUnit)
                    .map { normalizeUnit(it) }
                    .filter { it.isNotBlank() }
                    .distinct()
                val adapter = ArrayAdapter(this, android.R.layout.simple_dropdown_item_1line, unitOptions)
                unitInput.setAdapter(adapter)
                unitInput.keyListener = null

                quantityInput.addTextChangedListener(
                    object : TextWatcher {
                        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit

                        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                            updateInventoryEdit(item.id, quantity = s?.toString().orEmpty())
                        }

                        override fun afterTextChanged(s: Editable?) = Unit
                    }
                )

                unitInput.setOnItemClickListener { _, _, position, _ ->
                    val selectedUnit = adapter.getItem(position).orEmpty()
                    updateInventoryEdit(item.id, unit = selectedUnit)
                }

                unitInput.setOnFocusChangeListener { _, hasFocus ->
                    if (!hasFocus) {
                        updateInventoryEdit(item.id, unit = normalizeUnit(unitInput.text.toString()))
                    }
                }

                sectionContainer.addView(row)
            }

            categoryTitle.setOnClickListener {
                val nextExpanded = sectionContainer.visibility != View.VISIBLE
                sectionContainer.visibility = if (nextExpanded) View.VISIBLE else View.GONE
                categoryExpandedState[category] = nextExpanded
                categoryTitle.text = buildCategoryTitle(category, categoryItems.size, nextExpanded)
            }
            categoryContainer.addView(sectionContainer)
        }
    }

    private fun filteredInventoryItems(): List<InventoryItem> {
        val query = searchQuery.trim().lowercase()
        if (query.isBlank()) {
            return inventoryItems
        }

        return inventoryItems.filter { item ->
            item.name.lowercase().contains(query) ||
                item.sku.lowercase().contains(query) ||
                item.category.lowercase().contains(query)
        }
    }

    private fun buildLastUpdatedText(lastUpdatedAt: String): String {
        if (lastUpdatedAt.isBlank() || lastUpdatedAt.equals("null", ignoreCase = true)) {
            return "Last updated: Never"
        }

        return try {
            val parsed = OffsetDateTime.parse(lastUpdatedAt)
            "Last updated: ${parsed.toLocalDateTime().format(lastUpdatedFormatter)}"
        } catch (_: Exception) {
            "Last updated: $lastUpdatedAt"
        }
    }

    private fun updateInventoryEdit(itemId: String, quantity: String? = null, unit: String? = null) {
        val existing = inventoryEdits[itemId]
        val baseItem = inventoryItems.firstOrNull { it.id == itemId } ?: return
        inventoryEdits[itemId] = InventoryEdit(
            quantity = quantity ?: existing?.quantity ?: baseItem.lastQuantity,
            unit = unit ?: existing?.unit ?: normalizeUnit(baseItem.lastUnit)
        )
    }

    private fun buildCategoryTitle(category: String, itemCount: Int, expanded: Boolean): String {
        val marker = if (expanded) "▲" else "▼"
        val suffix = if (itemCount == 1) "item" else "items"
        return "$marker $category ($itemCount $suffix)"
    }

    private fun reviewUpdates() {
        val missingRequired = mutableListOf<String>()
        val invalidQuantity = mutableListOf<String>()
        val updatedItems = mutableListOf<UpdatedInventoryItem>()

        inventoryItems.forEach { item ->
            val edit = inventoryEdits[item.id]
            val quantity = (edit?.quantity ?: item.lastQuantity).trim()
            val unit = normalizeUnit(edit?.unit ?: item.lastUnit)
            val allowedUnits = (item.allowedUnits + item.lastUnit)
                .map { normalizeUnit(it) }
                .filter { it.isNotBlank() }
                .distinct()

            if (item.required && (quantity.isEmpty() || unit.isEmpty())) {
                missingRequired.add(item.name)
            }

            if (quantity.isNotEmpty()) {
                val numeric = quantity.toDoubleOrNull()
                if (numeric == null || numeric < 0) {
                    invalidQuantity.add(item.name)
                }
            }
            if (unit.isNotEmpty() && !allowedUnits.contains(unit)) {
                invalidQuantity.add(item.name)
            }

            val changed = quantity != item.lastQuantity || unit != normalizeUnit(item.lastUnit)
            if (changed && quantity.isNotEmpty() && unit.isNotEmpty()) {
                updatedItems.add(
                    UpdatedInventoryItem(
                        id = item.id,
                        name = item.name,
                        category = item.category,
                        quantity = quantity,
                        unit = unit,
                        required = item.required
                    )
                )
            }
        }

        if (missingRequired.isNotEmpty()) {
            Toast.makeText(
                this,
                "Fill required items: ${missingRequired.joinToString()}",
                Toast.LENGTH_LONG
            ).show()
            return
        }

        if (invalidQuantity.isNotEmpty()) {
            Toast.makeText(
                this,
                "Invalid quantity for: ${invalidQuantity.joinToString()}",
                Toast.LENGTH_LONG
            ).show()
            return
        }

        if (updatedItems.isEmpty()) {
            Toast.makeText(this, "No updates found to review.", Toast.LENGTH_SHORT).show()
            return
        }

        val intent = Intent(this, ReviewActivity::class.java).apply {
            putExtra(EXTRA_UPDATED_ITEMS, JsonMapper.updatedItemsToJson(updatedItems))
        }
        startActivity(intent)
    }

    private fun showLoading(show: Boolean) {
        progressBar.visibility = if (show) View.VISIBLE else View.GONE
        contentScrollView.visibility = if (show) View.GONE else View.VISIBLE
    }

    data class InventoryEdit(
        val quantity: String,
        val unit: String
    )

    companion object {
        const val EXTRA_UPDATED_ITEMS = "extra_updated_items"
    }
}

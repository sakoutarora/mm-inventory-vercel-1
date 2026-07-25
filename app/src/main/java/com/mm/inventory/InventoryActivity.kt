package com.mm.inventory

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
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

    private val ioExecutor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())
    private val dateTimeFormatter = DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm:ss a")

    private val editors = mutableListOf<ItemEditor>()
    private val dateTimeUpdater = object : Runnable {
        override fun run() {
            val now = LocalDateTime.now().format(dateTimeFormatter)
            dateTimeTextView.text = "Updating At: $now"
            mainHandler.postDelayed(this, 1000)
        }
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

        mainHandler.post(dateTimeUpdater)
        fetchAndRenderInventory()

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
                    renderItems(result.items)
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

    private fun renderItems(items: List<InventoryItem>) {
        categoryContainer.removeAllViews()
        editors.clear()

        if (items.isEmpty()) {
            Toast.makeText(this, "No inventory items found.", Toast.LENGTH_SHORT).show()
            return
        }

        val grouped = items.groupBy { it.category }
        grouped.forEach { (category, categoryItems) ->
            val categoryTitle = TextView(this).apply {
                text = category
                textSize = 20f
                setPadding(8, 24, 8, 8)
            }
            categoryContainer.addView(categoryTitle)

            categoryItems.forEach { item ->
                val row = LayoutInflater.from(this).inflate(R.layout.item_inventory_input, categoryContainer, false)

                val itemName = row.findViewById<TextView>(R.id.tvItemName)
                val lastValue = row.findViewById<TextView>(R.id.tvLastValue)
                val requiredTag = row.findViewById<TextView>(R.id.tvRequiredTag)
                val quantityInput = row.findViewById<EditText>(R.id.etQuantity)
                val unitInput = row.findViewById<MaterialAutoCompleteTextView>(R.id.actvUnit)

                itemName.text = item.name
                lastValue.text = "Last recorded: ${item.lastQuantity} ${item.lastUnit}".trim()
                requiredTag.visibility = if (item.required) View.VISIBLE else View.GONE

                quantityInput.setText(item.lastQuantity)
                unitInput.setText(item.lastUnit, false)

                val unitOptions = (item.allowedUnits + item.lastUnit).filter { it.isNotBlank() }.distinct()
                val adapter = ArrayAdapter(this, android.R.layout.simple_dropdown_item_1line, unitOptions)
                unitInput.setAdapter(adapter)

                editors.add(
                    ItemEditor(
                        item = item,
                        quantityEditText = quantityInput,
                        unitInput = unitInput
                    )
                )

                categoryContainer.addView(row)
            }
        }
    }

    private fun reviewUpdates() {
        val missingRequired = mutableListOf<String>()
        val invalidQuantity = mutableListOf<String>()
        val updatedItems = mutableListOf<UpdatedInventoryItem>()

        editors.forEach { editor ->
            val quantity = editor.quantityEditText.text.toString().trim()
            val unit = editor.unitInput.text.toString().trim()

            if (editor.item.required && (quantity.isEmpty() || unit.isEmpty())) {
                missingRequired.add(editor.item.name)
            }

            if (quantity.isNotEmpty()) {
                val numeric = quantity.toDoubleOrNull()
                if (numeric == null || numeric < 0) {
                    invalidQuantity.add(editor.item.name)
                }
            }

            val changed = quantity != editor.item.lastQuantity || unit != editor.item.lastUnit
            if (changed && quantity.isNotEmpty() && unit.isNotEmpty()) {
                updatedItems.add(
                    UpdatedInventoryItem(
                        id = editor.item.id,
                        name = editor.item.name,
                        category = editor.item.category,
                        quantity = quantity,
                        unit = unit,
                        required = editor.item.required
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

    data class ItemEditor(
        val item: InventoryItem,
        val quantityEditText: EditText,
        val unitInput: MaterialAutoCompleteTextView
    )

    companion object {
        const val EXTRA_UPDATED_ITEMS = "extra_updated_items"
    }
}

package com.mm.inventory

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.Executors

class ReviewActivity : AppCompatActivity() {

    private lateinit var sessionManager: SessionManager
    private lateinit var summaryTextView: TextView
    private lateinit var updatedContainer: LinearLayout
    private lateinit var submitButton: Button
    private lateinit var editButton: Button
    private lateinit var progressBar: ProgressBar

    private val ioExecutor = Executors.newSingleThreadExecutor()
    private val dateTimeFormatter = DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm:ss a")

    private var updatedItems: List<UpdatedInventoryItem> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_review)

        sessionManager = SessionManager(this)
        if (!sessionManager.isLoggedIn() || sessionManager.getToken().isBlank()) {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        summaryTextView = findViewById(R.id.tvSummary)
        updatedContainer = findViewById(R.id.updatedItemsContainer)
        submitButton = findViewById(R.id.btnSubmit)
        editButton = findViewById(R.id.btnEdit)
        progressBar = findViewById(R.id.submitProgress)

        val updatedJson = intent.getStringExtra(InventoryActivity.EXTRA_UPDATED_ITEMS).orEmpty()
        if (updatedJson.isBlank()) {
            Toast.makeText(this, "No updated items found.", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        updatedItems = JsonMapper.updatedItemsFromJson(updatedJson)
        if (updatedItems.isEmpty()) {
            Toast.makeText(this, "No updated items found.", Toast.LENGTH_SHORT).show()
            finish()
            return
        }

        renderSummary()
        renderUpdatedItems()

        editButton.setOnClickListener {
            finish()
        }

        submitButton.setOnClickListener {
            submitUpdates()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        ioExecutor.shutdown()
    }

    private fun renderSummary() {
        val user = sessionManager.getUsername()
        val branch = sessionManager.getBranch()
        val now = LocalDateTime.now().format(dateTimeFormatter)
        summaryTextView.text = "Review by: $user\nBranch: $branch\nReview Time: $now\nUpdated Items: ${updatedItems.size}"
    }

    private fun renderUpdatedItems() {
        updatedContainer.removeAllViews()
        updatedItems.forEach { item ->
            val row = LayoutInflater.from(this).inflate(R.layout.item_review_row, updatedContainer, false)
            val title = row.findViewById<TextView>(R.id.tvReviewTitle)
            val details = row.findViewById<TextView>(R.id.tvReviewDetails)

            title.text = item.name
            details.text = "Category: ${item.category} | New Value: ${item.quantity} ${item.unit}"

            updatedContainer.addView(row)
        }
    }

    private fun submitUpdates() {
        setSubmitting(true)

        val request = SubmitInventoryRequest(
            branchCode = sessionManager.getBranch(),
            submittedAt = OffsetDateTime.now().toString(),
            items = updatedItems
        )
        val token = sessionManager.getToken()

        ioExecutor.execute {
            val result = InventoryApiClient.submitInventoryUpdate(request, token)
            runOnUiThread {
                setSubmitting(false)
                Toast.makeText(this, result.message, Toast.LENGTH_LONG).show()
                if (result.success) {
                    val intent = Intent(this, LandingActivity::class.java).apply {
                        flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
                    }
                    startActivity(intent)
                    finish()
                } else if (result.message.contains("token", ignoreCase = true)
                    || result.message.contains("unauthorized", ignoreCase = true)
                ) {
                    sessionManager.logout()
                    startActivity(Intent(this, LoginActivity::class.java))
                    finish()
                }
            }
        }
    }

    private fun setSubmitting(submitting: Boolean) {
        progressBar.visibility = if (submitting) View.VISIBLE else View.GONE
        submitButton.isEnabled = !submitting
        editButton.isEnabled = !submitting
    }
}

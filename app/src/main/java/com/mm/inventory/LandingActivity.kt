package com.mm.inventory

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class LandingActivity : AppCompatActivity() {

    private lateinit var sessionManager: SessionManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_landing)

        sessionManager = SessionManager(this)

        if (!sessionManager.isLoggedIn() || sessionManager.getToken().isBlank()) {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        val welcomeText = findViewById<TextView>(R.id.tvWelcome)
        val branchText = findViewById<TextView>(R.id.tvBranch)
        val startButton = findViewById<Button>(R.id.btnStartUpdate)
        val logoutButton = findViewById<Button>(R.id.btnLogout)

        val username = sessionManager.getUsername()
        val branchCode = sessionManager.getBranch()
        val branchName = sessionManager.getBranchName()

        welcomeText.text = "Hello, $username"
        branchText.text = "Branch: $branchName ($branchCode)"

        startButton.setOnClickListener {
            startActivity(Intent(this, InventoryActivity::class.java))
        }

        logoutButton.setOnClickListener {
            sessionManager.logout()
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }
}

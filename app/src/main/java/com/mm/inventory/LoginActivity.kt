package com.mm.inventory

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.util.concurrent.Executors

class LoginActivity : AppCompatActivity() {

    private lateinit var sessionManager: SessionManager
    private val ioExecutor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        sessionManager = SessionManager(this)

        if (sessionManager.isLoggedIn()) {
            startActivity(Intent(this, LandingActivity::class.java))
            finish()
            return
        }

        val usernameEditText = findViewById<EditText>(R.id.etUsername)
        val passwordEditText = findViewById<EditText>(R.id.etPassword)
        val branchEditText = findViewById<EditText>(R.id.etBranch)
        val loginButton = findViewById<Button>(R.id.btnLogin)

        loginButton.setOnClickListener {
            val username = usernameEditText.text.toString().trim().lowercase()
            val password = passwordEditText.text.toString().trim()
            val branchCode = branchEditText.text.toString().trim().uppercase()

            if (username.isEmpty() || password.isEmpty() || branchCode.isEmpty()) {
                Toast.makeText(this, "Please fill username, password, and branch code.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            loginButton.isEnabled = false
            loginButton.text = "Logging in..."

            ioExecutor.execute {
                val result = InventoryApiClient.login(username, password, branchCode)
                runOnUiThread {
                    loginButton.isEnabled = true
                    loginButton.text = "Login"

                    if (result.success) {
                        sessionManager.saveLogin(
                            username = result.username,
                            branchCode = result.branchCode,
                            branchName = result.branchName,
                            token = result.token
                        )
                        startActivity(Intent(this, LandingActivity::class.java))
                        finish()
                    } else {
                        Toast.makeText(this, result.message, Toast.LENGTH_LONG).show()
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        ioExecutor.shutdown()
    }
}

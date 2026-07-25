package com.mm.inventory

import android.content.Context

class SessionManager(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun saveLogin(username: String, branchCode: String, branchName: String, token: String) {
        prefs.edit()
            .putString(KEY_USERNAME, username)
            .putString(KEY_BRANCH_CODE, branchCode)
            .putString(KEY_BRANCH_NAME, branchName)
            .putString(KEY_TOKEN, token)
            .putBoolean(KEY_LOGGED_IN, true)
            .apply()
    }

    fun isLoggedIn(): Boolean = prefs.getBoolean(KEY_LOGGED_IN, false)

    fun getUsername(): String = prefs.getString(KEY_USERNAME, "") ?: ""

    fun getBranch(): String = prefs.getString(KEY_BRANCH_CODE, "") ?: ""

    fun getBranchName(): String = prefs.getString(KEY_BRANCH_NAME, "") ?: ""

    fun getToken(): String = prefs.getString(KEY_TOKEN, "") ?: ""

    fun logout() {
        prefs.edit().clear().apply()
    }

    companion object {
        private const val PREFS_NAME = "inventory_session"
        private const val KEY_LOGGED_IN = "is_logged_in"
        private const val KEY_USERNAME = "username"
        private const val KEY_BRANCH_CODE = "branch_code"
        private const val KEY_BRANCH_NAME = "branch_name"
        private const val KEY_TOKEN = "auth_token"
    }
}

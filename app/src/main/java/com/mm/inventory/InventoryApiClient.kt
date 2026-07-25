package com.mm.inventory

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

object InventoryApiClient {

    private const val BASE_URL = "https://dqrul4dok9.execute-api.ap-south-1.amazonaws.com/prod"

    fun login(username: String, password: String, branchCode: String): LoginResult {
        return try {
            val connection = openConnection("POST", "/api/v1/auth/login")
            val payload = JSONObject()
                .put("username", username)
                .put("password", password)
                .put("branchCode", branchCode)
                .toString()

            OutputStreamWriter(connection.outputStream).use { writer ->
                writer.write(payload)
                writer.flush()
            }

            val responseCode = connection.responseCode
            val responseBody = readResponse(connection, responseCode)
            val responseJson = if (responseBody.isNotBlank()) JSONObject(responseBody) else JSONObject()

            if (responseCode in 200..299) {
                val user = responseJson.optJSONObject("user") ?: JSONObject()
                val branch = responseJson.optJSONObject("branch") ?: JSONObject()
                LoginResult(
                    success = true,
                    message = "Login successful.",
                    token = responseJson.optString("token"),
                    username = user.optString("username", username),
                    branchCode = branch.optString("code", branchCode),
                    branchName = branch.optString("name", branchCode)
                )
            } else {
                LoginResult(false, responseJson.optString("message", "Login failed."))
            }
        } catch (e: Exception) {
            LoginResult(false, "Login failed: ${e.message ?: "Unknown error"}")
        }
    }

    fun fetchInventoryItems(branchCode: String, token: String): InventoryFetchResult {
        return try {
            val encodedBranch = URLEncoder.encode(branchCode, "UTF-8")
            val path = "/api/v1/inventory/items?branchCode=$encodedBranch"
            val connection = openConnection("GET", path, token)

            val responseCode = connection.responseCode
            val responseBody = readResponse(connection, responseCode)

            if (responseCode in 200..299) {
                InventoryFetchResult(
                    success = true,
                    message = "Items loaded.",
                    items = JsonMapper.parseInventoryItems(responseBody)
                )
            } else {
                val message = parseMessage(responseBody, "Failed to fetch inventory items.")
                InventoryFetchResult(false, message)
            }
        } catch (e: Exception) {
            InventoryFetchResult(false, "Fetch failed: ${e.message ?: "Unknown error"}")
        }
    }

    fun submitInventoryUpdate(request: SubmitInventoryRequest, token: String): ApiResult {
        return try {
            val connection = openConnection("POST", "/api/v1/inventory/update", token)
            val payload = JsonMapper.submitRequestToJson(request)

            OutputStreamWriter(connection.outputStream).use { writer ->
                writer.write(payload)
                writer.flush()
            }

            val responseCode = connection.responseCode
            val responseBody = readResponse(connection, responseCode)
            if (responseCode in 200..299) {
                ApiResult(true, parseMessage(responseBody, "Inventory submitted successfully."))
            } else {
                ApiResult(false, parseMessage(responseBody, "Submission failed."))
            }
        } catch (e: Exception) {
            ApiResult(false, "Submission failed: ${e.message ?: "Unknown error"}")
        }
    }

    private fun openConnection(method: String, path: String, token: String? = null): HttpURLConnection {
        val url = URL("$BASE_URL$path")
        return (url.openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10000
            readTimeout = 10000
            setRequestProperty("Content-Type", "application/json")
            if (!token.isNullOrBlank()) {
                setRequestProperty("Authorization", "Bearer $token")
            }
            doInput = true
            doOutput = method == "POST" || method == "PUT" || method == "PATCH"
        }
    }

    private fun readResponse(connection: HttpURLConnection, responseCode: Int): String {
        val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
        if (stream == null) return ""
        return stream.use { BufferedReader(InputStreamReader(it)).readText() }
    }

    private fun parseMessage(rawBody: String, fallback: String): String {
        return try {
            if (rawBody.isBlank()) return fallback
            JSONObject(rawBody).optString("message", fallback)
        } catch (_: Exception) {
            fallback
        }
    }
}

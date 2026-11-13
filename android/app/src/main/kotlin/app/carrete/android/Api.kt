package app.carrete.android

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class ApiException(val status: Int, message: String, val code: String? = null) : Exception(message)

object Http {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .build()
}

data class Space(val id: String, val name: String, val role: String)
data class AlbumRef(val id: String, val name: String)

/** Cliente mínimo de la API de Carrete con el *token* de dispositivo (Authorization: Bearer). */
class CarreteApi(private val server: String, private val token: String?, private val client: OkHttpClient = Http.client) {
    private val json = "application/json".toMediaType()

    private fun request(path: String): Request.Builder {
        val builder = Request.Builder().url(server + path).header("Accept", "application/json")
        if (token != null) builder.header("Authorization", "Bearer $token")
        return builder
    }

    private fun send(builder: Request.Builder): JSONObject? {
        client.newCall(builder.build()).execute().use { response -> return parse(response) }
    }

    private fun parse(response: Response): JSONObject? {
        val body = response.body?.string().orEmpty()
        if (!response.isSuccessful) {
            val problem = try { JSONObject(body) } catch (e: Exception) { JSONObject() }
            throw ApiException(response.code, problem.optString("detail", "Error ${response.code}"), problem.optString("code").ifEmpty { null })
        }
        return if (body.isBlank()) null else JSONObject(body)
    }

    private fun post(path: String, payload: JSONObject) = send(request(path).post(payload.toString().toRequestBody(json)))

    /** Devuelve (etapa, token). La etapa es «full», «totp» o «enroll». */
    fun deviceLogin(username: String, password: String, deviceName: String): Pair<String, String> {
        val out = post("/api/v1/auth/device/login", JSONObject().put("username", username).put("password", password).put("device_name", deviceName))!!
        return out.getString("stage") to out.getString("token")
    }

    fun verifyCode(code: String): String = post("/api/v1/auth/totp", JSONObject().put("code", code))!!.getString("stage")

    fun spaces(): Pair<List<Space>, String?> {
        val me = send(request("/api/v1/me").get())!!
        val list = me.getJSONArray("spaces")
        val spaces = (0 until list.length()).map { i ->
            val s = list.getJSONObject(i)
            Space(s.getString("id"), s.getString("name"), s.getString("role"))
        }.filter { !it.role.equals("viewer", true) }
        return spaces to me.optString("current_space_id").ifEmpty { null }
    }

    fun albums(spaceId: String): List<AlbumRef> {
        client.newCall(request("/api/v1/spaces/$spaceId/albums").get().build()).execute().use { response ->
            if (!response.isSuccessful) return emptyList()
            val array = JSONArray(response.body?.string().orEmpty())
            return (0 until array.length()).map { i -> array.getJSONObject(i).let { AlbumRef(it.getString("id"), it.getString("name")) } }
        }
    }

    /** Deduplicación en origen: qué SHA-256 ya están en el espacio. */
    fun present(spaceId: String, hashes: List<String>): Set<String> {
        if (hashes.isEmpty()) return emptySet()
        val out = post("/api/v1/spaces/$spaceId/assets/check", JSONObject().put("sha256", JSONArray(hashes)))!!
        val list = out.getJSONArray("present")
        return (0 until list.length()).map { list.getString(it) }.toSet()
    }

    fun summary(spaceId: String, uploaded: Int, duplicates: Int, failed: Int) {
        post("/api/v1/spaces/$spaceId/uploads/summary", JSONObject().put("uploaded", uploaded).put("duplicates", duplicates).put("failed", failed))
    }

    /** Código de un solo uso para que la WebView obtenga su sesión sin la contraseña. */
    fun webCode(): String = post("/api/v1/auth/device/web-code", JSONObject())!!.getString("code")

    /** Versión de la app publicada en el servidor, o null si no hay. */
    fun latestVersionCode(): Int? {
        val out = send(request("/api/v1/app/android").get()) ?: return null
        return if (out.optBoolean("available")) out.optInt("version_code").takeIf { it > 0 } else null
    }
}

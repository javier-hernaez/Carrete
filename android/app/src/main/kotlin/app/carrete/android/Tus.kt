package app.carrete.android

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.BufferedSink
import java.io.File
import java.io.RandomAccessFile
import java.util.Base64

/** Resultado de una subida terminada. */
data class Uploaded(val assetId: String?, val duplicate: Boolean)

/**
 * Cliente tus 1.0 propio sobre OkHttp: crea la subida, la reanuda desde donde se quedó
 * y envía trozos de 16 MB. Un corte de red no obliga a empezar de cero.
 */
class TusClient(private val server: String, private val token: String, private val client: OkHttpClient = Http.client) {
    private val octet = "application/offset+octet-stream".toMediaType()

    private fun base(url: String) = Request.Builder().url(url).header("Tus-Resumable", "1.0.0").header("Authorization", "Bearer $token")

    fun create(length: Long, metadata: Map<String, String>): String {
        val meta = metadata.entries.joinToString(",") { (k, v) -> "$k ${Base64.getEncoder().encodeToString(v.toByteArray())}" }
        val request = base("$server/api/v1/uploads")
            .header("Upload-Length", length.toString())
            .header("Upload-Metadata", meta)
            .post(ByteArray(0).toRequestBody(null))
            .build()
        client.newCall(request).execute().use { response ->
            if (response.code == 409) throw DuplicateException()
            if (response.code != 201) throw ApiException(response.code, problem(response.body?.string()), null)
            val location = response.header("Location") ?: throw ApiException(500, "Sin Location", null)
            return if (location.startsWith("http")) location else server + location
        }
    }

    /** Desplazamiento actual en el servidor, o null si la subida ya no existe (caducó o terminó). */
    fun offset(location: String): Long? {
        client.newCall(base(location).head().build()).execute().use { response ->
            if (response.code == 404) return null
            if (!response.isSuccessful) throw ApiException(response.code, "HEAD ${response.code}", null)
            return response.header("Upload-Offset")?.toLongOrNull()
        }
    }

    /** Envía el resto del fichero desde ``start``. Devuelve el resultado al terminar. */
    fun send(location: String, file: File, start: Long, chunkSize: Long = CHUNK, onProgress: (Long) -> Unit = {}): Uploaded {
        var offset = start
        val length = file.length()
        var last: Uploaded? = null
        while (offset < length) {
            val size = minOf(chunkSize, length - offset)
            val body = ChunkBody(file, offset, size)
            val request = base(location).header("Upload-Offset", offset.toString()).patch(body).build()
            client.newCall(request).execute().use { response ->
                if (response.code != 204) throw ApiException(response.code, problem(response.body?.string()), null)
                offset = response.header("Upload-Offset")?.toLongOrNull() ?: (offset + size)
                if (offset >= length) last = Uploaded(response.header("Carrete-Asset-Id"), response.header("Carrete-Duplicate") == "1")
            }
            onProgress(offset)
        }
        return last ?: Uploaded(null, false)
    }

    private fun problem(body: String?): String = try {
        org.json.JSONObject(body ?: "").optString("detail", "Error en la subida")
    } catch (e: Exception) {
        "Error en la subida"
    }

    private inner class ChunkBody(private val file: File, private val offset: Long, private val size: Long) : RequestBody() {
        override fun contentType() = octet
        override fun contentLength() = size
        override fun writeTo(sink: BufferedSink) {
            RandomAccessFile(file, "r").use { raf ->
                raf.seek(offset)
                val buffer = ByteArray(64 * 1024)
                var remaining = size
                while (remaining > 0) {
                    val read = raf.read(buffer, 0, minOf(buffer.size.toLong(), remaining).toInt())
                    if (read < 0) break
                    sink.write(buffer, 0, read)
                    remaining -= read
                }
            }
        }
    }

    class DuplicateException : Exception("Ya estaba en el espacio")

    companion object {
        const val CHUNK = 16L * 1024 * 1024
    }
}

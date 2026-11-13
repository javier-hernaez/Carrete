package app.carrete.android

import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID

/** Elemento de la cola. El fichero ya está copiado al almacenamiento privado de la app. */
data class QueueItem(
    val id: String,
    val file: String,
    val name: String,
    val size: Long,
    val mtimeMs: Long?,
    val spaceId: String,
    val albumId: String?,
    val isVideo: Boolean,
    val status: String = PENDING,
    val sha256: String? = null,
    val uploadUrl: String? = null,
    val error: String? = null,
    val batch: String,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("id", id).put("file", file).put("name", name).put("size", size).put("mtime", mtimeMs ?: JSONObject.NULL)
        .put("space", spaceId).put("album", albumId ?: JSONObject.NULL).put("video", isVideo).put("status", status)
        .put("sha256", sha256 ?: JSONObject.NULL).put("upload", uploadUrl ?: JSONObject.NULL).put("error", error ?: JSONObject.NULL)
        .put("batch", batch)

    companion object {
        const val PENDING = "pending"
        const val DONE = "done"
        const val DUPLICATE = "duplicate"
        const val FAILED = "failed"

        fun fromJson(o: JSONObject) = QueueItem(
            id = o.getString("id"), file = o.getString("file"), name = o.getString("name"), size = o.getLong("size"),
            mtimeMs = if (o.isNull("mtime")) null else o.getLong("mtime"), spaceId = o.getString("space"),
            albumId = if (o.isNull("album")) null else o.getString("album"), isVideo = o.getBoolean("video"),
            status = o.getString("status"), sha256 = if (o.isNull("sha256")) null else o.getString("sha256"),
            uploadUrl = if (o.isNull("upload")) null else o.getString("upload"),
            error = if (o.isNull("error")) null else o.getString("error"), batch = o.getString("batch"),
        )
    }
}

/**
 * Cola de subida persistente en disco: sobrevive a reinicios del móvil y a que el sistema mate la app
 *. Un fichero JSON por elemento; el contenido, copiado al almacenamiento privado.
 */
class QueueStore(private val root: File) {
    private val items = File(root, "items").apply { mkdirs() }
    private val files = File(root, "files").apply { mkdirs() }

    @Synchronized
    fun add(input: InputStream, name: String, size: Long, mtimeMs: Long?, spaceId: String, albumId: String?, isVideo: Boolean, batch: String): QueueItem {
        val id = UUID.randomUUID().toString()
        val target = File(files, id)
        input.use { src -> target.outputStream().use { src.copyTo(it, 64 * 1024) } }
        val item = QueueItem(id, target.absolutePath, name, if (size > 0) size else target.length(), mtimeMs, spaceId, albumId, isVideo, batch = batch)
        save(item)
        return item
    }

    @Synchronized
    fun save(item: QueueItem) {
        val tmp = File(items, "${item.id}.tmp")
        tmp.writeText(item.toJson().toString())
        tmp.renameTo(File(items, "${item.id}.json"))
    }

    @Synchronized
    fun all(): List<QueueItem> = (items.listFiles { f -> f.name.endsWith(".json") } ?: emptyArray())
        .mapNotNull { f -> try { QueueItem.fromJson(JSONObject(f.readText())) } catch (e: Exception) { null } }
        .sortedBy { it.id }

    fun pending(includeVideos: Boolean = true): List<QueueItem> = all().filter { it.status == QueueItem.PENDING && (includeVideos || !it.isVideo) }

    /** Terminado: se borra la copia temporal del fichero, se conserva el registro para el resumen. */
    @Synchronized
    fun finish(item: QueueItem, status: String, error: String? = null) {
        File(item.file).delete()
        save(item.copy(status = status, error = error))
    }

    data class Summary(val uploaded: Int, val duplicates: Int, val failed: Int, val pending: Int)

    fun summary(batch: String? = null): Summary {
        val list = all().filter { batch == null || it.batch == batch }
        return Summary(
            list.count { it.status == QueueItem.DONE }, list.count { it.status == QueueItem.DUPLICATE },
            list.count { it.status == QueueItem.FAILED }, list.count { it.status == QueueItem.PENDING },
        )
    }

    /** Borra los registros de lotes ya terminados. */
    @Synchronized
    fun forgetFinished() {
        all().groupBy { it.batch }.filterValues { group -> group.none { it.status == QueueItem.PENDING } }
            .values.flatten().forEach { File(items, "${it.id}.json").delete() }
    }

    companion object {
        fun sha256(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { input ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    digest.update(buffer, 0, read)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }
    }
}

/**
 * Sube un elemento de la cola: huella → ¿ya estaba? → crear o reanudar la subida tus → trozos.
 * Devuelve el elemento actualizado. Lanza excepción si hay que reintentar más tarde (red, servidor).
 */
class Uploader(private val api: CarreteApi, private val tus: TusClient, private val store: QueueStore) {
    fun upload(item: QueueItem, onProgress: (Long) -> Unit = {}): QueueItem {
        val file = File(item.file)
        if (!file.exists()) {
            store.finish(item, QueueItem.FAILED, "El fichero ya no existe")
            return item.copy(status = QueueItem.FAILED)
        }
        var current = item
        if (current.sha256 == null) {
            current = current.copy(sha256 = QueueStore.sha256(file))
            store.save(current)
        }
        val sha = current.sha256!!
        if (current.uploadUrl == null && sha in api.present(current.spaceId, listOf(sha))) {
            store.finish(current, QueueItem.DUPLICATE)
            return current.copy(status = QueueItem.DUPLICATE)
        }
        var offset = 0L
        val resumed = current.uploadUrl?.let { tus.offset(it) }
        if (resumed == null) {
            val metadata = buildMap {
                put("filename", current.name)
                put("sha256", sha)
                put("space_id", current.spaceId)
                current.mtimeMs?.let { put("mtime", it.toString()) }
                current.albumId?.let { put("album_id", it) }
            }
            val location = try {
                tus.create(file.length(), metadata)
            } catch (e: TusClient.DuplicateException) {
                store.finish(current, QueueItem.DUPLICATE)
                return current.copy(status = QueueItem.DUPLICATE)
            }
            current = current.copy(uploadUrl = location)
            store.save(current)
        } else {
            offset = resumed
        }
        return try {
            val result = tus.send(current.uploadUrl!!, file, offset, onProgress = onProgress)
            val status = if (result.duplicate) QueueItem.DUPLICATE else QueueItem.DONE
            store.finish(current, status)
            current.copy(status = status)
        } catch (e: ApiException) {
            if (e.status in 400..499 && e.status != 409 && e.status != 423 && e.status != 404) {
                store.finish(current, QueueItem.FAILED, e.message)
                return current.copy(status = QueueItem.FAILED, error = e.message)
            }
            if (e.status == 404) store.save(current.copy(uploadUrl = null)) // caducó: empezar de nuevo
            throw e
        }
    }
}

package app.carrete.android

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.util.Log
import java.io.InputStream
import java.util.UUID

/**
 * Entrada a la cola.
 *
 * - Desde «Compartir» o el selector de fotos: copia cada fichero al almacenamiento privado de la app en el
 *   momento (los permisos sobre esas URIs son temporales), con su nombre original y su fecha de
 *   modificación.
 * - Desde una carpeta elegida: no copia nada; guarda la URI de cada original con permiso persistente y
 *   la cola los lee al subir. Así una carpeta con miles de fotos no llena el móvil.
 */
class Intake(private val context: Context) {
    data class Result(val added: Int, val failed: Int)

    fun enqueue(uris: List<Uri>, spaceId: String, albumId: String?): Result {
        val store = UploadWorker.queueStore(context)
        val batch = UUID.randomUUID().toString()
        var added = 0
        var failed = 0
        for (uri in uris) {
            // Un fichero que no se puede leer no debe tumbar el lote entero.
            try {
                val (name, size, mtime) = describe(uri)
                val mime = context.contentResolver.getType(uri).orEmpty()
                val input = open(uri) ?: throw java.io.FileNotFoundException(uri.toString())
                store.add(input, name, size, mtime, spaceId, albumId, isVideo(mime, name), batch)
                added++
            } catch (e: Exception) {
                Log.w(TAG, "No se pudo leer $uri", e)
                failed++
            }
        }
        if (added > 0) UploadWorker.enqueue(context)
        return Result(added, failed)
    }

    /** Todas las fotos y vídeos de una carpeta (y sus subcarpetas) elegida con el selector de carpetas. */
    fun enqueueFolder(tree: Uri, spaceId: String): Result {
        context.contentResolver.takePersistableUriPermission(tree, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        val store = UploadWorker.queueStore(context)
        val batch = UUID.randomUUID().toString()
        var added = 0
        for (doc in Folder.media(context, tree)) {
            store.addReference(doc.uri.toString(), doc.name, doc.size, doc.mtimeMs, spaceId, null, doc.isVideo, batch, tree.toString())
            added++
        }
        if (added > 0) {
            UploadWorker.enqueue(context)
        } else {
            context.contentResolver.releasePersistableUriPermission(tree, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        return Result(added, 0)
    }

    /**
     * Con el permiso ACCESS_MEDIA_LOCATION se intenta leer el original con su ubicación GPS. Android
     * no siempre lo permite (las fotos del selector moderno solo lo admiten si la persona compartió la
     * ubicación al elegirlas): si falla, se lee la foto tal cual.
     */
    private fun open(uri: Uri): InputStream? {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && uri.authority == MediaStore.AUTHORITY) {
            try {
                context.contentResolver.openInputStream(MediaStore.setRequireOriginal(uri))?.let { return it }
            } catch (e: Exception) {
                // UnsupportedOperationException, SecurityException…: sin ubicación, pero se sube.
                Log.i(TAG, "Sin el original con ubicación (${e.javaClass.simpleName}); se sube la foto tal cual")
            }
        }
        return context.contentResolver.openInputStream(uri)
    }

    private fun describe(uri: Uri): Triple<String, Long, Long?> {
        var name = uri.lastPathSegment ?: "foto"
        var size = -1L
        var mtime: Long? = null
        try {
            context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME).takeIf { it >= 0 }?.let { name = cursor.getString(it) ?: name }
                    cursor.getColumnIndex(OpenableColumns.SIZE).takeIf { it >= 0 }?.let { size = cursor.getLong(it) }
                    cursor.getColumnIndex(MediaStore.MediaColumns.DATE_MODIFIED).takeIf { it >= 0 }?.let {
                        mtime = cursor.getLong(it).takeIf { s -> s > 0 }?.times(1000)
                    }
                }
            }
        } catch (e: Exception) {
            // Sin metadatos: el servidor deducirá la fecha del nombre o del contenido.
        }
        return Triple(name, size, mtime)
    }

    companion object {
        private const val TAG = "CarreteIntake"

        fun isVideo(mime: String, name: String) = mime.startsWith("video/") || name.lowercase().endsWith(".mp4")
    }
}

/** Mensaje para la persona tras encolar. */
fun intakeMessage(context: Context, result: Intake.Result): String = when {
    result.added == 0 && result.failed > 0 -> context.getString(R.string.nothing_read)
    result.added == 0 -> context.getString(R.string.folder_empty)
    result.failed > 0 -> context.getString(R.string.queued_some_failed, result.added, result.failed)
    else -> context.getString(R.string.queued_count, result.added)
}

/** Recorre una carpeta del selector de carpetas (Storage Access Framework) sin copiar nada. */
object Folder {
    data class Doc(val uri: Uri, val name: String, val size: Long, val mtimeMs: Long?, val isVideo: Boolean)

    private val MEDIA_EXTENSIONS = setOf("jpg", "jpeg", "png", "heic", "heif", "webp", "gif", "dng", "mp4", "mov", "3gp", "mkv", "webm")

    fun isMedia(mime: String, name: String): Boolean =
        mime.startsWith("image/") || mime.startsWith("video/") || name.substringAfterLast('.', "").lowercase() in MEDIA_EXTENSIONS

    fun media(context: Context, tree: Uri): List<Doc> {
        val out = mutableListOf<Doc>()
        val pending = ArrayDeque(listOf(DocumentsContract.getTreeDocumentId(tree)))
        val columns = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED,
        )
        while (pending.isNotEmpty()) {
            val parent = pending.removeFirst()
            val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parent)
            context.contentResolver.query(children, columns, null, null, null)?.use { c ->
                while (c.moveToNext()) {
                    val id = c.getString(0)
                    val name = c.getString(1) ?: continue
                    val mime = c.getString(2).orEmpty()
                    if (name.startsWith(".")) continue // ocultos (.thumbnails, .trashed-…)
                    if (mime == DocumentsContract.Document.MIME_TYPE_DIR) {
                        pending.addLast(id)
                    } else if (isMedia(mime, name)) {
                        val size = if (c.isNull(3)) -1L else c.getLong(3)
                        val mtime = if (c.isNull(4)) null else c.getLong(4).takeIf { it > 0 }
                        out += Doc(DocumentsContract.buildDocumentUriUsingTree(tree, id), name, size, mtime, Intake.isVideo(mime, name))
                    }
                }
            }
        }
        return out
    }
}

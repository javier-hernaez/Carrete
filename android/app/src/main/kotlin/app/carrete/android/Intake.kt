package app.carrete.android

import android.content.Context
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.provider.OpenableColumns
import java.util.UUID

/**
 * Entrada a la cola desde «Compartir» o el selector: copia cada fichero al almacenamiento privado de la
 * app en el momento (los permisos sobre URIs recibidas son temporales), con su nombre original y
 * su fecha de modificación, y lanza la subida.
 */
class Intake(private val context: Context) {
    fun enqueue(uris: List<Uri>, spaceId: String, albumId: String?): Int {
        val store = UploadWorker.queueStore(context)
        val batch = UUID.randomUUID().toString()
        var added = 0
        for (uri in uris) {
            val source = original(uri)
            val (name, size, mtime) = describe(uri)
            val mime = context.contentResolver.getType(uri).orEmpty()
            val input = context.contentResolver.openInputStream(source) ?: continue
            store.add(input, name, size, mtime, spaceId, albumId, mime.startsWith("video/") || name.lowercase().endsWith(".mp4"), batch)
            added++
        }
        if (added > 0) UploadWorker.enqueue(context)
        return added
    }

    /** Con el permiso ACCESS_MEDIA_LOCATION, se lee el original con su ubicación GPS. */
    private fun original(uri: Uri): Uri = try {
        // En Android 9 no hace falta: la ubicación no se borra al leer la foto.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && uri.authority == MediaStore.AUTHORITY) {
            MediaStore.setRequireOriginal(uri)
        } else {
            uri
        }
    } catch (e: Exception) {
        uri
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
}

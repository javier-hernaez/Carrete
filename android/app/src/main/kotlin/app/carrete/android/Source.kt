package app.carrete.android

import android.content.Context
import android.net.Uri
import android.os.ParcelFileDescriptor
import java.io.File
import java.io.FileInputStream
import java.io.InputStream

/**
 * De dónde se lee un elemento de la cola: una copia en el almacenamiento privado (lo que llega por
 * «Compartir» o el selector de fotos, cuyos permisos son temporales) o el fichero original de una carpeta
 * elegida, con permiso persistente (no se copia: sirve para miles de fotos sin llenar el móvil).
 */
interface Source {
    fun exists(): Boolean
    fun length(): Long

    /** Flujo colocado en ``offset``, para reanudar una subida sin releer desde el principio. */
    fun open(offset: Long = 0): InputStream

    /** Se llama al terminar: borra la copia temporal (los originales de una carpeta no se tocan). */
    fun release()

    companion object {
        fun isContentUri(value: String) = value.startsWith("content://")
    }
}

class FileSource(private val file: File) : Source {
    override fun exists() = file.exists()
    override fun length() = file.length()
    override fun open(offset: Long): InputStream = FileInputStream(file).also { it.channel.position(offset) }
    override fun release() {
        file.delete()
    }
}

class UriSource(private val context: Context, private val uri: Uri) : Source {
    override fun exists(): Boolean = try {
        context.contentResolver.openFileDescriptor(uri, "r")?.use { true } ?: false
    } catch (e: Exception) {
        false
    }

    override fun length(): Long = context.contentResolver.openFileDescriptor(uri, "r")?.use { it.statSize } ?: -1L

    override fun open(offset: Long): InputStream {
        val fd = context.contentResolver.openFileDescriptor(uri, "r") ?: throw java.io.FileNotFoundException(uri.toString())
        return ParcelFileDescriptor.AutoCloseInputStream(fd).also { it.channel.position(offset) }
    }

    override fun release() = Unit
}

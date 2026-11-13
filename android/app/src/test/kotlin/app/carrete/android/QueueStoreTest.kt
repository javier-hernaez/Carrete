package app.carrete.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class QueueStoreTest {
    @get:Rule val tmp = TemporaryFolder()

    @Test
    fun guarda_copia_y_sobrevive_a_reiniciar() {
        val root = tmp.newFolder("cola")
        val store = QueueStore(root)
        val photo = store.add("foto".byteInputStream(), "IMG-20230415-WA0001.jpg", -1, 1_681_000_000_000, "esp", null, false, "lote")
        val video = store.add("video".byteInputStream(), "VID.mp4", 5, null, "esp", "alb", true, "lote")
        assertEquals("foto", File(photo.file).readText())
        assertEquals(4, photo.size)

        val again = QueueStore(root) // «se reinicia el móvil»
        assertEquals(2, again.pending().size)
        assertEquals(listOf(photo.id), again.pending(includeVideos = false).map { it.id })
        assertEquals("alb", again.all().first { it.id == video.id }.albumId)

        again.finish(photo, QueueItem.DONE)
        assertFalse(File(photo.file).exists()) // la copia temporal se borra al terminar
        again.finish(video, QueueItem.DUPLICATE)
        assertEquals(QueueStore.Summary(1, 1, 0, 0), again.summary("lote"))
        again.forgetFinished()
        assertTrue(again.all().isEmpty())
    }

    @Test
    fun huella_sha256() {
        val file = tmp.newFile().apply { writeText("abc") }
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", QueueStore.sha256(file))
    }
}

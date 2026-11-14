package app.carrete.android

import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.Base64

/** Servidor tus simulado: acepta subidas, guarda los bytes y puede cortar la conexión a propósito. */
class FakeCarrete : Dispatcher() {
    val received = ByteArrayOutputStream()
    var present = setOf<String>()
    var failNextPatch = false
    var metadata = mapOf<String, String>()
    var length = 0L
    var patches = 0

    override fun dispatch(request: RecordedRequest): MockResponse {
        assertEquals("Bearer tok", request.getHeader("Authorization"))
        val path = request.path!!
        return when {
            path.endsWith("/assets/check") -> {
                val asked = Regex("[0-9a-f]{64}").findAll(request.body.readUtf8()).map { it.value }.toList()
                val hits = asked.filter { it in present }.joinToString(",") { "\"$it\"" }
                MockResponse().setBody("{\"present\": [$hits]}")
            }
            path == "/api/v1/uploads" && request.method == "POST" -> {
                length = request.getHeader("Upload-Length")!!.toLong()
                metadata = request.getHeader("Upload-Metadata")!!.split(",").associate {
                    val (k, v) = it.split(" ")
                    k to String(Base64.getDecoder().decode(v))
                }
                MockResponse().setResponseCode(201).setHeader("Location", "/api/v1/uploads/u1")
            }
            request.method == "HEAD" -> MockResponse().setHeader("Upload-Offset", received.size().toString())
            request.method == "PATCH" -> {
                patches++
                assertEquals(received.size().toLong(), request.getHeader("Upload-Offset")!!.toLong())
                if (failNextPatch) {
                    failNextPatch = false
                    // Llega medio trozo y se corta: el servidor guarda lo recibido (como tus).
                    val bytes = request.body.readByteArray()
                    received.write(bytes, 0, bytes.size / 2)
                    return MockResponse().setResponseCode(500)
                }
                received.write(request.body.readByteArray())
                val response = MockResponse().setResponseCode(204).setHeader("Upload-Offset", received.size().toString())
                if (received.size().toLong() == length) response.setHeader("Carrete-Asset-Id", "a1").setHeader("Carrete-Duplicate", "0") else response
            }
            else -> MockResponse().setResponseCode(404)
        }
    }
}

class UploaderTest {
    @get:Rule val tmp = TemporaryFolder()
    private val server = MockWebServer()
    private val fake = FakeCarrete()

    @Before fun start() {
        server.dispatcher = fake
        server.start()
    }

    @After fun stop() = server.shutdown()

    private fun base() = server.url("/").toString().trimEnd('/')

    private fun setup(content: ByteArray): Pair<QueueStore, Uploader> {
        val store = QueueStore(tmp.newFolder())
        val uploader = Uploader(CarreteApi(base(), "tok"), TusClient(base(), "tok"), store)
        store.add(content.inputStream(), "IMG-20230415-WA0001.jpg", content.size.toLong(), 1_681_000_000_000, "esp", "alb", false, "lote")
        return store to uploader
    }

    @Test
    fun sube_por_trozos_con_metadatos() {
        val content = ByteArray(40_000) { (it % 251).toByte() }
        val (store, uploader) = setup(content)
        val item = store.pending().single()
        val tus = TusClient(base(), "tok")
        val done = Uploader(CarreteApi(base(), "tok"), tus, store).upload(item)
        assertEquals(QueueItem.DONE, done.status)
        assertTrue(fake.received.toByteArray().contentEquals(content))
        assertEquals("IMG-20230415-WA0001.jpg", fake.metadata["filename"])
        assertEquals("esp", fake.metadata["space_id"])
        assertEquals("alb", fake.metadata["album_id"])
        assertEquals("1681000000000", fake.metadata["mtime"])
        assertEquals(QueueStore.sha256(content.inputStream().let { s -> tmp.newFile().apply { writeBytes(s.readBytes()) } }), fake.metadata["sha256"])
        assertTrue(store.pending().isEmpty())
        assertTrue(uploader.toString().isNotEmpty())
    }

    @Test
    fun no_sube_lo_que_ya_estaba() {
        val content = "repetida".toByteArray()
        val (store, uploader) = setup(content)
        val sha = java.security.MessageDigest.getInstance("SHA-256").digest(content).joinToString("") { "%02x".format(it) }
        fake.present = setOf(sha)
        assertEquals(QueueItem.DUPLICATE, uploader.upload(store.pending().single()).status)
        assertEquals(0, fake.patches)
    }

    @Test
    fun reanuda_tras_un_corte() {
        val content = ByteArray(3 * 1024 * 1024) { (it % 7).toByte() }
        val store = QueueStore(tmp.newFolder())
        store.add(content.inputStream(), "VID.mp4", content.size.toLong(), null, "esp", null, true, "lote")
        val tus = TusClient(base(), "tok")
        val uploader = Uploader(CarreteApi(base(), "tok"), tus, store)
        fake.failNextPatch = true
        try {
            uploader.upload(store.pending().single())
        } catch (e: ApiException) {
            assertEquals(500, e.status) // se reintentará más tarde
        } catch (e: IOException) {
            // también válido según cómo corte la red
        }
        val pending = store.pending().single()
        assertTrue(pending.uploadUrl != null) // se recuerda la subida para reanudarla
        assertEquals(QueueItem.DONE, uploader.upload(pending).status) // HEAD → sigue desde donde se quedó
        assertTrue(fake.received.toByteArray().contentEquals(content))
    }
}

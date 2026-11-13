package app.carrete.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerUrlTest {
    @Test
    fun normaliza_direcciones() {
        assertEquals("https://equipo.tailnet.ts.net:10000", ServerUrl.normalize(" equipo.tailnet.ts.net:10000/ "))
        assertEquals("https://equipo.ts.net", ServerUrl.normalize("https://Equipo.ts.net:443/fotos"))
        assertEquals("https://a.b:10000", ServerUrl.normalize("carrete:https://a.b:10000"))
        assertNull(ServerUrl.normalize("http://a.b"))
        assertNull(ServerUrl.normalize(""))
        assertNull(ServerUrl.normalize("https://"))
    }

    @Test
    fun mismo_origen_con_puerto() {
        val server = "https://equipo.ts.net:10000"
        assertTrue(ServerUrl.sameOrigin(server, "https://equipo.ts.net:10000/revisar?x=1"))
        assertFalse(ServerUrl.sameOrigin(server, "https://equipo.ts.net:8443/"))
        assertFalse(ServerUrl.sameOrigin(server, "https://otro.ts.net:10000/"))
        assertFalse(ServerUrl.sameOrigin(server, "http://equipo.ts.net:10000/"))
        assertTrue(ServerUrl.sameOrigin("https://a.b", "https://a.b:443/x"))
    }
}

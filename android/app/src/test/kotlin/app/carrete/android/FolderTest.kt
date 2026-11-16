package app.carrete.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FolderTest {
    @Test
    fun reconoce_fotos_y_videos_por_tipo_o_extension() {
        assertTrue(Folder.isMedia("image/jpeg", "IMG_0001.jpg"))
        assertTrue(Folder.isMedia("video/mp4", "VID.mp4"))
        assertTrue(Folder.isMedia("application/octet-stream", "IMG_0002.HEIC")) // algunos proveedores no saben el tipo
        assertFalse(Folder.isMedia("application/pdf", "factura.pdf"))
        assertFalse(Folder.isMedia("text/plain", ".nomedia"))
    }

    @Test
    fun distingue_videos() {
        assertEquals(true, Intake.isVideo("video/quicktime", "a.mov"))
        assertEquals(true, Intake.isVideo("", "b.MP4"))
        assertEquals(false, Intake.isVideo("image/jpeg", "c.jpg"))
    }
}

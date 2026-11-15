package app.carrete.android

import android.annotation.SuppressLint
import android.os.Build
import android.os.ext.SdkExtensions
import android.provider.MediaStore

/**
 * Cuántas fotos se pueden pedir de una vez al selector del sistema. El selector moderno (Android 13, o
 * Android 11-12 actualizado) tiene un máximo propio, normalmente 100, y si se le pide más la app se cierra
 * (IllegalArgumentException en PickMultipleVisualMedia). Los selectores antiguos no tienen máximo.
 */
object PickLimit {
    /** Lo que se pide cuando el selector no impone máximo. */
    const val FALLBACK = 200

    fun maxItems(systemPicker: Boolean, systemLimit: () -> Int): Int =
        if (systemPicker) systemLimit().coerceIn(2, FALLBACK) else FALLBACK

    /** Misma condición que usa androidx.activity para elegir el selector del sistema. */
    @SuppressLint("NewApi") // getExtensionVersion existe desde Android 11 (R), comprobado antes
    fun systemPickerAvailable(): Boolean =
        Build.VERSION.SDK_INT >= 33 ||
            (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && SdkExtensions.getExtensionVersion(Build.VERSION_CODES.R) >= 2)

    @SuppressLint("NewApi") // solo se llama si systemPickerAvailable()
    fun forThisDevice(): Int = maxItems(systemPickerAvailable()) { MediaStore.getPickImagesMaxLimit() }
}

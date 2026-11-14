package app.carrete.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Ajustes de la app. El *token* de dispositivo se guarda cifrado con una clave del Android Keystore
 * (no extraíble del móvil). La contraseña no se guarda nunca.
 */
class AppSettings(context: Context) {
    private val prefs = context.getSharedPreferences("carrete", Context.MODE_PRIVATE)

    var server: String?
        get() = prefs.getString("server", null)
        set(value) = prefs.edit().putString("server", value).apply()

    var lastSpaceId: String?
        get() = prefs.getString("last_space", null)
        set(value) = prefs.edit().putString("last_space", value).apply()

    var wifiOnlyVideos: Boolean
        get() = prefs.getBoolean("wifi_only_videos", true)
        set(value) = prefs.edit().putBoolean("wifi_only_videos", value).apply()

    var token: String?
        get() = prefs.getString("token", null)?.let { decrypt(it) }
        set(value) {
            if (value == null) prefs.edit().remove("token").apply()
            else prefs.edit().putString("token", encrypt(value)).apply()
        }

    val configured: Boolean get() = server != null && token != null

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    private fun encrypt(plain: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val sealed = cipher.doFinal(plain.toByteArray())
        return Base64.getEncoder().encodeToString(cipher.iv + sealed)
    }

    private fun decrypt(stored: String): String? = try {
        val raw = Base64.getDecoder().decode(stored)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, raw.copyOfRange(0, 12)))
        String(cipher.doFinal(raw.copyOfRange(12, raw.size)))
    } catch (e: Exception) {
        null // clave borrada o datos dañados: hay que volver a entrar
    }

    private companion object {
        const val ALIAS = "carrete-token"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}

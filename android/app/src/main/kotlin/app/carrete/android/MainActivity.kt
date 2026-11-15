package app.carrete.android

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.URLUtil
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Interfaz principal: la misma web de Carrete en una WebView, más lo que la web no hace
 * bien: selector de fotos del sistema con subida fiable en segundo plano, descargas a
 * Pictures/Carrete y el botón «atrás» del sistema.
 */
class MainActivity : ComponentActivity() {
    private lateinit var settings: AppSettings
    private lateinit var web: WebView
    private var pickSpace: String? = null

    // Tope del selector según el móvil: pedir más de lo que admite cierra la app (PickLimit).
    private val picker = registerForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(PickLimit.forThisDevice())) { uris ->
        val space = pickSpace ?: return@registerForActivityResult
        if (uris.isNotEmpty()) {
            Toast.makeText(this, getString(R.string.preparing, uris.size), Toast.LENGTH_SHORT).show()
            lifecycleScope.launch {
                withContext(Dispatchers.IO) { Intake(this@MainActivity).enqueue(uris, space, null) }
                Toast.makeText(this@MainActivity, R.string.queued, Toast.LENGTH_SHORT).show()
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = AppSettings(this)
        val server = settings.server
        val token = settings.token
        if (server == null || token == null) {
            startActivity(Intent(this, SetupActivity::class.java))
            finish()
            return
        }
        web = WebView(this)
        setContentView(web)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            mediaPlaybackRequiresUserGesture = true
        }
        CookieManager.getInstance().setAcceptCookie(true)
        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            // Solo se navega dentro del servidor; cualquier otro enlace se abre en el navegador.
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                if (ServerUrl.sameOrigin(server, url)) return false
                startActivity(Intent(Intent.ACTION_VIEW, request.url))
                return true
            }
        }
        // Puente mínimo: solo «elegir fotos y subirlas en segundo plano». Comprueba el origen en cada llamada.
        web.addJavascriptInterface(Bridge(server), "CarreteAndroid")
        web.setDownloadListener { url, _, disposition, mime, _ -> download(server, url, disposition, mime) }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })
        signIn(server, token)
        checkForUpdate(server, token)
        UploadWorker.enqueue(this) // por si quedó algo pendiente
    }

    /** La WebView obtiene su sesión canjeando un código de un solo uso; la contraseña no se guarda. */
    private fun signIn(server: String, token: String) {
        lifecycleScope.launch {
            val code = withContext(Dispatchers.IO) { runCatching { CarreteApi(server, token).webCode() } }
            code.onSuccess { web.loadUrl("$server/api/v1/auth/device/web?code=${Uri.encode(it)}") }
            code.onFailure {
                if (it is ApiException && it.status == 401) {
                    settings.token = null // el dispositivo se revocó desde la web
                    startActivity(Intent(this@MainActivity, SetupActivity::class.java))
                    finish()
                } else {
                    web.loadUrl(server) // sin red: la web mostrará su propio estado
                }
            }
        }
    }

    private fun checkForUpdate(server: String, token: String) {
        lifecycleScope.launch {
            val latest = withContext(Dispatchers.IO) { runCatching { CarreteApi(server, token).latestVersionCode() }.getOrNull() }
            if (latest != null && latest > BuildConfig.VERSION_CODE) {
                Toast.makeText(this@MainActivity, R.string.update_available, Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun download(server: String, url: String, disposition: String?, mime: String?) {
        if (!ServerUrl.sameOrigin(server, url)) return
        val name = URLUtil.guessFileName(url, disposition, mime)
        val request = DownloadManager.Request(Uri.parse(url))
            .addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url))
            .setTitle(name)
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_PICTURES, "Carrete/$name")
        getSystemService(DownloadManager::class.java).enqueue(request)
        Toast.makeText(this, getString(R.string.downloading, name), Toast.LENGTH_SHORT).show()
    }

    private inner class Bridge(private val server: String) {
        @JavascriptInterface
        fun pickPhotos(spaceId: String) {
            runOnUiThread {
                val current = web.url ?: return@runOnUiThread
                if (!ServerUrl.sameOrigin(server, current) || !spaceId.matches(Regex("^[0-9a-f-]{36}$"))) return@runOnUiThread
                pickSpace = spaceId
                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageAndVideo))
            }
        }

        @JavascriptInterface
        fun version(): Int = BuildConfig.VERSION_CODE

        /** Cuántas fotos admite el selector de una vez, para avisarlo en la web. */
        @JavascriptInterface
        fun pickLimit(): Int = PickLimit.forThisDevice()
    }
}

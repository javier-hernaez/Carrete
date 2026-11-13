package app.carrete.android

import android.Manifest
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Primer arranque: dirección del servidor (por defecto la de la compilación, o la de un QR
 * «carrete:https://…»), usuario, contraseña y segundo factor → se registra el dispositivo.
 */
class SetupActivity : ComponentActivity() {
    private lateinit var settings: AppSettings
    private lateinit var server: EditText
    private lateinit var user: EditText
    private lateinit var password: EditText
    private lateinit var code: EditText
    private lateinit var message: TextView
    private lateinit var button: Button
    private var pendingToken: String? = null
    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { openMain() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = AppSettings(this)
        val pad = (24 * resources.displayMetrics.density).toInt()
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad * 2, pad, pad)
        }
        layout.addView(TextView(this).apply { setText(R.string.setup_title); textSize = 26f })
        layout.addView(TextView(this).apply { setText(R.string.setup_intro) })
        server = field(R.string.setup_server, InputType.TYPE_TEXT_VARIATION_URI)
        user = field(R.string.setup_user, InputType.TYPE_CLASS_TEXT)
        password = field(R.string.setup_password, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        code = field(R.string.setup_code, InputType.TYPE_CLASS_NUMBER).apply { visibility = View.GONE }
        message = TextView(this)
        button = Button(this).apply { setText(R.string.setup_enter); setOnClickListener { submit() } }
        listOf(server, user, password, code, message, button).forEach(layout::addView)
        setContentView(layout)

        val fromQr = intent?.data?.toString()?.let(ServerUrl::normalize)
        server.setText(fromQr ?: settings.server ?: BuildConfig.DEFAULT_SERVER)
    }

    private fun field(hint: Int, type: Int) = EditText(this).apply {
        setHint(hint)
        inputType = type
        isSingleLine = true
    }

    private fun submit() {
        val url = ServerUrl.normalize(server.text.toString())
        if (url == null) {
            message.setText(R.string.setup_bad_server)
            return
        }
        button.isEnabled = false
        message.setText(R.string.setup_connecting)
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                runCatching {
                    val token = pendingToken
                    if (token == null) {
                        val device = "${Build.MANUFACTURER} ${Build.MODEL}".trim()
                        CarreteApi(url, null).deviceLogin(user.text.toString(), password.text.toString(), device)
                    } else {
                        CarreteApi(url, token).verifyCode(code.text.toString()) to token
                    }
                }
            }
            button.isEnabled = true
            result.onFailure { message.text = it.message ?: getString(R.string.error_network) }
            result.onSuccess { (stage, token) ->
                when (stage) {
                    "full" -> done(url, token)
                    "totp" -> {
                        pendingToken = token
                        code.visibility = View.VISIBLE
                        code.requestFocus()
                        message.setText(R.string.setup_need_code)
                    }
                    else -> message.setText(R.string.setup_enroll_first)
                }
            }
        }
    }

    private fun done(url: String, token: String) {
        settings.server = url
        settings.token = token
        password.text.clear()
        val wanted = buildList {
            // Conservar la ubicación de las fotos. En Android 9 no hace falta.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) add(Manifest.permission.ACCESS_MEDIA_LOCATION)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) add(Manifest.permission.POST_NOTIFICATIONS)
        }.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (wanted.isNotEmpty()) permissions.launch(wanted.toTypedArray()) else openMain()
    }

    private fun openMain() {
        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }
}

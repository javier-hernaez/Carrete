package app.carrete.android

import androidx.activity.ComponentActivity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Destino de «Compartir» desde WhatsApp, la galería o cualquier app, para una o varias fotos y
 * vídeos: se elige espacio (por defecto, el último) y, si se quiere, álbum → «Subir».
 */
class ShareActivity : ComponentActivity() {
    private lateinit var settings: AppSettings
    private var uris: List<Uri> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = AppSettings(this)
        uris = received(intent)
        val server = settings.server
        val token = settings.token
        if (server == null || token == null) {
            Toast.makeText(this, R.string.share_setup_first, Toast.LENGTH_LONG).show()
            startActivity(Intent(this, SetupActivity::class.java))
            finish()
            return
        }
        if (uris.isEmpty()) {
            finish()
            return
        }
        val pad = (20 * resources.displayMetrics.density).toInt()
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }
        val title = TextView(this).apply { text = resources.getQuantityString(R.plurals.share_title, uris.size, uris.size); textSize = 20f }
        val spaceLabel = TextView(this).apply { setText(R.string.share_space) }
        val spaces = Spinner(this)
        val albumLabel = TextView(this).apply { setText(R.string.share_album) }
        val albums = Spinner(this)
        val upload = Button(this).apply { setText(R.string.share_upload); isEnabled = false }
        listOf(title, spaceLabel, spaces, albumLabel, albums, upload).forEach(layout::addView)
        setContentView(layout)

        val api = CarreteApi(server, token)
        var spaceList: List<Space> = emptyList()
        var albumList: List<AlbumRef?> = listOf(null)
        lifecycleScope.launch {
            val loaded = withContext(Dispatchers.IO) { runCatching { api.spaces() } }
            loaded.onFailure {
                Toast.makeText(this@ShareActivity, it.message ?: getString(R.string.error_network), Toast.LENGTH_LONG).show()
                finish()
            }
            loaded.onSuccess { (list, current) ->
                spaceList = list
                spaces.adapter = ArrayAdapter(this@ShareActivity, android.R.layout.simple_spinner_dropdown_item, list.map { it.name })
                val preferred = settings.lastSpaceId ?: current
                spaces.setSelection(list.indexOfFirst { it.id == preferred }.coerceAtLeast(0))
                upload.isEnabled = list.isNotEmpty()
                if (list.isEmpty()) Toast.makeText(this@ShareActivity, R.string.share_no_space, Toast.LENGTH_LONG).show()
            }
        }
        spaces.onItemSelectedListener = SimpleSelection { position ->
            val space = spaceList.getOrNull(position) ?: return@SimpleSelection
            lifecycleScope.launch {
                val list = withContext(Dispatchers.IO) { runCatching { api.albums(space.id) }.getOrDefault(emptyList()) }
                albumList = listOf(null) + list
                albums.adapter = ArrayAdapter(this@ShareActivity, android.R.layout.simple_spinner_dropdown_item, albumList.map { it?.name ?: getString(R.string.share_no_album) })
            }
        }
        upload.setOnClickListener {
            val space = spaceList.getOrNull(spaces.selectedItemPosition) ?: return@setOnClickListener
            val album = albumList.getOrNull(albums.selectedItemPosition)
            settings.lastSpaceId = space.id
            upload.isEnabled = false
            Toast.makeText(this, getString(R.string.preparing, uris.size), Toast.LENGTH_SHORT).show()
            lifecycleScope.launch {
                // La copia se hace ya, antes de cerrar: el permiso sobre las URIs recibidas es temporal.
                val result = withContext(Dispatchers.IO) { Intake(this@ShareActivity).enqueue(uris, space.id, album?.id) }
                Toast.makeText(this@ShareActivity, intakeMessage(this@ShareActivity, result), Toast.LENGTH_LONG).show()
                finish()
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun received(intent: Intent?): List<Uri> {
        intent ?: return emptyList()
        return when (intent.action) {
            Intent.ACTION_SEND -> listOfNotNull(
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else intent.getParcelableExtra(Intent.EXTRA_STREAM),
            )
            Intent.ACTION_SEND_MULTIPLE ->
                (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
                else intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM)).orEmpty()
            else -> emptyList()
        }
    }
}

private class SimpleSelection(private val onSelect: (Int) -> Unit) : android.widget.AdapterView.OnItemSelectedListener {
    override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) = onSelect(position)
    override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
}

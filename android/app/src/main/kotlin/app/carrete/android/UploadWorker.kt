package app.carrete.android

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.ForegroundInfo
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Cola de subida en segundo plano: WorkManager + servicio en primer plano. Sigue con la pantalla
 * apagada, sobrevive a reinicios, reintenta con espera creciente y reanuda por trozos. Los vídeos
 * esperan a una red sin límite de datos si así está configurado (por defecto, sí).
 */
class UploadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    private val settings = AppSettings(context)
    private val notifications = context.getSystemService(NotificationManager::class.java)

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val server = settings.server ?: return@withContext Result.failure()
        val token = settings.token ?: return@withContext Result.failure()
        val store = queueStore(applicationContext)
        val metered = applicationContext.getSystemService(ConnectivityManager::class.java).isActiveNetworkMetered
        val videosNow = !(settings.wifiOnlyVideos && metered)
        val items = store.pending(includeVideos = videosNow)
        if (items.isEmpty()) {
            if (!videosNow && store.pending().isNotEmpty()) enqueue(applicationContext, wifiOnly = true)
            return@withContext Result.success()
        }
        setForeground(foreground(0, items.size, items.first().name))
        val uploader = Uploader(CarreteApi(server, token), TusClient(server, token), store) { item ->
            if (Source.isContentUri(item.file)) UriSource(applicationContext, Uri.parse(item.file)) else FileSource(File(item.file))
        }
        var retry = false
        // Android descarta las notificaciones de una app que pasa de ~5 por segundo, y entre las descartadas
        // podía caer el resumen final. Con muchas fotos pequeñas, el progreso se actualiza una vez por segundo.
        var lastProgress = 0L
        items.forEachIndexed { index, item ->
            try {
                uploader.upload(item) { sent ->
                    val now = SystemClock.elapsedRealtime()
                    if (now - lastProgress >= PROGRESS_EVERY_MS) {
                        lastProgress = now
                        val fraction = if (item.size > 0) sent.toDouble() / item.size else 1.0
                        notifications.notify(PROGRESS_ID, progress(index + fraction, items.size, item.name))
                    }
                }
            } catch (e: ApiException) {
                if (e.status == 401) return@withContext Result.failure() // token revocado: hay que volver a entrar
                retry = true
            } catch (e: java.io.IOException) {
                retry = true // red caída: se reintenta con la red de vuelta
            }
        }
        if (!videosNow && store.pending().any { it.isVideo }) enqueue(applicationContext, wifiOnly = true)
        if (retry) return@withContext Result.retry()
        finishBatches(store, CarreteApi(server, token))
        Result.success()
    }

    /** Suelta el permiso persistente de las carpetas que ya no tienen nada pendiente. */
    private fun releaseFolders(group: List<QueueItem>, store: QueueStore) {
        val stillUsed = store.pending().mapNotNull { it.tree }.toSet()
        for (tree in group.mapNotNull { it.tree }.toSet() - stillUsed) {
            try {
                applicationContext.contentResolver.releasePersistableUriPermission(Uri.parse(tree), Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } catch (e: SecurityException) {
                // Ya no lo teníamos.
            }
        }
    }

    /** Resumen final: «58 subidas, 12 ya estaban, 0 errores». */
    private fun finishBatches(store: QueueStore, api: CarreteApi) {
        val finished = store.all().groupBy { it.batch }.filterValues { g -> g.none { it.status == QueueItem.PENDING } }
        for ((batch, group) in finished) {
            releaseFolders(group, store)
            val summary = store.summary(batch)
            try {
                api.summary(group.first().spaceId, summary.uploaded, summary.duplicates, summary.failed)
            } catch (e: Exception) {
                // El resumen de auditoría no es imprescindible.
            }
            val text = applicationContext.getString(R.string.upload_summary, summary.uploaded, summary.duplicates, summary.failed)
            Log.i("CarreteUpload", "Lote terminado: $text")
            notifications.cancel(PROGRESS_ID)
            notifications.notify(
                SUMMARY_ID,
                NotificationCompat.Builder(applicationContext, CHANNEL)
                    .setSmallIcon(R.drawable.ic_notification)
                    .setContentTitle(applicationContext.getString(R.string.upload_done_title))
                    .setContentText(text)
                    .setAutoCancel(true)
                    .build(),
            )
        }
        store.forgetFinished()
    }

    private fun progress(done: Double, total: Int, name: String) =
        NotificationCompat.Builder(applicationContext, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(applicationContext.getString(R.string.uploading_title, done.toInt().coerceAtMost(total - 1) + 1, total))
            .setContentText(name)
            .setProgress(1000, (done / total * 1000).toInt(), false)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()

    private fun foreground(done: Int, total: Int, name: String): ForegroundInfo {
        ensureChannel(applicationContext)
        val notification = progress(done.toDouble(), total, name)
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(PROGRESS_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            ForegroundInfo(PROGRESS_ID, notification)
        }
    }

    companion object {
        const val CHANNEL = "subidas"
        private const val PROGRESS_ID = 1
        private const val SUMMARY_ID = 2
        private const val PROGRESS_EVERY_MS = 1000L

        fun queueStore(context: Context) = QueueStore(File(context.filesDir, "cola"))

        fun ensureChannel(context: Context) {
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, context.getString(R.string.channel_uploads), NotificationManager.IMPORTANCE_LOW),
            )
        }

        fun enqueue(context: Context, wifiOnly: Boolean = false) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(if (wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED)
                .build()
            val request = OneTimeWorkRequestBuilder<UploadWorker>().setConstraints(constraints).build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                if (wifiOnly) "subidas-wifi" else "subidas",
                ExistingWorkPolicy.APPEND_OR_REPLACE,
                request,
            )
        }
    }
}

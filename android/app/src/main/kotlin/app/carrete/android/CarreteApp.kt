package app.carrete.android

import android.app.Application

class CarreteApp : Application() {
    override fun onCreate() {
        super.onCreate()
        UploadWorker.ensureChannel(this)
    }
}

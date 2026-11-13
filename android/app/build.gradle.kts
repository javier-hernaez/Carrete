// App Android de Carrete.
// La dirección por defecto, la versión y la firma llegan por variables de entorno: nada de eso se
// escribe en el repositorio.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val defaultServer = System.getenv("CARRETE_PUBLIC_URL") ?: ""
val versionCodeEnv = System.getenv("CARRETE_APK_VERSION_CODE")?.toIntOrNull() ?: 1
val versionNameEnv = System.getenv("CARRETE_APK_VERSION_NAME") ?: "0.1.0"
val keystorePath = System.getenv("CARRETE_KEYSTORE")

android {
    namespace = "app.carrete.android"
    compileSdk = 34

    defaultConfig {
        applicationId = "app.carrete.android"
        minSdk = 28 // Android 9
        targetSdk = 34
        versionCode = versionCodeEnv
        versionName = versionNameEnv
        buildConfigField("String", "DEFAULT_SERVER", "\"$defaultServer\"")
    }

    signingConfigs {
        if (keystorePath != null) {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = System.getenv("CARRETE_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("CARRETE_KEY_ALIAS") ?: "carrete"
                keyPassword = System.getenv("CARRETE_KEY_PASSWORD") ?: System.getenv("CARRETE_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (keystorePath != null) signingConfig = signingConfigs.getByName("release")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
    lint {
        abortOnError = true
        warningsAsErrors = false
        // ObsoleteSdkInt: el icono adaptativo necesita la carpeta -v26 aunque el mínimo sea 28.
        disable += setOf("GradleDependency", "OldTargetApi", "NewerVersionAvailable", "AndroidGradlePluginVersion", "ObsoleteSdkInt")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}

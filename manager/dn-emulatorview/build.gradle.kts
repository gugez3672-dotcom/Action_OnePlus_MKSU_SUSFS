plugins { id("com.android.library") }

android {
    namespace = "jackpal.androidterm.emulatorview"
    compileSdk = 37
    defaultConfig { minSdk = 26 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    lint { abortOnError = false }
}

dependencies {
    implementation("androidx.annotation:annotation:1.9.1")
}

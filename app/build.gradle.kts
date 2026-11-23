import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    kotlin("android")
}

android {
    namespace = "com.k3bora.ultrastalker.tv"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.k3bora.ultrastalker.tv"
        minSdk = 21
        targetSdk = 35
        versionCode = 2
        versionName = "1.1.0"
        // TV boxes and TVs are ARM; both kinds in one APK
        ndk { abiFilters += listOf("armeabi-v7a", "arm64-v8a") }
    }
    signingConfigs {
        // one fixed key, so a new APK installs over the old one
        create("tv") {
            storeFile = rootProject.file("signing/ultrastalker-tv.jks")
            storePassword = "ultrastalker-tv"
            keyAlias = "ultrastalker-tv"
            keyPassword = "ultrastalker-tv"
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("tv")
        }
        debug {
            signingConfig = signingConfigs.getByName("tv")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    packaging {
        jniLibs.useLegacyPackaging = true
        resources.excludes += listOf("META-INF/*.kotlin_module", "META-INF/versions/**")
    }
    // the interface is plain files: never compress them (fast start, ranged reads)
    androidResources { noCompress += listOf("html", "js", "css", "wasm", "webp", "png", "woff2") }
}
kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}
dependencies {
    implementation(project(":relay"))
    implementation("org.videolan.android:libvlc-all:3.7.7")
}

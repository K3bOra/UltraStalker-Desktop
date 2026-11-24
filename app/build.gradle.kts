import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    kotlin("android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("io.github.takahirom.roborazzi")
}

android {
    namespace = "com.k3bora.ultrastalker.tv"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.k3bora.ultrastalker.tv"
        minSdk = 21
        targetSdk = 35
        versionCode = 3
        versionName = "2.0.0"
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
    buildFeatures { compose = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    packaging {
        jniLibs.useLegacyPackaging = true
        resources.excludes += listOf("META-INF/*.kotlin_module", "META-INF/versions/**", "META-INF/AL2.0", "META-INF/LGPL2.1")
    }
    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all { it.systemProperty("robolectric.pixelCopyRenderMode", "hardware") }
    }
}
kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}
dependencies {
    implementation(project(":relay"))
    implementation("org.videolan.android:libvlc-all:3.7.7")
    implementation(platform("androidx.compose:compose-bom:2025.08.01"))
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.tv:tv-material:1.0.1")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.2")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.18.1")
    testImplementation("io.github.takahirom.roborazzi:roborazzi:1.79.0")
    testImplementation("io.github.takahirom.roborazzi:roborazzi-compose:1.79.0")
    testImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}

package com.k3bora.ultrastalker.tv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.ui.Modifier
import coil.Coil
import coil.ImageLoader
import coil.disk.DiskCache
import coil.memory.MemoryCache

class MainActivity : ComponentActivity() {
    companion object {
        @Volatile private var shared: AppState? = null
        fun state(a: ComponentActivity): AppState = shared ?: synchronized(this) {
            shared ?: AppState(a.applicationContext, BuildInfo.version(a)).also { shared = it }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val state = state(this)
        Coil.setImageLoader(
            ImageLoader.Builder(applicationContext)
                .okHttpClient(state.http)
                .respectCacheHeaders(false)
                .crossfade(180)
                .memoryCache { MemoryCache.Builder(applicationContext).maxSizePercent(0.2).build() }
                .diskCache { DiskCache.Builder().directory(cacheDir.resolve("pictures")).maxSizeBytes(120L * 1024 * 1024).build() }
                .build(),
        )
        setContent { UltraTheme { Root(state) } }
    }
}

object BuildInfo {
    fun version(a: ComponentActivity): String = try {
        a.packageManager.getPackageInfo(a.packageName, 0).versionName ?: ""
    } catch (_: Exception) {
        ""
    }
}

@Composable
fun Root(state: AppState) {
    val screen = state.stack.last()
    BackHandler(enabled = state.stack.size > 1) { state.back() }
    Box(Modifier.fillMaxSize().background(Gold.bg)) {
        key(screen) {
            when (screen) {
                is Screen.Home -> HomeScreen(state)
                is Screen.Browse -> BrowseScreen(state, screen)
                is Screen.Details -> DetailsScreen(state, screen)
                is Screen.Player -> PlayerScreen(state, screen)
                is Screen.AddSource -> AddSourceScreen(state)
                is Screen.Restore -> RestoreScreen(state)
            }
        }
        ToastHost(state)
    }
}

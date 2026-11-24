package com.k3bora.ultrastalker.tv

import android.content.Context
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import com.k3bora.ultrastalker.core.Item
import com.k3bora.ultrastalker.core.Media
import com.k3bora.ultrastalker.core.Provider
import com.k3bora.ultrastalker.core.Source
import com.k3bora.ultrastalker.core.SourceStore
import com.k3bora.ultrastalker.core.providerFor
import com.k3bora.ultrastalker.relay.FileSource
import com.k3bora.ultrastalker.relay.LocalServer
import com.k3bora.ultrastalker.relay.Relay
import okhttp3.OkHttpClient
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/* One per app: the saved sources, a provider per source, the local relay for portal streams. */
class AppState(context: Context, val version: String) {
    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .followRedirects(true)
        .retryOnConnectionFailure(true)
        .build()
    private val store = SourceStore(File(context.filesDir, "sources.json"))
    private val prefs = context.getSharedPreferences("ultrastalker", Context.MODE_PRIVATE)
    private val appContext = context.applicationContext
    /* one libVLC for the whole app (starting it takes a moment) */
    val vlc: org.videolan.libvlc.LibVLC by lazy {
        org.videolan.libvlc.LibVLC(appContext, arrayListOf("--http-reconnect", "--network-caching=2000", "--no-stats", "--audio-time-stretch"))
    }
    val sources = mutableStateListOf<Source>().also { it.addAll(store.all()) }
    private val providers = ConcurrentHashMap<String, Provider>()
    private val relay = Relay(http)
    private val server: LocalServer by lazy { LocalServer(0, object : FileSource {
        override fun open(path: String): java.io.InputStream? = null
    }, version, relay).also { it.start(15000, false) } }

    val stack = mutableStateListOf<Screen>(Screen.Home)
    val toast = mutableStateOf<String?>(null)

    fun go(s: Screen) {
        stack += s
    }

    fun back(): Boolean {
        if (stack.size <= 1) return false
        val gone = stack.removeAt(stack.lastIndex)
        if (gone is Screen.Browse) gone.state.close()
        return true
    }

    fun provider(s: Source): Provider = providers.getOrPut(s.key) { providerFor(s, http) }

    fun save(list: List<Source>) {
        store.replaceAll(list)
        sources.clear()
        sources.addAll(store.all())
        providers.keys.retainAll(sources.map { it.key }.toSet())
    }

    fun add(s: Source) = save(sources.filter { it.key != s.key } + s)
    fun remove(s: Source) = save(sources.filter { it.key != s.key })

    /* what VLC opens: portal streams go through the relay (a fresh link every time);
       Xtream and M3U streams are opened directly */
    fun streamFor(p: Provider, item: Item): Stream {
        val t = p.ticket(item)
        val mode = t["mode"].toString().trim('"')
        val ext = t["ext"]?.toString()?.trim('"') ?: ""
        if (mode == "direct") {
            val ua = (t["h"] as? kotlinx.serialization.json.JsonObject)?.get("User-Agent")?.toString()?.trim('"') ?: ""
            return Stream(t["u"].toString().trim('"'), ua, ext)
        }
        return Stream(relay.ticketUrl(t, server.origin), "", ext)
    }

    fun lastSource(): String = prefs.getString("last_source", "") ?: ""
    fun rememberSource(s: Source) = prefs.edit().putString("last_source", s.key).apply()
    fun lastMedia(key: String): Media = runCatching { Media.valueOf(prefs.getString("media|$key", "LIVE")!!) }.getOrDefault(Media.LIVE)
    fun rememberMedia(key: String, m: Media) = prefs.edit().putString("media|$key", m.name).apply()
    fun position(id: String): Long = prefs.getLong("pos|$id", 0)
    fun rememberPosition(id: String, ms: Long) = prefs.edit().apply { if (ms > 0) putLong("pos|$id", ms) else remove("pos|$id") }.apply()
    fun lastEpisode(seriesId: String): String = prefs.getString("ep|$seriesId", "") ?: ""
    fun rememberEpisode(seriesId: String, episodeId: String) = prefs.edit().putString("ep|$seriesId", episodeId).apply()
}

data class Stream(val url: String, val userAgent: String, val ext: String)

sealed class Screen {
    data object Home : Screen()
    class Browse(val source: Source) : Screen() {
        val state = BrowseState()
    }
    class Details(val source: Source, val item: Item) : Screen() {
        var info: com.k3bora.ultrastalker.core.Details? = null
        var seasons: List<com.k3bora.ultrastalker.core.Season>? = null
        var season = -1
    }
    class Player(val source: Source, val items: List<Item>, val index: Int, val live: Boolean, val start: Long = 0, val series: Item? = null) : Screen()
    data object AddSource : Screen()
    data object Restore : Screen()
}

package com.k3bora.ultrastalker.core

import kotlinx.serialization.json.JsonObject
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.URI

/* An M3U playlist: read once, then sorted into live, movies and series. */
class M3u(override val source: Source, private val http: OkHttpClient?) : Provider {
    class Data(val live: List<Item>, val movies: List<Item>, val series: List<Item>, val episodes: Map<String, List<Item>>) {
        fun of(m: Media) = when (m) {
            Media.LIVE -> live
            Media.MOVIES -> movies
            Media.SERIES -> series
        }
    }

    companion object {
        private val EP = listOf(Regex("\\bS(\\d{1,2})\\s*E(\\d{1,3})\\b", RegexOption.IGNORE_CASE), Regex("\\b(\\d{1,2})x(\\d{1,3})\\b", RegexOption.IGNORE_CASE), Regex("\\bseason[\\s._-]*(\\d{1,2}).{0,12}episode[\\s._-]*(\\d{1,3})\\b", RegexOption.IGNORE_CASE))
        private val EP_CLEAN = listOf(Regex("[\\s._-]*\\bS\\d{1,2}\\s*E\\d{1,3}\\b.*$", RegexOption.IGNORE_CASE), Regex("[\\s._-]*\\b\\d{1,2}x\\d{1,3}\\b.*$", RegexOption.IGNORE_CASE), Regex("[\\s._-]*\\bseason[\\s._-]*\\d{1,2}.{0,12}episode[\\s._-]*\\d{1,3}\\b.*$", RegexOption.IGNORE_CASE))

        private fun words(list: List<String>): (String) -> Boolean {
            val latin = list.filter { w -> w.all { it.code < 128 } }
            val other = list.filter { w -> !w.all { it.code < 128 } }
            val rx = Regex("(?<!\\p{L})(?:" + latin.joinToString("|") { Regex.escape(it) } + ")(?!\\p{L})")
            return { g -> rx.containsMatchIn(g) || other.any { g.contains(it) } }
        }
        private val isSeries = words(listOf("series", "tv series", "shows", "show", "مسلسل", "مسلسلات", "دراما"))
        private val isMovie = words(listOf("movie", "movies", "vod", "film", "films", "cinema", "افلام", "أفلام", "فيلم"))
        private val isLive = words(listOf("live", "channel", "channels", "قنوات", "قناة", "sports", "news", "bein", "osn"))

        fun episodeNumbers(name: String): Pair<Int, Int>? {
            val text = name.replace(Regex("(?<!\\w)24\\s*[x/]\\s*(?:7|365)(?!\\d)", RegexOption.IGNORE_CASE), " ")
            for (rx in EP) rx.find(text)?.let { return it.groupValues[1].toInt() to it.groupValues[2].toInt() }
            return null
        }

        fun seriesBase(name: String): String {
            val t = name.trim()
            for (rx in EP_CLEAN) {
                val c = t.replace(rx, "").trim(' ', '.', '_', '-', '|')
                if (c.isNotEmpty() && c != t) return c
            }
            return t
        }

        fun kind(group: String, name: String, url: String): Media {
            val g = group.lowercase()
            if (episodeNumbers(name) != null || isSeries(g)) return Media.SERIES
            if (isMovie(g)) return Media.MOVIES
            if (isLive(g)) return Media.LIVE
            val path = try {
                URI(url).path?.lowercase() ?: ""
            } catch (_: Exception) {
                ""
            }
            return if (Regex("\\.(mp4|mkv|avi|mov|wmv|m4v)$").containsMatchIn(path)) Media.MOVIES else Media.LIVE
        }

        fun attrs(info: String): Map<String, String> {
            val a = LinkedHashMap<String, String>()
            for (m in Regex("([\\w-]+)=(?:\"([^\"]*)\"|'([^']*)')").findAll(info)) a[m.groupValues[1].lowercase()] = m.groupValues[2].ifEmpty { m.groupValues[3] }
            for (m in Regex("([\\w-]+)=([^\"'\\s,]+)").findAll(info)) a.putIfAbsent(m.groupValues[1].lowercase(), m.groupValues[2])
            return a
        }

        private fun slug(vararg p: String) = hash("SHA-1", p.joinToString("|")).take(20)

        fun parse(text: String): Data {
            val live = mutableListOf<Item>()
            val movies = mutableListOf<Item>()
            class Box(val id: String, val name: String, val group: String, val logo: String, val eps: MutableList<Triple<Int, Int, Item>> = mutableListOf())
            val groups = LinkedHashMap<String, Box>()
            var pName = ""
            var pGroup = ""
            var pLogo = ""
            var pending = false
            for (raw in text.split(Regex("\r?\n"))) {
                val line = raw.trim()
                if (line.isEmpty()) continue
                if (line.startsWith("#EXTINF", true)) {
                    val body = line.substring(line.indexOf(':') + 1)
                    var quote = ' '
                    var split = -1
                    for ((i, ch) in body.withIndex()) {
                        if (ch == '"' || ch == '\'') {
                            if (quote == ' ') quote = ch else if (ch == quote) quote = ' '
                        } else if (ch == ',' && quote == ' ') {
                            split = i
                            break
                        }
                    }
                    val a = attrs(if (split < 0) body else body.substring(0, split))
                    val title = if (split < 0) "" else body.substring(split + 1).trim()
                    pName = (a["tvg-name"] ?: "").ifBlank { title }.ifBlank { "Untitled" }.trim()
                    pGroup = (a["group-title"] ?: a["group"] ?: "").trim().ifEmpty { "Other" }
                    pLogo = (a["tvg-logo"] ?: a["logo"] ?: a["icon"] ?: "").trim()
                    pending = true
                    continue
                }
                if (line.startsWith("#")) {
                    if (pending && line.startsWith("#EXTGRP:", true) && pGroup == "Other") pGroup = line.substringAfter(':').trim().ifEmpty { "Other" }
                    else if (pending && line.startsWith("#EXTIMG:", true) && pLogo.isEmpty()) pLogo = line.substringAfter(':').trim()
                    continue
                }
                val name = if (pending) pName else "Stream"
                val group = if (pending) pGroup else "Other"
                val logo = if (pending) pLogo else ""
                pending = false
                val url = line
                val common = jsonOf("name" to name, "cmd" to url, "url" to url, "category" to group, "logo" to logo)
                if (Adult.text(name) || Adult.text(group)) continue
                when (kind(group, name, url)) {
                    Media.SERIES -> {
                        val nums = episodeNumbers(name)
                        if (nums == null) {
                            movies += Item("m3u-vod-" + slug(url, name), name, Media.MOVIES, logo, raw = common)
                        } else {
                            val base = seriesBase(name).ifEmpty { name }
                            val gk = group.lowercase() + "\u0000" + base.lowercase()
                            val box = groups.getOrPut(gk) { Box("m3u-series-" + slug(group, base), base, group, logo) }
                            box.eps += Triple(nums.first, nums.second, Item("m3u-ep-" + slug(url, name), name, Media.SERIES, logo.ifEmpty { box.logo }, nums.second.toString(), raw = common.plus("season" to nums.first.toString(), "episode" to nums.second.toString())))
                        }
                    }
                    Media.MOVIES -> movies += Item("m3u-vod-" + slug(url, name), name, Media.MOVIES, logo, raw = common)
                    Media.LIVE -> live += Item("m3u-live-" + slug(url, name), name, Media.LIVE, logo, (live.size + 1).toString(), raw = common)
                }
            }
            val episodes = HashMap<String, List<Item>>()
            val series = groups.values.map { b ->
                val sorted = b.eps.sortedWith(compareBy({ it.first }, { it.second }))
                episodes[b.id] = sorted.map { it.third }
                Item(b.id, b.name, Media.SERIES, b.logo, raw = jsonOf("category" to b.group, "seasons" to sorted.map { it.first }.distinct().size))
            }
            return Data(live, movies, series, episodes)
        }
    }

    @Volatile private var data: Data? = null

    @Synchronized
    fun load(): Data {
        data?.let { return it }
        val client = http ?: throw ProviderError("No network")
        val res = client.newCall(Request.Builder().url(source.portal).header("User-Agent", "VLC/3.0.20 LibVLC/3.0.20").build()).execute()
        val text = res.use {
            if (!it.isSuccessful) throw ProviderError("Playlist answered ${it.code}")
            it.body?.string() ?: ""
        }
        if (!Regex("#EXTM3U|#EXTINF", RegexOption.IGNORE_CASE).containsMatchIn(text.take(4096))) throw ProviderError("This address is not an M3U playlist", 400)
        return parse(text).also { data = it }
    }

    fun use(d: Data) {
        data = d
    }

    override fun categories(media: Media): List<Category> = load().of(media).map { it.raw.s("category") }.distinct().map { Category(it, it) }

    override fun page(media: Media, category: String, page: Int): Page {
        val all = load().of(media)
        val rows = if (category.isEmpty() || category == "*") all else all.filter { it.raw.s("category") == category }
        val start = (page - 1) * PAGE
        return Page(rows.drop(start).take(PAGE), rows.size, start + PAGE < rows.size)
    }

    override fun seasons(series: Item): List<Season> {
        val eps = load().episodes[series.id] ?: return emptyList()
        return eps.groupBy { it.raw.s("season") }.map { (n, list) -> Season(series.id + ":" + n, n, "Season $n", list) }
    }

    override fun ticket(item: Item, seriesNumber: String?): JsonObject {
        val u = item.raw.s("url", "cmd")
        if (u.isEmpty()) throw ProviderError("This item has no stream", 404)
        return jsonOf("mode" to "direct", "u" to u, "h" to jsonOf("User-Agent" to "VLC/3.0.20 LibVLC/3.0.20"), "ext" to u.substringBefore("?").substringAfterLast(".", "ts").take(5))
    }
}

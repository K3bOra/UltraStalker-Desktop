package com.k3bora.ultrastalker.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

const val PAGE = 60

/* An Xtream Codes line (player_api.php). */
class Xtream(override val source: Source, private val http: OkHttpClient) : Provider {
    companion object {
        val AGENTS = listOf("VLC/3.0.20 LibVLC/3.0.20", "IPTVSmartersPlayer", "okhttp/4.9.3", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

        fun asRows(js: JsonElement?): List<JsonObject> {
            if (js is JsonArray) return js.mapNotNull { it as? JsonObject }
            if (js is JsonObject && !js.containsKey("user_info")) {
                val vals = js.values.mapNotNull { it as? JsonObject }
                if (vals.isNotEmpty() && vals.all { it.containsKey("category_id") || it.containsKey("stream_id") || it.containsKey("series_id") }) return vals
            }
            return emptyList()
        }

        fun firstOf(v: JsonElement?): String = when (v) {
            is JsonArray -> (v.firstOrNull() as? JsonPrimitive)?.content ?: ""
            is JsonPrimitive -> v.content
            else -> ""
        }
    }

    private val c = Sources.xtreamCreds(source.portal) ?: throw ProviderError("Xtream details are incomplete", 400)
    @Volatile private var ua = AGENTS[0]
    private val cache = ConcurrentHashMap<String, List<Item>>()
    @Volatile var fallback: M3u? = null

    private fun api(action: String, extra: Map<String, String> = emptyMap(), agent: String = ua): JsonElement? {
        val q = (linkedMapOf("username" to c.second, "password" to c.third) + (if (action.isNotEmpty()) mapOf("action" to action) else emptyMap()) + extra)
            .entries.joinToString("&") { (k, v) -> k + "=" + URLEncoder.encode(v, "UTF-8") }
        val res = http.newCall(Request.Builder().url("${c.first}/player_api.php?$q").header("User-Agent", agent).build()).execute()
        val text = res.use { it.body?.string() ?: "" }
        return parseLoose(text) ?: throw ProviderError(if (res.isSuccessful) "Server sent an unreadable answer" else "Server answered ${res.code}", if (res.code == 401 || res.code == 403) res.code else 502)
    }

    fun streamUrl(kind: Media, sid: String, ext: String): String {
        val u = URLEncoder.encode(c.second, "UTF-8")
        val p = URLEncoder.encode(c.third, "UTF-8")
        return when (kind) {
            Media.LIVE -> "${c.first}/live/$u/$p/$sid.${ext.ifEmpty { "ts" }}"
            Media.MOVIES -> "${c.first}/movie/$u/$p/$sid.${ext.ifEmpty { "mp4" }}"
            Media.SERIES -> "${c.first}/series/$u/$p/$sid.${ext.ifEmpty { "mp4" }}"
        }
    }

    override fun categories(media: Media): List<Category> {
        fallback?.let { return it.categories(media) }
        val action = when (media) {
            Media.LIVE -> "get_live_categories"
            Media.MOVIES -> "get_vod_categories"
            Media.SERIES -> "get_series_categories"
        }
        var last: Exception? = null
        for (agent in listOf(ua) + AGENTS.filter { it != ua }) {
            try {
                val out = asRows(api(action, agent = agent)).map { Category(it.s("category_id"), it.s("category_name").ifEmpty { "Other" }) }
                if (out.isNotEmpty()) {
                    ua = agent
                    return out.filterNot { Adult.text(it.title) }
                }
            } catch (e: Exception) {
                last = e
            }
        }
        val info = runCatching { api("") as? JsonObject }.getOrNull()
        val ui = info?.get("user_info") as? JsonObject
        if (ui != null && (ui.s("auth") == "0" || ui.s("auth") == "false")) throw ProviderError("The server refused this login (wrong details or an expired line)", 401)
        if (ui != null && ui.s("status").isNotEmpty() && !ui.s("status").equals("active", true)) throw ProviderError("This line is " + ui.s("status").lowercase(), 403)
        // last way in: the same line's M3U playlist
        try {
            val m = M3u(source.copy(portal = Sources.xtreamUrl(c.first, c.second, c.third), kind = SourceKind.M3U), http)
            val cats = m.categories(media)
            if (cats.isNotEmpty()) {
                fallback = m
                return cats
            }
        } catch (e: Exception) {
            last = last ?: e
        }
        if (ui == null && last != null) throw (last as? ProviderError ?: ProviderError(last.message ?: "Server unreachable"))
        return emptyList()
    }

    private fun normalise(media: Media, rows: List<JsonObject>): List<Item> = rows.filterNot { Adult.row(it) }.mapIndexed { pos, row ->
        when (media) {
            Media.LIVE -> {
                val sid = row.s("stream_id")
                val url = streamUrl(Media.LIVE, sid, "ts")
                Item("xt-live-$sid", row.s("name").ifEmpty { "Channel" }, media, row.s("stream_icon"), row.s("num").ifEmpty { (pos + 1).toString() }, raw = row.plus("cmd" to url, "url" to url))
            }
            Media.MOVIES -> {
                val sid = row.s("stream_id")
                val url = streamUrl(Media.MOVIES, sid, row.s("container_extension"))
                Item("xt-vod-$sid", cleanTitle(row.s("name").ifEmpty { "Movie" }), media, row.s("cover_big", "movie_image", "stream_icon", "cover"), year = row.s("year", "releaseDate", "release_date").take(4), rating = row.s("rating").takeIf { it != "0" } ?: "", plot = row.s("plot", "description"), raw = row.plus("cmd" to url, "url" to url))
            }
            Media.SERIES -> {
                val sid = row.s("series_id")
                Item("xt-series-$sid", cleanTitle(row.s("name").ifEmpty { "Series" }), media, row.s("cover", "cover_big", "stream_icon"), year = row.s("year", "releaseDate", "release_date").take(4), rating = row.s("rating").takeIf { it != "0" } ?: "", plot = row.s("plot"), raw = row)
            }
        }
    }

    fun list(media: Media, category: String): List<Item> {
        val key = media.name + ":" + category
        cache[key]?.let { return it }
        val action = when (media) {
            Media.LIVE -> "get_live_streams"
            Media.MOVIES -> "get_vod_streams"
            Media.SERIES -> "get_series"
        }
        val rows = normalise(media, asRows(api(action, if (category.isNotEmpty() && category != "*") mapOf("category_id" to category) else emptyMap())))
        cache[key] = rows
        return rows
    }

    override fun page(media: Media, category: String, page: Int): Page {
        fallback?.let { return it.page(media, category, page) }
        val rows = list(media, category)
        val start = (page - 1) * PAGE
        return Page(rows.drop(start).take(PAGE), rows.size, start + PAGE < rows.size)
    }

    override fun seasons(series: Item): List<Season> {
        fallback?.let { return it.seasons(series) }
        val sid = series.raw.s("series_id").ifEmpty { series.id.removePrefix("xt-series-") }
        val info = api("get_series_info", mapOf("series_id" to sid)) as? JsonObject ?: return emptyList()
        val eps = info["episodes"]
        val byNumber: Map<String, JsonArray> = when (eps) {
            is JsonArray -> mapOf("1" to eps)
            is JsonObject -> eps.mapNotNull { (k, v) -> (v as? JsonArray)?.let { k to it } }.toMap()
            else -> emptyMap()
        }
        val meta = (info["seasons"] as? JsonArray)?.mapNotNull { it as? JsonObject }?.associateBy { it.s("season_number") } ?: emptyMap()
        return byNumber.keys.sortedBy { it.toIntOrNull() ?: 999 }.map { n ->
            val list = byNumber[n]!!.mapNotNull { it as? JsonObject }.map { e ->
                val eid = e.s("id")
                val num = e.s("episode_num").ifEmpty { "0" }
                val url = streamUrl(Media.SERIES, eid, e.s("container_extension"))
                val inf = e["info"] as? JsonObject ?: JsonObject(emptyMap())
                Item("xt-ep-$eid", e.s("title").ifEmpty { "Episode $num" }, Media.SERIES, inf.s("movie_image").ifEmpty { series.image }, num, plot = inf.s("plot"), raw = e.plus("cmd" to url, "url" to url))
            }
            Season("xs-$sid-$n", n, meta[n]?.s("name")?.ifEmpty { null } ?: "Season $n", list)
        }
    }

    override fun details(item: Item): Details {
        if (fallback != null) return super.details(item)
        return try {
            if (item.media == Media.MOVIES) {
                val inf = (api("get_vod_info", mapOf("vod_id" to item.raw.s("stream_id"))) as? JsonObject)?.get("info") as? JsonObject ?: JsonObject(emptyMap())
                val secs = inf.s("duration_secs").toIntOrNull()
                Details(inf.s("plot", "description").ifEmpty { item.plot }, inf.s("releasedate", "release_date").take(4).ifEmpty { item.year }, inf.s("rating").ifEmpty { item.rating }, inf.s("genre"), if (secs != null && secs > 0) "${secs / 60} min" else "", firstOf(inf["backdrop_path"]), inf.s("movie_image", "cover_big").ifEmpty { item.image })
            } else {
                val inf = (api("get_series_info", mapOf("series_id" to item.raw.s("series_id"))) as? JsonObject)?.get("info") as? JsonObject ?: JsonObject(emptyMap())
                Details(inf.s("plot").ifEmpty { item.plot }, inf.s("releaseDate", "release_date").take(4).ifEmpty { item.year }, inf.s("rating").ifEmpty { item.rating }, inf.s("genre"), "", firstOf(inf["backdrop_path"]), inf.s("cover").ifEmpty { item.image })
            }
        } catch (_: Exception) {
            super.details(item)
        }
    }

    override fun ticket(item: Item, seriesNumber: String?): JsonObject {
        val u = item.raw.s("url", "cmd")
        if (u.isEmpty()) throw ProviderError("This item has no stream", 404)
        return jsonOf("mode" to "direct", "u" to u, "h" to jsonOf("User-Agent" to ua), "ext" to u.substringBefore("?").substringAfterLast(".", "ts"))
    }
}

/* Names like "EN - Title (2020) [4K]" → "Title (2020)": what the website does. */
fun cleanTitle(name: String): String {
    var t = name.trim()
    t = t.replace(Regex("^\\s*(?:[A-Z]{2,4}|[|•★\\[]\\s*[A-Z]{2,4}\\s*[|\\]])\\s*[-|:•]\\s+"), "")
    t = t.replace(Regex("\\s*[\\[(](?:4K|UHD|FHD|HD|SD|HEVC|H\\.?265|MULTI|SUB|DUB|VOSTFR)[\\])]\\s*", RegexOption.IGNORE_CASE), " ")
    return t.trim().ifEmpty { name.trim() }
}
